"""Unicorn-based register-trace extractor.

Loads a snippet ELF, sets up Unicorn, hooks peripheral memory accesses, and
emits a `.trace` file.
"""

from __future__ import annotations

import datetime as dt
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import unicorn
from elftools.elf.elffile import ELFFile

from .. import __version__, targets as targets_mod, vectors as vectors_mod


# Stack and sentinel layout in the emulator's address space.
STACK_BASE = 0x20000000
STACK_SIZE = 8 * 1024
STACK_TOP = STACK_BASE + STACK_SIZE
SENTINEL_BASE = 0x10000000
SENTINEL_SIZE = 0x1000
SENTINEL_PC = SENTINEL_BASE
PERIPHERAL_PAGE_SIZE = 0x10000

DEFAULT_STEP_CAP = 100_000


@dataclass
class TraceEvent:
    op: str           # "W" or "R"
    address: int
    value: int
    size: int


@dataclass
class TraceHeader:
    vector_id: str = ""
    library: str = ""
    library_commit: str = ""
    target: str = ""
    compiler: str = ""
    compile_flags: str = ""
    emulator: str = ""
    emulation: str = ""
    mode: str = "register_writes"

    def render(self, captured_iso: str) -> str:
        lines = [
            f"# regtrace v{__version__} — captured {captured_iso}",
            f"# vector:         {self.vector_id}",
            f"# library:        {self.library}",
            f"# library_commit: {self.library_commit}",
            f"# target:         {self.target}",
            f"# compiler:       {self.compiler}",
            f"# compile_flags:  {self.compile_flags}",
            f"# emulator:       {self.emulator}",
            f"# emulation:      {self.emulation}",
            f"# mode:           {self.mode}",
        ]
        return "\n".join(lines)


@dataclass
class ExtractedTrace:
    header: TraceHeader
    events: list[TraceEvent] = field(default_factory=list)
    target: targets_mod.Target | None = None

    def render(self, captured_iso: str | None = None) -> str:
        captured = captured_iso or _now_iso()
        lines = [self.header.render(captured)]
        for ev in self.events:
            sym = self.target.symbolise(ev.address) if self.target else f"0x{ev.address:08X}"
            comment = ""
            if self.target and self.target.peripheral_bases:
                # Comment from register_names if available.
                # Find the symbol whose base is closest below the address.
                best_name = None
                best_base = 0
                for name, base in self.target.peripheral_bases.items():
                    if base <= ev.address and base > best_base:
                        best_name = name
                        best_base = base
                if best_name and best_name in self.target.register_names:
                    offset = ev.address - best_base
                    if offset in self.target.register_names[best_name]:
                        comment = "         # " + self.target.register_names[best_name][offset]
            lines.append(
                f"{ev.op}{ev.size} {sym} 0x{ev.value:0{ev.size*2}X}{comment}"
            )
        return "\n".join(lines) + "\n"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class ELFInfo:
    entry_addr: int
    sentinel_loaded_at: int  # the address Unicorn maps the sentinel page to
    segments: list[tuple[int, bytes]]  # (vaddr, bytes) of LOADable segments
    symbols: dict[str, int]


def load_elf(elf_path: Path) -> ELFInfo:
    """Return the loadable layout + symbol table from a snippet ELF."""
    with open(elf_path, "rb") as f:
        ef = ELFFile(f)
        segments: list[tuple[int, bytes]] = []
        for seg in ef.iter_segments():
            if seg["p_type"] != "PT_LOAD":
                continue
            vaddr = seg["p_vaddr"]
            data = seg.data()
            if seg["p_filesz"] < seg["p_memsz"]:
                # bss-style fill with zeros up to memsz
                data = data + b"\x00" * (seg["p_memsz"] - seg["p_filesz"])
            segments.append((vaddr, data))
        symbols: dict[str, int] = {}
        symtab = ef.get_section_by_name(".symtab")
        if symtab is None:
            raise RuntimeError(f"{elf_path} has no .symtab — was it stripped?")
        for sym in symtab.iter_symbols():
            if sym.name:
                symbols[sym.name] = sym["st_value"]
    if "regtrace_test" not in symbols:
        raise RuntimeError(f"{elf_path}: regtrace_test symbol not found")
    return ELFInfo(
        entry_addr=symbols["regtrace_test"],
        sentinel_loaded_at=symbols.get("_sentinel", SENTINEL_PC),
        segments=segments,
        symbols=symbols,
    )


def _align_down(v: int, page: int) -> int:
    return v & ~(page - 1)


def _align_up(v: int, page: int) -> int:
    return (v + page - 1) & ~(page - 1)


def _map_page_aligned(uc: unicorn.Uc, base: int, size: int, page: int = 0x1000) -> tuple[int, int]:
    a_base = _align_down(base, page)
    a_end = _align_up(base + size, page)
    a_size = max(a_end - a_base, page)
    uc.mem_map(a_base, a_size)
    return (a_base, a_size)


