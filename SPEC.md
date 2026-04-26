# regtrace

A register-trace comparison tool for validating that two implementations of a microcontroller HAL produce equivalent peripheral configurations.

Architecture-agnostic in design — compile, disassemble, capture writes to memory-mapped peripheral regions, diff. Initial implementation targets ARM Cortex-M (the immediate need is GD32F1x0 libopencm3 vs SPL), but the same methodology applies to any architecture with memory-mapped I/O and a supported disassembler: Cortex-A/R, RISC-V (e.g., `GD32VF103`), Xtensa (ESP32), MSP430, AVR, PIC.

## Problem

Vendor and community HALs for the same chip wrap the same underlying silicon registers behind different APIs. There is no machine-readable contract that says "this `libopencm3.timer_set_mode(TIM1, ...)` produces the same final TIM1_CR1 register state as `SPL.timer_init(TIMER0, ...)` for equivalent params." The same gap exists for any HAL pair on any chip: vendor SDK vs community library vs higher-level framework, each independently developed against the same TRM, with no automated way to confirm they configure the silicon identically.

Today this is verified by reading the TRM, hand-tracing register pokes, or bench testing — slow, error-prone, and incomplete.

`regtrace` automates the comparison: compile small snippets that exercise each HAL's API, capture the resulting register-write trace, diff. Equivalent traces are evidence the two HALs configure the silicon identically; divergent traces flag a real bug or a deliberate design difference worth investigating.

## Goals

1. **Cross-HAL validation.** Confirm libopencm3 GD32F1x0 timer init produces the same register state as GigaDevice SPL.
2. **Regression detection.** When a libopencm3 PR refactors a shared file (e.g., `stm32/common/timer_common_all.c` to add `#ifdef GD32_*`), prove the existing STM32F0/F1/F4 traces are unchanged.
3. **Vendor-bug discovery.** Compare libopencm3 traces against ST Cube LL or GD `patched`-branch traces; differences may surface latent bugs in either library.
4. **Documentation.** A passing trace match is more compelling evidence in an upstream PR than a verbal "I tested it."
5. **Per-peripheral share-or-split decision.** When considering "should GD32F1x0's TIMER share `stm32/common/timer_common_all.h`?", trace comparison answers it empirically rather than by reading TRMs side-by-side and trusting the result. Bit-identical traces → share is accurate; divergent traces → split is the cleaner architectural choice.

## Non-goals

- Full silicon emulation. We only model peripheral memory writes; we don't simulate timer counters, ADC SARs, DMA transfers, or interrupts.
- Dynamic-state comparison. Polling loops, hardware-triggered events, time-dependent behaviour are out of scope.
- Replacing bench validation. `regtrace` complements hardware testing; it does not replace it. Some bugs only surface when the silicon actually responds.

## Bootstrap and dependencies

This project is intended to be developable end-to-end by an autonomous LLM agent without manual setup hand-holding. Every dependency below has a deterministic install path.

### System tools

| tool | macOS | Linux (Debian/Ubuntu) | purpose |
|---|---|---|---|
| Python ≥ 3.10 | `brew install python@3.12` | `apt install python3 python3-pip python3-venv` | extractor + harness |
| GCC ARM cross-compiler | `brew install --cask gcc-arm-embedded` (or use the PlatformIO-bundled one at `~/.platformio/packages/toolchain-gccarmnoneeabi/`) | `apt install gcc-arm-none-eabi` | compile snippets to ELF |
| Git | usually preinstalled | `apt install git` | clone repos |
| Git LFS | `brew install git-lfs` | `apt install git-lfs` | store golden `.elf` blobs |
| Make | preinstalled | `apt install build-essential` | drive libopencm3 + SPL builds |

### Python dependencies

Pin in `pyproject.toml` / `requirements.txt`:

```
capstone>=5.0       # disassembly across ARM/RISC-V/etc.
pyelftools>=0.30    # ELF parsing
pyyaml>=6.0         # test-vector format
click>=8.1          # CLI
tomli>=2.0          # per-target metadata
```

### External repos to clone

The agent should clone these into known sibling paths under `~/dev/c/` (or whatever the chosen workspace root is):

| repo | URL | purpose |
|---|---|---|
| **libopencm3** | https://github.com/libopencm3/libopencm3 | the HAL under development. F1x0 stub (`gd32/f1x0/`) already exists. |
| **GD32 vendor SPL mirror** | https://github.com/CommunityGD32Cores/GD32Firmware | pristine vendor SPL for all GD32 families on `main`; bug-fixed on `patched`. |
| **Hoverboard firmware** (test-vector source) | https://github.com/RoboDurden/Hoverboard-Firmware-Hack-Gen2.x-GD32 | mine `Src/setup.c` + `Src/it.c` for representative API call sites. |
| **GD32 PlatformIO platform** (build-system reference) | https://github.com/CommunityGD32Cores/platform-gd32 | how PIO drives SPL builds today; useful when porting later. |
| **GD32 SPL package** (build-system reference) | https://github.com/CommunityGD32Cores/gd32-pio-spl-package | PIO wrapper around vendor SPL. |

### Reference projects (for vector mining + idiom comparison)

These are read-only references — the agent should clone them when it needs to mine vectors but never modify them:

| repo | URL | what it shows |
|---|---|---|
| `ZhuYanzhen1/miniFOC` | https://github.com/ZhuYanzhen1/miniFOC | FOC on GD32F1x0 with stock SPL — closest to our use case |
| `the6p4c/peadee` | https://github.com/the6p4c/peadee | USB-PD on F1x0 with stock SPL |
| `EFeru/hoverboard-sideboard-hack-GD` | https://github.com/EFeru/hoverboard-sideboard-hack-GD | sister hoverboard hack, uses stock SPL |
| `gd32-rust/gd32f1x0-hal` | https://github.com/gd32-rust/gd32f1x0-hal | Rust HAL for F1x0 — peer artifact for cross-checking peripheral behavior |
| `Icenowy/gd32f1x0-libopencm3-experiments` | https://github.com/Icenowy/gd32f1x0-libopencm3-experiments | prior art on the libopencm3 GD32F1x0 port (stalled 2021) |
| `cjacker/gd32f10x_firmware_library_gcc_makefile` | https://github.com/cjacker/gd32f10x_firmware_library_gcc_makefile | minimal gcc + Makefile build of stock SPL — reference for the snippet harness |
| `maxgerhardt/pio-gd32f130c6` | https://github.com/maxgerhardt/pio-gd32f130c6 | minimal PIO + GD32F130 SPL test project |

### Optional oracles (for v0.4+)

