"""Paths a Task Card must never authorize (#1750)."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

_PROTECTED_TOP_DIRECTORIES = (".github", ".nexus-core")
_PROTECTED_NESTED_DIRECTORIES = (("docs", "governance"),)
_PROTECTED_ROOT_FILES = ("agents.md", "claude.md", "pyproject.toml", "uv.lock")
_GLOB_CHARS = ("*", "?", "[")
# Task Cards render each entry inside a Markdown bullet that is parsed back later, so
# anything beyond plain path characters (newlines, backticks, ...) could inject a
# second entry.
_SAFE_PATH = re.compile(r"[A-Za-z0-9._/@+-]+")


def protected_path_reason(path: str) -> str | None:
    """Return a short reason code when ``path`` may not appear in allowed_files.

    Matching is on normalized path components (``./``, ``//`` and ``a/./b`` collapse;
    a bare directory such as ``.github`` counts) and case-insensitive, because the
    canonical checkout lives on a case-insensitive macOS volume.
    """
    if any(char in path for char in _GLOB_CHARS):
        return "GLOB_NOT_ALLOWED"
    text = path.strip()
    # No backslashes either: ``\\AGENTS.md`` must not be reinterpreted later.
    if not _SAFE_PATH.fullmatch(text):
        return "UNSAFE_CHARACTERS"
    raw_parts = PurePosixPath(text).parts
    if text.startswith("/") or ".." in raw_parts:
        return "NOT_A_BOUNDED_RELATIVE_PATH"
    parts = tuple(part.lower() for part in raw_parts if part != ".")
    if not parts:
        return "AUTHORITY_DIRECTORY"  # the repository root covers everything
    if len(parts) == 1 and parts[0] in _PROTECTED_ROOT_FILES:
        return "AUTHORITY_ROOT_FILE"
    if parts[0] in _PROTECTED_TOP_DIRECTORIES:
        return "AUTHORITY_DIRECTORY"
    for prefix in _PROTECTED_NESTED_DIRECTORIES:
        # A directory entry covers everything below it, so a parent such as
        # ``docs`` would also cover ``docs/governance``.
        if parts[: len(prefix)] == prefix or prefix[: len(parts)] == parts:
            return "AUTHORITY_DIRECTORY"
    return None
