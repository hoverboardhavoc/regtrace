---
regtrace_version: v0.1
date: 2026-04-26
peripheral: TIMER
decision: share
confidence: partial
libraries_compared:
  - name: libopencm3
    rev: v0.8.0-457-g7b6c2205
    target: stm32f0
  - name: gd-spl
    rev: v3.2.0
    target: gd32f1x0
evidence:
  - golden/libopencm3/v0.8.0-457-g7b6c2205/stm32f0/timer_pwm_init_center_aligned_16khz.trace
  - golden/gd-spl/v3.2.0/gd32f1x0/timer_pwm_init_center_aligned_16khz.trace
draft_pr: TBD
---

# TIMER share-or-split decision

## Summary
A single TIMER init vector (center-aligned PWM @ 16 kHz, hoverboard FOC config) was compared between the libopencm3 STM32F0 driver and the GigaDevice SPL v3.2.0 GD32F1x0 driver. **Final TIM1 register state is identical**: both produce `CR1=0x60`, `ARR=0x8CA`, `PSC=0x0`, `RCR=0x1`, `EGR=0x1`. Trace **order and count differ** — gd-spl does multiple read-modify-write cycles on CR1 (writing 0x60 four times via redundant RMWs); libopencm3 does direct stores. **Recommendation: share** the libopencm3 STM32F0 timer driver for GD32F1x0 — same silicon at the register level. Confidence is *partial* because v0.1 covers only one vector; full confidence requires the v0.2 vector expansion (channel/event config, IRQ enable, DMA trigger).

## Method
Vector: `vectors/timer/pwm_init_center_aligned_16khz.yaml`
Mode: `register_writes` (order-sensitive)
A `final_state` re-run on the same trace pair confirms the underlying state matches; the divergence in the `register_writes` view is purely about emit count/order.

## Diff outcome

| level | applies here? |
|---|---|
| **bit-identical (final state)** | **yes** — every TIM1 register ends up at the same value |
| identical structure, different reset values or default bits | n/a |
| identical mostly, divergent on one or two bit-fields | n/a |
| diverges fundamentally | no |

The trace divergence in `register_writes` mode is implementation-side: gd-spl reads CR1 before each modification, libopencm3 writes the full word directly. Both correct; both produce the same silicon configuration.

## Recommended action
**Share** the libopencm3 STM32F0 timer driver. For the GD32F1x0 port, add `gd32/f1x0/timer.h` that simply `#include`s `stm32/common/timer_common_all.h`. No `#ifdef GD32_*` carve-outs needed.

## Implementation sketch
- `gd32/f1x0/timer.h` → one-line include of `stm32/common/timer_common_all.h`
- Verify the existing libopencm3 GD32F1x0 stub doesn't define a conflicting `timer.h`
- Capture goldens for the same vector under `golden/libopencm3/<commit-with-gd32-port>/gd32f1x0/` once the port lands; expect bit-identical to the stm32f0 trace

## Open questions
- v0.2 will mine more vectors (channel config, DMA trigger, BDTR setup); a single PWM init covers ~15% of the timer API surface.
- We compared against gd-spl `main` (v3.2.0); the `gd-spl-patched` branch may differ on community-fixed bugs. v0.4 adds Cube LL as a third oracle for STM32 sanity checks.
- TIMER15-17 (the lighter advanced timers) weren't covered. They share the same register layout but have a smaller subset of fields; trace evidence on those should follow.
