from __future__ import annotations

import json
import time
import concurrent.futures
import subprocess
import re
import difflib
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
from dataclasses import dataclass
import click

from nexus.engine.policies.research_policy import ResearchPolicy
from nexus.research.findings_memory import FindingsMemoryStore
from nexus.research.local_sprint_mutator import generate_local_candidate, generate_local_companion_edits
from nexus.research.sprint_service import SprintConfig, run_hyper_sprint, LLMCandidateGenerator, _candidate_summaries
from nexus.contracts import RLMTraceEvent, RLMTraceWriter
from nexus.engine.capability_router import CapabilityRouter
from nexus.services.codeintel import analyze_impact, scan_codebase


@dataclass(frozen=True)
class ParsedTuningKnobs:
    candidate_boost: int = 0
    max_rounds_boost: int = 0
    stage1_parallel_boost: int = 0
    baseline_fast_sec: float = 0.0
    skip_baseline_probe_for_hard: bool = False


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
    drone_crystals = learning_trace.get("drone_crystals", [])
    if not isinstance(drone_crystals, list):
        drone_crystals = []
    nightshift_report_path = str(learning_trace.get("nightshift_report_path") or result_report.get("nightshift_report_path") or "")
    nightshift_recovered = bool(
        learning_trace.get("nightshift_recovered", False)
        or result_report.get("nightshift_recovered", False)
    )
    return {
        "swarm_evidence_count": swarm_count,
        "swarm_used": swarm_count > 0,
        "drone_invoked_count": len(drone_crystals),
        "drone_used": len(drone_crystals) > 0,
        "nightshift_recommended": bool(nightshift_recommended),
        "nightshift_invoked": bool(nightshift_report_path),
        "nightshift_recovered": nightshift_recovered,
        "nightshift_report_path": nightshift_report_path,
    }


