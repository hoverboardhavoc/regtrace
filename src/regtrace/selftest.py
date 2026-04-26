"""regtrace selftest — validate toolchain + sibling repos."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from . import bootstrap


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def check_tool(name: str, version_args: list[str]) -> CheckResult:
    path = shutil.which(name)
    if not path:
        return CheckResult(name, False, f"{name} not found in PATH")
    try:
        out = subprocess.check_output(
            [path] + version_args, stderr=subprocess.STDOUT, text=True
        )
        first = out.splitlines()[0] if out else "(no version output)"
        return CheckResult(name, True, f"{name}: {first}")
    except subprocess.CalledProcessError as e:
        return CheckResult(name, False, f"{name}: {e}")


def check_python_pkg(pkg: str) -> CheckResult:
    try:
        mod = __import__(pkg)
    except ImportError as e:
        return CheckResult(pkg, False, f"python package {pkg!r}: {e}")
    ver = getattr(mod, "__version__", "(unknown)")
    return CheckResult(pkg, True, f"python {pkg}: {ver}")


def run(do_bootstrap: bool = False) -> int:
    """Return exit code (0 on success)."""
    results: list[CheckResult] = []

    results.append(check_tool("arm-none-eabi-gcc", ["--version"]))
    results.append(check_tool("git", ["--version"]))
    results.append(check_tool("make", ["--version"]))
    results.append(check_tool("git-lfs", ["version"]))

    for pkg in ("unicorn", "capstone", "elftools", "yaml", "click"):
        results.append(check_python_pkg(pkg))

    repos = bootstrap.load()
    missing: list[bootstrap.RepoSpec] = []
    repo_results: list[CheckResult] = []
    for name, spec in repos.items():
        status, detail = bootstrap.repo_status(spec)
        if status == "missing":
            missing.append(spec)
            repo_results.append(CheckResult(name, False, f"repo {name}: missing at {spec.path}"))
        elif status == "mismatch":
            # Mismatch is a warning, not a failure.
            repo_results.append(CheckResult(name, True, f"repo {name}: {detail} [warning]"))
        else:
            repo_results.append(CheckResult(name, True, f"repo {name}: {detail}"))

    if missing and do_bootstrap:
        for spec in missing:
            print(f"[bootstrap] cloning {spec.name} from {spec.url} → {spec.path}")
            try:
                bootstrap.clone_or_fetch(spec)
            except subprocess.CalledProcessError as e:
                print(f"[bootstrap] failed to clone {spec.name}: {e}")
        # Re-check after bootstrap
        repo_results = []
        for name, spec in repos.items():
            status, detail = bootstrap.repo_status(spec)
            ok = status != "missing"
            repo_results.append(CheckResult(name, ok, f"repo {name}: {detail}"))

    results.extend(repo_results)

    failed = [r for r in results if not r.ok]
    for r in results:
        marker = "[ok]" if r.ok else "[FAIL]"
        print(f"{marker} {r.detail}")

    if failed:
        print(f"FAIL — {len(failed)} check(s) failed")
        if any("missing at" in r.detail for r in failed) and not do_bootstrap:
            print("hint: run `regtrace selftest --bootstrap` to clone missing sibling repos")
        return 1
    print("PASS — bootstrap valid")
    return 0
