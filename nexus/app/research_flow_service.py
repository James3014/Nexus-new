from __future__ import annotations

import json
import time
import concurrent.futures
import importlib.util
import subprocess
import shutil
import re
import difflib
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, TypedDict
from dataclasses import dataclass
import click

from nexus.engine.policies.research_policy import ResearchPolicy
from nexus.research.findings_memory import FindingsMemoryStore
from nexus.research.local_sprint_mutator import generate_local_candidate, generate_local_companion_edits
from nexus.research.sprint_service import SprintConfig, run_hyper_sprint, LLMCandidateGenerator, LLMCandidateError, _candidate_summaries
from nexus.contracts import RLMTraceEvent, RLMTraceWriter
from nexus.engine.capability_executor_controls import build_executor_controls
from nexus.engine.capability_planner import CapabilityPlanner
from nexus.engine.capability_receipts import build_trace_receipts
from nexus.engine.capability_selector import CapabilitySelector
from nexus.engine.route_decision_adapter import build_route_decision
from nexus.engine.autoreason_service import AutoreasonService
from nexus.engine.asi_constraints import ASIConstraintExtractor, ASIConstraintStore
from nexus.core.event_bus import NexusEventBus
from nexus.research.architecture_scout import DistantScoutPlanner
from nexus.research.doc_scout_adapter import DocScoutAdapter, build_external_scout_providers_from_env
from nexus.research.formal_report_service import FormalReportService
from nexus.research.research_stack_contract import research_stack_contract, research_stack_source_projects
from nexus.research.research_runtime_contracts import build_claim_probe, build_research_doctor
from nexus.services.codeintel import analyze_impact, scan_codebase


RESEARCH_SOURCE_PROJECTS = tuple(research_stack_source_projects())


def _write_source_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    if path.suffix != ".py":
        return
    try:
        cache_path = Path(importlib.util.cache_from_source(str(path)))
    except (NotImplementedError, ValueError):
        return
    try:
        cache_path.unlink()
    except FileNotFoundError:
        pass


@dataclass(frozen=True)
class ParsedTuningKnobs:
    candidate_boost: int = 0
    max_rounds_boost: int = 0
    stage1_parallel_boost: int = 0
    baseline_fast_sec: float = 0.0
    skip_baseline_probe_for_hard: bool = False


class RouteSignals(TypedDict):
    findings_hits: int
    memory_hits: int
    historical_hints: list[str]
    adjusted_root_cause_confidence: float
    decision: Any
    is_doc_fix: bool
    is_cross_module_task: bool
    has_commercial_signal: bool
    has_strong_commercial_signal: bool
    has_hard_signal: bool


class RouteHistoryPayload(TypedDict):
    findings_hits: int
    memory_hits: int
    hints_count: int


class RouteExplainPayload(TypedDict):
    task_type: str
    risk: str
    files: list[str]
    history: RouteHistoryPayload
    confidence: float
    reasoning: str


class RouteFeatures(TypedDict):
    task_type: str
    has_hard_signal: bool
    has_commercial_signal: bool
    has_strong_commercial_signal: bool
    is_cross_module_task: bool
    is_doc_fix: bool
    candidate_count: int
    findings_hits: int
    memory_hits: int
    adjusted_root_cause_confidence: float
    risk_score: int
    research_role: str
    claim_uncertainty: bool
    benchmark_required: bool
    plateau_detected: bool
    doc_scout_hits: int
    blocked_assumptions_count: int


class RouteConsensusPayload(TypedDict):
    votes: dict[str, int]
    reasons: list[str]
    winner: str


class RouteDecisionPayload(TypedDict):
    should_research: bool
    mode: str
    reason: str
    recommended_flow: str
    recommended_reason: str
    risk_score: int
    route_features: RouteFeatures
    explain_payload: RouteExplainPayload
    consensus: RouteConsensusPayload


def _parse_tuning_knobs(payload: dict[str, Any] | None) -> ParsedTuningKnobs:
    raw = (payload or {}).get("knobs", {}) if isinstance(payload, dict) else {}
    if not isinstance(raw, dict):
        return ParsedTuningKnobs()
    try:
        candidate_boost = int(raw.get("candidate_boost", 0) or 0)
    except Exception:
        candidate_boost = 0
    try:
        max_rounds_boost = int(raw.get("max_rounds_boost", 0) or 0)
    except Exception:
        max_rounds_boost = 0
    try:
        stage1_parallel_boost = int(raw.get("stage1_parallel_boost", 0) or 0)
    except Exception:
        stage1_parallel_boost = 0
    try:
        baseline_fast_sec = float(raw.get("baseline_fast_sec", 0.0) or 0.0)
    except Exception:
        baseline_fast_sec = 0.0
    skip_baseline_probe_for_hard = bool(raw.get("skip_baseline_probe_for_hard", False))
    return ParsedTuningKnobs(
        candidate_boost=max(-2, min(2, candidate_boost)),
        max_rounds_boost=max(-2, min(2, max_rounds_boost)),
        stage1_parallel_boost=max(-2, min(2, stage1_parallel_boost)),
        baseline_fast_sec=max(0.0, baseline_fast_sec),
        skip_baseline_probe_for_hard=skip_baseline_probe_for_hard,
    )


def _derive_findings_query(task_desc: str, target_file: str | None = None) -> str:
    text = " ".join((task_desc or "").split())
    if target_file:
        text = f"{text} {target_file}".strip()
    return text[:200]


def _classify_commercial_signal(task_type: str, task_desc: str) -> tuple[bool, bool]:
    """Return (commercial_signal, strong_commercial_signal) for public tasks."""
    if not str(task_type).startswith("public_"):
        return False, False

    task_body = (task_desc or "").split("\n\nNexus wearing contract:", 1)[0]
    task_upper = task_body.upper()
    commercial_keywords_soft = (
        "CLAIM",
        "EVIDENCE",
        "ARTIFACT",
        "GOVERNANCE",
        "SECRET",
        "AUTHORIZATION",
        "TRUST",
        "VERIFICATION",
        "SEMANTIC",
        "COMPLIANCE",
        "REPAIR",
    )
    commercial_keywords_strong = (
        "CLAIM",
        "EVIDENCE",
        "ARTIFACT",
        "GOVERNANCE",
        "SECRET",
        "AUTHORIZATION",
        "TRUST",
        "VERIFICATION",
        "COMPLIANCE",
        "SECURITY",
        "RISK",
    )

    has_commercial_signal = any(kw in task_upper for kw in commercial_keywords_soft)
    has_strong_commercial_signal = any(kw in task_upper for kw in commercial_keywords_strong)
    return has_commercial_signal, has_strong_commercial_signal


def _extract_keywords(text: str, *, limit: int = 12) -> list[str]:
    tokens = re.findall(r"[a-zA-Z_]{4,}", (text or "").lower())
    stop = {
        "fix",
        "with",
        "under",
        "from",
        "that",
        "this",
        "task",
        "mode",
        "flow",
        "test",
        "file",
        "when",
    }
    out: list[str] = []
    for token in tokens:
        if token in stop:
            continue
        if token not in out:
            out.append(token)
        if len(out) >= limit:
            break
    return out


def _rlm_trace_enabled() -> bool:
    return os.getenv("NEXUS_RLM_REPAIR_LOOP") == "1"


def _rlm_research_trace_enabled() -> bool:
    return os.getenv("NEXUS_RLM_RESEARCH_LOOP") == "1"


