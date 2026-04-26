---
regtrace_version: v0.5
date: 2026-04-26
peripheral: TIMER
target_family: gd32f10x
decision: share
confidence: empirical
libraries_compared:
  - name: libopencm3
    rev: v0.8.0-458-gd7e20526
    targets: [stm32f1, stm32f0, stm32f4]
  - name: gd-spl
    rev: 4ead0d8
    targets: [gd32f10x, gd32f1x0]
  - name: cube-ll
    rev: v1.8.7-1-g5f2bc59
    target: stm32f1
evidence:
  - golden/gd-spl/4ead0d8/gd32f10x/timer_pwm_init_center_aligned_16khz.trace
  - golden/libopencm3/v0.8.0-458-gd7e20526/stm32f1/timer_pwm_init_center_aligned_16khz.trace
  - golden/cube-ll/v1.8.7-1-g5f2bc59/stm32f1/timer_pwm_init_center_aligned_16khz.trace
draft_pr: draft-prs/v0.5/gd32f10x-timer.patch
---

# TIMER share-or-split decision (GD32F10x)

## Summary
GD32F10x's TIM1 register layout is identical to STM32F1's. **All 5 implementations** (gd-spl/gd32f10x, gd-spl/gd32f1x0, libopencm3/stm32f0, libopencm3/stm32f1, libopencm3/stm32f4, cube-ll/stm32f1) produce the same final TIM1 register state for the canonical center-aligned PWM init. **Decision: share** the libopencm3 stm32 common timer driver from `gd32/f10x/`. Forwarder header is sufficient — no `#ifdef GD32F10X_*` carve-out, no shim.

## Method
Single vector `timer_pwm_init_center_aligned_16khz` with 6 implementations spanning 3 vendors (gd-spl, libopencm3, cube-ll) and 4 chip families (gd32f10x, gd32f1x0, stm32f0/f1/f4). All-pairs comparison in `final_state` mode → 15/15 pairs match.

The GD32F10x SPL `timer_init` API is identical to GD32F1x0's (same `timer_parameter_struct`, same `TIMER_COUNTER_CENTER_BOTH` constant, same `TIMER_CKDIV_DIV1`). This is unsurprising — vendor SPLs maintain API stability across families.

## Diff outcome

| level | applies here? |
|---|---|
| **bit-identical (final state)** | **yes** — across all 15 cross-impl pairs |
| identical structure, different reset values or default bits | n/a |
| identical mostly, divergent on one or two bit-fields | n/a |
| diverges fundamentally | no |

## Recommended action
**Share** the libopencm3 stm32/common timer driver from `gd32/f10x/`. The GD32F10x port should add:
- `include/libopencm3/gd32/f10x/timer.h` → one-line `#include <libopencm3/stm32/common/timer_common_all.h>`.
- The dispatching `stm32/timer.h` already has a chip define switch; add a `GD32F10X` branch.
- `lib/gd32/f10x/Makefile` lists `timer_common_all.o` (and any v1-specific TIM helper modules used in stm32/f1).

## Implementation sketch
See `draft-prs/v0.5/gd32f10x-timer.patch` for the full diff. Three files in libopencm3 touch:
- `include/libopencm3/gd32/f10x/timer.h` (new) — forwarder.
- `include/libopencm3/stm32/timer.h` — add `#elif defined(GD32F10X)` branch.
- `lib/gd32/f10x/Makefile` — add `timer_common_all.o`.

## Note vs F1x0
This is the same shape as the v0.2 TIMER decision for GD32F1x0 (also share). The difference is which STM32 family to share *against*: GD32F1x0 shares against stm32/f0 because that's the closest peripheral-architecture match (STM32F0-style modern v2 ADC etc., but TIMER is family-agnostic). GD32F10x shares against stm32/f1 because the rest of its peripherals (ADC, I2C, GPIO) match the legacy v1 layout. For TIMER specifically the choice doesn't matter — TIM1 is the same.
