"""Where canonical run receipts live, and how to find them again (#2689).

The canonical task seam writes ``<root>/.nexus/reports/run/<task>.canonical_runtime.json``
(the archived legacy repair pipeline also wrote ``<task>.unified_runtime_pointer.json``
there; it has no production caller and is not moved, but the reader finds it).  On
the live Gateway ``<root>`` is the per-deploy checkout, so every deploy left the
receipts behind and a confirmer looking for a past task found nothing.

This module reuses ``nexus.core.state_root`` (#2688) rather than a second variable:
when ``NEXUS_STATE_ROOT`` is set and ``<root>`` is a per-deploy root, the directory is
``$NEXUS_STATE_ROOT/.nexus/reports/run`` (the state root is the directory that
*contains* ``.nexus``, as for every other #2688 store).  File names and layout are
unchanged.  Unset, or for any isolated root (tests, canaries), the path is exactly the
old one.

Readers use :func:`find_run_receipt`, which looks in the state root first and then in
the given root, so receipts written before the variable was set are still found.
:func:`copy_run_receipts_to_state_root` copies receipts from an old root into the
state root once (idempotent, never deletes, never follows symlinks).
"""

from __future__ import annotations

import os
import re
import shutil
import stat
from pathlib import Path

from nexus.core.state_root import configured_state_root, rebase_state_path

RUN_REPORTS_RELATIVE = Path(".nexus") / "reports" / "run"
CANONICAL_RUNTIME_SUFFIX = ".canonical_runtime.json"
UNIFIED_RUNTIME_POINTER_SUFFIX = ".unified_runtime_pointer.json"
_RECEIPT_SUFFIXES = (CANONICAL_RUNTIME_SUFFIX, UNIFIED_RUNTIME_POINTER_SUFFIX)
_UNSAFE_NAME_CHARS = re.compile(r"[^a-zA-Z0-9_.-]+")


def safe_receipt_name(task_id: str) -> str:
    """File-name stem for a task id: one path segment, never empty."""
    return _UNSAFE_NAME_CHARS.sub("_", str(task_id or ""))[:120] or "task"


def run_reports_dir(root: Path | str) -> Path:
    """Directory the run receipts for ``root`` are written to.

    ``<root>/.nexus/reports/run`` unless ``NEXUS_STATE_ROOT`` moves ``root``.
    """
    return Path(rebase_state_path(Path(root) / RUN_REPORTS_RELATIVE))


def run_receipt_path(
    root: Path | str, task_id: str, suffix: str = CANONICAL_RUNTIME_SUFFIX
) -> Path:
    """Write path of one task's run receipt (state root when configured)."""
    if suffix not in _RECEIPT_SUFFIXES:
        raise ValueError(f"run_receipt_suffix_invalid:{suffix}")
    return run_reports_dir(root) / f"{safe_receipt_name(task_id)}{suffix}"


def _regular_file(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode)


def _search_dirs(root: Path | str | None) -> list[Path]:
    dirs: list[Path] = []
    state_root = configured_state_root()
    if state_root is not None:
        dirs.append(state_root / RUN_REPORTS_RELATIVE)
    if root is not None:
        dirs.append(Path(root) / RUN_REPORTS_RELATIVE)
    unique: list[Path] = []
    for directory in dirs:
        if directory not in unique:
            unique.append(directory)
    return unique


def find_run_receipt(
    task_id: str,
    root: Path | str | None = None,
    *,
    suffix: str = CANONICAL_RUNTIME_SUFFIX,
) -> Path | None:
    """Return the receipt file for ``task_id``, or None.

    Looks in ``$NEXUS_STATE_ROOT/.nexus/reports/run`` first (when configured), then
    in ``<root>/.nexus/reports/run``.  The task id is reduced to one safe file-name
    segment, so it can never leave those directories; symlinks are not followed.
    """
    if suffix not in _RECEIPT_SUFFIXES:
        raise ValueError(f"run_receipt_suffix_invalid:{suffix}")
    name = f"{safe_receipt_name(task_id)}{suffix}"
    for directory in _search_dirs(root):
        candidate = directory / name
        if candidate.parent != directory or os.sep in name:
            continue
        if _regular_file(candidate):
            return candidate
    return None


def copy_run_receipts_to_state_root(source_root: Path | str) -> list[Path]:
    """Copy ``<source_root>/.nexus/reports/run`` receipts into the state root once.

    Only regular receipt files at the top level are copied; symlinks, directories and
    other names are skipped, existing destination files are never overwritten, and
    nothing is deleted.  Returns the files created.  No-op when ``NEXUS_STATE_ROOT``
    is unset or the source already is the state root.
    """
    state_root = configured_state_root()
    if state_root is None:
        return []
    source_dir = Path(source_root) / RUN_REPORTS_RELATIVE
    target_dir = state_root / RUN_REPORTS_RELATIVE
    try:
        if source_dir.resolve() == target_dir.resolve():
            return []
        source_info = source_dir.lstat()
    except OSError:
        return []
    if not stat.S_ISDIR(source_info.st_mode):
        return []
    created: list[Path] = []
    for entry in sorted(os.scandir(source_dir), key=lambda item: item.name):
        if not entry.name.endswith(_RECEIPT_SUFFIXES):
            continue
        if not entry.is_file(follow_symlinks=False):
            continue
        destination = target_dir / entry.name
        if destination.exists() or destination.is_symlink():
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        temporary = target_dir / f".{entry.name}.copy-{os.getpid()}"
        try:
            shutil.copyfile(entry.path, temporary, follow_symlinks=False)
            try:
                os.link(temporary, destination)  # fails if another copier won the race
            except FileExistsError:
                continue
            created.append(destination)
        finally:
            temporary.unlink(missing_ok=True)
    return created
