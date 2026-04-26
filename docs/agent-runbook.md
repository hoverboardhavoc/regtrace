# Agent runbook

This is the field guide for an autonomous agent picking up regtrace from scratch. Read SPEC.md first, then follow the order here.

## 0. Bootstrap

```bash
git clone <regtrace-repo> ~/dev/regtrace
cd ~/dev/regtrace
python3.10 -m venv .venv && source .venv/bin/activate
pip install -e .
regtrace selftest --bootstrap
```

`--bootstrap` clones the sibling repos in `bootstrap.toml` (libopencm3, GD32Firmware, STM32CubeF1, ...) into `${REGTRACE_WORKSPACE}` (default `~/dev/c/`).

If the ARM toolchain isn't on PATH, install it:
- macOS (preferred): `brew install --cask gcc-arm-embedded`
- macOS (no-sudo fallback): download the xPack tarball from `github.com/xpack-dev-tools/arm-none-eabi-gcc-xpack/releases/`, extract under `~/opt/`, symlink the `bin/arm-none-eabi-*` entries into `~/.local/bin/`.
- Linux: `apt install gcc-arm-none-eabi`.

For RISC-V work (v0.6+): `riscv-none-elf-gcc` from the matching xPack repo. Same install pattern.

## 1. Daily commands

```bash
# Compile a vector for all declared impls
regtrace build vectors/timer/pwm_init_center_aligned_16khz.yaml

# Extract a trace from a built ELF
regtrace trace build/.../timer_pwm_init_center_aligned_16khz.elf

# Compare canonical pair (from default_compare in YAML)
regtrace compare timer_pwm_init_center_aligned_16khz

# Compare specific impls
regtrace compare timer_pwm_init_center_aligned_16khz \
    --against=gd-spl/gd32f1x0,libopencm3/stm32f0

# All-pairs N×N
regtrace compare timer_pwm_init_center_aligned_16khz --all-pairs

# Diff against a stored golden trace file
regtrace compare <vector> --against-trace=golden/.../foo.trace

# Capture goldens (build + extract + provenance)
regtrace capture --library=libopencm3 --vectors=vectors/

# Capture against a specific historical rev
regtrace capture --library=libopencm3 --library-rev=v0.8.0 --vectors=vectors/

# Regression run vs a golden tree
regtrace regression --baseline=golden/libopencm3/v0.8.0/

# Refresh .trace from .elf without recompiling
regtrace re-extract golden/libopencm3/v0.8.0/.../foo.elf

# Evict the HAL static-lib cache
regtrace clean --libs
```

## 2. Common workflows

### Mining a new vector

1. Find a representative API call sequence in a real project (priority: hoverboard `Src/setup.c`, then SPL `Examples/`, then real-world projects).
2. Translate into per-impl YAML bodies. Vector YAML lives at `vectors/<peripheral>/<name>.yaml`. The `name:` field MUST equal the YAML basename.
3. Build, trace, compare. Pick `mode: register_writes` if order matters, `final_state` if you only care about the end state.
4. If the comparator surfaces noise (clock-enable writes that vary by HAL), use `ignore: [<RCC_BASE>+0x18]` or `assert_only: [<TIM1_BASE>+0x00..0x44]` to scope the comparison.

### Making a share-or-split decision

1. Mine vectors covering the peripheral's API surface (~5-10 per peripheral).
2. Run `regtrace compare <vector> --all-pairs` for each.
3. Map the diff outcomes onto the four-level criterion in SPEC.md (bit-identical → share; identical-but-reset-values → share-with-shim; one-or-two bit-fields differ → share-with-macro; fundamentally different → split).
4. Write `decisions/<regtrace-version>/<PERIPHERAL>.md` using `decisions/TEMPLATE.md`. Cite the goldens by path.

### Producing a draft libopencm3 patch

1. In the libopencm3 sibling repo: `git checkout -b regtrace/<purpose> master`.
2. Add new files (`include/libopencm3/gd32/<family>/<periph>.h` forwarders, `lib/gd32/<family>/Makefile` updates, dispatcher entries in `stm32/<periph>.h`).
3. Verify build: `make TARGETS=<family>/<chip> lib`.
4. End-to-end validate by capturing both a `libopencm3/<family>` and `gd-spl/<family>` trace for the same vector and confirming they match.
5. Commit on the branch (this is fine to do without asking — see saved feedback memory).
6. Export with `git format-patch -1 -o ~/dev/regtrace/draft-prs/<version>/`.
7. Write `~/dev/regtrace/draft-prs/<version>/<peripheral>-PR-DESCRIPTION.md` with the submission notes (CLA, bench-validation checklist, links to evidence).

**NEVER push to libopencm3 upstream and NEVER `gh pr create` against upstream**, per SPEC.md:183.

## 3. Troubleshooting

- **"trace is empty"** — emulator fault. Re-run with `regtrace trace --debug` to see the per-instruction execution log; check the LR/RA sentinel was hit cleanly (not a step-cap timeout).
- **"trace differs but I expected match"** — check (1) compiler flags pinned across both impls, (2) bit-banding alias→underlying translation in `targets/<chip>.toml` (Cortex-M3/M4), (3) `reset_values` seeded for any registers the function reads before writing, (4) `read_responses` declared if the function polls.
- **"libopencm3 doesn't have a driver for peripheral X"** — expected at v0.1; mine the SPL behaviour, write down what would be needed in a follow-up `decisions/`.
- **"vendor SPL function name not found"** — mismatched SPL version. Check `bootstrap.toml` pin.
- **"ld error: uses VFP register arguments"** — ABI mismatch (snippet vs HAL lib). For STM32F4, `TARGET_FLAGS["stm32f4"]` includes `-mfloat-abi=hard -mfpu=fpv4-sp-d16` to match libopencm3's hard-float build.
- **"#error stm32 family not defined"** when compiling a libopencm3 common driver for a GD32 family** — the dispatcher in `include/libopencm3/stm32/<periph>.h` doesn't have a `#elif defined(GD32xxxx)` branch yet. Add one (see the v0.5 GD32F10X port patch for the pattern).
- **"`make clean` fails with `env: python: No such file or directory`"** — older libopencm3 revs (≤ v0.8.x) have `#!/usr/bin/env python` shebangs. The build pipeline already prepends a python-shim dir to PATH for libopencm3 makes; if you invoke `make` directly outside the pipeline, prepend `~/.cache/regtrace/shim/bin/` to PATH yourself.

## 4. What NOT to do

- **Don't push to upstream repos.** Local commits in sibling repos are fine; pushes never happen without explicit user ask. PR creation against upstream is forbidden by SPEC.md regardless of authorization.
- **Don't paste vendor SPL source into regtrace.** SPL is BSD; we compile it as an oracle but don't host its source.
- **Don't claim a milestone passes without running its gate.** "Should work" is not validation. The gates in SPEC.md exist to be run.
- **Don't use bench-validated SPL behaviour as the authoritative answer.** regtrace's emulator can't model peripheral feedback. If a bug surfaces only when the silicon responds, regtrace won't catch it. Note this limitation in the decision doc.
