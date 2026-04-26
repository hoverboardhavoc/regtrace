---
regtrace_version: v0.4
date: 2026-04-26
peripherals_three_way_validated: [TIMER, IWDG]
oracles:
  - name: gd-spl
    rev: v3.2.0
    target: gd32f1x0
  - name: libopencm3
    rev: v0.8.0-458-gd7e20526
    targets: [stm32f0, stm32f1, stm32f4]
  - name: cube-ll
    rev: v1.8.7-1-g5f2bc59
    target: stm32f1
---

# v0.4 finding: no libopencm3 bugs surfaced by 3-oracle TIMER/IWDG comparison

## What we tested
Two vectors covering peripherals where v0.2 already concluded "share":

- `timer_pwm_init_center_aligned_16khz` (5 implementations, 10 pairs)
- `iwdg_config_2sec_period` (5 implementations, 10 pairs)

Five implementations per vector:
- `gd-spl/gd32f1x0` (vendor SPL)
- `libopencm3/stm32f0` (Cortex-M0)
- `libopencm3/stm32f1` (Cortex-M3)
- `libopencm3/stm32f4` (Cortex-M4 + FPU)
- `cube-ll/stm32f1` (STMicro Low-Level driver — the third oracle)

## Result
**All 20 cross-oracle pairs match in `final_state` mode.** Every implementation produces the same final TIM1 / IWDG register state for the same configuration intent. There are no register-level disagreements between vendors.

In `register_writes` mode the traces diverge in the same shape we documented in v0.1 / v0.2:
- gd-spl emits more (defensive RMW) writes than libopencm3 or cube-ll;
- libopencm3 sometimes makes explicit "set to reset value" writes that gd-spl and cube-ll skip;
- cube-ll's `LL_TIM_Init` writes the consolidated CR1 value in a single 32-bit store, very similar to gd-spl's `timer_init` shape.

None of these emit-pattern differences change the final silicon state, and the 3-way oracle rules out "libopencm3 has a subtle bug both vendors compensate for" — if there were such a bug, gd-spl and cube-ll would agree against libopencm3, and they don't.

## Conclusion
For the v0.2 share decisions on TIMER and IWDG (decisions/v0.2/{TIMER,IWDG}.md), the 3-oracle finding is **corroborating evidence**: not only do gd-spl and libopencm3 agree at the register level, the third independent reference (STMicro's own LL driver) agrees too. **No libopencm3 bug PRs to file from this round.**

## Coverage limitations
- Only TIMER and IWDG were three-way-validated. v0.5 should expand to GPIO + USART once a v0.5 decision is made on the `-DSTM32F103xB` chip-define for cube-ll across more vectors.
- Cube LL was tested for the F1 family only (the family that maps to GD32F1x0 ADC/I2C, even though TIMER/IWDG are family-agnostic). The Cube F0 / F4 oracles would add weight to the existing decisions but require their own submodule init.
- We have no peripheral-response model. Cube LL's HAL (handle-based) layer wasn't tested — only LL. HAL has more "convenience" code paths that could in theory introduce divergent register behaviour; out of scope for v0.4.
- BAUD/clock-dependent registers (USART_BRR) were excluded via `ignore` in v0.2. Cube LL would compute these from a different SystemCoreClock value, so 3-way validation of USART would need clock-divisor normalisation.

## What's worth doing next
- Add `cube-ll/stm32f1` impls to DMA + USART vectors (DMA was "share" empirically, USART was "share-with-shim"). Confirm Cube LL agrees.
- Add the `cube-hal` library-id (the high-level handle-based driver) for at least TIMER, since some downstream projects use HAL not LL — divergences would matter.
- Once stm32cube-f0 lands as a sibling repo, do the 3-way TIMER + IWDG + USART check for the F0 family explicitly (currently only F1 was tested for cube-ll).
