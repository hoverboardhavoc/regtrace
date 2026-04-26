---
regtrace_version: v0.5
date: 2026-04-26
peripheral: IWDG
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
  - golden/gd-spl/4ead0d8/gd32f10x/iwdg_config_2sec_period.trace
  - golden/libopencm3/v0.8.0-458-gd7e20526/stm32f1/iwdg_config_2sec_period.trace
  - golden/cube-ll/v1.8.7-1-g5f2bc59/stm32f1/iwdg_config_2sec_period.trace
draft_pr: draft-prs/v0.5/gd32f10x-timer.patch
---

# IWDG share-or-split decision (GD32F10x)

## Summary
GD32F10x's IWDG (vendor name FWDGT) has identical register layout to STM32F1 IWDG. Same KR magic constants (0x5555 / 0xAAAA / 0xCCCC), same PR/RLR/SR layout. 15/15 pairs match in `final_state` across the 6-impl all-pairs comparison. **Decision: share** the libopencm3 stm32 common IWDG driver via a one-line forwarder.

## Method
Single vector `iwdg_config_2sec_period`. Same configuration as the v0.2 IWDG decision (reload=0x0FFF, prescaler /16, then enable). All-pairs match.

## Diff outcome
Bit-identical final state across all 6 implementations. Same outcome as v0.2's GD32F1x0 IWDG decision.

## Recommended action
**Share** via `include/libopencm3/gd32/f10x/iwdg.h` → `#include <libopencm3/stm32/common/iwdg_common_all.h>`. Note the F1 family uses `iwdg_common_all.h` (not the `_v2.h` variant the F0 uses) — F10x should match F1 here since that's the closer architectural sibling.

## Implementation sketch
Bundled into `draft-prs/v0.5/gd32f10x-timer.patch` since the changes share the same Makefile and dispatcher headers. See that patch for the full implementation.
