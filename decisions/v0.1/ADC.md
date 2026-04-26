---
regtrace_version: v0.1
date: 2026-04-26
peripheral: ADC
decision: deferred
confidence: inferred
libraries_compared: []
evidence: []
draft_pr: TBD
---

# ADC share-or-split decision (deferred)

## Status
**Deferred to v0.2.** The v0.1 milestone targeted TIMER + ADC. TIMER is complete (see [TIMER.md](TIMER.md)); ADC requires a vector and one additional piece of plumbing (the `with_polling` comparison mode for ADC calibration polling, which lands in v0.2).

## What's needed to complete this
1. Mine a representative ADC init+conversion sequence from `Hoverboard-Firmware-Hack-Gen2.x-GD32/Src/setup.c` (the production hoverboard ADC uses regular conversion, channel sequencing, DMA trigger).
2. Write `vectors/adc/regular_conversion_dma.yaml` with both `gd-spl/gd32f1x0` and `libopencm3/stm32f0` implementations.
3. For ADC calibration (which spins on a status bit), add a vector with `mode: with_polling` and a `read_responses:` map for the calibration-complete bit.
4. Capture goldens, compare, write up the diff outcome.

## Inferred recommendation (not load-bearing)
Based on register-layout reading (not yet a regtrace diff): GD32F1x0 ADC is closely related to STM32F0/F1 ADC v2 but has at least one known divergence — the OVRMOD overrun-mode default. This may push the decision toward "share with reset shim" rather than bare share. Empirical confirmation is the v0.2 work item.
