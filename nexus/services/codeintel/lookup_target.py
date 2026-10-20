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
"""

from __future__ import annotations

import ast
import os
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Any

from nexus.services.bm25_retrieval import BM25Index

MAX_SEARCH_PATHS = 4
MAX_CANDIDATE_PATHS = 16
MAX_FILE_BYTES = 1024 * 1024
MAX_SYMBOLS = 2000
MAX_TASK_CHARS = 4000
MAX_SYMBOL_LENGTH = 128
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


def _read_inside(root: Path, parts: tuple[str, ...]) -> bytes | None:
    """Bytes of ``root/parts`` opened without following any symlink, or ``None``."""
    fds: list[int] = []
    try:
        fds.append(os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
        for part in parts[:-1]:
            fds.append(os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fds[-1]))
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fds[-1])
        fds.append(fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
            return None
        return os.read(fd, MAX_FILE_BYTES + 1)[: MAX_FILE_BYTES + 1]
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
