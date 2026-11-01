from __future__ import annotations

import json
import logging
import time
import concurrent.futures
import importlib.util
import subprocess
import sys
import re
import difflib
import hashlib
import os
from pathlib import Path
from datetime import datetime, timezone
from collections.abc import Iterable, Mapping
from typing import Any
from dataclasses import asdict
import click

from nexus.core.argv_command import run_reaping_process_group
from nexus.core.repo_root import REPO_ROOT
from nexus.research.flow.auto_flow_decision import decide_auto_flow_routing, enrich_route_on_plateau
from nexus.research.sprint_service import SprintConfig, run_hyper_sprint, LLMCandidateGenerator, LLMCandidateError, _candidate_summaries, planner_route_signals, NO_LOCAL_CANDIDATE_GENERATOR
from nexus.contracts import RLMTraceEvent, RLMTraceWriter
from nexus.engine.capability_planner import CapabilityPlanner
from nexus.engine.route_decision_adapter import build_route_decision
from nexus.engine.openseeker_alignment import build_openseeker_trace
from nexus.research.findings_memory import FindingsMemoryStore
from nexus.contracts.learning_experience import (
    apply_autodata_quality_gate,
    build_learning_experience,
    project_model_training,
    project_nexus_policy,
    save_promoted_learning_policy,
)
from nexus.core.learning_steward import LearningSteward
from nexus.engine.learning_policy_loader import (
    DEFAULT_PROMOTED_POLICY_PATH,
    merge_runtime_learning_policy,
    route_cost_controls_from_env,
)
from nexus.engine.rlm_controller import build_bounded_rlm_orchestration_receipt
from nexus.learning.outcome_memory import EpisodeOutcomeRecord, OutcomeMemoryManager
from nexus.research.architecture_scout import DistantScoutPlanner
from nexus.research.research_stack_contract import research_stack_contract, research_stack_source_projects
from nexus.research.research_runtime_contracts import (
    build_claim_probe,
    build_nexus_failure_analysis,
    build_research_doctor,
)
from nexus.app import research_semantic_runtime as _research_semantic_runtime
from nexus.app.research_autoreason_runtime import build_autoreason_payload
from nexus.app.research_receipt_runtime import build_capability_receipt_payloads, runtime_receipt_plan_payload
from nexus.research.flow.capability_planning import drop_archived_capabilities
from nexus.app.research_s2t_runtime import (
    autoreason_s2t_candidates as _autoreason_s2t_candidates,
    record_autoreason_s2t_trace as _record_autoreason_s2t_trace,
)
from nexus.research.flow.route_decider import (
    RouteConsensusPayload,
    RouteDecisionPayload,
    RouteExplainPayload,
    RouteFeatures,
    RouteHistoryPayload,
    RouteSignals,
    _classify_commercial_signal,
    collect_route_signals as _route_collect_route_signals,
    _decide_flow,
    _derive_findings_query,
    _task_body_only,
)
from nexus.research.bench_treatment_lane import treatment_lane_active as _bench_treatment_lane_active
from nexus.research.flow.evidence_packer import (
    _build_research_context,
    _doc_scout_supports_specific_claim,
    _infer_research_role,
    _write_msa_receipt_reports,
    apply_nightshift_auto_run,
    maybe_run_nightshift_after_hyper_failure,
)
from nexus.research.flow.unified_capability_projection import (
    project_unified_capability_stages,
    unified_receipts_from_meta,
)
from nexus.services import post_candidate_seam as _post_candidate_seam
from nexus.research.flow.baseline_report import (
    baseline_report_from_meta,
    local_baseline_meta,
    strict_baseline_failure_meta,
)
from nexus.research.flow import codeintel_context as _codeintel_context
from nexus.research.flow.auto_flow_payload import AutoFlowPayloadParts, build_auto_flow_payload
from nexus.research.flow.auto_flow_executor import (
    build_hyper_sprint_report,
    build_verification_only_rescue_report,
    merge_guard_fallback_accounting,
)
from nexus.research.flow.capability_evidence import (
    augment_local_msa_bench_evidence as _augment_local_msa_bench_evidence,
    candidate_summary_has_swarm_evidence as _candidate_summary_has_swarm_evidence,
    capability_evidence as _capability_evidence,
    ultra_review_gate_evidence as _ultra_review_gate_evidence,
)
from nexus.research.flow.capability_planning import (
    benchmark_skill_mount_requests_from_env as _benchmark_skill_mount_requests_from_env,
    build_capability_plan_and_decision as _build_capability_plan_and_decision,
    build_route_executor_flags,
    compose_capability_plan,
    runtime_capability_budget as _runtime_capability_budget,
    runtime_skill_overlay_requested as _runtime_skill_overlay_requested,
)
from nexus.research.flow.governance_packets import (
    governance_events_packet as _governance_events_packet,
    research_preflight_packet as _research_preflight_packet,
    research_session_packet as _research_session_packet,
)
from nexus.research.flow.history_signal_store import HistorySignalStore
from nexus.research.flow.model_training_export import write_auto_flow_model_training_export
from nexus.research.flow.phase_clock import AutoFlowPhaseClock, apply_auto_flow_timing_payload
from nexus.research.flow.report_io import write_output_file as _write_output_file
from nexus.research.flow.runtime_decision import (
    asi_record as _asi_record,
    claim_check_summary as _claim_check_summary,
    detect_plateau as _detect_plateau,
    hitl_payload as _hitl_payload,
    nexus_tier as _nexus_tier,
)
from nexus.research.flow.runtime_state import (
    ParsedTuningKnobs,
    parse_tuning_knobs as _parse_tuning_knobs,
    read_belief_confidence_fast,
    read_capability_tuning_fast,
    read_phase_slo_summary_fast,
)
from nexus.research.flow.task_classifier import is_strictly_doc_fix as _is_strictly_doc_fix


RESEARCH_SOURCE_PROJECTS = tuple(research_stack_source_projects())


