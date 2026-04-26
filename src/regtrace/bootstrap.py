"""bootstrap.toml loader and sibling-repo management."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from .paths import REPO_ROOT, resolve_workspace_var


@dataclass(frozen=True)
class RepoSpec:
    name: str
    url: str
    commit: str
    path: Path


def load(bootstrap_path: Path | None = None) -> dict[str, RepoSpec]:
    """Load bootstrap.toml and return {name: RepoSpec} with paths resolved."""
    bootstrap_path = bootstrap_path or REPO_ROOT / "bootstrap.toml"
    with open(bootstrap_path, "rb") as f:
        data = tomllib.load(f)
    repos: dict[str, RepoSpec] = {}
    for name, body in data.get("repos", {}).items():
        repos[name] = RepoSpec(
            name=name,
            url=body["url"],
            commit=body["commit"],
            path=Path(resolve_workspace_var(body["path"])).expanduser(),
        )
    return repos


def repo_status(spec: RepoSpec) -> tuple[str, str]:
    """Return (status, detail) for a sibling repo.

    status is one of: missing, ok, mismatch.
    """
    if not spec.path.exists() or not (spec.path / ".git").exists():
        return ("missing", str(spec.path))
    try:
        head = subprocess.check_output(
            ["git", "-C", str(spec.path), "rev-parse", "HEAD"],
            text=True,
        ).strip()
    except subprocess.CalledProcessError as e:
        return ("missing", f"{spec.path}: {e}")
    pinned = spec.commit
    if head.startswith(pinned) or pinned == head:
        return ("ok", head)
    if pinned in {"main", "master", "HEAD"}:
        # Branch-name pin — can't strictly verify, just report HEAD.
        return ("ok", f"{head} (pin: {pinned}, branch-name pin)")
    return ("mismatch", f"have {head}, pinned {pinned}")


def clone_or_fetch(spec: RepoSpec) -> None:
    """Clone the repo if missing; checkout the pinned commit."""
    if not spec.path.exists():
        spec.path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.check_call(["git", "clone", spec.url, str(spec.path)])
    if spec.commit not in {"main", "master", "HEAD"}:
        subprocess.check_call(
            ["git", "-C", str(spec.path), "checkout", spec.commit]
        )
