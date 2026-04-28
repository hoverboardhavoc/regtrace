---
regtrace_version: v0.5+
date: 2026-04-28
peripheral: ADC
target_family: gd32f1x0
decision: share-with-stm32f1
confidence: empirical
libraries_compared:
  - name: gd-spl
    rev: 4ead0d8
    target: gd32f1x0
  - name: libopencm3
    rev: d5f222f8
    target: gd32f1x0
evidence:
  - vectors/adc/calibration_enable.yaml
  - vectors/adc/single_channel_right_aligned.yaml
  - vectors/adc/scan_dma_circular_t3trgo.yaml
draft_pr: TBD
---

# ADC share-or-split decision (GD32F1x0) — confirmation + multi-channel follow-up

## Summary
v0.2/ADC.md predicted GD32F1x0 ADC should **share with stm32/f1** (the
v1 ADC layout — RSQ1/2/3 sequence registers, SAMPT0/1 per-channel
sample times, two-step RSTCLB+CLB calibration). The fork's
`gd32/f1x0/adc.h` forwards to `stm32/f1/adc.h` per that recommendation;
this v0.5+ entry validates the choice empirically against three
vectors and records the divergences as decided-acceptable.

Three vectors compared, all `gd-spl/gd32f1x0` ↔ `libopencm3/gd32f1x0`:
1. `adc_calibration_enable` — divergent (4), decided-acceptable.
2. `adc_single_channel_right_aligned` — divergent (5),
   decided-acceptable.
3. `adc_scan_dma_circular_t3trgo` (new this commit) — divergent (4),
   decided-acceptable.

## Decided-acceptable divergences

### Calibration polling sequence
SPL's `adc_calibration_enable` issues two separate operations (write
RSTCLB, poll until clears, then write CLB, poll until clears).
libopencm3's `adc_calibrate` issues the same two operations but in a
slightly different polling pattern (specifically `adc_reset_calibration`
+ poll, then `adc_calibration` + poll inside one helper). The bits
written and the bits polled are the same; the order of the
read/write pairs differs by one step. ADC_CTL1 final state matches.

### Sample-time write granularity
libopencm3's `adc_set_sample_time_on_all_channels(SMP_13DOT5CYC)`
writes ALL 18 channel sample-time fields in SAMPT0 + SAMPT1
(`0x12492492` to each = 0x2 per 3-bit field, 9 fields per register).
SPL's `adc_regular_channel_config(rank, ch, time)` only writes the
3-bit field for the single channel being configured — leaving unused
channel sample times at post-reset 0 (= 1.5 cycles).

For the channels actually scanned (ch 0, 4, 8 in the FOC build), the
final SAMPT bit pattern is identical between the two paths. The
divergence is bookkeeping for unused channels, which never participate
in conversions and so never see the post-reset-vs-13.5-cycle
difference materialise.

### Explicit-zero register writes
libopencm3 explicit-clears ADC_SQR2 (offset 0x30) when the regular
sequence has fewer channels than its capacity, and DMA1_IFCR (offset
0x04) inside `dma_channel_reset`. Both are post-reset 0 anyway; SPL
skips the redundant write.

### Trigger-source two-step
The Hoverboard firmware preserves the SPL workaround of setting
ETSRC=SWSTART during init → calibrate → set ETSRC=TIM3_TRGO. Some F130
silicon hangs RSTCLB/CLB if ETERC=1 + a non-SW ETSRC is set before
calibration completes. Both libopencm3 and gd-spl paths execute the
two-step; the bit pattern at ADC_CR2.EXTSEL[19:17] is identical at
each step.

## Recommended action
**Share with stm32/f1** confirmed. The fork's
`include/libopencm3/gd32/f1x0/adc.h` consists solely of:
```c
#include <libopencm3/stm32/f1/adc.h>
```
which is the correct realization of the v0.2 recommendation.

The Hoverboard firmware port's `adc_init` body uses libopencm3's v1
ADC API (`adc_set_regular_sequence`,
`adc_set_sample_time_on_all_channels`, `adc_set_right_aligned`,
`adc_enable_external_trigger_regular`, `adc_calibrate`, `adc_power_on`,
`adc_enable_dma`, `adc_enable_scan_mode`) and traces with the
divergences listed above against the SPL ground truth.

## Open questions
- The sample-time-on-all-channels divergence costs ~10 µs of
  init-time DMA write traffic but is otherwise harmless. A
  `adc_set_sample_time_per_channel` libopencm3 helper that writes
  only the channels in the sequence would close the divergence; not
  needed for the Hoverboard port.
- ADC dual-mode and analog-watchdog config are not exercised by the
  Hoverboard firmware and aren't covered by these vectors.
