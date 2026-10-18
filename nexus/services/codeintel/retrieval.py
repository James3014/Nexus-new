"""Relevance-ranked file retrieval for CodeIntel (#2640).

Core: BM25 over ``path + "\\n" + content`` (``nexus.services.bm25_retrieval``), the same
hybrid R3 (#1185) used. On top of the normalised BM25 score, three fixed, additive boosts:

- path: the query names the file (``a/b/foo.py`` written out, or its dotted module name);
- symbol: an identifier from the query (snake_case, camelCase, CONSTANT_CASE or backticked)
  is *defined* in the file (``def``/``class``/module-level assignment);
- impact: the file imports, or is imported by, one of the top BM25 hits (import graph).

The boost weights were fixed before the #2640 re-run of the #2626 preregistration and were
not tuned on its answer key. Ranking is deterministic: score desc, then path asc.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from nexus.services.bm25_retrieval import BM25Index

__all__ = [
    "CodeRetrievalIndex",
    "RankedFile",
    "build_code_retrieval_index",
    "extract_query_identifiers",
    "rank_files",
]

PATH_BOOST = 1.0
MODULE_BOOST = 0.5
SYMBOL_BOOST = 0.25
SYMBOL_BOOST_CAP = 1.0
IMPACT_BOOST = 0.1
IMPACT_SEEDS = 5
MAX_FILE_BYTES = 2_000_000

_PATH_RE = re.compile(r"[\w./-]+\.py")
_DOTTED_RE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_DEF_RE = re.compile(r"^[ \t]*(?:async[ \t]+)?(?:def|class)[ \t]+([A-Za-z_]\w*)", re.MULTILINE)
_ASSIGN_RE = re.compile(r"^([A-Za-z_]\w*)[ \t]*(?::[^=\n]*)?=(?!=)", re.MULTILINE)
_IMPORT_RE = re.compile(
    r"^[ \t]*(?:from[ \t]+([\w.]+)[ \t]+import|import[ \t]+([\w.]+))", re.MULTILINE
)

_IGNORED_DIRS = {".codex", ".git", ".mypy_cache", ".nexus", ".pytest_cache", ".venv", "__pycache__"}


@dataclass(frozen=True)
class RankedFile:
    path: str
    score: float
    bm25: float = 0.0
    boosts: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_query_identifiers(text: str) -> dict[str, list[str]]:
    """Return ``{"paths": [...], "dotted": [...], "symbols": [...]}`` in first-seen order."""
    text = text or ""
    paths: list[str] = []
    for match in _PATH_RE.finditer(text):
        value = match.group(0)
        value = value[2:] if value.startswith("./") else value
        if value not in paths:
            paths.append(value)
    dotted: list[str] = []
    for match in _DOTTED_RE.finditer(text):
        value = match.group(0)
        if value.endswith(".py") or value in dotted:
            continue
        dotted.append(value)
    backticked = [(m.start(1), m.end(1)) for m in _BACKTICK_RE.finditer(text)]
    symbols: list[str] = []
    for match in _IDENT_RE.finditer(text):
        token = match.group(0)
        camel = any(c.isupper() for c in token[1:]) and any(c.islower() for c in token)
        in_backticks = any(a <= match.start() and match.end() <= b for a, b in backticked)
        if not ("_" in token.strip("_") or camel or in_backticks):
            continue
        if token not in symbols:
            symbols.append(token)
    return {"paths": paths, "dotted": dotted, "symbols": symbols}


def _module_name(rel_path: str) -> str:
    parts = list(Path(rel_path).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _read_text(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def iter_corpus_paths(root: Path, suffixes: Sequence[str] = (".py",)) -> list[str]:
    """Relative paths of files with ``suffixes`` under ``root``, skipping VCS/venv/cache/state dirs."""
    wanted = {suffix.lower() for suffix in suffixes}
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            name for name in dirnames if name not in _IGNORED_DIRS and not name.startswith(".venv")
        )
        base = Path(dirpath)
        for filename in sorted(filenames):
            if Path(filename).suffix.lower() in wanted:
                out.append(str((base / filename).relative_to(root)))
    return sorted(out)


class CodeRetrievalIndex:
    """BM25 + definition + import index over a fixed list of files under ``root``."""

    def __init__(self, root: str | Path, rel_paths: Iterable[str]) -> None:
        self.root = Path(root).resolve()
        self.paths: list[str] = sorted(dict.fromkeys(str(p) for p in rel_paths))
        contents = {rel: _read_text(self.root / rel) for rel in self.paths}
        self.bm25 = BM25Index((rel, f"{rel}\n{contents[rel]}") for rel in self.paths)
        self.definitions: dict[str, set[str]] = {}
        self.modules: dict[str, str] = {}
        imports: dict[str, set[str]] = {}
        for rel in self.paths:
            if not rel.endswith(".py"):
                continue
            text = contents[rel]
            self.modules[_module_name(rel)] = rel
            for name in set(_DEF_RE.findall(text)) | set(_ASSIGN_RE.findall(text)):
                self.definitions.setdefault(name, set()).add(rel)
            imports[rel] = {a or b for a, b in _IMPORT_RE.findall(text)}
        self.neighbors: dict[str, set[str]] = {rel: set() for rel in imports}
        for rel, imported in imports.items():
            for name in imported:
                target = self._resolve_module(name)
                if target and target != rel:
                    self.neighbors[rel].add(target)
                    self.neighbors.setdefault(target, set()).add(rel)

    def _resolve_module(self, name: str) -> str | None:
        parts = name.split(".")
        while parts:
            hit = self.modules.get(".".join(parts))
            if hit:
                return hit
            parts.pop()
        return None

    def rank(self, query: str, *, limit: int | None = None) -> list[RankedFile]:
        raw = self.bm25.rank(query)
        top = raw[0][1] if raw else 0.0
        bm25 = {str(path): (score / top if top > 0 else 0.0) for path, score in raw}
        boosts: dict[str, dict[str, float]] = {}

        def add(path: str, kind: str, value: float) -> None:
            entry = boosts.setdefault(path, {})
            entry[kind] = entry.get(kind, 0.0) + value

        idents = extract_query_identifiers(query)
        for named in idents["paths"]:
            for rel in self.paths:
                if rel == named or rel.endswith("/" + named):
                    add(rel, "path", PATH_BOOST)
        for dotted in idents["dotted"]:
            hit = self.modules.get(dotted)
            if hit:
                add(hit, "path", MODULE_BOOST)
        for symbol in idents["symbols"]:
            for rel in self.definitions.get(symbol, ()):
                add(rel, "symbol", SYMBOL_BOOST)
        for entry in boosts.values():
            if entry.get("symbol", 0.0) > SYMBOL_BOOST_CAP:
                entry["symbol"] = SYMBOL_BOOST_CAP
        for seed, _score in raw[:IMPACT_SEEDS]:
            for neighbor in sorted(self.neighbors.get(str(seed), ())):
                if neighbor in bm25 or neighbor in boosts:
                    add(neighbor, "impact", IMPACT_BOOST)

        candidates = set(bm25) | set(boosts)
        ranked = [
            RankedFile(
                path=path,
                score=round(bm25.get(path, 0.0) + sum(boosts.get(path, {}).values()), 6),
                bm25=round(bm25.get(path, 0.0), 6),
                boosts=dict(sorted(boosts.get(path, {}).items())),
            )
            for path in candidates
        ]
        ranked.sort(key=lambda item: (-item.score, item.path))
        if limit is not None and limit >= 0:
            ranked = ranked[:limit]
        return ranked


_INDEX_CACHE: dict[tuple[str, tuple[str, ...]], tuple[tuple[Any, ...], CodeRetrievalIndex]] = {}
_INDEX_CACHE_MAX = 4


def _signature(root: Path, rel_paths: Sequence[str]) -> tuple[Any, ...]:
    sig: list[Any] = []
    for rel in rel_paths:
        try:
            stat = (root / rel).stat()
            sig.append((rel, stat.st_mtime_ns, stat.st_size))
        except OSError:
            sig.append((rel, None, None))
    return tuple(sig)


def build_code_retrieval_index(
    root: str | Path, *, rel_paths: Sequence[str] | None = None, suffixes: Sequence[str] = (".py",)
) -> CodeRetrievalIndex:
    """Build (or reuse from a small mtime/size-checked cache) an index over ``root``."""
    project_root = Path(root).resolve()
    paths = (
        sorted(rel_paths) if rel_paths is not None else iter_corpus_paths(project_root, suffixes)
    )
    key = (
        str(project_root),
        tuple(sorted(s.lower() for s in suffixes)) if rel_paths is None else ("<explicit>",),
    )
    signature = _signature(project_root, paths)
    cached = _INDEX_CACHE.get(key)
    if cached and cached[0] == signature:
        return cached[1]
    index = CodeRetrievalIndex(project_root, paths)
    if len(_INDEX_CACHE) >= _INDEX_CACHE_MAX and key not in _INDEX_CACHE:
        _INDEX_CACHE.pop(next(iter(_INDEX_CACHE)))
    _INDEX_CACHE[key] = (signature, index)
    return index


def rank_files(
    root: str | Path,
    query: str,
    *,
    limit: int | None = 50,
    suffixes: Sequence[str] = (".py",),
) -> list[RankedFile]:
    """Rank files under ``root`` by relevance to free-text ``query`` (BM25 + boosts)."""
    return build_code_retrieval_index(root, suffixes=suffixes).rank(query, limit=limit)
