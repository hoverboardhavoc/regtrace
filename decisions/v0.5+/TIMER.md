---
regtrace_version: v0.5+
date: 2026-04-28
peripheral: TIMER
target_family: gd32f1x0
decision: share-confirmed
confidence: empirical
libraries_compared:
  - name: gd-spl
    rev: 4ead0d8
    target: gd32f1x0
  - name: libopencm3
    rev: d5f222f8
    target: gd32f1x0
evidence:
  - vectors/timer/pwm_init_center_aligned_16khz.yaml
  - vectors/timer/slave_restart_oc1ref_trgo.yaml
draft_pr: TBD
---

# TIMER share-or-split decision (GD32F1x0) — slave-mode + OC-mode follow-up

## Summary
v0.5/TIMER.md established that GD32 TIMER0/TIMER2 register layout matches
STM32 TIM1/TIM3 bit-identically for the canonical center-aligned PWM
init. This v0.5+ entry validates two additional patterns surfaced by
the Hoverboard firmware port: timer slave-mode (TIM3 reset-on-trigger
from TIM1 TRGO via ITR0, master-output-trigger = OC1REF) and per-channel
output-mode config.

## Method
Two vectors:
- `vectors/timer/pwm_init_center_aligned_16khz.yaml` — basic init
  pattern (mode/period/prescaler/repetition/UPG). Verified
  `gd-spl/gd32f1x0` ↔ `libopencm3/gd32f1x0` → **match** in final_state mode.
- `vectors/timer/slave_restart_oc1ref_trgo.yaml` (new this commit) —
  TIM3 slave reset on ITR0 + CH1 PWM mode + master-output OC1REF →
  **2 differences**, both decided-acceptable (below).

## Headline finding: PWM-mode naming inversion (bug-finder)

The vendor SPL and libopencm3 number PWM modes from opposite ends of
the OCxM[2:0] field. From the GD32F1x0 reference manual:
```
110: PWM mode0 — counting up, OxCPRE high when CNT < CCR
111: PWM mode1 — counting up, OxCPRE low when CNT < CCR
```

libopencm3's enum values:
```
TIM_OCM_PWM1 = 6 (= 0b110) — channel ACTIVE when CNT < CCR (= GD's PWM mode 0)
TIM_OCM_PWM2 = 7 (= 0b111) — channel INACTIVE when CNT < CCR (= GD's PWM mode 1)
```

A naive port that reads "TIMER_OC_MODE_PWM1" in the gd-spl source and
substitutes `TIM_OCM_PWM1` produces the wrong bit pattern (0b110 vs the
intended 0b111) — output polarity is FLIPPED. This was caught at trace
step `<TIM3_BASE>+0x18` in the slave_restart vector before bench, with
gd-spl writing `0x70` (= OC1M=7 = PWM mode 2 lp = PWM mode 1 GD) and
the initial libopencm3 port writing `0x60` (= OC1M=6).

**Fix**: when porting gd-spl `TIMER_OC_MODE_PWM1` → libopencm3, use
`TIM_OCM_PWM2`; conversely SPL `TIMER_OC_MODE_PWM0` → `TIM_OCM_PWM1`.
The Hoverboard firmware's setup.c::pwm_init and adc_trigger_timer_init
were both fixed accordingly (commit in firmware repo references this
file).

## Decided-acceptable divergences (slave_restart_oc1ref_trgo)

After the OC-mode fix, 2 differences remain, both decided-acceptable:

1. **gd-spl writes EGR.UG=1**: the SPL `timer_init` finishes by
   software-generating an update event so the new PSC/ARR shadow
   registers load. libopencm3's per-attribute setters (`timer_set_period`,
   `timer_set_prescaler`) don't write EGR. With ARPE=0 (auto-reload
   shadow disabled) the new values apply on the next timer cycle either
   way; final state of PSC/ARR is identical.

2. **libopencm3 writes RCR=0** (offset 0x30): libopencm3's
   `timer_set_repetition_counter(TIM3, 0)` writes the RCR register
   unconditionally, but TIM3 (general-purpose) has RCR reserved
   (RCR exists only on advanced timers TIM1/TIM8). The write to a
   reserved address is harmless on this part. gd-spl skips the write
   for non-advanced timers via internal type checking.

## Recommended action
**Share confirmed** (matches v0.5/TIMER.md decision). The fork's
`gd32/f1x0/timer.h` forwards directly to
`stm32/common/timer_common_all.h + timer_common_f24.h`, which is
correct. The only firmware-side caution is the PWM-mode naming
inversion — document it next to any port that translates SPL PWM mode
constants.

## Open questions
- Vector for the full hoverboard `pwm_init` body (with break-config +
  per-channel state writes) would be useful but high-effort. The
  per-call mapping (SPL fn → libopencm3 fn) is documented in the
  firmware port commit messages and decisions.md; bit positions are
  identical across the SPL/libopencm3 interpretation per
  v0.5/TIMER.md.
