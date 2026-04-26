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

### v0.1 gates — current status
After scaffolding and component tests:
- Gate 1 (`regtrace selftest`): passes everything except arm-none-eabi-gcc and the (uncloned) sibling repos. Once the toolchain is installed and `selftest --bootstrap` is run, this gate should pass.
- Gates 2-5: blocked on arm-none-eabi-gcc.
- Gate 6: blocked on Gates 2-5.
- All Python-side components have unit-test coverage (16 tests, all passing).