| oracle | URL | install method |
|---|---|---|
| STM32CubeF1 (Cube LL for STM32F1) | https://github.com/STMicroelectronics/STM32CubeF1 | `git clone` |
| STM32CubeF0 (Cube LL for STM32F0) | https://github.com/STMicroelectronics/STM32CubeF0 | `git clone` |
| STM32CubeF4 (Cube LL for STM32F4) | https://github.com/STMicroelectronics/STM32CubeF4 | `git clone` |

### Documentation references

The agent should treat these as authoritative sources of truth — when SPL docstrings and TRM disagree, the TRM wins:

| doc | URL | when to consult |
|---|---|---|
| GD32F1x0 User Manual Rev 3.6 | https://gd32mcu.com/data/documents/userManual/GD32F1x0_User_Manual_Rev3.6.pdf | F130 register layouts, peripheral behavior |
| GD32F10x User Manual | https://gd32mcu.com/en/download/0?kw=GD32F10x | F103 register layouts |
| GD32E23x User Manual | https://gd32mcu.com/en/download/0?kw=GD32E23x | E230 register layouts |
| ARM Cortex-M3 TRM (DDI 0337I) | https://developer.arm.com/documentation/ddi0337/i/ | NVIC, SCB, SysTick, bit-banding |
| libopencm3 docs (auto-gen Doxygen) | https://libopencm3.org/docs/latest/ | API surface for the HAL under development |
| STM32 reference manuals (per-family) | https://www.st.com/en/microcontrollers-microprocessors.html — search the chip's product page (e.g., `STM32F103C8` → "Resources" → "Reference manual"). Direct PDF for STM32F1 family RM is RM0008. | when comparing to STM32 family for share-or-split decisions |

## For autonomous LLM agents

This section is operational guidance for agents working on regtrace without human review of every step.

### Workspace layout

```
~/dev/regtrace/                 # this repo (the tool)
~/dev/c/libopencm3/             # the HAL we're extending
~/dev/c/GD32Firmware/           # vendor SPL mirror (oracle)
~/dev/c/Hoverboard-Firmware-Hack-Gen2.x-GD32/  # test vector source
~/dev/c/<reference projects>    # cloned as needed
```

### Self-validation gates

Each milestone has a verifiable command sequence the agent can run. If exit code is 0 and output matches expectation, the milestone is achieved. The agent should not advance to the next milestone until the current one's gate passes.

The gates are documented per-milestone in the Roadmap section.

### Operational principles

- **Never claim a milestone passes without running its gate.** "Should work" is not validation.
- **Pin everything.** Every commit should be reproducible. Specifically: gcc version, libopencm3 commit, SPL version. If it's not pinned, the agent's traces aren't comparable to anyone else's.
- **Prefer empirical over inferred.** If a question is "does GD32F1x0 timer share register layout with STM32F0?", the answer is a regtrace diff, not a TRM read.
- **Commit frequently with reproducible messages.** Each commit should be standalone — buildable from a fresh checkout. Failed-experiment commits should be reverted, not amended over.
- **Write tests for every comparator extension.** When adding a new comparison mode (e.g., `with_polling`), include unit tests with fixtures.
- **When stuck:** dump current state to a `STATE.md` in the workspace root with: what you tried, what failed, what you'd try next. Don't silently spin or fabricate progress.
- **Don't paste vendor SPL source into regtrace.** Vendor SPL is BSD; we may compile it as an oracle but we don't host its source. Same rule for Cube LL.
- **Never auto-submit upstream PRs.** regtrace produces decision documents (`decisions/<version>/<peripheral>.md`) and draft patches (`draft-prs/<version>/*.patch`). Opening PRs against libopencm3, GD32Firmware, or any other upstream is a human-controlled action. An agent that thinks it has a great PR ready should write the patch + description into the regtrace workspace and stop. Do not run `gh pr create` against upstream repos. The bar for "regtrace says this is right" → "spam the maintainer's inbox" is not auto-promoting.

### Self-test / smoke-test command

The agent can verify its own bootstrap with:

```bash
$ regtrace selftest
[ok] arm-none-eabi-gcc 12.3.1 found
[ok] capstone 5.0.x available
[ok] pyelftools 0.30+ available
[ok] libopencm3 at ~/dev/c/libopencm3 (commit: 7b6c2205)
[ok] GD32Firmware at ~/dev/c/GD32Firmware (branch: main)
[ok] sample snippet compiles for stm32f0
[ok] trace extractor produces non-empty output
PASS — bootstrap valid
```

Implemented in v0.1.

### Failure-mode playbook

Documented decision tree for common stuck states:

| symptom | likely cause | next step |
|---|---|---|
| "snippet compiles for libopencm3 but not for SPL" | missing system_<chip>.c or startup file | check `~/.platformio/packages/framework-spl-gd32/gd32/cmsis/`; copy or reference startup file. |
| "trace is empty" | extractor didn't recognise stores in this snippet | check the snippet's disassembly via `arm-none-eabi-objdump -d`; verify there are stores to peripheral memory; if so, file extractor bug. |
| "trace differs but I expected match" | check (1) compiler flags pinned, (2) bit-banding handled, (3) RMW resolved correctly. If all OK, the divergence is real. |
| "libopencm3 doesn't have driver for peripheral X" | expected at v0.1 stage — log it as an open peripheral, mine the SPL behavior, write down what would be needed. |
| "vendor SPL function name not found in headers" | mismatched SPL version. Re-check version pin, or this peripheral isn't supported on this chip. |

## Approach

### 1. Snippet harness

Each "test vector" is a self-contained C function calling one or more HAL APIs with concrete parameters. Two snippets per vector — one per HAL implementation under comparison.

Example:

