---
regtrace_version: v0.2
date: 2026-04-26
peripheral: ADC
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
  - golden/libopencm3/v0.8.0-457-g7b6c2205/stm32f0/adc_single_channel_right_aligned.trace
  - golden/libopencm3/v0.8.0-457-g7b6c2205/stm32f0/adc_calibration_enable.trace
  - golden/gd-spl/v3.2.0/gd32f1x0/adc_single_channel_right_aligned.trace
  - golden/gd-spl/v3.2.0/gd32f1x0/adc_calibration_enable.trace
draft_pr: TBD
---

# ADC share-or-split decision

## Summary
GD32F1x0 ADC and STM32F0 ADC have **fundamentally different register layouts**. GD32F1x0's ADC is the STM32F1-style v1 ADC: regular sequence in `ADC_RSQ0/RSQ1/RSQ2`, per-channel sample times in `ADC_SAMPT0/SAMPT1`, calibration via two separate operations (`RSTCLB` then `CLB`), control bits split across `ADC_CTL0`/`ADC_CTL1`. STM32F0's ADC (libopencm3 stm32/common/adc_common_v2) is the v2 ADC: channel selection via a *bitmap* in `CHSELR`, single sample-time for *all* channels in `SMPR`, single-bit calibration (`ADCAL` in `CR`), and a different control-register split (`CR`/`CFGR1`/`CFGR2`). **Decision: split** for `gd32/f1x0/adc.{h,c}`.

The right comparison oracle for GD32F1x0 ADC is **libopencm3 stm32/f1**, not stm32/f0. v0.3 should add a vector that compares against libopencm3 stm32/f1 to confirm.

## Method
Two vectors:
- `adc_single_channel_right_aligned` — basic regular-conversion init (channel length, regular channel config, alignment, power on). `register_writes` mode is divergent on every line because the implementations write to different register addresses (gd-spl: 0x2C/0x34/0x10/0x08; libopencm3: 0x0C/0x14/0x28/0x08).
- `adc_calibration_enable` — `with_polling` mode with `read_responses` for the calibration-complete bit. Both poll the same register (offset 0x08) but on different bit positions: gd-spl spins on RSTCLB (bit 3) then CLB (bit 2); libopencm3 spins on ADCAL (bit 31). Two separate ops vs one.

## Diff outcome

| level | applies here? |
|---|---|
| bit-identical | no |
| identical structure, different reset values | no |
| identical mostly, divergent on one or two bit-fields | no |
| **diverges fundamentally** | **yes** — entirely different register layouts |

## Recommended action
**Split**. Create a dedicated `lib/gd32/f1x0/adc.c` and `include/libopencm3/gd32/f1x0/adc.h`. Do *not* try to share the stm32/common/adc_common_v2 driver.

The right move for code reuse is to share with **stm32/common/adc_common_v1** instead (the F1-family ADC driver) once a v0.3 vector confirms it.

## Implementation sketch
Two paths to consider:

1. **Share with stm32/common/adc_common_v1** (preferred if v0.3 evidence confirms layout match):
   - `include/libopencm3/gd32/f1x0/adc.h` → `#include <libopencm3/stm32/common/adc_common_v1.h>`.
   - May need a small reset-value shim if GD differs from STM32F1 on calibration register defaults.

2. **Standalone `gd32/f1x0/adc.c`** (fallback if v1 doesn't quite match either):
   - Mirror the libopencm3 v1 API names (`adc_set_regular_sequence`, `adc_calibrate`, etc.) and implement against the GD register layout.
   - Sketch the API surface from this v0.2 evidence: single regular conversion, channel sequencing 1-16, sample time per channel, dual mode, DMA mode, calibration.

## Open questions
- v0.3 must compare against `libopencm3/stm32f1` (the v1 ADC) to determine if the share-with-v1 path is viable. If v1 matches exactly → bit-identical share. If close but not exact → share-with-shim or share-with-macro. If divergent on more than ~2 bit-fields → standalone.
- Multi-channel sequence vectors (≥4 channels) and triggered modes (TIMER → ADC trigger) not yet covered.
- The watchdog threshold register layout was flagged in PR #928's discussion as a likely divergence point. Add a vector covering analog watchdog config in v0.3.
