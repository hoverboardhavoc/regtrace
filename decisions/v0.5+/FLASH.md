---
regtrace_version: v0.5+
date: 2026-04-27
peripheral: FLASH
target_family: gd32f1x0
decision: share
confidence: empirical
libraries_compared:
  - name: gd-spl
    rev: 4ead0d8
    target: gd32f1x0
  - name: libopencm3
    rev: master
    targets: [stm32f1, gd32f1x0]
evidence:
  - vectors/flash/page_erase.yaml
  - vectors/flash/word_write.yaml
draft_pr: TBD
---

# FLASH share-or-split decision (GD32F1x0)

## Summary
GD32F1x0's FMC peripheral is register-compatible with STM32F1's FLASH
controller for the operations the Hoverboard firmware performs (page
erase + word program). FMC_KEY ↔ FLASH_KEYR (offset 0x04, same magic
constants 0x45670123 / 0xCDEF89AB), FMC_STAT ↔ FLASH_SR (0x0C),
FMC_CTL ↔ FLASH_CR (0x10) with matching bit positions for LK/PG/PER/
START/MER, FMC_ADDR ↔ FLASH_AR (0x14). **Decision: share** the libopencm3
stm32 common `flash_common_f01.h` from `gd32/f1x0/`; one-line forwarder
header is sufficient for the basic erase + program path.

## Method
Two vectors:
- `vectors/flash/page_erase.yaml` — mirrors `flashErase()` from
  Hoverboard `setup.c:1052`. Sequence:
  unlock → clear status flags → page_erase → lock.
- `vectors/flash/word_write.yaml` — mirrors one iteration of
  `flashWriteBuffer()` from `setup.c:1082` (which loops over
  `flashWrite()`). Sequence:
  unlock → clear status flags → program_word → lock.

Both use `mode: register_writes` because the order of writes matters
(unlock keys must be in sequence; PG/PER must be set before START;
status clear must precede unlock-key writes per SPL convention).

`read_responses` are declared for FMC_CTL (reset value 0x80, LK=1) and
FMC_STAT (0x00, never busy) so the `fmc_unlock` LK check and
`fmc_ready_wait` polling loop both behave deterministically under
emulation.

`confidence: empirical` — both vectors ran on 2026-04-27. All three
build legs (`gd-spl/gd32f1x0`, `libopencm3/stm32f1`,
`libopencm3/gd32f1x0`) compiled and produced traces. The fork's
`gd32/f1x0` re-uses `flash_common_f01` via VPATH, so no flash.h
forwarder needed to be added before running.

```
regtrace compare flash_page_erase
regtrace compare flash_word_write
```

## Diff outcome (observed)

**Both vectors: divergent in `register_writes` mode** — but the
divergence is purely in *write sequencing*, not in target registers
or final state.

`flash_page_erase` (gd-spl/gd32f1x0 vs libopencm3/gd32f1x0): 8
differences. gd-spl batches status-flag clearing into one SR write
(`0x30` = EOP|WRPRTERR), libopencm3 clears each flag individually
(three separate writes: `0x04`, `0x20`, `0x10`). Both then converge on
the same CR sequence: `0x82` (PER+LK) → write AR → `0xC0` (PER+LK+STRT)
→ `0x80` (LK). libopencm3 emits two extra `0x80` writes at the tail of
the trace (relock idempotency).

`flash_word_write`: 8 differences, same pattern. Status-flag clearing
diverges identically; CR sequence (`0x81` PG+LK → `0x80` LK) converges,
with libopencm3 again emitting extra trailing `0x80`/`0x81` writes.

| level | applies here? |
|---|---|
| bit-identical (register-write trace) | **no** — sequencing differs |
| **share at API level** (same registers, same final state, divergent intermediate writes) | **yes** — confirmed |
| identical mostly, divergent on one or two bit-fields | no |
| diverges fundamentally | no |

**Decision still stands: share.** The functional contract is identical
— same FMC registers touched, same unlock keys, same control bits in
the same order at decision points (PER set before STRT, etc.). The
trace-level divergence is style (batched vs per-bit clears, extra
relock writes) that doesn't affect chip behavior. Recommended
comparator config for any future flash vectors: either accept this
sequencing divergence or use `mode: final_state` for flash work.

Notable differences NOT exercised by these vectors:
- GD32F1x0 FMC adds `FMC_WSEN` register at offset 0x100 (no STM32F1
  equivalent). The Hoverboard firmware doesn't touch it; out of scope
  for this decision.
- GD32F1x0 has a GD-specific `fmc_word_reprogram()` for F170/F190 (not
  for F130). Not used by the Hoverboard firmware; out of scope.
- The actual flash-memory store (`*(uint32_t*)addr = data` inside
  `fmc_word_program`) lands at 0x08007C00 — outside the F1x0
  `peripheral_ranges` window (0x40000000..0x5FFFFFFF), so it's
  filtered from the trace. This is correct: regtrace compares
  peripheral-config sequences, not the data being written to flash.

## Recommended action
**Share.** The fork already pulls `flash_common_f01.o` into
`lib/gd32/f1x0/` via VPATH (verified at build time on 2026-04-27); no
new forwarder header was needed for the vectors to compile against
`libopencm3/gd32f1x0`. The Hoverboard port can call libopencm3's
`flash_unlock` / `flash_program_word` / `flash_erase_page` / `flash_lock`
directly on F1x0 with no fork-side changes.

## Implementation sketch
No fork changes required for the share path. The Hoverboard firmware's
`flashErase`/`flashWriteBuffer`/`flashReadBuffer` (`Src/setup.c:1052`,
`:1082`, `:1090`) get rewritten to call libopencm3 flash APIs. **Bench validation note:** regtrace's emulator
doesn't model FMC peripheral feedback (BUSY toggling, EOP latching,
WPERR on protected sectors). On real silicon the busy-poll loops will
spin a real number of cycles; this vector's `read_responses` short-
circuits them. A bench test on actual hardware is still required
before relying on this for production firmware.

## Open questions
- Does the GD32F130 32 KB part have any sectors with default write
  protection that the libopencm3 `flash_unlock` path doesn't account
  for? Probably not, but a `flash_get_status_flags()` round-trip
  vector after a deliberate WPERR-trigger could prove it empirically.
- The `flash_clear_status_flags()` call in the libopencm3 path may
  write a slightly different byte mask than `fmc_flag_clear(END|WPERR)`
  — STM32F1 FLASH_SR has EOP/PGERR/WRPRTERR while GD32F1x0 FMC_STAT has
  END/PGERR/WPERR. Bit positions match; mask values may differ by 1
  bit. Worth verifying once the trace lands.
