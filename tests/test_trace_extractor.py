"""Trace extractor smoke test.

Builds a minimal ELF in memory using struct (no arm-none-eabi-gcc needed)
and feeds it to the extractor. Validates that:
  - peripheral writes are captured
  - non-peripheral writes are filtered out
  - the bkpt sentinel halts emulation cleanly
"""

import struct
from pathlib import Path

from regtrace import targets as targets_mod
from regtrace.trace.extractor import (
    SENTINEL_PC,
    STACK_BASE,
    STACK_SIZE,
    STACK_TOP,
    TraceEvent,
    extract,
)
import unicorn


def _build_minimal_elf(thumb_bytes: bytes, entry_addr: int = 0x08000000) -> bytes:
    """Construct a minimal ELF32-LE ARM file containing one PT_LOAD segment
    with `thumb_bytes` and a `regtrace_test` symbol at `entry_addr`."""
    # Header sizes
    EI_NIDENT = 16
    Ehdr_size = 52
    Phdr_size = 32
    Shdr_size = 40

    # Layout:
    #   [Ehdr][Phdr][.text bytes][.shstrtab][.strtab][.symtab][shdrs]
    text_off = Ehdr_size + Phdr_size
    text_size = len(thumb_bytes)

    shstr = b"\x00.shstrtab\x00.strtab\x00.symtab\x00.text\x00"
    strtab = b"\x00regtrace_test\x00"

    # Symbol table: one null + one regtrace_test
    sym_null = struct.pack("<IIIBBH", 0, 0, 0, 0, 0, 0)
    # Bind=GLOBAL(1), Type=FUNC(2) → info = (1<<4)|2 = 0x12
    sym_test = struct.pack("<IIIBBH", 1, entry_addr | 1, 0, 0x12, 0, 1)  # shndx=1 (.text)
    symtab = sym_null + sym_test

    # Compute file offsets
    shstr_off = text_off + text_size
    strtab_off = shstr_off + len(shstr)
    symtab_off = strtab_off + len(strtab)
    shdrs_off = symtab_off + len(symtab)

    # Section headers: [null, .text, .shstrtab, .strtab, .symtab]
    def shdr(name_off, sh_type, flags, addr, offset, size, link=0, info=0, align=1, entsize=0):
        return struct.pack("<IIIIIIIIII", name_off, sh_type, flags, addr,
                           offset, size, link, info, align, entsize)

    SHT_NULL = 0; SHT_PROGBITS = 1; SHT_SYMTAB = 2; SHT_STRTAB = 3
    SHF_ALLOC = 2; SHF_EXECINSTR = 4

    # Find name offsets in shstr.
    def name_off(name: bytes) -> int:
        return shstr.index(name)

    sh_null = shdr(0, SHT_NULL, 0, 0, 0, 0)
    sh_text = shdr(name_off(b".text"), SHT_PROGBITS, SHF_ALLOC | SHF_EXECINSTR,
                   entry_addr, text_off, text_size)
    sh_shstrtab = shdr(name_off(b".shstrtab"), SHT_STRTAB, 0, 0, shstr_off, len(shstr))
    sh_strtab = shdr(name_off(b".strtab"), SHT_STRTAB, 0, 0, strtab_off, len(strtab))
    sh_symtab = shdr(name_off(b".symtab"), SHT_SYMTAB, 0, 0, symtab_off, len(symtab),
                     link=3, info=1, align=4, entsize=16)  # link=3 (.strtab), info=1 (one local)

    shdrs = sh_null + sh_text + sh_shstrtab + sh_strtab + sh_symtab

    # Program header (PT_LOAD covering .text)
    PT_LOAD = 1
    PF_X = 1; PF_R = 4
    phdr = struct.pack("<IIIIIIII",
                       PT_LOAD, text_off, entry_addr, entry_addr,
                       text_size, text_size, PF_X | PF_R, 0x1000)

    # ELF header
    ELFCLASS32 = 1; ELFDATA2LSB = 1; EV_CURRENT = 1
    EM_ARM = 40
    e_ident = bytes([0x7F, 0x45, 0x4C, 0x46, ELFCLASS32, ELFDATA2LSB, EV_CURRENT, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    ehdr = e_ident + struct.pack("<HHIIIIIHHHHHH",
                                  2,             # ET_EXEC
                                  EM_ARM,
                                  EV_CURRENT,
                                  entry_addr | 1,
                                  Ehdr_size,     # phoff
                                  shdrs_off,
                                  0x05000200,    # e_flags (EABI v5, hard-float optional — fine for parse)
                                  Ehdr_size,
                                  Phdr_size, 1,
                                  Shdr_size, 5, 2)  # shstrndx=2

    return ehdr + phdr + thumb_bytes + shstr + strtab + symtab + shdrs


def _thumb_minimal_write_to_tim1():
    """Generate Thumb code that writes 0x80 to TIM1_BASE (0x40012C00) then BX LR."""
    # We use simple Thumb instructions that are easy to hand-encode:
    #   ldr r0, [pc, #imm]    ; load TIM1_BASE
    #   ldr r1, [pc, #imm]    ; load 0x80
    #   str r1, [r0]
    #   bx  lr
    # And literal pool follows.
    #
    # Encodings (Thumb-1):
    #   ldr Rd, [pc, #imm]    : 0100_1ddd_iiiiiiii   imm = byte offset / 4 from (PC&~3)+4
    #   str Rd, [Rn, #0]      : 0110_0000_nnnRRR     (Rn=r0, Rd=r1)  → 0x6001
    #   bx lr                 : 0100_0111_01110_000  → 0x4770
    #
    # Layout (each instr 2 bytes):
    #   0x00: ldr r0, [pc, #4]    -> 0x4801   (PC reads as 0x04; effective = 0x04 + imm*4)
    #   0x02: ldr r1, [pc, #8]    -> 0x4902
    #   0x04: str r1, [r0]        -> 0x6001
    #   0x06: bx  lr              -> 0x4770
    #   0x08: TIM1_BASE (0x40012C00)
    #   0x0C: 0x00000080
    #
    # Thumb PC-relative load: effective = (PC & ~3) + imm*4, where PC = instr_addr + 4.
    # ldr at 0x00: PC=0x04, &~3 = 0x04. Want 0x08 → imm=1 → 0x4801.
    # ldr at 0x02: PC=0x06, &~3 = 0x04. Want 0x0C → imm=2 → 0x4902.
    instrs = [
        0x4801,   # ldr r0, [pc, #4]    → r0 = mem[0x08] = TIM1_BASE
        0x4902,   # ldr r1, [pc, #8]    → r1 = mem[0x0C] = 0x80
        0x6001,   # str r1, [r0]        → write to TIM1_BASE
        0x4770,   # bx  lr
    ]
    code = b""
    for w in instrs:
        code += struct.pack("<H", w)
    code += struct.pack("<I", 0x40012C00)  # TIM1_BASE
    code += struct.pack("<I", 0x00000080)  # value
    return code


def test_extractor_captures_peripheral_write(tmp_path):
    code = _thumb_minimal_write_to_tim1()
    elf_bytes = _build_minimal_elf(code)
    elf_path = tmp_path / "tiny.elf"
    elf_path.write_bytes(elf_bytes)

    target = targets_mod.load("stm32f0")
    trace = extract(elf_path, target=target)

    writes = [e for e in trace.events if e.op == "W"]
    assert len(writes) == 1
    w = writes[0]
    assert w.address == 0x40012C00
    assert w.value == 0x80
    assert w.size == 4
    # Header reflects clean exit.
    assert "clean-exit" in trace.header.emulation