```yaml
# vectors/timer/pwm_init_center_aligned_16khz.yaml
name: pwm_init_center_aligned_16khz
description: |
  Center-aligned PWM @ 16 kHz, repetition counter = 1 to fire UPIF
  once per period. The hoverboard FOC config used in production.

# Each implementation is keyed `<library-id>/<target-id>` matching the
# directory structure under golden/. The library-id distinguishes which
# HAL is being compiled (gd-spl vs libopencm3 vs cube-ll), and target-id
# distinguishes which chip family (gd32f1x0 vs stm32f0 vs gd32f10x ...).
# Both are required because the same library can produce different
# traces for different targets.
implementations:
  gd-spl/gd32f1x0:
    includes: [gd32f1x0.h, gd32f1x0_timer.h]
    body: |
      timer_parameter_struct ts;
      ts.alignedmode       = TIMER_COUNTER_CENTER_BOTH;
      ts.counterdirection  = TIMER_COUNTER_UP;
      ts.period            = 2250;
      ts.prescaler         = 0;
      ts.repetitioncounter = 1;
      ts.clockdivision     = TIMER_CKDIV_DIV1;
      timer_init(TIMER0, &ts);
      timer_event_software_generate(TIMER0, TIMER_EVENT_SRC_UPG);

  libopencm3/stm32f0:
    includes: [libopencm3/stm32/timer.h]
    body: |
      timer_set_mode(TIM1, TIM_CR1_CKD_CK_INT, TIM_CR1_CMS_CENTER_3, TIM_CR1_DIR_UP);
      timer_set_period(TIM1, 2250);
      timer_set_prescaler(TIM1, 0);
      timer_set_repetition_counter(TIM1, 1);
      timer_generate_event(TIM1, TIM_EGR_UG);

  libopencm3/gd32f1x0:        # the implementation under development
    includes: [libopencm3/gd32/f1x0/timer.h]
    body: |
      # ...same as stm32/f0 if shared, else GD-specific calls
      timer_set_mode(TIM1, TIM_CR1_CKD_CK_INT, TIM_CR1_CMS_CENTER_3, TIM_CR1_DIR_UP);
      ...
```

Library-ids are chosen from a short, stable vocabulary:

| library-id | refers to |
|---|---|
| `gd-spl` | GigaDevice Standard Peripheral Library (vendor SDK, BSD-3-Clause) |
| `gd-spl-patched` | Same SPL with the `patched`-branch fixes from `CommunityGD32Cores/GD32Firmware` |
| `libopencm3` | libopencm3 — the HAL under development |
| `cube-ll` | STMicro Cube LL (low-level layer) |
| `cube-hal` | STMicro Cube HAL (higher-level handle-based) — rarely useful for register validation |
| `st-stperiph` | STMicro StdPeriph (deprecated; only relevant if comparing to legacy ST projects) |

Target-ids match the chip-family naming used by the libraries and `targets/<family>.toml`: `gd32f1x0`, `gd32f10x`, `gd32e23x`, `stm32f0`, `stm32f1`, `stm32f4`, etc.

The harness wraps each `body` in a `__attribute__((noinline))` test function with a fixed name, generates a tiny entry point, links against the appropriate HAL static library for the `library-id`/`target-id` combo, and produces an ELF.

### 2. Trace extraction

Disassemble the test function and identify writes to memory-mapped peripheral regions. The architecture-specific bits are:

- **Disassembly backend** — capstone (covers ARM, ARM64, RISC-V, MIPS, x86, PowerPC, Sparc, Xtensa-via-plugin, etc.).
- **Peripheral address ranges** — declared per chip family, not per architecture. For Cortex-M3 STM32/GD32: SoC peripheral block `0x40000000`–`0x5FFFFFFF`, core peripherals `0xE0000000`–`0xE00FFFFF`. For RISC-V GD32VFx: different ranges. For ESP32, AVR, etc., declared as needed.
- **Architecture quirks** — Cortex-M3 bit-banding aliases (only relevant on chips that have them); RISC-V Zicsr CSR access for some peripherals; AVR special-function-register space sitting in the same address space as RAM. Each is a per-target plugin.

Output: ordered list of `(register_address, value, store_size)` tuples, with peripheral base addresses normalised to symbolic names (e.g., `<TIM1_BASE>+0x00` rather than `0x40012C00`) so traces compare across target families.

Implementation: Python with `capstone` for disassembly + `pyelftools` for symbol resolution. Dataflow walk to resolve register-relative stores back to their absolute target address. The dataflow walk is mostly architecture-agnostic; the load-store instruction recognition is the per-architecture seam.

### 3. Comparison

Three comparison modes per test vector, configurable:

- **`register_writes`** — pure store sequence. Compare ordered list of writes. Default for init functions.
- **`final_state`** — set-of-registers final value. Order-independent; assumes all writes start from a known reset state. Better for cases where bit-set order doesn't matter.
- **`with_polling`** — recognise polling loops (load-compare-branch on the same address) and treat them as a unit. Compare initial config + verify polling target is the same. Used for ADC calibration, HSE startup, etc.

Per-vector metadata declares which mode applies.

### 4. Regression mode

For PR-validation: capture traces for STM32F0/F1/F4 against a baseline commit, store as golden files in `golden/`. Re-run after refactor; any diff fails CI.

#### Directory layout

Goldens are organised by `library × version × target × vector`. Each golden is **two artifacts**:

- **`.elf`** — the compiled snippet binary, the canonical source-of-truth.
- **`.trace`** — the extracted register-write trace, derived from the `.elf`. Human-readable, diffable.

```
golden/
├── libopencm3/
│   ├── v0.8.0/
│   │   ├── stm32f0/
│   │   │   ├── timer_pwm_init_center_aligned_16khz.elf
│   │   │   └── timer_pwm_init_center_aligned_16khz.trace
│   │   ├── stm32f1/...
│   │   └── stm32f4/...
│   ├── v0.9.0/...
│   └── master/...                     # rolling pre-release baseline
├── gd-spl/
│   ├── v3.0.0/gd32f1x0/...
│   ├── v3.4.0/gd32f1x0/...
│   └── patched/gd32f1x0/...           # CommunityGD32Cores/GD32Firmware patched branch
└── cube-ll/
    └── v1.8.6/stm32f1/...
```

This lets you:
- Diff any two `(library, version)` pairs for the same `(target, vector)` from text traces alone, no build env required.
- Re-extract traces from stored `.elf` if regtrace's extractor improves (better dataflow analysis, new register-name maps).
- `git bisect` libopencm3 between two versions to find the commit that changed a trace.
- Track vendor SPL evolution across releases.
- Verify trace integrity — text trace and stored binary should always agree.

#### Why store the binaries

The `.elf` is the canonical artifact for several reasons:

- **Lowest barrier for PR reviewers.** A reviewer without arm-none-eabi-gcc / libopencm3 / Cube LL installed can still run `regtrace verify` against the stored `.elf` and confirm the proposed change matches expectations. Without binaries, every reviewer would need a full cross-compilation environment.
- **Toolchain rot resistance.** Years from now, the exact gcc / libopencm3 / SPL combination used to capture a golden may not be reproducible. The stored `.elf` survives.
- **Re-extractor compatibility.** If regtrace's analyzer adds a new feature (better RMW detection, additional register-name maps, support for a new architecture), re-running it against stored `.elf` regenerates richer traces without needing the original build env.
- **Verification.** Text traces alone can be tampered with or hand-edited. The `.elf` + extractor produces the trace deterministically — a third party can confirm `regtrace trace <golden.elf> == golden.trace` exactly.

#### Binary storage

