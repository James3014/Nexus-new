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

Readers use :func:`find_run_receipt`, which searches where the writer would write
first and then the other location (so receipts written before the variable was set are
still found), and accepts only a receipt whose embedded task id matches.
:func:`copy_run_receipts_to_state_root` copies receipts from an old root into the
state root once (idempotent, never deletes, never follows symlinks).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

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


# Field in each receipt kind that holds the task id it was written for.
_TASK_ID_FIELD = {
    CANONICAL_RUNTIME_SUFFIX: "task_id",
    UNIFIED_RUNTIME_POINTER_SUFFIX: "unified_runtime_task_id",
}


def _search_dirs(root: Path | str | None) -> list[Path]:
    """Writer's directory first, then the other location.

    For a root the writer rebases (a per-deploy root) that is the state root, then the
    root itself (receipts from before the variable was set).  For an isolated root
    (canary, test) the writer keeps ``<root>/.nexus/reports/run``, so that is searched
    first and a same-name receipt in the shared state root never shadows it.
    """
    dirs: list[Path] = []
    state_root = configured_state_root()
    if root is not None:
        dirs.append(run_reports_dir(root))
        dirs.append(Path(root) / RUN_REPORTS_RELATIVE)
    if state_root is not None:
        dirs.append(state_root / RUN_REPORTS_RELATIVE)
    unique: list[Path] = []
    for directory in dirs:
        if directory not in unique:
            unique.append(directory)
    return unique


def _read_receipt(path: Path) -> dict[str, Any] | None:
    if not _regular_file(path):
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _root_receipt_hash(payload: Mapping[str, Any]) -> str:
    root_receipt = payload.get("root_receipt")
    if not isinstance(root_receipt, Mapping):
        return ""
    return str(root_receipt.get("root_receipt_hash") or "")


def find_run_receipt(
    task_id: str,
    root: Path | str | None = None,
    *,
    suffix: str = CANONICAL_RUNTIME_SUFFIX,
    expected_root_receipt_hash: str | None = None,
    allow_unbound: bool = False,
) -> Path | None:
    """Return the receipt file written for exactly ``task_id``, or None.

    Search order mirrors the writer (see ``_search_dirs``); with no ``root`` only the
    state root is searched.  The task id is reduced to one safe file-name segment, so
    it can never leave those directories, and symlinks are not followed.

    A file is accepted only if it parses as a JSON object whose embedded task id
    (``task_id``; ``unified_runtime_task_id`` for pointers) equals ``task_id``
    exactly.  File names can collide (``a b``/``a_b``, ``task:1``/``task/1``, ids
    cut at 120 characters), so a mismatching file is skipped and the search goes on.

    The shared state root keeps one file per task id across deploys: a later run of
    the same task id overwrites it, and an earlier run's receipt stays there until
    then.  Every lookup is therefore bound to one run by default:
    ``expected_root_receipt_hash`` (``root_receipt.root_receipt_hash`` from the
    ``nexus_task_run`` response being confirmed) must equal the receipt's, so a stale
    receipt from another run of the same task id is rejected.  **Without it the lookup
    refuses and returns None** (None rather than an exception, so a forgotten binding
    can only produce "not found", never a confirmation).  An empty hash never matches.

    ``allow_unbound=True`` permits a lookup with no hash (a hash that is given is still
    enforced).  It exists only for discovery and
    witness tooling that lists what is on disk (#2689 follow-up).  **Completion
    confirmers must never use it**: an unbound lookup can return an earlier run's
    receipt for the same task id.
    """
    if suffix not in _RECEIPT_SUFFIXES:
        raise ValueError(f"run_receipt_suffix_invalid:{suffix}")
    if expected_root_receipt_hash is None and not allow_unbound:
        return None  # unbound lookup refused; see docstring
    name = f"{safe_receipt_name(task_id)}{suffix}"
    field = _TASK_ID_FIELD[suffix]
    for directory in _search_dirs(root):
        candidate = directory / name
        if candidate.parent != directory or os.sep in name:
            continue
        payload = _read_receipt(candidate)
        if payload is None or payload.get(field) != task_id:
            continue
        if expected_root_receipt_hash is not None and (
            not expected_root_receipt_hash
            or _root_receipt_hash(payload) != expected_root_receipt_hash
        ):
            continue
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
        temporary = target_dir / f".{entry.name}.copy-{uuid.uuid4().hex}"
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
