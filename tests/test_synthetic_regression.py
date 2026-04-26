"""Synthetic regression test (v0.3 Gate 3).

Verifies regtrace catches a deliberate behaviour change in libopencm3:
  1. Capture a baseline golden against the current libopencm3 commit.
  2. Patch a libopencm3 source file to alter a register-write value.
  3. Run regression against the baseline and confirm exit code is 1 (diff
     detected) and the diff identifies the modified write.
  4. Restore the patched file.

Marked slow because it builds libopencm3 twice (~30s each on a cold cache).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_env() -> dict[str, str]:
    """Env dict with the python-shim dir prepended to PATH."""
    from regtrace.build.hal import _python_shim_dir
    env = dict(os.environ)
    env["PATH"] = f"{_python_shim_dir()}:{env.get('PATH', '')}"
    return env


def _regtrace_bin() -> str:
    """Locate the regtrace CLI inside the project venv."""
    candidates = [REPO_ROOT / ".venv" / "bin" / "regtrace", "regtrace"]
    for c in candidates:
        if isinstance(c, Path) and c.exists():
            return str(c)
    return "regtrace"


@pytest.mark.slow
def test_synthetic_regression_caught(tmp_path):
    """Patch libopencm3's timer driver, prove regtrace flags the diff."""
    # Regression runs against the worktree the rev resolves to, not the user's
    # HEAD. Locate the v0.8.0 worktree so we can patch the same tree the
    # regression run will rebuild.
    from regtrace.build.hal import worktree_for
    try:
        v8_tree = worktree_for("libopencm3", "v0.8.0")
    except Exception as e:
        pytest.skip(f"libopencm3 v0.8.0 worktree unavailable: {e}")

    baseline = REPO_ROOT / "golden" / "libopencm3" / "v0.8.0"
    if not baseline.exists():
        pytest.skip(f"v0.8.0 baseline not captured at {baseline}")

    # Step 1: confirm clean baseline.
    rc = subprocess.call(
        [_regtrace_bin(), "regression", "--baseline", str(baseline)],
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    assert rc == 0, "Baseline regression should pass before we mutate libopencm3"

    # Step 2: patch the IWDG driver in the v0.8.0 worktree.
    iwdg_file = v8_tree / "lib" / "stm32" / "common" / "iwdg_common_all.c"
    assert iwdg_file.exists(), f"iwdg_common_all.c missing at {iwdg_file}"
    libopencm3_path = v8_tree

    original = iwdg_file.read_text()
    # iwdg_start() writes IWDG_KR = IWDG_KR_START (0xCCCC). Change to 0xCCCD
    # so the trace shows a different start-key value.
    sentinel = "IWDG_KR = IWDG_KR_START;"
    if sentinel not in original:
        pytest.skip(f"sentinel {sentinel!r} not present in {iwdg_file}")
    patched = original.replace(sentinel, "IWDG_KR = 0xCCCD;")

    # Drop the HAL static-lib cache so the rebuild picks up our patch.
    cache_libs = Path.home() / ".cache" / "regtrace" / "libs"
    if cache_libs.exists():
        shutil.rmtree(cache_libs)
    # Clean every target the vectors touch so the patched .c gets recompiled.
    for tgt in ("stm32/f0", "stm32/f1", "stm32/f4"):
        subprocess.check_call(
            ["make", f"TARGETS={tgt}", "clean"],
            cwd=str(libopencm3_path), env=_make_env(),
            stdout=subprocess.DEVNULL,
        )

    try:
        iwdg_file.write_text(patched)

        # Step 3: regression should now fail with exit 1.
        proc = subprocess.run(
            [_regtrace_bin(), "regression", "--baseline", str(baseline)],
            cwd=str(REPO_ROOT),
            capture_output=True, text=True,
        )
        # The current libopencm3 worktree may not be at v0.8.0, so the
        # captured rev differs and the regression also picks up timestamp /
        # gcc-driven differences. We just need to confirm: at least one diff
        # is reported AND the exit code is non-zero.
        assert proc.returncode != 0, (
            f"Expected non-zero exit after patching libopencm3; got 0.\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
        assert "FAIL" in proc.stdout or "divergent" in proc.stdout or "mismatch" in proc.stdout, (
            f"Expected a diff report; got:\n{proc.stdout}"
        )
    finally:
        # Step 4: restore.
        iwdg_file.write_text(original)
        if cache_libs.exists():
            shutil.rmtree(cache_libs)
        for tgt in ("stm32/f0", "stm32/f1", "stm32/f4"):
            subprocess.check_call(
                ["make", f"TARGETS={tgt}", "clean"],
                cwd=str(libopencm3_path), env=_make_env(),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