ELF sizes per snippet are typically 5-50 KB. Estimated total for the project's scope (~50 vectors × 4 libraries × 3-5 targets × 3-5 versions tracked) ≈ 60-100 MB. Manageable but big enough that a strategy matters:

- **Default: git LFS.** Binaries under `golden/**/*.elf` tracked via `.gitattributes` lfs filter. Keeps the main repo's history small while preserving full version-control semantics.
- **Alternative: separate `regtrace-goldens-bin` sibling repo.** If LFS is undesirable, the binary tree lives in its own repo; main repo references via git submodule or release artifact URLs in trace files.
- **Optional dedup.** Byte-identical ELFs across versions get content-addressed (`golden/blobs/<sha256>.elf`) with symlinks from the version-tree. Saves significant space when an unchanged peripheral driver compiles identically across many library versions.

#### License obligations for redistributed binaries

- **GD32 SPL (BSD-3-Clause)**: binary redistribution requires reproducing the copyright notice and disclaimer in documentation. Ship a `NOTICES` file in the repo root with the SPL header text.
- **Cube LL ("Permissive Binary License")**: similar — includes attribution requirement, restricts use to ST chips. Document in `NOTICES`.
- **libopencm3 (LGPL-3.0)**: more involved. LGPL requires that users be able to relink the program with a different version of the library. For our use case (small test snippets statically linked against libopencm3), the spirit is satisfied if we ship: (a) the source of the snippet, (b) the libopencm3 commit hash used, (c) build instructions. The `.elf` itself doesn't need to be re-linkable, but the rest of the package must enable a determined user to rebuild from scratch. Document this in `NOTICES`. Each library version in `golden/libopencm3/<version>/` includes a `BUILD.txt` with the exact commit, gcc version, and compile flags used.

The build-provenance metadata is also embedded in each `.trace` file's header — that's primarily for reproducibility, doubles as license-compliance evidence.

#### Trace file format

Plain text, one record per line, sortable. Header metadata in `# ...` comments. Designed to diff cleanly in `git diff` and PR review.

```
# regtrace v0.2 — captured 2026-04-26T09:14:33Z
# vector:        timer_pwm_init_center_aligned_16khz
# library:       libopencm3
# library_commit: 7b6c2205
# target:        stm32f1
# compiler:      arm-none-eabi-gcc 12.3.1 (xPack)
# compile_flags: -Os -mcpu=cortex-m3 -mthumb
# mode:          register_writes      # register_writes | final_state | with_polling

W4 <TIM1_BASE>+0x00 0x00000080         # CR1: ARPE=1
W4 <TIM1_BASE>+0x2C 0x000008CA         # ARR: 2250
W4 <TIM1_BASE>+0x28 0x00000000         # PSC: 0
W4 <TIM1_BASE>+0x30 0x00000001         # RCR: 1
W2 <TIM1_BASE>+0x14 0x0001             # EGR: UG=1
```

Format details:
- **`Wn`** — write of `n` bytes (`W1` byte, `W2` half-word, `W4` word).
- **Address** — peripheral base symbolised + offset, never raw hex. Bases come from a per-target map (e.g., `targets/stm32f1.toml` lists `TIM1_BASE = 0x40012C00`). Symbolisation makes traces compare across architectures and across chips that share peripheral layout.
- **Value** — hex literal.
- **Comment** — optional, generated from the per-target peripheral register-name map. Comments are advisory, ignored by the comparator.
- **Order** — preserved (sequence-mode comparison). Set-mode comparators sort before diffing.

#### Capture command

Capture writes both the `.elf` and the derived `.trace`:

```bash
# Capture goldens for a specific library at the current checked-out version
$ regtrace capture --library=libopencm3 --vectors=vectors/timer/
  → writes golden/libopencm3/<auto-detected-rev>/<target>/<vector>.elf
  → writes golden/libopencm3/<auto-detected-rev>/<target>/<vector>.trace
  → writes golden/libopencm3/<auto-detected-rev>/BUILD.txt (provenance)

# Capture for a specific git commit (reproducible from any working dir state)
$ regtrace capture --library=libopencm3 --library-rev=v0.9.0 --vectors=vectors/

# Refresh existing goldens (requires explicit --update flag to overwrite)
$ regtrace capture --library=libopencm3 --library-rev=master --update

# Re-extract a trace from an already-stored .elf (no compilation needed)
$ regtrace re-extract golden/libopencm3/v0.9.0/stm32f1/timer_pwm_init.elf
  → rewrites only the .trace, leaves .elf untouched
```

The `--library-rev` form checks out the requested commit/tag in a worktree, builds, captures, and writes goldens under the right `golden/<library>/<rev>/` path. The user's primary checkout is untouched.

`re-extract` is what runs when regtrace's analyzer improves and you want to refresh trace files without rebuilding.

#### Refresh discipline

A behaviour-changing PR (deliberate register-default tweak, bug fix, silicon-erratum workaround) MUST update its target's goldens. The golden-file diff in the PR becomes the audit trail:

```
$ git diff golden/libopencm3/master/stm32f1/timer_pwm_init.trace
- W4 <TIM1_BASE>+0x00 0x00000080
+ W4 <TIM1_BASE>+0x00 0x000000C0      # ARPE=1, URS=1 (this PR adds URS to suppress UEV on UG)
```

Reviewers can immediately see "what changed at the register level" alongside the source change.

A *non-behaviour-changing* PR (refactor, code cleanup, comment update) MUST NOT change any goldens. CI gates this — golden diffs in such PRs fail until either:
- The author proves the behaviour change is intentional and updates goldens explicitly, or
- The author fixes the unintended regression.

#### Bisect for behaviour regressions

```bash
# Find the libopencm3 commit that changed the TIM1 init trace
$ cd ~/dev/c/libopencm3
$ git bisect start HEAD v0.8.0
$ git bisect run regtrace verify \
      --vector=timer_pwm_init_center_aligned_16khz \
      --target=stm32f1 \
      --against=~/dev/regtrace/golden/libopencm3/v0.8.0/stm32f1/timer_pwm_init_center_aligned_16khz.trace
```

`regtrace verify` exits 0 if the trace matches the golden, 1 if it differs — feeding `git bisect run` cleanly. Useful when a downstream user reports "my project's behavior changed after upgrading" — bisect reveals the responsible commit even when the original PR didn't realise it had a behavioural effect.

### 5. Per-peripheral share-or-split decision

A primary use case alongside validation and regression. Answers "should this peripheral's GD32 driver share the existing libopencm3 stm32/common header, or have its own driver?" with empirical evidence rather than intuition.

#### Workflow

For each peripheral being considered (timer, adc, dma, usart, i2c, etc.):

