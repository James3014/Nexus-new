"""Paths a Task Card must never authorize (#1750)."""

from __future__ import annotations

from pathlib import PurePosixPath

_PROTECTED_TOP_DIRECTORIES = (".github", ".nexus-core")
_PROTECTED_NESTED_DIRECTORIES = (("docs", "governance"),)
_PROTECTED_ROOT_FILES = ("agents.md", "claude.md", "pyproject.toml", "uv.lock")
_GLOB_CHARS = ("*", "?", "[")


def protected_path_reason(path: str) -> str | None:
    """Return a short reason code when ``path`` may not appear in allowed_files.

    Matching is on normalized path components (``./``, ``//`` and ``a/./b`` collapse;
    a bare directory such as ``.github`` counts) and case-insensitive, because the
    canonical checkout lives on a case-insensitive macOS volume.
    """
    if any(char in path for char in _GLOB_CHARS):
        return "GLOB_NOT_ALLOWED"
    parts = tuple(
        part.lower() for part in PurePosixPath(path.strip().replace("\\", "/")).parts if part != "."
    )
    if not parts:
        return None
    if len(parts) == 1 and parts[0] in _PROTECTED_ROOT_FILES:
        return "AUTHORITY_ROOT_FILE"
    if parts[0] in _PROTECTED_TOP_DIRECTORIES:
        return "AUTHORITY_DIRECTORY"
    for prefix in _PROTECTED_NESTED_DIRECTORIES:
        if parts[: len(prefix)] == prefix:
            return "AUTHORITY_DIRECTORY"
    return None
