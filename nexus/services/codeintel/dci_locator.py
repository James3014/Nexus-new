from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nexus.services.bm25_retrieval import bm25_tokens
from nexus.services.codeintel.retrieval import build_code_retrieval_index

TEXT_SUFFIXES = {".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".rst"}
EXCLUDED_PARTS = {
    ".git",
    ".nexus",
    ".mypy_cache",
    ".nexus-swarm",
    ".obsidian",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "benchmarks",
    "logs",
    "nexus_swarm",
    "packages",
}
STOP_TERMS = {
    "about",
    "after",
    "before",
    "bugfix",
    "change",
    "context",
    "docs",
    "evidence",
    "file",
    "fix",
    "keep",
    "public",
    "repair",
    "sync",
    "task",
    "test",
    "with",
}


# Common words that carry no localisation signal for the token-level span fallback.
_STOP_TOKENS = frozenset(term.lower() for term in STOP_TERMS) | frozenset(
    {"and", "are", "for", "from", "has", "have", "into", "not", "that", "the", "this", "was", "when", "which"}
)


def should_enable_dci(
    *,
    task_type: str = "",
    route_lane: str = "",
    claim_missing: bool = False,
    codeintel_empty: bool = False,
    explicit_opt_in: bool = False,
) -> bool:
    if explicit_opt_in:
        return True
    lane = str(route_lane or "").strip().lower()
    if lane in {"hidden_lite", "hidden_bugfix_supervised", "lite"}:
        return False
    if lane == "context_sync_capped":
        return True
    task = str(task_type or "").strip().lower()
    if task == "public_docs_code_sync":
        return True
    return bool(claim_missing or codeintel_empty)


def locate_dci_evidence(
    repo_root: Path,
    *,
    task_desc: str,
    target_file: str,
    report_path: Path,
    route_lane: str = "",
    max_files: int = 32,
    max_matches: int = 8,
) -> dict[str, Any]:
    root = repo_root.resolve()
    terms = _query_terms(task_desc=task_desc, target_file=target_file)
    ranked = _ranked_candidates(root, task_desc=task_desc, target_file=target_file, max_files=max_files)
    candidate_paths = [path for path, _score in ranked]
    commands = [f"rg --line-number --fixed-strings {json.dumps(term)} <scoped-corpus>" for term in terms[:8]]
    query_tokens = set(bm25_tokens(f"{task_desc} {Path(target_file).stem}")) - _STOP_TOKENS
    spans = _collect_spans(root, candidate_paths, terms=terms, query_tokens=query_tokens, max_matches=max_matches)

    evidence_refs = [f"dci:{item['file']}:L{item['start_line']}" for item in spans]
    coverage_score = round(min(1.0, len({ref.split(':L', 1)[0] for ref in evidence_refs}) / 3.0), 4)
    localization_score = round(min(1.0, len(evidence_refs) / max(1, min(max_matches, 4))), 4)
    report = {
        "schema_version": "nexus_dci_evidence_locator.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "invoked": bool(terms),
        "route_lane": route_lane,
        "target_file": _safe_rel(root, Path(target_file)) or str(target_file),
        "query_terms": terms,
        "commands": commands,
        "localized_spans": spans,
        "ranking": "bm25_path_symbol_impact" if terms else "",
        "ranked_files": [
            {"file": _safe_rel(root, path) or str(path), "score": score} for path, score in ranked
        ],
        "evidence_refs": evidence_refs,
        "evidence_count": len(evidence_refs),
        "coverage_score": coverage_score,
        "localization_score": localization_score,
        "skipped_reason": "" if terms else "no_query_terms",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def _query_terms(*, task_desc: str, target_file: str) -> list[str]:
    raw = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", f"{task_desc} {Path(target_file).stem}")
    terms: list[str] = []
    seen: set[str] = set()
    for item in raw:
        normalized = item.strip("_")
        key = normalized.lower()
        if len(normalized) < 4 or key in STOP_TERMS or key in seen:
            continue
        seen.add(key)
        terms.append(normalized)
    return terms[:12]


def _target_path(root: Path, target_file: str) -> Path | None:
    if not str(target_file or "").strip():
        return None
    target = Path(target_file)
    if not target.is_absolute():
        target = root / target
    try:
        target = target.resolve()
    except OSError:
        target = root / target_file
    return target if _is_allowed_path(root, target) else None


def _allowed_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in EXCLUDED_PARTS)
        base = Path(dirpath)
        for filename in sorted(filenames):
            path = base / filename
            if _is_allowed_path(root, path):
                paths.append(path)
    return paths


def _ranked_candidates(
    root: Path, *, task_desc: str, target_file: str, max_files: int
) -> list[tuple[Path, float | None]]:
    """Files ranked by relevance (BM25 over path + content, plus path/symbol/impact boosts).

    The target file, when given and allowed, always comes first. Files with no relevance
    to the query are not returned (the old folder-walk order filled the budget with them).
    """
    out: list[tuple[Path, float | None]] = []
    target = _target_path(root, target_file)
    if target is not None:
        out.append((target, None))
    if max_files <= len(out):
        return out[:max_files]
    rel_paths: list[str] = []
    for path in _allowed_paths(root):
        rel = _safe_rel(root, path)
        if rel:
            rel_paths.append(rel)
    query = f"{task_desc}\n{target_file}" if str(target_file or "").strip() else task_desc
    index = build_code_retrieval_index(root, rel_paths=rel_paths)
    for item in index.rank(query):
        if len(out) >= max_files:
            break
        path = (root / item.path).resolve()
        if target is not None and path == target:
            continue
        out.append((path, item.score))
    return out


def _collect_spans(
    root: Path,
    paths: list[Path],
    *,
    terms: list[str],
    query_tokens: set[str],
    max_matches: int,
) -> list[dict[str, Any]]:
    """Spread the span budget over ranked files: one span per file first, then more.

    Spans are returned grouped by file in rank order, so file order of ``localized_spans``
    is the relevance order.
    """
    if max_matches <= 0 or not terms:
        return []
    per_file: list[list[dict[str, Any]]] = []
    for path in paths:
        found = _scan_path(root, path, terms=terms, max_matches=max_matches)
        if not found and query_tokens:
            found = _scan_path_tokens(root, path, query_tokens=query_tokens, max_matches=max_matches)
        if not found:
            found = _path_span(root, path)
        per_file.append(found)
    taken = [0] * len(per_file)
    budget = max_matches
    depth = 0
    while budget > 0:
        progressed = False
        for index, found in enumerate(per_file):
            if budget <= 0:
                break
            if depth < len(found):
                taken[index] += 1
                budget -= 1
                progressed = True
        if not progressed:
            break
        depth += 1
    spans: list[dict[str, Any]] = []
    for index, found in enumerate(per_file):
        spans.extend(found[: taken[index]])
    return spans


def _path_span(root: Path, path: Path) -> list[dict[str, Any]]:
    """A ranked file whose relevance comes only from its path (e.g. named in the task)."""
    try:
        with path.open(encoding="utf-8", errors="ignore") as handle:
            first = handle.readline()
    except OSError:
        return []
    return [
        {
            "file": _safe_rel(root, path) or str(path),
            "start_line": 1,
            "end_line": 1,
            "matched_terms": [],
            "match": "path",
            "excerpt": first.strip()[:240],
        }
    ]


def _scan_path_tokens(
    root: Path, path: Path, *, query_tokens: set[str], max_matches: int
) -> list[dict[str, Any]]:
    """Fallback for files ranked on sub-word tokens that no literal term matches."""
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        found = sorted(set(bm25_tokens(line)) & query_tokens)
        if not found:
            continue
        out.append(
            {
                "file": _safe_rel(root, path) or str(path),
                "start_line": index,
                "end_line": index,
                "matched_terms": found[:5],
                "excerpt": line.strip()[:240],
            }
        )
        if len(out) >= max_matches:
            break
    return out


def _scan_path(root: Path, path: Path, *, terms: list[str], max_matches: int) -> list[dict[str, Any]]:
    if max_matches <= 0:
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    lowered_terms = [(term, term.lower()) for term in terms]
    for index, line in enumerate(lines, start=1):
        found = [term for term, low in lowered_terms if low in line.lower()]
        if not found:
            continue
        out.append(
            {
                "file": _safe_rel(root, path) or str(path),
                "start_line": index,
                "end_line": index,
                "matched_terms": found[:5],
                "excerpt": line.strip()[:240],
            }
        )
        if len(out) >= max_matches:
            break
    return out


def _is_allowed_path(root: Path, path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
        return False
    rel = _safe_rel(root, path)
    if not rel:
        return False
    parts = set(Path(rel).parts)
    return not bool(parts & EXCLUDED_PARTS)


def _safe_rel(root: Path, path: Path) -> str | None:
    try:
        resolved = path.resolve()
        return str(resolved.relative_to(root))
    except (OSError, ValueError):
        return None
