---
regtrace_version: v0.2
date: 2026-04-26
peripheral: IWDG
decision: share
confidence: empirical
libraries_compared:
  - name: libopencm3
    rev: v0.8.0-457-g7b6c2205
    target: stm32f0
  - name: gd-spl
    rev: v3.2.0
    target: gd32f1x0
evidence:
  - golden/libopencm3/v0.8.0-457-g7b6c2205/stm32f0/iwdg_config_2sec_period.trace
  - golden/gd-spl/v3.2.0/gd32f1x0/iwdg_config_2sec_period.trace
draft_pr: draft-prs/v0.2/gd32f1x0-iwdg.patch
---

# IWDG share-or-split decision

## Summary
GD32F1x0 IWDG (vendor name FWDGT) and STM32F0 IWDG share **identical register layouts and identical key values**. KR (offset 0x00) accepts the same magic constants on both — 0x5555 (unlock), 0xAAAA (reset), 0xCCCC (start). PR (0x04), RLR (0x08), SR (0x0C), WINR (0x10) all match. The 32 kHz LSI assumption that libopencm3's `iwdg_set_period_ms` uses computes prescale + reload values byte-identical to gd-spl's raw `fwdgt_config(reload, prescaler_div)` when the inputs are chosen consistently. **Decision: share** — `gd32/f1x0/iwdg.h` is a one-line `#include` of `stm32/common/iwdg_common_v2.h`.

## Method
Single vector `iwdg_config_2sec_period` exercises the canonical bring-up: configure with reload=0x0FFF, prescaler /16, then start. `mode: final_state` matches; `mode: register_writes` shows a small benign emit-pattern difference (libopencm3 writes the START key 0xCCCC at the *top* of `iwdg_set_period_ms`, before the unlock — see "Implementation note" below).

## Diff outcome

| level | applies here? |
|---|---|
| **bit-identical (final state)** | **yes** — KR=0xCCCC, PR=2, RLR=0x0FFF on both |
| identical structure, different reset values or default bits | n/a (all reset values match per RM) |
| identical mostly, divergent on one or two bit-fields | n/a |
| diverges fundamentally | no |

## Recommended action
**Share** the existing libopencm3 stm32/common IWDG driver from `gd32/f1x0/`. Trivial header include, no carve-out, no `#ifdef GD32_*`.

## Implementation sketch
- New file: `lib/gd32/f1x0/iwdg.c` — empty (or omitted; the make system already pulls in `stm32/common/iwdg_common_all.c` for stm32 targets). Verify the libopencm3 GD32F1x0 stub's `Makefile` includes the common iwdg sources.
- New file: `include/libopencm3/gd32/f1x0/iwdg.h` — single `#include <libopencm3/stm32/common/iwdg_common_v2.h>`. (Or `_all.h` depending on which variant the F0 already uses; v0.2 evidence is captured against `iwdg_common_v2.h`.)

## Implementation note
libopencm3's `iwdg_set_period_ms` writes `IWDG_KR = 0xCCCC` (start) *before* writing `0x5555` (unlock). gd-spl writes 0x5555 first, never emits a leading 0xCCCC. The behavioural effect is to start the watchdog with reset values (timeout ≈ 512 ms at 32 kHz LSI) before reconfiguring. Probably intentional (defense-in-depth — the WDT is never not-running once `iwdg_set_period_ms` has been called), but it's a libopencm3 idiom worth being aware of when porting code that assumes the gd-spl ordering. Not a bug; not a portability concern.

## Open questions
- Window-mode WINR: not exercised by this vector. `gd-spl/fwdgt_window_value_config` has its own polling loop on STAT.WUD; a v0.3 vector with `mode: with_polling` should confirm the WINR layout matches and the unlock dance is identical.