def _ultra_review_gate_evidence(
    *,
    repo_root: Path,
    task_desc: str,
    capability_stack: dict[str, Any],
) -> dict[str, Any]:
    governance_layers = capability_stack.get("governance_layers", [])
    if not isinstance(governance_layers, list):
        governance_layers = []
    recommended = "ultra_review" in {str(item) for item in governance_layers}
    if not recommended:
        return {
            "recommended": False,
            "invoked": False,
            "gate_passed": None,
            "report_path": "",
            "failures": [],
            "reason": "not_recommended",
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
    report_path = repo_root / ".nexus" / "reports" / "ultra_review" / "route_gate_report.json"
    try:
        from nexus.engine.ultra_review_service import UltraReviewService
        from scripts.ops.ultra_gate import evaluate_report

        payload = UltraReviewService(repo_root).run(
            dry_run=True,
            task=task_desc,
            report_path=report_path,
            sandbox_root=repo_root / ".nexus" / "reports" / "ultra_review" / "route_gate_sandboxes",
        )
        gate_passed, failures = evaluate_report(payload, check_artifacts=True)
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


def build_route(
    *,
    repo_root: Path,
    task_desc: str,
    task_type: str,
    candidate_count: int,
    root_cause_confidence: float,
    findings_query: str | None,
    target_file: str | None = None,
) -> dict:

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

    # 🐝 [P2 Optimization] Doc-Fix Interception
    task_lower = (task_desc or "").lower()
    target_lower = (target_file or "").lower()
    doc_patterns = ["readme", ".md", "doc:", "fix typo", "documentation", "typo:"]
    is_doc_fix = any(p in task_lower for p in doc_patterns) or any(p in target_lower for p in doc_patterns if p.startswith("."))
    
    task_upper = (task_desc or "").upper()
    hard_keywords = ["FLAKY", "RACE", "DEADLOCK", "TIMEOUT", "LATENCY", "WEBSOCKET", "SDK", "API"]
    cross_module_keywords = ["CROSS-MODULE", "MULTI-MODULE", "COORDINATOR", "SWARM", "DRONE", "NIGHTSHIFT"]
    is_cross_module_task = "cross_module" in str(task_type).lower() or any(kw in task_upper for kw in cross_module_keywords)
    has_hard_signal = any(kw in task_upper for kw in hard_keywords) or is_cross_module_task
    
    # R2 Tuning: Feature/Refactor prefer baseline, Bugfix with risk prefers hyper
    if is_doc_fix:
        recommended_flow = "baseline"
        recommended_reason = "Matched Doc-Fix Rule"
    elif task_type in ["feature", "refactor"]:
        recommended_flow = "baseline"
        recommended_reason = f"structural_task_type_{task_type}_prefer_baseline"
    else:
        # Bugfix case
        is_risky_bug = (
            candidate_count > 1
            or adjusted_root_cause_confidence < 0.75
            or findings_hits > 0
            or memory_hits > 0
            or has_hard_signal
            or decision.should_research
        )
        recommended_flow = "hyper_sprint" if is_risky_bug else "baseline"
        recommended_reason = "complex_bug_prefer_hyper" if is_risky_bug else "simple_bug_prefer_baseline"

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
    risk_score = min(100, risk_score)
    route_features = {
        "task_type": task_type,
        "has_hard_signal": has_hard_signal,
        "is_cross_module_task": is_cross_module_task,
        "is_doc_fix": is_doc_fix,
        "candidate_count": int(candidate_count),
        "findings_hits": int(findings_hits),
        "memory_hits": int(memory_hits),
        "adjusted_root_cause_confidence": round(float(adjusted_root_cause_confidence), 4),
        "risk_score": risk_score,
    }

    explain = {
        "task_type": task_type,
        "risk": risk_level,
        "files": [target_file] if target_file else [],
        "history": {"findings_hits": findings_hits, "memory_hits": memory_hits, "hints_count": len(historical_hints)},
        "confidence": round(adjusted_root_cause_confidence, 2),
        "reasoning": f"Flow '{recommended_flow}' chosen due to {recommended_reason}. TaskType: {task_type}."
    }
    capability_stack = CapabilityRouter().route(
        task_desc=task_desc,
        task_type=task_type,
        recommended_flow=recommended_flow,
        route_features=route_features,
        target_file=target_file,
    ).to_dict()

    return {
        "should_research": should_research,
        "mode": mode,
        "reason": reason,
        "rounds": decision.rounds if should_research else 0,
        "stable_wins": decision.stable_wins if should_research else 0,
        "findings_hits": findings_hits,
        "prior_fix_hits": findings_hits + memory_hits,
        "historical_hints": list(dict.fromkeys(historical_hints))[:3],  # Unique, max 3
        "adjusted_root_cause_confidence": adjusted_root_cause_confidence,
        "require_codex_audit": adjusted_root_cause_confidence < 0.6,
        "recommended_flow": recommended_flow,
        "recommended_reason": recommended_reason,
        "explain_payload": explain,
        "route_features": route_features,
        "capability_stack": capability_stack,
        "consensus": {
            "votes": consensus_votes,
            "reasons": vote_reasons,
            "winner": recommended_flow,
        },
    }


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
    hard_keywords = ["flaky", "race", "deadlock", "timeout", "latency", "websocket", "sdk", "api"]
    has_hard_keyword = any(keyword in text for keyword in hard_keywords)
    is_cross_module = "cross_module" in str(task_type).lower() or any(
        kw in text for kw in ["cross-module", "multi-module", "coordinator", "swarm", "drone", "nightshift"]
    )
    low_confidence = float(root_cause_confidence) < 0.75
    risk_bug = task_type == "bug" and route_recommended_flow == "hyper_sprint"
    is_hard_task = bool(has_hard_keyword or is_cross_module or low_confidence or risk_bug)

    effective_candidate_count = max(1, int(candidate_count))
    effective_max_rounds = 1
    effective_stage1_max_parallel = 1
    prefer_direct_hyper = False
    tuning_reasons: list[str] = []

    if risk_bug:
        effective_candidate_count = max(effective_candidate_count, 3)
        effective_max_rounds = max(effective_max_rounds, 2)
        effective_stage1_max_parallel = max(effective_stage1_max_parallel, 2)
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
        "is_cross_module": is_cross_module,
        "prefer_direct_hyper": prefer_direct_hyper,
        "belief_confidence": float(belief_confidence),
        "prior_fix_hits": int(prior_fix_hits or 0),
        "effective_candidate_count": effective_candidate_count,
        "effective_max_rounds": effective_max_rounds,
        "effective_stage1_max_parallel": effective_stage1_max_parallel,
        "tuning_reasons": tuning_reasons,
    }


