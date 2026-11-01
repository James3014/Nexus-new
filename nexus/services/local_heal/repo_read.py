"""Host-side reads of source files under a local_heal ``repo_dir`` (#3018).

Sandboxed model code may have run in ``repo_dir`` before the host reads it (repro script,
verifier, micro verify), so an entry there can be a symlink or hard link to a host file, a FIFO,
or a very large file. Localization, patch synthesis, the repo map and the orchestrator put what
they read into model prompts, so they read through ``read_repo_text``: a regular single-link file
inside ``repo_dir``, walked without following links (``nexus.core.contained_write``), at most
``REPO_READ_MAX_BYTES``. Anything else reads as ``None`` and the caller treats it as unreadable.
"""

from __future__ import annotations

from pathlib import Path

from nexus.core.contained_write import contained_relative_path, read_text_in_root

__all__ = ["REPO_READ_MAX_BYTES", "read_repo_text"]

# Far above any source file the pipeline edits; a link to /dev/zero or a huge log is not read whole.
REPO_READ_MAX_BYTES = 4 * 1024 * 1024


def read_repo_text(
    repo_dir: Path | str, path: Path | str, *, max_bytes: int = REPO_READ_MAX_BYTES
) -> str | None:
    """Text (UTF-8, undecodable bytes replaced) of ``path`` under ``repo_dir``, or ``None``.

    ``path`` is relative to ``repo_dir`` or absolute. ``None`` when it is missing, lies outside
    ``repo_dir`` (also through a symlink that resolves outside), is a hard link, FIFO or other
    special file, or is larger than ``max_bytes``. A symlink that resolves inside ``repo_dir``
    reads its target; a link swapped in after that check is refused, not followed."""

    try:
        relative = contained_relative_path(repo_dir, path)
        return read_text_in_root(repo_dir, relative, max_bytes=max_bytes)
    except (OSError, ValueError):
        return None
