---
regtrace_version: v0.2
date: 2026-04-26
peripheral: USART
decision: share-with-shim
confidence: empirical
libraries_compared:
  - name: libopencm3
    rev: v0.8.0-457-g7b6c2205
    target: stm32f0
  - name: gd-spl
    rev: v3.2.0
    target: gd32f1x0
evidence:
  - golden/libopencm3/v0.8.0-457-g7b6c2205/stm32f0/usart_init_115200_8n1.trace
  - golden/libopencm3/v0.8.0-457-g7b6c2205/stm32f0/usart_dma_transmit_enable.trace
  - golden/libopencm3/v0.8.0-457-g7b6c2205/stm32f0/usart_rx_interrupt_enable.trace
  - golden/gd-spl/v3.2.0/gd32f1x0/usart_init_115200_8n1.trace
  - golden/gd-spl/v3.2.0/gd32f1x0/usart_dma_transmit_enable.trace
  - golden/gd-spl/v3.2.0/gd32f1x0/usart_rx_interrupt_enable.trace
draft_pr: TBD
---

# USART share-or-split decision

## Summary
GD32F1x0 USART and STM32F0 USART share **identical register layouts** for CR1/CR2/CR3 (the configuration registers), and the bit positions for word-length, stop-bits, parity, mode (TX/RX enable), DMA enables, and interrupt enables all match. The single-bit ops (`usart_enable_tx_dma`, `usart_enable_rx_interrupt`) match exactly. **However**, the BAUD register (BRR / USART_BAUD at offset 0x0C) requires the peripheral clock to be known at runtime to compute the divisor — gd-spl and libopencm3 both compute it from a stored frequency value, but those values are project-specific (`SystemCoreClock` / `rcc_apbN_frequency`). The BRR value differs unless both projects assume the same APB clock. **Decision: share-with-shim** — share the stm32 common USART driver, and ensure the GD32F1x0 RCC integration sets `rcc_apbN_frequency` to the actual GD32 clock value.

## Method
Three vectors:
- `usart_init_115200_8n1` — full init (baud + word length + parity + stop bits + mode + flow control + enable). `final_state` mode with BAUD ignored. Almost matches; libopencm3 has one extra explicit CR3=0 write (from `usart_set_flow_control(NONE)`) that gd-spl doesn't emit.
- `usart_dma_transmit_enable` — single bit-set on CR3.DMAT — matches exactly.
- `usart_rx_interrupt_enable` — single bit-set on CR1.RXNEIE — matches exactly.

## Diff outcome

| level | applies here? |
|---|---|
| bit-identical | **yes** for the per-bit operations; **almost** for full init |
| **identical structure, different reset values or default bits** | **yes** — BRR baud divisor depends on assumed peripheral clock |
| identical mostly, divergent on one or two bit-fields | n/a |
| diverges fundamentally | no |

## Recommended action
**Share with reset-value shim**: forward `gd32/f1x0/usart.h` to the stm32 common USART header. The shim is in the GD32F1x0 RCC support code: ensure `rcc_apbN_frequency` is populated correctly so libopencm3's `usart_set_baudrate` computes the right BRR divisor for GD32 silicon (which has slightly different default clocks than STM32).

The "explicit CR3=0" write libopencm3 emits is a benign idiom — gd-spl leaves CR3 at its reset value (which is also 0). Same silicon state. Worth noting in code review that this is intentional, not a bug.

## Implementation sketch
- `include/libopencm3/gd32/f1x0/usart.h` → `#include <libopencm3/stm32/common/usart_common_v2.h>` (or the appropriate common header — verify which version stm32f0 uses).
- `lib/gd32/f1x0/rcc.c` (or the equivalent RCC integration file) — make sure `rcc_apb1_frequency` and `rcc_apb2_frequency` are set after clock init, so `usart_set_baudrate` works correctly.

## Open questions
- USART variants on the GD32F1x0 family (USART1-4) have slightly different feature sets (not all support DMA on TX or HW flow control). Not exercised here; v0.3 should add per-variant vectors.
- Synchronous mode (USART as SPI) and LIN mode aren't covered.
