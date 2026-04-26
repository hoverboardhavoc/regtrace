"""regtrace capture: build + extract + write into golden/ with provenance."""

from __future__ import annotations

import shutil
from pathlib import Path

from .. import targets as targets_mod, vectors as vectors_mod
from ..paths import golden_dir
from ..trace.extractor import extract
from . import pipeline


def run_capture(
    library: str,
    library_rev: str | None,
    vectors_path: Path,
    update: bool,
    allow_dirty: bool,
) -> int:
    rev = library_rev or pipeline.auto_detect_rev(library)
    if rev.endswith("-dirty") and not allow_dirty:
        print(f"[error] auto-detected rev {rev!r} is dirty; pass --allow-dirty to override "
              f"(captured goldens will be excluded from regression baselines)")
        return 2

    vecs = vectors_mod.discover(vectors_path)
    if not vecs:
        print(f"[error] no vector YAML found under {vectors_path}")
        return 1

    rc = 0
    for vec in vecs:
        for slug, impl in vec.implementations.items():
            if impl.library != library:
                continue
            try:
                built = pipeline.build_one(vec, slug, rev=rev)
                tgt = targets_mod.load(built.target)
                trace = extract(built.elf_path, target=tgt, vector=vec)
                trace.header.vector_id = vec.vector_id
                trace.header.library = built.library
                trace.header.library_commit = built.rev
                trace.header.compiler = built.gcc_version
                trace.header.compile_flags = " ".join(built.compile_flags)

                gd = golden_dir(built.library, built.rev, built.target)
                gd.mkdir(parents=True, exist_ok=True)

                elf_dest = gd / f"{vec.vector_id}.elf"
                trace_dest = gd / f"{vec.vector_id}.trace"
                build_txt = gd / "BUILD.txt"

                if (elf_dest.exists() or trace_dest.exists()) and not update:
                    print(f"[skip] {elf_dest.name}: golden already exists; pass --update to overwrite")
                    rc = 1
                    continue

                shutil.copy2(built.elf_path, elf_dest)
                trace_dest.write_text(trace.render())
                build_txt.write_text(_render_build_txt(built))
                print(f"[capture] {trace_dest}")
                print(f"[capture] {elf_dest}")
            except Exception as e:
                print(f"[fail] {vec.vector_id} {slug}: {e}")
                rc = 1
    return rc


def _render_build_txt(built: pipeline.BuildResult) -> str:
    return (
        f"library:       {built.library}\n"
        f"rev:           {built.rev}\n"
        f"target:        {built.target}\n"
        f"compiler:      {built.gcc_version}\n"
        f"compile_flags: {' '.join(built.compile_flags)}\n"
    )
