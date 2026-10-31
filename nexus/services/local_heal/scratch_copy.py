"""Disposable copies of a task's repo_dir for runs of model code.

The reproduction script, the MicroVerifier and the verification commands run model-written code
with write access to their work dir. Run in repo_dir itself, anything they write (a rewritten
oracle, a planted pytest plugin, bytecode) stays there for the next verification of the same
directory. Each such run gets its own copy instead, deleted afterwards, so repo_dir only ever
receives the host's own writes (the applied patch, the repro script).
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404 - fixed argv, no shell
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

__all__ = ["copy_repo_entries", "disposable_repo_copy"]


def copy_repo_entries(repo_dir: Path, scratch_dir: Path) -> None:
    """Copy every top-level entry of ``repo_dir`` into ``scratch_dir``, links kept as links.

    On macOS a directory is cloned with ``cp -cR`` (APFS clone); anything else, or a failed
    clone, uses ``shutil``. An entry that is or contains ``scratch_dir`` is skipped."""

    repo_path = Path(repo_dir).resolve()
    scratch_path = Path(scratch_dir).resolve()
    for entry in repo_path.iterdir():
        entry_resolved = entry.resolve()
        if entry_resolved == scratch_path or scratch_path.is_relative_to(entry_resolved):
            continue
        target = scratch_path / entry.name
        copied = False
        if sys.platform == "darwin" and not entry.is_symlink():
            try:
                subprocess.run(  # noqa: S603,S607 - fixed argv
                    ["cp", "-cR", str(entry), str(target)],
                    capture_output=True,
                    check=True,
                )
                copied = True
            except Exception:
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target, ignore_errors=True)
                elif target.exists() or target.is_symlink():
                    target.unlink(missing_ok=True)
        if not copied:
            if entry.is_symlink():
                shutil.copy2(entry, target, follow_symlinks=False)
            elif entry.is_dir():
                shutil.copytree(entry, target, symlinks=True)
            else:
                shutil.copy2(entry, target, follow_symlinks=False)


@contextmanager
def disposable_repo_copy(repo_dir: Path | str, *, prefix: str) -> Iterator[Path]:
    """Yield a fresh copy of ``repo_dir``, made next to it and always deleted.

    Next to ``repo_dir`` so the copy has the same ancestors: tools that look upward for their
    configuration (pytest's rootdir and ini) find what they found for ``repo_dir``. Raises when
    the copy cannot be made; callers record that as a failed run, never a pass."""

    repo_path = Path(repo_dir).resolve()
    scratch_dir = Path(tempfile.mkdtemp(prefix=prefix, dir=str(repo_path.parent))).resolve()
    try:
        copy_repo_entries(repo_path, scratch_dir)
        yield scratch_dir
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
