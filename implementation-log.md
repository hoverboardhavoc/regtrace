# implementation-log.md

Running log of implementation decisions, choices, and inconsistencies encountered while building regtrace from SPEC.md.

## Spec inconsistencies addressed before implementation

These were decided pre-implementation and applied to SPEC.md in the same commit as this file.

### 1. Vector filename convention — `<peripheral>_<name>`
The spec previously showed both `timer_pwm_init.elf` and `timer_pwm_init_center_aligned_16khz.elf` for the same vector.
**Decision:** ELF/trace basename = `<peripheral>_<name>`, where `<peripheral>` is the YAML's parent directory under `vectors/` and `<name>` is the YAML's `name:` field (which must equal the YAML basename).
**Applied:** §Project layout pinned the rule. Gate 2 in v0.1 now uses the long form.

### 2. Example vector trimmed to v0.1-runnable impls
The §Snippet harness example declared `libopencm3/gd32f1x0` even though v0.1 scope says that implementation is stub-only.
**Decision:** Drop `libopencm3/gd32f1x0` from the example. `default_compare` becomes auto-derived for the remaining 2 impls and is removed from the YAML.

### 3. `regtrace verify` folded into `compare`
`verify` was referenced in the bisect example and PR-reviewer mention but never specified.
**Decision:** No separate `verify` command. `compare` accepts a new flag form `--against-trace=<path>` for golden-file checking. All `verify` mentions rewritten.

### 4. `--against=` overload — resolved by #3
After #3, `--against=` takes only impl slugs (in `compare`), and `--against-trace=` takes a golden path. No further action.

### 5. `regtrace regression` flag scheme — `--baseline=<path>`
Workflow showed `--baseline=golden/`; v0.3 Gate 2 showed `--library=… --against=…`.
**Decision:** `--baseline=<path>` is canonical. v0.3 Gate 2 rewritten to use it.

### 6. Rev resolution for branch names like `master`
`git describe --tags --always --dirty` cannot produce a branch name, but the spec uses `master/` as a rev directory.
**Decision:** `git describe` is used only for auto-detection (when `--library-rev=` is omitted). When `--library-rev=<value>` is passed, the value is taken verbatim — including branch names like `master`. Spec note added under §Clean-tree gating.

### 7. `build_assets/` directory key
Currently `build_assets/<target>/` but startup/linker files differ across HALs.
**Decision:** `build_assets/<library>/<target>/`. Library first because startup files vary more by library than by chip family.

### 8. SPL startup source contradiction
Failure-mode playbook pointed at `~/.platformio/.../cmsis/`; build pipeline says startup is vendored.
**Decision:** Startup files are vendored under `build_assets/<library>/<target>/`. The PlatformIO path is mentioned only as a *reference to copy from* when adding a new target. Failure-mode playbook entry rewritten to make this clear.

### 9. `assert_only` / `ignore` YAML schema (v0.2+)
Decided in open questions but never written into the schema.
**Decision:** Two optional, mutually-exclusive top-level fields. Lists of symbolic address ranges using the same form as trace records.

```yaml
assert_only:                          # optional, v0.2+
  - <TIM1_BASE>+0x00..0x44
# OR (mutually exclusive)
ignore:                               # optional, v0.2+
  - <RCU_BASE>+0x18                   # AHBEN — clock enables vary by HAL
```

### 10. `read_responses` syntax
Spec showed scalar form only.
**Decision:** Value can be a scalar (constant — returned every read) or a list (returned in order, last value sticks once exhausted).

```yaml
read_responses:
  <ADC_BASE>+0x08: 0x00                  # scalar
  <ADC_BASE>+0x10: [0x01, 0x01, 0x00]    # list — 1, 1, then 0 thereafter
```

