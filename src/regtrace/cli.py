"""regtrace command-line entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from . import __version__, selftest as selftest_mod


@click.group()
@click.version_option(__version__, prog_name="regtrace")
def main() -> None:
    """regtrace — register-trace comparison for HAL validation."""


@main.command("selftest")
@click.option("--bootstrap", "do_bootstrap", is_flag=True,
              help="Clone any missing sibling repos at the commits pinned in bootstrap.toml.")
@click.option("--target", default=None,
              help="Restrict checks to a specific target family (e.g., gd32f10x). v0.5+.")
def selftest_cmd(do_bootstrap: bool, target: str | None) -> None:
    """Validate the toolchain + sibling repositories."""
    if target is not None:
        click.echo(f"[note] --target filtering is a v0.5+ feature; ignored at v0.1.")
    sys.exit(selftest_mod.run(do_bootstrap=do_bootstrap))


@main.command("build")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def build_cmd(path: Path) -> None:
    """Compile vector snippets to ELF. PATH is a vector YAML or a directory of them."""
    from .build.pipeline import build_path
    sys.exit(build_path(path))


@main.command("trace")
@click.argument("elf", type=click.Path(exists=True, path_type=Path))
@click.option("--debug", is_flag=True, help="Print per-instruction execution log.")
def trace_cmd(elf: Path, debug: bool) -> None:
    """Extract a register-write trace from a snippet ELF."""
    from .trace.extractor import extract_trace_to_stdout
    sys.exit(extract_trace_to_stdout(elf, debug=debug))


@main.command("compare")
@click.argument("vector")
@click.option("--against", default=None,
              help="Comma-separated list of <library>/<target> impl slugs to compare. "
                   "Overrides default_compare from the vector YAML.")
@click.option("--against-trace", "against_trace", default=None, type=click.Path(path_type=Path),
              help="Path to a golden .trace file. Re-extracts the vector and diffs against this file. "
                   "Mutually exclusive with --against.")
@click.option("--all-pairs", "all_pairs", is_flag=True,
              help="Render the full N×N comparison matrix across all declared implementations.")
@click.option("--target", default=None, help="Override the target when used with --against-trace.")
def compare_cmd(vector: str, against: str | None, against_trace: Path | None,
                all_pairs: bool, target: str | None) -> None:
    """Compare implementations of VECTOR (or diff against a golden trace)."""
    if against and against_trace:
        raise click.UsageError("--against and --against-trace are mutually exclusive")
    from .compare.engine import run_compare
    sys.exit(run_compare(
        vector=vector,
        against=against,
        against_trace=against_trace,
        all_pairs=all_pairs,
        target=target,
    ))


@main.command("capture")
@click.option("--library", required=True, help="Library id, e.g. libopencm3 or gd-spl.")
@click.option("--library-rev", "library_rev", default=None,
              help="Verbatim rev (tag/branch/commit). If omitted, uses git describe --tags --always --dirty.")
@click.option("--vectors", "vectors_path", required=True, type=click.Path(exists=True, path_type=Path),
              help="Vector YAML or directory.")
@click.option("--update", is_flag=True, help="Allow overwriting existing goldens.")
@click.option("--allow-dirty", "allow_dirty", is_flag=True,
              help="Permit goldens labelled with a -dirty rev (excluded from regression baselines).")
def capture_cmd(library: str, library_rev: str | None, vectors_path: Path,
                update: bool, allow_dirty: bool) -> None:
    """Capture goldens (build + extract + provenance)."""
    from .build.capture import run_capture
    sys.exit(run_capture(
        library=library,
        library_rev=library_rev,
        vectors_path=vectors_path,
        update=update,
        allow_dirty=allow_dirty,
    ))


@main.command("re-extract")
@click.argument("elf", type=click.Path(exists=True, path_type=Path))
def re_extract_cmd(elf: Path) -> None:
    """Re-extract a .trace from an existing golden .elf (no rebuild)."""
    from .trace.extractor import re_extract
    sys.exit(re_extract(elf))


@main.command("regression")
@click.option("--baseline", required=True, type=click.Path(exists=True, path_type=Path),
              help="Path to a golden tree (e.g. golden/libopencm3/v0.8.0/) to diff against.")
def regression_cmd(baseline: Path) -> None:
    """Diff freshly-built traces against a stored golden tree."""
    from .compare.regression import run_regression
    sys.exit(run_regression(baseline=baseline))


@main.command("clean")
@click.option("--libs", "do_libs", is_flag=True, help="Evict ~/.cache/regtrace/libs/.")
def clean_cmd(do_libs: bool) -> None:
    """Clean cached artifacts."""
    from .build.cache import clean_libs
    if do_libs:
        clean_libs()
    else:
        click.echo("nothing to do — pass --libs to evict the HAL static-lib cache")
