"""HAL static-library builders.

Each library has a recipe for producing a `.a` to link snippets against.
The recipe lives in code (not a config file) because each HAL has different
build conventions; abstracting them prematurely would obscure rather than
clarify.

Currently implemented:
  - libopencm3 (calls its own Makefile, harvests the per-target .a)
  - gd-spl    (compiles the GD32Firmware SPL .c files into a .a)

Planned (v0.2+):
  - cube-ll
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .. import bootstrap as bootstrap_mod
from .cache import CacheKey, gcc_version, lookup, store


# Library-id → bootstrap.toml repo name. Same string when they match (libopencm3),
# different when one repo hosts multiple library-ids (GD32Firmware → gd-spl + gd-spl-patched).
LIBRARY_TO_REPO = {
    "libopencm3":     "libopencm3",
    "gd-spl":         "GD32Firmware",
    "gd-spl-patched": "GD32Firmware",
}


# Map regtrace target id → libopencm3 target name + path-component for its built .a.
LIBOPENCM3_TARGET_MAP = {
    "stm32f0": ("stm32/f0", "opencm3_stm32f0"),
    "stm32f1": ("stm32/f1", "opencm3_stm32f1"),
    "stm32f4": ("stm32/f4", "opencm3_stm32f4"),
    # gd32f1x0 stub exists on libopencm3 master but has no peripherals yet at
    # v0.1; declared here for forward-compatibility.
    "gd32f1x0": ("gd32/f1x0", "opencm3_gd32f1x0"),
}


# Per-(library, target) source-tree layout for the vendor SPL. The SPL doesn't
# ship a Makefile; we compile every gd32f1x0_*.c into a .a.
GD_SPL_LAYOUT = {
    "gd32f1x0": {
        "src_dir":     "GD32F1x0/GD32F1x0_standard_peripheral/Source",
        "include_dirs": [
            "GD32F1x0/GD32F1x0_standard_peripheral/Include",
            "GD32F1x0/CMSIS/GD/GD32F1x0/Include",
            "GD32F1x0/CMSIS",
        ],
        # GD ships core_cm3.h but expects CMSIS-Core 4.x to provide
        # core_cmInstr.h / core_cmFunc.h alongside. We vendor minimal stubs.
        "build_assets_includes": ["cmsis-stubs"],
        "chip_define": "GD32F130_150",
    },
}


def _resolve_repo(library: str):
    repo_name = LIBRARY_TO_REPO.get(library)
    if repo_name is None:
        raise RuntimeError(f"library {library!r} has no LIBRARY_TO_REPO mapping")
    repos = bootstrap_mod.load()
    if repo_name not in repos:
        raise RuntimeError(f"bootstrap.toml has no [repos.{repo_name}] entry")
    spec = repos[repo_name]
    if not spec.path.exists():
        raise RuntimeError(
            f"{repo_name} not present at {spec.path}. "
            f"Run `regtrace selftest --bootstrap` to clone."
        )
    return spec


def _git_describe(repo_path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo_path), "describe", "--tags", "--always", "--dirty"],
        text=True,
    ).strip()


def worktree_for(library: str, rev: str) -> Path:
    """Return a path containing `library`'s tree checked out at `rev`.

    If `rev` matches `git describe` on the default checkout, returns that
    path. Otherwise creates (or reuses) a git worktree under
    ~/.cache/regtrace/worktrees/<library>/<sanitised-rev>/.
    """
    spec = _resolve_repo(library)
    primary_rev = _git_describe(spec.path)
    if rev == primary_rev:
        return spec.path

    from ..paths import cache_root
    safe_rev = rev.replace("/", "_")
    worktree_path = cache_root() / "worktrees" / library / safe_rev
    if worktree_path.exists() and (worktree_path / ".git").exists():
        # Existing worktree — verify it's at the right rev. A "-dirty"
        # suffix means the user (or a synthetic-regression test) has edits in
        # the worktree; preserve those by keeping the worktree as long as the
        # underlying commit still resolves to the requested rev.
        cur = _git_describe(worktree_path)
        if cur == rev or cur == f"{rev}-dirty":
            return worktree_path
        # Stale; remove and recreate.
        subprocess.check_call(
            ["git", "-C", str(spec.path), "worktree", "remove", "--force", str(worktree_path)],
            stderr=subprocess.DEVNULL,
        )

    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        ["git", "-C", str(spec.path), "worktree", "add", "--force", "--detach",
         str(worktree_path), rev],
    )
    return worktree_path


def _python_shim_dir() -> Path:
    """Return a dir containing a `python` wrapper around `python3`.

    Older libopencm3 revs (≤ v0.8.x) ship scripts with `#!/usr/bin/env python`
    shebangs, but modern macOS only ships `python3`. We prepend this dir to
    PATH for libopencm3 makes so builds against historical revs work.
    """
    from ..paths import cache_root
    d = cache_root() / "shim" / "bin"
    d.mkdir(parents=True, exist_ok=True)
    shim = d / "python"
    if not shim.exists():
        py3 = subprocess.check_output(["which", "python3"], text=True).strip()
        shim.write_text(f"#!/bin/sh\nexec {py3} \"$@\"\n")
        shim.chmod(0o755)
    return d


def build_libopencm3(target: str, rev: str, compile_flags: tuple[str, ...]) -> Path:
    """Build (or fetch from cache) libopencm3 for `target`. Returns path to lib*.a."""
    if target not in LIBOPENCM3_TARGET_MAP:
        raise ValueError(f"libopencm3 target {target!r} not in LIBOPENCM3_TARGET_MAP")
    key = CacheKey(
        library="libopencm3", rev=rev, target=target,
        gcc_version=gcc_version(), compile_flags=compile_flags,
    )
    cached = lookup(key)
    if cached is not None:
        return cached

    tree = worktree_for("libopencm3", rev)
    lopencm3_target, libstem = LIBOPENCM3_TARGET_MAP[target]
    print(f"[build] libopencm3 {target} ({lopencm3_target}) at {tree} (rev {rev})")
    import os as _os
    env = dict(_os.environ)
    env["PATH"] = f"{_python_shim_dir()}:{env.get('PATH', '')}"
    subprocess.check_call(
        ["make", f"TARGETS={lopencm3_target}", "lib"],
        cwd=str(tree), env=env,
    )
    artifact = tree / "lib" / f"lib{libstem}.a"
    if not artifact.exists():
        raise RuntimeError(f"libopencm3 build did not produce {artifact}")
    return store(key, artifact)


def build_gd_spl(target: str, rev: str, compile_flags: tuple[str, ...],
                 patched: bool = False) -> Path:
    """Build (or fetch from cache) the GD32 vendor SPL for `target`.

    Compiles every gd32<family>_*.c in the SPL Source/ directory into a single
    static archive. The SPL has no Makefile of its own; this is the recipe.
    """
    layout = GD_SPL_LAYOUT.get(target)
    if layout is None:
        raise ValueError(f"gd-spl target {target!r} not in GD_SPL_LAYOUT")
    library = "gd-spl-patched" if patched else "gd-spl"

    key = CacheKey(
        library=library, rev=rev, target=target,
        gcc_version=gcc_version(), compile_flags=compile_flags,
    )
    cached = lookup(key)
    if cached is not None:
        return cached

    tree = worktree_for(library, rev)
    src_dir = tree / layout["src_dir"]
    if not src_dir.is_dir():
        raise RuntimeError(f"SPL source directory not found: {src_dir}")
    from ..paths import build_assets_dir
    assets_root = build_assets_dir(library, target)
    include_dirs = [str(assets_root / d) for d in layout.get("build_assets_includes", [])]
    include_dirs += [str(tree / d) for d in layout["include_dirs"]]
    chip_define = layout["chip_define"]

    sources = sorted(src_dir.glob(f"{target}_*.c"))
    if not sources:
        raise RuntimeError(f"no SPL .c sources matched {src_dir}/{target}_*.c")

    objs: list[Path] = []
    failed: list[tuple[Path, str]] = []
    print(f"[build] gd-spl {target} ({len(sources)} source files) at {tree} (rev {rev})")
    with tempfile.TemporaryDirectory(prefix="regtrace-gd-spl-") as tmpdir:
        tmp = Path(tmpdir)
        for src in sources:
            obj = tmp / f"{src.stem}.o"
            cmd = [
                "arm-none-eabi-gcc",
                *compile_flags,
                f"-D{chip_define}",
                "-DUSE_STDPERIPH_DRIVER",
                *(f"-I{d}" for d in include_dirs),
                "-c", str(src),
                "-o", str(obj),
            ]
            try:
                subprocess.check_output(cmd, stderr=subprocess.STDOUT)
                objs.append(obj)
            except subprocess.CalledProcessError as e:
                failed.append((src, e.output.decode("utf-8", "replace")))

        if not objs:
            details = "\n".join(f"  {s.name}: {err.splitlines()[0] if err else 'no output'}"
                                for s, err in failed[:5])
            raise RuntimeError(f"gd-spl build failed for all sources:\n{details}")
        if failed:
            print(f"[build] {len(failed)}/{len(sources)} SPL sources failed to compile "
                  f"(typically depend on USB or features outside our scope); excluded from archive")

        archive = tmp / f"lib{library.replace('-', '_')}.a"
        ar_cmd = ["arm-none-eabi-ar", "rcs", str(archive)] + [str(o) for o in objs]
        subprocess.check_call(ar_cmd)
        return store(key, archive)


def build_hal(library: str, target: str, rev: str, compile_flags: tuple[str, ...]) -> Path:
    """Dispatch to the per-library builder."""
    if library == "libopencm3":
        return build_libopencm3(target, rev, compile_flags)
    if library == "gd-spl":
        return build_gd_spl(target, rev, compile_flags, patched=False)
    if library == "gd-spl-patched":
        return build_gd_spl(target, rev, compile_flags, patched=True)
    raise NotImplementedError(f"library {library!r} has no builder")


def auto_detect_repo_rev(library: str) -> str:
    """Resolve the rev for `library` via git describe on its underlying repo."""
    repo = _resolve_repo(library)
    out = subprocess.check_output(
        ["git", "-C", str(repo.path), "describe", "--tags", "--always", "--dirty"],
        text=True,
    ).strip()
    return out