def _ensure_mapped(uc: unicorn.Uc, mapped: dict[int, int], addr: int, size: int = 4) -> None:
    """Map a page covering [addr, addr+size) if not already mapped."""
    page = PERIPHERAL_PAGE_SIZE
    base = _align_down(addr, page)
    end = _align_up(addr + size, page)
    cur = base
    while cur < end:
        if cur not in mapped:
            try:
                uc.mem_map(cur, page)
                mapped[cur] = page
            except unicorn.UcError:
                # Already mapped (overlap with a different alignment); ignore.
                mapped[cur] = page
        cur += page


@dataclass
class _ReadSequenceState:
    values: list[int]
    index: int = 0

    def next_value(self) -> int:
        if self.index < len(self.values):
            v = self.values[self.index]
            self.index += 1
        else:
            v = self.values[-1]  # last value sticks
        return v


def _resolve_read_responses(
    target: targets_mod.Target,
    raw: dict[str, int | list[int]],
) -> dict[int, _ReadSequenceState]:
    """Translate symbolic addresses (`<TIM1_BASE>+0x10`) to numeric, normalised to sequences."""
    out: dict[int, _ReadSequenceState] = {}
    for sym_addr, value in raw.items():
        addr = _resolve_symbolic(target, sym_addr)
        if isinstance(value, list):
            out[addr] = _ReadSequenceState(values=list(value))
        else:
            out[addr] = _ReadSequenceState(values=[value])
    return out


def _resolve_symbolic(target: targets_mod.Target, expr: str) -> int:
    """Parse `<SYMBOL>+0xOFFSET` (or `<SYMBOL>`) into a numeric address."""
    if not expr.startswith("<"):
        return int(expr, 0)
    end = expr.index(">")
    sym = expr[1:end]
    rest = expr[end + 1:]
    base = target.peripheral_bases[sym]
    if not rest:
        return base
    if not rest.startswith("+"):
        raise ValueError(f"malformed symbolic address {expr!r}")
    return base + int(rest[1:], 0)


