"""HAL static-library build cache.

Per-library, per-rev, per-target builds of the HAL library are cached at
~/.cache/regtrace/libs/<library>/<rev>/<target>/lib<library>.a. The cache
key includes the gcc version and compile flags via a sidecar manifest;
mismatched manifests trigger a rebuild.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..paths import cache_root, lib_cache_path


@dataclass(frozen=True)
class CacheKey:
    library: str
    rev: str
    target: str
    gcc_version: str
    compile_flags: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "library": self.library,
            "rev": self.rev,
            "target": self.target,
            "gcc_version": self.gcc_version,
            "compile_flags": list(self.compile_flags),
        }


def manifest_path(key: CacheKey) -> Path:
    return lib_cache_path(key.library, key.rev, key.target).with_suffix(".manifest.json")


def lookup(key: CacheKey) -> Path | None:
    """Return the cached lib path if present and the manifest matches; else None."""
    lib = lib_cache_path(key.library, key.rev, key.target)
    mf = manifest_path(key)
    if not lib.exists() or not mf.exists():
        return None
    try:
        stored = json.loads(mf.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if stored != key.to_dict():
        return None
    return lib


def store(key: CacheKey, lib_artifact: Path) -> Path:
    """Copy lib_artifact into the cache for `key`. Returns the cached path."""
    dest = lib_cache_path(key.library, key.rev, key.target)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(lib_artifact, dest)
    manifest_path(key).write_text(json.dumps(key.to_dict(), indent=2, sort_keys=True))
    return dest


def gcc_version(gcc: str = "arm-none-eabi-gcc") -> str:
    """Return the first line of `gcc --version`."""
    out = subprocess.check_output([gcc, "--version"], text=True, stderr=subprocess.STDOUT)
    return out.splitlines()[0].strip()


def clean_libs() -> None:
    """Evict the entire ~/.cache/regtrace/libs/ tree."""
    libs_root = cache_root() / "libs"
    if libs_root.exists():
        shutil.rmtree(libs_root)
        print(f"[clean] removed {libs_root}")
    else:
        print(f"[clean] nothing to do — {libs_root} does not exist")
