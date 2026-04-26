# Adding a new HAL library

regtrace supports a new HAL by:
1. Adding the repo to `bootstrap.toml`.
2. Mapping the library-id to that repo in `LIBRARY_TO_REPO`.
3. Writing a per-library builder in `src/regtrace/build/hal.py`.
4. Wiring snippet-build include paths and chip defines in `src/regtrace/build/pipeline.py`.
5. Vendoring `build_assets/<library>/<target>/` (startup.S + link.ld; CMSIS stubs if needed).

This is what `cube-ll` (v0.4) and `gd-spl-patched` (planned) follow. Concrete reference: `git log --oneline --all --grep='Cube LL'`.

## 1. bootstrap.toml entry

```toml
[repos.MyHALRepo]
url    = "https://github.com/example/my-hal"
commit = "main"   # or a specific tag/sha
path   = "${REGTRACE_WORKSPACE}/MyHALRepo"
```

Branch-name pins (`main`, `master`) are accepted but make goldens irreproducible across time. Pin a tag or commit before you capture goldens.

## 2. LIBRARY_TO_REPO mapping (src/regtrace/build/hal.py)

```python
LIBRARY_TO_REPO = {
    ...
    "my-hal": "MyHALRepo",
}
```

The library-id is what the vector YAML uses (`my-hal/<target>`). It can differ from the repo name when one repo hosts multiple library-ids (`gd-spl` and `gd-spl-patched` both come from `GD32Firmware`, on different branches).

## 3. Per-library builder

Two patterns exist:

**(a) HAL ships its own Makefile** (libopencm3 model). Call `make TARGETS=<target> lib`, harvest the resulting `lib<name>.a`. See `build_libopencm3()`.

**(b) HAL is just a tree of .c files** (gd-spl, cube-ll). Compile each source file, archive into a `.a`. Define a `<NAME>_LAYOUT` dict per target with `src_dir`, `include_dirs`, `chip_define`, optional `build_assets_includes` (for vendored CMSIS stubs the HAL expects but doesn't ship). See `build_gd_spl()` and `build_cube_ll()`.

Cache key is `CacheKey(library, rev, target, gcc_version, compile_flags)` — any change rebuilds. The cache lives at `~/.cache/regtrace/libs/<library>/<rev>/<target>/lib<name>.a`.

## 4. Pipeline wiring

In `pipeline.build_one()`, add an `elif library == "my-hal":` branch that resolves the worktree, appends `include_dirs`, and adds `extra_defines`. If the HAL needs special compile flags (a specific `-std=`, warning relaxation), add them to `LIBRARY_EXTRA_FLAGS`.

## 5. build_assets

Each `(library, target)` pair needs:
- `startup.S` — minimum: vector table (or RISC-V equivalent), reset handler that sets SP, branches to `regtrace_test`, halts on a sentinel (`bkpt`/`ebreak`).
- `link.ld` — minimum: define memory regions (FLASH, SRAM), `_estack`, place `.text`/`.data`/`.bss`. Real-target memory sizes are irrelevant; Unicorn maps whatever you declare.

Often you can copy from a sibling `(library, target)` if the architecture matches (`build_assets/cube-ll/stm32f1/` is identical to `libopencm3/stm32f1/` since both are Cortex-M3).

## 6. Validation

Add a vector with a `<library>/<target>` impl, run `regtrace compare <vector>`, and confirm the trace looks plausible. The `--all-pairs` flag is useful for comparing the new HAL against existing oracles for the same target.
