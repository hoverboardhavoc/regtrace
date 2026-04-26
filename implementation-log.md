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

(Populated as implementation progresses.)
