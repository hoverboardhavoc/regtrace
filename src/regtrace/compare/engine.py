"""Comparison engine.

Three modes (per-vector metadata):
  register_writes : ordered list of writes; reads ignored
  final_state     : unordered set of (address, final_value); reads ignored
  with_polling    : ordered writes + reads; polling target is part of the assertion

All modes are width-strict: W4 to address X never compares equal to W2+W2
covering the same bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import targets as targets_mod, vectors as vectors_mod
from ..build.pipeline import build_one
from ..trace.extractor import ExtractedTrace, extract


@dataclass
class TraceLine:
    op: str          # "W" | "R"
    size: int
    address_str: str # symbolic, e.g. "<TIM1_BASE>+0x00"
    value: int

    @property
    def key(self) -> tuple:
        return (self.op, self.size, self.address_str, self.value)


def _parse_trace_text(text: str) -> tuple[list[TraceLine], dict[str, str]]:
    """Parse a .trace file's records (and headers) into structured form."""
    headers: dict[str, str] = {}
    lines: list[TraceLine] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("#"):
            body = s[1:].strip()
            if ":" in body:
                k, v = body.split(":", 1)
                headers[k.strip()] = v.strip()
            continue
        # Strip inline comment.
        if "#" in s:
            s = s[:s.index("#")].rstrip()
        parts = s.split()
        if len(parts) < 3:
            continue
        op_token = parts[0]
        op, size = op_token[0], int(op_token[1:])
        addr = parts[1]
        value = int(parts[2], 0)
        lines.append(TraceLine(op=op, size=size, address_str=addr, value=value))
    return lines, headers


def _trace_lines_from_extracted(t: ExtractedTrace) -> list[TraceLine]:
    out: list[TraceLine] = []
    for ev in t.events:
        sym = t.target.symbolise(ev.address) if t.target else f"0x{ev.address:08X}"
        out.append(TraceLine(op=ev.op, size=ev.size, address_str=sym, value=ev.value))
    return out


@dataclass
class CompareResult:
    matched: bool
    mode: str
    summary: str
    diff: list[str]


def _parse_range(expr: str) -> tuple[str, int, int]:
    """Parse `<SYMBOL>+0xLO..0xHI` (or `<SYMBOL>+0xOFFSET` as a single-byte range).

    Returns (symbol, lo_offset, hi_offset). Both offsets are inclusive.
    """
    if not expr.startswith("<"):
        raise ValueError(f"filter expr must start with `<SYMBOL>`: {expr!r}")
    end = expr.index(">")
    sym = expr[1:end]
    rest = expr[end + 1:]
    if not rest:
        return (sym, 0, 0xFFFFFFFF)
    if not rest.startswith("+"):
        raise ValueError(f"malformed filter expr: {expr!r}")
    rest = rest[1:]
    if ".." in rest:
        lo_s, hi_s = rest.split("..", 1)
        return (sym, int(lo_s, 0), int(hi_s, 0))
    off = int(rest, 0)
    return (sym, off, off)


def _line_matches_range(line: TraceLine, sym: str, lo: int, hi: int) -> bool:
    """True if `line.address_str` is within `<sym>+lo..hi`."""
    s = line.address_str
    if not s.startswith(f"<{sym}>"):
        return False
    rest = s[len(sym) + 2:]
    if not rest:
        offset = 0
    elif rest.startswith("+"):
        offset = int(rest[1:], 0)
    else:
        return False
    return lo <= offset <= hi


def apply_filters(lines: list[TraceLine],
                  assert_only: tuple[str, ...] = (),
                  ignore: tuple[str, ...] = ()) -> list[TraceLine]:
    """Filter trace lines per a vector's `assert_only` (whitelist) or `ignore`
    (blacklist). Mutually exclusive — caller validates that."""
    if assert_only:
        ranges = [_parse_range(e) for e in assert_only]
        return [l for l in lines if any(_line_matches_range(l, *r) for r in ranges)]
    if ignore:
        ranges = [_parse_range(e) for e in ignore]
        return [l for l in lines if not any(_line_matches_range(l, *r) for r in ranges)]
    return lines


def compare(mode: str, a: list[TraceLine], a_label: str, b: list[TraceLine], b_label: str) -> CompareResult:
    if mode == "register_writes":
        a_w = [x for x in a if x.op == "W"]
        b_w = [x for x in b if x.op == "W"]
        return _diff_ordered(mode, a_w, a_label, b_w, b_label)
    if mode == "with_polling":
        return _diff_ordered(mode, a, a_label, b, b_label)
    if mode == "final_state":
        a_w = [x for x in a if x.op == "W"]
        b_w = [x for x in b if x.op == "W"]
        a_final: dict[str, TraceLine] = {x.address_str: x for x in a_w}
        b_final: dict[str, TraceLine] = {x.address_str: x for x in b_w}
        diff: list[str] = []
        all_keys = sorted(set(a_final) | set(b_final))
        for k in all_keys:
            la, lb = a_final.get(k), b_final.get(k)
            if la is None:
                diff.append(f"  - {b_label}-only: W{lb.size} {lb.address_str} 0x{lb.value:0{lb.size*2}X}")
            elif lb is None:
                diff.append(f"  - {a_label}-only: W{la.size} {la.address_str} 0x{la.value:0{la.size*2}X}")
            elif la.value != lb.value or la.size != lb.size:
                diff.append(
                    f"  - mismatch at {k}: {a_label}=W{la.size}/0x{la.value:X} "
                    f"vs {b_label}=W{lb.size}/0x{lb.value:X}"
                )
        return CompareResult(
            matched=not diff, mode=mode,
            summary=("match" if not diff else f"divergent ({len(diff)} differences)"),
            diff=diff,
        )
    raise ValueError(f"unknown mode {mode!r}")


