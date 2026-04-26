---
regtrace_version: v0.2
date: 2026-04-26
peripheral: DMA
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
  - golden/libopencm3/v0.8.0-457-g7b6c2205/stm32f0/dma_p2m_circular_16bit.trace
  - golden/libopencm3/v0.8.0-457-g7b6c2205/stm32f0/dma_m2m_8bit.trace
  - golden/libopencm3/v0.8.0-457-g7b6c2205/stm32f0/dma_transfer_complete_irq.trace
  - golden/gd-spl/v3.2.0/gd32f1x0/dma_p2m_circular_16bit.trace
  - golden/gd-spl/v3.2.0/gd32f1x0/dma_m2m_8bit.trace
  - golden/gd-spl/v3.2.0/gd32f1x0/dma_transfer_complete_irq.trace
draft_pr: TBD
---

# DMA share-or-split decision

## Summary
GD32F1x0 DMA and STM32F0 DMA share **identical register layouts**. DMA_BASE = 0x40020000 on both; per-channel offsets match: control register at base + 0x08 + 20·N, count at +0x0C + 20·N, peripheral address at +0x10 + 20·N, memory address at +0x14 + 20·N. CCR/CHxCTL bit fields (DIR, CIRC, PINC, MINC, PSIZE, MSIZE, PL, M2M) are at the same bit positions with the same values. **Decision: share** the libopencm3 stm32 common DMA driver (`stm32/common/dma_common_l1f013`) from the GD32F1x0 port. Channel-numbering convention differs (GD numbers from 0; libopencm3 from 1) but the underlying register addresses are the same.

## Method
Three vectors exercising different DMA scenarios:
- `dma_p2m_circular_16bit` — peripheral-to-memory, 16-bit, very-high priority, circulation enabled (the hoverboard ADC streaming pattern)
- `dma_m2m_8bit` — memory-to-memory, 8-bit, low priority
- `dma_transfer_complete_irq` — single bit-set (FTFIE / TCIE)

All three match in `final_state`. In `register_writes` mode the traces diverge in the same shape we see for TIMER and IWDG: gd-spl's `dma_init` writes the consolidated CCR value in one shot, then small RMWs to add CIRC/MINC bits; libopencm3's per-setting calls each do an RMW. Same final CCR value either way.

## Diff outcome

| level | applies here? |
|---|---|
| **bit-identical (final state)** | **yes** — across all 3 vectors |
| identical structure, different reset values or default bits | n/a |
| identical mostly, divergent on one or two bit-fields | n/a |
| diverges fundamentally | no |

## Recommended action
**Share** the libopencm3 stm32/common DMA driver from `gd32/f1x0/`. Provide a one-line forwarding header.

## Implementation sketch
- `include/libopencm3/gd32/f1x0/dma.h` → `#include <libopencm3/stm32/common/dma_common_l1f013.h>`.
- Verify the libopencm3 channel-numbering convention (`DMA_CHANNEL1` is the first channel, GD's "channel 0") is acceptable; it's the established libopencm3 idiom and will read naturally for libopencm3 users.
- The hoverboard's existing `TARGET_dma_*` macro shims map cleanly to libopencm3 names: `dma_init` → multiple `dma_set_*` calls; `dma_circulation_enable` → `dma_enable_circular_mode`; etc.

## Open questions
- DMA channel mapping (which peripheral can request which channel) is encoded in DMA_CSELR on later parts. F1x0 doesn't have CSELR; channels are hard-wired per peripheral per the TRM. Not exercised by these vectors but worth confirming the libopencm3 stm32f0 driver's CSELR handling is conditionally compiled out for the gd32f1x0 build (likely already is, since stm32f0 doesn't have CSELR either).