def _write_output_file(repo_root: Path, path: Path, payload: dict) -> Path:
    out = path if path.is_absolute() else (repo_root / path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out




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
):
    """Internal impl for Auto Flow Runner: route -> run baseline/hyper -> enforce guard -> emit report."""

    flow_started_at = time.time()
    phase_wall_sec: dict[str, float] = {}
    phase_started_at = time.time()
    route = build_route(
        repo_root=repo_root,
        task_desc=task_desc,
        task_type=task_type,
        candidate_count=candidate_count,
        root_cause_confidence=root_cause_confidence,
        findings_query=findings_query,
        target_file=target_file,
    )
    phase_wall_sec["P"] = round(time.time() - phase_started_at, 4)
    phase_started_at = time.time()
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
    phase_wall_sec["X"] = round(time.time() - phase_started_at, 4)
    phase_started_at = time.time()
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
    if force_flow is None and chosen_flow == "hyper_sprint" and recent_hyper_fails >= max(1, history_fail_threshold):
        chosen_flow = "baseline"
        history_forced_baseline = True
    phase_wall_sec["D"] = round(time.time() - phase_started_at, 4)

    guard_hit = False
    target_path = (repo_root / target_file).resolve()
    if not target_path.exists():
        raise click.ClickException(f"Target file not found: {target_file}")
    pytest_cmd = ["uv", "run", "pytest", "-q", "--maxfail=1", test_file]
    original_code = target_path.read_text(encoding="utf-8")
    normalized_success_criteria = (success_criteria or "all_target_tests_pass").strip()
    verification_only_allowed = normalized_success_criteria == "all_target_tests_pass"
    mutation_required = normalized_success_criteria in {"artifact_changed_and_tests_pass", "mutation_required"}
    codeintel_evidence = _build_codeintel_evidence(repo_root, target_file=target_file, task_desc=task_desc)
    task_desc_with_codeintel = _task_with_codeintel_context(task_desc, codeintel_evidence)

    def _generate_baseline_patch(trial: int = 0) -> tuple[str, str]:
        """R4: Enhanced baseline generation with LLM fast-fallback and conservative local paths."""
        source_label = "local"
        fallback_reason = None
        
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
        
        if llm_baseline and task_type in ["feature", "refactor"]:
            try:
                # Use a very short timeout for baseline assistance to avoid blocking
                gen = LLMCandidateGenerator(repo_root, safe_mode=True)
                # Note: gen.generate internal timeout depends on gateway, but we wrap it here if possible
                # For now, we trust internal model_chain but monitor for rapid failure
                patched, meta = gen.generate(source_code=original_code, task=task_desc_for_llm, mutation_hint="baseline", seed=trial)
                if patched and patched != original_code:
                    return patched, "llm_assisted"
                else:
                    fallback_reason = "llm_generation_empty_fallback_local"
            except Exception as e:
                err_str = str(e).lower()
                if "timeout" in err_str:
                    fallback_reason = "llm_timeout_fallback_local"
                elif any(p in err_str for p in ["quota", "429", "limit"]):
                    fallback_reason = "llm_quota_fallback_local"
                else:
                    fallback_reason = f"llm_error_{err_str}_fallback_local"
        
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
            
        return patched, label

    def _run_baseline_apply() -> dict:
        start = time.time()
        ok = False
        err = ""
        source = "local"
        companion_edits: dict[Path, str] = {}
        restored_files: dict[Path, str | None] = {}
        try:
            patched, source = _generate_baseline_patch()
            if patched == original_code:
                err = "no_mutation_generated"
            else:
                companion_edits = generate_local_companion_edits(repo_root, target_path, task_desc, "baseline", 0)
                restored_files[target_path] = original_code
                target_path.write_text(patched, encoding="utf-8")
                for extra_path, extra_code in companion_edits.items():
                    if extra_path == target_path:
                        continue
                    restored_files[extra_path] = extra_path.read_text(encoding="utf-8") if extra_path.exists() else None
                    extra_path.parent.mkdir(parents=True, exist_ok=True)
                    extra_path.write_text(extra_code, encoding="utf-8")
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
                    path.write_text(original_text, encoding="utf-8")
        return {
            "flow": "baseline",
            "status": "SUCCESS" if ok else "FAILED",
            "elapsed_sec": round(time.time() - start, 4),
            "error": err,
            "report": {
                "source": source,
                "attempt_count": 1,
                "model_calls": 0,
                "total_tokens": 0,
                "token_capture_status": "not_applicable_local_only",
            },
        }

    def _run_baseline_probe() -> dict:
        # Probe run used by guard. Always restore original state.
        start = time.time()
        ok = False
        err = ""
        source = "local"
        patched = original_code
        restored_files: dict[Path, str | None] = {}
        try:
            patched, source = _generate_baseline_patch()
            if patched == original_code:
                err = "no_mutation_generated"
            else:
                companion_edits = generate_local_companion_edits(repo_root, target_path, task_desc, "baseline_probe", 0)
                restored_files[target_path] = original_code
                target_path.write_text(patched, encoding="utf-8")
                for extra_path, extra_code in companion_edits.items():
                    if extra_path == target_path:
                        continue
                    restored_files[extra_path] = extra_path.read_text(encoding="utf-8") if extra_path.exists() else None
                    extra_path.parent.mkdir(parents=True, exist_ok=True)
                    extra_path.write_text(extra_code, encoding="utf-8")
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
                    path.write_text(original_text, encoding="utf-8")
        return {
            "flow": "baseline_probe",
            "status": "SUCCESS" if ok else "FAILED",
            "elapsed_sec": round(time.time() - start, 4),
            "error": err,
            "report": {
                "source": source,
                "attempt_count": 1,
                "model_calls": 0,
                "total_tokens": 0,
                "token_capture_status": "not_applicable_local_only",
            },
            "_patch": patched if ok else None,
        }

    def _run_original_verification_rescue(previous_result: dict) -> dict:
        start = time.time()
        target_path.write_text(original_code, encoding="utf-8")
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
            "elapsed_sec": round(float(previous_result.get("elapsed_sec", 0.0) or 0.0) + (time.time() - start), 4),
            "error": "" if ok else err,
            "report": report,
        }

    def _run_hyper_apply() -> dict:
        start = time.time()
        effective_stage1_timeout = stage1_timeout_sec
        if baseline_probe and baseline_probe.get("elapsed_sec", 0) > 0:
            dynamic_timeout = int(round(float(baseline_probe["elapsed_sec"]) * max(1.0, dynamic_timeout_multiplier)))
            effective_stage1_timeout = max(
                min_dynamic_stage1_timeout,
                min(stage1_timeout_sec, dynamic_timeout),
            )
        cfg = SprintConfig(
            task=task_desc_with_codeintel if llm_mode else task_desc,
            target_file=target_file,
            test_file=test_file,
            candidate_count=execution_profile["effective_candidate_count"],
            max_rounds=execution_profile["effective_max_rounds"],
            timeout_sec=timeout_sec,
            safe_mode=True,
            stage1_max_parallel=execution_profile["effective_stage1_max_parallel"],
            stage1_timeout_sec=effective_stage1_timeout,
            llm_mode=llm_mode,
        )
        res = run_hyper_sprint(repo_root=repo_root, config=cfg)
        ok = res.status == "SUCCESS" and bool(res.patch)
        err = ""
        if ok:
            target_path.write_text(res.patch, encoding="utf-8")
        else:
            err = res.reason
        return {
            "flow": "hyper_sprint",
            "status": "SUCCESS" if ok else "FAILED",
            "elapsed_sec": round(time.time() - start, 4),
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
                },
            }

    baseline_probe = None
    early_baseline_shortcut = False
    baseline_probe_skipped = False
    phase_started_at = time.time()
    if chosen_flow == "baseline":
        result = _run_baseline_apply()
        strategy_path = "baseline_only"
    else:
        direct_hyper = bool(execution_profile.get("prefer_direct_hyper", False))
        if (
            force_flow is None
            and execution_profile["is_hard_task"]
            and (skip_baseline_probe_for_hard or direct_hyper)
        ):
            baseline_probe_skipped = True
            result = _run_hyper_apply()
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
                    target_path.write_text(probe_patch, encoding="utf-8")
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
                    target_path.write_text(original_code, encoding="utf-8")
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
                    target_path.write_text(original_code, encoding="utf-8")
                    result = _run_baseline_apply()
                    if isinstance(result.get("report"), dict) and isinstance(hyper_result_for_guard.get("report"), dict):
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
                    chosen_flow = "baseline"
                    strategy_path = "hyper_guard_fallback_to_baseline"
    phase_wall_sec["R"] = round(time.time() - phase_started_at, 4)

    baseline_probe_for_report = None
    if isinstance(baseline_probe, dict):
        baseline_probe_for_report = {k: v for k, v in baseline_probe.items() if k != "_patch"}

    phase_started_at = time.time()
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
    capability_evidence = _capability_evidence(
        result_report=result_report,
        learning_trace=hyper_learning_trace,
        nightshift_recommended=nightshift_recommended,
    )
    ultra_review_evidence = _ultra_review_gate_evidence(
        repo_root=repo_root,
        task_desc=task_desc,
        capability_stack=route.get("capability_stack", {}),
    )
    phase_wall_sec["A"] = round(time.time() - phase_started_at, 4)
    nexus_usage_trace = {
        "gemini_uses_nexus": bool(gemini_invoked),
        "nexus_context_delivered": True,
        "nexus_tier": tier_decision["tier"],
        "nexus_tier_reason": tier_decision["reason"],
        "pillars": {
            "lancedb": {"active": True, "hits": int(route.get("findings_hits", 0) or 0)},
            "memory": {"active": True, "hits": int((route.get("route_features", {}) or {}).get("memory_hits", 0) or 0)},
            "mempalace": {"active": bool(hyper_learning_trace), "verified": mempalace_verified},
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
            "research_used": bool(hyper_used),
            "hyper_used": bool(hyper_used),
            "nightshift_recommended": capability_evidence["nightshift_recommended"],
            "nightshift_invoked": capability_evidence["nightshift_invoked"],
            "nightshift_recovered": capability_evidence["nightshift_recovered"],
            "nightshift_report_path": capability_evidence["nightshift_report_path"],
            "swarm_used": capability_evidence["swarm_used"],
            "swarm_evidence_count": capability_evidence["swarm_evidence_count"],
            "drone_used": capability_evidence["drone_used"],
            "drone_invoked_count": capability_evidence["drone_invoked_count"],
            "self_heal_used": self_heal_used,
            "claim_verified": artifact_verified,
            "ultra_review_recommended": ultra_review_evidence["recommended"],
            "ultra_review_invoked": ultra_review_evidence["invoked"],
            "ultra_review_gate_passed": ultra_review_evidence["gate_passed"],
            "ultra_review_report_path": ultra_review_evidence["report_path"],
        },
        "phase_wall_sec": phase_wall_sec,
        "capability_stack": route.get("capability_stack", {}),
        "autoreason": hyper_learning_trace.get("autoreason", {}) if isinstance(hyper_learning_trace, dict) else {},
        "ddtree": hyper_learning_trace.get("ddtree", {}) if isinstance(hyper_learning_trace, dict) else {},
        "ultra_review": ultra_review_evidence,
        "codeintel": codeintel_evidence,
        "gemini_patch_status": "passed" if tests_passed and gemini_invoked and not nexus_rescued else ("failed" if gemini_invoked else "missing"),
        "nexus_rescued": nexus_rescued,
        "winner_source": winner_source,
        "usage_valid": bool(gemini_invoked and artifact_verified),
    }
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

    payload = {
        "schema_version": "1.0",
        "task_desc": task_desc,
        "task_type": task_type,
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
        },
        "learn_phase_slo": {
            "phase_slo_pass": bool(learn_phase_slo.get("phase_slo_pass", False)),
            "required_done_ratio": float((learn_phase_slo.get("global", {}) or {}).get("required_done_ratio", 0.0) or 0.0),
            "status": learn_phase_slo.get("status", "UNAVAILABLE"),
            "reason": learn_phase_slo.get("reason", ""),
        },
        "result": result,
        "strategy": {
            "path": strategy_path,
            "forced_flow": force_flow or "auto",
            "flow_ladder": ["baseline_probe", "hyper_sprint", "baseline_fallback"],
            "learn_gate_blocked": bool(learn_gate_blocked),
        },
        "artifact_summary": artifact_summary,
        "success_criteria": {
            "name": normalized_success_criteria,
            "mutation_required": mutation_required,
            "verification_only_allowed": verification_only_allowed,
        },
        "nexus_usage_trace": nexus_usage_trace,
        "timing": {
            "cli_elapsed_sec": round(time.time() - flow_started_at, 4),
            "phase_wall_sec": phase_wall_sec,
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
    phase_started_at = time.time()
    recent.append(
        {
            "flow": chosen_flow,
            "status": result["status"],
            "reason": result.get("error", ""),
            "task_type": task_type,
            "task_desc": task_desc[:200],
            "route_recommended_flow": str(route.get("recommended_flow", "")),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )
    history_data[flow_key] = recent[-200:]
    _write_history(history_data)
    phase_wall_sec["C"] = round(time.time() - phase_started_at, 4)
    payload["timing"]["cli_elapsed_sec"] = round(time.time() - flow_started_at, 4)
    payload["timing"]["phase_wall_sec"] = phase_wall_sec
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
