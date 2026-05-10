from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TEXT_SUFFIXES = {".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".rst"}
EXCLUDED_PARTS = {
    ".git",
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
    candidate_paths = _candidate_paths(root, target_file=target_file, max_files=max_files)
    spans: list[dict[str, Any]] = []
    commands = [f"rg --line-number --fixed-strings {json.dumps(term)} <scoped-corpus>" for term in terms[:8]]
    for path in candidate_paths:
        if len(spans) >= max_matches:
            break
        spans.extend(_scan_path(root, path, terms=terms, max_matches=max_matches - len(spans)))

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


def _candidate_paths(root: Path, *, target_file: str, max_files: int) -> list[Path]:
    paths: list[Path] = []
    target = Path(target_file)
    if not target.is_absolute():
        target = root / target
    try:
        target = target.resolve()
    except OSError:
        target = root / target_file
    if _is_allowed_path(root, target):
        paths.append(target)

    for path in root.rglob("*"):
        if len(paths) >= max_files:
            break
        if path in paths or not _is_allowed_path(root, path):
            continue
        paths.append(path)
    return paths


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
