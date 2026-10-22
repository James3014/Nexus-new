"""Pick a codeintel lookup target from the task's own files (#2721).

On the Gateway worker path the codeintel executor needs a ``target_symbol`` and
``search_paths``; callers rarely supply them, so codeintel refused every task
(``TARGET_SYMBOL_REQUIRED``).  This ranks the symbols defined in the task's
existing allowed ``.py`` files against the task text with BM25 and proposes the
best match.  Deterministic, no model call; the result is still re-validated by
``_codeintel_lookup_context`` before the executor sees it.

Each file is opened component by component with ``O_NOFOLLOW`` relative to the
worktree directory, so the check and the read are one step (no symlink swap in
between), and the work is bounded so it cannot stall dispatch.

Directory scopes (#2721, #2786).  An allowed entry ending in exactly one ``/``
(``pkg/``) is expanded into the ``.py`` files under that directory:

* the walk is breadth-first over sorted names, so it is deterministic; each
  directory is opened component by component with ``O_NOFOLLOW`` relative to the
  worktree, and symlinked directories or files met during the walk are skipped;
* hidden names (``.*``), ``__pycache__`` and test code are never entered or read
  (names compared case-insensitively, since APFS is case-insensitive).
  Test code is a directory named ``tests``, ``test`` or ``testing`` and a file
  named ``test_*.py``, ``*_test.py`` or ``conftest.py``; a directory entry that
  itself names such a directory is ignored.  Tests are not the lookup target,
  and hidden tests must never be read even when present;
* the walk stops at ``MAX_WALK_FILES`` candidate files and ``MAX_WALK_DIRS``
  directories (visited plus queued, so the queue never exceeds it either), skips a
  directory with more than ``MAX_DIR_ENTRIES`` entries, and skips a file whose
  size (from ``fstat``, before reading) would take the total past
  ``MAX_WALK_BYTES``; the per-file limits are unchanged;
* a regular file with more than one hard link is skipped: a hard link can pull a
  file from outside the worktree in without any symlink.  Files checked out by git
  have one link, so this is conservative and costs nothing in practice.

For such a scope ``search_paths`` lists the file defining the chosen symbol first,
then the files of the next best-scoring (score > 0) symbols, at most
``MAX_SEARCH_PATHS`` files: ``_codeintel_lookup_context`` only accepts 1-4
existing ``.py`` files, not directories.  A scope made only of files keeps the
original behaviour exactly.
"""

from __future__ import annotations

import ast
import os
import re
import stat
from collections import deque
from collections.abc import Hashable, Iterator
from pathlib import Path, PurePosixPath
from typing import Any

from nexus.services.bm25_retrieval import BM25Index

MAX_SEARCH_PATHS = 4
MAX_CANDIDATE_PATHS = 16
MAX_FILE_BYTES = 1024 * 1024
MAX_SYMBOLS = 2000
MAX_TASK_CHARS = 4000
MAX_SYMBOL_LENGTH = 128
MAX_WALK_FILES = 200
MAX_WALK_DIRS = 400
MAX_DIR_ENTRIES = 4096
MAX_WALK_BYTES = 16 * 1024 * 1024
_TEST_DIRS = frozenset({"tests", "test", "testing"})
_SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_SPLIT = re.compile(r"[._]+|(?<=[a-z0-9])(?=[A-Z])")


def _symbol_text(symbol: str) -> str:
    """Symbol name split into words (snake_case, dotted, camelCase)."""
    return f"{symbol} " + " ".join(part for part in _SPLIT.split(symbol) if part)


def derive_codeintel_lookup(
    task_text: Any, allowed_files: Any, workspace_root: Any
) -> dict[str, Any]:
    """``{"target_symbol", "search_paths"}`` for the best-matching symbol, or ``{}``."""
    if not isinstance(task_text, str) or not task_text or not workspace_root:
        return {}
    if not isinstance(allowed_files, (list, tuple)):
        return {}
    try:
        root = Path(str(workspace_root)).resolve(strict=True)
        return _derive(task_text[:MAX_TASK_CHARS], allowed_files, root)
    except (OSError, RuntimeError, ValueError, SyntaxError, MemoryError):
        return {}  # a missing target is a codeintel refusal, never a dispatch failure


def _relative_parts(rel: Any) -> tuple[str, ...] | None:
    if not isinstance(rel, str) or not rel.endswith(".py") or "\\" in rel:
        return None
    path = PurePosixPath(rel)
    parts = path.parts
    if not parts or path.is_absolute() or any(part in ("", ".", "..") for part in parts):
        return None
    return parts