def extract(
    elf_path: Path,
    target: targets_mod.Target,
    vector: vectors_mod.Vector | None = None,
    debug: bool = False,
    step_cap: int = DEFAULT_STEP_CAP,
) -> ExtractedTrace:
    """Run the snippet under Unicorn, capturing peripheral writes/reads."""
    info = load_elf(elf_path)

    if target.unicorn_arch != "arm":
        raise NotImplementedError(f"unicorn_arch {target.unicorn_arch!r} not yet supported")
    uc = unicorn.Uc(unicorn.UC_ARCH_ARM, unicorn.UC_MODE_THUMB)
    mapped: dict[int, int] = {}

    # Map and load ELF segments.
    for vaddr, data in info.segments:
        _ensure_mapped(uc, mapped, vaddr, len(data))
        uc.mem_write(vaddr, data)

    # Map RAM/stack.
    _ensure_mapped(uc, mapped, STACK_BASE, STACK_SIZE)

    # Map sentinel page and write a bkpt instruction at SENTINEL_PC.
    _ensure_mapped(uc, mapped, SENTINEL_BASE, SENTINEL_SIZE)
    # Thumb BKPT #0 = 0xBE00. We use #0x55 (0xBE55) for grep-ability.
    uc.mem_write(SENTINEL_PC, b"\x55\xBE")

    # Map peripheral ranges lazily on first access via UC_HOOK_MEM_INVALID,
    # but seeding reset values requires mapping them up front. So map any base
    # that has a reset-values entry.
    for sym, regs in target.reset_values.items():
        if sym not in target.peripheral_bases:
            continue
        base = target.peripheral_bases[sym]
        _ensure_mapped(uc, mapped, base, max(regs.keys()) + 4)
        for offset, val in regs.items():
            uc.mem_write(base + offset, val.to_bytes(4, "little"))

    # Resolve read_responses.
    read_state: dict[int, _ReadSequenceState] = {}
    if vector and vector.read_responses:
        read_state = _resolve_read_responses(target, vector.read_responses)

    events: list[TraceEvent] = []

    def hook_mem_write(uc, access, address, size, value, user_data):
        if target.is_peripheral(address):
            # Apply bit-band alias translation (Cortex-M3 only — empty otherwise).
            if target.bit_band_aliases:
                for alias_base, real_base in target.bit_band_aliases.items():
                    if alias_base <= address < alias_base + 0x02000000:
                        # 32 alias addresses per real word — translate.
                        offset_bits = (address - alias_base) // 4
                        real_addr = real_base + (offset_bits // 8) * 4
                        bit = offset_bits % 8
                        old = int.from_bytes(uc.mem_read(real_addr, 4), "little")
                        new = (old & ~(1 << bit)) | ((value & 1) << bit)
                        events.append(TraceEvent("W", real_addr, new, 4))
                        uc.mem_write(real_addr, new.to_bytes(4, "little"))
                        return
            events.append(TraceEvent("W", address, value & ((1 << (size * 8)) - 1), size))

    def hook_mem_read(uc, access, address, size, value, user_data):
        if target.is_peripheral(address):
            # Apply read-response override if present.
            if address in read_state:
                v = read_state[address].next_value()
                uc.mem_write(address, v.to_bytes(4, "little"))
                events.append(TraceEvent("R", address, v & ((1 << (size * 8)) - 1), size))
            else:
                cur = int.from_bytes(uc.mem_read(address, size), "little")
                events.append(TraceEvent("R", address, cur, size))

    def hook_mem_invalid(uc, access, address, size, value, user_data):
        # Lazily map any peripheral page touched by the snippet.
        if target.is_peripheral(address):
            _ensure_mapped(uc, mapped, address, size)
            return True
        return False

    uc.hook_add(unicorn.UC_HOOK_MEM_WRITE, hook_mem_write)
    uc.hook_add(unicorn.UC_HOOK_MEM_READ, hook_mem_read)
    uc.hook_add(
        unicorn.UC_HOOK_MEM_READ_UNMAPPED
        | unicorn.UC_HOOK_MEM_WRITE_UNMAPPED
        | unicorn.UC_HOOK_MEM_FETCH_UNMAPPED,
        hook_mem_invalid,
    )

    # Initialise registers.
    uc.reg_write(unicorn.arm_const.UC_ARM_REG_SP, STACK_TOP)
    uc.reg_write(unicorn.arm_const.UC_ARM_REG_LR, SENTINEL_PC | 1)  # Thumb
    pc = info.entry_addr | 1  # Ensure Thumb mode

    last_pc = pc
    instr_count = 0
    if debug:
        def hook_code(uc, addr, size, ud):
            nonlocal last_pc, instr_count
            last_pc = addr
            instr_count += 1
            print(f"  pc=0x{addr:08X} sz={size}", file=sys.stderr)
        uc.hook_add(unicorn.UC_HOOK_CODE, hook_code)
    else:
        def hook_code(uc, addr, size, ud):
            nonlocal last_pc, instr_count
            last_pc = addr
            instr_count += 1
        uc.hook_add(unicorn.UC_HOOK_CODE, hook_code)

    emulation_status = "clean-exit"
    try:
        # `until=` triggers UC_ERR_OK when PC == until_address; bkpt also halts cleanly.
        uc.emu_start(pc & ~1 | 1, SENTINEL_PC | 0, count=step_cap)
        emulation_status = f"clean-exit (LR sentinel hit at instr {instr_count})"
    except unicorn.UcError as e:
        # BKPT raises UC_ERR_EXCEPTION on most builds, which is the expected
        # halt path. Treat that as a clean exit too.
        if e.errno == unicorn.UC_ERR_EXCEPTION and (last_pc & ~1) == SENTINEL_PC:
            emulation_status = f"clean-exit (BKPT sentinel at instr {instr_count})"
        else:
            emulation_status = f"emulation-error: {e} (last pc=0x{last_pc:08X}, instr {instr_count})"
    if instr_count >= step_cap:
        emulation_status = (
            f"step-cap-hit ({step_cap} instrs); likely polling target near pc=0x{last_pc:08X}"
        )

    header = TraceHeader(
        target=target.name,
        emulator=f"unicorn {unicorn.__version__} (UC_ARCH_ARM, UC_MODE_THUMB)",
        emulation=emulation_status,
        mode=vector.mode if vector else "register_writes",
    )
    return ExtractedTrace(header=header, events=events, target=target)


def _infer_target_from_path(elf_path: Path) -> str:
    """Guess target family from build/<library>/<rev>/<target>/... path layout."""
    parts = elf_path.resolve().parts
    if "build" in parts:
        idx = parts.index("build")
        if idx + 4 < len(parts):
            return parts[idx + 3]
    if "golden" in parts:
        idx = parts.index("golden")
        if idx + 4 < len(parts):
            return parts[idx + 3]
    raise RuntimeError(f"cannot infer target from {elf_path} — pass it explicitly")


def extract_trace_to_stdout(elf_path: Path, debug: bool = False) -> int:
    target_name = _infer_target_from_path(elf_path)
    target = targets_mod.load(target_name)
    trace = extract(elf_path, target=target, debug=debug)
    sys.stdout.write(trace.render())
    return 0


def re_extract(elf_path: Path) -> int:
    """Re-extract a .trace from an existing golden .elf, overwriting the .trace."""
    target_name = _infer_target_from_path(elf_path)
    target = targets_mod.load(target_name)
    trace = extract(elf_path, target=target)
    trace_path = elf_path.with_suffix(".trace")
    trace_path.write_text(trace.render())
    print(f"[re-extract] {trace_path}")
    return 0
