"""Path resolution and workspace conventions.

All path-related helpers live here so the layout pinned in SPEC.md is
expressed once and used everywhere.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_WORKSPACE = Path.home() / "dev" / "c"
REPO_ROOT = Path(__file__).resolve().parents[2]


def workspace_root() -> Path:
    """Return ${REGTRACE_WORKSPACE}, defaulting to ~/dev/c/."""
    raw = os.environ.get("REGTRACE_WORKSPACE")
    return Path(raw).expanduser() if raw else DEFAULT_WORKSPACE


def cache_root() -> Path:
    """HAL static-lib cache root."""
    return Path.home() / ".cache" / "regtrace"


def resolve_workspace_var(value: str) -> str:
    """Replace ${REGTRACE_WORKSPACE} in a TOML-loaded string.

    bootstrap.toml uses this interpolation; tomli does not handle it natively,
    so we apply a custom resolver pass after load.
    """
    return value.replace("${REGTRACE_WORKSPACE}", str(workspace_root()))


def vector_id(yaml_path: Path) -> str:
    """Return the canonical vector identifier from a vector YAML path.

    `<peripheral>_<name>` where peripheral is the parent directory under
    vectors/ and name is the YAML basename.
    """
    return f"{yaml_path.parent.name}_{yaml_path.stem}"


def build_dir(library: str, rev: str, target: str) -> Path:
    """build/<library>/<rev>/<target>/."""
    return REPO_ROOT / "build" / library / rev / target


def golden_dir(library: str, rev: str, target: str) -> Path:
    """golden/<library>/<rev>/<target>/."""
    return REPO_ROOT / "golden" / library / rev / target


def lib_cache_path(library: str, rev: str, target: str) -> Path:
    """~/.cache/regtrace/libs/<library>/<rev>/<target>/lib<library>.a."""
    return cache_root() / "libs" / library / rev / target / f"lib{library}.a"


def build_assets_dir(library: str, target: str) -> Path:
    """build_assets/<library>/<target>/."""
    return REPO_ROOT / "build_assets" / library / target


def targets_dir() -> Path:
    return REPO_ROOT / "targets"


def vectors_dir() -> Path:
    return REPO_ROOT / "vectors"
