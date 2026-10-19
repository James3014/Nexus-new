"""Pick a codeintel lookup target from the task's own files (#2721).

On the Gateway worker path the codeintel executor needs a ``target_symbol`` and
``search_paths``; callers rarely supply them, so codeintel refused every task
(``TARGET_SYMBOL_REQUIRED``).  This ranks the symbols defined in the task's
existing allowed ``.py`` files against the task text with BM25 and proposes the
best match.  Deterministic, no model call; the result is still re-validated by
``_codeintel_lookup_context`` before the executor sees it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Sequence

from nexus.services.bm25_retrieval import BM25Index
from nexus.services.codeintel.skeleton_provider import PythonCodeSkeletonProvider

MAX_SEARCH_PATHS = 4
MAX_SYMBOL_LENGTH = 128
_SPLIT = re.compile(r"[._]+|(?<=[a-z0-9])(?=[A-Z])")


def _symbol_text(symbol: str, signature: str) -> str:
    """Symbol name split into words (snake_case, dotted, camelCase) plus its signature."""
    words = " ".join(part for part in _SPLIT.split(symbol) if part)
    return f"{symbol} {words} {signature}"


def derive_codeintel_lookup(
    task_text: str, allowed_files: Sequence[Any], workspace_root: Any
) -> dict[str, Any]:
    """``{"target_symbol", "search_paths"}`` for the best-matching symbol, or ``{}``."""
    if not task_text or not workspace_root:
        return {}
    try:
        return _derive(task_text, allowed_files, Path(str(workspace_root)).resolve(strict=True))
    except (OSError, RuntimeError, ValueError, SyntaxError):
        return {}  # a missing target is a codeintel refusal, never a dispatch failure


def _inside(root: Path, rel: Any) -> bool:
    """An existing ``.py`` regular file inside ``root``, reached without a symlink."""
    if not isinstance(rel, str) or not rel.endswith(".py"):
        return False
    parts = Path(rel).parts
    if not parts or Path(rel).is_absolute() or any(part in ("", ".", "..") for part in parts):
        return False
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            return False
    return current.is_file() and root in current.resolve().parents


def _derive(task_text: str, allowed_files: Sequence[Any], root: Path) -> dict[str, Any]:
    files = [path for path in allowed_files if _inside(root, path)][:MAX_SEARCH_PATHS]
    if not files:
        return {}
    provider = PythonCodeSkeletonProvider(root, search_paths=files)
    docs: list[tuple[str, str]] = []
    for rel in files:
        for item in provider._symbols_for_file(root / rel):
            if len(item.symbol) <= MAX_SYMBOL_LENGTH:
                docs.append((item.symbol, _symbol_text(item.symbol, item.signature)))
    if not docs:
        return {}
    ranked = BM25Index(docs).rank(task_text, limit=1)
    if not ranked or ranked[0][1] <= 0:
        return {}
    return {"target_symbol": str(ranked[0][0]), "search_paths": files}
