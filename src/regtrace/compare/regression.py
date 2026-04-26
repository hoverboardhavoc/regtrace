"""Regression mode: diff freshly-built traces against a stored golden tree."""

from __future__ import annotations

from pathlib import Path

from .. import targets as targets_mod, vectors as vectors_mod
from ..build.pipeline import build_one
from ..paths import vectors_dir
from ..trace.extractor import extract
from .engine import apply_filters, compare, _parse_trace_text, _trace_lines_from_extracted


def run_regression(baseline: Path) -> int:
    """Walk `baseline/` (golden/<library>/<rev>/), rebuild each vector for
    each (target, vector) pair found, and diff against the stored .trace."""
    baseline = baseline.resolve()
    if not baseline.is_dir():
        print(f"[error] {baseline} is not a directory")
        return 2

    # Layout: baseline = golden/<library>/<rev>/  →  parts[-2]=<library>, parts[-1]=<rev>
    library = baseline.parent.name
    rev = baseline.name

    failed: list[str] = []
    matched: list[str] = []
    for trace_file in sorted(baseline.rglob("*.trace")):
        target = trace_file.parent.name
        vec = _find_vector_by_id(trace_file.stem)
        if vec is None:
            print(f"[skip] {trace_file}: no matching vector found")
            continue
        # Find the implementation slug for (library, target).
        slug = f"{library}/{target}"
        if slug not in vec.implementations:
            print(f"[skip] {trace_file}: vector has no implementation {slug!r}")
            continue
        try:
            built = build_one(vec, slug, rev=rev)
            tgt = targets_mod.load(target)
            live = extract(built.elf_path, target=tgt, vector=vec)
            live_lines = apply_filters(_trace_lines_from_extracted(live), vec.assert_only, vec.ignore)
            golden_lines, _ = _parse_trace_text(trace_file.read_text())
            golden_lines = apply_filters(golden_lines, vec.assert_only, vec.ignore)
            cr = compare(vec.mode, live_lines, "live", golden_lines, "golden")
            if cr.matched:
                matched.append(f"{slug}/{vec.vector_id}")
            else:
                failed.append(f"{slug}/{vec.vector_id}: {cr.summary}")
                for line in cr.diff:
                    print(line)
        except Exception as e:
            failed.append(f"{slug}/{vec.vector_id}: {e}")

    print(f"matched: {len(matched)} / {len(matched) + len(failed)}")
    if failed:
        print("FAIL:")
        for f in failed:
            print(f"  {f}")
        return 1
    print(f"PASS — {len(matched)} vectors match {library}/{rev} goldens")
    return 0


def _find_vector_by_id(vector_id: str):
    for yaml in vectors_dir().rglob("*.yaml"):
        if f"{yaml.parent.name}_{yaml.stem}" == vector_id:
            return vectors_mod.load(yaml)
    return None
