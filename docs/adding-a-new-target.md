# Adding a new target (chip family)

A "target" in regtrace is a chip family that shares a peripheral memory layout. Examples: `stm32f0`, `gd32f1x0`, `gd32vf103`. Adding one means:

1. Write `targets/<target>.toml`.
2. Add per-library `build_assets/<library>/<target>/` for each HAL that supports it.
3. If the target is a new architecture, see `adding-a-new-architecture.md` first.
4. Wire the chip-define in `pipeline.build_one()` for each library.
5. Add the target to `LIBOPENCM3_TARGET_MAP` (if libopencm3 supports it) or the equivalent layout dict for your HAL.

## 1. targets/<target>.toml

```toml
arch         = "cortex-m3"   # or cortex-m0, cortex-m4, riscv32-imac, ...
unicorn_arch = "arm"          # or "riscv"
unicorn_mode = "thumb"        # or "riscv32"

[[peripheral_ranges]]         # Inclusive [start, end]. One or more.
start = 0x40000000
end   = 0x5FFFFFFF

[peripheral_bases]            # Symbolic name → numeric base.
TIM1_BASE   = 0x40012C00
RCC_BASE    = 0x40021000
# ...

[register_names.TIM1_BASE]    # Optional — generates `# CR1` etc. comments in traces.
"0x00" = "CR1"
"0x14" = "EGR"

[reset_values.RCC_BASE]       # Optional — Unicorn's seeded memory state.
"0x00" = "0x00000083"

[bit_band_aliases]            # Cortex-M3/M4 only. Empty table for other archs.
0x42000000 = 0x40000000
```

**Symbol-name discipline.** Use STM32-style names (TIM1_BASE, USART1_BASE, I2C1_BASE) even for vendor parts that name them differently (gd-spl calls these TIMER0, USART0, I2C0). The trace comparator matches on the symbolic key, so consistent names are what makes cross-family comparisons work. Add a comment noting the vendor name where it differs.

## 2. build_assets/<library>/<target>/

Per `adding-a-new-library.md` step 5. Two files:
- `startup.S` — sets SP, branches to `regtrace_test`, halts on sentinel.
- `link.ld` — minimum memory map.

If the target shares an architecture with an existing target (e.g., new Cortex-M3 chip), copy from the existing assets and adjust memory sizes.

## 3. Pipeline chip define

In `pipeline.build_one()`, add the new target to the per-library `target_define` map (or equivalent). Example:

```python
target_define = {
    "stm32f0":   "STM32F0",
    "stm32f1":   "STM32F1",
    ...
    "my-target": "MY_TARGET",
}[target]
```

For libraries that pick a chip via a layout dict (gd-spl, cube-ll), add the layout entry per `adding-a-new-library.md` step 3.

## 4. Validation

Add an existing vector with a new `<library>/<target>` impl. Run `regtrace build vectors/<vector>.yaml` and `regtrace trace build/<library>/<rev>/<target>/<vector>.elf`. Trace should be non-empty and the symbolic addresses should match what's in the target file.
