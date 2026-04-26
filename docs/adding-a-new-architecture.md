# Adding a new architecture

regtrace's per-architecture seam is small — adding RISC-V on top of the existing ARM/Cortex-M backend was about 50 lines of code (v0.6). Other architectures should be similar effort.

The seam:
- Unicorn arch flag (`UC_ARCH_ARM` vs `UC_ARCH_RISCV` vs `UC_ARCH_X86` ...)
- Unicorn mode (`UC_MODE_THUMB`, `UC_MODE_RISCV32`, etc.)
- Per-architecture register names (SP, return address, PC quirks)
- Halt-instruction encoding (`BKPT`, `EBREAK`, `INT3`, ...)
- For non-MMIO architectures (RISC-V CSR, x86 I/O ports), an additional Unicorn hook

## 1. Toolchain

Add the cross-compiler to PATH. xPack distributions are the easiest: download a tarball, symlink the `bin/` entries into a directory already on PATH (e.g., `~/.local/bin/`).

## 2. Compile flags + toolchain prefix

In `src/regtrace/build/pipeline.py`:

```python
TARGET_FLAGS["my-arch-target"] = (
    "-Os", "-march=...", "-mabi=...",
    "-fno-common", "-ffreestanding", "-fno-builtin", "-Wall",
)

TARGET_TOOLCHAIN_PREFIX["my-arch-target"] = "myarch-none-elf-"
```

The `toolchain_prefix(target)` helper returns the prefix used to find `gcc`, `ar`, etc. — defaults to `arm-none-eabi-` if the target isn't listed.

## 3. Extractor dispatch

In `src/regtrace/trace/extractor.py`, the `extract()` function picks the Unicorn arch:

```python
elif target.unicorn_arch == "myarch":
    uc = unicorn.Uc(unicorn.UC_ARCH_MYARCH, unicorn.UC_MODE_MYARCH32)
    is_my_arch = True
```

You'll also need:
- The right register constants (`unicorn.myarch_const.UC_MYARCH_REG_SP`, `_RA`, etc.).
- The halt-instruction encoding written to `SENTINEL_PC`. RISC-V uses `EBREAK` (0x00100073, 32-bit). x86 uses `INT3` (0xCC). ARM Thumb uses `BKPT #imm` (0xBE+imm).
- The PC dispatch convention. ARM Thumb sets bit 0 of LR/PC; RISC-V doesn't.

For architectures with non-MMIO I/O (RISC-V CSR, x86 I/O port), you'll need an extra hook beyond `UC_HOOK_MEM_WRITE`. RISC-V's `csrrw`/`csrrs`/`csrrc` are visible to Unicorn via the CSR-access hook.

## 4. Startup + linker

`build_assets/<library>/<arch-target>/`:
- `startup.S` — uses architecture-appropriate instructions (RISC-V `la sp, _estack; la ra, _sentinel; call regtrace_test; ebreak`).
- `link.ld` — same shape as ARM, just no Thumb-specific flags.

## 5. Targets file

`targets/<target>.toml` declares `unicorn_arch` and `unicorn_mode` so the extractor dispatches correctly. Per-architecture quirks (RISC-V's lack of bit-banding aliases, x86's I/O port range) get an empty table for fields that don't apply.

## 6. Validation

Build a vector for the new architecture against an existing HAL (vendor SPLs are usually available for multiple architectures of the same chip family). Run `regtrace compare <vector> --all-pairs` against ARM impls of the same vector. If the trace matches in `final_state` mode, the cross-architecture seam is working.

This is exactly what v0.6 did for RISC-V (GD32VF103) — TIM1 PWM init produces a matching trace to the ARM GD32F103 / STM32F1 because the silicon is the same.