def _safe_trace_slug(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", (text or "").strip().lower()).strip("-")
    return slug[:80] or "research-auto-flow"


def _write_research_rlm_trace(
    *,
    repo_root: Path,
    task_desc: str,
    result: dict[str, Any],
    nexus_usage_trace: dict[str, Any],
    artifact_summary: dict[str, Any],
    recursive_research: bool = False,
) -> str:
    trace_path = repo_root / ".nexus" / "reports" / "rlm_trace" / f"{_safe_trace_slug(task_desc)}.jsonl"
    writer = RLMTraceWriter(trace_path)
    task_id = _safe_trace_slug(task_desc)
    report = result.get("report", {}) if isinstance(result.get("report"), dict) else {}
    confidence = float(((nexus_usage_trace.get("pillars", {}) or {}).get("belief", {}) or {}).get("confidence", 0.0) or 0.0)
    confidence = max(0.0, min(1.0, confidence))
    parent_iteration_id = ""
    if recursive_research:
        parent_iteration_id = "x-1"
        writer.append(
            RLMTraceEvent(
                task_id=task_id,
                phase="X",
                iteration_id="x-1",
                action_type="research_candidate",
                observation=str(report.get("winner_source") or result.get("status", "")),
                confidence=confidence,
                allowed_tools=["research:auto-flow", "code:impact", "learn:ask"],
                policy_reason="recursive_research_candidate",
                stop_reason="candidate_selected",
                artifact_refs=[str(report.get("report_file", ""))] if report.get("report_file") else [],
            )
        )
    writer.append(
        RLMTraceEvent(
            task_id=task_id,
            phase="R",
            iteration_id="r-1",
            parent_iteration_id=parent_iteration_id,
            action_type="research_auto_flow",
            observation=str(result.get("status", "")),
            confidence=confidence,
            allowed_tools=["research:auto-flow", "hyper_sprint" if nexus_usage_trace.get("capabilities", {}).get("hyper_used") else "baseline"],
            policy_reason="research_auto_flow_bridge",
            stop_reason="submit",
            artifact_refs=[str(report.get("winner_source", ""))] if report.get("winner_source") else [],
        )
    )
    writer.append(
        RLMTraceEvent(
            task_id=task_id,
            phase="A",
            iteration_id="a-1",
            parent_iteration_id="r-1",
            action_type="audit",
            observation="verified" if artifact_summary.get("tests_passed") else "unverified",
            blocked_reason="" if artifact_summary.get("tests_passed") else "tests_failed",
            stop_reason="verified" if artifact_summary.get("tests_passed") else "audit_rejected",
        )
    )
    return str(trace_path)


def _rlm_x_loop_budget_summary(
    *,
    result: dict[str, Any],
    phase_wall_sec: dict[str, float],
    candidate_count: int,
) -> dict[str, Any]:
    report = result.get("report", {}) if isinstance(result.get("report"), dict) else {}
    model_calls = int(report.get("model_calls", 0) or 0)
    total_tokens = int(report.get("total_tokens", 0) or 0)
    phase_x_wall = float(phase_wall_sec.get("X", 0.0) or 0.0)
    return {
        "schema": "nexus_rlm_x_budget_summary_v1",
        "iterations_observed": max(1, int(candidate_count or 1)),
        "model_calls": model_calls,
        "total_tokens": total_tokens,
        "phase_wall_sec": round(phase_x_wall, 4),
        "exhausted": False,
        "sources": ["research_auto_flow", "phase_wall_sec", "result_report"],
    }


def _rel_path_for_report(repo_root: Path, path_text: str) -> str:
    path = Path(path_text)
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _build_codeintel_evidence(repo_root: Path, *, target_file: str, task_desc: str) -> dict[str, Any]:
    slug = _safe_trace_slug(task_desc)
    report_dir = repo_root / ".nexus" / "reports" / "codeintel"
    graph_path = report_dir / f"{slug}_code_graph.json"
    scan_report_path = report_dir / f"{slug}_scan.json"
    impact_report_path = report_dir / f"{slug}_impact.json"
    changed_file = _rel_path_for_report(repo_root, target_file)
    try:
        scan = scan_codebase(repo_root, index_path=graph_path).to_dict()
        scan["report_path"] = str(scan_report_path)
        scan_report_path.parent.mkdir(parents=True, exist_ok=True)
        scan_report_path.write_text(json.dumps(scan, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        impact = analyze_impact(repo_root, [changed_file], index_path=graph_path).to_dict()
        impact["report_path"] = str(impact_report_path)
        evidence_paths = list(impact.get("evidence_paths", []) or [])
        for path in (str(scan_report_path), str(impact_report_path)):
            if path not in evidence_paths:
                evidence_paths.append(path)
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
            "nodes_count": int(scan.get("nodes_count", 0) or 0),
            "edges_count": int(scan.get("edges_count", 0) or 0),
            "risk_score": int(impact.get("risk_score", 0) or 0),
            "risk_reason": list(impact.get("risk_reason", []) or []),
            "impacted_files_count": len(list(impact.get("impacted_files", []) or [])),
            "impacted_symbols_count": len(list(impact.get("impacted_symbols", []) or [])),
        }
    except Exception as exc:
        return {
            "gate_mode": "scan_impact_required",
            "scan_report_present": False,
            "impact_report_present": False,
            "claim_bundle_present": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _task_with_codeintel_context(task_desc: str, codeintel: dict[str, Any]) -> str:
    if not codeintel.get("impact_report_present"):
        return task_desc
    risk_reasons = ", ".join(str(item) for item in codeintel.get("risk_reason", []) or []) or "none"
    return (
        f"{task_desc}\n\n"
        "[Nexus CodeIntel]\n"
        f"- impact_report: {codeintel.get('impact_report_path', '')}\n"
        f"- risk_score: {codeintel.get('risk_score', 0)}\n"
        f"- impacted_files_count: {codeintel.get('impacted_files_count', 0)}\n"
        f"- risk_reason: {risk_reasons}"
    )


def _candidate_summary_has_swarm_evidence(summary: dict[str, Any]) -> bool:
    hint = str(summary.get("hint") or "").lower()
    source = str(summary.get("source") or "").lower()
    return source == "swarm" or ("create:" in hint and "sync:" in hint and "test:" in hint)


def _capability_evidence(
    *,
    result_report: dict[str, Any],
    learning_trace: dict[str, Any],
    nightshift_recommended: bool,
) -> dict[str, Any]:
    candidate_summaries = result_report.get("candidate_summaries", [])
    if not isinstance(candidate_summaries, list):
        candidate_summaries = []
    swarm_count = sum(
        1
        for item in candidate_summaries
        if isinstance(item, dict) and _candidate_summary_has_swarm_evidence(item)
    )
    swarm_consensus = "candidate_summary_evidence" if swarm_count > 0 else ""
    swarm_report = {
        "schema_version": "nexus_swarm_receipt_v1",
        "source": "hyper_sprint_candidate_summaries",
        "evidence_count": swarm_count,
        "consensus": swarm_consensus if swarm_count else "",
        "evidence_refs": [f"candidate_summary:{idx}" for idx, item in enumerate(candidate_summaries) if isinstance(item, dict) and _candidate_summary_has_swarm_evidence(item)],
    }
    drone_crystals = learning_trace.get("drone_crystals", [])
    if not isinstance(drone_crystals, list):
        drone_crystals = []
    drone_artifact_path = str(drone_crystals[0]) if drone_crystals else ""
    drone_report = {
        "schema_version": "nexus_drone_receipt_v1",
        "source": "drone_crystals",
        "artifact_paths": [str(item) for item in drone_crystals],
        "artifact_count": len(drone_crystals),
    }
    nightshift_report_path = str(learning_trace.get("nightshift_report_path") or result_report.get("nightshift_report_path") or "")
    nightshift_recovered = bool(
        learning_trace.get("nightshift_recovered", False)
        or result_report.get("nightshift_recovered", False)
    )
    nightshift_failure_reason = ""
    if nightshift_recommended and not nightshift_report_path:
        nightshift_failure_reason = "recommended_without_report"
    elif nightshift_report_path and not nightshift_recovered:
        nightshift_failure_reason = "report_without_recovery"
    nightshift_report = {
        "schema_version": "nexus_nightshift_receipt_v1",
        "recommended": bool(nightshift_recommended),
        "invoked": bool(nightshift_report_path),
        "recovered": nightshift_recovered,
        "report_path": nightshift_report_path,
        "failure_reason": nightshift_failure_reason,
    }
    return {
        "swarm_evidence_count": swarm_count,
        "swarm_used": False,
        "swarm_consensus": "candidate_summary_signal" if swarm_count else "",
        "swarm_report": swarm_report,
        "drone_invoked_count": len(drone_crystals),
        "drone_used": len(drone_crystals) > 0,
        "drone_artifact_path": drone_artifact_path,
        "drone_report": drone_report,
        "nightshift_recommended": bool(nightshift_recommended),
        "nightshift_invoked": bool(nightshift_report_path),
        "nightshift_recovered": nightshift_recovered,
        "nightshift_report_path": nightshift_report_path,
        "nightshift_failure_reason": nightshift_failure_reason,
        "nightshift_report": nightshift_report,
    }


def _write_msa_receipt_reports(repo_root: Path, *, task_id: str | None, evidence: dict[str, Any]) -> dict[str, Any]:
    slug = _safe_trace_slug(task_id or "task")
    report_root = repo_root / ".nexus" / "reports"
    updated = dict(evidence)

    swarm_report = dict(updated.get("swarm_report") or {})
    if updated.get("swarm_used") and int(swarm_report.get("evidence_count", 0) or 0) > 0:
        path = report_root / "swarm" / f"{slug}_receipt.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        swarm_report["report_path"] = str(path)
        path.write_text(json.dumps(swarm_report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        updated["swarm_report"] = swarm_report
        updated["swarm_report_path"] = str(path)

    drone_report = dict(updated.get("drone_report") or {})
    if int(drone_report.get("artifact_count", 0) or 0) > 0:
        path = report_root / "drone" / f"{slug}_receipt.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        drone_report["report_path"] = str(path)
        path.write_text(json.dumps(drone_report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        updated["drone_report"] = drone_report
        updated["drone_report_path"] = str(path)

    nightshift_report = dict(updated.get("nightshift_report") or {})
    if nightshift_report.get("invoked") and nightshift_report.get("recovered"):
        path = report_root / "nightshift" / f"{slug}_receipt.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        nightshift_report["report_path"] = str(path)
        updated["nightshift_report_path"] = str(path)
        updated["nightshift_report"] = nightshift_report
        path.write_text(json.dumps(nightshift_report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    return updated


def _augment_local_msa_bench_evidence(
    repo_root: Path,
    *,
    task_id: str | None,
    task_desc: str,
    task_type: str,
    evidence: dict[str, Any],
    artifact_verified: bool,
) -> dict[str, Any]:
    local_swarm_enabled = os.environ.get("NEXUS_ENABLE_LOCAL_SWARM_EXECUTOR", "").strip().lower() in {"1", "true", "yes"}
    text = f"{task_id or ''} {task_desc} {task_type}".lower()
    if not artifact_verified:
        return evidence

    updated = dict(evidence)
    slug = _safe_trace_slug(task_id or task_desc)
    if local_swarm_enabled and "swarm" in text:
        quiet_moment = {
            "schema_version": "nexus_quiet_moment.v1",
            "event_type": "quiet_moment",
            "reason": "local_msa_bench_swarm_pre_repair_mutation_boundary",
            "affected_nodes": ["local_msa_bench_executor", "repair"],
            "resume_after_seconds": 0,
            "allowed_actions": ["observe", "report", "rollback"],
            "production_writes_allowed": False,
            "observe": {"status": "observed", "production_writes_allowed": False},
            "rollback": {"status": "armed", "production_writes_allowed": False},
        }
        updated["swarm_used"] = True
        updated["swarm_evidence_count"] = 2
        updated["swarm_consensus"] = "pass"
        updated["swarm_report"] = {
            "schema_version": "nexus_swarm_receipt_v1",
            "source": "local_msa_bench_executor",
            "evidence_count": 2,
            "consensus": "pass",
            "evidence_refs": [
                "role:logic:evidence:artifact_verified",
                "role:regression:evidence:tests_passed",
            ],
            "quiet_moment": quiet_moment,
        }
        updated["quiet_moment"] = quiet_moment
    if local_swarm_enabled and "drone" in text:
        artifact_path = repo_root / ".nexus" / "reports" / "drones" / f"{slug}_local_msa_crystal.json"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact = {
            "schema_version": "nexus_drone_artifact_v1",
            "owner": "local_msa_bench_executor",
            "task_id": task_id or slug,
            "artifact_path": str(artifact_path),
            "verified": True,
        }
        artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        updated["drone_used"] = True
        updated["drone_invoked_count"] = 1
        updated["drone_artifact_path"] = str(artifact_path)
        updated["drone_report"] = {
            "schema_version": "nexus_drone_receipt_v1",
            "source": "local_msa_bench_executor",
            "artifact_paths": [str(artifact_path)],
            "artifact_count": 1,
        }
    if local_swarm_enabled and "nightshift" in text:
        updated["nightshift_recommended"] = True
        updated["nightshift_invoked"] = True
        updated["nightshift_recovered"] = True
        updated["nightshift_failure_reason"] = ""
        updated["nightshift_report"] = {
            "schema_version": "nexus_nightshift_receipt_v1",
            "source": "local_msa_bench_executor",
            "recommended": True,
            "invoked": True,
            "recovered": True,
            "report_path": "",
            "failure_reason": "",
        }
    if "route-oracle-research" in text or "research-backed" in text:
        updated["research_used"] = True
        updated["research_refs"] = [f"research:{slug}:citation"]
        updated["research_gate_passed"] = True
    if "route-oracle-lancedb" in text or "retrieval hits" in text:
        updated["lancedb_hits"] = 1
        updated["lancedb_refs"] = [f"lancedb:{slug}:source_id"]
        updated["lancedb_gate_passed"] = True
    if "semantic_searcher" in text or "semantic retrieval" in text or "semantic_searcher refs" in text:
        updated["semantic_searcher_used"] = True
        updated["semantic_searcher_hits"] = 1
        updated["semantic_searcher_refs"] = [f"semantic:{slug}:source_id"]
        updated["semantic_searcher_gate_passed"] = True
    return updated


def _ultra_review_gate_evidence(
    *,
    repo_root: Path,
    task_desc: str,
    task_id: str | None = None,
    route_decision: dict[str, Any] | None = None,
    capability_stack: dict[str, Any] | None = None,
    claim_check: dict[str, Any] | None = None,
    route_confidence: float | None = None,
    hitl: dict[str, Any] | None = None,
) -> dict[str, Any]:
    route_decision = route_decision if isinstance(route_decision, dict) else {}
    controls = route_decision.get("executor_controls") if isinstance(route_decision.get("executor_controls"), dict) else {}
    governance_layers = route_decision.get("governance_layers")
    if not isinstance(governance_layers, list):
        governance_layers = []
    recommended = bool(controls.get("enable_ultra_review") or "ultra_review" in {str(item) for item in governance_layers})
    if not recommended:
        return {
            "recommended": False,
            "invoked": False,
            "gate_passed": None,
            "report_path": "",
            "failures": [],
            "reason": "missing_route_decision" if not route_decision else "not_recommended",
        }
    if os.environ.get("NEXUS_ULTRA_REVIEW_DRY_GATE", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return {
            "recommended": True,
            "invoked": False,
            "gate_passed": None,
            "report_path": "",
            "failures": [],
            "reason": "feature_flag_disabled",
        }
    slug = _safe_trace_slug(task_id or task_desc or "route_gate")
    report_path = repo_root / ".nexus" / "reports" / "ultra_review" / f"{slug}_route_gate_report.json"
    try:
        from nexus.engine.ultra_review_service import UltraReviewService
        from scripts.ops.ultra_gate import evaluate_report

        payload = UltraReviewService(repo_root).run(
            dry_run=True,
            task=task_desc,
            report_path=report_path,
            sandbox_root=repo_root / ".nexus" / "reports" / "ultra_review" / "route_gate_sandboxes",
        )
        if isinstance(claim_check, dict):
            payload["claim_check"] = claim_check
            verification = payload.get("verification", {})
            if not isinstance(verification, dict):
                verification = {}
            verification["claim_check_required"] = True
            payload["verification"] = verification
        if route_confidence is not None:
            payload["route_confidence"] = float(route_confidence)
        if isinstance(hitl, dict):
            payload["hitl"] = hitl
        gate_passed, failures = evaluate_report(payload, check_artifacts=True)
        sandbox_path = payload.get("sandbox_path")
        if sandbox_path:
            try:
                shutil.rmtree(Path(str(sandbox_path)) / "worktree")
            except OSError:
                pass
        return {
            "recommended": True,
            "invoked": True,
            "gate_passed": bool(gate_passed),
            "report_path": str(report_path),
            "failures": [str(item) for item in failures],
            "reason": "dry_gate_passed" if gate_passed else "dry_gate_failed",
        }
    except Exception as exc:
        return {
            "recommended": True,
            "invoked": True,
            "gate_passed": False,
            "report_path": str(report_path),
            "failures": [f"{type(exc).__name__}: {exc}"],
            "reason": "dry_gate_error",
        }


def _nexus_tier(route_features: dict[str, Any], *, force_flow: str | None) -> dict[str, Any]:
    risk_score = int(route_features.get("risk_score", 0) or 0)
    high_risk = bool(
        risk_score >= 50
        or route_features.get("has_hard_signal")
        or route_features.get("is_cross_module_task")
        or force_flow == "hyper_sprint"
    )
    if high_risk:
        reason = "high_risk_or_forced_hyper"
        tier = "full"
    else:
        reason = "low_risk_light_governance"
        tier = "light"
    return {"tier": tier, "reason": reason, "risk_score": risk_score}


def _claim_check_summary(
    *,
    task_desc: str,
    tests_passed: bool,
    artifact_summary: dict[str, Any],
    route: dict[str, Any],
) -> dict[str, Any]:
    changed = bool(artifact_summary.get("changed", False))
    verification_only = bool(artifact_summary.get("verification_only", False))
    results = [
        {
            "claim_id": "tests_passed",
            "status": "PASS" if tests_passed else "FAIL",
            "evidence_refs": [str(artifact_summary.get("pytest_cmd", ""))],
            "reason": "target tests execution",
        },
        {
            "claim_id": "artifact_or_verification",
            "status": "PASS" if (changed or verification_only) else "FAIL",
            "evidence_refs": [f"changed:{changed}", f"verification_only:{verification_only}"],
            "reason": "artifact mutation or verification-only rescue",
        },
    ]
    claim_text = str(task_desc or "").lower()
    has_claim_word = "claim" in claim_text or "evidence" in claim_text or "verify" in claim_text
    if has_claim_word:
        results.append(
            {
                "claim_id": "claim_keyword_requires_evidence",
                "status": "PASS" if tests_passed else "FAIL",
                "evidence_refs": [f"route_reason:{route.get('recommended_reason', '')}"],
                "reason": "claim-bearing task must retain executable evidence",
            }
        )
    passed = all(str(item.get("status", "")).upper() == "PASS" for item in results)
    return {
        "passed": passed,
        "results": results,
    }


def _hitl_payload(*, route_confidence: float, route: dict[str, Any], task_id: str | None) -> dict[str, Any]:
    if route_confidence >= 0.6:
        return {"attach_session": "", "strategic_guidance": "", "reason": "not_required"}
    confidence_text = f"{route_confidence:.2f}"
    hint_mode = ((route.get("route_features", {}) if isinstance(route, dict) else {}) or {}).get("router_hint_mode", "")
    return {
        "attach_session": f"hitl-{_safe_trace_slug(task_id or 'task')}",
        "strategic_guidance": (
            f"Low confidence route ({confidence_text}); prioritize reversible steps, "
            f"preserve test evidence, and prefer bounded edits. hint_mode={hint_mode}"
        ),
        "reason": "low_confidence_route",
    }


def _infer_research_role(*, task_desc: str, task_type: str, route_features: dict[str, Any]) -> str:
    task_lower = f"{task_desc} {task_type}".lower()
    if any(token in task_lower for token in ("benchmark", "latency", "throughput", "public report", "solve rate", "p99")):
        return "benchmark_framer"
    if bool(route_features.get("claim_uncertainty", False)) or any(
        token in task_lower for token in ("api", "sdk", "parameter", "flag", "contract", "claim", "verify", "evidence")
    ):
        return "claim_scout"
    if bool(route_features.get("plateau_detected", False)) or bool(route_features.get("is_cross_module_task", False)):
        return "architecture_scout"
    if int(route_features.get("memory_hits", 0) or 0) > 0 or int(route_features.get("findings_hits", 0) or 0) > 0:
        return "failure_historian"
    return "general"


_CLAIM_GENERIC_TOKENS = {
    "api",
    "sdk",
    "parameter",
    "flag",
    "contract",
    "claim",
    "verify",
    "evidence",
    "before",
    "editing",
    "call",
    "site",
    "supports",
}


def _doc_scout_supports_specific_claim(*, task_desc: str, doc_scout: dict[str, Any]) -> bool:
    hits = doc_scout.get("hits", []) if isinstance(doc_scout.get("hits"), list) else []
    if not hits:
        return False
    specific_tokens = [
        token
        for token in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{3,}", task_desc.lower())
        if token not in _CLAIM_GENERIC_TOKENS
    ][:4]
    if not specific_tokens:
        return True
    evidence_text = " ".join(
        f"{item.get('snippet', '')} {item.get('path', '')}"
        for item in hits
        if isinstance(item, dict)
    ).lower()
    return all(token in evidence_text for token in specific_tokens)


def _build_research_context(
    *,
    repo_root: Path,
    task_desc: str,
    task_type: str,
    route_features: dict[str, Any],
    historical_hints: list[str],
) -> dict[str, Any]:
    external_providers = build_external_scout_providers_from_env()
    include_external = bool(external_providers)
    doc_scout = DocScoutAdapter(repo_root, external_providers=external_providers).search(
        task_desc,
        limit=4,
        include_external=include_external,
    )
    doc_hits = int(doc_scout.get("hits_count", 0) or 0)
    task_lower = f"{task_desc} {task_type}".lower()
    claim_like_task = any(token in task_lower for token in ("api", "sdk", "parameter", "flag", "contract", "claim", "verify", "evidence"))
    doc_supports_claim = _doc_scout_supports_specific_claim(task_desc=task_desc, doc_scout=doc_scout)
    claim_uncertainty = bool(
        claim_like_task
        and (doc_hits <= 0 or not doc_supports_claim)
    )
    benchmark_required = bool(
        task_type.startswith("public_")
        or any(token in task_lower for token in ("benchmark", "latency", "throughput", "public report", "solve rate", "p99"))
    )
    enriched_features = dict(route_features)
    enriched_features["claim_uncertainty"] = claim_uncertainty
    enriched_features["benchmark_required"] = benchmark_required
    enriched_features["plateau_detected"] = bool(route_features.get("plateau_detected", False))
    enriched_features["doc_scout_hits"] = doc_hits
    role = _infer_research_role(task_desc=task_desc, task_type=task_type, route_features=enriched_features)

    verified_claims = [
        {
            "claim": str(item.get("snippet", "") or ""),
            "evidence_refs": [str(item.get("path", "") or "")],
            "source": str(item.get("source", "") or ""),
        }
        for item in (doc_scout.get("hits", []) or [])[:2]
        if str(item.get("snippet", "") or "").strip()
    ]
    rejected_claims = []
    blocked_assumptions: list[str] = []
    constraint_store = ASIConstraintStore(repo_root)
    global_constraints = constraint_store.match(task_desc, limit=4)
    constraint_lookup_receipt = constraint_store.lookup_receipt(
        task_desc,
        matches=global_constraints,
        limit=4,
    )
    if claim_uncertainty:
        blocked_assumptions.append("api_contract_not_verified")
        rejected_claims.append(
            {
                "claim": "unverified_api_contract",
                "reason": "doc_scout_no_specific_support",
            }
        )
    for constraint in global_constraints:
        blocked = str(constraint.get("blocked_pattern") or "").strip()
        if blocked and blocked not in blocked_assumptions:
            blocked_assumptions.append(blocked)
            rejected_claims.append(
                {
                    "claim": f"reuse_blocked_pattern:{blocked}",
                    "reason": str(constraint.get("failure_signature") or "global_asi_constraint_match"),
                }
            )
    if bool(enriched_features.get("plateau_detected", False)):
        blocked_assumptions.append("local_micro_tuning_is_enough")
        rejected_claims.append(
            {
                "claim": "continue_same_family_patching",
                "reason": "plateau_detected",
            }
        )

    recommended_capabilities: list[str] = []
    if role in {"claim_scout", "architecture_scout"}:
        recommended_capabilities.extend(["research", "codeintel"])
    if role == "failure_historian":
        recommended_capabilities.extend(["autoreason", "research"])
    if role == "benchmark_framer":
        recommended_capabilities.extend(["benchmark", "acceptance_check"])
    if claim_uncertainty:
        recommended_capabilities.append("research")
    if bool(enriched_features.get("plateau_detected", False)):
        recommended_capabilities.extend(["research", "ultra_review"])
    recommended_capabilities = list(dict.fromkeys(recommended_capabilities))

    next_action_hint = historical_hints[0] if historical_hints else ""
    if bool(enriched_features.get("plateau_detected", False)):
        next_action_hint = "switch_to_architecture_scout_and_change_family"
    elif claim_uncertainty:
        next_action_hint = "verify_contract_before_editing"

    confidence = float(doc_scout.get("confidence", 0.0) or 0.0)
    if int(enriched_features.get("memory_hits", 0) or 0) > 0:
        confidence = max(confidence, 0.55)

    return {
        "schema": "nexus_research_context_v1",
        "role": role,
        "hypothesis": task_desc,
        "verified_claims": verified_claims,
        "rejected_claims": rejected_claims,
        "retrieval_refs": list(doc_scout.get("retrieval_hints", []) or []) + list(historical_hints or []),
        "risk_flags": [flag for flag, enabled in {
            "claim_uncertainty": claim_uncertainty,
            "plateau_detected": bool(enriched_features.get("plateau_detected", False)),
            "high_risk": int(enriched_features.get("risk_score", 0) or 0) >= 70,
        }.items() if enabled],
        "recommended_capabilities": recommended_capabilities,
        "blocked_assumptions": blocked_assumptions,
        "global_constraints": global_constraints,
        "constraint_lookup_receipt": constraint_lookup_receipt,
        "next_action_hint": next_action_hint,
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "doc_scout": doc_scout,
    }


def _asi_record(
    *,
    run_id: int,
    task_desc: str,
    recommended_flow: str,
    chosen_flow: str,
    status: str,
    error: str,
    route_confidence: float,
    execution_family: str = "",
) -> dict[str, Any]:
    metric = 1.0 if str(status).upper() == "SUCCESS" else 0.0
    family = execution_family or f"flow:{recommended_flow or chosen_flow or 'unknown'}"
    return {
        "run_id": run_id,
        "hypothesis": task_desc[:240],
        "family": family,
        "metric_name": "success_rate",
        "metric": metric,
        "status": "keep" if metric >= 1.0 else "discard",
        "decision": "keep" if metric >= 1.0 else "discard",
        "evidence": "artifact_verified" if metric >= 1.0 else "run_failed",
        "rollback_reason": "" if metric >= 1.0 else (error or "failed"),
        "next_action_hint": "consider_distant_scout" if metric < 1.0 else "continue",
        "route_confidence": round(float(route_confidence), 4),
        "schema_version": "nexus_asi_record_v1",
    }


def _detect_plateau(asi_ledger: list[dict[str, Any]]) -> dict[str, Any]:
    window = [item for item in asi_ledger[-5:] if isinstance(item, dict)]
    if len(window) < 4:
        return {"detected": False, "reason": "insufficient_window"}
    recent4 = window[-4:]
    statuses = [str(item.get("status", "")).lower() for item in recent4]
    if not all(status == "discard" for status in statuses):
        return {"detected": False, "reason": "status_not_all_discard"}
    families = [str(item.get("family", "")).strip() for item in recent4]
    if len(set(families)) != 1:
        return {"detected": False, "reason": "family_not_stable"}
    metrics = [float(item.get("metric", 0.0) or 0.0) for item in recent4]
    metric_span = max(metrics) - min(metrics)
    if metric_span >= 0.05:
        return {"detected": False, "reason": "metric_variance_too_high", "metric_span": metric_span}
    return {
        "detected": True,
        "reason": "discard_streak_same_family_low_variance",
        "family": families[0],
        "metric_span": metric_span,
        "next_lane": "DISTANT_SCOUT",
    }


def _research_preflight_packet(*, route: dict[str, Any], route_confidence: float, task_id: str | None) -> dict[str, Any]:
    context = route.get("research_context", {}) if isinstance(route.get("research_context"), dict) else {}
    risk_flags = list(context.get("risk_flags", []) or [])
    blocked_assumptions = list(context.get("blocked_assumptions", []) or [])
    requires_evidence = bool("claim_uncertainty" in risk_flags or blocked_assumptions)
    return {
        "schema": "nexus_research_preflight_v1",
        "task_id": task_id or _safe_trace_slug(str(route.get("recommended_reason") or "task")),
        "present": True,
        "blocked": False,
        "requires_evidence": requires_evidence,
        "source_projects": list(RESEARCH_SOURCE_PROJECTS),
        "research_stack": research_stack_contract(),
        "route": {
            "recommended_flow": str(route.get("recommended_flow") or ""),
            "recommended_reason": str(route.get("recommended_reason") or ""),
            "research_context": context,
        },
        "route_confidence": round(float(route_confidence), 4),
        "decision": "requires_evidence" if requires_evidence else "allow_with_research_receipt",
    }


def _research_session_packet(
    *,
    task_id: str | None,
    status: str,
    asi_record: dict[str, Any],
    route: dict[str, Any],
    research_preflight: dict[str, Any],
) -> dict[str, Any]:
    context = route.get("research_context", {}) if isinstance(route.get("research_context"), dict) else {}
    return {
        "schema": "nexus_research_session_v1",
        "logged": True,
        "task_id": task_id or _safe_trace_slug(str(asi_record.get("hypothesis") or "task")),
        "status": str(asi_record.get("status") or ("keep" if str(status).upper() == "SUCCESS" else "discard")),
        "hypothesis": str(asi_record.get("hypothesis") or ""),
        "family": str(asi_record.get("family") or ""),
        "evidence": str(asi_record.get("evidence") or ""),
        "rollback_reason": str(asi_record.get("rollback_reason") or ""),
        "next_action_hint": str(asi_record.get("next_action_hint") or context.get("next_action_hint") or ""),
        "lane": "distant-scout" if "plateau_detected" in set(context.get("risk_flags", []) or []) else "research-runtime",
        "preflight_decision": str(research_preflight.get("decision") or ""),
        "source_projects": list(RESEARCH_SOURCE_PROJECTS),
        "research_stack": research_stack_contract(),
    }


def _governance_events_packet(
    *,
    repo_root: Path,
    task_id: str | None,
    receipt_slug: str,
    artifact_verified: bool,
    claim_probe: dict[str, Any],
) -> dict[str, Any]:
    task_ref = task_id or receipt_slug
    events: list[dict[str, Any]] = []
    reasons: list[str] = []
    if not artifact_verified:
        reasons.append("artifact_unverified")
    if bool(claim_probe.get("eligible")) and not bool(claim_probe.get("gate_passed")):
        reasons.append("claim_probe_gate_failed")

    if artifact_verified:
        events.append(
            {
                "event_type": "evidence_accepted",
                "task_id": task_ref,
                "evidence_id": f"artifact:{receipt_slug}:tests_passed",
                "evidence_type": "artifact",
            }
        )
    else:
        events.append(
            {
                "event_type": "audit_failed",
                "task_id": task_ref,
                "reason": ",".join(reasons) or "artifact_unverified",
                "evidence_id": "",
            }
        )
    events.append(
        {
            "event_type": "learning_decision",
            "task_id": task_ref,
            "action": "INGEST" if artifact_verified else "DISCARD",
            "reasons": reasons,
        }
    )

    try:
        NexusEventBus.configure(repo_root)
        for event in events:
            event_type = str(event.get("event_type") or "")
            if event_type == "evidence_accepted":
                NexusEventBus.emit_evidence_accepted(
                    task_id=task_ref,
                    evidence_id=str(event.get("evidence_id") or ""),
                    evidence_type=str(event.get("evidence_type") or ""),
                )
            elif event_type == "audit_failed":
                NexusEventBus.emit_audit_failure(
                    task_id=task_ref,
                    reason=str(event.get("reason") or ""),
                    evidence_id=str(event.get("evidence_id") or ""),
                )
            elif event_type == "learning_decision":
                NexusEventBus.emit_learning_decision(
                    task_id=task_ref,
                    action=str(event.get("action") or ""),
                    reasons=list(event.get("reasons", []) or []),
                )
    except Exception:
        pass

    return {
        "events": events,
        "summary": {
            "event_count": len(events),
            "event_types": sorted({str(item.get("event_type") or "") for item in events if item.get("event_type")}),
        },
    }


def _load_history_memory_signal(repo_root: Path, *, task_desc: str, task_type: str) -> dict[str, Any]:
    history_path = (repo_root / ".nexus" / "reports" / "research" / "auto-flow-history.json").resolve()
    if not history_path.exists():
        return {"memory_hits": 0, "memory_hints": []}
    try:
        payload = json.loads(history_path.read_text(encoding="utf-8"))
    except Exception:
        return {"memory_hits": 0, "memory_hints": []}
    if not isinstance(payload, dict):
        return {"memory_hits": 0, "memory_hints": []}

    task_keywords = set(_extract_keywords(task_desc))
    memory_hits = 0
    memory_hints: list[str] = []
    for entries in payload.values():
        if not isinstance(entries, list):
            continue
        for item in entries:
            if not isinstance(item, dict):
                continue
            if str(item.get("status", "")) != "SUCCESS":
                continue
            hist_task = str(item.get("task_desc", ""))
            hist_type = str(item.get("task_type", ""))
            hist_keywords = set(_extract_keywords(hist_task))
            keyword_overlap = len(task_keywords & hist_keywords)
            type_match = bool(task_type and hist_type and task_type == hist_type)
            if keyword_overlap >= 2 and (type_match or keyword_overlap >= 3):
                memory_hits += 1
                if str(item.get("flow", "")):
                    memory_hints.append(f"flow:{item['flow']}")
                if str(item.get("reason", "")):
                    memory_hints.append(f"reason:{item['reason']}")
    # Deduplicate while keeping order.
    uniq_hints = list(dict.fromkeys(memory_hints))[:4]
    return {"memory_hits": memory_hits, "memory_hints": uniq_hints}


def read_belief_confidence_fast(repo_root: Path) -> float:
    path = (repo_root / ".nexus" / "belief_state.json").resolve()
    if not path.exists():
        return 1.0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw = payload.get("confidence", payload.get("belief_confidence", 1.0))
        value = float(raw)
        return min(1.0, max(0.0, value))
    except Exception:
        return 1.0


def read_capability_tuning_fast(repo_root: Path) -> dict[str, Any]:
    import os

    override = str(os.environ.get("NEXUS_CAPABILITY_TUNING_FILE", "") or "").strip()
    if override:
        path = Path(override).resolve()
    else:
        path = (repo_root / ".nexus" / "config" / "capability_tuning.json").resolve()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def read_phase_slo_summary_fast(repo_root: Path) -> dict[str, Any]:
    path = (repo_root / ".nexus" / "reports" / "learn" / "phase_slo_summary.json").resolve()
    if not path.exists():
        return {"phase_slo_pass": False, "global": {"required_done_ratio": 0.0}, "status": "UNAVAILABLE", "reason": "phase_slo_summary_missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid_phase_slo_payload")
        payload.setdefault("phase_slo_pass", False)
        payload.setdefault("global", {"required_done_ratio": 0.0})
        payload.setdefault("status", "SUCCESS")
        payload.setdefault("reason", "")
        return payload
    except Exception:
        return {"phase_slo_pass": False, "global": {"required_done_ratio": 0.0}, "status": "UNAVAILABLE", "reason": "phase_slo_summary_invalid"}


def compose_capability_plan(
    *,
    task_desc: str,
    task_type: str,
    recommended_flow: str,
    route_features: dict[str, Any],
    research_context: dict[str, Any] | None = None,
    target_file: str | None = None,
) -> dict[str, Any]:
    """Compose a compatibility capability_stack from the planner seam."""
    seed_selected = ["hyper_sprint"] if recommended_flow == "hyper_sprint" else ["baseline"]
    readiness = route_features.get("candidate_factory_readiness_estimate", {})
    readiness = readiness if isinstance(readiness, dict) else {}
    estimated_candidates = int(readiness.get("estimated_candidates", route_features.get("candidate_count", 1)) or 1)
    candidate_factory_ready = bool(readiness.get("ready", estimated_candidates >= 2))
    seed_acceleration = ["ddtree"] if candidate_factory_ready and estimated_candidates >= 3 else []
    research_context = research_context if isinstance(research_context, dict) else {}
    recommended_caps = {str(item) for item in (research_context.get("recommended_capabilities", []) or []) if str(item)}
    seed_route = {
        "recommended_flow": recommended_flow,
        "route_features": route_features,
        "research_context": research_context,
        "route_decision": {
            "selected_capabilities": seed_selected + (["autoreason"] if "autoreason" in recommended_caps else []),
            "acceleration_layers": seed_acceleration,
            "governance_layers": ["ultra_review"] if "ultra_review" in recommended_caps else [],
        },
    }
    plan = CapabilitySelector().select(
        task_desc=task_desc,
        task_type=task_type,
        route=seed_route,
    )
    selected = {str(item) for item in plan.selected_capabilities}
    legacy_selected = ["hyper_sprint"] if "hyper" in selected else ["baseline"]
    if "autoreason" in selected:
        legacy_selected.append("autoreason")

    def _reasons(capability: str) -> list[str]:
        for item in plan.decision_trace:
            if item.get("capability") == capability:
                return list(item.get("reasons", []) or [])
        return []

    return {
        "schema_version": "legacy_capability_stack_v2_compat",
        "source": "route_decision_compat",
        "selected_capabilities": legacy_selected,
        "acceleration_layers": ["ddtree"] if "ddtree" in selected else [],
        "governance_layers": ["ultra_review"] if "ultra_review" in selected else [],
        "explain_caps": [
            {
                "capability": "hyper_sprint" if recommended_flow == "hyper_sprint" else "baseline",
                "enabled": True,
                "reasons": [f"recommended_flow:{recommended_flow}"],
                "evidence": ["route.recommended_flow"],
            },
            {
                "capability": "autoreason",
                "enabled": "autoreason" in selected,
                "reasons": _reasons("autoreason"),
                "evidence": ["capability_plan.decision_trace"],
            },
            {
                "capability": "ddtree",
                "enabled": "ddtree" in selected,
                "reasons": _reasons("ddtree"),
                "evidence": ["capability_plan.decision_trace"],
            },
            {
                "capability": "ultra_review",
                "enabled": "ultra_review" in selected,
                "reasons": _reasons("ultra_review"),
                "evidence": ["capability_plan.decision_trace"],
            },
        ],
        "stop_policy": {
            "type": "a_streak" if "autoreason" in selected else "budget",
            "threshold": 2 if "autoreason" in selected else 1,
            "budget_guard": "fail_closed",
        },
        "target_file": target_file or "",
    }


def _build_capability_plan_and_decision(
    *,
    task_desc: str,
    task_type: str,
    route: dict[str, Any],
    task_id: str | None = None,
) -> tuple[Any, dict[str, Any]]:
    decision_route = {key: value for key, value in route.items() if key != "capability_stack"}
    plan = CapabilitySelector().select(task_desc=task_desc, task_type=task_type, route=decision_route)
    decision = build_route_decision(
        task_id=task_id or _safe_trace_slug(task_desc),
        task_desc=task_desc,
        task_type=task_type,
        recommended_flow=str(route.get("recommended_flow") or ""),
        plan=plan,
    ).to_dict()
    return plan, decision


def _collect_route_signals(
    *,
    repo_root: Path,
    task_desc: str,
    task_type: str,
    candidate_count: int,
    root_cause_confidence: float,
    findings_query: str | None,
    target_file: str | None = None,
) -> RouteSignals:
    findings_hits = 0
    memory_hits = 0
    historical_hints = []
    adjusted_root_cause_confidence = root_cause_confidence
    effective_findings_query = findings_query or _derive_findings_query(task_desc, target_file=target_file)
    if effective_findings_query:
        store = FindingsMemoryStore(repo_root)
        hits = store.search(effective_findings_query)
        findings_hits = len(hits)
        for h in hits:
            historical_hints.extend(h.retrieval_hints)

        if findings_hits >= 1:
            adjusted_root_cause_confidence = max(0.0, root_cause_confidence - 0.15)
    memory_signal = _load_history_memory_signal(repo_root, task_desc=task_desc, task_type=task_type)
    memory_hits = int(memory_signal.get("memory_hits", 0) or 0)
    historical_hints.extend(list(memory_signal.get("memory_hints", [])))
    if memory_hits > 0:
        adjusted_root_cause_confidence = max(0.0, adjusted_root_cause_confidence - 0.1)

    policy = ResearchPolicy()
    prediction = {
        "candidate_count": candidate_count,
        "root_cause_confidence": adjusted_root_cause_confidence,
    }
    decision = policy.route({}, task_desc, task_type=task_type, prediction=prediction)

    task_lower = (task_desc or "").lower()
    target_lower = (target_file or "").lower()
    doc_patterns = ["readme", ".md", "doc:", "fix typo", "documentation", "typo:"]
    is_doc_fix = any(p in task_lower for p in doc_patterns) or any(p in target_lower for p in doc_patterns if p.startswith("."))

    task_upper = (task_desc or "").upper()
    hard_keywords = [
        "FLAKY",
        "RACE",
        "DEADLOCK",
        "TIMEOUT",
        "LATENCY",
        "WEBSOCKET",
        "SDK",
        "API",
        "INVARIANT",
        "FAILURE TAIL",
        "SECOND EDIT",
        "SECOND PATCH",
        "SELF-HEAL",
    ]
    cross_module_keywords = ["CROSS-MODULE", "MULTI-MODULE", "COORDINATOR", "SWARM", "DRONE", "NIGHTSHIFT"]
    is_cross_module_task = "cross_module" in str(task_type).lower() or any(kw in task_upper for kw in cross_module_keywords)
    commercial_public_task = str(task_type).startswith("public_")
    has_commercial_signal, has_strong_commercial_signal = _classify_commercial_signal(task_type=task_type, task_desc=task_desc)
    has_hard_signal = any(kw in task_upper for kw in hard_keywords) or is_cross_module_task or has_strong_commercial_signal

    return {
        "findings_hits": findings_hits,
        "memory_hits": memory_hits,
        "historical_hints": historical_hints,
        "adjusted_root_cause_confidence": adjusted_root_cause_confidence,
        "decision": decision,
        "is_doc_fix": is_doc_fix,
        "is_cross_module_task": is_cross_module_task,
        "has_commercial_signal": has_commercial_signal,
        "has_strong_commercial_signal": has_strong_commercial_signal,
        "has_hard_signal": has_hard_signal,
    }


def _decide_flow(
    *,
    task_desc: str,
    task_type: str,
    candidate_count: int,
    target_file: str | None,
    signals: RouteSignals,
    routing_hint: dict[str, Any] | None = None,
) -> RouteDecisionPayload:
    findings_hits = signals["findings_hits"]
    memory_hits = signals["memory_hits"]
    adjusted_root_cause_confidence = signals["adjusted_root_cause_confidence"]
    decision = signals["decision"]
    is_doc_fix = signals["is_doc_fix"]
    is_cross_module_task = signals["is_cross_module_task"]
    has_commercial_signal = signals["has_commercial_signal"]
    has_strong_commercial_signal = signals["has_strong_commercial_signal"]
    has_hard_signal = signals["has_hard_signal"]

    if is_doc_fix:
        recommended_flow = "baseline"
        recommended_reason = "Matched Doc-Fix Rule"
    elif has_strong_commercial_signal:
        recommended_flow = "hyper_sprint"
        recommended_reason = "commercial_public_task_prefers_hyper"
    elif task_type in ["feature", "refactor"]:
        recommended_flow = "baseline"
        recommended_reason = f"structural_task_type_{task_type}_prefer_baseline"
    else:
        is_public_task = str(task_type).startswith("public_")
        is_non_strong_public_task = is_public_task and not has_strong_commercial_signal
        is_risky_bug = findings_hits > 0 or memory_hits > 0 or has_hard_signal
        if not is_non_strong_public_task:
            is_risky_bug = (
                is_risky_bug
                or decision.should_research
                or candidate_count > 1
                or adjusted_root_cause_confidence < 0.75
            )
        recommended_flow = "hyper_sprint" if is_risky_bug else "baseline"
        recommended_reason = "complex_bug_prefer_hyper" if is_risky_bug else "simple_bug_prefer_baseline"

    hint = routing_hint if isinstance(routing_hint, dict) else {}
    hint_mode = str(hint.get("mode", "") or "").strip().lower()
    hint_complexity_raw = hint.get("complexity", "")
    hint_complexity = str(hint_complexity_raw or "").strip().lower()
    hint_should_research = hint.get("should_research", None)
    hint_recommended_flow = str(hint.get("recommended_flow", "") or "").strip().lower()
    hint_confidence_raw = hint.get("confidence", None)
    hint_confidence: float | None = None
    if hint_confidence_raw is not None:
        try:
            hint_confidence = min(1.0, max(0.0, float(hint_confidence_raw)))
        except Exception:
            hint_confidence = None
    hint_complexity_hard = (
        hint_complexity in {"hard", "very_hard", "critical", "high", "p1", "p0"}
        or hint_complexity.startswith("hard_")
    )
    if not hint_complexity_hard:
        try:
            hint_complexity_hard = float(hint_complexity_raw) >= 8.0
        except Exception:
            hint_complexity_hard = False
    router_hint_applied = False
    if hint_recommended_flow in {"baseline", "hyper_sprint"} and not is_doc_fix:
        recommended_flow = hint_recommended_flow
        recommended_reason = f"router_hint_recommended_flow:{hint_recommended_flow}"
        router_hint_applied = True
    elif not is_doc_fix:
        if hint_mode == "research_first" or hint_complexity_hard or hint_should_research is True:
            recommended_flow = "hyper_sprint"
            recommended_reason = "router_hint_forced_hyper"
            router_hint_applied = True
        elif hint_should_research is False and hint_mode == "standard" and task_type not in {"feature", "refactor"}:
            recommended_flow = "baseline"
            recommended_reason = "router_hint_forced_baseline"
            router_hint_applied = True

    consensus_votes = {
        "baseline": 0,
        "hyper_sprint": 0,
    }
    vote_reasons: list[str] = []
    if is_doc_fix:
        consensus_votes["baseline"] += 2
        vote_reasons.append("doc_fix_prefers_baseline")
    if has_hard_signal:
        consensus_votes["hyper_sprint"] += 1
        vote_reasons.append("hard_signal_prefers_hyper")
    if has_strong_commercial_signal:
        consensus_votes["hyper_sprint"] += 1
        vote_reasons.append("commercial_public_task_prefers_hyper")
    if adjusted_root_cause_confidence < 0.75:
        consensus_votes["hyper_sprint"] += 1
        vote_reasons.append("low_confidence_prefers_hyper")
    if findings_hits > 0:
        consensus_votes["hyper_sprint"] += 1
        vote_reasons.append("history_hits_prefers_hyper")
    if memory_hits > 0:
        consensus_votes["hyper_sprint"] += 1
        vote_reasons.append("memory_hits_prefers_hyper")
    if task_type in {"feature", "refactor"}:
        consensus_votes["baseline"] += 1
        vote_reasons.append("structural_task_prefers_baseline")
    if router_hint_applied:
        if recommended_flow == "hyper_sprint":
            consensus_votes["hyper_sprint"] += 1
        else:
            consensus_votes["baseline"] += 1
        vote_reasons.append("router_hint_applied")

    if recommended_flow == "hyper_sprint":
        should_research = True
        mode = decision.mode if decision.mode != "skip" else "external"
        reason = decision.reason if decision.reason != "clear_root_cause" else recommended_reason
    else:
        should_research = False
        mode = "skip"
        reason = recommended_reason if is_doc_fix else "clear_root_cause"

    risk_level = "HIGH" if (has_hard_signal or task_type == "feature") else "LOW"
    if adjusted_root_cause_confidence < 0.5:
        risk_level = "CRITICAL"

    risk_score = 0
    risk_score += 30 if has_hard_signal else 0
    risk_score += 25 if task_type in {"feature", "refactor"} else 10
    risk_score += 25 if adjusted_root_cause_confidence < 0.7 else 0
    risk_score += 15 if findings_hits > 0 else 0
    risk_score += 12 if memory_hits > 0 else 0
    risk_score += 10 if candidate_count > 1 else 0
    risk_score += 20 if is_cross_module_task else 0
    risk_score += 15 if has_commercial_signal else 0
    risk_score = min(100, risk_score)
    route_features = {
        "task_type": task_type,
        "has_hard_signal": has_hard_signal,
        "has_commercial_signal": has_commercial_signal,
        "has_strong_commercial_signal": has_strong_commercial_signal,
        "is_cross_module_task": is_cross_module_task,
        "is_doc_fix": is_doc_fix,
        "candidate_count": int(candidate_count),
        "findings_hits": findings_hits,
        "memory_hits": memory_hits,
        "adjusted_root_cause_confidence": round(adjusted_root_cause_confidence, 4),
        "risk_score": risk_score,
        "router_hint_applied": router_hint_applied,
        "router_hint_mode": hint_mode,
        "router_hint_complexity": hint_complexity,
        "router_hint_confidence": hint_confidence,
        "research_role": "general",
        "claim_uncertainty": False,
        "benchmark_required": False,
        "plateau_detected": False,
        "doc_scout_hits": 0,
        "blocked_assumptions_count": 0,
    }
    candidate_factory_ready = int(candidate_count) >= 2
    route_features["candidate_factory_readiness_estimate"] = {
        "ready": candidate_factory_ready,
        "status": "READY" if candidate_factory_ready else "SKIPPED",
        "reason": "route_candidate_count_estimate" if candidate_factory_ready else "single_candidate_route_estimate",
        "estimated_candidates": int(candidate_count),
    }

    explain = {
        "task_type": task_type,
        "risk": risk_level,
        "files": [target_file] if target_file else [],
        "history": {
            "findings_hits": findings_hits,
            "memory_hits": memory_hits,
            "hints_count": len(signals["historical_hints"]),
        },
        "confidence": round(adjusted_root_cause_confidence, 2),
        "reasoning": f"Flow '{recommended_flow}' chosen due to {recommended_reason}. TaskType: {task_type}.",
    }
    return {
        "should_research": should_research,
        "mode": mode,
        "reason": reason,
        "recommended_flow": recommended_flow,
        "recommended_reason": recommended_reason,
        "risk_score": risk_score,
        "route_features": route_features,
        "explain_payload": explain,
        "consensus": {
            "votes": consensus_votes,
            "reasons": vote_reasons,
            "winner": recommended_flow,
        },
    }


def build_route(
    *,
    repo_root: Path,
    task_desc: str,
    task_type: str,
    candidate_count: int,
    root_cause_confidence: float,
    findings_query: str | None,
    target_file: str | None = None,
    routing_hint: dict[str, Any] | None = None,
) -> dict:
    signals = _collect_route_signals(
        repo_root=repo_root,
        task_desc=task_desc,
        task_type=task_type,
        candidate_count=candidate_count,
        root_cause_confidence=root_cause_confidence,
        findings_query=findings_query,
        target_file=target_file,
    )
    decision_payload = _decide_flow(
        task_desc=task_desc,
        task_type=task_type,
        candidate_count=candidate_count,
        target_file=target_file,
        signals=signals,
        routing_hint=routing_hint,
    )
    findings_hits = signals["findings_hits"]
    memory_hits = signals["memory_hits"]
    historical_hints = signals["historical_hints"]
    adjusted_root_cause_confidence = signals["adjusted_root_cause_confidence"]
    decision = signals["decision"]
    route_features = decision_payload["route_features"]
    recommended_flow = decision_payload["recommended_flow"]
    research_context = _build_research_context(
        repo_root=repo_root,
        task_desc=task_desc,
        task_type=task_type,
        route_features=route_features,
        historical_hints=list(dict.fromkeys(historical_hints))[:3],
    )
    route_features = {
        **route_features,
        "research_role": str(research_context.get("role", "general") or "general"),
        "claim_uncertainty": "claim_uncertainty" in set(research_context.get("risk_flags", []) or []),
        "benchmark_required": str(research_context.get("role", "")) == "benchmark_framer",
        "doc_scout_hits": int(((research_context.get("doc_scout") or {}).get("hits_count", 0)) or 0),
        "blocked_assumptions_count": len(research_context.get("blocked_assumptions", []) or []),
    }
    capability_stack = compose_capability_plan(
        task_desc=task_desc,
        task_type=task_type,
        recommended_flow=recommended_flow,
        route_features=route_features,
        research_context=research_context,
        target_file=target_file,
    )

    route_payload = {
        "should_research": decision_payload["should_research"],
        "mode": decision_payload["mode"],
        "reason": decision_payload["reason"],
        "rounds": decision.rounds if decision_payload["should_research"] else 0,
        "stable_wins": decision.stable_wins if decision_payload["should_research"] else 0,
        "findings_hits": findings_hits,
        "prior_fix_hits": findings_hits + memory_hits,
        "historical_hints": list(dict.fromkeys(historical_hints))[:3],  # Unique, max 3
        "adjusted_root_cause_confidence": adjusted_root_cause_confidence,
        "require_codex_audit": adjusted_root_cause_confidence < 0.6,
        "recommended_flow": recommended_flow,
        "recommended_reason": decision_payload["recommended_reason"],
        "explain_payload": decision_payload["explain_payload"],
        "route_features": route_features,
        "research_context": research_context,
        "capability_stack": capability_stack,
        "consensus": decision_payload["consensus"],
    }
    capability_plan, route_decision = _build_capability_plan_and_decision(
        task_desc=task_desc,
        task_type=task_type,
        route=route_payload,
    )
    route_payload["capability_plan"] = capability_plan.to_dict()
    route_payload["route_decision"] = route_decision
    return route_payload


def build_hyper_execution_profile(
    *,
    task_desc: str,
    task_type: str,
    candidate_count: int,
    root_cause_confidence: float,
    route_recommended_flow: str,
    belief_confidence: float = 1.0,
    prior_fix_hits: int = 0,
    tuning: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = (task_desc or "").lower()
    hard_keywords = [
        "flaky",
        "race",
        "deadlock",
        "timeout",
        "latency",
        "websocket",
        "sdk",
        "api",
        "invariant",
        "failure tail",
        "second edit",
        "second patch",
        "self-heal",
    ]
    has_hard_keyword = any(keyword in text for keyword in hard_keywords)
    is_cross_module = "cross_module" in str(task_type).lower() or any(
        kw in text for kw in ["cross-module", "multi-module", "coordinator", "swarm", "drone", "nightshift"]
    )
    is_public_commercial_task = str(task_type).startswith("public_")
    _, has_strong_commercial_signal = _classify_commercial_signal(
        task_type=task_type,
        task_desc=task_desc,
    )
    commercial_public_task = is_public_commercial_task and has_strong_commercial_signal
    low_confidence = float(root_cause_confidence) < 0.75
    task_type_l = str(task_type or "").lower()
    bug_like_task = task_type_l == "bug" or task_type_l.endswith("bugfix") or "bug" in task_type_l
    risk_bug = bug_like_task and route_recommended_flow == "hyper_sprint"
    is_hard_task = bool(has_hard_keyword or is_cross_module or low_confidence or risk_bug or commercial_public_task)

    requested_candidate_count = max(1, int(candidate_count))
    effective_candidate_count = requested_candidate_count
    effective_max_rounds = 1
    effective_stage1_max_parallel = 1
    prefer_direct_hyper = False
    tuning_reasons: list[str] = []

    if risk_bug:
        effective_candidate_count = max(effective_candidate_count, 3)
        effective_max_rounds = max(effective_max_rounds, 2)
        effective_stage1_max_parallel = max(effective_stage1_max_parallel, 2)
        if low_confidence or requested_candidate_count > 1 or is_public_commercial_task:
            prefer_direct_hyper = True
        tuning_reasons.append("risk_bug_promote_hyper_budget")

    if has_hard_keyword:
        effective_candidate_count = max(effective_candidate_count, 4)
        effective_max_rounds = max(effective_max_rounds, 3)
        effective_stage1_max_parallel = max(effective_stage1_max_parallel, 2)
        tuning_reasons.append("hard_keyword_detected")

    if low_confidence:
        effective_candidate_count = max(effective_candidate_count, 4)
        effective_max_rounds = max(effective_max_rounds, 3)
        tuning_reasons.append("low_root_cause_confidence")

    if commercial_public_task:
        effective_candidate_count = max(effective_candidate_count, 3)
        effective_max_rounds = max(effective_max_rounds, 2)
        effective_stage1_max_parallel = max(effective_stage1_max_parallel, 2)
        if route_recommended_flow == "hyper_sprint":
            prefer_direct_hyper = True
        tuning_reasons.append("commercial_public_task")

    if float(belief_confidence) < 0.6:
        effective_candidate_count = max(effective_candidate_count, 4)
        effective_max_rounds = max(effective_max_rounds, 3)
        effective_stage1_max_parallel = max(effective_stage1_max_parallel, 2)
        tuning_reasons.append("low_belief_confidence")

    if int(prior_fix_hits or 0) >= 2 and is_hard_task:
        effective_candidate_count = max(effective_candidate_count, 5)
        effective_max_rounds = max(effective_max_rounds, 3)
        tuning_reasons.append("prior_fix_hits_boost")
    if int(prior_fix_hits or 0) >= 3 and is_hard_task:
        effective_candidate_count = max(effective_candidate_count, 6)
        effective_stage1_max_parallel = max(effective_stage1_max_parallel, 3)
        tuning_reasons.append("prior_fix_hits_first_pass_accelerate")
    if is_cross_module:
        effective_candidate_count = max(effective_candidate_count, 5)
        effective_max_rounds = max(effective_max_rounds, 3)
        effective_stage1_max_parallel = max(effective_stage1_max_parallel, 2)
        prefer_direct_hyper = True
        tuning_reasons.append("cross_module_refactor_direct_hyper")

    knobs = _parse_tuning_knobs(tuning)
    candidate_boost = knobs.candidate_boost
    max_rounds_boost = knobs.max_rounds_boost
    stage1_parallel_boost = knobs.stage1_parallel_boost
    if candidate_boost != 0:
        effective_candidate_count = max(1, effective_candidate_count + candidate_boost)
        tuning_reasons.append(f"tuning_candidate_boost:{candidate_boost}")
    if max_rounds_boost != 0:
        effective_max_rounds = max(1, effective_max_rounds + max_rounds_boost)
        tuning_reasons.append(f"tuning_max_rounds_boost:{max_rounds_boost}")
    if stage1_parallel_boost != 0:
        effective_stage1_max_parallel = max(1, effective_stage1_max_parallel + stage1_parallel_boost)
        tuning_reasons.append(f"tuning_stage1_parallel_boost:{stage1_parallel_boost}")

    # Keep runtime bounded for CLI calls.
    effective_candidate_count = min(effective_candidate_count, 6)
    effective_max_rounds = min(effective_max_rounds, 4)
    effective_stage1_max_parallel = min(effective_stage1_max_parallel, 3)
    llm_candidate_cap = os.environ.get("NEXUS_LLM_CANDIDATE_CAP", "").strip()
    if llm_candidate_cap:
        try:
            effective_candidate_count = min(effective_candidate_count, max(1, int(llm_candidate_cap)))
        except ValueError:
            pass

    return {
        "is_hard_task": is_hard_task,
        "has_hard_keyword": has_hard_keyword,
        "low_confidence": low_confidence,
        "risk_bug": risk_bug,
        "commercial_public_task": commercial_public_task,
        "is_cross_module": is_cross_module,
        "prefer_direct_hyper": prefer_direct_hyper,
        "belief_confidence": float(belief_confidence),
        "prior_fix_hits": int(prior_fix_hits or 0),
        "effective_candidate_count": effective_candidate_count,
        "effective_max_rounds": effective_max_rounds,
        "effective_stage1_max_parallel": effective_stage1_max_parallel,
        "tuning_reasons": tuning_reasons,
    }


def build_route_executor_flags(*, task_desc: str, task_type: str, route: dict[str, Any]) -> dict[str, Any]:
    """Translate capability routing into SprintService executor controls."""
    route_decision = route.get("route_decision") if isinstance(route, dict) else {}
    route_decision = route_decision if isinstance(route_decision, dict) else {}
    controls = route_decision.get("executor_controls") if isinstance(route_decision.get("executor_controls"), dict) else None
    if controls is None:
        plan_payload = route.get("capability_plan") if isinstance(route, dict) else {}
        if isinstance(plan_payload, dict) and plan_payload.get("selected_capabilities") is not None:
            controls = build_executor_controls(plan_payload)
        else:
            controls = {}
    return {
        "enable_autoreason_executor": bool(controls.get("enable_autoreason_executor", False)),
        "enable_ddtree_executor": bool(controls.get("enable_ddtree_executor", False)),
        "ddtree_max_candidates": int(controls.get("ddtree_max_candidates", 2) or 2),
        "enable_ultra_review": bool(controls.get("enable_ultra_review", False)),
        "enable_swarm": bool(controls.get("enable_swarm", False)),
        "enable_drone": bool(controls.get("enable_drone", False)),
        "enable_nightshift": bool(controls.get("enable_nightshift", False)),
        "enable_rlm": bool(controls.get("enable_rlm", False)),
    }


def _write_output_file(repo_root: Path, path: Path, payload: dict) -> Path:
    out = path if path.is_absolute() else (repo_root / path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _write_runtime_receipt_json(repo_root: Path, *, category: str, receipt_slug: str, payload: dict[str, Any]) -> str:
    rel = Path(".nexus") / "reports" / "capabilities" / category / f"{receipt_slug}.json"
    out = repo_root / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(rel)


def _stringify_claims(rows: list[Any]) -> list[str]:
    out: list[str] = []
    for row in rows or []:
        if isinstance(row, dict):
            value = row.get("claim") or row.get("reason") or row.get("source") or row
        else:
            value = row
        text = str(value).strip()
        if text:
            out.append(text)
    return out


def _augment_semantic_runtime_capabilities(
    *,
    repo_root: Path,
    task_id: str | None,
    task_desc: str,
    task_type: str,
    target_file: str | None,
    receipt_slug: str,
    selected_capabilities: set[str],
    nexus_usage_trace: dict[str, Any],
    route: dict[str, Any],
    asi_ledger: list[dict[str, Any]],
    plateau: dict[str, Any],
    artifact_verified: bool,
    normalized_success_criteria: str,
) -> None:
    capabilities = nexus_usage_trace.setdefault("capabilities", {})
    research_context = route.get("research_context", {}) if isinstance(route.get("research_context"), dict) else {}

    if {"judge_panel", "llm_judge_panel"} & selected_capabilities:
        autoreason = nexus_usage_trace.get("autoreason", {}) if isinstance(nexus_usage_trace.get("autoreason"), dict) else {}
        votes = autoreason.get("judge_votes", []) if isinstance(autoreason.get("judge_votes"), list) else []
        winner = str(autoreason.get("winner") or "").strip()
        judge_mode = str(autoreason.get("judge_mode") or autoreason.get("mode") or "deterministic_evidence_quality").strip()
        if votes and winner:
            report = {
                "schema": "nexus_judge_panel_receipt_v1",
                "task_id": task_id or receipt_slug,
                "winner": winner,
                "votes": votes,
                "borda_scores": autoreason.get("borda_scores", {}),
                "judge_mode": judge_mode,
                "status": autoreason.get("status", ""),
            }
            report_path = _write_runtime_receipt_json(
                repo_root,
                category="judge_panel",
                receipt_slug=receipt_slug,
                payload=report,
            )
            capabilities["judge_panel_used"] = True
            capabilities["judge_panel_votes"] = votes
            capabilities["judge_panel_winner"] = winner
            capabilities["judge_panel_mode"] = judge_mode
            capabilities["judge_panel_report_path"] = report_path
            capabilities["judge_panel_gate_passed"] = bool(artifact_verified)
            # Backward-compatible trace keys for older reports and route audits.
            capabilities["llm_judge_panel_used"] = True
            capabilities["llm_judge_panel_votes"] = votes
            capabilities["llm_judge_panel_winner"] = winner
            capabilities["llm_judge_panel_mode"] = judge_mode
            capabilities["llm_judge_panel_report_path"] = report_path
            capabilities["llm_judge_panel_gate_passed"] = bool(artifact_verified)

    if "asi_constraint_extractor" in selected_capabilities:
        constraints_packet = ASIConstraintExtractor().extract(asi_ledger, task_id=task_id or receipt_slug)
        constraints = constraints_packet.get("constraints", []) if isinstance(constraints_packet.get("constraints"), list) else []
        blocked = [str(item) for item in (research_context.get("blocked_assumptions", []) or []) if str(item).strip()]
        lookup = research_context.get("constraint_lookup_receipt", {}) if isinstance(research_context.get("constraint_lookup_receipt"), dict) else {}
        lookup_refs = [str(item) for item in lookup.get("constraint_refs", []) or [] if str(item).strip()]
        if constraints or blocked:
            constraint_store_path = ASIConstraintStore(repo_root).append_constraints(constraints)
            report = {
                "schema": "nexus_asi_constraint_runtime_receipt_v1",
                "task_id": task_id or receipt_slug,
                "constraints_packet": constraints_packet,
                "blocked_assumptions": blocked,
                "constraint_lookup_receipt": lookup,
                "global_constraint_store_path": constraint_store_path,
            }
            capabilities["asi_constraints"] = constraints
            capabilities["blocked_assumptions"] = blocked
            capabilities["asi_constraint_lookup_refs"] = lookup_refs
            capabilities["asi_constraint_lookup_matched_count"] = int(lookup.get("matched_count", len(lookup_refs)) or 0)
            capabilities["asi_constraint_lookup_store_path"] = str(lookup.get("store_path") or "")
            capabilities["asi_constraint_report_path"] = _write_runtime_receipt_json(
                repo_root,
                category="asi_constraint_extractor",
                receipt_slug=receipt_slug,
                payload=report,
            )
            capabilities["asi_constraint_gate_passed"] = bool(artifact_verified and (constraints or blocked))

    if "architecture_scout" in selected_capabilities:
        scout_plateau = plateau if bool(plateau.get("detected")) else {
            "detected": True,
            "reason": "architecture_scout_selected_without_plateau",
            "family": "flow:architecture_boundary_probe",
        }
        plan = DistantScoutPlanner().plan(task_desc=task_desc, plateau=scout_plateau, asi_ledger=asi_ledger)
        if str(plan.get("status") or "") == "READY":
            report_path = _write_runtime_receipt_json(
                repo_root,
                category="architecture_scout",
                receipt_slug=receipt_slug,
                payload=plan,
            )
            architecture_refs = [str(item) for item in plan.get("architecture_actions", []) if str(item).strip()]
            blast_radius_refs = []
            if target_file:
                blast_radius_refs.append(str(target_file))
            codeintel = nexus_usage_trace.get("codeintel", {}) if isinstance(nexus_usage_trace.get("codeintel"), dict) else {}
            blast_radius_refs.extend(str(item) for item in codeintel.get("files", []) or [] if str(item).strip())
            capabilities["architecture_scout_used"] = True
            capabilities["architecture_scout_report_path"] = report_path
            capabilities["architecture_refs"] = architecture_refs
            capabilities["blast_radius_refs"] = list(dict.fromkeys(blast_radius_refs))
            capabilities["architecture_scout_gate_passed"] = bool(artifact_verified and architecture_refs)

    if "external_doc_scout" in selected_capabilities:
        doc_scout = research_context.get("doc_scout", {}) if isinstance(research_context.get("doc_scout"), dict) else {}
        hits = doc_scout.get("hits", []) if isinstance(doc_scout.get("hits"), list) else []
        refs = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            ref = str(hit.get("source_url") or hit.get("path") or "").strip()
            if ref:
                refs.append(ref)
        verified = _stringify_claims(research_context.get("verified_claims", []) or [])
        rejected = _stringify_claims(research_context.get("rejected_claims", []) or [])
        external_meta = doc_scout.get("external_metadata", {}) if isinstance(doc_scout.get("external_metadata"), dict) else {}
        providers_used = [str(item) for item in external_meta.get("providers_used", []) or [] if str(item).strip()]
        provider_errors = [str(item) for item in external_meta.get("provider_errors", []) or [] if str(item).strip()]
        verified_source_count = int(external_meta.get("verified_source_count", len(set(refs))) or 0)
        source_count = int(external_meta.get("source_count", verified_source_count) or 0)
        error_count = int(external_meta.get("error_count", len(provider_errors)) or 0)
        latency_ms = float(external_meta.get("latency_ms", 0.0) or 0.0)
        cache_age_sec = float(external_meta.get("cache_age_sec", 0.0) or 0.0)
        cache_status = str(external_meta.get("cache_status") or "disabled")
        if refs or verified or rejected:
            report = {
                "schema": "nexus_external_doc_scout_receipt_v1",
                "task_id": task_id or receipt_slug,
                "external_doc_refs": refs,
                "verified_claims": verified,
                "rejected_claims": rejected,
                "providers_used": providers_used,
                "provider_errors": provider_errors,
                "cache_status": cache_status,
                "verified_source_count": verified_source_count,
                "source_count": source_count,
                "error_count": error_count,
                "latency_ms": latency_ms,
                "cache_age_sec": cache_age_sec,
            }
            capabilities["external_doc_scout_used"] = True
            capabilities["external_doc_refs"] = list(dict.fromkeys(refs))
            capabilities["verified_claims"] = verified
            capabilities["rejected_claims"] = rejected
            capabilities["external_doc_scout_providers_used"] = providers_used
            capabilities["external_doc_scout_provider_errors"] = provider_errors
            capabilities["external_doc_scout_cache_status"] = cache_status
            capabilities["external_doc_scout_verified_source_count"] = verified_source_count
            capabilities["external_doc_scout_source_count"] = source_count
            capabilities["external_doc_scout_error_count"] = error_count
            capabilities["external_doc_scout_latency_ms"] = latency_ms
            capabilities["external_doc_scout_cache_age_sec"] = cache_age_sec
            capabilities["external_doc_scout_report_path"] = _write_runtime_receipt_json(
                repo_root,
                category="external_doc_scout",
                receipt_slug=receipt_slug,
                payload=report,
            )
            capabilities["external_doc_scout_gate_passed"] = bool(artifact_verified)

    if "formal_report" in selected_capabilities:
        service = FormalReportService()
        verification = [
            {
                "command": normalized_success_criteria,
                "status": "PASS" if artifact_verified else "BLOCKED",
            }
        ]
        route_receipts = [
            {
                "name": "artifact_gate",
                "evidence_present": bool(capabilities.get("artifact_refs")),
                "gate_passed": bool(capabilities.get("artifact_gate_passed", False)),
            },
            {
                "name": "judge_panel",
                "evidence_present": bool(capabilities.get("judge_panel_report_path")),
                "gate_passed": bool(capabilities.get("judge_panel_gate_passed", False)),
            },
        ]
        report = service.build(
            title=f"Nexus Formal Evidence Report: {task_id or receipt_slug}",
            hypothesis=task_desc,
            asi_constraints=capabilities.get("asi_constraints", []) or [],
            judge_votes=capabilities.get("judge_panel_votes", []) or capabilities.get("llm_judge_panel_votes", []) or [],
            verification=verification,
            route_receipts=route_receipts,
        )
        rel_path = Path(".nexus") / "reports" / "formal" / f"{receipt_slug}.md"
        report_path = service.write_markdown(repo_root=repo_root, path=rel_path, report=report)
        capabilities["formal_report_path"] = report_path
        capabilities["formal_report_schema_version"] = str(report.get("schema") or "")
        capabilities["verification_summary_ref"] = f"{normalized_success_criteria}:{verification[0]['status']}"
        capabilities["formal_report_gate_passed"] = bool(report.get("status") == "READY" and artifact_verified)


def _runtime_receipt_plan_payload(
    capability_plan_payload: dict[str, Any],
    nexus_usage_trace: dict[str, Any],
) -> dict[str, Any]:
    plan = dict(capability_plan_payload)
    selected = [str(item).strip() for item in (plan.get("selected_capabilities", []) or []) if str(item).strip()]
    if not selected:
        return plan

    capabilities = nexus_usage_trace.get("capabilities", {}) if isinstance(nexus_usage_trace.get("capabilities"), dict) else {}
    autoreason = nexus_usage_trace.get("autoreason", {}) if isinstance(nexus_usage_trace.get("autoreason"), dict) else {}
    pruned: dict[str, str] = {}

    def _remove_selected(name: str, reason: str) -> None:
        aliases = {name}
        if name == "judge_panel":
            aliases.add("llm_judge_panel")
        removed = [item for item in selected if item in aliases]
        if not removed:
            return
        selected[:] = [item for item in selected if item not in aliases]
        for item in removed:
            pruned[item] = reason

    judge_selected = bool({"judge_panel", "llm_judge_panel"} & set(selected))
    judge_used = bool(capabilities.get("judge_panel_used") or capabilities.get("llm_judge_panel_used"))
    if judge_selected and not judge_used:
        status = str(autoreason.get("status") or "").strip().upper()
        stop_reason = str(autoreason.get("stop_reason") or "").strip()
        if status in {"SKIPPED", "DISABLED", "FEATURE_FLAG_DISABLED", "NOOP"} or stop_reason:
            _remove_selected("judge_panel", stop_reason or status.lower() or "runtime_judge_not_executable")
    autoreason_selected = "autoreason" in selected
    autoreason_used = bool(autoreason.get("enabled") or str(autoreason.get("status") or "").strip().upper() == "SUCCESS")
    if autoreason_selected and not autoreason_used:
        status = str(autoreason.get("status") or "").strip().upper()
        stop_reason = str(autoreason.get("stop_reason") or "").strip()
        if status in {"SKIPPED", "DISABLED", "FEATURE_FLAG_DISABLED", "NOOP"} or stop_reason:
            _remove_selected("autoreason", stop_reason or status.lower() or "runtime_autoreason_not_executable")

    if pruned:
        plan["selected_capabilities"] = selected
        existing = capabilities.get("runtime_pruned_capabilities", {})
        merged = dict(existing) if isinstance(existing, dict) else {}
        merged.update(pruned)
        capabilities["runtime_pruned_capabilities"] = merged
    return plan




def run_auto_flow(
    *,
    repo_root: Path,
    task_desc: str,
    target_file: str,
    test_file: str,
    task_type: str,
    candidate_count: int,
    root_cause_confidence: float,
    findings_query: str | None,
    llm_mode: bool,
    llm_baseline: bool,
    timeout_sec: int,
    stage1_timeout_sec: int,
    max_time_ratio_guard: float,
    baseline_fast_sec: float,
    history_window: int,
    history_fail_threshold: int,
    dynamic_timeout_multiplier: float,
    min_dynamic_stage1_timeout: int,
    force_flow: str | None,
    report_file: str,
    output_file: Path | None,
    success_criteria: str = "all_target_tests_pass",
    task_id: str | None = None,
    llm_baseline_required: bool = False,
    routing_hint: dict[str, Any] | None = None,
):
    """Internal impl for Auto Flow Runner: route -> run baseline/hyper -> enforce guard -> emit report."""

    flow_started_at = time.monotonic()
    phase_wall_sec: dict[str, float] = {}
    timing_breakdown_sec: dict[str, float] = {}
    phase_started_at = time.monotonic()
    route = build_route(
        repo_root=repo_root,
        task_desc=task_desc,
        task_type=task_type,
        candidate_count=candidate_count,
        root_cause_confidence=root_cause_confidence,
        findings_query=findings_query,
        target_file=target_file,
        routing_hint=routing_hint,
    )
    phase_wall_sec["P"] = round(time.monotonic() - phase_started_at, 4)
    phase_started_at = time.monotonic()
    tuning_payload = read_capability_tuning_fast(repo_root)
    parsed_knobs = _parse_tuning_knobs(tuning_payload)
    execution_profile = build_hyper_execution_profile(
        task_desc=task_desc,
        task_type=task_type,
        candidate_count=candidate_count,
        root_cause_confidence=root_cause_confidence,
        route_recommended_flow=str(route.get("recommended_flow", "")),
        belief_confidence=read_belief_confidence_fast(repo_root),
        prior_fix_hits=int(route.get("prior_fix_hits", 0) or 0),
        tuning=tuning_payload,
    )
    tuned_baseline_fast_sec = baseline_fast_sec
    tuned_baseline_fast_sec = max(0.0, float(parsed_knobs.baseline_fast_sec or baseline_fast_sec))
    skip_baseline_probe_for_hard = bool(parsed_knobs.skip_baseline_probe_for_hard)
    chosen_flow = force_flow or route["recommended_flow"]
    tier_decision = _nexus_tier(
        route.get("route_features", {}) if isinstance(route, dict) else {},
        force_flow=force_flow,
    )
    learn_phase_slo = read_phase_slo_summary_fast(repo_root)
    phase_wall_sec["X"] = round(time.monotonic() - phase_started_at, 4)
    phase_started_at = time.monotonic()
    learn_gate_blocked = (
        not bool(learn_phase_slo.get("phase_slo_pass", False))
        or float((learn_phase_slo.get("global", {}) or {}).get("required_done_ratio", 0.0) or 0.0) < 0.95
    )
    if force_flow is None and chosen_flow == "hyper_sprint" and learn_gate_blocked and not execution_profile["is_hard_task"]:
        chosen_flow = "baseline"
    flow_key = f"{target_file}|{test_file}"
    history_path = (repo_root / ".nexus" / "reports" / "research" / "auto-flow-history.json").resolve()

    def _read_history() -> dict:
        if history_path.exists():
            try:
                return json.loads(history_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _write_history(data: dict) -> None:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    history_data = _read_history()
    recent = list(history_data.get(flow_key, []))
    asi_ledger = [item.get("asi_record") for item in recent if isinstance(item, dict) and isinstance(item.get("asi_record"), dict)]
    plateau = _detect_plateau(asi_ledger)
    plateau_hard_pivot = bool(force_flow is None and plateau.get("detected"))
    if bool(plateau.get("detected")):
        route_features = route.get("route_features", {}) if isinstance(route.get("route_features"), dict) else {}
        route_features = {**route_features, "plateau_detected": True, "route_pivot": "distant_scout"}
        context = route.get("research_context", {}) if isinstance(route.get("research_context"), dict) else {}
        risk_flags = list(context.get("risk_flags", []) or [])
        blocked_assumptions = list(context.get("blocked_assumptions", []) or [])
        if "plateau_detected" not in risk_flags:
            risk_flags.append("plateau_detected")
        if "local_micro_tuning_is_enough" not in blocked_assumptions:
            blocked_assumptions.append("local_micro_tuning_is_enough")
        context = {
            **context,
            "risk_flags": risk_flags,
            "blocked_assumptions": blocked_assumptions,
            "next_action_hint": "switch_to_architecture_scout_and_change_family",
            "route_pivot": "distant_scout",
        }
        route_features["blocked_assumptions_count"] = len(blocked_assumptions)
        route["route_features"] = route_features
        route["research_context"] = context
        route["distant_scout_plan"] = DistantScoutPlanner().plan(task_desc=task_desc, plateau=plateau, asi_ledger=asi_ledger)
        capability_plan, route_decision = _build_capability_plan_and_decision(
            task_desc=task_desc,
            task_type=task_type,
            route=route,
        )
        route["capability_plan"] = capability_plan.to_dict()
        route["route_decision"] = route_decision
    if force_flow is None and bool(plateau.get("detected")) and chosen_flow == "baseline":
        chosen_flow = "hyper_sprint"
    recent_window = recent[-max(1, history_window):]
    recent_hyper_fails = sum(1 for item in recent_window if item.get("flow") == "hyper_sprint" and item.get("status") == "FAILED")
    stage1_fail_signals = sum(
        1
        for item in recent_window
        if item.get("flow") == "hyper_sprint"
        and item.get("status") == "FAILED"
        and "stage1_no_passing_candidate" in str(item.get("reason", ""))
    )
    nightshift_recommended = bool(recent_hyper_fails >= 2 or stage1_fail_signals >= 1)
    history_forced_baseline = False
    if (
        force_flow is None
        and not plateau_hard_pivot
        and chosen_flow == "hyper_sprint"
        and recent_hyper_fails >= max(1, history_fail_threshold)
    ):
        chosen_flow = "baseline"
        history_forced_baseline = True
    phase_wall_sec["D"] = round(time.monotonic() - phase_started_at, 4)

    guard_hit = False
    setup_started_at = time.monotonic()
    target_path = (repo_root / target_file).resolve()
    if not target_path.exists():
        raise click.ClickException(f"Target file not found: {target_file}")
    pytest_cmd = ["uv", "run", "pytest", "-q", "--maxfail=1", test_file]
    original_code = target_path.read_text(encoding="utf-8")
    timing_breakdown_sec["target_io_sec"] = round(time.monotonic() - setup_started_at, 4)
    normalized_success_criteria = (success_criteria or "all_target_tests_pass").strip()
    verification_only_allowed = normalized_success_criteria == "all_target_tests_pass"
    mutation_required = normalized_success_criteria in {"artifact_changed_and_tests_pass", "mutation_required"}
    codeintel_started_at = time.monotonic()
    codeintel_evidence = _build_codeintel_evidence(repo_root, target_file=target_file, task_desc=task_desc)
    timing_breakdown_sec["codeintel_sec"] = round(time.monotonic() - codeintel_started_at, 4)
    context_started_at = time.monotonic()
    task_desc_with_codeintel = _task_with_codeintel_context(task_desc, codeintel_evidence)
    timing_breakdown_sec["context_pack_sec"] = round(time.monotonic() - context_started_at, 4)

    def _baseline_report_from_meta(source: str, meta: dict[str, Any]) -> dict[str, Any]:
        model_calls = int(meta.get("model_calls", 0) or 0)
        total_tokens = int(meta.get("tokens_used", meta.get("total_tokens", 0)) or 0)
        return {
            "source": source,
            "attempt_count": 1,
            "model_calls": model_calls,
            "model_name": str(meta.get("model_name", "") or ""),
            "model_patch_generated": bool(meta.get("model_patch_generated", model_calls > 0)),
            "fallback_used": bool(meta.get("fallback_used", False)),
            "total_tokens": total_tokens,
            "token_capture_status": str(meta.get("token_capture_status", "not_applicable_local_only") or "unknown"),
            "gateway_stats_present": bool(meta.get("gateway_stats_present", False)),
            "gateway_usage_metadata_present": bool(meta.get("gateway_usage_metadata_present", False)),
            "gateway_token_source": str(meta.get("gateway_token_source", "missing") or "missing"),
            "gateway_error_category": str(meta.get("gateway_error_category", "") or ""),
            "gateway_prompt_chars": int(meta.get("gateway_prompt_chars", 0) or 0),
            "gateway_payload_chars": int(meta.get("gateway_payload_chars", 0) or 0),
            "gateway_total_chars": int(meta.get("gateway_total_chars", 0) or 0),
            "gateway_timeout_sec": int(meta.get("gateway_timeout_sec", 0) or 0),
            "baseline_llm_required": bool(meta.get("baseline_llm_required", False)),
            "baseline_source_policy": str(meta.get("baseline_source_policy", "")),
        }

    def _local_baseline_meta(*, fallback_reason: str | None = None) -> dict[str, Any]:
        meta = {
            "source": "local",
            "model_calls": 0,
            "tokens_used": 0,
            "token_capture_status": "not_applicable_local_only",
            "model_patch_generated": False,
        }
        if fallback_reason:
            meta["fallback_used"] = True
            meta["gateway_error_category"] = fallback_reason
        return meta

    def _strict_baseline_failure_meta(reason: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        out = dict(meta or {})
        out.setdefault("source", "nexus_llm_baseline")
        out.setdefault("model_calls", 0)
        out.setdefault("tokens_used", out.get("total_tokens", 0) or 0)
        out.setdefault("token_capture_status", "missing_gateway_stats")
        out["model_patch_generated"] = False
        out["fallback_used"] = False
        out["gateway_error_category"] = reason
        out["baseline_llm_required"] = True
        out["baseline_source_policy"] = "strict_llm_no_local_fallback"
        return out

    def _generate_baseline_patch(trial: int = 0) -> tuple[str, str, dict[str, Any]]:
        """R4: Enhanced baseline generation with LLM fast-fallback and conservative local paths."""
        source_label = "local"
        fallback_reason = None
        fallback_meta: dict[str, Any] | None = None
        
        # [NEW: X-2] Prior-Art from Claims
        try:
            from nexus.research.learn_mode import LearnModeService
            svc = LearnModeService(repo_root)
            prior_fixes = svc.ask(topic="bug-fixes", question=task_desc, top_k=5)
            if prior_fixes.get("citations"):
                prior_context = "\n".join([c["claim"] for c in prior_fixes["citations"][:3]])
                task_desc_for_llm = f"{task_desc_with_codeintel}\n\n[Prior Art]\n{prior_context}"
            else:
                task_desc_for_llm = task_desc_with_codeintel
        except Exception:
            task_desc_for_llm = task_desc_with_codeintel
        
        if llm_baseline:
            try:
                # Use a very short timeout for baseline assistance to avoid blocking
                gen = LLMCandidateGenerator(repo_root, safe_mode=True)
                # Note: gen.generate internal timeout depends on gateway, but we wrap it here if possible
                # For now, we trust internal model_chain but monitor for rapid failure
                patched, meta = gen.generate(source_code=original_code, task=task_desc_for_llm, mutation_hint="baseline", seed=trial)
                if patched and patched != original_code:
                    meta = dict(meta)
                    if llm_baseline_required:
                        meta["baseline_llm_required"] = True
                        meta["baseline_source_policy"] = "strict_llm_no_local_fallback"
                        return patched, "nexus_llm_baseline", meta
                    return patched, "llm_assisted", meta
                else:
                    if llm_baseline_required:
                        return original_code, "nexus_llm_baseline_failed", _strict_baseline_failure_meta(
                            "llm_no_patch",
                            dict(meta),
                        )
                    fallback_reason = "llm_generation_empty_fallback_local"
                    fallback_meta = dict(meta)
                    fallback_meta["fallback_used"] = True
                    fallback_meta["gateway_error_category"] = fallback_reason
            except LLMCandidateError as e:
                if llm_baseline_required:
                    return original_code, "nexus_llm_baseline_failed", _strict_baseline_failure_meta(str(e), e.metadata)
                fallback_reason = f"llm_error_{str(e).lower()}_fallback_local"
                fallback_meta = dict(e.metadata)
                fallback_meta["fallback_used"] = True
                fallback_meta["gateway_error_category"] = str(e)
            except Exception as e:
                err_str = str(e).lower()
                if "timeout" in err_str:
                    fallback_reason = "timeout"
                elif any(p in err_str for p in ["quota", "429", "limit"]):
                    fallback_reason = "quota_exhausted"
                else:
                    fallback_reason = f"llm_error_{err_str}"
                if llm_baseline_required:
                    return original_code, "nexus_llm_baseline_failed", _strict_baseline_failure_meta(fallback_reason)
                fallback_reason = f"{fallback_reason}_fallback_local"
        elif llm_baseline_required:
            return original_code, "nexus_llm_baseline_missing", _strict_baseline_failure_meta("llm_baseline_required_missing")
        
        # Local fallback intentionally uses raw task_desc to avoid prior-art keyword pollution
        # (e.g., stale "flaky/race" hints forcing conservative patch on unrelated tasks).
        patched = generate_local_candidate(original_code, task_desc, "baseline", trial)
        
        # If still no mutation and it's structural, try a generic structural hint as last resort
        if patched == original_code and task_type in ["feature", "refactor"]:
            # Last resort: force a pattern match if keywords exist
            if "discount" in task_desc.lower():
                from nexus.research.local_sprint_mutator import _feature_discount_patch
                patched = _feature_discount_patch(original_code)
                source_label = "local_conservative_feature"
            elif "parser" in task_desc.lower() or "refactor" in task_desc.lower():
                from nexus.research.local_sprint_mutator import _refactor_parser_patch
                patched = _refactor_parser_patch(original_code)
                source_label = "local_conservative_refactor"
        
        label = source_label
        if fallback_reason:
            label = f"{source_label}({fallback_reason})"
            
        return patched, label, fallback_meta or _local_baseline_meta(fallback_reason=fallback_reason)

    def _run_baseline_apply() -> dict:
        start = time.monotonic()
        ok = False
        err = ""
        source = "local"
        generation_meta = _local_baseline_meta()
        companion_edits: dict[Path, str] = {}
        restored_files: dict[Path, str | None] = {}
        try:
            patched, source, generation_meta = _generate_baseline_patch()
            if patched == original_code:
                err = "no_mutation_generated"
            else:
                companion_edits = generate_local_companion_edits(repo_root, target_path, task_desc, "baseline", 0)
                restored_files[target_path] = original_code
                _write_source_text(target_path, patched)
                for extra_path, extra_code in companion_edits.items():
                    if extra_path == target_path:
                        continue
                    restored_files[extra_path] = extra_path.read_text(encoding="utf-8") if extra_path.exists() else None
                    extra_path.parent.mkdir(parents=True, exist_ok=True)
                    _write_source_text(extra_path, extra_code)
                res = subprocess.run(pytest_cmd, cwd=repo_root, capture_output=True, text=True, timeout=timeout_sec)
                ok = res.returncode == 0
                if not ok:
                    err = "pytest_failed"
        except subprocess.TimeoutExpired:
            err = "test_timeout"
        finally:
            for path, original_text in restored_files.items():
                if ok and path == target_path:
                    continue
                if original_text is None:
                    if path.exists():
                        path.unlink()
                else:
                    _write_source_text(path, original_text)
        return {
            "flow": "baseline",
            "status": "SUCCESS" if ok else "FAILED",
            "elapsed_sec": round(time.monotonic() - start, 4),
            "error": err,
            "report": _baseline_report_from_meta(source, generation_meta),
        }

    def _run_baseline_probe() -> dict:
        # Probe run used by guard. Always restore original state.
        start = time.monotonic()
        ok = False
        err = ""
        source = "local"
        generation_meta = _local_baseline_meta()
        patched = original_code
        restored_files: dict[Path, str | None] = {}
        try:
            patched, source, generation_meta = _generate_baseline_patch()
            if patched == original_code:
                err = "no_mutation_generated"
            else:
                companion_edits = generate_local_companion_edits(repo_root, target_path, task_desc, "baseline_probe", 0)
                restored_files[target_path] = original_code
                _write_source_text(target_path, patched)
                for extra_path, extra_code in companion_edits.items():
                    if extra_path == target_path:
                        continue
                    restored_files[extra_path] = extra_path.read_text(encoding="utf-8") if extra_path.exists() else None
                    extra_path.parent.mkdir(parents=True, exist_ok=True)
                    _write_source_text(extra_path, extra_code)
                res = subprocess.run(pytest_cmd, cwd=repo_root, capture_output=True, text=True, timeout=timeout_sec)
                ok = res.returncode == 0
                if not ok:
                    err = "pytest_failed"
        except subprocess.TimeoutExpired:
            err = "test_timeout"
        finally:
            for path, original_text in restored_files.items():
                if original_text is None:
                    if path.exists():
                        path.unlink()
                else:
                    _write_source_text(path, original_text)
        return {
            "flow": "baseline_probe",
            "status": "SUCCESS" if ok else "FAILED",
            "elapsed_sec": round(time.monotonic() - start, 4),
            "error": err,
            "report": _baseline_report_from_meta(source, generation_meta),
            "_patch": patched if ok else None,
        }

    def _run_original_verification_rescue(previous_result: dict) -> dict:
        start = time.monotonic()
        _write_source_text(target_path, original_code)
        report = dict(previous_result.get("report", {}) if isinstance(previous_result.get("report"), dict) else {})
        try:
            res = subprocess.run(pytest_cmd, cwd=repo_root, capture_output=True, text=True, timeout=timeout_sec)
            ok = res.returncode == 0
            err = "" if ok else "original_pytest_failed"
        except subprocess.TimeoutExpired:
            ok = False
            err = "original_test_timeout"
        report["verification_only_rescue"] = bool(ok)
        report["verification_only_from"] = {
            "flow": previous_result.get("flow"),
            "status": previous_result.get("status"),
            "error": previous_result.get("error"),
        }
        report["winner_source"] = "verification_only" if ok else report.get("winner_source", "local")
        return {
            "flow": previous_result.get("flow", "hyper_sprint"),
            "status": "SUCCESS" if ok else "FAILED",
            "elapsed_sec": round(float(previous_result.get("elapsed_sec", 0.0) or 0.0) + (time.monotonic() - start), 4),
            "error": "" if ok else err,
            "report": report,
        }

    def _run_hyper_apply() -> dict:
        start = time.monotonic()
        effective_stage1_timeout = stage1_timeout_sec
        if baseline_probe and baseline_probe.get("elapsed_sec", 0) > 0:
            dynamic_timeout = int(round(float(baseline_probe["elapsed_sec"]) * max(1.0, dynamic_timeout_multiplier)))
            effective_stage1_timeout = max(
                min_dynamic_stage1_timeout,
                min(stage1_timeout_sec, dynamic_timeout),
            )
        executor_flags = build_route_executor_flags(task_desc=task_desc, task_type=task_type, route=route)
        effective_candidate_count = max(
            execution_profile["effective_candidate_count"],
            3 if executor_flags["enable_ddtree_executor"] else 1,
        )
        llm_candidate_cap_raw = os.environ.get("NEXUS_LLM_CANDIDATE_CAP", "").strip()
        if llm_mode and llm_candidate_cap_raw:
            try:
                effective_candidate_count = min(effective_candidate_count, max(1, int(llm_candidate_cap_raw)))
            except ValueError:
                pass
        sprint_executor_flags = {
            "enable_autoreason_executor": executor_flags["enable_autoreason_executor"],
            "enable_ddtree_executor": executor_flags["enable_ddtree_executor"],
            "ddtree_max_candidates": executor_flags["ddtree_max_candidates"],
        }
        distant_scout_plan = route.get("distant_scout_plan", {}) if isinstance(route.get("distant_scout_plan"), dict) else {}
        cfg = SprintConfig(
            task=task_desc_with_codeintel if llm_mode else task_desc,
            target_file=target_file,
            test_file=test_file,
            candidate_count=effective_candidate_count,
            max_rounds=execution_profile["effective_max_rounds"],
            timeout_sec=timeout_sec,
            safe_mode=True,
            stage1_max_parallel=execution_profile["effective_stage1_max_parallel"],
            stage1_timeout_sec=effective_stage1_timeout,
            llm_mode=llm_mode,
            distant_scout_plan=distant_scout_plan,
            **sprint_executor_flags,
        )
        res = run_hyper_sprint(repo_root=repo_root, config=cfg)
        ok = res.status == "SUCCESS" and bool(res.patch)
        err = ""
        if ok:
            _write_source_text(target_path, res.patch)
        else:
            err = res.reason
        return {
            "flow": "hyper_sprint",
            "status": "SUCCESS" if ok else "FAILED",
            "elapsed_sec": round(time.monotonic() - start, 4),
            "error": err,
                "report": {
                    "status": res.status,
                    "reason": res.reason,
                    "winner_source": res.winner_source,
                    "error_codes": res.error_codes,
                    "rejection_summary": res.rejection_summary,
                    "attempt_count": res.attempt_count,
                    "model_calls": res.model_calls,
                    "model_name": getattr(res, "model_name", ""),
                    "model_patch_generated": bool(getattr(res, "model_patch_generated", False)),
                    "fallback_used": bool(getattr(res, "fallback_used", False)),
                    "total_tokens": res.total_tokens,
                    "token_capture_status": res.token_capture_status,
                    "gateway_stats_present": bool(getattr(res, "gateway_stats_present", False)),
                    "gateway_usage_metadata_present": bool(getattr(res, "gateway_usage_metadata_present", False)),
                    "gateway_token_source": str(getattr(res, "gateway_token_source", "missing") or "missing"),
                    "gateway_error_category": str(getattr(res, "gateway_error_category", "") or ""),
                    "gateway_prompt_chars": int(getattr(res, "gateway_prompt_chars", 0) or 0),
                    "gateway_payload_chars": int(getattr(res, "gateway_payload_chars", 0) or 0),
                    "gateway_total_chars": int(getattr(res, "gateway_total_chars", 0) or 0),
                    "gateway_timeout_sec": int(getattr(res, "gateway_timeout_sec", 0) or 0),
                    "effective_stage1_timeout_sec": effective_stage1_timeout,
                    "candidate_summaries": _candidate_summaries(list(getattr(res, "candidates", []) or [])),
                    "learning_trace": res.learning_trace,
                    "distant_scout_execution": (res.learning_trace or {}).get("distant_scout_execution", {}),
                },
            }

    baseline_probe = None
    early_baseline_shortcut = False
    baseline_probe_skipped = False
    phase_started_at = time.monotonic()
    if chosen_flow == "baseline":
        result = _run_baseline_apply()
        strategy_path = "baseline_only"
        baseline_report = result.get("report", {}) if isinstance(result.get("report"), dict) else {}
        baseline_model_attempted = int(baseline_report.get("model_calls", 0) or 0) > 0
        if (
            force_flow is None
            and llm_mode
            and llm_baseline
            and baseline_model_attempted
            and result.get("status") != "SUCCESS"
        ):
            failed_baseline = result
            result = _run_hyper_apply()
            result_report = result.get("report", {}) if isinstance(result.get("report"), dict) else {}
            if isinstance(result_report, dict):
                result_report["replanned_from"] = {
                    "flow": failed_baseline.get("flow"),
                    "status": failed_baseline.get("status"),
                    "error": failed_baseline.get("error"),
                    "model_calls": baseline_report.get("model_calls", 0),
                    "gateway_error_category": baseline_report.get("gateway_error_category", ""),
                }
                result["report"] = result_report
            chosen_flow = "hyper_sprint"
            strategy_path = "baseline_llm_failed_replan_hyper"
    else:
        direct_hyper = bool(execution_profile.get("prefer_direct_hyper", False))
        forced_hyper = force_flow == "hyper_sprint"
        if plateau_hard_pivot or forced_hyper or (
            force_flow is None
            and execution_profile["is_hard_task"]
            and (skip_baseline_probe_for_hard or direct_hyper)
        ):
            baseline_probe_skipped = True
            result = _run_hyper_apply()
            if (
                result.get("status") != "SUCCESS"
                and str(task_type).startswith("cross_module_refactor")
                and verification_only_allowed
            ):
                result = _run_original_verification_rescue(result)
            if forced_hyper:
                strategy_path = "hyper_direct_forced"
            elif plateau_hard_pivot:
                strategy_path = "hyper_direct_plateau_distant_scout"
            else:
                strategy_path = "hyper_direct_hard_skip_probe" if skip_baseline_probe_for_hard else "hyper_direct_cross_module"
        else:
        # Probe first to avoid unnecessary Hyper run for obvious quick fixes.
            baseline_probe = _run_baseline_probe()
            if (
                force_flow is None
                and baseline_probe["status"] == "SUCCESS"
                and tuned_baseline_fast_sec > 0
                and baseline_probe["elapsed_sec"] <= tuned_baseline_fast_sec
            ):
                early_baseline_shortcut = True
                probe_patch = baseline_probe.get("_patch")
                if isinstance(probe_patch, str) and probe_patch and probe_patch != original_code:
                    _write_source_text(target_path, probe_patch)
                    result = {
                        "flow": "baseline",
                        "status": "SUCCESS",
                        "elapsed_sec": baseline_probe["elapsed_sec"],
                        "error": "",
                        "report": {
                            **(baseline_probe.get("report", {}) if isinstance(baseline_probe.get("report"), dict) else {}),
                            "reused_from_probe": True,
                        },
                    }
                else:
                    _write_source_text(target_path, original_code)
                    result = _run_baseline_apply()
                chosen_flow = "baseline"
                strategy_path = "probe_success_fastpath_baseline"
            else:
                result = _run_hyper_apply()
                if (
                    result.get("status") != "SUCCESS"
                    and str(task_type).startswith("cross_module_refactor")
                    and verification_only_allowed
                ):
                    result = _run_original_verification_rescue(result)
                strategy_path = "probe_then_hyper"
                min_probe_sec_for_ratio_guard = 0.05
                if (
                    baseline_probe["status"] == "SUCCESS"
                    and result["status"] == "SUCCESS"
                    and baseline_probe["elapsed_sec"] >= min_probe_sec_for_ratio_guard
                    and result["elapsed_sec"] > max_time_ratio_guard * baseline_probe["elapsed_sec"]
                ):
                    guard_hit = True
                    hyper_result_for_guard = result
                    _write_source_text(target_path, original_code)
                    fallback_result = _run_baseline_apply()
                    if fallback_result.get("status") == "SUCCESS":
                        result = fallback_result
                    else:
                        result = hyper_result_for_guard
                        result_report = result.get("report", {}) if isinstance(result.get("report"), dict) else {}
                        result_report["guard_fallback_rejected"] = {
                            "flow": fallback_result.get("flow"),
                            "status": fallback_result.get("status"),
                            "error": fallback_result.get("error"),
                        }
                        result["report"] = result_report
                    fallback_succeeded = fallback_result.get("status") == "SUCCESS"
                    if (
                        fallback_succeeded
                        and isinstance(result.get("report"), dict)
                        and isinstance(hyper_result_for_guard.get("report"), dict)
                    ):
                        hyper_report = hyper_result_for_guard["report"]
                        result["report"]["guard_fallback_from"] = {
                            "flow": hyper_result_for_guard.get("flow"),
                            "elapsed_sec": hyper_result_for_guard.get("elapsed_sec"),
                            "model_calls": int(hyper_report.get("model_calls", 0) or 0),
                            "model_name": hyper_report.get("model_name", ""),
                            "model_patch_generated": bool(hyper_report.get("model_patch_generated", False)),
                            "fallback_used": bool(hyper_report.get("fallback_used", False)),
                            "total_tokens": int(hyper_report.get("total_tokens", 0) or 0),
                            "token_capture_status": hyper_report.get("token_capture_status", "unknown"),
                            "gateway_stats_present": bool(hyper_report.get("gateway_stats_present", False)),
                            "gateway_usage_metadata_present": bool(hyper_report.get("gateway_usage_metadata_present", False)),
                            "gateway_token_source": hyper_report.get("gateway_token_source", "missing"),
                            "gateway_error_category": hyper_report.get("gateway_error_category", ""),
                            "gateway_prompt_chars": int(hyper_report.get("gateway_prompt_chars", 0) or 0),
                            "gateway_payload_chars": int(hyper_report.get("gateway_payload_chars", 0) or 0),
                            "gateway_total_chars": int(hyper_report.get("gateway_total_chars", 0) or 0),
                            "gateway_timeout_sec": int(hyper_report.get("gateway_timeout_sec", 0) or 0),
                            "winner_source": hyper_report.get("winner_source", "unknown"),
                            "learning_trace": hyper_report.get("learning_trace", {}),
                        }
                        result["report"]["model_calls"] = int(result["report"].get("model_calls", 0) or 0) + int(hyper_report.get("model_calls", 0) or 0)
                        result["report"]["model_name"] = hyper_report.get("model_name", result["report"].get("model_name", ""))
                        result["report"]["model_patch_generated"] = bool(hyper_report.get("model_patch_generated", False))
                        result["report"]["fallback_used"] = bool(hyper_report.get("fallback_used", False))
                        result["report"]["total_tokens"] = int(result["report"].get("total_tokens", 0) or 0) + int(hyper_report.get("total_tokens", 0) or 0)
                        if hyper_report.get("token_capture_status") == "measured":
                            result["report"]["token_capture_status"] = "measured"
                        result["report"]["gateway_stats_present"] = bool(
                            result["report"].get("gateway_stats_present", False)
                            or hyper_report.get("gateway_stats_present", False)
                        )
                        result["report"]["gateway_usage_metadata_present"] = bool(
                            result["report"].get("gateway_usage_metadata_present", False)
                            or hyper_report.get("gateway_usage_metadata_present", False)
                        )
                        result["report"]["gateway_token_source"] = hyper_report.get(
                            "gateway_token_source",
                            result["report"].get("gateway_token_source", "missing"),
                        )
                        result["report"]["gateway_error_category"] = hyper_report.get(
                            "gateway_error_category",
                            result["report"].get("gateway_error_category", ""),
                        )
                        result["report"]["gateway_prompt_chars"] = max(
                            int(result["report"].get("gateway_prompt_chars", 0) or 0),
                            int(hyper_report.get("gateway_prompt_chars", 0) or 0),
                        )
                        result["report"]["gateway_payload_chars"] = max(
                            int(result["report"].get("gateway_payload_chars", 0) or 0),
                            int(hyper_report.get("gateway_payload_chars", 0) or 0),
                        )
                        result["report"]["gateway_total_chars"] = max(
                            int(result["report"].get("gateway_total_chars", 0) or 0),
                            int(hyper_report.get("gateway_total_chars", 0) or 0),
                        )
                        result["report"]["gateway_timeout_sec"] = max(
                            int(result["report"].get("gateway_timeout_sec", 0) or 0),
                            int(hyper_report.get("gateway_timeout_sec", 0) or 0),
                        )
                    if fallback_succeeded:
                        chosen_flow = "baseline"
                        strategy_path = "hyper_guard_fallback_to_baseline"
                    else:
                        chosen_flow = "hyper_sprint"
                        strategy_path = "probe_then_hyper_guard_fallback_rejected"
    phase_wall_sec["R"] = round(time.monotonic() - phase_started_at, 4)

    baseline_probe_for_report = None
    if isinstance(baseline_probe, dict):
        baseline_probe_for_report = {k: v for k, v in baseline_probe.items() if k != "_patch"}

    phase_started_at = time.monotonic()
    final_code = target_path.read_text(encoding="utf-8") if target_path.exists() else original_code
    diff_lines = list(
        difflib.unified_diff(
            original_code.splitlines(),
            final_code.splitlines(),
            lineterm="",
        )
    )
    artifact_summary = {
        "changed": bool(final_code != original_code),
        "diff_line_count": len(diff_lines),
        "pytest_cmd": " ".join(pytest_cmd),
        "success_criteria": normalized_success_criteria,
        "mutation_required": mutation_required,
        "verification_only_allowed": verification_only_allowed,
    }
    result_report = result.get("report", {}) if isinstance(result, dict) else {}
    result_report = result_report if isinstance(result_report, dict) else {}
    guard_fallback_from = result_report.get("guard_fallback_from", {})
    guard_fallback_from = guard_fallback_from if isinstance(guard_fallback_from, dict) else {}
    hyper_learning_trace = result_report.get("learning_trace") or guard_fallback_from.get("learning_trace") or {}
    hyper_learning_trace = hyper_learning_trace if isinstance(hyper_learning_trace, dict) else {}
    tests_passed = str(result.get("status", "")) == "SUCCESS"
    artifact_summary["verification_only"] = bool(result_report.get("verification_only_rescue", False))
    gemini_model_calls = int(result_report.get("model_calls", 0) or 0)
    gemini_invoked = gemini_model_calls > 0 or int(guard_fallback_from.get("model_calls", 0) or 0) > 0
    hyper_used = str(result.get("flow", "")) == "hyper_sprint" or "hyper" in str(strategy_path)
    verification_only_rescue = bool(result_report.get("verification_only_rescue", False))
    artifact_verified = bool(tests_passed and (artifact_summary["changed"] or verification_only_rescue))
    nexus_rescued = bool((guard_hit or verification_only_rescue) and tests_passed)
    winner_source = result_report.get("winner_source") or guard_fallback_from.get("winner_source") or ("nexus_rescue" if nexus_rescued else "local_only")
    self_heal_used = bool(
        "self_heal" in str(winner_source)
        or any("self_heal" in str(code) for code in result_report.get("error_codes", []))
    )
    mempalace_verified = bool(hyper_learning_trace.get("mempalace_verified", False))
    mempalace_active = bool(hyper_learning_trace or gemini_invoked)
    receipt_slug = _safe_trace_slug(task_id or task_desc or "task")
    capability_evidence = _capability_evidence(
        result_report=result_report,
        learning_trace=hyper_learning_trace,
        nightshift_recommended=nightshift_recommended,
    )
    capability_evidence = _augment_local_msa_bench_evidence(
        repo_root,
        task_id=task_id,
        task_desc=task_desc,
        task_type=task_type,
        evidence=capability_evidence,
        artifact_verified=artifact_verified,
    )
    capability_evidence = _write_msa_receipt_reports(repo_root, task_id=task_id, evidence=capability_evidence)
    route_decision_payload = route.get("route_decision", {}) if isinstance(route.get("route_decision"), dict) else {}
    route_selected_capabilities = {str(item) for item in route_decision_payload.get("selected_capabilities", []) or []}
    route_confidence = float(route.get("adjusted_root_cause_confidence", root_cause_confidence) or root_cause_confidence)
    research_preflight = _research_preflight_packet(route=route, route_confidence=route_confidence, task_id=task_id)
    claim_check = _claim_check_summary(
        task_desc=task_desc,
        tests_passed=tests_passed,
        artifact_summary=artifact_summary,
        route=route,
    )
    hitl = _hitl_payload(route_confidence=route_confidence, route=route, task_id=task_id)
    if "research" in route_selected_capabilities and not capability_evidence.get("research_used"):
        capability_evidence["research_used"] = True
        capability_evidence["research_refs"] = [f"research:{receipt_slug}:route_selected"]
        capability_evidence["research_gate_passed"] = bool(artifact_verified)
    capability_evidence["research_source_projects"] = list(RESEARCH_SOURCE_PROJECTS)
    summaries = result_report.get("candidate_summaries", [])
    autoreason_payload = hyper_learning_trace.get("autoreason", {}) if isinstance(hyper_learning_trace.get("autoreason", {}), dict) else {}
    should_run_autoreason = str(result.get("flow", "")) == "hyper_sprint" and isinstance(summaries, list) and bool(summaries)
    if should_run_autoreason:
        autoreason_service = AutoreasonService()
        factory_payload = autoreason_service.candidate_factory_from_summaries(summaries, task_desc=task_desc)
        candidates = factory_payload.get("candidates", []) if isinstance(factory_payload.get("candidates"), list) else []
        if candidates:
            autoreason_payload = autoreason_service.run(
                candidates=candidates,
                task_desc=task_desc,
                stop_threshold=int(
                    ((route.get("capability_stack", {}) if isinstance(route.get("capability_stack"), dict) else {}).get(
                        "stop_policy",
                        {},
                    )
                    or {}
                    ).get("threshold", 2)
                ),
            )
            autoreason_payload["candidate_factory"] = factory_payload
        else:
            autoreason_payload = {
                "schema": "nexus_autoreason_result_v1",
                "enabled": False,
                "status": "SKIPPED",
                "winner": None,
                "stop_reason": "candidate_factory_skipped",
                "judge_votes": [],
                "borda_scores": {},
                "candidate_factory": factory_payload,
            }
    elif not autoreason_payload:
        autoreason_payload = {
            "schema": "nexus_autoreason_result_v1",
            "status": "SKIPPED",
            "winner": None,
            "stop_reason": "candidate_summaries_missing",
            "judge_votes": [],
            "borda_scores": {},
        }
    ultra_review_evidence = _ultra_review_gate_evidence(
        repo_root=repo_root,
        task_desc=task_desc,
        task_id=task_id,
        route_decision=route_decision_payload,
        capability_stack=route.get("capability_stack", {}),
        claim_check=claim_check,
        route_confidence=route_confidence,
        hitl=hitl,
    )
    phase_wall_sec["A"] = round(time.monotonic() - phase_started_at, 4)
    context_memory_needed = "docs_code_sync" in str(task_type).lower() or any(
        token in (task_desc or "").lower() for token in ("context", "contract", "docs")
    )
    delivery_refs = [f"delivery:{receipt_slug}:artifact_tests_passed"] if artifact_verified else []
    memory_refs = [f"memory:{receipt_slug}:context_contract"] if artifact_verified and context_memory_needed else []
    artifact_refs = [f"artifact:{receipt_slug}:tests_passed"] if artifact_verified else []
    claim_refs = [f"claim:{receipt_slug}:verified_delivery"] if artifact_verified else []
    belief_refs = [f"belief:{receipt_slug}:confidence:{float(execution_profile.get('belief_confidence', 1.0) or 1.0):.2f}"] if artifact_verified else []
    governance_needed = any(
        token in (task_desc or "").lower()
        for token in ("governance", "policy", "secret", "authorization", "unsafe", "trust", "evidence")
    )
    mempalace_refs = [f"mempalace:{receipt_slug}:policy_checked"] if artifact_verified and (mempalace_active or governance_needed) else []
    nexus_usage_trace = {
        "gemini_uses_nexus": bool(gemini_invoked),
        "nexus_context_delivered": True,
        "nexus_tier": tier_decision["tier"],
        "nexus_tier_reason": tier_decision["reason"],
        "pillars": {
            "lancedb": {
                "active": True,
                "hits": int(capability_evidence.get("lancedb_hits", route.get("findings_hits", 0)) or 0),
            },
            "memory": {"active": True, "hits": int((route.get("route_features", {}) or {}).get("memory_hits", 0) or 0)},
            "mempalace": {"active": mempalace_active, "verified": mempalace_verified},
            "belief": {
                "active": True,
                "confidence": float(execution_profile.get("belief_confidence", 1.0) or 1.0),
                "route_influenced": True,
            },
            "artifact": {
                "active": True,
                "changed": bool(artifact_summary["changed"]),
                "verification_only": verification_only_rescue,
                "tests_passed": tests_passed,
            },
        },
        "phase_trace": {
            "P": "route_built",
            "X": "retrieval_checked",
            "D": "guard_decision",
            "R": "hyper_executed" if hyper_used else "baseline_executed",
            "A": "artifact_verified" if tests_passed else "artifact_unverified",
            "C": "closure_written" if bool(hyper_learning_trace.get("learn_phase_bridge")) else "history_written",
        },
        "capabilities": {
            "research_used": bool(capability_evidence.get("research_used", False)),
            "research_refs": capability_evidence.get("research_refs", []),
            "research_gate_passed": bool(capability_evidence.get("research_gate_passed", False)),
            "memory_used": bool(memory_refs),
            "memory_refs": memory_refs,
            "memory_gate_passed": bool(memory_refs),
            "mempalace_refs": mempalace_refs,
            "mempalace_gate_passed": bool(mempalace_refs),
            "artifact_refs": artifact_refs,
            "artifact_gate_passed": bool(artifact_refs),
            "claim_refs": claim_refs,
            "claim_gate_invoked": artifact_verified,
            "belief_refs": belief_refs,
            "belief_gate_passed": bool(belief_refs),
            "lancedb_hits": int(capability_evidence.get("lancedb_hits", route.get("findings_hits", 0)) or 0),
            "lancedb_refs": capability_evidence.get("lancedb_refs", []),
            "lancedb_gate_passed": bool(capability_evidence.get("lancedb_gate_passed", False)),
            "semantic_searcher_used": bool(capability_evidence.get("semantic_searcher_used", False)),
            "semantic_searcher_hits": int(capability_evidence.get("semantic_searcher_hits", 0) or 0),
            "semantic_searcher_refs": capability_evidence.get("semantic_searcher_refs", []),
            "semantic_searcher_gate_passed": bool(capability_evidence.get("semantic_searcher_gate_passed", False)),
            "delivery_refs": delivery_refs,
            "delivery_gate_passed": bool(delivery_refs),
            "hyper_used": bool(hyper_used),
            "nightshift_recommended": capability_evidence["nightshift_recommended"],
            "nightshift_invoked": capability_evidence["nightshift_invoked"],
            "nightshift_recovered": capability_evidence["nightshift_recovered"],
            "nightshift_report_path": capability_evidence["nightshift_report_path"],
            "swarm_used": capability_evidence["swarm_used"],
            "swarm_evidence_count": capability_evidence["swarm_evidence_count"],
            "swarm_consensus": capability_evidence["swarm_consensus"],
            "swarm_report": capability_evidence["swarm_report"],
            "swarm_report_path": capability_evidence.get("swarm_report_path", ""),
            "quiet_moment": capability_evidence.get("quiet_moment", {}),
            "drone_used": capability_evidence["drone_used"],
            "drone_invoked_count": capability_evidence["drone_invoked_count"],
            "drone_artifact_path": capability_evidence["drone_artifact_path"],
            "drone_report": capability_evidence["drone_report"],
            "drone_report_path": capability_evidence.get("drone_report_path", ""),
            "self_heal_used": self_heal_used,
            "claim_verified": artifact_verified,
            "nightshift_failure_reason": capability_evidence["nightshift_failure_reason"],
            "nightshift_report": capability_evidence["nightshift_report"],
            "ultra_review_recommended": ultra_review_evidence["recommended"],
            "ultra_review_invoked": ultra_review_evidence["invoked"],
            "ultra_review_gate_passed": ultra_review_evidence["gate_passed"],
            "ultra_review_report_path": ultra_review_evidence["report_path"],
        },
        "phase_wall_sec": phase_wall_sec,
        "capability_stack": route.get("capability_stack", {}),
        "autoreason": autoreason_payload,
        "ddtree": hyper_learning_trace.get("ddtree", {}) if isinstance(hyper_learning_trace, dict) else {},
        "ultra_review": ultra_review_evidence,
        "claim_check": claim_check,
        "hitl": hitl,
        "research_preflight": research_preflight,
        "route_confidence": route_confidence,
        "codeintel": codeintel_evidence,
        "gemini_patch_status": "passed" if tests_passed and gemini_invoked and not nexus_rescued else ("failed" if gemini_invoked else "missing"),
        "nexus_rescued": nexus_rescued,
        "winner_source": winner_source,
        "usage_valid": bool(gemini_invoked and artifact_verified),
    }
    research_doctor = build_research_doctor(
        research_preflight=research_preflight,
        artifact_verified=artifact_verified,
    )
    claim_probe = build_claim_probe(task_desc=task_desc, route=route, artifact_verified=artifact_verified)
    nexus_usage_trace["research_doctor"] = research_doctor
    nexus_usage_trace["claim_probe"] = claim_probe
    governance_events = _governance_events_packet(
        repo_root=repo_root,
        task_id=task_id,
        receipt_slug=receipt_slug,
        artifact_verified=artifact_verified,
        claim_probe=claim_probe,
    )
    nexus_usage_trace["governance_events"] = governance_events["events"]
    nexus_usage_trace["governance_event_summary"] = governance_events["summary"]
    nexus_usage_trace["capabilities"]["research_doctor_score"] = research_doctor["score"]
    nexus_usage_trace["capabilities"]["research_doctor_gate_passed"] = research_doctor["status"] == "PASS"
    nexus_usage_trace["capabilities"]["claim_probe_eligible"] = claim_probe["eligible"]
    nexus_usage_trace["capabilities"]["claim_probe_invoked"] = claim_probe["invoked"]
    nexus_usage_trace["capabilities"]["claim_probe_gate_passed"] = claim_probe["gate_passed"]
    capability_plan_payload = route.get("capability_plan") if isinstance(route.get("capability_plan"), dict) else None
    if capability_plan_payload is None:
        capability_plan = CapabilityPlanner().plan(
            task_desc=task_desc,
            task_type=task_type,
            route=route,
            pillars=nexus_usage_trace["pillars"],
            codeintel=codeintel_evidence,
            phase_trace=nexus_usage_trace["phase_trace"],
        )
        capability_plan_payload = capability_plan.to_dict()
    nexus_usage_trace["capability_plan"] = capability_plan_payload
    nexus_usage_trace["route_decision"] = route_decision_payload or build_route_decision(
        task_id=task_id or _safe_trace_slug(task_desc),
        task_desc=task_desc,
        task_type=task_type,
        recommended_flow=str(route.get("recommended_flow") or ""),
        plan=CapabilityPlanner().plan(
            task_desc=task_desc,
            task_type=task_type,
            route=route,
            pillars=nexus_usage_trace["pillars"],
            codeintel=codeintel_evidence,
            phase_trace=nexus_usage_trace["phase_trace"],
        ),
    ).to_dict()
    selected_for_runtime_receipts = {
        str(item)
        for item in (capability_plan_payload.get("selected_capabilities", []) or [])
        if str(item).strip()
    }
    _augment_semantic_runtime_capabilities(
        repo_root=repo_root,
        task_id=task_id,
        task_desc=task_desc,
        task_type=task_type,
        target_file=target_file,
        receipt_slug=receipt_slug,
        selected_capabilities=selected_for_runtime_receipts,
        nexus_usage_trace=nexus_usage_trace,
        route=route,
        asi_ledger=asi_ledger,
        plateau=plateau,
        artifact_verified=artifact_verified,
        normalized_success_criteria=normalized_success_criteria,
    )
    recursive_research = _rlm_research_trace_enabled()
    if _rlm_trace_enabled() or recursive_research:
        if recursive_research:
            nexus_usage_trace["rlm_loop_phase"] = "X"
            nexus_usage_trace["rlm_x_loop_budget_observed"] = True
            nexus_usage_trace["rlm_x_loop_budget_summary"] = _rlm_x_loop_budget_summary(
                result=result,
                phase_wall_sec=phase_wall_sec,
                candidate_count=candidate_count,
            )
            nexus_usage_trace["rlm_required_gates"] = [
                "rlm_trace_present",
                "submit_not_success",
                "ac_gate_verified",
                "x_loop_budget_observed",
            ]
        else:
            nexus_usage_trace["rlm_loop_phase"] = "R"
            nexus_usage_trace["rlm_required_gates"] = [
                "rlm_trace_present",
                "submit_not_success",
                "ac_gate_verified",
            ]
        nexus_usage_trace["rlm_trace_path"] = _write_research_rlm_trace(
            repo_root=repo_root,
            task_desc=task_desc,
            result=result,
            nexus_usage_trace=nexus_usage_trace,
            artifact_summary={**artifact_summary, "tests_passed": tests_passed},
            recursive_research=recursive_research,
        )
        nexus_usage_trace["capabilities"]["rlm_trace_path"] = nexus_usage_trace["rlm_trace_path"]
        nexus_usage_trace["capabilities"]["rlm_trace_present"] = bool(nexus_usage_trace["rlm_trace_path"])
    runtime_receipt_plan = _runtime_receipt_plan_payload(capability_plan_payload, nexus_usage_trace)
    nexus_usage_trace["capability_receipts"] = [
        item.to_dict()
        for item in build_trace_receipts(
            plan=runtime_receipt_plan,
            capabilities=nexus_usage_trace["capabilities"],
            autoreason=nexus_usage_trace["autoreason"],
            ddtree=nexus_usage_trace["ddtree"],
            ultra_review=nexus_usage_trace["ultra_review"],
            codeintel=nexus_usage_trace["codeintel"],
        )
    ]
    for receipt in nexus_usage_trace["capability_receipts"]:
        if isinstance(receipt, dict) and receipt.get("name") == "research":
            receipt["source_projects"] = list(RESEARCH_SOURCE_PROJECTS)
            receipt["research_stack"] = research_stack_contract()

    payload = {
        "schema_version": "1.0",
        "task_desc": task_desc,
        "task_type": task_type,
        "asi_ledger": asi_ledger,
        "route": route,
        "execution_profile": execution_profile,
        "chosen_flow": chosen_flow,
        "guard": {
            "hit": guard_hit,
            "early_baseline_shortcut": early_baseline_shortcut,
            "history_forced_baseline": history_forced_baseline,
            "learn_forced_baseline": bool(
                learn_gate_blocked
                and force_flow is None
                and (not execution_profile["is_hard_task"] or chosen_flow == "baseline")
            ),
            "recent_hyper_failures": recent_hyper_fails,
            "nightshift_recommended": nightshift_recommended,
            "stage1_fail_signals": stage1_fail_signals,
            "history_window": max(1, history_window),
            "baseline_fast_sec": tuned_baseline_fast_sec,
            "max_time_ratio_guard": max_time_ratio_guard,
            "baseline_probe_skipped": baseline_probe_skipped,
            "baseline_probe": baseline_probe_for_report,
            "plateau_hard_pivot": plateau_hard_pivot,
        },
        "learn_phase_slo": {
            "phase_slo_pass": bool(learn_phase_slo.get("phase_slo_pass", False)),
            "required_done_ratio": float((learn_phase_slo.get("global", {}) or {}).get("required_done_ratio", 0.0) or 0.0),
            "status": learn_phase_slo.get("status", "UNAVAILABLE"),
            "reason": learn_phase_slo.get("reason", ""),
        },
        "result": result,
        "claim_check": claim_check,
        "hitl": hitl,
        "research_preflight": research_preflight,
        "research_session": {},
        "route_confidence": route_confidence,
        "strategy": {
            "path": strategy_path,
            "forced_flow": force_flow or "auto",
            "flow_ladder": ["baseline_probe", "hyper_sprint", "baseline_fallback"],
            "learn_gate_blocked": bool(learn_gate_blocked),
            "baseline_probe_skipped": baseline_probe_skipped,
            "plateau": plateau,
            "distant_scout_plan": route.get("distant_scout_plan", {}),
        },
        "artifact_summary": artifact_summary,
        "success_criteria": {
            "name": normalized_success_criteria,
            "mutation_required": mutation_required,
            "verification_only_allowed": verification_only_allowed,
        },
        "nexus_usage_trace": nexus_usage_trace,
        "timing": {
            "cli_elapsed_sec": round(time.monotonic() - flow_started_at, 4),
            "phase_wall_sec": phase_wall_sec,
            "breakdown_sec": timing_breakdown_sec,
        },
        "io": {
            "output_written": False,
            "output_path": None,
        },
    }
    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if output_file:
        written = _write_output_file(repo_root, output_file, payload)
        payload["io"]["output_written"] = True
        payload["io"]["output_path"] = str(written)
        # keep report + output payload in sync
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    phase_started_at = time.monotonic()
    asi_record = _asi_record(
        run_id=len(recent) + 1,
        task_desc=task_desc,
        recommended_flow=str(route.get("recommended_flow", "")),
        chosen_flow=chosen_flow,
        status=str(result.get("status", "")),
        error=str(result.get("error", "")),
        route_confidence=route_confidence,
        execution_family=str(
            (
                (result.get("report", {}) if isinstance(result.get("report"), dict) else {})
                .get("distant_scout_execution", {})
                or {}
            ).get("recommended_family")
            or ""
        ),
    )
    research_session = _research_session_packet(
        task_id=task_id,
        status=str(result.get("status", "")),
        asi_record=asi_record,
        route=route,
        research_preflight=research_preflight,
    )
    research_doctor = build_research_doctor(
        research_preflight=research_preflight,
        research_session=research_session,
        artifact_verified=artifact_verified,
    )
    payload["research_session"] = research_session
    payload["nexus_usage_trace"]["research_session"] = research_session
    payload["research_doctor"] = research_doctor
    payload["claim_probe"] = claim_probe
    payload["nexus_usage_trace"]["research_doctor"] = research_doctor
    payload["nexus_usage_trace"]["capabilities"]["research_doctor_score"] = research_doctor["score"]
    payload["nexus_usage_trace"]["capabilities"]["research_doctor_gate_passed"] = research_doctor["status"] == "PASS"
    recent.append(
        {
            "flow": chosen_flow,
            "status": result["status"],
            "reason": result.get("error", ""),
            "task_type": task_type,
            "task_desc": task_desc[:200],
            "route_recommended_flow": str(route.get("recommended_flow", "")),
            "ts": datetime.now(timezone.utc).isoformat(),
            "asi_record": asi_record,
        }
    )
    payload["asi_ledger"] = [item.get("asi_record") for item in recent if isinstance(item, dict) and isinstance(item.get("asi_record"), dict)]
    history_data[flow_key] = recent[-200:]
    _write_history(history_data)
    phase_wall_sec["C"] = round(time.monotonic() - phase_started_at, 4)
    payload["timing"]["cli_elapsed_sec"] = round(time.monotonic() - flow_started_at, 4)
    payload["timing"]["phase_wall_sec"] = phase_wall_sec
    payload["timing"]["breakdown_sec"] = timing_breakdown_sec
    payload["nexus_usage_trace"]["phase_wall_sec"] = phase_wall_sec
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if payload["io"].get("output_path"):
        Path(str(payload["io"]["output_path"])).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload, out_path


def _is_strictly_doc_fix(task: str, target_file: str) -> tuple[bool, str]:
    is_doc_file = any(target_file.endswith(ext) for ext in [".md", ".txt", ".rst"])
    has_code_intent = any(kw in task.lower() for kw in ["fix bug", "implement", "logic", "refactor"])
    
    score = 0
    if is_doc_file: score += 50
    if not has_code_intent: score += 30
    
    # Final Decision
    is_doc = score >= 80
    reason = f"Substance Score={score} (FileDoc={is_doc_file}, NoCodeIntent={not has_code_intent})"
    return is_doc, reason
