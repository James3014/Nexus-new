"""Deterministic task facts for the canonical planner (Issue #2688).

Commit 5665fa00f (2026-08-06) moved ``nexus run`` onto the canonical seam and
left the planner two route features. The planner still reads the task facts the
old auto-flow computed (risk, cross-module, memory and findings hits, hard
signals, root-cause confidence), so every Gateway task was tiered
``L1_green_lane`` and most capabilities were never selected.

This module recomputes those facts with the existing signal builders. It only
reports facts: it never chooses a flow, route, lane, worker or model, and the
Planner stays the sole route authority. No model or network call is made.
"""

from __future__ import annotations

import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any, Sequence

SCHEMA = "nexus.canonical_route_facts.v1"
_ROOT_CAUSE_CONFIDENCE = 0.8
_CONTRACT_PREFIXES = ("nexus/orchestrator/", "nexus/delivery/", "nexus/contracts/")

# One import graph per (root, HEAD) for the life of the process: a full scan of
# Nexus-new takes ~6 s, an impact query on the cached graph ~10 ms.
_GRAPH_LOCK = threading.Lock()
_GRAPH_INDEX: dict[tuple[str, str], Path] = {}
_GRAPH_DIR: Path | None = None


def _head(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _graph_index(root: Path) -> Path:
    global _GRAPH_DIR
    from nexus.services.codeintel.graph_builder import scan_codebase

    key = (str(root.resolve()), _head(root))
    with _GRAPH_LOCK:
        cached = _GRAPH_INDEX.get(key)
        if cached is not None and cached.exists():
            return cached
        if _GRAPH_DIR is None:
            _GRAPH_DIR = Path(tempfile.mkdtemp(prefix="nexus-route-facts-"))
        index = _GRAPH_DIR / f"graph-{len(_GRAPH_INDEX)}.json"
        scan_codebase(root, index_path=index)
        _GRAPH_INDEX[key] = index
        return index


def allowed_files_cross_module(allowed_files: Sequence[str]) -> bool:
    """The MCP ingress rule removed in 5665fa00f: several files across modules."""
    files = tuple(sorted(str(path) for path in allowed_files if str(path).strip()))
    top_level = {path.split("/", 1)[0] for path in files}
    return len(files) > 1 and (len(top_level) > 1 or any(p.startswith("nexus/") for p in files))


def derive_canonical_route_facts(
    *,
    repo_root: Path,
    task_text: str,
    task_type: str,
    allowed_files: Sequence[str],
    target_file: str = "",
) -> dict[str, Any]:
    """Return ``{"route_features": {...}, "codeintel": {...}, "errors": [...]}``.

    Each source fails closed to "no fact": an error leaves its keys out and is
    listed in ``errors``, so the planner sees the pre-#2688 inputs for it.
    """
    root = Path(repo_root)
    files = [str(path) for path in allowed_files if str(path).strip()]
    features: dict[str, Any] = {}
    codeintel: dict[str, Any] = {}
    errors: list[str] = []

    try:
        from nexus.research.flow.signal_collector import collect_route_signals

        signals = collect_route_signals(
            repo_root=root,
            task_desc=task_text,
            task_type=task_type,
            candidate_count=1,
            root_cause_confidence=_ROOT_CAUSE_CONFIDENCE,
            findings_query=None,
            target_file=target_file or (files[0] if files else None),
        )
        features.update({
            "findings_hits": int(signals["findings_hits"]),
            "memory_hits": int(signals["memory_hits"]),
            "has_hard_signal": bool(signals["has_hard_signal"]),
            "is_cross_module_task": bool(signals["is_cross_module_task"]),
            "adjusted_root_cause_confidence": float(signals["adjusted_root_cause_confidence"]),
        })
    except Exception as exc:  # noqa: BLE001 - a missing fact must not block planning
        errors.append(f"signals:{type(exc).__name__}")

    if allowed_files_cross_module(files):
        features["is_cross_module_task"] = True
    features["impact_complexity"] = 0.8 if features.get("is_cross_module_task") else 0.1

    if files:
        try:
            from nexus.services.codeintel.impact_service import analyze_impact

            impact = analyze_impact(root, files, index_path=_graph_index(root)).to_dict()
            impacted = list(impact.get("impacted_files") or [])
            features["risk_score"] = int(impact.get("risk_score") or 0)
            codeintel.update({
                "impact_report_present": True,
                "risk_score": features["risk_score"],
                "risk_reason": list(impact.get("risk_reason") or []),
                "impacted_files_count": len(impacted),
                "governance_contract_impacted": any(
                    str(path).startswith(_CONTRACT_PREFIXES) for path in impacted
                ),
            })
        except Exception as exc:  # noqa: BLE001
            errors.append(f"impact:{type(exc).__name__}")

    return {"schema": SCHEMA, "route_features": features, "codeintel": codeintel, "errors": errors}