1. Write representative API call snippets — typical init sequence, channel/event configuration, IRQ enable, etc. ~10-50 calls per peripheral.
2. Compile twice: once against the **STM32 family** the GD chip's libopencm3 stub plans to share with (e.g., `stm32/f0` for GD32F1x0, `stm32/f1` for GD32F10x), once against the **vendor SPL**.
3. Capture register-write traces. Symbolise base addresses (`<TIM1_BASE>+...`) so they compare across families.
4. Diff. The diff outcome maps onto a four-level decision:

| diff result | architectural meaning | recommended action |
|---|---|---|
| **bit-identical** | the silicon really is the same at register level | **Share**. Add `gd32/<family>/<peri>.h` that just `#include`s the stm32 common header. No `#ifdef` carve-outs needed. |
| **identical structure, different reset values or default bits** | the peripheral is functionally compatible but vendor differs on initial state | **Share with reset shim**. Use the stm32 common driver, plus a small gd32-specific init helper that adjusts default bits before/after the shared init. |
| **identical mostly, divergent on one or two bit-fields** | mostly shared, vendor-specific carve-out | **Share via parameterised macro**. Refactor stm32/common to expose the bit-field as a configurable macro; gd32 and stm32 each provide their own value. |
| **diverges fundamentally** (different register layout, peripheral structure differs) | parallel design that happens to look similar | **Split**. Give it its own `gd32/<family>/<peri>.{h,c}`. No conditional growth in stm32/common/. |

#### Why this matters