def _skipped_dir(name: str) -> bool:
    """Case-insensitive: on APFS ``Tests/`` is the same directory as ``tests/``."""
    folded = name.casefold()
    return folded.startswith(".") or folded == "__pycache__" or folded in _TEST_DIRS


def _skipped_file(name: str) -> bool:
    folded = name.casefold()
    return (
        folded.startswith(".")
        or not name.endswith(".py")
        or folded.startswith("test_")
        or folded in {"test.py", "tests.py"}
        or folded.endswith("_test.py")
        or folded.endswith("_tests.py")
        or folded == "conftest.py"
    )


def _dir_parts(rel: Any) -> tuple[str, ...] | None:
    """``pkg/sub/`` -> ``("pkg", "sub")``: one trailing ``/``, normalized, not skipped."""
    if not isinstance(rel, str) or not rel.endswith("/") or rel.endswith("//") or "\\" in rel:
        return None
    stripped = rel[:-1]
    path = PurePosixPath(stripped)
    parts = path.parts
    if (
        not parts
        or path.is_absolute()
        or "/".join(parts) != stripped
        or any(part in ("", ".", "..") or _skipped_dir(part) for part in parts)
    ):
        return None
    return parts


def _list_inside(root: Path, parts: tuple[str, ...]) -> tuple[list[str], list[str]] | None:
    """Sorted ``(subdirs, py_files)`` of ``root/parts`` without following any symlink."""
    fds: list[int] = []
    try:
        fds.append(os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
        for part in parts:
            fds.append(os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fds[-1]))
        dirs: list[str] = []
        files: list[str] = []
        with os.scandir(fds[-1]) as entries:
            for count, entry in enumerate(entries):
                if count >= MAX_DIR_ENTRIES:
                    return None
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if not _skipped_dir(entry.name):
                        dirs.append(entry.name)
                elif entry.is_file(follow_symlinks=False) and not _skipped_file(entry.name):
                    files.append(entry.name)
        return sorted(dirs), sorted(files)
    except OSError:
        return None
    finally:
        for fd in reversed(fds):
            os.close(fd)


def _walk(root: Path, start: tuple[str, ...], budget: dict[str, int]) -> Iterator[tuple[str, ...]]:
    """``.py`` files under ``root/start``, breadth-first; ``budget["dirs"]`` is shared."""
    queue: deque[tuple[str, ...]] = deque([start])
    while queue and budget["dirs"] < MAX_WALK_DIRS:
        current = queue.popleft()
        budget["dirs"] += 1
        listing = _list_inside(root, current)
        if listing is None:
            continue
        dirs, files = listing
        for name in files:
            yield (*current, name)
        for name in dirs:
            if budget["dirs"] + len(queue) >= MAX_WALK_DIRS:
                break  # the queue itself stays within the directory cap
            queue.append((*current, name))