def _diff_ordered(mode: str, a: list[TraceLine], a_label: str,
                  b: list[TraceLine], b_label: str) -> CompareResult:
    diff: list[str] = []
    n = max(len(a), len(b))
    for i in range(n):
        la = a[i] if i < len(a) else None
        lb = b[i] if i < len(b) else None
        if la is None:
            diff.append(f"  [{i:3d}] {b_label}-only: {lb.op}{lb.size} {lb.address_str} 0x{lb.value:0{lb.size*2}X}")
        elif lb is None:
            diff.append(f"  [{i:3d}] {a_label}-only: {la.op}{la.size} {la.address_str} 0x{la.value:0{la.size*2}X}")
        elif la.key != lb.key:
            diff.append(
                f"  [{i:3d}] mismatch: {a_label}={la.op}{la.size} {la.address_str} 0x{la.value:0{la.size*2}X} "
                f"vs {b_label}={lb.op}{lb.size} {lb.address_str} 0x{lb.value:0{lb.size*2}X}"
            )
    matched = not diff
    summary = (
        f"match: {min(len(a), len(b))}/{max(len(a), len(b))} entries identical"
        if matched else f"divergent ({len(diff)} differences)"
    )
    return CompareResult(matched=matched, mode=mode, summary=summary, diff=diff)


def _find_vector(vector_id: str) -> vectors_mod.Vector:
    from ..paths import vectors_dir
    for yaml in vectors_dir().rglob("*.yaml"):
        if f"{yaml.parent.name}_{yaml.stem}" == vector_id:
            return vectors_mod.load(yaml)
    raise FileNotFoundError(f"no vector matches id {vector_id!r}")


def run_compare(
    vector: str,
    against: str | None,
    against_trace: Path | None,
    all_pairs: bool,
    target: str | None,
) -> int:
    vec = _find_vector(vector)

    if against_trace is not None:
        # Build + extract this vector for the implementation matching the
        # given target (or single declared impl), then diff against the file.
        slug = _slug_for_target(vec, target)
        result = build_one(vec, slug)
        tgt = targets_mod.load(result.target)
        live = extract(result.elf_path, target=tgt, vector=vec)
        live_lines = _trace_lines_from_extracted(live)
        golden_text = Path(against_trace).read_text()
        golden_lines, golden_headers = _parse_trace_text(golden_text)
        live_lines = apply_filters(live_lines, vec.assert_only, vec.ignore)
        golden_lines = apply_filters(golden_lines, vec.assert_only, vec.ignore)
        cr = compare(vec.mode, live_lines, "live", golden_lines, "golden")
        return _print_compare(vec, slug, "golden:" + str(against_trace), cr)

    if all_pairs:
        slugs = list(vec.implementations.keys())
        rc = 0
        for i in range(len(slugs)):
            for j in range(i + 1, len(slugs)):
                rc |= _compare_two(vec, slugs[i], slugs[j])
        return rc

    if against is not None:
        pair = [s.strip() for s in against.split(",")]
        if len(pair) != 2:
            print(f"[error] --against= expects exactly 2 slugs, got {len(pair)}: {pair!r}")
            return 2
        a, b = pair
    else:
        a, b = vec.canonical_pair()

    return _compare_two(vec, a, b)


def _slug_for_target(vec: vectors_mod.Vector, target: str | None) -> str:
    if target is None:
        if len(vec.implementations) == 1:
            return next(iter(vec.implementations))
        raise ValueError(
            "--target= is required when vector has multiple implementations and --against-trace is used"
        )
    matches = [s for s, impl in vec.implementations.items() if impl.target == target]
    if not matches:
        raise ValueError(f"vector has no implementation with target={target!r}")
    if len(matches) > 1:
        raise ValueError(f"vector has multiple implementations with target={target!r}: {matches}")
    return matches[0]


def _compare_two(vec: vectors_mod.Vector, a_slug: str, b_slug: str) -> int:
    a_build = build_one(vec, a_slug)
    b_build = build_one(vec, b_slug)
    a_target = targets_mod.load(a_build.target)
    b_target = targets_mod.load(b_build.target)
    a_trace = extract(a_build.elf_path, target=a_target, vector=vec)
    b_trace = extract(b_build.elf_path, target=b_target, vector=vec)
    a_lines = apply_filters(_trace_lines_from_extracted(a_trace), vec.assert_only, vec.ignore)
    b_lines = apply_filters(_trace_lines_from_extracted(b_trace), vec.assert_only, vec.ignore)
    cr = compare(vec.mode, a_lines, a_slug, b_lines, b_slug)
    return _print_compare(vec, a_slug, b_slug, cr)


def _print_compare(vec: vectors_mod.Vector, a_label: str, b_label: str, cr: CompareResult) -> int:
    print(f"vector: {vec.vector_id}  mode: {cr.mode}")
    print(f"  {a_label}  vs  {b_label}")
    print(f"  {cr.summary}")
    for line in cr.diff:
        print(line)
    return 0 if cr.matched else 1
