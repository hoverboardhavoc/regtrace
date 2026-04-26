---
regtrace_version: v0.2
date: 2026-04-26
peripheral: I2C
decision: split
confidence: empirical
libraries_compared:
  - name: libopencm3
    rev: v0.8.0-457-g7b6c2205
    target: stm32f0
  - name: gd-spl
    rev: v3.2.0
    target: gd32f1x0
evidence:
  - golden/libopencm3/v0.8.0-457-g7b6c2205/stm32f0/i2c_init_100khz_7bit.trace
  - golden/libopencm3/v0.8.0-457-g7b6c2205/stm32f0/i2c_peripheral_disable.trace
  - golden/gd-spl/v3.2.0/gd32f1x0/i2c_init_100khz_7bit.trace
  - golden/gd-spl/v3.2.0/gd32f1x0/i2c_peripheral_disable.trace
draft_pr: TBD
---

# I2C share-or-split decision

## Summary
Same v1-vs-v2 split as ADC. GD32F1x0 I2C is the STM32F1-style v1 (CTL0/CTL1 control, CKCFG clock, RT rise-time, dedicated address registers). STM32F0 I2C (libopencm3 stm32/common/i2c_common_v2) is the v2 architecture with a *single* TIMINGR register encoding all timing parameters, a different control-register layout, and built-in 7/10-bit slave address handling in OAR1. **Decision: split** for `gd32/f1x0/i2c.{h,c}`. Compare against `libopencm3/stm32f1` in v0.3 to determine the right share target.

## Method
Two vectors:
- `i2c_init_100khz_7bit` — clock config + addressing mode + enable. Divergent in any mode: gd-spl writes to CTL1=0x04, CKCFG=0x1C, RT=0x20, CTL0=0x00; libopencm3 writes only to TIMINGR=0x10 (one bit-packed value) and CR1=0x00.
- `i2c_peripheral_disable` — single PE/I2CEN bit-clear. **Matches** in `final_state` because both v1 and v2 use bit 0 of CTL0/CR1 as "peripheral enable".

## Diff outcome

| level | applies here? |
|---|---|
| bit-identical | only for the simple PE-bit operations |
| identical structure, different reset values | no — different layouts entirely |
| identical mostly, divergent on one or two bit-fields | no |
| **diverges fundamentally** | **yes** — TIMINGR-vs-CKCFG/RT is a fundamental layout difference |

## Recommended action
**Split**. `gd32/f1x0/i2c.{h,c}` standalone; do not share stm32/common/i2c_common_v2. Pursue share against stm32/common/i2c_common_v1 in v0.3 (the F1-family I2C is much closer in layout).

## Implementation sketch
Same as ADC: try share with v1 first, fall back to standalone if v1 doesn't quite match. The PE-bit ops can be inlined in both cases.

## Open questions
- v0.3: capture vectors against libopencm3/stm32f1 to confirm v1 layout match.
- Master vs slave mode, fast-mode (400 kHz), and DMA integration not yet covered.
- The hoverboard IMU uses 100 kHz standard mode with bit-banging fallback — the BMI160 driver sometimes bit-bangs around SPL bugs. Worth a vector that exercises the bit-bang code path against gd-spl's I2C peripheral state to check for any leftover hardware-state assumptions.
