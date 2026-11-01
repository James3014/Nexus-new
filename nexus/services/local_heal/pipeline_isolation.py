"""Workspace isolation used before the World C pipeline may mutate files."""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Sequence
from pathlib import Path

from nexus.core.contained_write import (
    PathContainmentError,
    copy_file_in_root,
    copy_tree_in_root,
)
from nexus.services.local_heal.armor_artifact_storage import (
    ENV_ARMOR_ALLOW_EPHEMERAL,
    is_ephemeral_path,
    make_isolated_workspace,
)

_IGNORED_NAMES = {
    ".git",
    ".nexus",
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
}


class WorldCCopyRefused(ValueError):
    """The World C copy met a link or special file it must not read; no workspace is made."""


def _ephemeral_source_allowed() -> bool:
    return str(os.environ.get(ENV_ARMOR_ALLOW_EPHEMERAL, "") or "").strip() in {
        "1",
        "true",
        "TRUE",
        "yes",
    }


def prepare_world_c_workspace(
    source_root: str | Path,
    task_id: str,
    *,
    target_file: str = "",
    repro_script: str = "",
    verifier_files: Sequence[str] = (),
) -> Path:
    """Copy the source snapshot before HealOrchestrator patch/verify execution.

    A synthetic source (no ``.git``/``pyproject.toml``) copies only the named files, so the
    files the authoritative verifier command reads (``verifier_files``) are copied as well.

    Model code may have run in ``source_root`` before, so the copy never reads through a link
    (#3037 follow-up): a symlink at a named file or on the way to it, a hard link and a FIFO or
    other special file anywhere in the copy raise ``WorldCCopyRefused`` and no workspace is
    returned. A symlink in a full-tree copy is kept only if it resolves inside the copy.
    """
    source = Path(source_root).expanduser().resolve()
    if not source.is_dir():
        raise ValueError("world_c_source_root_missing")
    if is_ephemeral_path(source) and not _ephemeral_source_allowed():
        raise ValueError(f"World C source root must not be ephemeral OS temp: {source}")
    safe_task = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(task_id)).strip("-") or "unknown"
    target = make_isolated_workspace(prefix=f"world-c-{safe_task[:32]}-")

    try:
        if (source / ".git").exists() or (source / "pyproject.toml").exists():
            copy_tree_in_root(source, target, ignore_names=_IGNORED_NAMES)
        else:
            # Synthetic workspaces must not expand an arbitrary parent such as /tmp.
            for relative in (target_file, repro_script, *verifier_files):
                if not relative:
                    continue
                relative_path = Path(relative)
                if relative_path.is_absolute() or ".." in relative_path.parts:
                    continue
                copy_file_in_root(source, os.path.normpath(relative_path), target)
    except PathContainmentError as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise WorldCCopyRefused(f"world_c_copy_refused:{exc}") from exc
    return target.resolve()


def verifier_input_files(
    source_root: str | Path, verifier_command: Sequence[str]
) -> tuple[str, ...]:
    """Relative regular files under ``source_root`` named by the verifier command arguments.

    ``("python", "repro.py")`` yields ``("repro.py",)``. The interpreter (argv[0]), options,
    absolute paths, parent traversal, symlinks and paths that resolve outside the source root
    are skipped, so only files the verifier reads from the task snapshot are returned. So are
    hard links (``st_nlink != 1``): one can name a file outside the source root (#3037 follow-up).
    """
    source = Path(source_root).expanduser().resolve()
    found: list[str] = []
    for token in tuple(verifier_command or ())[1:]:
        text = str(token or "").strip()
        if not text or text.startswith("-"):
            continue
        relative = Path(text)
        if relative.is_absolute() or ".." in relative.parts:
            continue
        candidate = source / relative
        try:
            if candidate.is_symlink() or not candidate.is_file():
                continue
            if candidate.lstat().st_nlink != 1:
                continue
            if not candidate.resolve().is_relative_to(source):
                continue
        except OSError:  # e.g. ENAMETOOLONG for a long ``-c`` body: not a file (#2967)
            continue
        if text not in found:
            found.append(text)
    return tuple(found)