def _read_inside(
    root: Path,
    parts: tuple[str, ...],
    *,
    max_bytes: int = MAX_FILE_BYTES,
    single_link: bool = False,
) -> bytes | None:
    """Bytes of ``root/parts`` opened without following any symlink, or ``None``.

    ``max_bytes`` is checked against ``fstat`` before reading; ``single_link``
    refuses a file with more than one hard link (directory scopes only).
    """
    fds: list[int] = []
    try:
        fds.append(os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
        for part in parts[:-1]:
            fds.append(os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fds[-1]))
        fd = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fds[-1]
        )
        fds.append(fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            return None
        if single_link and info.st_nlink > 1:
            return None
        return os.read(fd, max_bytes + 1)[: max_bytes + 1]
    except OSError:
        return None
    finally:
        for fd in reversed(fds):
            os.close(fd)


def _module_name(parts: tuple[str, ...]) -> str:
    names = [*parts[:-1], parts[-1][: -len(".py")]]
    if names[-1] == "__init__":
        names = names[:-1]
    return ".".join(names)


def _qualified(*names: str) -> str:
    return ".".join(name for name in names if name)


def _symbols(module: str, source: bytes, limit: int) -> list[str]:
    """Top-level functions/classes and class methods, as the skeleton provider names them
    (a root ``__init__.py`` has an empty module, so its symbols carry no prefix)."""
    tree = ast.parse(source)
    found: list[str] = []
    for node in tree.body:
        if len(found) >= limit:
            break
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.append(_qualified(module, node.name))
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if len(found) >= limit:
                    break
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found.append(_qualified(module, node.name, child.name))
    return found


def _derive(
    task_text: str, allowed_files: list[Any] | tuple[Any, ...], root: Path
) -> dict[str, Any]:
    entries = list(
        dict.fromkeys(item for item in allowed_files[:MAX_CANDIDATE_PATHS] if isinstance(item, str))
    )
    if any(_dir_parts(rel) is not None for rel in entries):
        return _derive_scoped(task_text, entries, root)
    return _derive_files(task_text, allowed_files, root)


def _derive_scoped(task_text: str, entries: list[str], root: Path) -> dict[str, Any]:
    """Files and expanded directories; ``search_paths`` = the chosen symbol's file first."""
    candidates: dict[tuple[str, ...], None] = {}
    budget = {"dirs": 0}
    # Explicit files first, so a large directory cannot use up the file budget
    # before a file the task names itself; directories get what is left.
    for rel in entries:
        file_parts = _relative_parts(rel)
        if file_parts is not None and len(candidates) < MAX_WALK_FILES:
            candidates.setdefault(file_parts)
    for rel in entries:
        if len(candidates) >= MAX_WALK_FILES:
            break
        dir_parts = _dir_parts(rel)
        if dir_parts is None:
            continue
        for parts in _walk(root, dir_parts, budget):
            if len(candidates) >= MAX_WALK_FILES:
                break
            candidates.setdefault(parts)
    docs: list[tuple[int, str]] = []
    owners: dict[Hashable, tuple[str, str]] = {}
    read_bytes = 0
    for parts in candidates:
        if len(docs) >= MAX_SYMBOLS:
            break
        limit = min(MAX_FILE_BYTES, MAX_WALK_BYTES - read_bytes)
        source = _read_inside(root, parts, max_bytes=limit, single_link=True)
        if source is None or len(source) > limit:
            continue  # too big for what is left of the total: skipped before reading
        read_bytes += len(source)
        try:
            symbols = _symbols(_module_name(parts), source, MAX_SYMBOLS - len(docs))
        except (SyntaxError, ValueError, RecursionError):
            continue  # one unparsable file must not drop the others
        for symbol in symbols:
            if len(docs) >= MAX_SYMBOLS:
                break
            if len(symbol) <= MAX_SYMBOL_LENGTH and _SYMBOL.fullmatch(symbol):
                owners[len(docs)] = (symbol, "/".join(parts))
                docs.append((len(docs), _symbol_text(symbol)))
    if not docs:
        return {}
    ranked = [(index, score) for index, score in BM25Index(docs).rank(task_text) if score > 0]
    if not ranked:
        return {}
    search_paths: list[str] = []
    for index, _score in ranked:
        rel = owners[index][1]
        if rel not in search_paths:
            search_paths.append(rel)
            if len(search_paths) >= MAX_SEARCH_PATHS:
                break
    return {"target_symbol": owners[ranked[0][0]][0], "search_paths": search_paths}


def _derive_files(
    task_text: str, allowed_files: list[Any] | tuple[Any, ...], root: Path
) -> dict[str, Any]:
    files: list[str] = []
    docs: list[tuple[str, str]] = []
    for rel in dict.fromkeys(
        item for item in allowed_files[:MAX_CANDIDATE_PATHS] if isinstance(item, str)
    ):
        if len(files) >= MAX_SEARCH_PATHS:
            break
        parts = _relative_parts(rel)
        if parts is None:
            continue
        source = _read_inside(root, parts)
        if source is None or len(source) > MAX_FILE_BYTES:
            continue
        try:
            symbols = _symbols(_module_name(parts), source, MAX_SYMBOLS - len(docs))
        except (SyntaxError, ValueError, RecursionError):
            continue  # one unparsable file must not drop the others
        files.append(rel)
        for symbol in symbols:
            if len(docs) >= MAX_SYMBOLS:
                break
            if len(symbol) <= MAX_SYMBOL_LENGTH and _SYMBOL.fullmatch(symbol):
                docs.append((symbol, _symbol_text(symbol)))
    if not docs:
        return {}
    ranked = BM25Index(docs).rank(task_text, limit=1)
    if not ranked or ranked[0][1] <= 0:
        return {}
    return {"target_symbol": str(ranked[0][0]), "search_paths": files}
