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

import hashlib
import posixpath
import subprocess
import tempfile
import threading
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

SCHEMA = "nexus.canonical_route_facts.v1"
_ROOT_CAUSE_CONFIDENCE = 0.8
_CONTRACT_PREFIXES = ("nexus/orchestrator/", "nexus/delivery/", "nexus/contracts/")

# One import graph per (root, HEAD, worktree status) for the life of the process: a full
# scan of Nexus-new takes ~6 s, an impact query on the cached graph ~10 ms.  A root whose
# revision cannot be read is never cached (each query walks the imports live).
_GRAPH_LOCK = threading.Lock()
_GRAPH_KEY_LOCKS: dict[tuple[str, str, str], threading.Lock] = {}
_GRAPH_INDEX: dict[tuple[str, str, str], Path] = {}
_GRAPH_DIR: Path | None = None


def _git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _graph_key(root: Path) -> tuple[str, str, str] | None:
    head = (_git(root, "rev-parse", "HEAD") or "").strip()
    status = _git(root, "status", "--porcelain", "-z", "--untracked-files=all", "--", "*.py")
    if not head or status is None:
        return None
    # Hash the status and the current bytes of every dirty Python file, so a second
    # edit of an already-modified file also rebuilds the graph.
    digest = hashlib.sha256(status.encode("utf-8"))
    for entry in status.split("\0"):
        relative = entry[3:] if len(entry) > 3 else ""
        if not relative:
            continue
        try:
            digest.update((root / relative).read_bytes())
        except OSError:
            digest.update(b"<unreadable>")
    return (str(root.resolve()), head, digest.hexdigest())


def _graph_index(root: Path) -> Path | None:
    global _GRAPH_DIR
    from nexus.services.codeintel.graph_builder import scan_codebase

    key = _graph_key(root)
    if key is None:
        return None
    with _GRAPH_LOCK:
        cached = _GRAPH_INDEX.get(key)
        if cached is not None and cached.exists():
            return cached
        if _GRAPH_DIR is None:
            _GRAPH_DIR = Path(tempfile.mkdtemp(prefix="nexus-route-facts-"))
        key_lock = _GRAPH_KEY_LOCKS.setdefault(key, threading.Lock())
        index = _GRAPH_DIR / f"graph-{hashlib.sha256(repr(key).encode()).hexdigest()[:16]}.json"
    # Scan outside the global lock: other roots and revisions do not wait on this one.
    with key_lock:
        with _GRAPH_LOCK:
            cached = _GRAPH_INDEX.get(key)
        if cached is not None and cached.exists():
            return cached
        scan_codebase(root, index_path=index)
        with _GRAPH_LOCK:
            _GRAPH_INDEX[key] = index
        return index


def _bounded_relative_files(root: Path, allowed_files: Sequence[str]) -> list[str]:
    """Unique repo-relative paths that stay inside ``root``; anything else is dropped."""
    resolved_root = root.resolve()
    bounded: list[str] = []
    for raw in allowed_files:
        raw_text = str(raw).strip()
        path = PurePosixPath(raw_text)
        if not raw_text or path.is_absolute() or ".." in path.parts or "\\" in raw_text:
            continue
        text = posixpath.normpath(raw_text)
        try:
            (resolved_root / text).resolve().relative_to(resolved_root)
        except (OSError, ValueError):
            continue
        if text not in bounded:
            bounded.append(text)
    return bounded


def allowed_files_cross_module(allowed_files: Sequence[str]) -> bool:
    """The MCP ingress rule removed in 5665fa00f: several files across modules."""
    files = tuple(
        sorted({
            posixpath.normpath(str(path).strip()) for path in allowed_files if str(path).strip()
        })
    )
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

    Only repo-relative ``allowed_files`` inside ``repo_root`` are read.  Each source
    degrades to "no fact": an error leaves its keys out and is listed in ``errors``, so
    the planner sees the pre-#2688 inputs for it (never less than before this module).
    """
    root = Path(repo_root)
    files = _bounded_relative_files(root, allowed_files)
    if target_file and target_file not in files:
        target_file = ""
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
    if "is_cross_module_task" in features:
        features["impact_complexity"] = 0.8 if features["is_cross_module_task"] else 0.1

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
