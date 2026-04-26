"""HAL static-library builders.

Each library has a recipe for producing a `.a` to link snippets against.
The recipe lives in code (not a config file) because each HAL has different
build conventions; abstracting them prematurely would obscure rather than
clarify.

Currently implemented:
  - libopencm3 (calls its own Makefile, harvests the per-target .a)

Planned (v0.2+):
  - gd-spl (small per-family Makefile in regtrace driving the vendored sources)
  - cube-ll
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .. import bootstrap as bootstrap_mod
from .cache import CacheKey, gcc_version, lookup, store


# Map regtrace target id → libopencm3 target name + path-component for its built .a.
LIBOPENCM3_TARGET_MAP = {
    "stm32f0": ("stm32/f0", "opencm3_stm32f0"),
    "stm32f1": ("stm32/f1", "opencm3_stm32f1"),
    "stm32f4": ("stm32/f4", "opencm3_stm32f4"),
    # gd32f1x0 stub exists on libopencm3 master but has no peripherals yet at
    # v0.1; declared here for forward-compatibility.
    "gd32f1x0": ("gd32/f1x0", "opencm3_gd32f1x0"),
}


def build_libopencm3(target: str, rev: str, compile_flags: tuple[str, ...]) -> Path:
    """Build (or fetch from cache) libopencm3 for `target`. Returns path to lib*.a."""
    if target not in LIBOPENCM3_TARGET_MAP:
        raise ValueError(f"libopencm3 target {target!r} not in LIBOPENCM3_TARGET_MAP")
    key = CacheKey(
        library="libopencm3",
        rev=rev,
        target=target,
        gcc_version=gcc_version(),
        compile_flags=compile_flags,
    )
    cached = lookup(key)
    if cached is not None:
        return cached

    repos = bootstrap_mod.load()
    if "libopencm3" not in repos:
        raise RuntimeError("bootstrap.toml has no [repos.libopencm3] entry")
    repo = repos["libopencm3"]
    if not repo.path.exists():
        raise RuntimeError(
            f"libopencm3 not present at {repo.path}. "
            f"Run `regtrace selftest --bootstrap` to clone."
        )

    lopencm3_target, libstem = LIBOPENCM3_TARGET_MAP[target]
    print(f"[build] libopencm3 {target} ({lopencm3_target}) at {repo.path} (rev {rev})")
    subprocess.check_call(
        ["make", f"TARGETS={lopencm3_target}", "lib"],
        cwd=str(repo.path),
    )
    artifact = repo.path / "lib" / f"lib{libstem}.a"
    if not artifact.exists():
        raise RuntimeError(f"libopencm3 build did not produce {artifact}")
    return store(key, artifact)


def build_hal(library: str, target: str, rev: str, compile_flags: tuple[str, ...]) -> Path:
    """Dispatch to the per-library builder."""
    if library == "libopencm3":
        return build_libopencm3(target, rev, compile_flags)
    if library in {"gd-spl", "gd-spl-patched"}:
        raise NotImplementedError(
            f"{library} HAL build is planned for v0.2; only libopencm3 supported at v0.1"
        )
    raise NotImplementedError(f"library {library!r} has no builder")