### 11. Smaller fixes (bundled)
- YAML `body:` example for `libopencm3/gd32f1x0` used `#` (Python comment) — fixed to `//` (and removed since #2 dropped that impl).
- `BUILD.txt` moved from `golden/<library>/<rev>/BUILD.txt` to `golden/<library>/<rev>/<target>/BUILD.txt`. Per-target gcc/flag drift is now faithfully recorded.
- `${REGTRACE_WORKSPACE}` interpolation in `bootstrap.toml` is non-standard TOML — needs a custom resolver. Spec now notes this.
- Added `regtrace clean --libs` and `regtrace re-extract` to the §Workflow listing.

## Implementation decisions made during build

### Python 3.14 (not 3.10)
Spec requires ≥3.10. Only Python 3.14 is available on this system (Homebrew). Using 3.14; nothing in the deps requires <3.14.

### `tomli` only on Python <3.11
Standard-library `tomllib` exists from 3.11 onward. `pyproject.toml` makes `tomli` a conditional dep. `bootstrap.py` imports `tomllib` on 3.11+ and falls back to `tomli`.

### `arm-none-eabi-gcc` install requires sudo — user action
`brew install --cask gcc-arm-embedded` runs `installer -pkg` under `sudo`, which needs a terminal-attached password prompt. The autonomous install attempt failed:
```
sudo: a terminal is required to read the password
```
This is a one-time user action. The user should run:
```
! brew install --cask gcc-arm-embedded
```
in this session (the `!` prefix in Claude Code runs the command in the user's terminal). Build/trace gates will fail until the toolchain is on PATH.

### `git-lfs` installed but not configured
`git lfs install` (per-user) and `git lfs install --system` are user actions. The `.gitattributes` declares the LFS filter for `golden/**/*.elf`; the actual filter only kicks in once `git lfs install` has been run. v0.1 has no goldens checked in yet, so this isn't urgent.

### CLI surface — small additions beyond SPEC.md
- `compare --target=<id>` flag added to support `--against-trace=` from a bisect, where the target isn't always derivable from the vector context.
- `selftest --target=<id>` accepts but ignores the flag at v0.1 (spec says it's v0.5+); printed warning.

### `re-extract` as a top-level command, not a flag
SPEC.md mentions `regtrace re-extract <golden.elf>` as its own command form. Implemented as `regtrace re-extract` rather than `compare --re-extract`.

### Targets schema (v0.1 minimum)
A target `.toml` declares: `peripheral_ranges` (list of address-range pairs to filter trace events to), `peripheral_bases` (symbolic base → numeric base map for symbolisation), `register_names` (per-base offset → name comment generator), `reset_values` (per-base offset → reset value to seed), and `bit_band_aliases` (only on Cortex-M3 — alias address → underlying-word mapping). For Cortex-M0/M0+ targets like stm32f0, `bit_band_aliases` is omitted.

### Sentinel halt mechanism
The vendored startup sets `LR = _sentinel | 1` (Thumb) and branches to `regtrace_test`. On return, execution falls into a `BKPT #0x55` instruction at `_sentinel`. Unicorn raises `UC_ERR_EXCEPTION` on BKPT; the extractor treats `(errno == UC_ERR_EXCEPTION) and (last_pc == SENTINEL_PC)` as a clean exit. No need for `until=` to land on the BKPT itself.

### Extractor lazy MMIO mapping
Unicorn requires every accessed page to be mapped or it raises `UC_ERR_READ_UNMAPPED` / `UC_ERR_WRITE_UNMAPPED`. Reset-value-seeded pages are mapped up front; everything else is mapped lazily from the `MEM_*_UNMAPPED` hooks (returning True to retry). Page granularity is 64 KiB so any peripheral cluster is covered in one map call.

### Comparator address-key strategy
`_diff_ordered` keys writes/reads on `(op, size, address_str, value)`. The `address_str` is symbolic (`<TIM1_BASE>+0x00`), which means traces compare across families: a write to TIM1+0x00 on stm32f0 matches a write to TIM1+0x00 on gd32f1x0 even though the numeric addresses differ. This is what makes share-or-split decisions work.

### `assert_only` / `ignore` not yet wired into the comparator
The schema validates and parses but the comparator doesn't apply the filter. Land in v0.2 alongside the `with_polling` mode work.

### Toolchain installed via xPack tarball (no sudo)
The `brew install --cask gcc-arm-embedded` cask requires sudo. As a no-sudo alternative I downloaded the official xPack ARM toolchain v15.2.1-1.1 from `github.com/xpack-dev-tools/arm-none-eabi-gcc-xpack/releases/`, extracted it under `~/opt/`, and symlinked the binaries into `~/.local/bin/`. xPack is the same toolchain ARM ships, just packaged as a self-contained tarball — same gcc version, same behaviour. `arm-none-eabi-gcc --version` reports "xPack GNU Arm Embedded GCC arm64 15.2.1 20251203".

### gd-spl HAL builder — actually implemented in v0.1
I'd initially scoped gd-spl as v0.2, but the spec's v0.1 explicitly covers `gd-spl/v3.0.0/gd32f1x0/`. So gd-spl is fully wired in v0.1:
- `LIBRARY_TO_REPO` maps `gd-spl` → the `GD32Firmware` repo entry in bootstrap.toml
- `build_gd_spl()` in `hal.py` compiles every `gd32<family>_*.c` into a static archive; sources that fail to compile (USB stack and similar that depend on features outside v0.1 scope) are excluded
- `build_assets/gd-spl/gd32f1x0/cmsis-stubs/` contains:
  - `core_cmInstr.h`, `core_cmFunc.h` — minimal CMSIS-Core 4.x compatibility shims (GD ships only `core_cm3.h` and expects the user to provide the split-out instruction/function headers)
  - `gd32f1x0_libopt.h` — minimal version including all SPL peripheral headers
- Pinned GD-SPL `-std=gnu11` because gcc 15 defaults to C23 where `bool` is a keyword, conflicting with the SPL's `typedef enum { … } bool`
- Used `v3.2.0` as the rev label (matches the SPL header `\version` markers); the GD32Firmware repo is a pristine vendor mirror with no tags

### Bit-banding handled but not exercised yet
The extractor handles Cortex-M3 bit-band aliases (translating writes to `0x42xxxxxx` aliases into RMW writes to the underlying word at `0x40xxxxxx`). The first vector doesn't exercise this path — both libopencm3 timer_set_mode and SPL timer_init use direct word stores. A future vector (e.g., GPIO bit-set/clear via PSOR/PCOR alias) would exercise it.

### v0.1 gates — all six pass
- **Gate 1** `regtrace selftest --bootstrap`: PASS. Cloned all three sibling repos (libopencm3, GD32Firmware, Hoverboard firmware); validates toolchain and python deps.
- **Gate 2** `regtrace build vectors/timer/pwm_init_center_aligned_16khz.yaml`: PASS. Both `gd-spl/gd32f1x0` (16 KB ELF) and `libopencm3/stm32f0` (81 KB ELF) compile.
- **Gate 3** `regtrace trace <elf>`: PASS for both. gd-spl trace contains 17 events (10 W + 7 R, lots of redundant CR1 RMW); libopencm3 trace contains 7 events (5 W + 2 R, direct stores).
- **Gate 4** `regtrace compare timer_pwm_init_center_aligned_16khz`: PASS — produces structured diff. The traces are divergent in `register_writes` mode (different order and count of writes), but all final-state register values match.
- **Gate 5** `ls golden/<library>/<rev>/<target>/`: PASS. Both impl pairs captured (.elf + .trace + BUILD.txt) under `golden/gd-spl/v3.2.0/gd32f1x0/` and `golden/libopencm3/v0.8.0-457-g7b6c2205/stm32f0/`.
- **Gate 6** `ls decisions/v0.1/`: PASS. `TIMER.md` (decision: share, confidence: partial) and `ADC.md` (deferred to v0.2) present, plus `decisions/TEMPLATE.md`.

All 16 pytest tests pass. The extractor unit test uses a hand-rolled in-memory ELF (no toolchain needed) so the test suite stays fast and self-contained.

### TIMER decision — empirical finding worth noting
The first comparison reveals a real implementation pattern difference: gd-spl's `timer_init` reads CR1 four times and re-writes it to the same value 0x60 between each peripheral write (defensive RMW idiom from the vendor SPL). libopencm3 just stores 0x60 once. Both produce identical *final* register state. In `register_writes` mode this is divergent; in `final_state` mode it'd match. The TIMER decision recommends **share** based on the final-state equivalence.