def _unified_runtime_capability_stages(result_report: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Capability stages of the UnifiedRuntime run(s) behind the delivered flow result."""

    if not isinstance(result_report, dict):
        return []
    stages = result_report.get("unified_runtime_capability_stages")
    if not isinstance(stages, list):
        return []
    return [dict(item) for item in stages if isinstance(item, dict)]


def _unified_receipt_from_meta(meta: Mapping[str, Any] | None) -> dict[str, Any]:
    receipts = unified_receipts_from_meta(meta if isinstance(meta, dict) else None)
    return dict(receipts[0]) if receipts else {}


def _seam_task_id(task_id: str | None, target_file: str) -> str:
    return f"auto-flow:{task_id or _safe_trace_slug(target_file)}"


def _apply_post_candidate_seam(
    report: dict[str, Any],
    *,
    generation_meta: Mapping[str, Any] | None,
    task_id: str,
    target_path: Path,
    test_file: Path,
    original_code: str,
    candidate_code: str,
    pre_stages: list[dict[str, Any]],
    released: Mapping[str, list[str]],
    workspace_root: Path | None = None,
) -> None:
    """Run sandbox/ultra_review on the candidate (scratch copy) and project every seam stage.

    Never changes the row outcome: the stages only reach the capability receipts.
    """

    unified = _unified_receipt_from_meta(generation_meta)
    try:
        post = _post_candidate_seam.run_seam_for_candidate(
            workspace_root=workspace_root,
            task_id=task_id,
            unified_receipt=unified,
            target_path=target_path,
            visible_test_path=test_file,
            original_code=original_code,
            candidate_code=candidate_code,
        )
    except Exception as exc:  # noqa: BLE001 - the seam never breaks the row
        post = None
        report["post_candidate_seam_error"] = f"{type(exc).__name__}: {exc}"[:300]
    merged = _post_candidate_seam.merge_seam_receipts(
        task_id=task_id, pre_stages=pre_stages, post_receipt=post, released=released
    )
    if merged is None:
        return
    report["post_candidate_seam"] = {
        key: value for key, value in merged.items() if key != "capabilities"
    } | {"capabilities": [str(stage.get("name")) for stage in merged["capabilities"]]}
    stages = project_unified_capability_stages([unified, merged] if unified else [merged])
    if stages:
        report["unified_runtime_capability_stages"] = stages


def _run_visible_pytest(
    pytest_cmd: list[str],
    *,
    repo_root: Path,
    target_path: Path,
    test_path: Path,
    original_code: str,
    candidate_code: str,
    timeout_sec: int,
    companion_files: Iterable[Path] = (),
) -> subprocess.CompletedProcess:
    """Visible test for the candidate; confined on a scratch copy under the strict/counted lane
    (no OS barrier -> not executed, stderr ``confinement_unavailable``).

    The confined copy holds only the candidate target, the visible test and their sibling files;
    a candidate that also edits companion files elsewhere cannot be reproduced there, so under
    the confinement it is refused (``confinement_unavailable:multi_file``, not executed) instead
    of failing its visible test spuriously."""
    if _post_candidate_seam.confine_visible_test_enabled():
        companions = sorted(str(p) for p in companion_files if Path(p) != Path(target_path))
        if companions:
            return subprocess.CompletedProcess(
                pytest_cmd,
                1,
                "",
                f"{_post_candidate_seam.CONFINEMENT_UNAVAILABLE}:multi_file:{len(companions)}",
            )
        completed, _executed = _post_candidate_seam.run_visible_test_confined(
            target_path=target_path,
            visible_test_path=test_path,
            original_code=original_code,
            candidate_code=candidate_code,
            timeout_sec=timeout_sec,
            workspace_root=repo_root,
        )
        return completed
    # Runs the candidate's tests: their process group is killed after (#3052).
    return run_reaping_process_group(pytest_cmd, cwd=repo_root, timeout=timeout_sec)


def _visible_error(res: subprocess.CompletedProcess, default: str) -> str:
    stderr = str(getattr(res, "stderr", "") or "")
    multi_file = f"{_post_candidate_seam.CONFINEMENT_UNAVAILABLE}:multi_file"
    if stderr.startswith(multi_file):
        return multi_file
    return _post_candidate_seam.CONFINEMENT_UNAVAILABLE if stderr.startswith(_post_candidate_seam.CONFINEMENT_UNAVAILABLE) else default


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
    return _route_collect_route_signals(
        repo_root=repo_root,
        task_desc=task_desc,
        task_type=task_type,
        candidate_count=candidate_count,
        root_cause_confidence=root_cause_confidence,
        findings_query=findings_query,
        target_file=target_file,
        findings_memory_store_cls=FindingsMemoryStore,
    )


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
    return _codeintel_context.rel_path_for_report(repo_root, path_text)


def _codeintel_run_cache_graph_path(repo_root: Path) -> Path | None:
    return _codeintel_context.codeintel_run_cache_graph_path(repo_root)


def _load_codeintel_graph(path: Path) -> dict[str, Any] | None:
    return _codeintel_context.load_codeintel_graph(path)


def _build_codeintel_evidence(repo_root: Path, *, target_file: str, task_desc: str) -> dict[str, Any]:
    return _codeintel_context.build_codeintel_evidence(repo_root, target_file=target_file, task_desc=task_desc)


def _mapping_get(value: object, key: str) -> object:
    return value.get(key, "") if isinstance(value, dict) else ""


_SYMMETRIC_MODEL_SOURCES = frozenset({"llm", "nexus_llm_baseline", "llm_assisted"})


# PR-3 treatment lane: the visible-test self-heal output is also the model's own candidate.
_TREATMENT_MODEL_SOURCES = frozenset({"llm_self_heal"})


def _is_symmetric_model_source(source: str) -> bool:
    """Exact model-source allowlist: the product labels of a model-generated candidate only."""

    label = str(source or "").strip().lower()
    if label in _SYMMETRIC_MODEL_SOURCES:
        return True
    return label in _TREATMENT_MODEL_SOURCES and _bench_treatment_lane_active()


def _symmetric_prompt_mode() -> bool:
    """Like-for-like A/B mode (``NEXUS_SYMMETRIC_PROMPT``); see sprint_service._symmetric_prompt_mode."""

    return os.environ.get("NEXUS_SYMMETRIC_PROMPT", "").strip().lower() in {"1", "true", "yes"}


def _task_with_codeintel_context(task_desc: str, codeintel: dict[str, Any]) -> str:
    if _symmetric_prompt_mode():
        # S6: no repository context in the model prompt; the bare arm never reads the repo.
        return task_desc
    res = _codeintel_context.task_with_codeintel_context(task_desc, codeintel)
    if "[Nexus CodeIntel Compact]" in res and "[Nexus CodeIntel]" not in res:
        res = res.replace("[Nexus CodeIntel Compact]", "[Nexus CodeIntel]\n[Nexus CodeIntel Compact]")
    return res


def build_route(
    *,
    repo_root: Path,
    task_desc: str,
    task_type: str,
    candidate_count: int,
    root_cause_confidence: float,
    findings_query: str | None,
    task_id: str | None = None,
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
    route_cost_controls = route_cost_controls_from_env()
    if route_cost_controls.get("disable_research") is True:
        decision_payload["should_research"] = False
        research_context = {
            "role": "general",
            "risk_flags": [],
            "blocked_assumptions": [],
            "global_constraints": [],
            "doc_scout": {"hits_count": 0, "hits": []},
            "route_cost_policy": {
                "disable_research": True,
                "source": str(route_cost_controls.get("policy_source") or ""),
                "route_lane": str(route_cost_controls.get("route_lane") or ""),
            },
        }
    else:
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
        "route_cost_disable_research": bool(route_cost_controls.get("disable_research", False)),
        "route_cost_context_mode": str(route_cost_controls.get("context_mode") or ""),
        "route_lane": str(route_cost_controls.get("route_lane") or ""),
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
    if task_id:
        route_payload["task_id"] = task_id
    capability_plan, route_decision = _build_capability_plan_and_decision(
        task_desc=task_desc,
        task_type=task_type,
        route=route_payload,
        budget=merge_runtime_learning_policy(repo_root),
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
    route_cost_controls = route_cost_controls_from_env()
    if route_cost_controls.get("max_rounds"):
        try:
            effective_max_rounds = min(effective_max_rounds, max(1, int(route_cost_controls["max_rounds"])))
            tuning_reasons.append(f"route_cost_max_rounds:{route_cost_controls['max_rounds']}")
        except (TypeError, ValueError):
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


def _refresh_route_for_runtime_candidate_factory(
    *,
    repo_root: Path,
    route: dict[str, Any],
    result: dict[str, Any],
    result_report: dict[str, Any],
    task_desc: str,
    task_type: str,
) -> dict[str, Any]:
    """Replan when runtime evidence proves A/B/AB candidate judging is possible."""
    summaries = result_report.get("candidate_summaries", []) if isinstance(result_report, dict) else []
    if str(result.get("flow", "")) != "hyper_sprint" or not isinstance(summaries, list) or len(summaries) < 2:
        return route

    route_features = dict(route.get("route_features", {}) if isinstance(route.get("route_features"), dict) else {})
    previous_count = int(route_features.get("candidate_count", 1) or 1)
    route_features["candidate_count"] = max(previous_count, len(summaries))
    route_features["candidate_factory_readiness_estimate"] = {
        "ready": True,
        "status": "READY",
        "reason": "runtime_candidate_summaries",
        "estimated_candidates": len(summaries),
    }
    route["route_features"] = route_features
    route["runtime_candidate_factory_replanned"] = True
    capability_plan, route_decision = _build_capability_plan_and_decision(
        task_desc=task_desc,
        task_type=task_type,
        route=route,
        budget=merge_runtime_learning_policy(repo_root),
    )
    route["capability_plan"] = capability_plan.to_dict()
    route["route_decision"] = route_decision
    return route


def _write_runtime_receipt_json(repo_root: Path, *, category: str, receipt_slug: str, payload: dict[str, Any]) -> str:
    return _research_semantic_runtime._write_runtime_receipt_json(
        repo_root,
        category=category,
        receipt_slug=receipt_slug,
        payload=payload,
    )


def _stringify_claims(rows: list[Any]) -> list[str]:
    return _research_semantic_runtime.stringify_claims(rows)


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
    _research_semantic_runtime.augment_semantic_runtime_capabilities(
        repo_root=repo_root,
        task_id=task_id,
        task_desc=task_desc,
        task_type=task_type,
        target_file=target_file,
        receipt_slug=receipt_slug,
        selected_capabilities=selected_capabilities,
        nexus_usage_trace=nexus_usage_trace,
        route=route,
        asi_ledger=asi_ledger,
        plateau=plateau,
        artifact_verified=artifact_verified,
        normalized_success_criteria=normalized_success_criteria,
    )


def _runtime_receipt_plan_payload(
    capability_plan_payload: dict[str, Any],
    nexus_usage_trace: dict[str, Any],
) -> dict[str, Any]:
    return runtime_receipt_plan_payload(capability_plan_payload, nexus_usage_trace)


SKILL_MOUNT_CAPABILITY_ALIASES: dict[str, tuple[str, ...]] = {
    "benchmark_and_promotion": ("claim_gate", "artifact_gate", "jit_validation", "harness_preflight_sensor"),
    "forecast_pregate": ("forecast_gate", "pregate", "plan_quality_gate"),
    "governance_and_trust": ("claim_gate", "pregate", "ultra_review", "mempalace"),
    "notebook_and_knowledge_injection": ("research", "memory", "lancedb", "semantic_searcher"),
    "planning_and_handoff": ("plan_quality_gate", "research", "memory"),
    "repair_and_coding": ("hyper", "codeintel", "jit_validation", "semantic_failure_sensor"),
    "research_and_source_discipline": ("research", "lancedb", "semantic_searcher"),
}


def _skill_mount_receipt_names(capability_mount: str) -> set[str]:
    names = {capability_mount}
    names.update(SKILL_MOUNT_CAPABILITY_ALIASES.get(capability_mount, ()))
    return {name for name in names if name}


def _confirmed_skill_mount_receipt(
    planned: dict[str, Any],
    receipts_by_name: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    capability_mount = str(planned.get("capability_mount") or planned.get("capability") or "").strip()
    for receipt_name in _skill_mount_receipt_names(capability_mount):
        receipt = receipts_by_name.get(receipt_name)
        if not receipt:
            continue
        if bool(receipt.get("public_claim_safe")) or (
            bool(receipt.get("invoked"))
            and bool(receipt.get("evidence_present"))
            and bool(receipt.get("gate_passed"))
            and bool(receipt.get("outcome_contributed"))
        ):
            return receipt
    return None


def _build_runtime_skill_mount_contracts(
    *,
    capability_plan_payload: dict[str, Any],
    route_decision_payload: dict[str, Any],
    capability_receipts: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    signal_snapshot = (
        capability_plan_payload.get("signal_snapshot", {})
        if isinstance(capability_plan_payload.get("signal_snapshot"), dict)
        else {}
    )
    planned_contracts = [
        item for item in (signal_snapshot.get("planned_skill_mount_contracts", []) or []) if isinstance(item, dict)
    ]
    violations = [
        item for item in (signal_snapshot.get("skill_mount_violations", []) or []) if isinstance(item, dict)
    ]
    receipts_by_name = {
        str(item.get("name") or "").strip(): item
        for item in capability_receipts
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    route_ref = str(route_decision_payload.get("task_id") or route_decision_payload.get("schema_version") or "").strip()
    contracts: list[dict[str, Any]] = []
    for planned in planned_contracts:
        skill_id = str(planned.get("skill_id") or "").strip()
        if not skill_id:
            continue
        receipt = _confirmed_skill_mount_receipt(planned, receipts_by_name)
        if not receipt:
            violations.append(
                {
                    "skill_name": skill_id,
                    "path": "",
                    "reason": "skill_mount_not_confirmed_by_runtime_receipt",
                }
            )
            continue
        evidence_refs = [
            str(ref)
            for ref in (planned.get("evidence_refs", []) or [])
            if str(ref).strip()
        ]
        evidence_refs.extend(
            str(ref)
            for ref in (receipt.get("evidence_refs", []) or [])
            if str(ref).strip()
        )
        if route_ref:
            evidence_refs.append(f"route_decision:{route_ref}")
        evidence_refs.append(f"capability_receipt:{receipt.get('name')}")
        contracts.append(
            {
                "skill_id": skill_id,
                "skill_status": str(planned.get("skill_status") or ""),
                "capability_mount": str(planned.get("capability_mount") or planned.get("capability") or ""),
                "capability": str(receipt.get("name") or planned.get("capability") or ""),
                "load_reason_codes": list(planned.get("load_reason_codes", []) or [])
                + ["runtime_capability_receipt_confirmed"],
                "evidence_refs": list(dict.fromkeys(evidence_refs)),
                "outcome_contributed": True,
            }
        )
    return {"skill_mount_contracts": contracts, "skill_mount_violations": violations}


def _bind_gate_input_files(gen: Any, repo_root: Path, *, target_file: str, test_file: str) -> None:
    """Hand the task's target and registered visible test to the generator's gate inputs.

    Absolute in-repo paths (as the counted runner passes them) are made repo-relative; an
    invalid or hidden test file is bound as "" so the gates keep refusing.
    """
    from nexus.research.sprint_service import repo_relative_path, visible_test_target_error

    target_rel, target_error = repo_relative_path(repo_root, target_file)
    test_rel, test_error = repo_relative_path(repo_root, test_file)
    if test_rel and (test_error or visible_test_target_error(repo_root, test_rel)):
        test_rel = ""
    if hasattr(gen, "gate_input_target_file"):
        setattr(gen, "gate_input_target_file", "" if target_error else target_rel)
    if hasattr(gen, "gate_input_test_file"):
        setattr(gen, "gate_input_test_file", "" if test_error else test_rel)


def _model_baseline_failure_meta(
    reason: str, meta: dict[str, Any] | None = None, *, llm_baseline_required: bool
) -> dict[str, Any]:
    """A failed model baseline never falls back to a locally generated patch (any lane)."""
    out = strict_baseline_failure_meta(reason, meta)
    if not llm_baseline_required:
        out["baseline_llm_required"] = False
        out["baseline_source_policy"] = "llm_no_local_fallback"
    return out


def _build_baseline_patch(
    *,
    trial: int,
    original_code: str,
    task_desc: str,
    route: dict[str, Any],
    llm_baseline_required: bool,
    llm_baseline: bool,
    task_desc_with_codeintel: str,
    repo_root: Path,
    task_type: str,
    test_source: str = "",
    target_file: str = "",
    test_file: str = "",
    model_configured: bool = False,
) -> tuple[str, str, dict[str, Any]]:
    if model_configured and not llm_baseline:
        # #2339 follow-up: a run with a model never delivers the local answer table, even when
        # the model baseline is skipped (route-cost skip_llm_baseline); the flow escalates instead.
        meta = local_baseline_meta()
        meta["source"] = "model_baseline_skipped"
        meta["baseline_source_policy"] = "model_run_no_local_baseline"
        return original_code, "model_baseline_skipped", meta

    symmetric_prompt = _symmetric_prompt_mode()
    # [NEW: X-2] Prior-Art from Claims
    try:
        if symmetric_prompt:
            # S5: nothing learned in a previous task/trial reaches the model in the like-for-like A/B.
            raise RuntimeError("prior_art_skipped_symmetric_prompt")
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
            gen = LLMCandidateGenerator(repo_root, safe_mode=True, route_signals=route)
            # Wiring PR-4: the counted A/B baseline path is where the strict lane's model call
            # happens; bind the task contract for the preflight gate inputs only (the generator's
            # own target_file, which also gates a Local assist request, stays unset here).
            _bind_gate_input_files(gen, repo_root, target_file=target_file, test_file=test_file)
            patched, meta = gen.generate(
                source_code=original_code,
                task=task_desc_for_llm,
                mutation_hint="baseline",
                seed=trial,
                # S4: the bare arm always sees the visible test; so does the model here in the A/B.
                test_source=test_source if symmetric_prompt else "",
            )
            if patched and patched != original_code:
                meta = dict(meta)
                if llm_baseline_required:
                    meta["baseline_llm_required"] = True
                    meta["baseline_source_policy"] = "strict_llm_no_local_fallback"
                    return patched, "nexus_llm_baseline", meta
                return patched, "llm_assisted", meta
            else:
                return original_code, "nexus_llm_baseline_failed", _model_baseline_failure_meta(
                    "llm_no_patch",
                    dict(meta),
                    llm_baseline_required=llm_baseline_required,
                )
        except LLMCandidateError as e:
            return original_code, "nexus_llm_baseline_failed", _model_baseline_failure_meta(
                str(e), e.metadata, llm_baseline_required=llm_baseline_required
            )
        except Exception as e:
            err_str = str(e).lower()
            if "timeout" in err_str:
                failure_reason = "timeout"
            elif any(p in err_str for p in ["quota", "429", "limit"]):
                failure_reason = "quota_exhausted"
            else:
                failure_reason = f"llm_error_{err_str}"
            return original_code, "nexus_llm_baseline_failed", _model_baseline_failure_meta(
                failure_reason, llm_baseline_required=llm_baseline_required
            )
    elif llm_baseline_required:
        return original_code, "nexus_llm_baseline_missing", strict_baseline_failure_meta("llm_baseline_required_missing")
    
    # No model: the deterministic local answer table was deleted (#2339 follow-up), so the
    # baseline honestly has no candidate instead of a fabricated patch.
    meta = local_baseline_meta()
    meta["source"] = NO_LOCAL_CANDIDATE_GENERATOR
    meta["baseline_source_policy"] = NO_LOCAL_CANDIDATE_GENERATOR
    return original_code, NO_LOCAL_CANDIDATE_GENERATOR, meta


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
    phase_clock = AutoFlowPhaseClock()
    phase_wall_sec = phase_clock.phase_wall_sec
    timing_breakdown_sec: dict[str, float] = {}
    benchmark_skill_mount_requests = _benchmark_skill_mount_requests_from_env(task_id=task_id)
    runtime_budget = _runtime_capability_budget(repo_root)
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
    if benchmark_skill_mount_requests or _runtime_skill_overlay_requested(runtime_budget):
        capability_plan, route_decision = _build_capability_plan_and_decision(
            task_desc=task_desc,
            task_type=task_type,
            route=route,
            task_id=task_id,
            budget=runtime_budget,
            skills=benchmark_skill_mount_requests,
        )
        route["capability_plan"] = capability_plan.to_dict()
        route["route_decision"] = route_decision
    phase_clock.mark("P")
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
    chosen_flow_input = force_flow or route["recommended_flow"]
    tier_decision = _nexus_tier(
        route.get("route_features", {}) if isinstance(route, dict) else {},
        force_flow=force_flow,
    )
    learn_phase_slo = read_phase_slo_summary_fast(repo_root)
    phase_clock.mark("X")
    learn_gate_blocked = (
        not bool(learn_phase_slo.get("phase_slo_pass", False))
        or float((learn_phase_slo.get("global", {}) or {}).get("required_done_ratio", 0.0) or 0.0) < 0.95
    )

    history_store = HistorySignalStore(repo_root)
    recent = history_store.recent_for(target_file=target_file, test_file=test_file)
    asi_ledger = [item.get("asi_record") for item in recent if isinstance(item, dict) and isinstance(item.get("asi_record"), dict)]
    plateau = _detect_plateau(asi_ledger)
    plateau_detected = bool(plateau.get("detected"))

    if plateau_detected:
        def build_plan_callback(r: dict[str, Any]):
            return _build_capability_plan_and_decision(
                task_desc=task_desc,
                task_type=task_type,
                route=r,
                task_id=task_id,
                budget=runtime_budget,
                skills=benchmark_skill_mount_requests,
            )
        enrich_route_on_plateau(
            route=route,
            task_desc=task_desc,
            task_type=task_type,
            plateau=plateau,
            asi_ledger=asi_ledger,
            build_capability_plan_fn=build_plan_callback,
        )

    recent_window = recent[-max(1, history_window):]
    decisions = decide_auto_flow_routing(
        chosen_flow=chosen_flow_input,
        force_flow=force_flow,
        execution_profile=execution_profile,
        learn_gate_blocked=learn_gate_blocked,
        plateau_detected=plateau_detected,
        recent_window=recent_window,
        history_fail_threshold=history_fail_threshold,
    )
    chosen_flow = decisions["chosen_flow"]
    plateau_hard_pivot = decisions["plateau_hard_pivot"]
    nightshift_recommended = decisions["nightshift_recommended"]
    history_forced_baseline = decisions["history_forced_baseline"]
    recent_hyper_fails = decisions["recent_hyper_fails"]
    stage1_fail_signals = decisions["stage1_fail_signals"]

    phase_clock.mark("D")

    guard_hit = False
    setup_started_at = time.monotonic()
    target_path = (repo_root / target_file).resolve()
    if not target_path.exists():
        raise click.ClickException(f"Target file not found: {target_file}")
    # Run the child verifier with the interpreter that owns this process.
    # A temporary task repository does not have its own .venv, and resolving
    # a bare pytest binary can re-enter a different environment (or uv cache)
    # and hang before the target test starts.
    pytest_cmd = [sys.executable, "-m", "pytest", "-q", "--maxfail=1", test_file]
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
    # M2: symmetric behaviour applies only to model runs; the LLM-off lane is unchanged.
    symmetric_prompt = _symmetric_prompt_mode() and bool(llm_mode)
    test_path_for_prompt = Path(test_file) if Path(test_file).is_absolute() else repo_root / test_file
    visible_test_source = (
        test_path_for_prompt.read_text(encoding="utf-8")
        if symmetric_prompt and test_path_for_prompt.is_file()
        else ""
    )
    timing_breakdown_sec["context_pack_sec"] = round(time.monotonic() - context_started_at, 4)

    def _restore_baseline_files(restored_files: dict[Path, str | None], *, keep_target: bool) -> None:
        for path, original_text in restored_files.items():
            should_restore = not keep_target
            if should_restore and original_text is None:
                if path.exists():
                    path.unlink()
            elif should_restore:
                _write_source_text(path, original_text)

    def _run_baseline_apply() -> dict:
        start = time.monotonic()
        ok = False
        err = ""
        source = "local"
        patched = original_code
        generation_meta = local_baseline_meta()
        companion_edits: dict[Path, str] = {}
        restored_files: dict[Path, str | None] = {}
        seam_lock_task = ""
        seam_pre_stages: list[dict[str, Any]] = []
        seam_released: dict[str, list[str]] = {}
        apply_release: list[Any] = []

        apply_companions: list[dict[Path, str]] = []

        def _hold_apply_lock() -> bool:
            # Held from the in-place write until the row's files are settled (no check-then-write).
            # The lock covers the target AND every companion file written in place; any one
            # held by another task refuses the whole delivery.
            # The patch is delivered alone: the fixture-keyed local companion edits were deleted
            # with the answer table (#2339 follow-up).
            companions: dict[Path, str] = {}
            release = _post_candidate_seam.hold_target_lock(
                repo_root, target_file, [path for path in companions if path != target_path]
            )
            if release is None:
                return False
            apply_release.append(release)
            apply_companions.append(companions)
            return True

        try:
            patched, source, generation_meta = _build_baseline_patch(
                trial=0,
                original_code=original_code,
                task_desc=task_desc,
                route=route,
                llm_baseline_required=llm_baseline_required,
                llm_baseline=llm_baseline,
                task_desc_with_codeintel=task_desc_with_codeintel,
                repo_root=repo_root,
                task_type=task_type,
                test_source=visible_test_source,
                target_file=str(target_file),
                test_file=str(test_file),
                model_configured=bool(llm_mode),
            )
            if patched != original_code:
                # PR-2 seam: lock the target before the candidate is written (runtime-selected only).
                seam_lock_task, seam_pre_stages = _post_candidate_seam.lock_target_if_selected(
                    unified_receipt=_unified_receipt_from_meta(generation_meta),
                    task_id=_post_candidate_seam.seam_holder_id(repo_root, target_file),
                    workspace_root=repo_root,
                    target_file=target_file,
                )
            if patched == original_code:
                err = "no_mutation_generated"
            elif _post_candidate_seam.lock_denied(seam_pre_stages) or not _hold_apply_lock():
                # Another task holds the target: the candidate is never written (no delivery).
                err = "file_lock_denied"
            else:
                companion_edits = apply_companions[0]
                restored_files[target_path] = original_code
                _write_source_text(target_path, patched)
                for extra_path, extra_code in companion_edits.items():
                    if extra_path == target_path:
                        continue
                    restored_files[extra_path] = extra_path.read_text(encoding="utf-8") if extra_path.exists() else None
                    extra_path.parent.mkdir(parents=True, exist_ok=True)
                    _write_source_text(extra_path, extra_code)
                res = _run_visible_pytest(
                    pytest_cmd,
                    repo_root=repo_root,
                    target_path=target_path,
                    test_path=test_path_for_prompt,
                    original_code=original_code,
                    candidate_code=patched,
                    timeout_sec=timeout_sec,
                    companion_files=companion_edits,
                )
                ok = res.returncode == 0
                if not ok:
                    err = _visible_error(res, "pytest_failed")
        except subprocess.TimeoutExpired:
            err = "test_timeout"
        finally:
            # S20: in the like-for-like A/B the model's file stays delivered even when the visible
            # test fails, so the bench verifies it with the hidden test exactly like the bare arm.
            keep_model_delivery = symmetric_prompt and _is_symmetric_model_source(str(source))
            try:
                _restore_baseline_files(restored_files, keep_target=ok or keep_model_delivery)
            finally:
                for release in apply_release:
                    release()
                if seam_lock_task:
                    seam_released = _post_candidate_seam.release_target_lock(seam_lock_task)
        report = baseline_report_from_meta(source, generation_meta)
        lock_denied = err == "file_lock_denied"
        if lock_denied:
            report["file_lock_denied"] = True
        _apply_post_candidate_seam(
            report,
            generation_meta=generation_meta,
            task_id=_seam_task_id(task_id, target_file),
            target_path=target_path,
            test_file=test_path_for_prompt,
            original_code=original_code,
            candidate_code=original_code if lock_denied else patched,
            pre_stages=seam_pre_stages,
            released=seam_released,
            workspace_root=repo_root,
        )
        if symmetric_prompt and _is_symmetric_model_source(str(source)) and patched != original_code:
            # P1-2: identity of the model candidate, checked by the bench against the delivered file.
            report["model_candidate_sha256"] = hashlib.sha256(patched.encode("utf-8")).hexdigest()
            report["symmetric_model_delivery"] = True
        return {
            "flow": "baseline",
            "status": "SUCCESS" if ok else "FAILED",
            "elapsed_sec": round(time.monotonic() - start, 4),
            "error": err,
            "report": report,
        }

    def _run_baseline_probe() -> dict:
        # Probe run used by guard. Always restore original state.
        start = time.monotonic()
        ok = False
        err = ""
        source = "local"
        generation_meta = local_baseline_meta()
        patched = original_code
        restored_files: dict[Path, str | None] = {}
        probe_lock_task = ""
        probe_release: list[Any] = []

        probe_companions: list[dict[Path, str]] = []

        def _hold_probe_lock() -> bool:
            # Held from the in-place write until the original is restored (no check-then-write).
            # The lock covers the target AND every companion file written in place; any one
            # held by another task refuses the whole delivery.
            # The patch is delivered alone: the fixture-keyed local companion edits were deleted
            # with the answer table (#2339 follow-up).
            companions: dict[Path, str] = {}
            release = _post_candidate_seam.hold_target_lock(
                repo_root, target_file, [path for path in companions if path != target_path]
            )
            if release is None:
                return False
            probe_release.append(release)
            probe_companions.append(companions)
            return True

        try:
            patched, source, generation_meta = _build_baseline_patch(
                trial=0,
                original_code=original_code,
                task_desc=task_desc,
                route=route,
                llm_baseline_required=llm_baseline_required,
                llm_baseline=llm_baseline,
                task_desc_with_codeintel=task_desc_with_codeintel,
                repo_root=repo_root,
                task_type=task_type,
                test_source=visible_test_source,
                target_file=str(target_file),
                test_file=str(test_file),
                model_configured=bool(llm_mode),
            )
            probe_pre: list[dict[str, Any]] = []
            if patched != original_code:
                # PR-2 seam: the probe writes the candidate in place too -> same lock as apply.
                probe_lock_task, probe_pre = _post_candidate_seam.lock_target_if_selected(
                    unified_receipt=_unified_receipt_from_meta(generation_meta),
                    task_id=_post_candidate_seam.seam_holder_id(repo_root, target_file),
                    workspace_root=repo_root,
                    target_file=target_file,
                )
            if patched == original_code:
                err = "no_mutation_generated"
            elif _post_candidate_seam.lock_denied(probe_pre) or not _hold_probe_lock():
                err = "file_lock_denied"
            else:
                companion_edits = probe_companions[0]
                restored_files[target_path] = original_code
                _write_source_text(target_path, patched)
                for extra_path, extra_code in companion_edits.items():
                    if extra_path == target_path:
                        continue
                    restored_files[extra_path] = extra_path.read_text(encoding="utf-8") if extra_path.exists() else None
                    extra_path.parent.mkdir(parents=True, exist_ok=True)
                    _write_source_text(extra_path, extra_code)
                res = _run_visible_pytest(
                    pytest_cmd,
                    repo_root=repo_root,
                    target_path=target_path,
                    test_path=test_path_for_prompt,
                    original_code=original_code,
                    candidate_code=patched,
                    timeout_sec=timeout_sec,
                    companion_files=companion_edits,
                )
                ok = res.returncode == 0
                if not ok:
                    err = _visible_error(res, "pytest_failed")
        except subprocess.TimeoutExpired:
            err = "test_timeout"
        finally:
            try:
                _restore_baseline_files(restored_files, keep_target=False)
            finally:
                for release in probe_release:
                    release()
                if probe_lock_task:
                    _post_candidate_seam.release_target_lock(probe_lock_task)
        return {
            "flow": "baseline_probe",
            "status": "SUCCESS" if ok else "FAILED",
            "elapsed_sec": round(time.monotonic() - start, 4),
            "error": err,
            "report": baseline_report_from_meta(source, generation_meta),
            "_patch": patched if ok else None,
        }

    def _run_original_verification_rescue(previous_result: dict) -> dict:
        start = time.monotonic()
        _write_source_text(target_path, original_code)
        try:
            res = _run_visible_pytest(
                pytest_cmd,
                repo_root=repo_root,
                target_path=target_path,
                test_path=test_path_for_prompt,
                original_code=original_code,
                candidate_code=original_code,
                timeout_sec=timeout_sec,
            )
            ok = res.returncode == 0
            err = "" if ok else _visible_error(res, "original_pytest_failed")
        except subprocess.TimeoutExpired:
            ok = False
            err = "original_test_timeout"
        report = build_verification_only_rescue_report(previous_result, ok=ok)
        return {
            "flow": previous_result.get("flow", "hyper_sprint"),
            "status": "SUCCESS" if ok else "FAILED",
            "elapsed_sec": round(float(previous_result.get("elapsed_sec", 0.0) or 0.0) + (time.monotonic() - start), 4),
            "error": "" if ok else err,
            "report": report,
        }

    def _run_hyper_apply() -> dict:
        start = time.monotonic()
        breakdown: dict[str, float] = {}
        setup_started_at = time.monotonic()
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
        effective_max_rounds = execution_profile["effective_max_rounds"]
        if symmetric_prompt and llm_mode and not _bench_treatment_lane_active():
            # L3: exactly one model candidate, one round, in the counted A/B (strict lane). The
            # treatment lane (PR-3) keeps the profile counts, capped by NEXUS_LLM_CANDIDATE_CAP.
            effective_candidate_count = 1
            effective_max_rounds = 1
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
            max_rounds=effective_max_rounds,
            timeout_sec=timeout_sec,
            safe_mode=True,
            stage1_max_parallel=execution_profile["effective_stage1_max_parallel"],
            stage1_timeout_sec=effective_stage1_timeout,
            llm_mode=llm_mode,
            distant_scout_plan=distant_scout_plan,
            route_signals=planner_route_signals(route),
            **sprint_executor_flags,
        )
        breakdown["setup_sec"] = round(time.monotonic() - setup_started_at, 4)
        sprint_started_at = time.monotonic()
        res = run_hyper_sprint(repo_root=repo_root, config=cfg)
        breakdown["hyper_sprint_sec"] = round(time.monotonic() - sprint_started_at, 4)
        ok = res.status == "SUCCESS" and bool(res.patch)
        err = ""
        apply_started_at = time.monotonic()
        # H1 / P1-1: in the symmetric A/B the model candidate's file is delivered even when the
        # visible test fails (status stays FAILED); the bench's hidden-only gate decides.
        raw_model_sha = str(_mapping_get(getattr(res, "learning_trace", None), "model_candidate_sha256"))
        if symmetric_prompt and _bench_treatment_lane_active() and res.patch:
            # PR-3: the delivered candidate is the winner of the row's model candidates (last of
            # its lineage), bound only if its sha is one of the recorded raw model outputs.
            recorded = _mapping_get(getattr(res, "learning_trace", None), "model_candidate_sha256s")
            patch_sha = hashlib.sha256(str(res.patch).encode("utf-8")).hexdigest()
            raw_model_sha = patch_sha if isinstance(recorded, list) and patch_sha in recorded else ""
        symmetric_delivery = bool(
            symmetric_prompt
            and res.patch
            and _is_symmetric_model_source(str(getattr(res, "winner_source", "") or ""))
            # L2: the delivered patch must be the raw model candidate, byte for byte.
            and raw_model_sha
            and hashlib.sha256(str(res.patch).encode("utf-8")).hexdigest() == raw_model_sha
        )
        if (ok or symmetric_delivery) and not _post_candidate_seam.run_under_target_lock(
            repo_root, target_file, lambda: _write_source_text(target_path, res.patch)
        ):
            # The sprint released its lock; another task holds the target now: no delivery.
            # The write itself happens while holding the lock (acquire -> write -> release).
            ok = False
            symmetric_delivery = False
            err = "file_lock_denied"
        if not ok and not err:
            err = res.reason
        breakdown["patch_apply_sec"] = round(time.monotonic() - apply_started_at, 4)
        breakdown["total_sec"] = round(time.monotonic() - start, 4)
        report = build_hyper_sprint_report(
            res,
            effective_stage1_timeout_sec=effective_stage1_timeout,
            candidate_summaries=_candidate_summaries(list(getattr(res, "candidates", []) or [])),
            r_phase_breakdown_sec=breakdown,
        )
        if symmetric_delivery:
            report["model_candidate_sha256"] = raw_model_sha
            report["symmetric_model_delivery"] = True
        return {
            "flow": "hyper_sprint",
            "status": "SUCCESS" if ok else "FAILED",
            "elapsed_sec": round(time.monotonic() - start, 4),
            "error": err,
            "report": report,
        }

    baseline_probe = None
    early_baseline_shortcut = False
    baseline_probe_skipped = False
    if chosen_flow == "baseline":
        result = _run_baseline_apply()
        strategy_path = "baseline_only"
        baseline_report = result.get("report", {}) if isinstance(result.get("report"), dict) else {}
        baseline_model_attempted = int(baseline_report.get("model_calls", 0) or 0) > 0
        if (
            force_flow is None
            and llm_mode
            and ((llm_baseline and baseline_model_attempted) or not llm_baseline)
            and result.get("status") != "SUCCESS"
            and not symmetric_prompt
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
            forced_hyper_needs_probe = (
                forced_hyper
                and tuned_baseline_fast_sec <= 0
                and dynamic_timeout_multiplier > 0
                and min_dynamic_stage1_timeout < stage1_timeout_sec
            )
            if forced_hyper_needs_probe and not (symmetric_prompt and llm_mode):
                baseline_probe = _run_baseline_probe()
            else:
                baseline_probe_skipped = True
            result = _run_hyper_apply()
            if (
                result.get("status") != "SUCCESS"
                and str(task_type).startswith("cross_module_refactor")
                and verification_only_allowed
                and not symmetric_prompt
            ):
                result = _run_original_verification_rescue(result)
            if forced_hyper:
                strategy_path = "hyper_direct_forced"
            elif plateau_hard_pivot:
                strategy_path = "hyper_direct_plateau_distant_scout"
            else:
                strategy_path = "hyper_direct_hard_skip_probe" if skip_baseline_probe_for_hard else "hyper_direct_cross_module"
        elif symmetric_prompt and llm_mode:
            # L3: no probe + hyper (two model calls) in the counted A/B; one direct hyper attempt.
            baseline_probe_skipped = True
            result = _run_hyper_apply()
            strategy_path = "hyper_direct_symmetric"
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
                if (
                    isinstance(probe_patch, str)
                    and probe_patch
                    and probe_patch != original_code
                    and not _post_candidate_seam.run_under_target_lock(
                        repo_root, target_file, lambda: _write_source_text(target_path, probe_patch)
                    )
                ):
                    # The probe's lock is released; another task holds the target now.
                    result = {
                        "flow": "baseline",
                        "status": "FAILED",
                        "elapsed_sec": baseline_probe["elapsed_sec"],
                        "error": "file_lock_denied",
                        "report": {
                            **(baseline_probe.get("report", {}) if isinstance(baseline_probe.get("report"), dict) else {}),
                            "reused_from_probe": True,
                        },
                    }
                elif isinstance(probe_patch, str) and probe_patch and probe_patch != original_code:
                    # Written above while holding the target lock.
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
                        result["report"] = merge_guard_fallback_accounting(
                            result["report"],
                            hyper_flow=str(hyper_result_for_guard.get("flow", "")),
                            hyper_elapsed_sec=hyper_result_for_guard.get("elapsed_sec"),
                            hyper_report=hyper_report,
                        )
                    if fallback_succeeded:
                        chosen_flow = "baseline"
                        strategy_path = "hyper_guard_fallback_to_baseline"
                    else:
                        chosen_flow = "hyper_sprint"
                        strategy_path = "probe_then_hyper_guard_fallback_rejected"
    nightshift_auto_run = maybe_run_nightshift_after_hyper_failure(
        repo_root=repo_root,
        result=result,
        # L2: symmetric mode never re-runs the task through Nightshift.
        nightshift_recommended=nightshift_recommended and not (symmetric_prompt and llm_mode),
        task_desc=task_desc,
        target_file=target_file,
        test_file=test_file,
    )
    phase_clock.mark("R")

    baseline_probe_for_report = None
    if isinstance(baseline_probe, dict):
        baseline_probe_for_report = {k: v for k, v in baseline_probe.items() if k != "_patch"}

    phase_clock.restart()
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
    r_phase_breakdown = result_report.get("r_phase_breakdown_sec", {})
    if isinstance(r_phase_breakdown, dict):
        for key, value in r_phase_breakdown.items():
            try:
                timing_breakdown_sec[f"r_{key}"] = round(float(value), 4)
            except (TypeError, ValueError):
                continue
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
    winner_source = (
        result_report.get("winner_source")
        or result_report.get("source")
        or guard_fallback_from.get("winner_source")
        or ("nexus_rescue" if nexus_rescued else "local_only")
    )
    route = _refresh_route_for_runtime_candidate_factory(
        repo_root=repo_root,
        route=route,
        result=result,
        result_report=result_report,
        task_desc=task_desc,
        task_type=task_type,
    )
    self_heal_used = bool(
        "self_heal" in str(winner_source)
        or any("self_heal" in str(code) for code in result_report.get("error_codes", []))
    )
    governance_needed = any(
        token in (task_desc or "").lower()
        for token in ("governance", "policy", "secret", "authorization", "unsafe", "trust", "evidence")
    )
    mempalace_active = bool(hyper_learning_trace or gemini_invoked or governance_needed)
    mempalace_verified = bool(hyper_learning_trace.get("mempalace_verified", False) or governance_needed)
    receipt_slug = _safe_trace_slug(task_id or task_desc or "task")
    capability_evidence = _capability_evidence(
        result_report=result_report,
        learning_trace=hyper_learning_trace,
        nightshift_recommended=nightshift_recommended,
    )
    capability_evidence = apply_nightshift_auto_run(capability_evidence, nightshift_auto_run)
    capability_evidence = _augment_local_msa_bench_evidence(
        repo_root,
        task_id=task_id,
        task_desc=task_desc,
        task_type=task_type,
        evidence=capability_evidence,
        artifact_verified=artifact_verified,
        route_executor_flags=build_route_executor_flags(task_desc=task_desc, task_type=task_type, route=route),
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
        retrieval_refs = [
            str(item)
            for item in ((route.get("research_context", {}) or {}).get("retrieval_refs", []) or [])
            if str(item).strip()
        ]
        capability_evidence["research_used"] = True
        capability_evidence["research_refs"] = retrieval_refs[:3] or [f"research:{receipt_slug}:route_selected"]
        capability_evidence["research_gate_passed"] = bool(artifact_verified)
    # P-CONTAM-01 (#2199/#2216): record-only signal; it never changes research_gate_passed.
    try:
        from nexus.research.contamination_enforcement import record_flow_contamination_signal

        capability_evidence = record_flow_contamination_signal(
            capability_evidence,
            research_context=route.get("research_context"),
            task_desc=task_desc,
            log_root=repo_root,
            task_id=task_id,
        )
    except Exception:  # record-only signal must never break the auto-flow
        capability_evidence["research_contamination_signal"] = {
            "policy_id": "P-CONTAM-01",
            "mode": "record_only",
            "detected": None,
            "reason": "RESEARCH_CONTAMINATION_GUARD_ERROR",
            "terms": [],
        }
    capability_evidence["research_source_projects"] = list(RESEARCH_SOURCE_PROJECTS)
    autoreason_payload = build_autoreason_payload(
        result=result,
        result_report=result_report,
        hyper_learning_trace=hyper_learning_trace,
        route=route,
        task_desc=task_desc,
    )
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
    phase_clock.mark("A")
    context_memory_needed = "docs_code_sync" in str(task_type).lower() or any(
        token in (task_desc or "").lower() for token in ("context", "contract", "docs")
    )
    delivery_refs = [f"delivery:{receipt_slug}:artifact_tests_passed"] if artifact_verified else []
    memory_refs = [f"memory:{receipt_slug}:context_contract"] if artifact_verified and context_memory_needed else []
    artifact_refs = [f"artifact:{receipt_slug}:tests_passed"] if artifact_verified else []
    claim_refs = [f"claim:{receipt_slug}:verified_delivery"] if artifact_verified else []
    belief_refs = [f"belief:{receipt_slug}:confidence:{float(execution_profile.get('belief_confidence', 1.0) or 1.0):.2f}"] if artifact_verified else []
    mempalace_refs = [f"mempalace:{receipt_slug}:policy_checked" if (mempalace_active or governance_needed) else f"mempalace:{receipt_slug}:bypass_non_llm"] if artifact_verified else []
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
            "research_contamination_signal": capability_evidence.get("research_contamination_signal"),
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
    nexus_failure_analysis = build_nexus_failure_analysis(
        artifact_verified=artifact_verified,
        tests_passed=tests_passed,
        artifact_summary=artifact_summary,
        research_doctor=research_doctor,
        claim_probe=claim_probe,
        gemini_invoked=gemini_invoked,
        nexus_context_delivered=True,
        self_heal_used=self_heal_used,
        result_report=result_report,
    )
    nexus_usage_trace["research_doctor"] = research_doctor
    nexus_usage_trace["claim_probe"] = claim_probe
    nexus_usage_trace["nexus_failure_analysis"] = nexus_failure_analysis
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
        capability_plan = CapabilityPlanner(shared_playbook_root=REPO_ROOT).plan(
            task_desc=task_desc,
            task_type=task_type,
            route=route,
            pillars=nexus_usage_trace["pillars"],
            codeintel=codeintel_evidence,
            phase_trace=nexus_usage_trace["phase_trace"],
            budget=runtime_budget,
            skills=benchmark_skill_mount_requests,
        )
        capability_plan_payload = capability_plan.to_dict()
    # Archived nodes are never selectable (integration_manager, archived 2026-10-13).
    capability_plan_payload = drop_archived_capabilities(capability_plan_payload)
    nexus_usage_trace["capability_plan"] = capability_plan_payload
    nexus_usage_trace["route_decision"] = drop_archived_capabilities(route_decision_payload or build_route_decision(
        task_id=task_id or _safe_trace_slug(task_desc),
        task_desc=task_desc,
        task_type=task_type,
        recommended_flow=str(route.get("recommended_flow") or ""),
        plan=CapabilityPlanner(shared_playbook_root=REPO_ROOT).plan(
            task_desc=task_desc,
            task_type=task_type,
            route=route,
            pillars=nexus_usage_trace["pillars"],
            codeintel=codeintel_evidence,
            phase_trace=nexus_usage_trace["phase_trace"],
            budget=runtime_budget,
            skills=benchmark_skill_mount_requests,
        ),
    ).to_dict())
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
    s2t_trace = _record_autoreason_s2t_trace(
        repo_root=repo_root,
        task_id=task_id,
        receipt_slug=receipt_slug,
        autoreason_payload=autoreason_payload,
        result_report=result_report,
        artifact_verified=artifact_verified,
        normalized_success_criteria=normalized_success_criteria,
        route_decision_ref=str(nexus_usage_trace.get("route_decision", {}).get("task_id", "")),
    )
    if s2t_trace:
        nexus_usage_trace["s2t"] = s2t_trace
        nexus_usage_trace["capabilities"]["s2t_trace_present"] = True
        nexus_usage_trace["capabilities"]["s2t_candidate_count"] = int(s2t_trace["candidate_count"])
    recursive_research = _rlm_research_trace_enabled()
    if _rlm_trace_enabled() or recursive_research:
        rlm_budget_summary: dict[str, Any] = {}
        if recursive_research:
            nexus_usage_trace["rlm_loop_phase"] = "X"
            nexus_usage_trace["rlm_x_loop_budget_observed"] = True
            rlm_budget_summary = _rlm_x_loop_budget_summary(
                result=result,
                phase_wall_sec=phase_wall_sec,
                candidate_count=candidate_count,
            )
            nexus_usage_trace["rlm_x_loop_budget_summary"] = rlm_budget_summary
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
        rlm_orchestration = build_bounded_rlm_orchestration_receipt(
            gate_passed=bool(artifact_verified),
            belief_confidence=float(route_confidence or 0.0),
            current_tokens=int(result_report.get("total_tokens", 0) or 0),
            x_observations=int(rlm_budget_summary.get("iterations_observed", 0) or 0),
            r_observations=0 if recursive_research else 1,
        )
        nexus_usage_trace["rlm_bounded_orchestration_receipt"] = rlm_orchestration
        nexus_usage_trace["rlm_runtime_decision_receipt"] = rlm_orchestration["final_decision_receipt"]
        nexus_usage_trace["rlm_nightshift_handoff_receipt"] = rlm_orchestration["nightshift_handoff_receipt"]
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
    nexus_usage_trace["unified_runtime_capabilities"] = _unified_runtime_capability_stages(result_report)
    nexus_usage_trace["capability_receipts"] = build_capability_receipt_payloads(capability_plan_payload, nexus_usage_trace)
    for receipt in nexus_usage_trace["capability_receipts"]:
        if isinstance(receipt, dict) and receipt.get("name") == "research":
            receipt["source_projects"] = list(RESEARCH_SOURCE_PROJECTS)
            receipt["research_stack"] = research_stack_contract()
    skill_mount_runtime = _build_runtime_skill_mount_contracts(
        capability_plan_payload=capability_plan_payload,
        route_decision_payload=nexus_usage_trace.get("route_decision", {}),
        capability_receipts=nexus_usage_trace["capability_receipts"],
    )
    if skill_mount_runtime["skill_mount_contracts"]:
        nexus_usage_trace["skill_mount_contracts"] = skill_mount_runtime["skill_mount_contracts"]
    if skill_mount_runtime["skill_mount_violations"]:
        nexus_usage_trace["skill_mount_violations"] = skill_mount_runtime["skill_mount_violations"]
    openseeker_trace = build_openseeker_trace(
        usage_trace=nexus_usage_trace,
        capability_receipts=nexus_usage_trace["capability_receipts"],
    )
    nexus_usage_trace["openseeker_alignment"] = openseeker_trace
    nexus_usage_trace["capabilities"]["trajectory_step_count"] = openseeker_trace["trajectory_step_count"]
    nexus_usage_trace["capabilities"]["evidence_hop_count"] = openseeker_trace["evidence_hop_count"]
    nexus_usage_trace["capabilities"]["tool_action_count"] = openseeker_trace["tool_action_count"]
    nexus_usage_trace["capabilities"]["low_step_filtered"] = openseeker_trace["low_step_filtered"]
    learning_experience = build_learning_experience(
        task_id=task_id or receipt_slug,
        task_type=task_type,
        usage_trace=nexus_usage_trace,
        capability_receipts=nexus_usage_trace["capability_receipts"],
        route_decision_ref=str(nexus_usage_trace.get("route_decision", {}).get("task_id", "")),
        learning_steward_decision=str(learn_phase_slo.get("status") or "shadow"),
    )
    nexus_usage_trace["learning_experience"] = learning_experience.to_dict()
    learning_decision = LearningSteward().decide_experience(learning_experience)
    autodata_quality_row = {
        "task_id": learning_experience.task_id,
        "eligible_for_training": bool(
            learning_experience.outcome == "verified_success"
            and learning_experience.s2t_trace_refs
            and not openseeker_trace.get("low_step_filtered", False)
            and not openseeker_trace.get("single_source_claim", False)
        ),
        "reasons": [
            reason
            for reason, failed in (
                ("low_step_trajectory", bool(openseeker_trace.get("low_step_filtered", False))),
                ("single_source_claim", bool(openseeker_trace.get("single_source_claim", False))),
                ("missing_s2t_trace_refs", not bool(learning_experience.s2t_trace_refs)),
                ("outcome_not_verified_success", learning_experience.outcome != "verified_success"),
            )
            if failed
        ],
        "trajectory_steps": int(openseeker_trace.get("trajectory_step_count", 0) or 0),
        "information_density": float(
            (
                int(openseeker_trace.get("evidence_hop_count", 0) or 0)
                + int(openseeker_trace.get("tool_action_count", 0) or 0)
            )
            / max(1, int(openseeker_trace.get("trajectory_step_count", 0) or 0))
        ),
    }
    nexus_usage_trace["learning_projection"] = {
        "nexus_policy": project_nexus_policy(learning_experience),
        "model_training": apply_autodata_quality_gate(project_model_training(learning_experience), autodata_quality_row),
        "dual_learning_decision": asdict(learning_decision),
    }
    _persist_auto_flow_learning_projection(
        repo_root=repo_root,
        learning_projection=nexus_usage_trace["learning_projection"],
        learning_decision=learning_decision,
        learning_experience=learning_experience,
        receipt_slug=receipt_slug,
        s2t_trace=s2t_trace,
        autodata_quality_row=autodata_quality_row,
        outcome_record_factory=lambda: EpisodeOutcomeRecord.from_task(
            task_id=task_id or receipt_slug,
            task_type=task_type,
            task_desc=task_desc,
            solved=learning_experience.outcome == "verified_success",
            wall_duration_sec=float(result.get("elapsed_sec", 0.0) or 0.0),
            total_tokens_used=int(result_report.get("total_tokens", 0) or 0),
            trust_mismatch=bool(nexus_usage_trace.get("trust_mismatch", False)),
            receipts=nexus_usage_trace["capability_receipts"],
        ),
    )

    payload = build_auto_flow_payload(
        AutoFlowPayloadParts(
            task_desc=task_desc,
            task_type=task_type,
            asi_ledger=asi_ledger,
            route=route,
            execution_profile=execution_profile,
            chosen_flow=chosen_flow,
            guard_hit=guard_hit,
            early_baseline_shortcut=early_baseline_shortcut,
            history_forced_baseline=history_forced_baseline,
            learn_gate_blocked=learn_gate_blocked,
            force_flow=force_flow,
            recent_hyper_fails=recent_hyper_fails,
            nightshift_recommended=nightshift_recommended,
            stage1_fail_signals=stage1_fail_signals,
            history_window=history_window,
            baseline_fast_sec=tuned_baseline_fast_sec,
            max_time_ratio_guard=max_time_ratio_guard,
            baseline_probe_skipped=baseline_probe_skipped,
            baseline_probe=baseline_probe_for_report,
            plateau_hard_pivot=plateau_hard_pivot,
            learn_phase_slo=learn_phase_slo,
            result=result,
            claim_check=claim_check,
            hitl=hitl,
            research_preflight=research_preflight,
            route_confidence=route_confidence,
            strategy_path=strategy_path,
            plateau=plateau,
            artifact_summary=artifact_summary,
            success_criteria_name=normalized_success_criteria,
            mutation_required=mutation_required,
            verification_only_allowed=verification_only_allowed,
            nexus_usage_trace=nexus_usage_trace,
            cli_elapsed_sec=time.monotonic() - flow_started_at,
            phase_wall_sec=phase_wall_sec,
            timing_breakdown_sec=timing_breakdown_sec,
        )
    )
    out_path = (repo_root / report_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if output_file:
        written = _write_output_file(repo_root, output_file, payload)
        payload["io"]["output_written"] = True
        payload["io"]["output_path"] = str(written)
        # keep report + output payload in sync
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    phase_clock.restart()
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
    nexus_failure_analysis = build_nexus_failure_analysis(
        artifact_verified=artifact_verified,
        tests_passed=tests_passed,
        artifact_summary=artifact_summary,
        research_doctor=research_doctor,
        claim_probe=claim_probe,
        gemini_invoked=gemini_invoked,
        nexus_context_delivered=bool(payload["nexus_usage_trace"].get("nexus_context_delivered", False)),
        self_heal_used=self_heal_used,
        result_report=result_report,
    )
    payload["nexus_failure_analysis"] = nexus_failure_analysis
    payload["nexus_usage_trace"]["research_doctor"] = research_doctor
    payload["nexus_usage_trace"]["nexus_failure_analysis"] = nexus_failure_analysis
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
    history_store.write_recent_for(target_file=target_file, test_file=test_file, recent=recent, max_items=200)
    phase_clock.mark("C")
    apply_auto_flow_timing_payload(
        payload,
        cli_elapsed_sec=time.monotonic() - flow_started_at,
        phase_wall_sec=phase_wall_sec,
        breakdown_sec=timing_breakdown_sec,
    )
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if payload["io"].get("output_path"):
        Path(str(payload["io"]["output_path"])).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload, out_path


def _persist_auto_flow_learning_projection(
    *,
    repo_root: Path,
    learning_projection: dict[str, Any],
    learning_decision: Any,
    learning_experience: Any,
    receipt_slug: str,
    s2t_trace: Any,
    autodata_quality_row: dict[str, Any],
    outcome_record_factory: Any,
) -> None:
    """Write the auto-flow learning projection: promoted policy, training export, outcome memory.

    #2721 L-B: with ``NEXUS_STATE_READ_ONLY=1`` (re-read at call time) all three writes are
    skipped, an info line says so, nothing raises and no write is reported as a success.
    With the switch unset the behaviour is the old one.
    """
    from nexus.core.state_root import persistent_state_root, rebase_state_path, state_read_only

    if state_read_only():
        logging.getLogger(__name__).info(
            "[AutoFlow] NEXUS_STATE_READ_ONLY=1: skipped promoted policy, model training "
            "export and outcome-memory writes; not a learning success"
        )
        learning_projection["promoted_policy"] = {"status": "SKIPPED_READ_ONLY"}
        learning_projection["outcome_memory"] = {
            "schema_version": "nexus_outcome_memory_write.v1",
            "status": "SKIPPED_READ_ONLY",
            "reason": "NEXUS_STATE_READ_ONLY",
        }
        return
    if learning_decision.nexus_action == "PROMOTE_NEXUS":
        promoted_policy = save_promoted_learning_policy(
            rebase_state_path(repo_root / DEFAULT_PROMOTED_POLICY_PATH),  # #2688
            [learning_experience],
        )
        learning_projection["promoted_policy"] = promoted_policy
        learning_projection["promoted_policy_path"] = str(DEFAULT_PROMOTED_POLICY_PATH)
    else:
        learning_projection["promoted_policy"] = {"status": "not_promoted"}
    model_training_export = write_auto_flow_model_training_export(
        repo_root=repo_root,
        receipt_slug=receipt_slug,
        s2t_trace=s2t_trace,
        experiences=[learning_experience],
        quality_rows=[autodata_quality_row],
    )
    if model_training_export:
        learning_projection["model_training_export"] = model_training_export
    try:
        outcome_memory = OutcomeMemoryManager.save_episode_and_tune_sync(
            outcome_record_factory(),
            project_root=persistent_state_root(repo_root),
        )
    except (OSError, ValueError, TypeError) as exc:
        outcome_memory = {
            "schema_version": "nexus_outcome_memory_write.v1",
            "status": "RETURN",
            "reason": str(exc),
        }
    learning_projection["outcome_memory"] = outcome_memory
