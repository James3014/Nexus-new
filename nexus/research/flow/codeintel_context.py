from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nexus.engine.learning_policy_loader import route_cost_controls_from_env
from nexus.services.codeintel import analyze_impact, scan_codebase
from nexus.services.codeintel.dci_locator import locate_dci_evidence, should_enable_dci


def _safe_codeintel_slug(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", (text or "").strip().lower()).strip("-")
    return slug[:80] or "research-auto-flow"


def rel_path_for_report(repo_root: Path, path_text: str) -> str:
    path = Path(path_text)
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def codeintel_run_cache_graph_path(repo_root: Path) -> Path | None:
    if os.environ.get("NEXUS_CODEINTEL_CACHE_SCOPE", "").strip().lower() != "run":
        return None
    cache_dir = os.environ.get("NEXUS_CODEINTEL_RUN_CACHE_DIR", "").strip()
    if not cache_dir:
        return None
    path = Path(cache_dir)
    if not path.is_absolute():
        path = repo_root / path
    return path / "code_graph.json"


def load_codeintel_graph(path: Path) -> dict[str, Any] | None:
    try:
        graph = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(graph, dict) and isinstance(graph.get("nodes"), list) and isinstance(graph.get("edges"), list):
        return graph
    return None


def build_codeintel_evidence(repo_root: Path, *, target_file: str, task_desc: str) -> dict[str, Any]:
    slug = _safe_codeintel_slug(task_desc)
    report_dir = repo_root / ".nexus" / "reports" / "codeintel"
    graph_path = codeintel_run_cache_graph_path(repo_root) or report_dir / f"{slug}_code_graph.json"
    scan_report_path = report_dir / f"{slug}_scan.json"
    impact_report_path = report_dir / f"{slug}_impact.json"
    dci_report_path = report_dir / f"{slug}_dci.json"
    changed_file = rel_path_for_report(repo_root, target_file)
    try:
        cached_graph = load_codeintel_graph(graph_path) if graph_path.exists() else None
        if cached_graph is None:
            scan = scan_codebase(repo_root, index_path=graph_path).to_dict()
            cache_status = "miss"
        else:
            scan = {
                "nodes_count": len(cached_graph.get("nodes", []) or []),
                "edges_count": len(cached_graph.get("edges", []) or []),
                "languages": ["python"] if cached_graph.get("nodes") else [],
                "index_path": str(graph_path),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            cache_status = "hit"
        scan["report_path"] = str(scan_report_path)
        scan["cache_status"] = cache_status
        scan_report_path.parent.mkdir(parents=True, exist_ok=True)
        scan_report_path.write_text(json.dumps(scan, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        impact = analyze_impact(repo_root, [changed_file], index_path=graph_path).to_dict()
        impact["report_path"] = str(impact_report_path)
        evidence_paths = list(impact.get("evidence_paths", []) or [])
        for path in (str(scan_report_path), str(impact_report_path)):
            if path not in evidence_paths:
                evidence_paths.append(path)
        route_controls = route_cost_controls_from_env()
        route_lane = str(route_controls.get("route_lane") or "")
        dci_report: dict[str, Any] = {}
        if should_enable_dci(
            route_lane=route_lane,
            codeintel_empty=not bool(impact.get("impacted_files", []) or impact.get("impacted_symbols", [])),
            explicit_opt_in=bool(route_controls.get("enable_dci_locator", False)),
        ):
            dci_report = locate_dci_evidence(
                repo_root,
                task_desc=task_desc,
                target_file=target_file,
                report_path=dci_report_path,
                route_lane=route_lane,
            )
            if dci_report.get("report_path") and dci_report.get("report_path") not in evidence_paths:
                evidence_paths.append(str(dci_report["report_path"]))
        impact["evidence_paths"] = evidence_paths
        impact_report_path.write_text(json.dumps(impact, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return {
            "gate_mode": "scan_impact_required",
            "scan_report_present": True,
            "impact_report_present": True,
            "claim_bundle_present": True,
            "scan_report_path": str(scan_report_path),
            "impact_report_path": str(impact_report_path),
            "graph_index_path": str(graph_path),
            "cache_status": cache_status,
            "nodes_count": int(scan.get("nodes_count", 0) or 0),
            "edges_count": int(scan.get("edges_count", 0) or 0),
            "risk_score": int(impact.get("risk_score", 0) or 0),
            "risk_reason": list(impact.get("risk_reason", []) or []),
            "impacted_files_count": len(list(impact.get("impacted_files", []) or [])),
            "impacted_symbols_count": len(list(impact.get("impacted_symbols", []) or [])),
            "dci_locator_present": bool(dci_report.get("invoked", False)),
            "dci_locator_report_path": str(dci_report.get("report_path") or ""),
            "dci_evidence_refs": list(dci_report.get("evidence_refs", []) or []),
            "dci_evidence_count": int(dci_report.get("evidence_count", 0) or 0),
            "dci_coverage_score": float(dci_report.get("coverage_score", 0.0) or 0.0),
            "dci_localization_score": float(dci_report.get("localization_score", 0.0) or 0.0),
        }
    except Exception as exc:
        return {
            "gate_mode": "scan_impact_required",
            "scan_report_present": False,
            "impact_report_present": False,
            "claim_bundle_present": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def task_with_codeintel_context(task_desc: str, codeintel: dict[str, Any]) -> str:
    if not codeintel.get("impact_report_present"):
        return task_desc
    risk_reasons = ", ".join(str(item) for item in codeintel.get("risk_reason", []) or []) or "none"
    controls = route_cost_controls_from_env()
    if str(controls.get("context_mode") or "").lower() == "compact":
        dci_context = ""
        if codeintel.get("dci_locator_present"):
            dci_context = (
                f"\n- dci_evidence_count: {codeintel.get('dci_evidence_count', 0)}"
                f"\n- dci_report: {codeintel.get('dci_locator_report_path', '')}"
            )
        return (
            f"{task_desc}\n\n"
            "[Nexus CodeIntel Compact]\n"
            f"- impact_report: {codeintel.get('impact_report_path', '')}\n"
            f"- risk_score: {codeintel.get('risk_score', 0)}\n"
            f"- impacted_files_count: {codeintel.get('impacted_files_count', 0)}\n"
            f"- risk_reason: {risk_reasons[:240]}"
            f"{dci_context}"
        )
    return (
        f"{task_desc}\n\n"
        "[Nexus CodeIntel]\n"
        f"- impact_report: {codeintel.get('impact_report_path', '')}\n"
        f"- risk_score: {codeintel.get('risk_score', 0)}\n"
        f"- impacted_files_count: {codeintel.get('impacted_files_count', 0)}\n"
        f"- risk_reason: {risk_reasons}\n"
        f"- dci_evidence_count: {codeintel.get('dci_evidence_count', 0)}"
    )