The default approach today is "look at the TRM, decide intuitively, hope karlp agrees." That produces PRs that get bounced (#928, #1424) because the architectural choice was wrong or the maintainer disagrees with the call.

regtrace makes the decision deterministic and the evidence shippable. A PR that proposes sharing can include:

> "GD32F1x0 timer shares stm32/common/timer_common_all.h. Verified by regtrace v0.2: 47 representative API call patterns produce bit-identical register-write traces between libopencm3 stm32/f0 and GigaDevice SPL v3.4. Trace files in golden/. CI runs the comparison on every PR."

A PR that proposes splitting can include:

> "GD32F1x0 ADC has its own driver in gd32/f1x0/adc.c. Verified by regtrace v0.2: of 23 representative calls, 18 traces match stm32/f0 exactly but 5 diverge on the OVRMOD bit-field (F1x0's overrun-mode default is 1 vs F0's 0) and the watchdog-threshold register layout differs. Sharing would require an `#ifdef GD32_F1x0` carve-out in stm32/common/adc_common_v2.c covering ~40 lines; cleaner to keep separate. Diff evidence in regtrace-output/."

Both are concrete, falsifiable claims a maintainer can spot-check.

#### Decision criteria

The four-level diff outcome above is the primary signal. Secondary considerations:

- **Frequency of stm32/common changes** — if the shared file is touched often (active maintenance), every change forces re-validation against gd32 traces. High change rate weighs toward split.
- **Number of conditional carve-outs needed** — if sharing requires more than ~3-5 `#ifdef GD32_*` per file, split is cleaner. The "conditional density growth" risk discussed in the F1x0/F10x analysis.
- **Silicon errata divergence** — if vendor errata are frequent and don't affect both, split keeps the workaround localised.

regtrace's output answers the first two empirically. The third is human judgment, but trace evidence makes it less speculative.

#### Per-target metadata

```
targets/
├── stm32f0.toml      # peripheral_bases, register_names, address_quirks (bit-banding, etc.)
├── stm32f1.toml
├── stm32f4.toml
├── gd32f1x0.toml
├── gd32f10x.toml
└── gd32e23x.toml
```

These describe per-target peripheral memory layout used both to symbolise raw addresses in trace output and to filter "is this address a peripheral write?" during extraction. Maintained by hand from each chip's TRM; relatively stable since address maps rarely change within a chip family.

## Workflow

```
$ regtrace build vectors/                        # compile all snippets for all targets
$ regtrace trace build/timer_pwm_init.elf        # extract trace
$ regtrace compare timer_pwm_init                # compare across implementations
$ regtrace regression --baseline=golden/         # run full regression
```

## Comparison oracles

Per-target HAL implementations to compare:

| target          | HAL options                                                  |
|-----------------|--------------------------------------------------------------|
| STM32F0/F1/F4   | libopencm3 (current), libopencm3 (pre-refactor), Cube LL     |
| GD32F1x0/F130   | libopencm3 (under development), GigaDevice SPL `main` branch, GigaDevice SPL `patched` branch (community fixes) |
| GD32F10x/F103   | libopencm3 (not yet supported), GigaDevice SPL               |
| GD32E23x/E230   | libopencm3 (not yet supported), GigaDevice SPL               |

Initial focus: **GD32F1x0 libopencm3 vs SPL**, since that's the active porting work.

## Test-vector mining sources

In priority order:

1. **Hoverboard project's own usage** (`Src/setup.c`, `Src/it.c`). Bench-validated parameters; smallest set of vectors that lets us swap HALs in our project.
2. **Vendor SPL examples** (`CommunityGD32Cores/GD32Firmware/<family>/Examples/`). Per-peripheral, vendor-blessed.
3. **Real-world projects** using stock SPL: [`ZhuYanzhen1/miniFOC`](https://github.com/ZhuYanzhen1/miniFOC), [`the6p4c/peadee`](https://github.com/the6p4c/peadee), [`EFeru/hoverboard-sideboard-hack-GD`](https://github.com/EFeru/hoverboard-sideboard-hack-GD). Production usage patterns, including idioms beyond the vendor examples.
4. **Optional: combinatorial coverage from docstrings.** SPL `\arg` lists are sometimes stale or copy-paste; useful as hints, not as ground truth. Low priority.

## Initial peripheral scope

For the hoverboard libopencm3 port, the peripherals to validate first:

- **TIMER** (TIM1 advanced PWM — most critical for FOC + valley alignment)
- **ADC** (regular conversion, channel sequencing, DMA trigger)
- **DMA** (channel config, circulation, transfer count)
- **GPIO** (mode_set, output_options, alternate function)
- **USART** (init, baud, DMA mode)
- **I2C** (optional, for IMU)
- **IWDG** (independent watchdog config + reload)
- **NVIC** (IRQ enable + priority — core, not peripheral, but still register pokes)

## Caveats and known limitations

- **Optimization-induced reordering.** `-Os` may reorder independent stores. The comparator should sort by `(address, value)` for set-comparison modes; preserve order for sequence-comparison modes. Always pin compiler version and flags.
- **Inlined function-pointer stores.** Some HALs initialise function pointers (callbacks) via stores to RAM. These aren't peripheral writes; the trace extractor filters them out by address range.
- **Bit-banding (Cortex-M3 only).** ARM Cortex-M3 has alias regions that turn writes-to-bit-band-address into atomic single-bit RMW. The extractor must recognise alias addresses and resolve them to the underlying word. Other architectures don't have this; per-target plugin handles it.
- **RMW sequences.** `timer_interrupt_enable` reads CTL, ORs a mask, writes back. The extractor needs to capture load-store pairs and report the resulting write value, not just the raw store.
- **Volatile memory layout differences.** SPL and libopencm3 may layout the *same* C struct differently in DMA buffers (alignment, padding). Cross-comparison should distinguish "different padding" from "different register state".
- **Out-of-scope: dynamic state.** Timer counters running, ADC SAR converting, DMA transferring, IRQ priority interactions. `regtrace` is static analysis only.
- **Architecture-specific peripheral access modes.** Most architectures use memory-mapped peripheral access (covered cleanly). Some (RISC-V Zicsr CSRs, AVR I/O space, x86 IN/OUT) use special instructions. Each requires per-architecture extraction logic.

## Implementation language

Python with `capstone` (disassembly) + `pyelftools` (ELF parsing). Both are standard, MIT/BSD licensed, and well-maintained. Familiar enough for people doing embedded review.

Rust with `goblin` + `bad64` is a possible alternative if performance becomes an issue at scale. Not currently warranted.

## Licensing

`regtrace` itself: **MPL-2.0** (Mozilla Public License 2.0). See `LICENSE` in the project root.

Why MPL-2.0:
- File-level copyleft. Modifications to MPL'd files must be released under MPL. New files combined with MPL files can be under different licenses, including proprietary.
- Lighter touch than GPL — won't scare off CI integrations at chip vendors, PlatformIO, or libopencm3 upstream where corporate (A)GPL bans are common.
- Stronger than MIT/Apache-2.0 — improvements to regtrace's own code must come back, can't be sucked into a closed-source fork.
- Compatible with all the libraries we treat as binary oracles.

Per-file MPL-2.0 header for new source files:

```c
/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
```

Test vectors derived from vendor or third-party HALs:

- **GigaDevice SPL** is BSD-3-Clause; lifting parameter values into a snippet is fine. Don't copy SPL function bodies into the regtrace repo.
- **STMicro Cube LL** is "Permissive Binary License" (effectively BSD-equivalent for ST chips); same treatment.
- **libopencm3** is LGPL-3.0; we don't copy from it, we just call its API.

The trace extraction process compiles these libraries locally as binary oracles. We don't redistribute their source. License-clean against MPL-2.0.

`NOTICES` file at the project root reproduces the BSD copyright notices for any compiled artifacts (golden `.elf` blobs) we redistribute, satisfying the BSD-3-Clause clauses 1-2 and the corresponding clauses in Cube LL's permissive binary license.

## Naming gotcha: GD32F1x0 vs GD32F10x

Two confusingly-named GD32 families:

| family | chips | peripheral architecture | maps to STM32 family |
|---|---|---|---|
| **GD32F1x0** ("one-ex-zero") | F130, F150, F170, F190 | "modern" v2 — STM32F0-style (split-API GPIO MODER/PUPDR/AFRL/AFRH, newer USART/I2C) | stm32/f0 |
| **GD32F10x** ("one-zero-ex") | F101, F102, F103, F105, F107 | "legacy" v1 — STM32F1-style (combined GPIO CRL/CRH MODE+CNF) | stm32/f1 |

So **F130 ∈ GD32F1x0** and **F103 ∈ GD32F10x** — different SPL trees with different register layouts. This is what caused the `pinModeAF` divergence the hoverboard firmware hit between F130 and F103.

Both families are in scope eventually; F1x0 is the v0.1 focus because libopencm3 already has a partial stub for it.

## Roadmap

### v0.1 — GD32F1x0 (F130 family) bring-up + first share-or-split decision

Initial scope, picked for tightest fit with the existing libopencm3 stub. Doubles as a proof-of-concept for the per-peripheral share-or-split workflow.

**Scope:**
- Targets covered: `gd-spl/v3.0.0/gd32f1x0/`, `libopencm3/master/stm32f0/`. (`libopencm3/master/gd32f1x0/` is stub-only, no peripherals available yet — that's what v0.1 starts to inform.)
- Vectors: TIMER (TIM1 advanced PWM matching the hoverboard FOC config) + ADC (regular conversion, channel sequencing). ~5-10 total, mined from `Hoverboard-Firmware-Hack-Gen2.x-GD32/HoverBoardGigaDevice/Src/setup.c`.
- Comparison modes: `register_writes` only.
- Goldens: full `.elf + .trace` two-artifact form, Git LFS for `.elf`.
- Regression hook: manual via CLI. CI integration deferred to v0.3.

**Validation gates** (the agent should be able to run each command and confirm the expected output):

```bash
# Gate 1: bootstrap + dependencies
$ regtrace selftest
PASS — bootstrap valid

# Gate 2: a single vector compiles for both implementations
$ regtrace build vectors/timer/pwm_init_center_aligned_16khz.yaml
[ok] gd-spl/gd32f1x0 → build/v0.1/.../timer_pwm_init.elf (size: ~2-5kb)
[ok] libopencm3/stm32f0 → build/v0.1/.../timer_pwm_init.elf

# Gate 3: trace extraction produces non-empty output for both
$ regtrace trace build/v0.1/gd-spl/gd32f1x0/timer_pwm_init.elf
W4 <TIM1_BASE>+0x00 0x00000080
W4 <TIM1_BASE>+0x2C 0x000008CA
... (≥3 register writes expected for any non-trivial init)

# Gate 4: comparison produces a structured diff
$ regtrace compare timer_pwm_init_center_aligned_16khz \
      --against=gd-spl/gd32f1x0,libopencm3/stm32f0
match: 5/5 register writes identical    # OR: divergent: ...
exit 0

# Gate 5: goldens captured and checked in
$ ls golden/gd-spl/v3.0.0/gd32f1x0/
timer_pwm_init_center_aligned_16khz.elf
timer_pwm_init_center_aligned_16khz.trace
BUILD.txt

# Gate 6: per-peripheral share-or-split decisions documented
$ ls decisions/v0.1/
TIMER.md   # contains the four-level diff outcome + recommendation
ADC.md
```

**Done definition:** all six gates pass. A reasonable PR could be drafted from `decisions/v0.1/*.md` to libopencm3 for one of the peripherals.

### v0.2 — Peripheral coverage expansion

**Scope:**
- DMA + USART vectors mined from hoverboard + `ZhuYanzhen1/miniFOC`.
- `with_polling` comparison mode for ADC calibration.
- I2C and IWDG vectors.

**Validation gates:**
```bash
# Gate 1: vector count expanded
$ ls vectors/dma/*.yaml | wc -l       # ≥3
$ ls vectors/usart/*.yaml | wc -l     # ≥3
$ ls vectors/i2c/*.yaml | wc -l       # ≥2
$ ls vectors/iwdg/*.yaml | wc -l      # ≥1

# Gate 2: with_polling mode handles ADC calibration without spurious diffs
$ regtrace compare adc_calibration_enable --against=gd-spl/gd32f1x0,libopencm3/stm32f0
match: ... (polling structure recognised, body comparison passes)

# Gate 3: all v0.2 peripherals produce a decision document
$ ls decisions/v0.2/
DMA.md  USART.md  I2C.md  IWDG.md
```

**Done definition:** all gates pass + at least one share-or-split decision is published as a draft libopencm3 PR.

### v0.3 — Multi-target regression for libopencm3 PRs

**Scope:**
- Capture goldens at `libopencm3/v0.8.0/` and `libopencm3/master/` for `stm32/f0`, `stm32/f1`, `stm32/f4` (whichever are touched by `stm32/common/*` work).
- CI hook: any PR touching `stm32/common/*` runs regression vs the merge-base goldens.
- This is what makes a karlp-acceptable GD32 PR possible — "I added GD32F1x0 timer support via stm32/common shared code, here's proof STM32F0/F1/F4 traces are unchanged."

**Validation gates:**
```bash
# Gate 1: goldens captured for at least 2 libopencm3 versions × 3 targets
$ find golden/libopencm3/ -mindepth 3 -maxdepth 3 -type d
golden/libopencm3/v0.8.0/stm32f0
golden/libopencm3/v0.8.0/stm32f1
golden/libopencm3/v0.8.0/stm32f4
golden/libopencm3/master/stm32f0
... etc

# Gate 2: regression runs deterministically
$ regtrace regression --library=libopencm3 --against=v0.8.0
PASS — 47 vectors × 3 targets all match v0.8.0 goldens

# Gate 3: a synthetic regression is detected
$ git -C ~/dev/c/libopencm3 show abc123:lib/stm32/common/timer_common_all.c | \
      sed 's/0x80/0x90/' > /tmp/regression_test.c
... (apply patched file, rebuild, regtrace catches the diff)
exit 1 — diff at <TIM1_BASE>+0x00: expected 0x80, got 0x90

# Gate 4: CI workflow exists
$ cat .github/workflows/regtrace.yml
... (runs `regtrace regression` on PRs touching stm32/common)
```

### v0.4 — Cube LL oracle

**Scope:**
- Add Cube LL as a third oracle for STM32 sanity checks.
- Begin filing libopencm3 bug PRs for any divergences that turn out to be libopencm3 bugs (not Cube bugs or design intent).

**Validation gates:**
```bash
# Gate 1: cube-ll/<version>/<target>/ goldens exist
$ ls golden/cube-ll/v1.8.6/stm32f1/

# Gate 2: cross-oracle three-way diff works
$ regtrace compare timer_pwm_init_center_aligned_16khz \
      --against=cube-ll/stm32f1,libopencm3/stm32f1,gd-spl/gd32f10x
... (renders 3-way diff or unanimous match)

# Gate 3: at least one libopencm3 bug filed (or absence-of-bugs documented)
$ ls findings/v0.4/
```

### v0.5 — GD32F10x (F103 family) extension

**Scope:**
- Adds `gd-spl/<version>/gd32f10x/` and `libopencm3/<commit>/gd32f10x/` as new target oracles.
- libopencm3 GD32F10x port doesn't exist yet (PR #928 was rejected); this version uses regtrace as part of the work to write that port karlp-acceptably.
- STM32 families touched: `stm32/f1/*`, plus `stm32/common/*` consumers.

**Validation gates:**
```bash
# Gate 1: GD32F10x targets compile + trace
$ regtrace selftest --target=gd32f10x

# Gate 2: F103 share-or-split decisions documented per peripheral
$ ls decisions/v0.5/

# Gate 3: a draft libopencm3 PR exists for at least one peripheral
$ ls draft-prs/v0.5/
gd32f10x-timer.patch
gd32f10x-timer-PR-DESCRIPTION.md
```

### v0.6+ — Architecture extension

**Scope:**
- RISC-V backend for the trace extractor (capstone supports RV32/RV64).
- First target: `GD32VF103` (RISC-V variant from same vendor).
- The architecture seam is the disassembly + load-store recognition; everything else (snippet harness, comparison modes, golden file format) is reusable as-is.

**Validation gates:**
```bash
# Gate 1: RISC-V backend extracts traces
$ regtrace trace build/v0.6/.../riscv_snippet.elf
W4 <TIMx_BASE>+0x00 0x000000080  ... (non-empty)

# Gate 2: GD32VF103 produces a vector that compares against gd-spl
$ regtrace compare timer_pwm_init --target=gd32vf103
```

### v1.0

**Scope:**
- CI hook that gates libopencm3 PRs and the hoverboard firmware port.
- Architecture-portable backend (Cortex-M + RISC-V at minimum).
- Documentation on adding new HAL oracles, new target architectures, new chip families.

**Validation gates:**
```bash
# Gate 1: end-to-end CI exercise
$ gh workflow run regtrace.yml
... (passes)

# Gate 2: docs cover extension paths
$ ls docs/
adding-a-new-library.md
adding-a-new-target.md
adding-a-new-architecture.md
agent-runbook.md           # how an agent picks up the project from scratch

# Gate 3: a real upstream PR has landed using regtrace evidence
# (this is the meta-success criterion — if a libopencm3 PR cites regtrace
#  output and merges, the project has demonstrated value)
```

## Open questions

These are decisions an agent will encounter; recording them so they're answered deliberately rather than implicitly:

- ~~**C++ in snippets?**~~ **Decided: C only.** Revisit only if a future vector specifically can't be expressed in C without ugliness. Vendor SPL, libopencm3, Cube LL are all C; mangled C++ symbols in traces would also complicate the comparator.
- ~~**Auto-select comparison modes?**~~ **Decided: always declared in vector metadata.** Each YAML vector declares its `mode:` explicitly. Reasoning: only three modes, easy to choose between, declaration is one line, no silent-failure risk if the auto-detector misclassifies. Defer auto-detection to a future major version if it ever becomes painful.
- ~~**Trace minimisation mode?**~~ **Decided: yes, land in v0.2.** Each vector may declare optional `assert_only:` (whitelist) or `ignore:` (blacklist) address ranges to filter the trace before comparison. Example: `assert_only: [<TIM1_BASE>+0x00..0x44]` strips out unrelated RCU clock-enable writes that vary by HAL. Caveat documented in the YAML schema's docstring: too-narrow filtering could mask real bugs (e.g., a missing clock-enable). Use sparingly and prefer comparing the full trace where possible.
- ~~**Cube LL pinning strategy?**~~ **Decided: git submodule pinned by tag**, located at `oracles/cube/STM32CubeFx/`. Each Cube family submodule is opt-in (`git submodule update --init oracles/cube/STM32CubeF1` only when needed) so a default clone stays small. Reproducibility matters more than disk space — goldens are byte-deterministic only if the source they were captured against is bit-identically available. Upgrade path: file an issue → bump submodule → recapture goldens with explicit commit message.
- ~~**Decision-document format?**~~ **Decided: fixed markdown template** at `decisions/<version>/<peripheral>.md`, codified in `decisions/TEMPLATE.md`. Schema:
  - `Decision`: strict vocabulary — `share` / `share-with-shim` / `share-with-macro` / `split`.
  - `Confidence`: `empirical` (all vectors traced), `partial` (peripheral coverage incomplete), `inferred` (TRM-reading only, no traces — discouraged).
  - `Evidence`: links to specific trace files.
  - `Implementation sketch`: shape of the actual code change.
  - `Draft PR`: link to a `.patch` in the regtrace repo, or `TBD`. **Never auto-opened upstream.**
- ~~**What library-id to use for the hoverboard's `target.h` macro shims?**~~ **Decided: no separate library-id; expand the macros to raw SPL calls** in the YAML `body`. Vectors must NOT `#include "target.h"` — that would couple them to whatever the hoverboard's wrappers happen to compile to (including bugs in those wrappers, e.g., the broken `pinModeAF` macro on F103 silicon that we discovered while building this project). A vector for "F103 PWM init" describes the canonical SPL call sequence — `gpio_init(GPIOA, GPIO_MODE_AF_PP, GPIO_OSPEED_2MHZ, GPIO_PIN_8)` etc. — independent of any project-specific macro layer. Self-contained, reproducible across hoverboard revisions, and the regtrace traces become the source of truth for "what the silicon should look like" rather than echoing whatever wrapper is in fashion.
- ~~**Handling RAM-resident peripherals (DMA buffers, vector tables)?**~~ **Decided: filter to peripheral-MMIO ranges only.** Only writes to ranges declared as peripheral in `targets/<chip>.toml` enter the trace. RAM writes (DMA buffer init, vector-table relocation, static config struct population) are filtered out. Trade-off: a HAL that forgets to zero-init a DMA buffer when the other one does won't show as a diff. Comparing DMA buffer state or vector-table relocation is out of scope for regtrace — would need a separate validation tool. Documented in the YAML schema's caveats.
- ~~**CSR access on RISC-V?**~~ **Decided: defer to v0.6+ (RISC-V backend).** The Cortex-M v0.1-v0.5 path is unaffected — ARM uses memory-mapped peripherals exclusively, even for NVIC/SCB at `0xE000E000`. When the RISC-V backend lands, the disassembly plugin recognises `csrrw`/`csrrs`/`csrrc` instructions alongside memory-mapped stores, with the comparator treating both uniformly. Architecture-specific code lives in the disassembly plugin, doesn't leak into the comparator.
- ~~**Should regtrace try to run snippets in QEMU/Renode?**~~ **Decided: out of scope for v1.0.** Static trace comparison stays the focus — different problem from dynamic emulation. Anyone needing "would this configuration actually run?" should integrate Renode separately. Logged as a v2 idea, not on the v0.1-v1.0 roadmap.

## Reference implementations to follow

When building regtrace, structurally similar prior art:

**Binary / semantic diffing tools:**

- **BinDiff** (Google, open-sourced 2023) — https://github.com/google/bindiff
  Binary diffing originally built for malware analysis. Uses semantic basic-block comparison. Architecturally closest to what regtrace does — translate machine code into a comparable abstraction, then diff. Worth reading their basic-block matching algorithm even if we don't reuse it.

- **Diaphora** — https://github.com/joxeankoret/diaphora
  Open-source bindiff alternative, runs in IDA. Newer, more actively developed than BinDiff. Same problem domain.

- **angr** — https://github.com/angr/angr
  Symbolic execution framework for binaries. Overkill for our needs but useful reference for "extract semantic state from compiled code." Their VEX IR translation handles many architectures — worth understanding if we extend regtrace beyond Cortex-M + RISC-V.

**Golden-file regression testing patterns:**

- **`cargo-insta`** (Rust snapshot testing) — https://github.com/mitsuhiko/insta
  The cleanest implementation of "capture output, store as committed reference, refresh deliberately." Their UX for accepting/rejecting snapshot updates is well-considered; worth borrowing for `regtrace capture --update`.

- **esbuild snapshot tests** — https://github.com/evanw/esbuild
  Per-feature snapshot files committed to the repo (look under `internal/bundler/snapshots/` or run their test suite to regenerate). Output is human-readable for review.

- **prettier**'s test fixtures — https://github.com/prettier/prettier/tree/main/tests
  Same idiom — golden output checked into the repo, regenerated explicitly.

**ELF + disassembly libraries:**

- **pyelftools** — https://github.com/eliben/pyelftools
  Primary dependency for ELF parsing. Well-documented; example scripts in the repo.

- **capstone** — https://github.com/capstone-engine/capstone (Python bindings: https://www.capstone-engine.org/lang_python.html)
  Multi-architecture disassembler. Supports ARM/ARM64/RISC-V/MIPS/x86/PowerPC/Sparc out of the box.

- **goblin** (Rust alternative for ELF parsing) — https://github.com/m4b/goblin
  Reference if regtrace ever needs Rust performance.

**Cross-architecture compiled-test validation (less direct relevance, similar mindset):**

- **glibc test framework** — https://sourceware.org/glibc/
  Tests compile and run against the library; behavior is validated empirically. We're doing static rather than dynamic validation, but the "compile a small test, validate behavior" loop is similar. (The wiki page on testing has moved several times; start at the project home and follow links to "Contributing" → testing.)

**Per-peripheral validation precedents in embedded:**

- **CMSIS-SVD register definitions** — https://github.com/cmsis-svd/cmsis-svd
  Machine-readable register descriptions per chip family. Could potentially be used to populate the `targets/<family>.toml` peripheral-base maps automatically rather than maintaining them by hand.

- **probe-rs target definitions** — https://github.com/probe-rs/probe-rs/tree/master/probe-rs/targets
  How the Rust embedded ecosystem encodes per-chip metadata. Reference for what target-metadata fields are useful in practice.
