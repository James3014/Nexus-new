"""Disposable copies of a task's repo_dir for runs of model code.

The reproduction script, the MicroVerifier and the verification commands run model-written code
with write access to their work dir. Run in repo_dir itself, anything they write (a rewritten
oracle, a planted pytest plugin, bytecode) stays there for the next verification of the same
directory. Each such run gets its own copy instead, deleted afterwards, so repo_dir only ever
receives the host's own writes (the applied patch, the repro script).
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess  # nosec B404 - fixed argv, no shell
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from nexus.core.contained_write import HOST_RUN_SUBTREES, PathContainmentError

__all__ = ["copy_repo_entries", "disposable_repo_copy"]


def _refuse_hard_links(entry: Path) -> None:
    """Raise when ``entry`` is or holds a regular file with another link (#3037 follow-up).

    Both copies below turn a hard link into a plain file with its content, so a hard link to a
    file outside repo_dir would hand that file to the model code run in the copy, whose output
    reaches a prompt. Symlinks are copied as links and not followed. ``.git`` and ``.venv`` are
    not walked: model code cannot write there (HOST_RUN_SUBTREES), and git and uv may hard-link
    their own files."""

    info = os.lstat(entry)
    if stat.S_ISREG(info.st_mode):
        if info.st_nlink != 1:
            raise PathContainmentError(f"file_has_other_links:{entry.name}")
        return
    if not stat.S_ISDIR(info.st_mode) or entry.name in HOST_RUN_SUBTREES:
        return
    for dirpath, dirnames, filenames in os.walk(entry):
        dirnames[:] = [name for name in dirnames if name not in HOST_RUN_SUBTREES]
        for name in filenames:
            child = os.path.join(dirpath, name)
            child_info = os.lstat(child)
            if stat.S_ISREG(child_info.st_mode) and child_info.st_nlink != 1:
                raise PathContainmentError(
                    f"file_has_other_links:{os.path.relpath(child, entry.parent)}"
                )


def copy_repo_entries(repo_dir: Path, scratch_dir: Path) -> None:
    """Copy every top-level entry of ``repo_dir`` into ``scratch_dir``, links kept as links.

    On macOS a directory is cloned with ``cp -cR`` (APFS clone); anything else, or a failed
    clone, uses ``shutil``. An entry that is or contains ``scratch_dir`` is skipped. A hard-linked
    regular file anywhere outside ``.git``/``.venv`` raises ``PathContainmentError`` before
    anything is copied."""

    repo_path = Path(repo_dir).resolve()
    scratch_path = Path(scratch_dir).resolve()
    entries = []
    for entry in repo_path.iterdir():
        entry_resolved = entry.resolve()
        if entry_resolved == scratch_path or scratch_path.is_relative_to(entry_resolved):
            continue
        if not entry.is_symlink():
            _refuse_hard_links(entry)
        entries.append(entry)
    for entry in entries:
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
