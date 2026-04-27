---
regtrace_version: v0.5+
date: 2026-04-27
peripheral: RCC
target_family: gd32f1x0
decision: split
confidence: empirical
libraries_compared:
  - name: gd-spl
    rev: 4ead0d8
    target: gd32f1x0
  - name: libopencm3
    rev: master
    targets: [stm32f1, gd32f1x0]
evidence:
  - vectors/rcc/irc8m_pll_72mhz.yaml
draft_pr: TBD
---

# RCC share-or-split decision (GD32F1x0)

## Summary
GD32F1x0 RCU is structurally similar to STM32F1 RCC at the register-layout
level (CR @0x00, CFGR @0x04, AHBENR @0x14, APB2ENR @0x18, APB1ENR @0x1C
all align), but the **PLL multiplier field is meaningfully wider** on GD:
GD32F1x0 has PLLMF[3:0] in RCU_CFG0[21:18] **plus** PLLMF[4] at bit 27,
extending the multiplier range to 2..32. STM32F1 has only the 4-bit
PLLMUL[3:0] at the same low position, capping at x16.

The Hoverboard firmware's actual production clock config on GD32F130 is
IRC8M / 2 * 18 = 72 MHz, set by the vendor SPL's `system_clock_72m_irc8m()`
running from `SystemInit()`. **STM32F1 cannot express this multiplier**;
the closest libopencm3/stm32f1 helper, `rcc_clock_setup_in_hsi_out_64mhz()`,
maxes out at x16 → 64 MHz. A bare libopencm3/gd32f1x0 forwarder to
stm32/f1/rcc.h (the v0.5 epilogue's provisional pattern) silently produces
the wrong PLL config — 64 MHz instead of 72 MHz, no error.

**Decision: split.** The libopencm3 GD32F1x0 RCC port needs
GD32-specific clock-setup code that writes RCU_CFG0 bit 27 (PLLMF[4])
when the multiplier exceeds 16. Forwarding to stm32/f1/rcc.h alone is
insufficient.

## Method
Vector `vectors/rcc/irc8m_pll_72mhz.yaml` reproduces the canonical
SystemInit + system_clock_72m_irc8m sequence as inline writes
(gd-spl/gd32f1x0 implementation), matched against
`rcc_clock_setup_in_hsi_out_64mhz()` calls (libopencm3/stm32f1 and
libopencm3/gd32f1x0 implementations). `mode: register_writes` so the
sequence — not just the end state — is captured.

`confidence: empirical` — vector ran on 2026-04-27 against
`gd-spl/gd32f1x0` and `libopencm3/stm32f1`; the third leg
(`libopencm3/gd32f1x0`) **failed to build**, which is itself empirical
evidence for the split decision (see below).

```
regtrace build vectors/rcc/irc8m_pll_72mhz.yaml
regtrace compare rcc_irc8m_pll_72mhz --against=gd-spl/gd32f1x0,libopencm3/stm32f1
```

## Diff outcome (observed)

**Build leg failed for `libopencm3/gd32f1x0`:** the fork's
`gd32/f1x0/rcc.h` does not provide `rcc_clock_setup_in_hsi_out_64mhz()`
(or any 72 MHz helper). The vector references it in the libopencm3
slot, the linker can't resolve it, the build aborts with
`implicit declaration of function 'rcc_clock_setup_in_hsi_out_64mhz'`.
This is empirical evidence that the fork's gd32/f1x0 RCC surface is
incomplete for this firmware's needs — not a vector defect. A bare
forwarder to `stm32/f1/rcc.h` would also be wrong (caps at 64 MHz).
The split is required to land a 72 MHz helper.

**Compare leg `gd-spl/gd32f1x0` vs `libopencm3/stm32f1`:** divergent,
14 differences. The headline write — proof of the predicted split — is
at trace step [13]:

```
gd-spl/gd32f1x0-only: W4 <RCC_BASE>+0x04 0x08040008
```

`0x08040008` decodes to RCU_CFG0 with bit 27 (PLLMF[4]) set, bit 18
(PLLMF[0]) set, and bit 3 (SW[1]=PLL) set — i.e., the GD-specific
extended PLL multiplier write. STM32F1's libopencm3 helper writes only
bits 18–21 (legacy 4-bit PLLMUL), which caps at x16 → 64 MHz. The
`-only` annotation on this line is the regtrace-comparator confirming
this write has no counterpart in the STM32F1 trace.

| level | applies here? |
|---|---|
| bit-identical | no — confirmed |
| identical structure, different reset values | partial |
| identical mostly, divergent on one or two bit-fields | **yes** — PLLMF[4] is the headline divergence; RCU_CFG2/CTL1/CFG0 reset writes also gd-only |
| diverges fundamentally | no |

Other observed divergences:
- gd-spl writes RCU_CFG2 @0x2C (USART0SEL/CECSEL/ADCSEL) and RCU_CTL1
  @0x34 (IRC14M) during SystemInit reset-to-defaults; libopencm3/stm32f1
  has no equivalents (registers don't exist on STM32F1). Trace steps
  [5]–[7] show these as gd-spl writes that mismatch unrelated stm32f1
  writes (the comparator aligns on position, not register).
- libopencm3/stm32f1 writes `<FLASH_BASE>+0x00 0x00000002` at step [6]
  (sets FLASH_ACR.LATENCY = 2 wait states for 48–72 MHz operation).
  gd-spl in this snippet does NOT write FLASH_ACR — likely because
  the GD32F1x0 SystemInit assumes the post-reset FMC_WS default
  (PFTEN+ICEN, no wait states required up to 72 MHz on this part).
  This is a real flash-config difference worth a separate vector.

## Recommended action
**Split.** Add a `gd32/f1x0/rcc.h` that does NOT include
`stm32/f1/rcc.h` blindly. It should:
1. Provide GD32-specific PLLMUL constants up to x32 (5-bit field across
   PLLMF[3:0] + PLLMF[4]).
2. Provide a `gd32f1x0_rcc_clock_setup` taking a struct that supports
   the IRC8M_DIV2 → x18 → 72 MHz topology used by the vendor.
3. Provide GD-specific clock enables for peripherals not present on
   STM32F1 (TIM14/15/16/17, USART4, etc.).
4. Re-export the bits that ARE shared (CR layout, basic CFGR layout,
   peripheral enable bit positions where they overlap).

A targeted regtrace vector after the split is implemented should produce
a bit-identical trace versus the gd-spl reference for the canonical
72 MHz config — that's the empirical gate for landing the split.

## Implementation sketch
- `include/libopencm3/gd32/f1x0/rcc.h` (new) — GD-specific declarations:
  `RCC_PLL_MUL18` etc., `gd32f1x0_rcc_clock_setup_in_hsi_out_72mhz()`,
  `RCU_CFG2` definitions for USART0SEL/CECSEL/ADCSEL.
- `lib/gd32/f1x0/rcc.c` (new) — implementation that touches RCU_CFG0
  PLLMF[4] correctly. Cannot share `stm32/f1/rcc.c` because that file
  hard-codes the 4-bit PLLMUL field.
- `lib/gd32/f1x0/Makefile` — list `rcc.o`.
- `include/libopencm3/stm32/rcc.h` dispatcher — already routes
  `GD32F1X0` to `gd32/f1x0/rcc.h` (per the existing v0.5+ epilogue
  branching).

## Open questions
- Are there other GD32F1x0 clock-tree features unique to this family
  (clock-out divider extensions, USART clock multiplexing) that warrant
  more vectors before locking the split design? Likely yes — at minimum
  USART0SEL routing (RCU_CFG2[1:0]) used by the firmware's
  `rcu_periph_clock_enable(RCU_USART0)` path needs its own vector if
  cross-impl USART clock setup is going to be regtraceable.
- Does the firmware ever call `Clock_init()` with the F103/STM32F103
  branch live (TARGET == 2 path)? That branch DOES write FMC_WS — so
  the F1x0 branch's lack of FMC_WS write is an explicit design choice,
  not an oversight. Document this in the F1x0 RCC port code.
