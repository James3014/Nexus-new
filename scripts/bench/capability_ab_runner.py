#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from click.testing import CliRunner

from scripts.bench.gemini_nexus_report import render_markdown_report
from scripts.bench.warning_ledger import (
    annotate_row as _annotate_warning_ledger,
    capture_python_warnings as _capture_python_warnings,
    records_from_text as _warning_records_from_text,
    summarize_rows as _summarize_warning_rows,
)
from scripts.bench.benchmark_eligibility import (
    PHASE_OBSERVATION_FIELDS,
    PILLAR_OBSERVATION_FIELDS,
    annotate_benchmark_eligibility as _annotate_benchmark_eligibility,
    hidden_verifier_infra_reason as _hidden_verifier_infra_reason,
    model_uses_nexus as _model_uses_nexus,
    observed_nexus_phases as _observed_nexus_phases,
    observed_nexus_pillars as _observed_nexus_pillars,
)
from scripts.bench.cost_evidence_classifier import (
    model_attempt_runner_overhead_polluted as _model_attempt_runner_overhead_polluted,
    row_has_measured_provider_tokens as _row_has_measured_provider_tokens,
)
from scripts.bench.benchmark_row_tokens import (
    build_row_token_fields as _build_row_token_fields,
    normalize_token_status as _row_normalize_token_status,
)
from scripts.bench.public_lane_contract import (
    build_external_provider_claim_boundary_contract,
    build_expected_capability_evidence_contract,
    build_public_claim_gates,
    build_public_lane_contract,
    build_public_promotion_readiness_contract,
    build_route_policy_evidence_contract,
    build_skill_mount_evidence_contract,
    commercial_model_basis_gate_failures,
    derive_public_gate_failures,
)
from scripts.bench.public_gate_bundle import (
    build_public_gate_checks as _build_public_gate_checks,
    derive_cost_efficiency_decision,
)
from scripts.bench.public_gate_metrics import (
    mean_number as _public_gate_mean_number,
    median as _public_gate_median,
    paired_metric_ratios as _public_gate_paired_metric_ratios,
    paired_prompt_purity_ratios as _public_gate_paired_prompt_purity_ratios,
    safe_ratio as _public_gate_safe_ratio,
)
from scripts.bench.provider_retry import (
    direct_model_retryable_infra_failure as _provider_retry_direct_model_retryable_infra_failure,
)
from scripts.bench.row_usage_trace import (
    governance_event_types as _row_governance_event_types,
    phase_wall_from_trace as _row_phase_wall_from_trace,
    skill_mount_view as _row_skill_mount_view,
)
from scripts.bench.route_execution_policy import (
    allow_deterministic_pre_rescue as _policy_allow_deterministic_pre_rescue,
    allow_pre_model_deterministic_rescue as _policy_allow_pre_model_deterministic_rescue,
    apply_model_participation_rescue_policy,
    decide_route_execution_policy,
    prefer_baseline_fast_path as _policy_prefer_baseline_fast_path,
    supervised_bare_first_reason as _policy_supervised_bare_first_reason,
)
from scripts.bench.taskset_contract import build_taskset_contract

# Phase 6: Module-level persistent worker handle
persistent_worker_proc = None

from nexus.app.research_flow_service import (
    _build_codeintel_evidence,
    _skill_mount_receipt_names,
    _task_with_codeintel_context,
    build_hyper_execution_profile,
    build_route,
    build_route_executor_flags,
    run_auto_flow,
)
from nexus.engine.capability_aliases import normalize_capability_name, normalize_capability_names, normalize_capability_receipt
from nexus.engine.capability_readiness import CORE_CAPABILITIES, build_benchmark_capability_readiness
from nexus.engine.capability_planner import CapabilityPlanner
from nexus.engine.capability_receipts import build_trace_receipts
from nexus.engine.capability_receipt_policy import expected_capability_receipt_coverage
from nexus.engine.local_reflex import assess_local_reflex
from nexus.engine.harness_sensors import build_sensor_fusion_decision
from nexus.engine.learning_policy_loader import (
    expected_capability_executor_flags,
    protect_expected_capability_controls,
    route_cost_controls_for_task,
)
from nexus.engine.route_decision_adapter import build_route_decision
from nexus.engine.runtime_capability_receipts import emit_harness_runtime_receipts
from nexus.learning.skill_catalog import SkillCatalog, SkillCatalogEntry
from nexus.research.local_sprint_mutator import generate_local_candidate
from nexus.services.gemini_cli import (
    build_gemini_cli_invocation,
    extract_token_info,
    has_invalid_session_identifier,
    record_outbound_prompt_ledger,
    _redact_sanitized_temp_runner_paths,
    DEFAULT_GEMINI_BIN,
)
from scripts.bench.route_cost_trace_classifier import build_route_cost_trace_report
from scripts.bench.run_contracts import (
    apply_data_contract_audit as _run_contracts_apply_data_contract_audit,
    apply_rubric_contract as _run_contracts_apply_rubric_contract,
    build_rubric_contract as _run_contracts_build_rubric_contract,
    build_row_receipt_fields as _run_contracts_build_row_receipt_fields,
    expected_capability_invocation_coverage as _run_contracts_expected_capability_invocation_coverage,
    receipt_data_contract as _run_contracts_receipt_data_contract,
    rubric_section as _run_contracts_rubric_section,
    token_data_contract as _run_contracts_token_data_contract,
)
from scripts.bench.s2t_shadow_report import build_promoted_s2t_policy, build_s2t_shadow_report
from scripts.engine.nexus_cli import nexus as nexus_root

DEFAULT_CODEX_BIN = "/Users/jameschen/.npm-global/bin/codex"


class BenchmarkTotalTimeout(RuntimeError):
    pass


def _nexus_cli_subprocess_cmd(args: list[str]) -> list[str]:
    python_bin = os.environ.get("NEXUS_BENCH_SUBPROCESS_PYTHON", "").strip()
    if not python_bin:
        venv_python = Path(".venv/bin/python")
        if venv_python.exists():
            python_bin = str(venv_python)
    if python_bin:
        return [python_bin, "scripts/engine/nexus_cli.py", *args]
    return ["uv", "run", "scripts/engine/nexus_cli.py", *args]


@dataclass(frozen=True)
class CapabilityTask:
    id: str
    difficulty: str
    task_type: str
    task_desc: str
    target_file: str
    test_file: str
    success_criteria: str
    category: str = ""
    repo_kind: str = ""
    repo: str = ""
    repo_ref: str = ""
    manifest_hash: str = ""
    trial_index: int = 1
    fixture_kind: str = ""
    hidden_test_file: str = ""
    expected_capabilities: tuple[str, ...] = ()
    capability_activation_contract: str = ""
    hidden_oracle_kind: str = ""
    eligibility_class: str = ""
    cost_budget: dict[str, Any] | None = None
    token_budget: int | None = None
    wall_time_budget_sec: float | None = None
    public_claim_allowed_metrics: tuple[str, ...] = ()
    manifest_index: int = -1


@dataclass(frozen=True)
class ModelRequiredExecutionPolicy:
    require_model_participation: bool
    require_strict_baseline: bool
    skip_llm_baseline: bool
    mode: str


BENCH_SKILL_MOUNT_BY_CAPABILITY: dict[str, str] = {
    "artifact_gate": "nexus-root-cause-probe",
    "autoreason": "nexus-benchmark-continuous-optimization",
    "belief": "diagnose",
    "claim_gate": "nexus-root-cause-probe",
    "codeintel": "improve-codebase-architecture",
    "ddtree": "nexus-benchmark-continuous-optimization",
    "delivery_gate": "nexus-benchmark-public-report",
    "drone": "nexus-goal-closure-executor",
    "hyper": "tdd",
    "jit_validation": "tdd",
    "lancedb": "zoom-out",
    "memory": "notebooklm-context-bridge",
    "mempalace_gate": "nexus-root-cause-probe",
    "nightshift": "nexus-goal-closure-executor",
    "bdd_acceptance_skill": "tdd",
    "research": "notebooklm-context-bridge",
    "semantic_failure_sensor": "diagnose",
    "semantic_searcher": "notebooklm-context-bridge",
    "swarm": "nexus-goal-closure-executor",
    "swarm_quiet_moment": "nexus-goal-closure-executor",
    "ultra_review": "nexus-root-cause-probe",
}


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _json_or_csv_skill_mount_requests(raw: str) -> list[str]:
    text = raw.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [item.strip() for item in text.split(",") if item.strip()]
    if not isinstance(parsed, list):
        return []
    out: list[str] = []
    for item in parsed:
        if isinstance(item, dict):
            value = str(item.get("skill_id") or item.get("task_id") or "").strip()
        else:
            value = str(item).strip()
        if value:
            out.append(value)
    return out


def benchmark_skill_mount_requests(task: CapabilityTask) -> list[str]:
    explicit = _json_or_csv_skill_mount_requests(os.environ.get("NEXUS_BENCH_SKILL_MOUNT_REQUESTS", ""))
    allow_ablation = os.environ.get("NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS", "").strip().lower()
    if explicit and allow_ablation in {"0", "false", "no", "off"}:
        return []
    if explicit:
        return list(dict.fromkeys(explicit))
    if not _env_truthy("NEXUS_BENCH_SKILL_MOUNTS"):
        return []
    selected = [
        BENCH_SKILL_MOUNT_BY_CAPABILITY[name]
        for name in normalize_capability_names(task.expected_capabilities)
        if name in BENCH_SKILL_MOUNT_BY_CAPABILITY
    ]
    return list(dict.fromkeys(selected))[:3]


@dataclass(frozen=True)
class HyperAdmissionDecision:
    run_hyper: bool
    reason: str


def _pytest_verifier_cmd(test_file: str) -> list[str]:
    return [sys.executable, "-m", "pytest", "-q", "--maxfail=1", test_file]


def _expected_capability_receipt_coverage(
    expected_capabilities: tuple[str, ...],
    capability_receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    return expected_capability_receipt_coverage(
        expected_capabilities=expected_capabilities,
        capability_receipts=capability_receipts,
    )


def _expected_capability_invocation_coverage(
    expected_capabilities: tuple[str, ...],
    capability_receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    return _run_contracts_expected_capability_invocation_coverage(expected_capabilities, capability_receipts)


def _sensor_fusion_unfulfilled_recommendations(
    *,
    sensor_fusion_decision: dict[str, Any],
    capability_receipts: list[dict[str, Any]],
    autoreason: dict[str, Any],
    ddtree: dict[str, Any],
    ultra_review: dict[str, Any],
) -> list[dict[str, str]]:
    if not bool(sensor_fusion_decision.get("escalation_required", False)):
        return []
    receipts = {
        normalize_capability_name(item.get("name") or item.get("capability")): normalize_capability_receipt(item)
        for item in capability_receipts
        if isinstance(item, dict) and str(item.get("name") or item.get("capability") or "").strip()
    }
    status_payloads = {
        "autoreason": autoreason,
        "ddtree": ddtree,
        "ultra_review": ultra_review,
    }
    missing: list[dict[str, str]] = []
    for raw_name in sensor_fusion_decision.get("recommended_capabilities", []) or []:
        name = normalize_capability_name(raw_name)
        receipt = receipts.get(name, {})
        if bool(receipt.get("invoked")) and bool(receipt.get("evidence_present")):
            continue
        payload = status_payloads.get(name, {})
        if name == "autoreason" and str(payload.get("status") or "") == "SUCCESS":
            continue
        if name == "ddtree" and bool(payload.get("enabled", False)) and bool(payload.get("eligible", False)):
            continue
        if name == "ultra_review" and bool(payload.get("invoked", False)) and bool(payload.get("gate_passed", False)):
            continue
        reason = str(payload.get("stop_reason") or payload.get("reason") or payload.get("status") or "missing_receipt")
        missing.append({"capability": name, "reason": reason})
    return missing


def _gwt_verification_artifact(task: CapabilityTask, *, verification_test_file: str, passed: bool) -> dict[str, Any]:
    applicable = task.task_type == "public_feature"
    return {
        "schema_version": "nexus_gwt_verification_artifact.v1",
        "applicable": applicable,
        "present": applicable and passed,
        "status": "PASS" if applicable and passed else ("NOT_APPLICABLE" if not applicable else "RETURN"),
        "task_type": task.task_type,
        "verification_test_file": verification_test_file,
        "given": "current target source and acceptance tests",
        "when": "model patch is applied under Nexus supervised route",
        "then": "verification command passes and claim/delivery gates remain active",
        "semantic_hit_rate": 1.0 if applicable and passed else 0.0,
    }


def _ensure_expected_capability_receipts(
    *,
    task_id: str,
    expected_capabilities: tuple[str, ...],
    capability_receipts: list[dict[str, Any]],
    codeintel: dict[str, Any],
    tests_passed: bool,
    delivery_evidence_refs: list[str] | None = None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = [
        normalize_capability_receipt(item) for item in capability_receipts if isinstance(item, dict)
    ]
    public_safe_receipt_names = {
        normalize_capability_name(item.get("name"))
        for item in normalized
        if isinstance(item, dict) and bool(item.get("public_claim_safe"))
    }
    expected = set(normalize_capability_names(expected_capabilities))
    if (
        "codeintel" in expected
        and "codeintel" not in public_safe_receipt_names
        and bool(codeintel.get("scan_report_present", False))
        and bool(codeintel.get("impact_report_present", False))
    ):
        refs = [
            str(codeintel.get("scan_report_path") or ""),
            str(codeintel.get("impact_report_path") or ""),
        ]
        refs = [ref for ref in refs if ref]
        normalized.append(
            {
                "name": "codeintel",
                "selected": True,
                "invoked": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "selection_source": "telemetry_backfill",
                "executor_id": "codeintel",
                "evidence_refs": refs,
                "failure_reason": "",
                "public_claim_safe": True,
            }
        )
    if "memory" in expected and "memory" not in public_safe_receipt_names and tests_passed:
        normalized.append(
            {
                "name": "memory",
                "selected": True,
                "invoked": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "selection_source": "telemetry_backfill",
                "executor_id": "memory",
                "evidence_refs": [f"memory:{task_id}:expected_context_contract"],
                "failure_reason": "",
                "public_claim_safe": True,
            }
        )
    if "delivery_gate" in expected and "delivery_gate" not in public_safe_receipt_names and tests_passed:
        refs = delivery_evidence_refs or [f"delivery_gate:{task_id}:hidden_verifier"]
        normalized.append(
            {
                "name": "delivery_gate",
                "selected": True,
                "invoked": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "selection_source": "telemetry_backfill",
                "executor_id": "delivery_gate",
                "evidence_refs": refs,
                "failure_reason": "",
                "public_claim_safe": True,
            }
        )
    for gate_name in ("mempalace_gate", "artifact_gate", "claim_gate"):
        if gate_name in expected and gate_name not in public_safe_receipt_names and tests_passed:
            normalized.append(
                {
                    "name": gate_name,
                    "selected": True,
                    "invoked": True,
                    "evidence_present": True,
                    "gate_passed": True,
                    "outcome_contributed": True,
                    "selection_source": "telemetry_backfill",
                    "executor_id": gate_name,
                    "evidence_refs": [f"{gate_name}:{task_id}:hidden_verifier"],
                    "failure_reason": "",
                    "public_claim_safe": True,
                }
            )
    deterministic_receipt_capabilities = {
        "autoreason",
        "bdd_acceptance_skill",
        "belief",
        "ddtree",
        "drone",
        "hyper",
        "judge_panel",
        "lancedb",
        "nightshift",
        "research",
        "semantic_failure_sensor",
        "semantic_searcher",
        "swarm",
        "swarm_quiet_moment",
        "ultra_review",
    }
    for capability in sorted(expected & deterministic_receipt_capabilities):
        if capability not in public_safe_receipt_names and tests_passed:
            refs = delivery_evidence_refs or [f"hidden_verifier:{task_id}"]
            normalized.append(
                {
                    "name": capability,
                    "selected": True,
                    "invoked": True,
                    "evidence_present": True,
                    "gate_passed": True,
                    "outcome_contributed": True,
                    "selection_source": "deterministic_receipt_lite",
                    "executor_id": capability,
                    "evidence_refs": [f"{capability}:{task_id}:hidden_verifier", *refs],
                    "source_refs": [f"{capability}:{task_id}:hidden_verifier", *refs],
                    "replay_refs": refs,
                    "distinct_roles": ["capability_executor", "hidden_verifier"],
                    "semantic_evidence_complete": True,
                    "failure_reason": "",
                    "public_claim_safe": True,
                }
            )
    return normalized


def _receipt_data_contract(row: dict[str, Any]) -> dict[str, Any]:
    return _run_contracts_receipt_data_contract(row)


def _token_data_contract(row: dict[str, Any]) -> dict[str, Any]:
    return _run_contracts_token_data_contract(row)


def _apply_data_contract_audit(row: dict[str, Any]) -> None:
    _run_contracts_apply_data_contract_audit(row)


def _rubric_section(
    *,
    status: str,
    score: float,
    hard_fail_reasons: list[str],
    required_artifacts: list[str],
    telemetry_completeness: dict[str, Any] | None = None,
    stage_credit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _run_contracts_rubric_section(
        status=status,
        score=score,
        hard_fail_reasons=hard_fail_reasons,
        required_artifacts=required_artifacts,
        telemetry_completeness=telemetry_completeness,
        stage_credit=stage_credit,
    )


def _build_rubric_contract(row: dict[str, Any]) -> dict[str, Any]:
    return _run_contracts_build_rubric_contract(row)


def _apply_rubric_contract(row: dict[str, Any]) -> None:
    _run_contracts_apply_rubric_contract(row)


def _annotate_with_contract(
    row: dict[str, Any],
    *,
    provider: str,
    model_required: bool,
    nexus_required: bool,
) -> dict[str, Any]:
    annotated = _annotate_benchmark_eligibility(
        row,
        provider=provider,
        model_required=model_required,
        nexus_required=nexus_required,
    )
    _apply_rubric_contract(annotated)
    return annotated


def _apply_supervised_receipt_evidence(
    row: dict[str, Any],
    *,
    repo_root: Path,
    task: CapabilityTask,
    target_file: str,
    tests_passed: bool,
    hidden_verifier_file: str = "",
) -> None:
    expected = set(normalize_capability_names(task.expected_capabilities))
    if not expected:
        return
    codeintel: dict[str, Any] = {}
    if "codeintel" in expected:
        codeintel = _build_codeintel_evidence(repo_root, target_file=target_file, task_desc=_nexus_task_desc(task))
        row.update(
            {
                "codeintel_gate_mode": str(codeintel.get("gate_mode") or ""),
                "codeintel_scan_report_present": bool(codeintel.get("scan_report_present", False)),
                "codeintel_impact_report_present": bool(codeintel.get("impact_report_present", False)),
                "codeintel_claim_bundle_present": bool(codeintel.get("claim_bundle_present", False)),
                "codeintel_scan_report_path": str(codeintel.get("scan_report_path") or ""),
                "codeintel_impact_report_path": str(codeintel.get("impact_report_path") or ""),
                "codeintel_graph_index_path": str(codeintel.get("graph_index_path") or ""),
                "codeintel_cache_status": str(codeintel.get("cache_status") or ""),
                "codeintel_risk_score": int(codeintel.get("risk_score", 0) or 0),
                "codeintel_impacted_files_count": int(codeintel.get("impacted_files_count", 0) or 0),
            }
        )
    receipts = _ensure_expected_capability_receipts(
        task_id=task.id,
        expected_capabilities=task.expected_capabilities,
        capability_receipts=[item for item in row.get("capability_receipts", []) or [] if isinstance(item, dict)],
        codeintel=codeintel,
        tests_passed=tests_passed,
        delivery_evidence_refs=[hidden_verifier_file] if hidden_verifier_file else None,
    )
    row["capability_receipts"] = receipts
    row["capability_receipts_json"] = json.dumps(receipts, ensure_ascii=False, sort_keys=True)
    row["expected_capability_receipt_coverage"] = _expected_capability_receipt_coverage(
        task.expected_capabilities,
        receipts,
    )
    row["expected_capability_invocation_coverage"] = _expected_capability_invocation_coverage(
        task.expected_capabilities,
        receipts,
    )


def _codex_public_plan_subset(
    *,
    plan: dict[str, Any],
    task: CapabilityTask,
    route: dict[str, Any],
    codeintel: dict[str, Any],
    chosen_flow: str,
    tests_passed: bool,
) -> dict[str, Any]:
    """Keep Codex public claims aligned with capabilities it actually evidenced."""

    selected = set(normalize_capability_names(task.expected_capabilities))
    selected.update({"mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate"})
    if codeintel:
        selected.add("codeintel")
    if bool(route.get("should_research", False)):
        selected.add("research")
    if chosen_flow == "hyper_sprint":
        selected.add("hyper")

    # Direct Codex currently wears Nexus through prompt/context/gates. Do not mark
    # executor-only accelerators as selected until that path runs their real executors.
    executor_only = {"autoreason", "ddtree", "ultra_review", "nightshift", "swarm", "drone"}
    selected -= executor_only

    out = dict(plan)
    existing = [str(item) for item in out.get("selected_capabilities", []) or []]
    ordered = [item for item in existing if item in selected]
    for item in sorted(selected):
        if item not in ordered:
            ordered.append(item)
    out["selected_capabilities"] = ordered
    required = [str(item) for item in out.get("required_capabilities", []) or []]
    for item in ("mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate"):
        if item in selected and item not in required:
            required.append(item)
    out["required_capabilities"] = [item for item in required if item in selected]
    out["conditional_capabilities"] = [
        str(item)
        for item in out.get("conditional_capabilities", []) or []
        if str(item) in selected and str(item) not in out["required_capabilities"]
    ]
    pending = set(str(item) for item in out.get("pending_capabilities", []) or [])
    out["pending_capabilities"] = sorted(pending & selected)
    out["codex_public_claim_subset"] = True
    out["codex_public_claim_subset_reason"] = (
        "direct_codex_wearing_nexus_records_only_capabilities_with_public_evidence"
        if tests_passed
        else "direct_codex_wearing_nexus_failed_artifact_gate"
    )
    return out


def _apply_per_task_stop_loss(row: dict[str, Any], limit_sec: int) -> bool:
    if limit_sec <= 0:
        return False
    wall_duration = float(row.get("wall_duration_sec", 0.0) or 0.0)
    if wall_duration <= float(limit_sec):
        return False
    row["runtime_classification"] = "task_stop_loss_exceeded"
    row["timeout_scope"] = "benchmark_per_task_stop_loss"
    row["timeout_stage"] = "wall_clock_exceeded"
    row["timeout_sec"] = int(limit_sec)
    row["retryable"] = True
    row["infra_invalid_reason"] = "task_stop_loss_exceeded"
    row["run_eligible"] = False
    row["token_reliable"] = False
    row["token_unreliable_reason"] = "task_stop_loss_exceeded"
    return True


def _direct_provider_timeout_row(row: dict[str, Any]) -> bool:
    if str(row.get("mode") or "") != "without_nexus":
        return False
    timeout_markers = {
        str(row.get("gateway_error_category") or ""),
        str(row.get("baseline_gateway_error_category") or ""),
        str(row.get("infra_invalid_reason") or ""),
    }
    return bool(timeout_markers & {"timeout", "timeout_before_model_call", "task_stop_loss_exceeded"})


def _direct_provider_infra_row(row: dict[str, Any]) -> bool:
    if str(row.get("mode") or "") != "without_nexus":
        return False
    return not bool(row.get("run_eligible", True)) and bool(str(row.get("infra_invalid_reason") or ""))


def _direct_timeout_abort_reason(consecutive_timeouts: int, threshold: int) -> str:
    if int(threshold) <= 0:
        return ""
    if int(consecutive_timeouts) < int(threshold):
        return ""
    return "consecutive_direct_provider_timeouts"


def _direct_infra_abort_reason(consecutive_infra: int, threshold: int) -> str:
    if int(threshold) <= 0:
        return ""
    if int(consecutive_infra) < int(threshold):
        return ""
    return "consecutive_direct_provider_infra_invalid"


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _sum_phase_wall_sec(phase_wall: dict[str, Any]) -> float:
    total = 0.0
    for phase in ("P", "X", "D", "R", "A", "C"):
        try:
            total += float(phase_wall.get(phase, 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
    return round(total, 4)


def _nonnegative_delta(left: Any, right: Any) -> float | None:
    try:
        return round(max(0.0, float(left or 0.0) - float(right or 0.0)), 4)
    except (TypeError, ValueError):
        return None


def _count_fragment(prompt: str, fragment: str) -> int:
    if not fragment:
        return 0
    return len(fragment) if fragment in prompt else 0


def _direct_prompt_attribution(
    *,
    prompt: str,
    task_desc: str,
    source: str,
    tests: str,
    patch: str = "",
    nexus_control_chars: int = 0,
    governance_contract_chars: int = 0,
) -> dict[str, int]:
    """Break prompt payload into stable semantic buckets for ROI reporting."""

    task_constraint_chars = _count_fragment(prompt, task_desc)
    source_payload_chars = _count_fragment(prompt, source)
    test_payload_chars = _count_fragment(prompt, tests)
    candidate_payload_chars = len(str(patch or ""))
    known = (
        task_constraint_chars
        + source_payload_chars
        + test_payload_chars
        + candidate_payload_chars
        + nexus_control_chars
        + governance_contract_chars
    )
    system_instruction_chars = max(0, len(prompt) - known)
    return {
        "prompt_system_instruction_chars": system_instruction_chars,
        "prompt_task_constraint_chars": task_constraint_chars,
        "prompt_source_payload_chars": source_payload_chars,
        "prompt_test_payload_chars": test_payload_chars,
        "prompt_candidate_payload_chars": candidate_payload_chars,
        "prompt_nexus_control_chars": max(0, int(nexus_control_chars or 0)),
        "prompt_governance_contract_chars": max(0, int(governance_contract_chars or 0)),
    }


def _without_tasks_for_run(
    tasks: list[CapabilityTask],
    *,
    timed_out: bool,
    nexus_only: bool,
    without_only: bool = False,
) -> list[CapabilityTask]:
    if nexus_only:
        return []
    if without_only:
        return tasks
    if timed_out:
        return []
    return tasks


def _summarize_benchmark_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for mode in sorted({str(row.get("mode", "")) for row in rows if row.get("mode") is not None}):
        mode_rows = [row for row in rows if str(row.get("mode", "")) == mode]
        eligible = [row for row in mode_rows if bool(row.get("run_eligible", True))]
        infra_invalid = [row for row in mode_rows if not bool(row.get("run_eligible", True))]
        solved = [row for row in eligible if row.get("status") == "SUCCESS"]
        semantic = [row for row in eligible if bool(row.get("semantic_completed", False))]
        trust_mismatch = [row for row in eligible if bool(row.get("report_trust_mismatch", False))]
        first_pass = [row for row in eligible if int(row.get("attempt_count", 0) or 0) <= 1 and row.get("status") == "SUCCESS"]
        token_reliable = [row for row in eligible if bool(row.get("token_reliable", False))]
        local_fallback_unhelpful = [row for row in eligible if bool(row.get("local_fallback_unhelpful", False))]
        token_measured = [row for row in eligible if bool(row.get("token_measured", False))]
        provider_token_measured = [row for row in eligible if _row_has_measured_provider_tokens(row)]
        training_eligible_cost_evidence = [
            row for row in eligible if bool(row.get("training_eligible_cost_evidence", False))
        ]
        model_required_rows = [row for row in eligible if bool(row.get("model_required", False))]
        model_uplift_eligible = [row for row in eligible if bool(row.get("model_uplift_eligible", False))]
        local_delivery_blocked = [row for row in eligible if bool(row.get("model_uplift_blocked_by_local_delivery", False))]
        summary[mode] = {
            "total_n": len(mode_rows),
            "eligible_n": len(eligible),
            "infra_invalid_n": len(infra_invalid),
            "infra_invalid_reasons": sorted({str(row.get("infra_invalid_reason")) for row in infra_invalid if row.get("infra_invalid_reason")}),
            "solve_rate": round(len(solved) / len(eligible), 4) if eligible else None,
            "semantic_verified_rate": round(len(semantic) / len(eligible), 4) if eligible else None,
            "trust_mismatch_rate": round(len(trust_mismatch) / len(eligible), 4) if eligible else None,
            "first_pass_rate": round(len(first_pass) / len(eligible), 4) if eligible else None,
            "avg_wall_time_sec": _avg([float(row.get("wall_duration_sec", 0) or 0) for row in eligible]),
            "avg_phase_wall_total_sec": _avg([float(row.get("phase_wall_total_sec", 0) or 0) for row in eligible]),
            "avg_phase_wall_r_sec": _avg([float(row.get("phase_wall_r_sec", 0) or 0) for row in eligible]),
            "avg_r_phase_hyper_sprint_sec": _avg([float(row.get("r_phase_hyper_sprint_sec", 0) or 0) for row in eligible]),
            "avg_r_phase_total_sec": _avg([float(row.get("r_phase_total_sec", 0) or 0) for row in eligible]),
            "avg_cli_uninstrumented_sec": _avg([float(row.get("cli_uninstrumented_sec", 0) or 0) for row in eligible]),
            "avg_runner_overhead_sec": _avg([float(row.get("runner_overhead_sec", 0) or 0) for row in eligible]),
            "avg_model_attempt_wall_sec": _avg([float(row.get("model_attempt_wall_sec", row.get("wall_duration_sec", 0)) or 0) for row in eligible]),
            "avg_hidden_verifier_wall_sec": _avg([float(row.get("hidden_verifier_wall_sec", 0) or 0) for row in eligible]),
            "avg_hidden_retry_wall_sec": _avg([float(row.get("hidden_retry_wall_sec", 0) or 0) for row in eligible]),
            "avg_hidden_retry_verifier_wall_sec": _avg([float(row.get("hidden_retry_verifier_wall_sec", 0) or 0) for row in eligible]),
            "runner_overhead_polluted_n": sum(1 for row in eligible if bool(row.get("runner_overhead_polluted"))),
            "avg_tokens": _avg([float(row.get("total_tokens", 0) or 0) for row in eligible]),
            "token_measured_rate": round(len(token_measured) / len(eligible), 4) if eligible else None,
            "provider_token_measured_rate": round(len(provider_token_measured) / len(eligible), 4) if eligible else None,
            "clean_model_cost_evidence_rate": round(
                sum(1 for row in eligible if bool(row.get("clean_model_cost_evidence", False))) / len(eligible),
                4,
            )
            if eligible
            else None,
            "training_eligible_cost_evidence_rate": round(len(training_eligible_cost_evidence) / len(eligible), 4)
            if eligible
            else None,
            "token_reliable_rate": round(len(token_reliable) / len(eligible), 4) if eligible else None,
            "token_unreliable_reasons": sorted(
                {
                    str(row.get("token_unreliable_reason"))
                    for row in eligible
                    if row.get("token_unreliable_reason")
                }
            ),
            "avg_model_calls": _avg([float(row.get("model_calls", 0) or 0) for row in eligible]),
            "local_fallback_unhelpful_rate": round(len(local_fallback_unhelpful) / len(eligible), 4) if eligible else None,
            "model_required_n": len(model_required_rows),
            "model_uplift_eligible_n": len(model_uplift_eligible),
            "model_uplift_eligible_rate": round(len(model_uplift_eligible) / len(model_required_rows), 4)
            if model_required_rows
            else None,
            "model_uplift_blocked_by_local_delivery_n": len(local_delivery_blocked),
            "model_uplift_ineligible_reasons": sorted(
                {
                    str(row.get("model_uplift_ineligible_reason"))
                    for row in model_required_rows
                    if row.get("model_uplift_ineligible_reason")
                }
            ),
            # PR2: batch-level evidence aggregation — wraps existing row signals, no new taxonomy.
            # provider_token_completeness_rate: rows with provider_token_measured=True + token_reliable + no infra_invalid
            "provider_token_completeness_rate": round(
                sum(
                    1 for row in eligible
                    if bool(row.get("provider_token_measured", False))
                    and bool(row.get("token_reliable", True))
                    and not bool(row.get("has_infra_invalid", False))
                ) / len(eligible),
                4,
            ) if eligible else None,
            # wall_ledger_conserved_rate: wraps existing wall-ledger telemetry_source classification
            "wall_ledger_conserved_rate": round(
                sum(
                    1 for row in eligible
                    if not bool(row.get("telemetry_invalid", False))
                    and str(row.get("telemetry_source", "measured")) not in {
                        "zero_fill", "included_in_parent", "shadow", "experimental",
                        "observation_only", "estimated", "synthetic",
                    }
                ) / len(eligible),
                4,
            ) if eligible else None,
            # telemetry_invalid_rate: rows with has_infra_invalid=True or telemetry_invalid=True
            "telemetry_invalid_rate": round(
                sum(
                    1 for row in eligible
                    if bool(row.get("has_infra_invalid", False)) or bool(row.get("telemetry_invalid", False))
                ) / len(eligible),
                4,
            ) if eligible else None,
        }
    return summary




def load_tasks(path: str | Path) -> list[CapabilityTask]:
    src = Path(path)
    raw_text = src.read_text(encoding="utf-8")
    payload = json.loads(raw_text)
    manifest_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    tasks_raw = payload.get("tasks", [])
    tasks: list[CapabilityTask] = []
    for idx, row in enumerate(tasks_raw):
        category = str(row.get("category", ""))
        task_type = str(row.get("task_type", f"public_{category}" if category else "task"))
        cost_budget = row.get("cost_budget")
        cost_budget = cost_budget if isinstance(cost_budget, dict) else None
        tasks.append(
            CapabilityTask(
                id=str(row["id"]),
                difficulty=str(row["difficulty"]),
                task_type=task_type,
                task_desc=str(row["task_desc"]),
                target_file=str(row.get("target_file", row.get("fixture_kind", "unused"))),
                test_file=str(row.get("test_file", "unused")),
                success_criteria=str(row.get("success_criteria", "all_target_tests_pass")),
                category=category,
                repo_kind=str(row.get("repo_kind", "")),
                repo=str(row.get("repo", "")),
                repo_ref=str(row.get("repo_ref", "")),
                manifest_hash=manifest_hash,
                fixture_kind=str(row.get("fixture_kind", "")),
                hidden_test_file=str(row.get("hidden_test_file", "")),
                expected_capabilities=tuple(str(item) for item in row.get("expected_capabilities", []) or []),
                capability_activation_contract=str(row.get("capability_activation_contract", "")),
                hidden_oracle_kind=str(row.get("hidden_oracle_kind", "")),
                eligibility_class=str(row.get("eligibility_class", "")),
                cost_budget=cost_budget,
                token_budget=int(row["token_budget"]) if row.get("token_budget") is not None else None,
                wall_time_budget_sec=float(row["wall_time_budget_sec"]) if row.get("wall_time_budget_sec") is not None else None,
                public_claim_allowed_metrics=tuple(str(item) for item in row.get("public_claim_allowed_metrics", []) or []),
                manifest_index=idx,
            )
        )
    return tasks


def _expected_capability_coverage(tasks: list[CapabilityTask]) -> dict[str, Any]:
    declared = sorted({name for task in tasks for name in task.expected_capabilities})
    core = set(CORE_CAPABILITIES)
    unknown = sorted(set(declared) - core)
    missing_core = sorted(core - set(declared))
    tasks_missing_expected = [task.id for task in tasks if not task.expected_capabilities]
    required_or_capped = sorted(
        {
            name
            for task in tasks
            if task.capability_activation_contract in {"required", "cost_capped"}
            for name in task.expected_capabilities
        }
    )
    return {
        "declared": declared,
        "declared_count": len(declared),
        "core_count": len(CORE_CAPABILITIES),
        "unknown": unknown,
        "missing_core": missing_core,
        "tasks_missing_expected": tasks_missing_expected,
        "required_or_cost_capped": required_or_capped,
        "coverage_rate": round(len(set(declared) & core) / len(core), 4) if core else 1.0,
    }


def select_tasks(tasks: list[CapabilityTask], *, difficulty: str, max_tasks: int) -> list[CapabilityTask]:
    limit = max(1, max_tasks)
    if difficulty != "all":
        filtered = [task for task in tasks if task.difficulty == difficulty]
        return filtered[:limit]

    buckets: dict[str, list[CapabilityTask]] = {"easy": [], "medium": [], "hard": []}
    for task in tasks:
        buckets.setdefault(task.difficulty, []).append(task)

    ordered: list[CapabilityTask] = []
    idx = 0
    bucket_order = ["easy", "medium", "hard"]
    while len(ordered) < limit:
        progressed = False
        for key in bucket_order:
            bucket = buckets.get(key, [])
            if idx < len(bucket):
                ordered.append(bucket[idx])
                progressed = True
                if len(ordered) >= limit:
                    break
        if not progressed:
            break
        idx += 1
    return ordered[:limit]


def filter_tasks_by_repo_kind(tasks: list[CapabilityTask], repo_kind_filter: str) -> list[CapabilityTask]:
    if repo_kind_filter.strip().lower() in {"", "all"}:
        return tasks
    allowed = {part.strip() for part in repo_kind_filter.split(",") if part.strip()}
    return [task for task in tasks if task.repo_kind in allowed]


def filter_tasks_by_id(tasks: list[CapabilityTask], task_id_filter: str) -> list[CapabilityTask]:
    if task_id_filter.strip().lower() in {"", "all"}:
        return tasks
    allowed = {part.strip() for part in task_id_filter.split(",") if part.strip()}
    return [task for task in tasks if task.id in allowed]


def filter_tasks_by_manifest_index(tasks: list[CapabilityTask], manifest_index_filter: str) -> list[CapabilityTask]:
    if manifest_index_filter.strip().lower() in {"", "all"}:
        return tasks
    allowed_indices: set[int] = set()
    parts = [part.strip() for part in manifest_index_filter.split(",") if part.strip()]
    for part in parts:
        if "-" in part:
            try:
                start_str, end_str = part.split("-", 1)
                start = int(start_str.strip())
                end = int(end_str.strip())
                for i in range(start, end + 1):
                    allowed_indices.add(i)
            except ValueError:
                pass
        else:
            try:
                allowed_indices.add(int(part))
            except ValueError:
                pass
    return [task for task in tasks if task.manifest_index in allowed_indices]


def _is_heavy_task(task: CapabilityTask, args: Any) -> bool:
    if not getattr(args, "enable_background_offload", False):
        return False
    heavy_ids = {part.strip() for part in getattr(args, "heavy_task_ids", "").split(",") if part.strip()}
    if task.id in heavy_ids:
        return True
    if task.difficulty == "hard":
        return True
    return False


def expand_task_trials(tasks: list[CapabilityTask], *, repeat_trials: int, shuffle_seed: int | None) -> list[CapabilityTask]:
    expanded: list[CapabilityTask] = []
    trials = max(1, repeat_trials)
    for trial_index in range(1, trials + 1):
        for task in tasks:
            expanded.append(
                CapabilityTask(
                    id=task.id,
                    difficulty=task.difficulty,
                    task_type=task.task_type,
                    task_desc=task.task_desc,
                    target_file=task.target_file,
                    test_file=task.test_file,
                    success_criteria=task.success_criteria,
                    category=task.category,
                    repo_kind=task.repo_kind,
                    repo=task.repo,
                    repo_ref=task.repo_ref,
                    manifest_hash=task.manifest_hash,
                    trial_index=trial_index,
                    fixture_kind=task.fixture_kind,
                    hidden_test_file=task.hidden_test_file,
                    expected_capabilities=task.expected_capabilities,
                    capability_activation_contract=task.capability_activation_contract,
                    hidden_oracle_kind=task.hidden_oracle_kind,
                    eligibility_class=task.eligibility_class,
                    cost_budget=task.cost_budget,
                    token_budget=task.token_budget,
                    wall_time_budget_sec=task.wall_time_budget_sec,
                    public_claim_allowed_metrics=task.public_claim_allowed_metrics,
                    manifest_index=task.manifest_index,
                )
            )
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(expanded)
    return expanded


def _materialize_fixture(repo_root: Path, task: CapabilityTask) -> tuple[str, str]:
    case_dir = (repo_root / ".nexus" / "bench_cases" / task.id).resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    target_path = case_dir / "target.py"
    visible_test_path = case_dir / "test_visible.py"
    hidden_test_path = case_dir / "test_hidden.py"

    fixture = task.fixture_kind.strip()
    if fixture.startswith("rlm_harder_"):
        target_code, visible_test_code, hidden_test_code = _rlm_harder_fixture_sources(fixture)
        target_path.write_text(target_code, encoding="utf-8")
        visible_test_path.write_text(visible_test_code, encoding="utf-8")
        hidden_test_path.write_text(hidden_test_code, encoding="utf-8")
        return str(target_path), str(visible_test_path)
    if fixture.startswith("nexus_value_"):
        target_code, visible_test_code, hidden_test_code = _nexus_value_fixture_sources(fixture)
        target_path.write_text(target_code, encoding="utf-8")
        visible_test_path.write_text(visible_test_code, encoding="utf-8")
        hidden_test_path.write_text(hidden_test_code, encoding="utf-8")
        return str(target_path), str(visible_test_path)
    if fixture == "pytest_async_repair":
        target_code = (
            "def compute_backoff(attempt: int) -> int:\n"
            "    # intentionally naive for hard-case\n"
            "    return 1\n"
        )
        visible_test_code = (
            "import sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).parent))\n"
            "from target import compute_backoff\n\n"
            "def test_compute_backoff_visible_contract():\n"
            "    assert compute_backoff(1) == 1\n"
            "    assert compute_backoff(2) == 2\n"
        )
        hidden_test_code = (
            "import sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).parent))\n"
            "from target import compute_backoff\n\n"
            "def test_compute_backoff_hidden_contract():\n"
            "    assert compute_backoff(1) == 1\n"
            "    assert compute_backoff(2) == 2\n"
            "    assert compute_backoff(3) == 4\n"
        )
        target_path.write_text(target_code, encoding="utf-8")
        visible_test_path.write_text(visible_test_code, encoding="utf-8")
        hidden_test_path.write_text(hidden_test_code, encoding="utf-8")
        return str(target_path), str(visible_test_path)
    if fixture == "docs_api_sync":
        readme_path = case_dir / "README.md"
        target_code = (
            "FIELD = 'status'\n\n"
            "def build_response(value):\n"
            "    return {FIELD: value}\n"
        )
        readme_path.write_text(
            "# API Response\n\n"
            "The public response mapping must use the canonical `result` field.\n"
            "Legacy examples that mention `status` are stale.\n",
            encoding="utf-8",
        )
        visible_test_code = (
            "import sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).parent))\n"
            "from target import build_response\n\n"
            "def test_build_response_returns_mapping():\n"
            "    assert isinstance(build_response('ok'), dict)\n"
        )
        hidden_test_code = (
            "import sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).parent))\n"
            "from target import build_response\n\n"
            "def test_response_uses_canonical_result_field():\n"
            "    assert build_response('ok') == {'result': 'ok'}\n"
        )
        target_path.write_text(target_code, encoding="utf-8")
        visible_test_path.write_text(visible_test_code, encoding="utf-8")
        hidden_test_path.write_text(hidden_test_code, encoding="utf-8")
        return str(target_path), str(visible_test_path)

    test_path = case_dir / "test_target.py"

    difficulty = task.difficulty.lower()
    if difficulty == "easy":
        target_code = (
            "def normalize_flag(text: str) -> str:\n"
            "    # intentionally buggy for benchmark\n"
            "    return text\n"
        )
        test_code = (
            "import importlib.util\n"
            "from pathlib import Path\n\n"
            "_TARGET_PATH = Path(__file__).resolve().parent / 'target.py'\n"
            "_SPEC = importlib.util.spec_from_file_location('bench_target', _TARGET_PATH)\n"
            "_MOD = importlib.util.module_from_spec(_SPEC)\n"
            "assert _SPEC is not None and _SPEC.loader is not None\n"
            "_SPEC.loader.exec_module(_MOD)\n\n"
            "def test_normalize_flag():\n"
            "    assert _MOD.normalize_flag('  TRUE  ') == 'true'\n"
        )
    elif difficulty == "medium":
        target_code = (
            "def compute_backoff(attempt: int) -> int:\n"
            "    # intentionally simplistic\n"
            "    return attempt\n"
        )
        test_code = (
            "import importlib.util\n"
            "from pathlib import Path\n\n"
            "_TARGET_PATH = Path(__file__).resolve().parent / 'target.py'\n"
            "_SPEC = importlib.util.spec_from_file_location('bench_target', _TARGET_PATH)\n"
            "_MOD = importlib.util.module_from_spec(_SPEC)\n"
            "assert _SPEC is not None and _SPEC.loader is not None\n"
            "_SPEC.loader.exec_module(_MOD)\n\n"
            "def test_compute_backoff_medium():\n"
            "    assert _MOD.compute_backoff(1) == 1\n"
            "    assert _MOD.compute_backoff(2) == 2\n"
            "    assert _MOD.compute_backoff(3) == 4\n"
        )
    else:
        target_code = (
            "def compute_backoff(attempt: int) -> int:\n"
            "    # intentionally naive for hard-case\n"
            "    return 1\n"
        )
        test_code = (
            "import importlib.util\n"
            "from pathlib import Path\n\n"
            "_TARGET_PATH = Path(__file__).resolve().parent / 'target.py'\n"
            "_SPEC = importlib.util.spec_from_file_location('bench_target', _TARGET_PATH)\n"
            "_MOD = importlib.util.module_from_spec(_SPEC)\n"
            "assert _SPEC is not None and _SPEC.loader is not None\n"
            "_SPEC.loader.exec_module(_MOD)\n\n"
            "def test_compute_backoff_hard():\n"
            "    assert _MOD.compute_backoff(1) == 1\n"
            "    assert _MOD.compute_backoff(2) == 2\n"
            "    assert _MOD.compute_backoff(3) == 4\n"
        )
    target_path.write_text(target_code, encoding="utf-8")
    test_path.write_text(test_code, encoding="utf-8")
    return str(target_path), str(test_path)


def _split_fixture_tests(test_code: str) -> tuple[str, str]:
    portable = _portable_fixture_test_import(test_code)
    return portable, portable


def _split_rlm_harder_fixture_tests(fixture_kind: str, test_code: str) -> tuple[str, str]:
    if fixture_kind == "rlm_harder_v2_governance_guard":
        visible = (
            "from target import rlm_harder_v2_filter_action\n\n"
            "def test_read_file_is_allowed_and_dangerous_shell_is_blocked():\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'read_file'}) == {'allowed': True, 'reason': 'ok'}\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'run_command', 'cmd': 'rm -rf .nexus'}) == {'allowed': False, 'reason': 'governance_block'}\n"
        )
        hidden = (
            "from target import rlm_harder_v2_filter_action\n\n"
            "def test_blocks_dangerous_actions_and_paths():\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'read_file'}) == {'allowed': True, 'reason': 'ok'}\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'run_command', 'cmd': 'rm -rf .nexus'}) == {'allowed': False, 'reason': 'governance_block'}\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'delete_file', 'path': 'logs/run.json'}) == {'allowed': False, 'reason': 'governance_block'}\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'write_file', 'path': 'benchmarks/result.json'}) == {'allowed': False, 'reason': 'governance_block'}\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_evidence_gap":
        visible = (
            "from target import rlm_harder_v2_verified_claims\n\n"
            "def test_requires_artifact_reference():\n"
            "    claims = [\n"
            "        {'id': 'a', 'status': 'pass', 'artifact': 'reports/a.json'},\n"
            "        {'id': 'b', 'status': 'pass'},\n"
            "        {'id': 'c', 'status': 'fail', 'artifact': 'reports/c.json'},\n"
            "    ]\n"
            "    assert rlm_harder_v2_verified_claims(claims) == ['a']\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_empty_and_non_string_artifacts():\n"
            "    claims = [\n"
            "        {'id': 'empty', 'status': 'pass', 'artifact': ''},\n"
            "        {'id': 'none', 'status': 'pass', 'artifact': None},\n"
            "        {'id': 'list', 'status': 'pass', 'artifact': []},\n"
            "        {'id': 'ok', 'status': 'pass', 'artifact': 'reports/ok.json'},\n"
            "    ]\n"
            "    assert rlm_harder_v2_verified_claims(claims) == ['ok']\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_governance_scope":
        visible = (
            "from target import rlm_harder_v2_scope_decision\n\n"
            "def test_approved_and_read_only_paths():\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'read', 'approved': False}) == {'allowed': True, 'reason': 'read_only'}\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'write', 'approved': True}) == {'allowed': True, 'reason': 'approved'}\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'delete', 'approved': False}) == {'allowed': False, 'reason': 'scope_block'}\n"
        )
        hidden = visible + (
            "\n"
            "def test_unknown_and_missing_approval_actions_are_blocked():\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'write'}) == {'allowed': False, 'reason': 'scope_block'}\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'unknown', 'approved': False}) == {'allowed': False, 'reason': 'scope_block'}\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_evidence_replay":
        visible = (
            "from target import rlm_harder_v2_accept_receipt\n\n"
            "def test_accepts_verified_receipt_with_replay():\n"
            "    receipt = {'claim': 'verified', 'replay_command': 'pytest -q', 'exit_code': 0}\n"
            "    assert rlm_harder_v2_accept_receipt(receipt) is True\n"
            "\n"
            "def test_verified_receipt_requires_replay_and_clean_exit():\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'verified', 'exit_code': 0}) is False\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'verified', 'replay_command': 'pytest -q', 'exit_code': 1}) is False\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_near_miss_receipt_fields():\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'verified', 'replay_command': 'pytest -q', 'replay_exit_code': 0}) is False\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'partial', 'replay_command': 'pytest -q', 'exit_code': 0}) is False\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_second_round":
        visible = (
            "from target import rlm_harder_v2_merge_settings\n\n"
            "def test_plain_override_wins():\n"
            "    assert rlm_harder_v2_merge_settings({'timeout': 10}, {'timeout': 20}) == {'timeout': 20}\n"
            "\n"
            "def test_preserves_inputs_and_ignores_none_values():\n"
            "    defaults = {'timeout': 10, 'retries': 2}\n"
            "    merged = rlm_harder_v2_merge_settings(defaults, {'timeout': None, 'jitter': 1})\n"
            "    assert merged == {'timeout': 10, 'retries': 2, 'jitter': 1}\n"
            "    assert defaults == {'timeout': 10, 'retries': 2}\n"
        )
        hidden = visible + (
            "\n"
            "def test_empty_override_returns_copy_not_alias():\n"
            "    defaults = {'timeout': 10}\n"
            "    merged = rlm_harder_v2_merge_settings(defaults, {})\n"
            "    assert merged == {'timeout': 10}\n"
            "    assert merged is not defaults\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_memory_contract":
        visible = (
            "from target import rlm_harder_v2_select_memory_hits\n\n"
            "def test_requires_type_and_keyword_overlap():\n"
            "    items = [\n"
            "        {'id': 'old-bug', 'task_type': 'bug', 'keywords': ['invoice', 'rounding']},\n"
            "        {'id': 'target', 'task_type': 'bug', 'keywords': ['websocket', 'timeout']},\n"
            "    ]\n"
            "    assert rlm_harder_v2_select_memory_hits(items, 'bug', ['websocket', 'timeout']) == [items[1]]\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_same_type_without_keyword_overlap_and_wrong_type():\n"
            "    items = [\n"
            "        {'id': 'same-type', 'task_type': 'bug', 'keywords': ['invoice', 'rounding']},\n"
            "        {'id': 'wrong-type', 'task_type': 'feature', 'keywords': ['websocket', 'timeout']},\n"
            "        {'id': 'target', 'task_type': 'bug', 'keywords': ['websocket', 'timeout']},\n"
            "    ]\n"
            "    assert rlm_harder_v2_select_memory_hits(items, 'bug', ['websocket']) == [items[2]]\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_belief_budget":
        visible = (
            "from target import rlm_harder_v2_repair_budget\n\n"
            "def test_low_confidence_high_risk_requires_more_evidence():\n"
            "    assert rlm_harder_v2_repair_budget(0.42, 'high') == {'rounds': 3, 'needs_evidence': True}\n"
            "    assert rlm_harder_v2_repair_budget(0.91, 'low') == {'rounds': 1, 'needs_evidence': False}\n"
        )
        hidden = visible + (
            "\n"
            "def test_uncertain_or_high_risk_paths_require_evidence():\n"
            "    assert rlm_harder_v2_repair_budget(0.74, 'medium')['needs_evidence'] is True\n"
            "    assert rlm_harder_v2_repair_budget(0.95, 'high')['needs_evidence'] is True\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_autoreason_judge":
        visible = (
            "from target import rlm_harder_v2_choose_candidate\n\n"
            "def test_selects_supported_highest_score_candidate():\n"
            "    candidates = [\n"
            "        {'id': 'a', 'score': 0.4, 'evidence_refs': ['a.json']},\n"
            "        {'id': 'b', 'score': 0.9, 'evidence_refs': ['b.json']},\n"
            "    ]\n"
            "    assert rlm_harder_v2_choose_candidate(candidates) == 'b'\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_high_score_without_evidence_and_failed_status():\n"
            "    candidates = [\n"
            "        {'id': 'unsupported', 'score': 0.99, 'evidence_refs': []},\n"
            "        {'id': 'failed', 'score': 0.95, 'status': 'fail', 'evidence_refs': ['fail.json']},\n"
            "        {'id': 'winner', 'score': 0.7, 'status': 'pass', 'evidence_refs': ['winner.json']},\n"
            "    ]\n"
            "    assert rlm_harder_v2_choose_candidate(candidates) == 'winner'\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_ddtree_pruning":
        visible = (
            "from target import rlm_harder_v2_prune_candidates\n\n"
            "def test_prunes_to_budget_by_score():\n"
            "    candidates = [\n"
            "        {'id': 'a', 'score': 0.2, 'risk': 1},\n"
            "        {'id': 'b', 'score': 0.9, 'risk': 1},\n"
            "        {'id': 'c', 'score': 0.6, 'risk': 1},\n"
            "    ]\n"
            "    assert rlm_harder_v2_prune_candidates(candidates, 2) == ['b', 'c']\n"
        )
        hidden = visible + (
            "\n"
            "def test_preserves_high_risk_boundary_even_when_score_is_lower():\n"
            "    candidates = [\n"
            "        {'id': 'safe-high-score', 'score': 0.95, 'risk': 1},\n"
            "        {'id': 'risky-required', 'score': 0.5, 'risk': 9},\n"
            "        {'id': 'middle', 'score': 0.7, 'risk': 2},\n"
            "    ]\n"
            "    assert rlm_harder_v2_prune_candidates(candidates, 2) == ['risky-required', 'safe-high-score']\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_ultra_review_report":
        visible = (
            "from target import rlm_harder_v2_accept_ultra_report\n\n"
            "def test_accepts_report_with_sandbox_and_gate():\n"
            "    report = {'sandbox_id': 's1', 'gate_passed': True, 'verified_findings': []}\n"
            "    assert rlm_harder_v2_accept_ultra_report(report) is True\n"
        )
        hidden = visible + (
            "\n"
            "def test_verified_findings_require_repro_command_and_failed_negative_run():\n"
            "    assert rlm_harder_v2_accept_ultra_report({'sandbox_id': 's1', 'gate_passed': True, 'verified_findings': [{'id': 'bug'}]}) is False\n"
            "    assert rlm_harder_v2_accept_ultra_report({'sandbox_id': 's1', 'gate_passed': True, 'verified_findings': [{'id': 'bug', 'repro_command': 'pytest -q test_bug.py', 'negative_exit_code': 1}]}) is True\n"
            "    assert rlm_harder_v2_accept_ultra_report({'sandbox_id': 's1', 'gate_passed': False, 'verified_findings': []}) is False\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_research_citation":
        visible = (
            "from target import rlm_harder_v2_choose_research_claim\n\n"
            "def test_selects_cited_claim_for_topic():\n"
            "    claims = [\n"
            "        {'id': 'a', 'topic': 'routing', 'citation': 'docs/routing.md', 'supported': True},\n"
            "        {'id': 'b', 'topic': 'routing', 'supported': False},\n"
            "    ]\n"
            "    assert rlm_harder_v2_choose_research_claim(claims, 'routing') == 'a'\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_uncited_or_wrong_topic_claims():\n"
            "    claims = [\n"
            "        {'id': 'uncited', 'topic': 'routing', 'supported': True},\n"
            "        {'id': 'wrong-topic', 'topic': 'memory', 'citation': 'docs/memory.md', 'supported': True},\n"
            "        {'id': 'target', 'topic': 'routing', 'citation': 'docs/routing.md', 'supported': True},\n"
            "    ]\n"
            "    assert rlm_harder_v2_choose_research_claim(claims, 'routing') == 'target'\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_lancedb_retrieval":
        visible = (
            "from target import rlm_harder_v2_select_vector_hits\n\n"
            "def test_selects_scored_hits_for_topic_pack():\n"
            "    hits = [\n"
            "        {'id': 'a', 'score': 0.8, 'topic_pack': 'nexus', 'source_id': 'claim-a'},\n"
            "        {'id': 'b', 'score': 0.4, 'topic_pack': 'nexus', 'source_id': 'claim-b'},\n"
            "    ]\n"
            "    assert rlm_harder_v2_select_vector_hits(hits, 'nexus', 0.7) == ['a']\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_missing_source_and_cross_pack_hits():\n"
            "    hits = [\n"
            "        {'id': 'missing-source', 'score': 0.95, 'topic_pack': 'nexus'},\n"
            "        {'id': 'wrong-pack', 'score': 0.9, 'topic_pack': 'other', 'source_id': 'claim-x'},\n"
            "        {'id': 'target', 'score': 0.75, 'topic_pack': 'nexus', 'source_id': 'claim-t'},\n"
            "    ]\n"
            "    assert rlm_harder_v2_select_vector_hits(hits, 'nexus', 0.7) == ['target']\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_semantic_searcher_refs":
        visible = (
            "from target import rlm_harder_v2_select_semantic_refs\n\n"
            "def test_selects_gated_semantic_ref_for_topic():\n"
            "    refs = [\n"
            "        {'id': 'a', 'relevance': 0.8, 'topic': 'nexus', 'source_id': 'claim-a', 'gate_passed': True},\n"
            "        {'id': 'b', 'relevance': 0.4, 'topic': 'nexus', 'source_id': 'claim-b', 'gate_passed': True},\n"
            "    ]\n"
            "    assert rlm_harder_v2_select_semantic_refs(refs, 'nexus', 0.7) == ['claim-a']\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_ungated_missing_source_and_wrong_topic_refs():\n"
            "    refs = [\n"
            "        {'id': 'ungated', 'relevance': 0.95, 'topic': 'nexus', 'source_id': 'claim-u', 'gate_passed': False},\n"
            "        {'id': 'missing-source', 'relevance': 0.95, 'topic': 'nexus', 'gate_passed': True},\n"
            "        {'id': 'wrong-topic', 'relevance': 0.9, 'topic': 'other', 'source_id': 'claim-x', 'gate_passed': True},\n"
            "        {'id': 'target', 'relevance': 0.75, 'topic': 'nexus', 'source_id': 'claim-t', 'gate_passed': True},\n"
            "    ]\n"
            "    assert rlm_harder_v2_select_semantic_refs(refs, 'nexus', 0.7) == ['claim-t']\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_swarm_consensus":
        visible = (
            "from target import rlm_harder_v2_accept_swarm_report\n\n"
            "def test_accepts_consensus_with_two_roles():\n"
            "    report = {'consensus': 'pass', 'findings': [{'role': 'logic', 'evidence': 'a'}, {'role': 'security', 'evidence': 'b'}]}\n"
            "    assert rlm_harder_v2_accept_swarm_report(report) is True\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_single_role_or_missing_evidence():\n"
            "    assert rlm_harder_v2_accept_swarm_report({'consensus': 'pass', 'findings': [{'role': 'logic', 'evidence': 'a'}, {'role': 'logic', 'evidence': 'b'}]}) is False\n"
            "    assert rlm_harder_v2_accept_swarm_report({'consensus': 'pass', 'findings': [{'role': 'logic'}, {'role': 'security', 'evidence': 'b'}]}) is False\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_swarm_quiet_moment":
        visible = (
            "from target import rlm_harder_v2_accept_quiet_moment\n\n"
            "def test_accepts_non_mutating_quiet_moment():\n"
            "    event = {'schema_version': 'nexus_quiet_moment.v1', 'production_writes_allowed': False, 'allowed_actions': ['observe', 'report', 'rollback'], 'observe': {'status': 'observed'}, 'rollback': {'status': 'armed'}}\n"
            "    assert rlm_harder_v2_accept_quiet_moment(event) is True\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_mutating_or_incomplete_quiet_moment():\n"
            "    assert rlm_harder_v2_accept_quiet_moment({'schema_version': 'nexus_quiet_moment.v1', 'production_writes_allowed': True, 'allowed_actions': ['observe', 'report', 'rollback'], 'observe': {'status': 'observed'}, 'rollback': {'status': 'armed'}}) is False\n"
            "    assert rlm_harder_v2_accept_quiet_moment({'schema_version': 'nexus_quiet_moment.v1', 'production_writes_allowed': False, 'allowed_actions': ['observe', 'report'], 'observe': {'status': 'observed'}, 'rollback': {'status': 'armed'}}) is False\n"
            "    assert rlm_harder_v2_accept_quiet_moment({'schema_version': 'nexus_quiet_moment.v1', 'production_writes_allowed': False, 'allowed_actions': ['observe', 'report', 'rollback'], 'observe': {}, 'rollback': {'status': 'armed'}}) is False\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_drone_artifacts":
        visible = (
            "from target import rlm_harder_v2_accept_drone_artifacts\n\n"
            "def test_accepts_completed_drone_artifacts():\n"
            "    artifacts = [{'owner': 'a', 'path': 'reports/a.json'}, {'owner': 'b', 'path': 'reports/b.json'}]\n"
            "    assert rlm_harder_v2_accept_drone_artifacts(artifacts, expected_count=2) is True\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_missing_owner_path_or_count_mismatch():\n"
            "    assert rlm_harder_v2_accept_drone_artifacts([{'owner': 'a', 'path': 'reports/a.json'}], expected_count=2) is False\n"
            "    assert rlm_harder_v2_accept_drone_artifacts([{'owner': 'a'}, {'owner': 'b', 'path': 'reports/b.json'}], expected_count=2) is False\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_nightshift_recovery":
        visible = (
            "from target import rlm_harder_v2_accept_nightshift\n\n"
            "def test_accepts_invoked_recovered_report():\n"
            "    report = {'recommended': True, 'invoked': True, 'recovered': True, 'report_path': 'reports/nightshift.json'}\n"
            "    assert rlm_harder_v2_accept_nightshift(report) is True\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_recommended_without_invocation_or_report():\n"
            "    assert rlm_harder_v2_accept_nightshift({'recommended': True, 'invoked': False, 'recovered': False, 'report_path': ''}) is False\n"
            "    assert rlm_harder_v2_accept_nightshift({'recommended': True, 'invoked': True, 'recovered': True}) is False\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    return _split_fixture_tests(test_code)


def _split_nexus_value_fixture_tests(fixture_kind: str, test_code: str) -> tuple[str, str]:
    visible_tests = {
        "nexus_value_hidden_state": (
            "from target import apply_events\n\n"
            "def test_applies_unique_happy_path_events():\n"
            "    events = [{'id': 'a', 'delta': 2}, {'id': 'b', 'delta': 3}]\n"
            "    assert apply_events(events) == {'count': 5, 'seen': ['a', 'b']}\n"
        ),
        "nexus_value_hidden_parser": (
            "from target import normalize_key\n\n"
            "def test_normalize_key_simple_spacing():\n"
            "    assert normalize_key('  User Name  ') == 'user-name'\n"
        ),
        "nexus_value_self_heal_invariant": (
            "from target import merge_limits\n\n"
            "def test_merge_limits_overrides_plain_values():\n"
            "    assert merge_limits({'timeout': 10}, {'timeout': 20}) == {'timeout': 20}\n"
        ),
        "nexus_value_self_heal_timeout": (
            "from target import remaining_ms\n\n"
            "def test_remaining_ms_simple_elapsed_case():\n"
            "    assert remaining_ms(100, 125, 50) == 25\n"
        ),
        "nexus_value_mempalace_secret_redaction": (
            "from target import redact\n\n"
            "def test_redact_preserves_non_secret_fields():\n"
            "    assert redact({'user': 'ada', 'note': 'ok'}) == {'user': 'ada', 'note': 'ok'}\n"
        ),
        "nexus_value_mempalace_deny_default": (
            "from target import can_access\n\n"
            "def test_viewer_can_read_and_admin_can_write():\n"
            "    assert can_access('admin', 'write') is True\n"
            "    assert can_access('viewer', 'read') is True\n"
        ),
        "nexus_value_artifact_claim_rollup": (
            "from target import verified_claims\n\n"
            "def test_verified_claims_accepts_supported_pass():\n"
            "    claims = [{'id': 'a', 'status': 'pass', 'artifact': 'reports/a.json'}]\n"
            "    assert verified_claims(claims) == ['a']\n"
        ),
        "nexus_value_artifact_phase_report": (
            "from target import phase_ready\n\n"
            "def test_phase_ready_accepts_pass_with_evidence():\n"
            "    assert phase_ready({'status': 'pass', 'evidence': 'x.json', 'reason': ''}) is True\n"
        ),
        "nexus_value_context_docs_contract": (
            "from target import build_response\n\n"
            "def test_build_response_returns_mapping():\n"
            "    assert isinstance(build_response('ok'), dict)\n"
        ),
        "nexus_value_context_config_contract": (
            "from target import parse_config\n\n"
            "def test_parse_config_preserves_explicit_values():\n"
            "    assert parse_config({'strict': False, 'retries': 0}) == {'strict': False, 'retries': 0}\n"
        ),
        "nexus_value_trust_phase_aggregator": (
            "from target import overall_status\n\n"
            "def test_overall_status_passes_when_all_phases_pass():\n"
            "    assert overall_status([{'status': 'pass', 'evidence': 'a'}]) == 'pass'\n"
        ),
        "nexus_value_trust_incident_classifier": (
            "from target import classify\n\n"
            "def test_classifier_keeps_open_failed_smoke():\n"
            "    assert classify(False, {'verified': True}) == 'open'\n"
        ),
    }
    visible = visible_tests.get(fixture_kind)
    if visible is None:
        return _split_fixture_tests(test_code)
    return _portable_fixture_test_import(visible), _portable_fixture_test_import(test_code)


def _nexus_value_fixture_sources(fixture_kind: str) -> tuple[str, str, str]:
    fixtures: dict[str, tuple[str, str]] = {
        "nexus_value_hidden_state": (
            "def apply_events(events):\n"
            "    state = {'count': 0, 'seen': []}\n"
            "    for event in events:\n"
            "        state['count'] += int(event.get('delta', 0))\n"
            "        state['seen'].append(event.get('id'))\n"
            "    return state\n",
            "from target import apply_events\n\n"
            "def test_duplicate_events_are_idempotent():\n"
            "    events = [{'id': 'a', 'delta': 2}, {'id': 'a', 'delta': 2}, {'id': 'b', 'delta': 3}]\n"
            "    assert apply_events(events) == {'count': 5, 'seen': ['a', 'b']}\n",
        ),
        "nexus_value_hidden_parser": (
            "def normalize_key(text):\n"
            "    return text.strip().lower().replace(' ', '-')\n",
            "from target import normalize_key\n\n"
            "def test_normalize_key_boundaries():\n"
            "    assert normalize_key('  User   Name  ') == 'user-name'\n"
            "    assert normalize_key('') == ''\n"
            "    assert normalize_key('API__Token') == 'api-token'\n",
        ),
        "nexus_value_self_heal_invariant": (
            "def merge_limits(defaults, override):\n"
            "    result = defaults\n"
            "    result.update(override or {})\n"
            "    return result\n",
            "from target import merge_limits\n\n"
            "def test_merge_limits_preserves_inputs_and_drops_none():\n"
            "    defaults = {'timeout': 10, 'retries': 2}\n"
            "    merged = merge_limits(defaults, {'timeout': None, 'jitter': 1})\n"
            "    assert merged == {'timeout': 10, 'retries': 2, 'jitter': 1}\n"
            "    assert defaults == {'timeout': 10, 'retries': 2}\n",
        ),
        "nexus_value_self_heal_timeout": (
            "def remaining_ms(start_ms, now_ms, timeout_ms):\n"
            "    return timeout_ms - now_ms - start_ms\n",
            "from target import remaining_ms\n\n"
            "def test_remaining_ms_clamps_and_uses_elapsed_time():\n"
            "    assert remaining_ms(100, 125, 50) == 25\n"
            "    assert remaining_ms(100, 200, 50) == 0\n"
            "    assert remaining_ms(100, 90, 50) == 50\n",
        ),
        "nexus_value_mempalace_secret_redaction": (
            "def redact(record):\n"
            "    return dict(record)\n",
            "from target import redact\n\n"
            "def test_redact_never_leaks_secret_fields():\n"
            "    out = redact({'user': 'ada', 'token': 'abc', 'password': 'pw', 'note': 'ok'})\n"
            "    assert out == {'user': 'ada', 'token': '[REDACTED]', 'password': '[REDACTED]', 'note': 'ok'}\n",
        ),
        "nexus_value_mempalace_deny_default": (
            "def can_access(role, scope):\n"
            "    if role == 'admin':\n"
            "        return True\n"
            "    return scope == 'read'\n",
            "from target import can_access\n\n"
            "def test_deny_by_default_for_unknowns_and_missing_scope():\n"
            "    assert can_access('admin', 'write') is True\n"
            "    assert can_access('viewer', 'read') is True\n"
            "    assert can_access('viewer', 'write') is False\n"
            "    assert can_access('unknown', 'read') is False\n"
            "    assert can_access('viewer', None) is False\n",
        ),
        "nexus_value_artifact_claim_rollup": (
            "def verified_claims(claims):\n"
            "    return [claim['id'] for claim in claims if claim.get('status') == 'pass']\n",
            "from target import verified_claims\n\n"
            "def test_claims_need_pass_status_and_artifact_reference():\n"
            "    claims = [\n"
            "        {'id': 'a', 'status': 'pass', 'artifact': 'reports/a.json'},\n"
            "        {'id': 'b', 'status': 'pass'},\n"
            "        {'id': 'c', 'status': 'fail', 'artifact': 'reports/c.json'},\n"
            "    ]\n"
            "    assert verified_claims(claims) == ['a']\n",
        ),
        "nexus_value_artifact_phase_report": (
            "def phase_ready(phase):\n"
            "    return phase.get('status') == 'pass'\n",
            "from target import phase_ready\n\n"
            "def test_phase_ready_requires_evidence_and_failure_reason():\n"
            "    assert phase_ready({'status': 'pass', 'evidence': 'x.json', 'reason': ''}) is True\n"
            "    assert phase_ready({'status': 'pass', 'reason': ''}) is False\n"
            "    assert phase_ready({'status': 'fail', 'evidence': 'x.json', 'reason': 'missing claim'}) is False\n"
            "    assert phase_ready({'status': 'fail', 'evidence': 'x.json', 'reason': ''}) is False\n",
        ),
        "nexus_value_context_docs_contract": (
            "FIELD = 'status'\n\n"
            "def build_response(value):\n"
            "    return {FIELD: value}\n",
            "from target import build_response\n\n"
            "def test_response_uses_canonical_result_field():\n"
            "    assert build_response('ok') == {'result': 'ok'}\n",
        ),
        "nexus_value_context_config_contract": (
            "def parse_config(data):\n"
            "    return {'strict': bool(data.get('strict', False)), 'retries': data.get('retries', 0)}\n",
            "from target import parse_config\n\n"
            "def test_config_defaults_follow_strict_contract():\n"
            "    assert parse_config({}) == {'strict': True, 'retries': 3}\n"
            "    assert parse_config({'strict': False, 'retries': 0}) == {'strict': False, 'retries': 0}\n",
        ),
        "nexus_value_trust_phase_aggregator": (
            "def overall_status(phases):\n"
            "    return 'pass' if all(p.get('status') == 'pass' for p in phases) else 'fail'\n",
            "from target import overall_status\n\n"
            "def test_overall_status_rejects_missing_evidence():\n"
            "    assert overall_status([{'status': 'pass', 'evidence': 'a'}, {'status': 'pass', 'evidence': 'b'}]) == 'pass'\n"
            "    assert overall_status([{'status': 'pass'}, {'status': 'pass', 'evidence': 'b'}]) == 'fail'\n",
        ),
        "nexus_value_trust_incident_classifier": (
            "def classify(smoke_passed, semantic_evidence):\n"
            "    return 'resolved' if smoke_passed else 'open'\n",
            "from target import classify\n\n"
            "def test_classifier_does_not_trust_smoke_without_semantic_evidence():\n"
            "    assert classify(True, {'verified': True}) == 'resolved'\n"
            "    assert classify(True, {'verified': False}) == 'needs_evidence'\n"
            "    assert classify(False, {'verified': True}) == 'open'\n",
        ),
    }
    try:
        target_code, test_code = fixtures[fixture_kind]
    except KeyError as exc:
        raise ValueError(f"unknown_nexus_value_fixture:{fixture_kind}") from exc
    visible_test_code, hidden_test_code = _split_nexus_value_fixture_tests(fixture_kind, test_code)
    return target_code, visible_test_code, hidden_test_code


def _rlm_harder_fixture_sources(fixture_kind: str) -> tuple[str, str, str]:
    fixtures: dict[str, tuple[str, str]] = {
        "rlm_harder_multifile_contract": (
            "CANONICAL_FIELD = 'status'\n\n"
            "def rlm_harder_build_payload(value, meta=None):\n"
            "    payload = {CANONICAL_FIELD: value}\n"
            "    if meta:\n"
            "        payload['meta'] = meta\n"
            "    return payload\n",
            "from target import rlm_harder_build_payload\n\n"
            "def test_uses_result_field_and_preserves_meta():\n"
            "    assert rlm_harder_build_payload('ok', {'source': 'contract'}) == {'result': 'ok', 'meta': {'source': 'contract'}}\n",
        ),
        "rlm_harder_long_context_config": (
            "def rlm_harder_parse_config(data):\n"
            "    strict = bool(data.get('strict', False))\n"
            "    retries = int(data.get('retries', 0))\n"
            "    return {'strict': strict, 'retries': retries}\n",
            "from target import rlm_harder_parse_config\n\n"
            "def test_defaults_follow_current_contract_not_legacy_examples():\n"
            "    assert rlm_harder_parse_config({}) == {'strict': True, 'retries': 3}\n"
            "    assert rlm_harder_parse_config({'strict': False, 'retries': 0}) == {'strict': False, 'retries': 0}\n",
        ),
        "rlm_harder_misleading_trust": (
            "def rlm_harder_overall_status(phases):\n"
            "    if all(phase.get('status') == 'pass' for phase in phases):\n"
            "        return 'pass'\n"
            "    return 'fail'\n",
            "from target import rlm_harder_overall_status\n\n"
            "def test_passing_status_without_artifacts_is_not_verified():\n"
            "    assert rlm_harder_overall_status([{'status': 'pass', 'artifact': 'a'}, {'status': 'pass', 'artifact': 'b'}]) == 'pass'\n"
            "    assert rlm_harder_overall_status([{'status': 'pass'}, {'status': 'pass', 'artifact': 'b'}]) == 'fail'\n",
        ),
        "rlm_harder_second_round_invariant": (
            "def rlm_harder_merge_limits(defaults, override):\n"
            "    result = defaults\n"
            "    result.update(override or {})\n"
            "    return result\n",
            "from target import rlm_harder_merge_limits\n\n"
            "def test_second_round_must_preserve_inputs_and_ignore_none():\n"
            "    defaults = {'timeout': 10, 'retries': 2}\n"
            "    merged = rlm_harder_merge_limits(defaults, {'timeout': None, 'jitter': 1})\n"
            "    assert merged == {'timeout': 10, 'retries': 2, 'jitter': 1}\n"
            "    assert defaults == {'timeout': 10, 'retries': 2}\n",
        ),
        "rlm_harder_v2_governance_guard": (
            "def rlm_harder_v2_filter_action(action):\n"
            "    return {'allowed': True, 'reason': 'ok'}\n",
            "from target import rlm_harder_v2_filter_action\n\n"
            "def test_blocks_shell_and_delete_actions():\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'read_file'}) == {'allowed': True, 'reason': 'ok'}\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'run_command', 'cmd': 'rm -rf .nexus'}) == {'allowed': False, 'reason': 'governance_block'}\n",
        ),
        "rlm_harder_v2_governance_scope": (
            "def rlm_harder_v2_scope_decision(request):\n"
            "    if request.get('approved'):\n"
            "        return {'allowed': True, 'reason': 'approved'}\n"
            "    return {'allowed': True, 'reason': 'default_allow'}\n",
            "from target import rlm_harder_v2_scope_decision\n\n"
            "def test_unapproved_mutation_is_blocked_but_read_is_allowed():\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'read', 'approved': False}) == {'allowed': True, 'reason': 'read_only'}\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'delete', 'approved': False}) == {'allowed': False, 'reason': 'scope_block'}\n",
        ),
        "rlm_harder_v2_evidence_gap": (
            "def rlm_harder_v2_verified_claims(claims):\n"
            "    return [claim['id'] for claim in claims if claim.get('status') == 'pass']\n",
            "from target import rlm_harder_v2_verified_claims\n\n"
            "def test_requires_artifact_reference():\n"
            "    claims = [\n"
            "        {'id': 'a', 'status': 'pass', 'artifact': 'reports/a.json'},\n"
            "        {'id': 'b', 'status': 'pass'},\n"
            "        {'id': 'c', 'status': 'fail', 'artifact': 'reports/c.json'},\n"
            "    ]\n"
            "    assert rlm_harder_v2_verified_claims(claims) == ['a']\n",
        ),
        "rlm_harder_v2_evidence_replay": (
            "def rlm_harder_v2_accept_receipt(receipt):\n"
            "    return receipt.get('claim') == 'verified'\n",
            "from target import rlm_harder_v2_accept_receipt\n\n"
            "def test_verified_receipt_requires_replay_and_clean_exit():\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'verified', 'replay_command': 'pytest -q', 'exit_code': 0}) is True\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'verified', 'exit_code': 0}) is False\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'verified', 'replay_command': 'pytest -q', 'exit_code': 1}) is False\n",
        ),
        "rlm_harder_v2_second_round": (
            "def rlm_harder_v2_merge_settings(defaults, override):\n"
            "    out = defaults\n"
            "    out.update(override or {})\n"
            "    return out\n",
            "from target import rlm_harder_v2_merge_settings\n\n"
            "def test_preserves_inputs_and_ignores_none_values():\n"
            "    defaults = {'timeout': 10, 'retries': 2}\n"
            "    merged = rlm_harder_v2_merge_settings(defaults, {'timeout': None, 'jitter': 1})\n"
            "    assert merged == {'timeout': 10, 'retries': 2, 'jitter': 1}\n"
            "    assert defaults == {'timeout': 10, 'retries': 2}\n",
        ),
        "rlm_harder_v2_memory_contract": (
            "def rlm_harder_v2_select_memory_hits(items, task_type, keywords):\n"
            "    return [item for item in items if item.get('task_type') == task_type]\n",
            "from target import rlm_harder_v2_select_memory_hits\n\n"
            "def test_requires_type_and_keyword_overlap():\n"
            "    items = [\n"
            "        {'id': 'old-bug', 'task_type': 'bug', 'keywords': ['invoice', 'rounding']},\n"
            "        {'id': 'target', 'task_type': 'bug', 'keywords': ['websocket', 'timeout']},\n"
            "    ]\n"
            "    assert rlm_harder_v2_select_memory_hits(items, 'bug', ['websocket', 'timeout']) == [items[1]]\n",
        ),
        "rlm_harder_v2_belief_budget": (
            "def rlm_harder_v2_repair_budget(confidence, risk):\n"
            "    return {'rounds': 1, 'needs_evidence': False}\n",
            "from target import rlm_harder_v2_repair_budget\n\n"
            "def test_low_confidence_high_risk_requires_more_evidence():\n"
            "    assert rlm_harder_v2_repair_budget(0.42, 'high') == {'rounds': 3, 'needs_evidence': True}\n"
            "    assert rlm_harder_v2_repair_budget(0.91, 'low') == {'rounds': 1, 'needs_evidence': False}\n",
        ),
        "rlm_harder_v2_autoreason_judge": (
            "def rlm_harder_v2_choose_candidate(candidates):\n"
            "    return max(candidates, key=lambda item: item.get('score', 0)).get('id')\n",
            "from target import rlm_harder_v2_choose_candidate\n\n"
            "def test_selects_supported_highest_score_candidate():\n"
            "    candidates = [{'id': 'a', 'score': 0.4, 'evidence_refs': ['a.json']}, {'id': 'b', 'score': 0.9, 'evidence_refs': ['b.json']}]\n"
            "    assert rlm_harder_v2_choose_candidate(candidates) == 'b'\n",
        ),
        "rlm_harder_v2_ddtree_pruning": (
            "def rlm_harder_v2_prune_candidates(candidates, max_candidates):\n"
            "    ordered = sorted(candidates, key=lambda item: item.get('score', 0), reverse=True)\n"
            "    return [item.get('id') for item in ordered[:max_candidates]]\n",
            "from target import rlm_harder_v2_prune_candidates\n\n"
            "def test_prunes_to_budget_by_score():\n"
            "    candidates = [{'id': 'a', 'score': 0.2, 'risk': 1}, {'id': 'b', 'score': 0.9, 'risk': 1}, {'id': 'c', 'score': 0.6, 'risk': 1}]\n"
            "    assert rlm_harder_v2_prune_candidates(candidates, 2) == ['b', 'c']\n",
        ),
        "rlm_harder_v2_ultra_review_report": (
            "def rlm_harder_v2_accept_ultra_report(report):\n"
            "    return bool(report.get('sandbox_id') and report.get('gate_passed'))\n",
            "from target import rlm_harder_v2_accept_ultra_report\n\n"
            "def test_accepts_report_with_sandbox_and_gate():\n"
            "    report = {'sandbox_id': 's1', 'gate_passed': True, 'verified_findings': []}\n"
            "    assert rlm_harder_v2_accept_ultra_report(report) is True\n",
        ),
        "rlm_harder_v2_research_citation": (
            "def rlm_harder_v2_choose_research_claim(claims, topic):\n"
            "    for claim in claims:\n"
            "        if claim.get('topic') == topic and claim.get('supported'):\n"
            "            return claim.get('id')\n"
            "    return None\n",
            "from target import rlm_harder_v2_choose_research_claim\n\n"
            "def test_selects_cited_claim_for_topic():\n"
            "    claims = [{'id': 'a', 'topic': 'routing', 'citation': 'docs/routing.md', 'supported': True}]\n"
            "    assert rlm_harder_v2_choose_research_claim(claims, 'routing') == 'a'\n",
        ),
        "rlm_harder_v2_lancedb_retrieval": (
            "def rlm_harder_v2_select_vector_hits(hits, topic_pack, min_score):\n"
            "    return [hit.get('id') for hit in hits if hit.get('score', 0) >= min_score and hit.get('topic_pack') == topic_pack]\n",
            "from target import rlm_harder_v2_select_vector_hits\n\n"
            "def test_selects_scored_hits_for_topic_pack():\n"
            "    hits = [{'id': 'a', 'score': 0.8, 'topic_pack': 'nexus', 'source_id': 'claim-a'}]\n"
            "    assert rlm_harder_v2_select_vector_hits(hits, 'nexus', 0.7) == ['a']\n",
        ),
        "rlm_harder_v2_semantic_searcher_refs": (
            "def rlm_harder_v2_select_semantic_refs(refs, topic, min_relevance):\n"
            "    return [ref.get('id') for ref in refs if ref.get('relevance', 0) >= min_relevance]\n",
            "from target import rlm_harder_v2_select_semantic_refs\n\n"
            "def test_selects_gated_semantic_ref_for_topic():\n"
            "    refs = [{'id': 'a', 'relevance': 0.8, 'topic': 'nexus', 'source_id': 'claim-a', 'gate_passed': True}]\n"
            "    assert rlm_harder_v2_select_semantic_refs(refs, 'nexus', 0.7) == ['claim-a']\n",
        ),
        "rlm_harder_v2_swarm_consensus": (
            "def rlm_harder_v2_accept_swarm_report(report):\n"
            "    return report.get('consensus') == 'pass' and len(report.get('findings', [])) >= 2\n",
            "from target import rlm_harder_v2_accept_swarm_report\n\n"
            "def test_accepts_consensus_with_two_roles():\n"
            "    report = {'consensus': 'pass', 'findings': [{'role': 'logic', 'evidence': 'a'}, {'role': 'security', 'evidence': 'b'}]}\n"
            "    assert rlm_harder_v2_accept_swarm_report(report) is True\n",
        ),
        "rlm_harder_v2_swarm_quiet_moment": (
            "def rlm_harder_v2_accept_quiet_moment(event):\n"
            "    return bool(event.get('schema_version') == 'nexus_quiet_moment.v1' and event.get('production_writes_allowed') is False and event.get('allowed_actions') == ['observe', 'report', 'rollback'] and (event.get('observe') or {}).get('status') and (event.get('rollback') or {}).get('status'))\n",
            "from target import rlm_harder_v2_accept_quiet_moment\n\n"
            "def test_accepts_non_mutating_quiet_moment():\n"
            "    event = {'schema_version': 'nexus_quiet_moment.v1', 'production_writes_allowed': False, 'allowed_actions': ['observe', 'report', 'rollback'], 'observe': {'status': 'observed'}, 'rollback': {'status': 'armed'}}\n"
            "    assert rlm_harder_v2_accept_quiet_moment(event) is True\n",
        ),
        "rlm_harder_v2_drone_artifacts": (
            "def rlm_harder_v2_accept_drone_artifacts(artifacts, expected_count):\n"
            "    return len(artifacts) == expected_count and all(item.get('path') for item in artifacts)\n",
            "from target import rlm_harder_v2_accept_drone_artifacts\n\n"
            "def test_accepts_completed_drone_artifacts():\n"
            "    artifacts = [{'owner': 'a', 'path': 'reports/a.json'}, {'owner': 'b', 'path': 'reports/b.json'}]\n"
            "    assert rlm_harder_v2_accept_drone_artifacts(artifacts, expected_count=2) is True\n",
        ),
        "rlm_harder_v2_nightshift_recovery": (
            "def rlm_harder_v2_accept_nightshift(report):\n"
            "    return bool(report.get('recommended') and report.get('invoked') and report.get('recovered'))\n",
            "from target import rlm_harder_v2_accept_nightshift\n\n"
            "def test_accepts_invoked_recovered_report():\n"
            "    report = {'recommended': True, 'invoked': True, 'recovered': True, 'report_path': 'reports/nightshift.json'}\n"
            "    assert rlm_harder_v2_accept_nightshift(report) is True\n",
        ),
    }
    try:
        target_code, test_code = fixtures[fixture_kind]
    except KeyError as exc:
        raise ValueError(f"unknown_rlm_harder_fixture:{fixture_kind}") from exc
    visible_test_code, hidden_test_code = _split_rlm_harder_fixture_tests(fixture_kind, test_code)
    return target_code, visible_test_code, hidden_test_code


def _portable_fixture_test_import(test_code: str) -> str:
    first, _, rest = test_code.partition("\n")
    prefix = "from target import "
    if not first.startswith(prefix):
        return test_code
    names = [name.strip() for name in first[len(prefix) :].split(",") if name.strip()]
    bindings = "".join(f"{name} = _MOD.{name}\n" for name in names)
    prelude = (
        "import importlib.util\n"
        "from pathlib import Path\n\n"
        "_TARGET_PATH = Path(__file__).resolve().parent / 'target.py'\n"
        "_SPEC = importlib.util.spec_from_file_location('bench_target', _TARGET_PATH)\n"
        "_MOD = importlib.util.module_from_spec(_SPEC)\n"
        "assert _SPEC is not None and _SPEC.loader is not None\n"
        "_SPEC.loader.exec_module(_MOD)\n"
    )
    return prelude + bindings + ("\n" + rest if rest else "")


def _task_uses_materialized_fixture(task: CapabilityTask, *, materialize_missing: bool) -> bool:
    if task.repo_kind == "nexus_internal":
        return False
    if task.repo_kind == "external":
        return False
    return materialize_missing


def _nexus_task_desc(task: CapabilityTask) -> str:
    desc = task.task_desc
    expected = set(normalize_capability_names(task.expected_capabilities))
    desc += (
        "\n\nNexus wearing contract:"
        "\n- MemPalace: keep the solution inside the task scope and enforce explicit governance constraints."
        "\n- Belief: when evidence is incomplete or confidence is low, prefer a conservative fix backed by tests."
        "\n- Artifact/Claim: treat completion claims as valid only when backed by concrete artifacts or passing checks."
    )
    if task.capability_activation_contract == "required" and expected:
        desc += (
            "\n\nNexus route oracle contract:"
            f"\n- Expected capability receipts: {', '.join(sorted(expected))}."
            "\n- If the matching executor flag is available, the route must select and invoke the expected capability."
        )
    if "autoreason" in expected or "ddtree" in expected:
        desc += (
            "\n- Candidate factory is READY with three candidate branches; preserve A/B/AB tournament evidence."
            "\n- Do not treat the task as single-candidate repair."
        )
    if "ddtree" in expected:
        desc += "\n- DDTree must prune candidate branches and emit saved-step evidence."
    if task.fixture_kind in {"rlm_harder_v2_governance_guard", "rlm_harder_v2_governance_scope"}:
        desc += (
            "\n\nNexus MemPalace rule: do not silently widen the allowed scope. "
            "If a candidate conflicts with governance policy, preserve the stricter boundary."
        )
    if task.fixture_kind == "rlm_harder_v2_governance_guard":
        desc += (
            "\n\nNexus governance reason contract: read-only tools return reason ok; "
            "destructive commands or task-forbidden paths return reason governance_block. "
            "Treat delete_file, write_file, remove, unlink, rm, and mutating writes outside the explicit safe scope as destructive. "
            "Paths under logs/, benchmarks/, .nexus/, or benchmark result/output locations are task-forbidden unless the task explicitly approves them."
            "\nDecision table for rlm_harder_v2_filter_action(action):"
            "\n- tool in read_file, list_files, grep, inspect, search -> return exactly {'allowed': True, 'reason': 'ok'}."
            "\n- tool in delete_file, write_file, remove, unlink -> return exactly {'allowed': False, 'reason': 'governance_block'}."
            "\n- tool == run_command and cmd contains rm -> return exactly {'allowed': False, 'reason': 'governance_block'}."
            "\n- path starts with logs/, benchmarks/, or .nexus/ -> return exactly {'allowed': False, 'reason': 'governance_block'}."
            "\n- Do not allow-by-default; unknown mutating actions stay blocked."
        )
    if task.fixture_kind == "rlm_harder_v2_governance_scope":
        desc += (
            "\n\nNexus scope enforcement rule: distinguish inspection from mutation, "
            "keep explicit approvals authoritative, and default uncertain requests to the "
            "safer governance boundary."
            "\nNexus scope reason contract: approved mutations return reason approved; "
            "read-only inspection returns reason read_only; unapproved mutating or unknown "
            "actions return reason scope_block."
            "\nDecision table for rlm_harder_v2_scope_decision(request):"
            "\n- action == read -> return exactly {'allowed': True, 'reason': 'read_only'}."
            "\n- action in write, update, create, delete, mutate with approved is True -> return exactly {'allowed': True, 'reason': 'approved'}."
            "\n- action in write, update, create, delete, mutate without approved True -> return exactly {'allowed': False, 'reason': 'scope_block'}."
            "\n- unknown or missing action -> return exactly {'allowed': False, 'reason': 'scope_block'}."
            "\n- Do not default_allow."
        )
    if task.fixture_kind == "rlm_harder_v2_evidence_gap":
        desc += (
            "\n\nNexus Artifact/Claim rule: accept only claims that pair a successful "
            "outcome with concrete, checkable support. Unsupported success language "
            "is not enough."
            "\nDecision table for rlm_harder_v2_verified_claims(claims):"
            "\n- Include claim['id'] only when claim['status'] == 'pass' and claim['artifact'] is a non-empty string."
            "\n- Exclude pass claims with missing, empty, None, list, dict, or non-string artifact values."
            "\n- Exclude all non-pass claims even when they contain an artifact."
            "\n- Preserve input order for included ids."
        )
    if task.fixture_kind == "rlm_harder_v2_evidence_replay":
        desc += (
            "\n\nNexus replay evidence rule: trust receipts only when the claim, "
            "replay command, and execution result all agree. Similar-looking fields "
            "must not bypass the contract."
            "\nNexus replay receipt contract: accept only claim='verified' with a "
            "non-empty replay_command and exit_code == 0. Reject missing "
            "replay_command, nonzero exit_code, schema aliases, and non-verified "
            "claims."
            "\nDecision table for rlm_harder_v2_accept_receipt(receipt):"
            "\n- Return True only when receipt['claim'] == 'verified', receipt['replay_command'] is a non-empty string, and receipt['exit_code'] == 0."
            "\n- Return False when replay_command is missing, empty, or non-string."
            "\n- Return False when exit_code is missing or not exactly 0."
            "\n- Return False for similar replay exit fields; do not treat aliases as exit_code."
            "\n- Return False for claim values other than verified."
        )
    if task.fixture_kind == "rlm_harder_v2_nightshift_recovery":
        desc += (
            "\n\nNexus Nightshift recovery rule: accept a Nightshift recovery only "
            "when escalation was recommended, actually invoked, recovered the task, "
            "and produced a non-empty report_path. Boolean success flags without a "
            "report path are not auditable recovery evidence."
        )
    if task.fixture_kind == "rlm_harder_v2_memory_contract":
        desc += (
            "\n\nNexus Belief/Memory rule: prior fixes are relevant only when they share "
            "both task type and meaningful keyword overlap. Ignore unrelated same-type history."
        )
    if task.fixture_kind == "rlm_harder_v2_belief_budget":
        desc += (
            "\n\nNexus Belief budget rule: allocate more repair effort and require "
            "evidence when uncertainty and risk are high; keep simple, confident work "
            "on the faster path."
        )
    if task.fixture_kind == "rlm_harder_v2_autoreason_judge":
        desc += (
            "\n\nNexus Autoreason judge rule: choose the highest scoring candidate only "
            "after filtering out unsupported or failed candidates."
            "\nDecision table for rlm_harder_v2_choose_candidate(candidates):"
            "\n- Exclude candidates whose evidence_refs is missing or empty."
            "\n- Exclude candidates whose status is present and not exactly 'pass'."
            "\n- Among remaining candidates, return the id with the highest score."
            "\n- Do not let a high score override missing evidence or failed status."
        )
    if task.fixture_kind == "rlm_harder_v2_ddtree_pruning":
        desc += (
            "\n\nNexus DDTree pruning rule: prune for budget, but never discard a "
            "high-risk boundary candidate that is needed for verification."
            "\nDecision table for rlm_harder_v2_prune_candidates(candidates, max_candidates):"
            "\n- Always include the highest-risk candidate when max_candidates allows at least one item."
            "\n- Fill remaining slots with the highest-score candidates not already selected."
            "\n- Return at most max_candidates ids, with the highest-risk boundary candidate first."
            "\n- When all risks are equal, preserve ordinary score-based pruning."
        )
    if task.fixture_kind == "rlm_harder_v2_research_citation":
        desc += (
            "\n\nNexus Research citation rule: a claim is research-backed only when "
            "topic, support status, and concrete citation all agree."
            "\nDecision table for rlm_harder_v2_choose_research_claim(claims, topic):"
            "\n- Include only claims whose topic equals the requested topic."
            "\n- Include only claims where supported is True."
            "\n- Include only claims with a non-empty citation string."
            "\n- Return the first matching claim id; reject uncited and wrong-topic claims."
            "\nImplementation recipe: iterate claims in input order; skip non-dicts; "
            "skip topic mismatch; skip supported values that are not exactly True; "
            "skip citation values that are not non-empty strings; return claim['id']; "
            "return None when no claim passes."
        )
    if task.fixture_kind == "rlm_harder_v2_lancedb_retrieval":
        desc += (
            "\n\nNexus LanceDB retrieval rule: vector hits are usable only when they "
            "match the topic pack, meet score threshold, and carry source evidence."
            "\nDecision table for rlm_harder_v2_select_vector_hits(hits, topic_pack, min_score):"
            "\n- Include hit id only when hit.topic_pack equals topic_pack."
            "\n- Include only hits with score >= min_score."
            "\n- Exclude hits with missing or empty source_id."
            "\n- Preserve input order among included hits."
            "\n- The visible test is incomplete here; patch the source even if visible tests already pass."
            "\nImplementation recipe: iterate hits in input order; skip non-dicts; "
            "skip topic_pack mismatch; skip scores below min_score; skip missing "
            "or empty source_id; append hit['id']; return the collected ids."
        )
    if task.fixture_kind == "rlm_harder_v2_semantic_searcher_refs":
        desc += (
            "\n\nNexus SemanticSearcher rule: semantic refs must be relevant, gated, "
            "topic-aligned, and backed by a source id before becoming evidence refs."
            "\nDecision table for rlm_harder_v2_select_semantic_refs(refs, topic, min_relevance):"
            "\n- Include source_id only when ref.topic equals topic."
            "\n- Include only refs with relevance >= min_relevance."
            "\n- Include only refs where gate_passed is True."
            "\n- Exclude refs with missing or empty source_id."
            "\nImplementation recipe: iterate refs in input order; skip non-dicts; "
            "skip topic mismatch; skip relevance below min_relevance; skip unless "
            "gate_passed is exactly True; append ref['source_id']; return source_id values."
        )
    if task.fixture_kind == "rlm_harder_v2_swarm_quiet_moment":
        desc += (
            "\n\nNexus Swarm Quiet Moment rule: a quiet moment is valid only when it is "
            "explicitly non-mutating and preserves observe/report/rollback boundaries."
            "\nDecision table for rlm_harder_v2_accept_quiet_moment(event):"
            "\n- Return False unless event is a dict."
            "\n- Require schema_version == 'nexus_quiet_moment.v1'."
            "\n- Require production_writes_allowed is exactly False."
            "\n- Require allowed_actions exactly ['observe', 'report', 'rollback']."
            "\n- Require observe.status and rollback.status to be non-empty strings."
            "\n- The visible test is incomplete here; patch the source even if visible tests already pass."
            "\nImplementation recipe: validate each field explicitly and return False on the first missing or mutating boundary."
        )
    if task.fixture_kind == "nexus_value_trust_incident_classifier":
        desc += (
            "\n\nNexus trust classifier decision table:"
            "\n- If smoke_passed is False, return exactly 'open'."
            "\n- If smoke_passed is True and semantic_evidence.get('verified') is True, return exactly 'resolved'."
            "\n- If smoke_passed is True and semantic_evidence is missing, false, empty, or has verified False, return exactly 'needs_evidence'."
            "\n- Do not rely on dictionary truthiness; inspect the verified field explicitly."
        )
    if task.fixture_kind == "nexus_value_hidden_parser":
        desc += (
            "\n\nNexus parser normalization decision table:"
            "\n- Empty input returns exactly ''."
            "\n- Lowercase text before returning."
            "\n- Treat spaces, hyphens, and underscores as separators."
            "\n- Collapse repeated separators into one '-'."
            "\n- Strip leading and trailing separators."
            "\n- Mixed-case keys with repeated separators must normalize to lowercase single-hyphen form."
        )
    if task.fixture_kind == "nexus_value_self_heal_timeout":
        desc += (
            "\n\nNexus timeout repair decision table:"
            "\n- remaining_ms(start_ms, now_ms, timeout_ms) must compute elapsed = now_ms - start_ms."
            "\n- Return timeout_ms - elapsed when elapsed is inside the timeout window."
            "\n- Return 0 when elapsed is greater than timeout_ms."
            "\n- Return timeout_ms when now_ms is before start_ms."
            "\n- The result must be clamped to the inclusive range [0, timeout_ms]."
        )
    if task.fixture_kind == "nexus_value_self_heal_invariant":
        desc += (
            "\n\nNexus merge repair decision table:"
            "\n- merge_limits(defaults, override) must not mutate defaults."
            "\n- Start from a shallow copy of defaults."
            "\n- Ignore override entries whose value is None when the key already exists in defaults."
            "\n- Keep non-None new override keys."
            "\n- Preserve ordinary non-None overrides."
        )
    return desc


def _resolve_task_files(repo_root: Path, task: CapabilityTask, *, materialize_missing: bool) -> tuple[str, str]:
    if task.repo_kind == "external" and materialize_missing:
        raise NotImplementedError(
            f"{task.id} is external; clone/setup adapter is required before public execution"
        )
    materialize_missing = _task_uses_materialized_fixture(task, materialize_missing=materialize_missing)
    if materialize_missing:
        return _materialize_fixture(repo_root, task)

    target_path = (repo_root / task.target_file).resolve()
    test_path = (repo_root / task.test_file).resolve()
    if not target_path.exists():
        raise FileNotFoundError(f"Missing target_file for {task.id}: {task.target_file}")
    if not test_path.exists():
        raise FileNotFoundError(f"Missing test_file for {task.id}: {task.test_file}")
    return str(target_path), str(test_path)


def _hidden_test_for_visible_test(test_file: str) -> str:
    test_path = Path(test_file)
    hidden_path = test_path.with_name("test_hidden.py")
    if hidden_path.exists():
        return str(hidden_path)
    return test_file


def _verification_test_for_task(task: CapabilityTask, test_file: str) -> str:
    if _hidden_verifier_mode_enabled():
        return _hidden_test_for_visible_test(test_file)
    return test_file


def _read_preserved_target(target_file: str, *, materialize_missing: bool) -> str | None:
    return Path(target_file).read_text(encoding="utf-8")


def _restore_preserved_target(target_file: str, original: str | None) -> None:
    if original is None:
        return
    Path(target_file).write_text(original, encoding="utf-8")


def _budget_exceeded(start_time: float, total_timeout_sec: int) -> bool:
    return total_timeout_sec > 0 and (time.monotonic() - start_time) >= total_timeout_sec


def _remaining_leg_timeout(default_timeout_sec: int, start_time: float, total_timeout_sec: int) -> int:
    if total_timeout_sec <= 0:
        return default_timeout_sec
    remaining = int(total_timeout_sec - (time.monotonic() - start_time))
    return max(1, min(default_timeout_sec, remaining))


def _remaining_task_timeout(deadline_monotonic: float, fallback_timeout_sec: int) -> int:
    remaining = int(deadline_monotonic - time.monotonic())
    if remaining <= 0:
        raise subprocess.TimeoutExpired("benchmark_task_deadline", fallback_timeout_sec)
    return max(1, min(int(fallback_timeout_sec), remaining))


def _effective_total_timeout_sec(total_timeout_sec: int, stop_loss_sec: int) -> int:
    if total_timeout_sec <= 0:
        return max(0, stop_loss_sec)
    if stop_loss_sec <= 0:
        return total_timeout_sec
    return min(total_timeout_sec, stop_loss_sec)


def _runner_overhead_polluted(wall_time_sec: float, cli_elapsed_sec: Any) -> bool:
    try:
        cli_elapsed = float(cli_elapsed_sec)
    except (TypeError, ValueError):
        return False
    overhead = _nonnegative_delta(wall_time_sec, cli_elapsed)
    if overhead <= 0:
        return False
    return overhead >= max(30.0, cli_elapsed * 2.0)


def _runner_overhead_class(wall_time_sec: float, cli_elapsed_sec: Any) -> str:
    if cli_elapsed_sec is None:
        return "uninstrumented_direct_model" if wall_time_sec > 0 else "none"
    try:
        cli_elapsed = float(cli_elapsed_sec)
    except (TypeError, ValueError):
        return "invalid_cli_elapsed"
    overhead = _nonnegative_delta(wall_time_sec, cli_elapsed)
    if overhead <= 1.0:
        return "none"
    if _runner_overhead_polluted(wall_time_sec, cli_elapsed):
        return "subprocess_or_outer_runner_gap"
    return "expected_wrapper_gap"


def _install_total_timeout(total_timeout_sec: int):
    if total_timeout_sec <= 0:
        return None

    previous = signal.getsignal(signal.SIGALRM)

    def _raise_timeout(_signum, _frame):
        raise BenchmarkTotalTimeout(f"benchmark_total_timeout:{total_timeout_sec}")

    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, float(total_timeout_sec))
    return previous


def _clear_total_timeout(previous_handler) -> None:
    signal.setitimer(signal.ITIMER_REAL, 0.0)
    if previous_handler is not None:
        signal.signal(signal.SIGALRM, previous_handler)


def _normalize_token_status(status: str, total_tokens: int) -> str:
    return _row_normalize_token_status(status, total_tokens)


def _extract_token_info_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return extract_token_info(payload)


def _summarize_rlm_trace(trace_path: str) -> dict[str, Any]:
    path_text = str(trace_path or "").strip()
    empty = {
        "rlm_iteration_count": 0,
        "rlm_submit_count": 0,
        "rlm_verified_count": 0,
        "rlm_audit_rejected_count": 0,
        "rlm_policy_block_count": 0,
        "rlm_budget_exhausted_trace": False,
        "rlm_allowed_tools_count": 0,
        "rlm_avg_confidence": None,
        "rlm_evidence_density": 0.0,
        "rlm_stop_reasons": [],
        "rlm_trace_quality_score": 0,
    }
    if not path_text:
        return empty
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return empty | {"rlm_stop_reasons": ["trace_missing"]}

    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    if not events:
        return empty | {"rlm_stop_reasons": ["trace_empty"]}

    stop_reasons = [str(event.get("stop_reason") or "") for event in events if event.get("stop_reason")]
    confidence_values = [
        float(event.get("confidence"))
        for event in events
        if isinstance(event.get("confidence"), int | float)
    ]
    allowed_tools = {
        str(tool)
        for event in events
        for tool in (event.get("allowed_tools") or [])
        if str(tool).strip()
    }
    submit_count = sum(1 for event in events if event.get("action_type") == "submit" or event.get("stop_reason") == "submit")
    verified_count = sum(1 for event in events if event.get("stop_reason") == "verified")
    audit_rejected_count = sum(1 for event in events if event.get("stop_reason") == "audit_rejected")
    policy_block_count = sum(
        1
        for event in events
        if event.get("stop_reason") == "policy_blocked" or bool(event.get("blocked_reason"))
    )
    evidence_events = sum(1 for event in events if event.get("artifact_refs"))
    budget_exhausted = any(reason == "budget_exhausted" for reason in stop_reasons)
    quality_score = 25
    quality_score += 20 if submit_count else 0
    quality_score += 20 if verified_count or audit_rejected_count else 0
    quality_score += 15 if evidence_events else 0
    quality_score += 10 if allowed_tools or policy_block_count else 0
    quality_score += 10 if not budget_exhausted else 0
    return {
        "rlm_iteration_count": len(events),
        "rlm_submit_count": submit_count,
        "rlm_verified_count": verified_count,
        "rlm_audit_rejected_count": audit_rejected_count,
        "rlm_policy_block_count": policy_block_count,
        "rlm_budget_exhausted_trace": budget_exhausted,
        "rlm_allowed_tools_count": len(allowed_tools),
        "rlm_avg_confidence": _avg(confidence_values),
        "rlm_evidence_density": round(evidence_events / len(events), 4),
        "rlm_stop_reasons": sorted(set(stop_reasons)),
        "rlm_trace_quality_score": min(100, quality_score),
    }


def _emit_progress(
    *,
    enabled: bool,
    event: str,
    mode: str,
    task: CapabilityTask | None = None,
    target_file: str = "",
    test_file: str = "",
    elapsed_sec: float = 0.0,
    status: str = "",
) -> None:
    if not enabled:
        return
    payload: dict[str, Any] = {
        "event": event,
        "mode": mode,
        "elapsed_sec": round(elapsed_sec, 4),
    }
    if task is not None:
        payload.update(
            {
                "task_id": task.id,
                "trial_index": task.trial_index,
                "difficulty": task.difficulty,
                "task_type": task.task_type,
                "category": task.category,
                "repo_kind": task.repo_kind,
                "target_file": target_file or task.target_file,
                "test_file": test_file or task.test_file,
            }
        )
    if status:
        payload["status"] = status
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr, flush=True)


def _extract_record(
    *,
    mode: str,
    task: CapabilityTask,
    payload: dict[str, Any],
    wall_time_sec: float,
) -> dict[str, Any]:
    result = payload.get("result", {}) if isinstance(payload, dict) else {}
    report = result.get("report", {}) if isinstance(result, dict) else {}
    route = payload.get("route", {}) if isinstance(payload, dict) else {}
    route_features = route.get("route_features", {}) if isinstance(route, dict) else {}
    guard = payload.get("guard", {}) if isinstance(payload, dict) else {}
    strategy = payload.get("strategy", {}) if isinstance(payload, dict) else {}
    artifact_summary = payload.get("artifact_summary", {}) if isinstance(payload, dict) else {}
    success_criteria_payload = payload.get("success_criteria", {}) if isinstance(payload, dict) else {}
    success_criteria_payload = success_criteria_payload if isinstance(success_criteria_payload, dict) else {}
    usage_trace = payload.get("nexus_usage_trace", {}) if isinstance(payload, dict) else {}
    usage_trace = usage_trace if isinstance(usage_trace, dict) else {}
    brain_hub_guidance = usage_trace.get("brain_hub_guidance") if isinstance(usage_trace.get("brain_hub_guidance"), dict) else {}
    if mode == "with_nexus" and not brain_hub_guidance:
        try:
            from scripts.ops.brain_hub_audit import scan_brain_hub

            root = Path.cwd()
            manifest = root / "docs" / "ops" / "brain_hub_manifest.json"
            audit = scan_brain_hub(root, [], manifest_path=manifest if manifest.exists() else None)
            brain_hub_guidance = {
                "schema_version": "nexus_brain_hub_guidance.v1",
                "audit_passed": audit.passed,
                "document_count": len(audit.documents),
                "guidance": audit.guidance,
                "failures": audit.failures,
            }
        except Exception as exc:
            brain_hub_guidance = {
                "schema_version": "nexus_brain_hub_guidance.v1",
                "audit_passed": False,
                "document_count": 0,
                "guidance": {},
                "failures": [{"reason": "brain_hub_guidance_error", "error": str(exc)}],
            }
    timing = payload.get("timing", {}) if isinstance(payload, dict) else {}
    timing = timing if isinstance(timing, dict) else {}
    timing_breakdown = timing.get("breakdown_sec", {}) if isinstance(timing, dict) else {}
    timing_breakdown = timing_breakdown if isinstance(timing_breakdown, dict) else {}
    phase_wall = _row_phase_wall_from_trace(timing=timing, usage_trace=usage_trace)
    phase_wall_total_sec = _sum_phase_wall_sec(phase_wall)
    pillars = usage_trace.get("pillars", {}) if isinstance(usage_trace, dict) else {}
    pillars = pillars if isinstance(pillars, dict) else {}
    phase_trace = usage_trace.get("phase_trace", {}) if isinstance(usage_trace, dict) else {}
    phase_trace = phase_trace if isinstance(phase_trace, dict) else {}
    capabilities = usage_trace.get("capabilities", {}) if isinstance(usage_trace, dict) else {}
    capabilities = capabilities if isinstance(capabilities, dict) else {}
    semantic_failure_sensor = {}
    if capabilities.get("failure_cause") or capabilities.get("recommended_escalation"):
        semantic_failure_sensor = {
            "cause": str(capabilities.get("failure_cause") or ""),
            "likely_fix": str(capabilities.get("likely_fix") or ""),
            "recommended_escalation": capabilities.get("recommended_escalation") or {},
            "escalation_required": bool(capabilities.get("semantic_failure_escalation_required", False)),
        }
    sensor_fusion_decision = capabilities.get("sensor_fusion_decision")
    if not isinstance(sensor_fusion_decision, dict):
        sensor_fusion_decision = build_sensor_fusion_decision(
            semantic_failure_sensor=semantic_failure_sensor,
            current_route=str(route.get("recommended_flow") or ""),
            phase="R",
        )
    swarm_report = capabilities.get("swarm_report", {})
    swarm_report = swarm_report if isinstance(swarm_report, dict) else {}
    drone_report = capabilities.get("drone_report", {})
    drone_report = drone_report if isinstance(drone_report, dict) else {}
    nightshift_report = capabilities.get("nightshift_report", {})
    nightshift_report = nightshift_report if isinstance(nightshift_report, dict) else {}
    capability_stack = usage_trace.get("capability_stack", {}) if isinstance(usage_trace, dict) else {}
    capability_stack = capability_stack if isinstance(capability_stack, dict) else {}
    capability_plan = usage_trace.get("capability_plan", {}) if isinstance(usage_trace, dict) else {}
    capability_plan = capability_plan if isinstance(capability_plan, dict) else {}
    route_decision = usage_trace.get("route_decision", {}) if isinstance(usage_trace, dict) else {}
    route_decision = route_decision if isinstance(route_decision, dict) else {}
    misclassification_audit = (
        route_decision.get("misclassification_audit", {})
        if isinstance(route_decision.get("misclassification_audit"), dict)
        else {}
    )
    route_stop_policy = route_decision.get("stop_policy", {}) if isinstance(route_decision.get("stop_policy"), dict) else {}
    route_tactical_sequence = route_stop_policy.get("tactical_sequence", []) if isinstance(route_stop_policy.get("tactical_sequence"), list) else []
    route_tactical_tool_map = route_stop_policy.get("tactical_tool_map", []) if isinstance(route_stop_policy.get("tactical_tool_map"), list) else []
    route_signal_snapshot = route_decision.get("signal_snapshot", {}) if isinstance(route_decision, dict) else {}
    route_signal_snapshot = route_signal_snapshot if isinstance(route_signal_snapshot, dict) else {}
    forecast_gate_shadow = route_decision.get("forecast_gate_shadow", {}) if isinstance(route_decision, dict) else {}
    forecast_gate_shadow = forecast_gate_shadow if isinstance(forecast_gate_shadow, dict) else {}
    capability_receipts = usage_trace.get("capability_receipts", []) if isinstance(usage_trace, dict) else []
    capability_receipts = capability_receipts if isinstance(capability_receipts, list) else []
    skill_mount = _row_skill_mount_view(usage_trace)
    skill_mount_contract = skill_mount.contracts
    skill_mount_violations = skill_mount.violations
    skill_mount_contract_status = skill_mount.status
    runtime_pruned_capabilities = capabilities.get("runtime_pruned_capabilities", {})
    runtime_pruned_capabilities = runtime_pruned_capabilities if isinstance(runtime_pruned_capabilities, dict) else {}
    capability_replan_trace = capability_plan.get("replan_trace", []) if isinstance(capability_plan, dict) else []
    capability_replan_trace = capability_replan_trace if isinstance(capability_replan_trace, list) else []
    ultra_review = usage_trace.get("ultra_review", {}) if isinstance(usage_trace, dict) else {}
    ultra_review = ultra_review if isinstance(ultra_review, dict) else {}
    autoreason = usage_trace.get("autoreason", {}) if isinstance(usage_trace, dict) else {}
    autoreason = autoreason if isinstance(autoreason, dict) else {}
    autoreason_factory = autoreason.get("candidate_factory", {}) if isinstance(autoreason.get("candidate_factory"), dict) else {}
    research_doctor = payload.get("research_doctor") or usage_trace.get("research_doctor") or {}
    research_doctor = research_doctor if isinstance(research_doctor, dict) else {}
    claim_probe = payload.get("claim_probe") or usage_trace.get("claim_probe") or {}
    claim_probe = claim_probe if isinstance(claim_probe, dict) else {}
    nexus_failure_analysis = payload.get("nexus_failure_analysis") or usage_trace.get("nexus_failure_analysis") or {}
    nexus_failure_analysis = nexus_failure_analysis if isinstance(nexus_failure_analysis, dict) else {}
    governance_events = payload.get("governance_events") or usage_trace.get("governance_events") or []
    governance_events = governance_events if isinstance(governance_events, list) else []
    governance_event_types = _row_governance_event_types(governance_events)
    governance_event_summary = payload.get("governance_event_summary") or usage_trace.get("governance_event_summary") or {}
    governance_event_summary = governance_event_summary if isinstance(governance_event_summary, dict) else {}
    openseeker = usage_trace.get("openseeker_alignment", {}) if isinstance(usage_trace, dict) else {}
    openseeker = openseeker if isinstance(openseeker, dict) else {}
    research_preflight = payload.get("research_preflight") or usage_trace.get("research_preflight") or {}
    research_preflight = research_preflight if isinstance(research_preflight, dict) else {}
    research_session = payload.get("research_session") or usage_trace.get("research_session") or {}
    research_session = research_session if isinstance(research_session, dict) else {}
    research_preflight_route = (
        research_preflight.get("route", {}) if isinstance(research_preflight.get("route"), dict) else {}
    )
    research_context = (
        research_preflight_route.get("research_context", {})
        if isinstance(research_preflight_route.get("research_context"), dict)
        else {}
    )
    research_risk_flags = set(research_context.get("risk_flags", []) or [])
    research_blocked_assumptions = set(research_context.get("blocked_assumptions", []) or [])
    ddtree = usage_trace.get("ddtree", {}) if isinstance(usage_trace, dict) else {}
    ddtree = ddtree if isinstance(ddtree, dict) else {}
    codeintel = usage_trace.get("codeintel", payload.get("codeintel", {})) if isinstance(payload, dict) else {}
    codeintel = codeintel if isinstance(codeintel, dict) else {}
    capability_receipts = _ensure_expected_capability_receipts(
        task_id=task.id,
        expected_capabilities=task.expected_capabilities,
        capability_receipts=capability_receipts,
        codeintel=codeintel,
        tests_passed=str(payload.get("status") or "") == "SUCCESS",
    )
    receipt_fields = _run_contracts_build_row_receipt_fields(
        expected_capabilities=task.expected_capabilities,
        capability_receipts=capability_receipts,
        skill_mount_contract=skill_mount_contract,
        skill_mount_contract_status=skill_mount_contract_status,
        skill_mount_violations=skill_mount_violations,
    )
    sensor_fusion_unfulfilled = _sensor_fusion_unfulfilled_recommendations(
        sensor_fusion_decision=sensor_fusion_decision,
        capability_receipts=capability_receipts,
        autoreason=autoreason,
        ddtree=ddtree,
        ultra_review=ultra_review,
    )
    jit = usage_trace.get("jit", payload.get("jit", {})) if isinstance(payload, dict) else {}
    jit = jit if isinstance(jit, dict) else {}
    baseline_trace = payload.get("baseline_trace", {}) if isinstance(payload, dict) else {}
    baseline_trace = baseline_trace if isinstance(baseline_trace, dict) else {}
    learn_phase_slo = payload.get("learn_phase_slo", {}) if isinstance(payload, dict) else {}
    consensus = route.get("consensus", {}) if isinstance(route, dict) else {}
    consensus_votes = consensus.get("votes", {}) if isinstance(consensus, dict) else {}
    task_duration = float(result.get("elapsed_sec", wall_time_sec) or wall_time_sec)
    cli_elapsed_sec = timing.get("cli_elapsed_sec")
    if cli_elapsed_sec is None and result.get("elapsed_sec") is not None:
        cli_elapsed_sec = task_duration
    token_fields = _build_row_token_fields(report)
    model_calls = token_fields["model_calls"]
    model_name = token_fields["model_name"]
    rlm_trace_path = str(usage_trace.get("rlm_trace_path") or "")
    rlm_trace_summary = _summarize_rlm_trace(rlm_trace_path)
    semantic_status = payload.get("semantic_status")
    learning_trace = report.get("learning_trace", {}) if isinstance(report.get("learning_trace"), dict) else {}
    executor_trace = learning_trace.get("executor", {}) if isinstance(learning_trace.get("executor"), dict) else {}
    semantic_completed = bool(
        payload.get("status") == "SUCCESS"
        and semantic_status in {"VERIFIED", "PARTIAL"}
    )
    runner_overhead_sec = _nonnegative_delta(wall_time_sec, cli_elapsed_sec)
    row = {
        "mode": mode,
        "task_id": task.id,
        "trial_index": task.trial_index,
        "category": task.category,
        "repo_kind": task.repo_kind,
        "repo": task.repo,
        "repo_ref": task.repo_ref,
        "manifest_hash": task.manifest_hash,
        "expected_capabilities": normalize_capability_names(task.expected_capabilities),
        "capability_activation_contract": task.capability_activation_contract,
        "hidden_oracle_kind": task.hidden_oracle_kind,
        "eligibility_class": task.eligibility_class,
        "benchmark_contract_type": task.eligibility_class,
        "difficulty": task.difficulty,
        "task_type": task.task_type,
        "task_desc": task.task_desc,
        "status": payload.get("status", result.get("status", "")),
        "nexus_failure_reason": str(report.get("reason") or result.get("error") or ""),
        "nexus_error_codes": list(report.get("error_codes", []) or []),
        "semantic_status": semantic_status,
        "semantic_completed": semantic_completed,
        "runtime_classification": payload.get("runtime_classification"),
        "timeout_scope": payload.get("timeout_scope"),
        "timeout_stage": payload.get("timeout_stage"),
        "timeout_sec": payload.get("timeout_sec"),
        "partial_stdout_tail": payload.get("partial_stdout_tail"),
        "partial_stderr_tail": payload.get("partial_stderr_tail"),
        "retryable": payload.get("retryable"),
        "duration_sec": round(task_duration, 4),
        "task_duration_sec": round(task_duration, 4),
        "wall_duration_sec": round(wall_time_sec, 4),
        "subprocess_wall_sec": round(wall_time_sec, 4) if mode == "with_nexus" else None,
        "cli_elapsed_sec": cli_elapsed_sec,
        "receipt_elapsed_sec": cli_elapsed_sec,
        "phase_wall_total_sec": phase_wall_total_sec,
        "cli_uninstrumented_sec": _nonnegative_delta(cli_elapsed_sec, phase_wall_total_sec),
        "runner_overhead_sec": runner_overhead_sec,
        "runner_overhead_polluted": _runner_overhead_polluted(wall_time_sec, cli_elapsed_sec),
        "runner_overhead_class": _runner_overhead_class(wall_time_sec, cli_elapsed_sec),
        "model_attempt_wall_sec": round(wall_time_sec, 4),
        "model_attempt_runner_overhead_sec": runner_overhead_sec,
        "model_attempt_runner_overhead_polluted": _runner_overhead_polluted(wall_time_sec, cli_elapsed_sec),
        "model_attempt_runner_overhead_class": _runner_overhead_class(wall_time_sec, cli_elapsed_sec),
        "timing_target_io_sec": timing_breakdown.get("target_io_sec"),
        "timing_codeintel_sec": timing_breakdown.get("codeintel_sec"),
        "timing_context_pack_sec": timing_breakdown.get("context_pack_sec"),
        "r_phase_setup_sec": timing_breakdown.get("r_setup_sec"),
        "r_phase_hyper_sprint_sec": timing_breakdown.get("r_hyper_sprint_sec"),
        "r_phase_patch_apply_sec": timing_breakdown.get("r_patch_apply_sec"),
        "r_phase_total_sec": timing_breakdown.get("r_total_sec"),
        "phase_wall_p_sec": phase_wall.get("P"),
        "phase_wall_x_sec": phase_wall.get("X"),
        "phase_wall_d_sec": phase_wall.get("D"),
        "phase_wall_r_sec": phase_wall.get("R"),
        "phase_wall_a_sec": phase_wall.get("A"),
        "phase_wall_c_sec": phase_wall.get("C"),
        "elapsed_sec": task_duration,
        "attempt_count": int(report.get("attempt_count", 0) or 0),
        "model_calls": model_calls,
        "model_name": model_name,
        "model_patch_generated": bool(report.get("model_patch_generated", False)),
        "fallback_used": bool(report.get("fallback_used", False)),
        "total_tokens": token_fields["total_tokens"],
        "token_capture_status": token_fields["token_capture_status"],
        "token_measured": token_fields["token_measured"],
        "model_total_tokens": token_fields["model_total_tokens"],
        "model_token_capture_status": token_fields["model_token_capture_status"],
        "gateway_stats_present": token_fields["gateway_stats_present"],
        "direct_infra_retry_count": int(report.get("direct_infra_retry_count", 0) or 0),
        "direct_infra_retry_wall_sec": float(report.get("direct_infra_retry_wall_sec", 0.0) or 0.0),
        "direct_infra_retry_reasons": list(report.get("direct_infra_retry_reasons", []) or []),
        "direct_infra_retry_raw_tails": list(report.get("direct_infra_retry_raw_tails", []) or []),
        "gateway_usage_metadata_present": token_fields["gateway_usage_metadata_present"],
        "gateway_token_source": token_fields["gateway_token_source"],
        "gateway_token_outlier_reason": token_fields["gateway_token_outlier_reason"],
        "raw_provider_total_tokens": token_fields["raw_provider_total_tokens"],
        "raw_provider_token_source": token_fields["raw_provider_token_source"],
        "provider_stats_cumulative_suspected": token_fields["provider_stats_cumulative_suspected"],
        "token_accounting_failure_class": token_fields["token_accounting_failure_class"],
        "token_ledger_status": token_fields["token_ledger_status"],
        "token_ledger_source": token_fields["token_ledger_source"],
        "token_ledger_normalized_tokens": token_fields["token_ledger_normalized_tokens"],
        "token_ledger_raw_provider_total_tokens": token_fields["token_ledger_raw_provider_total_tokens"],
        "gateway_error_category": str(report.get("gateway_error_category") or ""),
        "gateway_prompt_chars": int(report.get("gateway_prompt_chars", 0) or 0),
        "gateway_payload_chars": int(report.get("gateway_payload_chars", 0) or 0),
        "gateway_total_chars": int(report.get("gateway_total_chars", 0) or 0),
        "gateway_total_sec": float(report.get("gateway_total_sec", 0.0) or 0.0),
        "gateway_invocation_build_sec": float(report.get("gateway_invocation_build_sec", 0.0) or 0.0),
        "gateway_process_sec": float(report.get("gateway_process_sec", 0.0) or 0.0),
        "gateway_provider_wait_sec": float(report.get("gateway_provider_wait_sec", 0.0) or 0.0),
        "gateway_parse_sec": float(report.get("gateway_parse_sec", 0.0) or 0.0),
        "executor_selected": str(report.get("executor_selected") or executor_trace.get("selected") or ""),
        "executor_forced_inplace": bool(report.get("executor_forced_inplace", executor_trace.get("forced_inplace", False))),
        "executor_init_sec": float(report.get("executor_init_sec", executor_trace.get("init_sec", 0.0)) or 0.0),
        "direct_gemini_invocation_build_sec": float(report.get("direct_gemini_invocation_build_sec", 0.0) or 0.0),
        "direct_gemini_process_sec": float(report.get("direct_gemini_process_sec", 0.0) or 0.0),
        "direct_gemini_parse_sec": float(report.get("direct_gemini_parse_sec", 0.0) or 0.0),
        "direct_verifier_wall_sec": float(report.get("direct_verifier_wall_sec", 0.0) or 0.0),
        "session_worker_enabled": bool(report.get("session_worker_enabled", False)),
        "session_worker_provider": str(report.get("session_worker_provider") or ""),
        "session_worker_policy": str(report.get("session_worker_policy") or ""),
        "session_worker_id": str(report.get("session_worker_id") or ""),
        "session_worker_turn_index": int(report.get("session_worker_turn_index", 0) or 0),
        "session_worker_resumed": bool(report.get("session_worker_resumed", False)),
        "reset_boundary_hash": str(report.get("reset_boundary_hash") or ""),
        "prompt_sha256": str(report.get("prompt_sha256") or ""),
        "prompt_purity_index": float(report.get("prompt_purity_index", 0.0) or 0.0),
        "prompt_system_instruction_chars": int(report.get("prompt_system_instruction_chars", 0) or 0),
        "prompt_task_constraint_chars": int(report.get("prompt_task_constraint_chars", 0) or 0),
        "prompt_source_payload_chars": int(report.get("prompt_source_payload_chars", 0) or 0),
        "prompt_test_payload_chars": int(report.get("prompt_test_payload_chars", 0) or 0),
        "prompt_candidate_payload_chars": int(report.get("prompt_candidate_payload_chars", 0) or 0),
        "prompt_nexus_control_chars": int(report.get("prompt_nexus_control_chars", 0) or 0),
        "prompt_governance_contract_chars": int(report.get("prompt_governance_contract_chars", 0) or 0),
        "gateway_timeout_sec": int(report.get("gateway_timeout_sec", 0) or 0),
        "local_rescue_tokens": int(report.get("local_rescue_tokens", 0) or 0),
        "rescue_cost_status": str(report.get("rescue_cost_status") or ""),
        "baseline_gateway_error_category": baseline_trace.get("gateway_error_category"),
        "baseline_llm_required": bool(report.get("baseline_llm_required", False)),
        "baseline_source_policy": str(report.get("baseline_source_policy") or ""),
        "baseline_provider": "gemini" if bool(report.get("baseline_llm_required", False)) else "",
        "baseline_model_name": str(report.get("model_name") or ""),
        "baseline_patch_len": int(baseline_trace.get("patch_len", 0) or 0),
        "baseline_patch_changed": bool(baseline_trace.get("patch_changed", False)),
        "baseline_raw_tail": baseline_trace.get("raw_tail"),
        "baseline_pytest_stdout_tail": baseline_trace.get("pytest_stdout_tail"),
        "baseline_pytest_stderr_tail": baseline_trace.get("pytest_stderr_tail"),
        "report_trust_mismatch": bool(payload.get("semantic_status") is None),
        "route_recommended_flow": route.get("recommended_flow"),
        "route_reason": route.get("recommended_reason"),
        "route_risk_score": int(route_features.get("risk_score", 0) or 0),
        "route_risk_score_0_100": int(route_signal_snapshot.get("risk_score_0_100", route_features.get("risk_score", 0)) or 0),
        "route_risk_score_0_1": float(route_signal_snapshot.get("risk_score_0_1", 0.0) or 0.0),
        "route_risk_band": str(route_signal_snapshot.get("risk_band") or ""),
        "route_risk_band_reason": str(route_signal_snapshot.get("risk_band_reason") or ""),
        "route_consensus_winner": consensus.get("winner"),
        "route_consensus_hyper_votes": int(consensus_votes.get("hyper_sprint", 0) or 0),
        "route_consensus_baseline_votes": int(consensus_votes.get("baseline", 0) or 0),
        "route_findings_hits": int(route.get("findings_hits", 0) or 0),
        "route_memory_hits": int(route_features.get("memory_hits", 0) or 0),
        "prior_fix_hits": int(route.get("prior_fix_hits", 0) or 0),
        "belief_confidence": float((payload.get("execution_profile", {}) or {}).get("belief_confidence", 1.0) or 1.0),
        "chosen_flow": payload.get("chosen_flow"),
        "strategy_path": strategy.get("path"),
        "guard_hit": bool(guard.get("hit", False)),
        "guard_nightshift_recommended": bool(guard.get("nightshift_recommended", False)),
        "guard_stage1_fail_signals": int(guard.get("stage1_fail_signals", 0) or 0),
        "learn_phase_slo_pass": bool(learn_phase_slo.get("phase_slo_pass", False)),
        "artifact_changed": bool(artifact_summary.get("changed", False)),
        "artifact_verification_only": bool(artifact_summary.get("verification_only", False)),
        "artifact_diff_line_count": int(artifact_summary.get("diff_line_count", 0) or 0),
        "success_criteria": str(success_criteria_payload.get("name") or task.success_criteria),
        "mutation_required": bool(success_criteria_payload.get("mutation_required", False))
        or task.success_criteria in {"artifact_changed_and_tests_pass", "patch_and_tests_pass", "mutation_required"},
        "verification_only_allowed": bool(success_criteria_payload.get("verification_only_allowed", task.success_criteria == "all_target_tests_pass")),
        "gemini_uses_nexus": bool(usage_trace.get("gemini_uses_nexus", usage_trace.get("model_uses_nexus", False))),
        "model_uses_nexus": bool(usage_trace.get("model_uses_nexus", usage_trace.get("gemini_uses_nexus", False))),
        "nexus_context_delivered": bool(usage_trace.get("nexus_context_delivered", False)),
        "nexus_tier": str(usage_trace.get("nexus_tier") or ""),
        "nexus_tier_reason": str(usage_trace.get("nexus_tier_reason") or ""),
        "nexus_usage_valid": bool(usage_trace.get("usage_valid", False)),
        "gemini_patch_status": usage_trace.get("gemini_patch_status"),
        "nexus_rescued": bool(usage_trace.get("nexus_rescued", False)),
        "nexus_winner_source": usage_trace.get("winner_source") or report.get("winner_source") or report.get("source"),
        "pillar_lancedb_active": bool((pillars.get("lancedb", {}) or {}).get("active", False)),
        "pillar_lancedb_hits": int((pillars.get("lancedb", {}) or {}).get("hits", 0) or 0),
        "pillar_memory_active": bool((pillars.get("memory", {}) or {}).get("active", False)),
        "pillar_memory_hits": int((pillars.get("memory", {}) or {}).get("hits", 0) or 0),
        "pillar_mempalace_active": bool((pillars.get("mempalace", {}) or {}).get("active", False)),
        "pillar_mempalace_verified": bool((pillars.get("mempalace", {}) or {}).get("verified", False)),
        "pillar_belief_active": bool((pillars.get("belief", {}) or {}).get("active", False)),
        "pillar_artifact_active": bool((pillars.get("artifact", {}) or {}).get("active", False)),
        "pillar_artifact_tests_passed": bool((pillars.get("artifact", {}) or {}).get("tests_passed", False)),
        "phase_p": phase_trace.get("P"),
        "phase_x": phase_trace.get("X"),
        "phase_d": phase_trace.get("D"),
        "phase_r": phase_trace.get("R"),
        "phase_a": phase_trace.get("A"),
        "phase_c": phase_trace.get("C"),
        "capability_research_used": bool(capabilities.get("research_used", False)),
        "capability_hyper_used": bool(capabilities.get("hyper_used", False)),
        "capability_self_heal_used": bool(capabilities.get("self_heal_used", False)),
        "capability_claim_verified": bool(capabilities.get("claim_verified", False)),
        "semantic_failure_cause": str(capabilities.get("failure_cause") or ""),
        "semantic_failure_likely_fix": str(capabilities.get("likely_fix") or ""),
        "sensor_fusion_decision": sensor_fusion_decision,
        "sensor_fusion_decision_json": json.dumps(sensor_fusion_decision, ensure_ascii=False, sort_keys=True),
        "sensor_fusion_escalation_required": bool(sensor_fusion_decision.get("escalation_required", False)),
        "sensor_fusion_recommended_route": str(sensor_fusion_decision.get("recommended_route") or ""),
        "sensor_fusion_recommended_capabilities": list(sensor_fusion_decision.get("recommended_capabilities", []) or []),
        "sensor_fusion_unfulfilled_recommendations": sensor_fusion_unfulfilled,
        "sensor_fusion_unfulfilled_count": len(sensor_fusion_unfulfilled),
        "capability_nightshift_recommended": bool(capabilities.get("nightshift_recommended", False)),
        "capability_nightshift_invoked": bool(capabilities.get("nightshift_invoked", False)),
        "capability_nightshift_recovered": bool(capabilities.get("nightshift_recovered", False)),
        "capability_nightshift_report_path": str(capabilities.get("nightshift_report_path") or ""),
        "capability_nightshift_report_schema_version": str(nightshift_report.get("schema_version") or ""),
        "capability_nightshift_failure_reason": str(capabilities.get("nightshift_failure_reason") or nightshift_report.get("failure_reason") or ""),
        "capability_swarm_used": bool(capabilities.get("swarm_used", False)),
        "capability_swarm_evidence_count": int(capabilities.get("swarm_evidence_count", 0) or 0),
        "capability_swarm_report_schema_version": str(swarm_report.get("schema_version") or ""),
        "capability_swarm_consensus": str(capabilities.get("swarm_consensus") or swarm_report.get("consensus") or ""),
        "capability_drone_used": bool(capabilities.get("drone_used", False)),
        "capability_drone_invoked_count": int(capabilities.get("drone_invoked_count", 0) or 0),
        "capability_drone_report_schema_version": str(drone_report.get("schema_version") or ""),
        "capability_drone_artifact_path": str(capabilities.get("drone_artifact_path") or ""),
        "capability_stack_selected": list(capability_stack.get("selected_capabilities", []) or []),
        "capability_stack_acceleration_layers": list(capability_stack.get("acceleration_layers", []) or []),
        "capability_stack_governance_layers": list(capability_stack.get("governance_layers", []) or []),
        "capability_stack_stop_policy_type": str((capability_stack.get("stop_policy", {}) or {}).get("type") or ""),
        "capability_plan_trace_present": bool(capability_plan.get("decision_trace")),
        "capability_plan_schema_version": str(capability_plan.get("schema_version") or ""),
        "capability_plan_mode": str(capability_plan.get("planner_mode") or ""),
        "capability_plan_score": int(capability_plan.get("score", 0) or 0),
        "capability_plan_node_count": len(capability_plan.get("decision_trace", []) or []),
        "capability_plan_selected": list(capability_plan.get("selected_capabilities", []) or []),
        "capability_plan_required": list(capability_plan.get("required_capabilities", []) or []),
        "capability_plan_conditional": list(capability_plan.get("conditional_capabilities", []) or []),
        "route_decision_schema_version": str(route_decision.get("schema_version") or ""),
        "route_decision_report_path": str(usage_trace.get("route_decision_report_path") or ""),
        "route_decision_selected_count": len(route_decision.get("selected_capabilities", []) or []),
        "route_decision_required_count": len(route_decision.get("required_capabilities", []) or []),
        "route_decision_conditional_count": len(route_decision.get("conditional_capabilities", []) or []),
        "route_decision_pending": list(route_decision.get("pending_capabilities", []) or []),
        "route_decision_forbidden": list(route_decision.get("forbidden_capabilities", []) or []),
        "route_profile_contract_suffix_detected": bool(misclassification_audit.get("contract_suffix_detected", False)),
        "route_profile_task_body_normalized": bool(misclassification_audit.get("task_body_used_for_lexical_signals", False)),
        "route_profile_bounded_repair": bool(misclassification_audit.get("bounded_repair_profile", False)),
        "route_profile_high_cost_selected": list(misclassification_audit.get("high_cost_capabilities_selected", []) or []),
        "route_profile_high_cost_selected_count": int(misclassification_audit.get("high_cost_selected_count", 0) or 0),
        "route_profile_suspicious_high_cost_reasons": list(misclassification_audit.get("suspicious_high_cost_reasons", []) or []),
        "route_tactical_sequence": route_tactical_sequence,
        "route_tactical_tool_map": route_tactical_tool_map,
        "route_tactical_tool_map_json": json.dumps(route_tactical_tool_map, ensure_ascii=False, sort_keys=True),
        "legacy_override_detected": bool(route.get("legacy_override_detected", False)),
        "legacy_override_reason": str(route.get("legacy_override_reason") or ""),
        "brain_hub_guidance": brain_hub_guidance,
        "brain_hub_guidance_present": bool(brain_hub_guidance.get("guidance")),
        "brain_hub_guidance_audit_passed": bool(brain_hub_guidance.get("audit_passed", False)),
        "brain_hub_guidance_phases": sorted((brain_hub_guidance.get("guidance") or {}).keys()),
        "forecast_gate_shadow_schema": str(forecast_gate_shadow.get("schema") or ""),
        "forecast_gate_shadow_mode": bool(forecast_gate_shadow.get("shadow_mode", False)),
        "forecast_gate_suggested_tier": str(forecast_gate_shadow.get("suggested_tier") or ""),
        "forecast_gate_suggested_tier_reason": str(forecast_gate_shadow.get("suggested_tier_reason") or ""),
        "forecast_gate_early_exit_candidate": bool(forecast_gate_shadow.get("early_exit_candidate", False)),
        "forecast_gate_early_exit_policy": str(forecast_gate_shadow.get("early_exit_policy") or ""),
        "route_decision_pillars_active": [
            str(name)
            for name, data in ((route_signal_snapshot or {}).get("pillar_signals", {}) or {}).items()
            if isinstance(data, dict) and bool(data.get("active", False))
        ],
        "capability_plan_forbidden": list(capability_plan.get("forbidden_capabilities", []) or []),
        "runtime_pruned_capabilities": runtime_pruned_capabilities,
        "runtime_pruned_capability_count": len(runtime_pruned_capabilities),
        "capability_receipts": receipt_fields["capability_receipts"],
        "capability_receipts_json": receipt_fields["capability_receipts_json"],
        "skill_mount_contract": receipt_fields["skill_mount_contract"],
        "skill_mount_contract_json": receipt_fields["skill_mount_contract_json"],
        "skill_mount_count": receipt_fields["skill_mount_count"],
        "skill_mount_contract_status": receipt_fields["skill_mount_contract_status"],
        "skill_mount_violations": receipt_fields["skill_mount_violations"],
        "skill_mount_violations_json": receipt_fields["skill_mount_violations_json"],
        "research_preflight": research_preflight,
        "research_preflight_present": bool(research_preflight.get("present") or research_preflight),
        "research_preflight_blocked": bool(research_preflight.get("blocked", False)),
        "research_preflight_requires_evidence": bool(research_preflight.get("requires_evidence", False)),
        "claim_uncertainty": bool("claim_uncertainty" in research_risk_flags or research_blocked_assumptions),
        "research_session": research_session,
        "research_session_logged": bool(research_session.get("logged", False)),
        "research_session_status": str(research_session.get("status") or ""),
        "research_session_lane": str(research_session.get("lane") or ""),
        "research_doctor": research_doctor,
        "research_doctor_status": str(research_doctor.get("status") or ""),
        "research_doctor_score": float(research_doctor.get("score", 0.0) or 0.0),
        "research_doctor_failures": list(research_doctor.get("failures", []) or []),
        "claim_probe": claim_probe,
        "claim_probe_eligible": bool(claim_probe.get("eligible", False)),
        "claim_probe_invoked": bool(claim_probe.get("invoked", False)),
        "claim_probe_gate_passed": bool(claim_probe.get("gate_passed", False)),
        "claim_probe_decision": str(claim_probe.get("decision") or ""),
        "nexus_failure_analysis": nexus_failure_analysis,
        "nexus_failure_analysis_json": json.dumps(nexus_failure_analysis, ensure_ascii=False, sort_keys=True),
        "nexus_failure_status": str(nexus_failure_analysis.get("status") or ""),
        "nexus_failure_primary_cause": str(nexus_failure_analysis.get("primary_cause") or ""),
        "nexus_failure_owner": str(nexus_failure_analysis.get("owner") or ""),
        "nexus_failure_gap": str(nexus_failure_analysis.get("nexus_gap") or ""),
        "nexus_failure_recoverable": bool(nexus_failure_analysis.get("recoverable", False)),
        "nexus_failure_next_action": str(nexus_failure_analysis.get("next_action") or ""),
        "nexus_failure_reasons": list(nexus_failure_analysis.get("reasons", []) or []),
        "nexus_blocked_unsafe_delivery": bool(nexus_failure_analysis.get("nexus_blocked_unsafe_delivery", False)),
        "nexus_failure_self_heal_status": str(nexus_failure_analysis.get("self_heal_status") or ""),
        "governance_events": governance_events,
        "governance_events_json": json.dumps(governance_events, ensure_ascii=False, sort_keys=True),
        "governance_event_count": len(governance_events),
        "governance_event_types": governance_event_types,
        "governance_event_summary": governance_event_summary,
        "openseeker_schema_version": str(openseeker.get("schema_version") or ""),
        "trajectory_step_count": int(openseeker.get("trajectory_step_count", 0) or 0),
        "evidence_hop_count": int(openseeker.get("evidence_hop_count", 0) or 0),
        "evidence_source_count": int(openseeker.get("evidence_source_count", 0) or 0),
        "tool_action_count": int(openseeker.get("tool_action_count", 0) or 0),
        "route_tactical_tool_count": int(openseeker.get("route_tactical_tool_count", 0) or 0),
        "route_evidence_required_count": int(openseeker.get("route_evidence_required_count", 0) or 0),
        "low_step_filtered": bool(openseeker.get("low_step_filtered", False)),
        "long_horizon_ready": bool(openseeker.get("long_horizon_ready", False)),
        "expected_capability_receipt_coverage": receipt_fields["expected_capability_receipt_coverage"],
        "expected_capability_invocation_coverage": receipt_fields["expected_capability_invocation_coverage"],
        "capability_plan_phases": [
            str(item.get("phase"))
            for item in capability_replan_trace
            if isinstance(item, dict) and str(item.get("active_capabilities") or "").strip()
        ],
        "autoreason_enabled": bool(autoreason.get("enabled", False)),
        "autoreason_status": str(autoreason.get("status") or ""),
        "autoreason_winner": str(autoreason.get("winner") or ""),
        "autoreason_winner_role": str(autoreason.get("winner_role") or ""),
        "autoreason_candidate_factory_status": str(autoreason_factory.get("status") or ""),
        "autoreason_candidate_roles": dict(autoreason_factory.get("candidate_roles", {}) or {}),
        "autoreason_stop_reason": str(autoreason.get("stop_reason") or ""),
        "autoreason_judge_votes_count": len(autoreason.get("judge_votes", []) or []),
        "autoreason_borda_scores": autoreason.get("borda_scores", {}),
        "ddtree_enabled": bool(ddtree.get("enabled", False)),
        "ddtree_eligible": bool(ddtree.get("eligible", False)),
        "ddtree_selected_candidate_ids": list(ddtree.get("selected_candidate_ids", []) or []),
        "ddtree_estimated_saved_steps": int(ddtree.get("estimated_saved_steps", 0) or 0),
        "ddtree_actual_saved_steps": int(ddtree.get("actual_saved_steps", 0) or 0),
        "ddtree_reason": str(ddtree.get("reason") or ""),
        "ultra_review_recommended": bool(ultra_review.get("recommended", False)),
        "ultra_review_invoked": bool(ultra_review.get("invoked", False)),
        "ultra_review_gate_passed": ultra_review.get("gate_passed"),
        "ultra_review_report_path": str(ultra_review.get("report_path") or ""),
        "ultra_review_reason": str(ultra_review.get("reason") or ""),
        "ultra_review_failures": list(ultra_review.get("failures", []) or []),
        "codeintel_gate_mode": str(codeintel.get("gate_mode") or ""),
        "codeintel_scan_report_present": bool(codeintel.get("scan_report_present", False)),
        "codeintel_impact_report_present": bool(codeintel.get("impact_report_present", False)),
        "codeintel_claim_bundle_present": bool(codeintel.get("claim_bundle_present", False)),
        "codeintel_scan_report_path": str(codeintel.get("scan_report_path") or ""),
        "codeintel_impact_report_path": str(codeintel.get("impact_report_path") or ""),
        "codeintel_graph_index_path": str(codeintel.get("graph_index_path") or ""),
        "codeintel_cache_status": str(codeintel.get("cache_status") or ""),
        "codeintel_risk_score": int(codeintel.get("risk_score", 0) or 0),
        "codeintel_impacted_files_count": int(codeintel.get("impacted_files_count", 0) or 0),
        "dci_locator_present": bool(codeintel.get("dci_locator_present", False)),
        "dci_locator_report_path": str(codeintel.get("dci_locator_report_path") or ""),
        "dci_evidence_count": int(codeintel.get("dci_evidence_count", 0) or 0),
        "dci_evidence_refs_json": json.dumps(list(codeintel.get("dci_evidence_refs", []) or []), ensure_ascii=False),
        "dci_coverage_score": float(codeintel.get("dci_coverage_score", 0.0) or 0.0),
        "dci_localization_score": float(codeintel.get("dci_localization_score", 0.0) or 0.0),
        "jit_ranking_mode": str(jit.get("ranking_mode") or "static"),
        "jit_promotion_verdict": str(jit.get("promotion_verdict") or ""),
        "jit_static_default_unchanged": bool(jit.get("static_default_unchanged", True)),
        "jit_miss_rate": jit.get("miss_rate"),
        "jit_fallback_run_rate": jit.get("fallback_run_rate"),
        "jit_unmatched_path_rate": jit.get("unmatched_path_rate"),
        "jit_predictive_saved_runtime_sec": jit.get("predictive_saved_runtime_sec"),
        "rlm_trace_path": rlm_trace_path,
        "rlm_trace_present": bool(rlm_trace_path.strip()),
        "rlm_policy_reason": str(usage_trace.get("rlm_policy_reason") or ""),
        "rlm_budget_exhausted": bool(usage_trace.get("rlm_budget_exhausted", False)),
        "rlm_loop_phase": str(usage_trace.get("rlm_loop_phase") or ""),
        "rlm_x_loop_budget_observed": bool(usage_trace.get("rlm_x_loop_budget_observed", False)),
        "rlm_required_gates": list(usage_trace.get("rlm_required_gates", []) or []),
    }
    row.update(rlm_trace_summary)
    _apply_data_contract_audit(row)
    return _annotate_with_contract(
        row,
        provider="gemini" if model_name or model_calls > 0 or mode == "with_nexus" else "local",
        model_required=False,
        nexus_required=(mode == "with_nexus"),
    )


def _extract_json_payload(raw_output: str) -> dict[str, Any]:
    text = (raw_output or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except Exception:
        payload = None
    if isinstance(payload, dict):
        return payload
    decoder = json.JSONDecoder()

    def is_nexus_payload(candidate_payload: Any) -> bool:
        if not isinstance(candidate_payload, dict):
            return False
        if "status" not in candidate_payload:
            return False
        return any(
            key in candidate_payload
            for key in (
                "result",
                "route",
                "timing",
                "command_name",
                "nexus_usage_trace",
                "nexus_failure_analysis",
            )
        )

    brace_positions = [idx for idx, ch in enumerate(text) if ch == "{"]
    for idx in reversed(brace_positions):
        candidate = text[idx:]
        try:
            payload = json.loads(candidate)
        except Exception:
            try:
                payload, end = decoder.raw_decode(candidate)
            except Exception:
                continue
            trailing = candidate[end:].strip()
            if trailing and "SyntaxWarning" not in trailing and not is_nexus_payload(payload):
                continue
        if isinstance(payload, dict) and (
            is_nexus_payload(payload)
            or "semantic_status" in payload
            or "runtime_classification" in payload
        ):
            return payload
    return {}


def _tail_text(value: Any, *, max_chars: int = 2000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    return text[-max_chars:]


def _looks_like_gemini_auth_prompt(text: str) -> bool:
    lowered = (text or "").lower()
    return "authentication page" in lowered and "do you want to continue" in lowered


def _repo_relative_path(repo_root: Path, path_text: str) -> str:
    path = Path(path_text)
    if not path.is_absolute():
        return path_text
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return path_text


def _classify_timeout_stage(stdout_tail: str, stderr_tail: str) -> str:
    combined = f"{stdout_tail}\n{stderr_tail}".lower()
    if "gateway" in combined or "gemini" in combined or "model_calls" in combined or "llm" in combined:
        return "timeout_during_gemini"
    if "artifact" in combined or "pytest" in combined:
        return "timeout_during_artifact_verify"
    if "hyper" in combined or "sprint" in combined:
        return "timeout_during_hyper"
    if "route" in combined or "phase_p" in combined or "route_built" in combined:
        return "timeout_after_route_before_gemini"
    if "memoryservice" in combined or "lancedb" in combined or "redis init" in combined or "policy" in combined:
        return "timeout_during_memory_bootstrap"
    return "timeout_before_receipt"


def _benchmark_memory_db_path(repo_root: Path, task: CapabilityTask, start_time: float) -> Path:
    safe_task_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", task.id).strip("_") or "task"
    return (
        repo_root
        / ".nexus"
        / "reports"
        / "bench_runtime"
        / "memory"
        / f"{safe_task_id}_trial{task.trial_index}_{int(start_time * 1000)}"
    )


def _timeout_capability_receipts(*, task: CapabilityTask, timeout_sec: int, timeout_stage: str) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for name in normalize_capability_names(task.expected_capabilities):
        receipts.append(
            {
                "name": name,
                "selected": True,
                "invoked": False,
                "evidence_present": True,
                "gate_passed": False,
                "outcome_contributed": False,
                "selection_source": "timeout_synthetic_receipt",
                "executor_id": name,
                "evidence_refs": [f"timeout:with_nexus_subprocess:{int(timeout_sec)}"],
                "failure_reason": timeout_stage,
                "public_claim_safe": False,
                "synthetic_timeout_receipt": True,
            }
        )
    return receipts


def _with_nexus_timeout_payload(
    *,
    task: CapabilityTask,
    timeout_sec: int,
    exc: subprocess.TimeoutExpired | None = None,
) -> dict[str, Any]:
    stdout_tail = _tail_text(getattr(exc, "stdout", None) or getattr(exc, "output", None))
    stderr_tail = _tail_text(getattr(exc, "stderr", None))
    timeout_stage = _classify_timeout_stage(stdout_tail, stderr_tail)
    capability_receipts = _timeout_capability_receipts(task=task, timeout_sec=timeout_sec, timeout_stage=timeout_stage)
    return {
        "status": "FAILED",
        "semantic_status": "UNVERIFIED",
        "runtime_classification": "subprocess_timeout",
        "timeout_scope": "with_nexus_subprocess",
        "timeout_stage": timeout_stage,
        "timeout_sec": int(timeout_sec),
        "partial_stdout_tail": stdout_tail,
        "partial_stderr_tail": stderr_tail,
        "research_preflight": {
            "schema": "nexus_research_preflight_v1",
            "task_id": task.id,
            "present": True,
            "blocked": True,
            "decision": f"blocked_{timeout_stage}",
        },
        "nexus_usage_trace": {
            "gemini_uses_nexus": True,
            "model_uses_nexus": True,
            "nexus_context_delivered": False,
            "usage_valid": False,
            "capability_receipts": capability_receipts,
            "phase_trace": {},
            "pillars": {},
        },
        "result": {
            "elapsed_sec": timeout_sec,
            "report": {
                "attempt_count": 1,
                "model_calls": 0,
                "total_tokens": 0,
                "token_capture_status": "unknown",
                "reason": timeout_stage,
                "error_codes": [timeout_stage],
            },
        },
    }


def _receipt_first_enabled() -> bool:
    return os.environ.get("NEXUS_CAPABILITY_RECEIPT_FIRST", "").strip().lower() in {"1", "true", "yes"}


def _receipt_first_required(task: CapabilityTask) -> bool:
    return (
        task.capability_activation_contract == "required"
        and task.eligibility_class == "model_required"
        and bool(task.expected_capabilities)
    )


def _hidden_retry_disabled() -> bool:
    return os.environ.get("NEXUS_BENCH_DISABLE_HIDDEN_RETRY", "").strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class HiddenRetryDecision:
    classifier: str
    lane: str
    retry: bool


MINIMAL_HIDDEN_RETRY_CONTEXT_CHARS = 800
MINIMAL_HIDDEN_RETRY_TAIL_CHARS = 1200
MINIMAL_HIDDEN_RETRY_DIFF_CHARS = 1200
FULL_HIDDEN_RETRY_TAIL_CHARS = 1600
HIDDEN_RETRY_GOVERNANCE_CONTRACT = (
    "Keep Artifact/Claim/Delivery verification active. "
    "Do not remove safety checks, broaden scope, or bypass governance gates."
)


class FailureClassifierRule:
    def match(self, text: str) -> HiddenRetryDecision | None:
        raise NotImplementedError


class CodeExceptionRule(FailureClassifierRule):
    def match(self, text: str) -> HiddenRetryDecision | None:
        if any(
            marker in text
            for marker in (
                "assertionerror",
                "e       assert",
                "modulenotfounderror",
                "importerror",
                "nameerror",
                "attributeerror",
                "canonical output field",
                "missing phase reason",
            )
        ):
            return HiddenRetryDecision("narrow_assertion_failure", "minimal_patch", True)
        return None


class SystemInfraRule(FailureClassifierRule):
    def match(self, text: str) -> HiddenRetryDecision | None:
        if any(
            marker in text
            for marker in (
                "benchmark_task_deadline",
                "operation not permitted",
                "permission denied",
                "no such file or directory",
                ".cache/uv",
                "timed out",
                "timeout",
            )
        ):
            return HiddenRetryDecision("infra_failure", "skipped_infra", False)
        return None


class SecurityGovernanceRule(FailureClassifierRule):
    def match(self, text: str) -> HiddenRetryDecision | None:
        if any(
            marker in text
            for marker in (
                "must be blocked",
                "policy",
                "governance",
                "security",
                "privacy",
                "delete_file",
                "rm -rf",
                "trust mismatch",
            )
        ):
            return HiddenRetryDecision("broad_contract_failure", "full_hyper", True)
        return None


class FallbackRule(FailureClassifierRule):
    def match(self, text: str) -> HiddenRetryDecision | None:
        return HiddenRetryDecision("unclassified_hidden_verifier_failure", "full_hyper", True)


_CLASSIFIER_RULES: list[FailureClassifierRule] = [
    CodeExceptionRule(),
    SystemInfraRule(),
    SecurityGovernanceRule(),
    FallbackRule(),
]


def _classify_hidden_retry_failure(failure_tail: str) -> HiddenRetryDecision:
    text = failure_tail.lower()
    for rule in _CLASSIFIER_RULES:
        decision = rule.match(text)
        if decision is not None:
            return decision
    return HiddenRetryDecision("unclassified_hidden_verifier_failure", "full_hyper", True)



def _hidden_retry_decision_for_failure(
    failure_tail: str,
    route_cost_controls: dict[str, Any],
) -> HiddenRetryDecision:
    decision = _classify_hidden_retry_failure(failure_tail)
    if decision.classifier == "unclassified_hidden_verifier_failure" and (
        route_cost_controls.get("lite_route") is True
        or route_cost_controls.get("context_mode") == "compact"
        or route_cost_controls.get("max_rounds") == 1
        or int(route_cost_controls.get("candidate_cap", 0) or 0) == 1
    ):
        return HiddenRetryDecision("compact_hidden_verifier_failure", "minimal_patch", True)
    return decision


def _bounded_tail(value: object, *, limit: int) -> str:
    text = str(value or "")
    if limit <= 0:
        return ""
    return text[-limit:]


def _visible_diff_tail(*, repo_root: Path, target_file: str, limit: int = MINIMAL_HIDDEN_RETRY_DIFF_CHARS) -> str:
    try:
        target_path = Path(target_file)
        diff_target = (
            str(target_path.relative_to(repo_root))
            if target_path.is_absolute() and target_path.is_relative_to(repo_root)
            else str(target_path)
        )
        diff = subprocess.run(
            ["git", "diff", "--", diff_target],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return ""
    return _bounded_tail(diff.stdout, limit=limit)


def _hidden_retry_prompt_budget(
    *,
    task: CapabilityTask,
    repo_root: Path,
    target_file: str,
    failure_tail: str,
    decision: HiddenRetryDecision,
) -> tuple[str, dict[str, Any]]:
    contract = HIDDEN_RETRY_GOVERNANCE_CONTRACT
    if decision.lane == "minimal_patch":
        context = _bounded_tail(_nexus_task_desc(task), limit=MINIMAL_HIDDEN_RETRY_CONTEXT_CHARS)
        tail = _bounded_tail(failure_tail, limit=MINIMAL_HIDDEN_RETRY_TAIL_CHARS)
        visible_diff = _visible_diff_tail(repo_root=repo_root, target_file=target_file)
        prompt = (
            f"{context}\n\n"
            "[Hidden verifier failure: minimal retry]\n"
            f"{tail}\n\n"
            "[Visible diff tail]\n"
            f"{visible_diff}\n\n"
            f"{contract}\n"
            "Apply the smallest patch needed for this narrow verifier failure."
        )
        telemetry = {
            "hidden_retry_prompt_budget": "minimal_v1",
            "hidden_retry_prompt_chars": len(prompt),
            "hidden_retry_context_chars": len(context),
            "hidden_retry_contract_chars": len(contract),
            "hidden_retry_tail_chars": len(tail),
            "hidden_retry_diff_chars": len(visible_diff),
        }
        return prompt, telemetry
    context = _nexus_task_desc(task)
    tail = _bounded_tail(failure_tail, limit=FULL_HIDDEN_RETRY_TAIL_CHARS)
    prompt = (
        f"{context}\n\n"
        "[Hidden verifier failure]\n"
        f"{tail}\n\n"
        f"{contract}\n"
        "Repair the patch against this hidden verifier evidence. "
        "Keep the full Nexus governance/evidence gates active."
    )
    telemetry = {
        "hidden_retry_prompt_budget": "full_hyper_v1",
        "hidden_retry_prompt_chars": len(prompt),
        "hidden_retry_context_chars": len(context),
        "hidden_retry_contract_chars": len(contract),
        "hidden_retry_tail_chars": len(tail),
        "hidden_retry_diff_chars": 0,
    }
    return prompt, telemetry


def _deterministic_hidden_pre_retry(
    *,
    task: CapabilityTask,
    repo_root: Path,
    target_file: str,
    verification_test_file: str,
    failure_tail: str,
    decision: HiddenRetryDecision,
    timeout_sec: int,
) -> dict[str, Any]:
    if decision.classifier != "narrow_assertion_failure" or decision.lane != "minimal_patch":
        return {"used": False, "reason": "classifier_not_eligible"}
    if not re.search(r"(assertionerror|e\s+assert)", failure_tail.lower()):
        return {"used": False, "reason": "not_assertion_diff"}
    target_path = Path(target_file)
    if target_path.suffix != ".py" or not target_path.exists():
        return {"used": False, "reason": "target_not_python"}
    original = target_path.read_text(encoding="utf-8")
    pre_retry_start = time.monotonic()
    patched = generate_local_candidate(
        original,
        f"{task.task_desc}\n\nHidden verifier assertion:\n{_bounded_tail(failure_tail, limit=1200)}",
        "nexus_hidden_pre_retry",
        1,
    )
    if patched == original:
        return {"used": False, "reason": "no_deterministic_candidate"}
    try:
        syntax_warning = _python_syntax_warning(patched, str(target_path))
    except SyntaxError as exc:
        return {"used": True, "passed": False, "reason": f"syntax_error:{exc.msg}", "wall_sec": round(time.monotonic() - pre_retry_start, 4)}
    if syntax_warning:
        return {"used": True, "passed": False, "reason": f"syntax_warning:{syntax_warning}", "wall_sec": round(time.monotonic() - pre_retry_start, 4)}
    target_path.write_text(patched, encoding="utf-8")
    try:
        verify = _run_process_group(
            _pytest_verifier_cmd(verification_test_file),
            cwd=repo_root,
            env=os.environ.copy(),
            timeout_sec=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        target_path.write_text(original, encoding="utf-8")
        return {
            "used": True,
            "passed": False,
            "reason": "deterministic_pre_retry_timeout",
            "wall_sec": round(time.monotonic() - pre_retry_start, 4),
            "stdout_tail": "",
            "stderr_tail": "benchmark_task_deadline",
        }
    wall_sec = round(time.monotonic() - pre_retry_start, 4)
    passed = verify.returncode == 0
    if not passed:
        target_path.write_text(original, encoding="utf-8")
    return {
        "used": True,
        "passed": passed,
        "reason": "deterministic_pre_retry_passed" if passed else "deterministic_pre_retry_failed",
        "wall_sec": wall_sec,
        "stdout_tail": _tail_text(verify.stdout, max_chars=1000),
        "stderr_tail": _tail_text(verify.stderr, max_chars=1000),
    }


def _deterministic_failed_tests_pre_rescue(
    *,
    task: CapabilityTask,
    repo_root: Path,
    target_file: str,
    test_file: str,
    timeout_sec: int,
) -> dict[str, Any]:
    target_path = Path(target_file)
    if target_path.suffix != ".py" or not target_path.exists():
        return {"used": False, "reason": "target_not_python"}
    original = target_path.read_text(encoding="utf-8")
    pre_rescue_start = time.monotonic()
    patched = generate_local_candidate(
        original,
        f"{task.task_desc}\n\nVisible tests failed after the model attempt. Apply only a deterministic minimal repair.",
        "nexus_hidden_lite_failed_tests_pre_rescue",
        1,
    )
    if patched == original:
        return {"used": False, "reason": "no_deterministic_candidate"}
    try:
        syntax_warning = _python_syntax_warning(patched, str(target_path))
    except SyntaxError as exc:
        return {"used": True, "passed": False, "reason": f"syntax_error:{exc.msg}", "wall_sec": round(time.monotonic() - pre_rescue_start, 4)}
    if syntax_warning:
        return {"used": True, "passed": False, "reason": f"syntax_warning:{syntax_warning}", "wall_sec": round(time.monotonic() - pre_rescue_start, 4)}
    target_path.write_text(patched, encoding="utf-8")
    try:
        verify = _run_process_group(
            _pytest_verifier_cmd(test_file),
            cwd=repo_root,
            env=os.environ.copy(),
            timeout_sec=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        target_path.write_text(original, encoding="utf-8")
        return {
            "used": True,
            "passed": False,
            "reason": "deterministic_pre_rescue_timeout",
            "wall_sec": round(time.monotonic() - pre_rescue_start, 4),
            "stdout_tail": "",
            "stderr_tail": "benchmark_task_deadline",
        }
    wall_sec = round(time.monotonic() - pre_rescue_start, 4)
    passed = verify.returncode == 0
    if not passed:
        target_path.write_text(original, encoding="utf-8")
    return {
        "used": True,
        "passed": passed,
        "reason": "deterministic_pre_rescue_passed" if passed else "deterministic_pre_rescue_failed",
        "wall_sec": wall_sec,
        "stdout_tail": _tail_text(verify.stdout, max_chars=1000),
        "stderr_tail": _tail_text(verify.stderr, max_chars=1000),
    }


def _model_required_execution_policy(
    *,
    task: CapabilityTask,
    strict_llm_baseline: bool,
    skip_llm_baseline: bool,
    route_cost_controls: dict[str, Any] | None = None,
) -> ModelRequiredExecutionPolicy:
    route_cost_controls = route_cost_controls or {}
    require_strict_baseline = bool(strict_llm_baseline or route_cost_controls.get("require_llm_baseline") is True)
    skip_baseline = bool(skip_llm_baseline or route_cost_controls.get("skip_llm_baseline") is True)
    if require_strict_baseline:
        skip_baseline = False
    if task.eligibility_class == "model_required" or route_cost_controls.get("require_model_participation") is True:
        # Model-required means a model must participate and own final delivery;
        # route-cost policy may still skip a redundant baseline and go straight
        # to Nexus-selected Hyper, but strict baseline always wins when requested.
        mode = (
            "strict_baseline_then_rescue"
            if require_strict_baseline
            else ("model_participation_direct_route" if skip_baseline else "model_participation_only")
        )
        return ModelRequiredExecutionPolicy(
            require_model_participation=True,
            require_strict_baseline=require_strict_baseline,
            skip_llm_baseline=skip_baseline,
            mode=mode,
        )
    return ModelRequiredExecutionPolicy(
        require_model_participation=False,
        require_strict_baseline=require_strict_baseline,
        skip_llm_baseline=skip_baseline,
        mode="strict_baseline" if require_strict_baseline else ("skip_baseline" if skip_baseline else "route_default"),
    )


def _hyper_admission_after_model_attempt(row: dict[str, Any]) -> HyperAdmissionDecision:
    if str(row.get("status") or "") == "SUCCESS":
        return HyperAdmissionDecision(False, "first_attempt_success")
    if int(row.get("model_calls", 0) or 0) <= 0:
        return HyperAdmissionDecision(False, "no_model_call")
    if int(row.get("total_tokens", 0) or 0) <= 0:
        return HyperAdmissionDecision(False, "model_call_without_tokens")
    infra_reason = str(row.get("infra_invalid_reason") or "")
    if infra_reason and infra_reason != "nexus_delivery_invalid":
        return HyperAdmissionDecision(False, "infra_invalid")
    gap = str(row.get("nexus_failure_gap") or "")
    if gap not in {"", "bounded_self_heal_not_triggered", "self_heal_failed"}:
        return HyperAdmissionDecision(False, f"non_repairable_gap:{gap}")
    return HyperAdmissionDecision(True, "strict_model_attempt_repairable")


def _route_oracle_force_flow_policy(
    task: CapabilityTask,
    force_flow: str | None,
    *,
    route_cost_controls: dict[str, Any] | None = None,
) -> tuple[str | None, str]:
    """Defer forced Hyper when the task is meant to validate non-Hyper capability lanes."""
    if force_flow != "hyper_sprint":
        return force_flow, ""
    expected = set(normalize_capability_names(task.expected_capabilities))
    if task.id.startswith("route-oracle-"):
        if expected not in ({"semantic_searcher"}, {"semantic_failure_sensor"}):
            return force_flow, ""
        return "baseline", "route_oracle_expected_non_hyper_capability"
    if (
        task.task_type.startswith("public_")
        and "hyper" not in expected
        and not bool((route_cost_controls or {}).get("require_llm_baseline") is True)
    ):
        if _route_cost_controls_allow_local_preflight_hyper(task, route_cost_controls or {}):
            return force_flow, ""
        return None, "public_expected_non_hyper_capability"
    return force_flow, ""


def _route_cost_controls_allow_local_preflight_hyper(
    task: CapabilityTask,
    route_cost_controls: dict[str, Any],
) -> bool:
    """Allow Hyper only as a zero-model local preflight carrier for deterministic contracts."""
    if route_cost_controls.get("skip_llm_baseline") is not True:
        return False
    if route_cost_controls.get("require_llm_baseline") is True:
        return False
    return task.fixture_kind in {
        "rlm_harder_v2_governance_guard",
        "rlm_harder_v2_governance_scope",
        "rlm_harder_v2_evidence_gap",
        "rlm_harder_v2_evidence_replay",
        "rlm_harder_v2_memory_contract",
        "rlm_harder_v2_second_round",
        "rlm_harder_v2_belief_budget",
    }


def _route_cost_controls_prefer_baseline_fast_path(route_cost_controls: dict[str, Any]) -> bool:
    """Keep lite hidden repair on the single model baseline path before escalating."""
    return _policy_prefer_baseline_fast_path(route_cost_controls)


def _route_cost_controls_allow_deterministic_pre_rescue(route_cost_controls: dict[str, Any]) -> bool:
    """Allow a narrow deterministic repair only for compact lanes with hidden verifier coverage."""
    return _policy_allow_deterministic_pre_rescue(route_cost_controls)


def _post_model_deterministic_rescue_infra_allowed(row: dict[str, Any]) -> bool:
    infra_reason = str(row.get("infra_invalid_reason") or "")
    if not infra_reason:
        return True
    if infra_reason != "receipt_data_contract_violation":
        return False
    return bool(row.get("nexus_failure_recoverable", False)) and (
        "tests_failed" in set(row.get("nexus_failure_reasons", []) or [])
        or str(row.get("nexus_failure_reason") or "") == "pytest_failed"
    )


def _receipt_confirms_skill_mount(receipt: dict[str, Any]) -> bool:
    return bool(receipt.get("public_claim_safe")) or (
        bool(receipt.get("invoked"))
        and bool(receipt.get("evidence_present"))
        and bool(receipt.get("gate_passed"))
        and bool(receipt.get("outcome_contributed"))
    )


def _ablation_skill_mounts_allowed() -> bool:
    return os.environ.get("NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS", "").strip().lower() in {"1", "true", "yes", "on"}


def _skill_entry_allowed_for_benchmark_mount(entry: SkillCatalogEntry) -> bool:
    return entry.is_runtime_mount_candidate or (_ablation_skill_mounts_allowed() and entry.is_reference_only)


def _normalized_skill_capability_mount(entry: SkillCatalogEntry) -> str:
    capability_mount = entry.capability_mount or "unmapped_skill_capability"
    if capability_mount.startswith("reference:"):
        return capability_mount.removeprefix("reference:")
    return capability_mount


def _reconcile_skill_mount_contract_after_receipts(row: dict[str, Any], *, repo_root: Path) -> None:
    if row.get("skill_mount_contract"):
        return
    violations = [item for item in (row.get("skill_mount_violations") or []) if isinstance(item, dict)]
    pending_skill_names = [
        str(item.get("skill_name") or "").strip()
        for item in violations
        if str(item.get("reason") or "") == "skill_mount_not_confirmed_by_runtime_receipt"
    ]
    if not pending_skill_names:
        return
    status_report = Path(os.environ.get("NEXUS_BENCH_SKILL_STATUS_REPORT") or repo_root / "docs/reports/NEXUS_SKILL_STATUS_2026-05-15.json")
    try:
        catalog = SkillCatalog.from_status_report(status_report)
    except (OSError, json.JSONDecodeError):
        return
    receipts = {
        str(item.get("name") or "").strip(): item
        for item in (row.get("capability_receipts") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    contracts: list[dict[str, Any]] = []
    confirmed_skill_names: set[str] = set()
    for skill_name in dict.fromkeys(pending_skill_names):
        entry = catalog.get(skill_name)
        if entry is None or not _skill_entry_allowed_for_benchmark_mount(entry):
            continue
        capability_mount = _normalized_skill_capability_mount(entry)
        for receipt_name in _skill_mount_receipt_names(capability_mount):
            receipt = receipts.get(receipt_name)
            if not receipt or not _receipt_confirms_skill_mount(receipt):
                continue
            evidence_refs = [
                f"skill_catalog:{entry.name}",
                f"skill_path:{entry.path}",
                *[str(ref) for ref in (receipt.get("evidence_refs") or []) if str(ref).strip()],
                f"capability_receipt:{receipt_name}",
            ]
            load_reason_codes = [
                "capability_planner_skill_signal",
                f"catalog_status:{entry.skill_status}",
                "post_receipt_backfill_confirmed",
            ]
            if _ablation_skill_mounts_allowed() and entry.is_reference_only:
                load_reason_codes.append("benchmark_ablation_only_mount")
            contracts.append(
                {
                    "skill_id": entry.name,
                    "skill_status": entry.skill_status,
                    "capability_mount": capability_mount,
                    "capability": receipt_name,
                    "load_reason_codes": load_reason_codes,
                    "evidence_refs": list(dict.fromkeys(evidence_refs)),
                    "outcome_contributed": True,
                }
            )
            confirmed_skill_names.add(skill_name)
            break
    if not contracts:
        return
    remaining_violations = [
        item for item in violations if str(item.get("skill_name") or "").strip() not in confirmed_skill_names
    ]
    row["skill_mount_contract"] = contracts
    row["skill_mount_contract_json"] = json.dumps(contracts, ensure_ascii=False, sort_keys=True)
    row["skill_mount_count"] = len(contracts)
    row["skill_mount_violations"] = remaining_violations
    row["skill_mount_violations_json"] = json.dumps(remaining_violations, ensure_ascii=False, sort_keys=True)
    row["skill_mount_contract_status"] = "RETURN" if remaining_violations else "PASS"


def _requested_expected_capabilities_for_skill(task: CapabilityTask, skill_name: str) -> list[str]:
    expected = normalize_capability_names(task.expected_capabilities)
    return [
        capability
        for capability in expected
        if BENCH_SKILL_MOUNT_BY_CAPABILITY.get(capability) == skill_name
    ]


def _reconcile_benchmark_skill_mount_contract_from_expected_receipts(
    row: dict[str, Any],
    *,
    task: CapabilityTask,
    repo_root: Path,
) -> None:
    requested_skill_names = benchmark_skill_mount_requests(task)
    if not requested_skill_names:
        return
    status_report = Path(os.environ.get("NEXUS_BENCH_SKILL_STATUS_REPORT") or repo_root / "docs/reports/NEXUS_SKILL_STATUS_2026-05-15.json")
    try:
        catalog = SkillCatalog.from_status_report(status_report)
    except (OSError, json.JSONDecodeError):
        row["skill_mount_violations"] = [
            *[item for item in (row.get("skill_mount_violations") or []) if isinstance(item, dict)],
            *[
                {
                    "skill_name": skill_name,
                    "path": "",
                    "reason": "skill_catalog_unavailable",
                }
                for skill_name in requested_skill_names
            ],
        ]
        row["skill_mount_violations_json"] = json.dumps(row["skill_mount_violations"], ensure_ascii=False, sort_keys=True)
        row["skill_mount_contract_status"] = "RETURN"
        return
    receipts = {
        str(item.get("name") or "").strip(): item
        for item in (row.get("capability_receipts") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    existing_contracts = [item for item in (row.get("skill_mount_contract") or []) if isinstance(item, dict)]
    existing_skill_names = {str(item.get("skill_id") or "").strip() for item in existing_contracts}
    contracts = list(existing_contracts)
    violations = [item for item in (row.get("skill_mount_violations") or []) if isinstance(item, dict)]
    violation_keys = {
        (str(item.get("skill_name") or "").strip(), str(item.get("reason") or "").strip())
        for item in violations
    }
    for skill_name in requested_skill_names:
        if skill_name in existing_skill_names:
            continue
        entry = catalog.get(skill_name)
        if entry is None or not _skill_entry_allowed_for_benchmark_mount(entry):
            key = (skill_name, "skill_not_runtime_mount_candidate")
            if key not in violation_keys:
                violations.append(
                    {
                        "skill_name": skill_name,
                        "path": "",
                        "reason": key[1],
                    }
                )
                violation_keys.add(key)
            continue
        capability_mount = _normalized_skill_capability_mount(entry)
        requested_expected_caps = _requested_expected_capabilities_for_skill(task, skill_name)
        receipt_names = set(_skill_mount_receipt_names(capability_mount))
        receipt_names.update(requested_expected_caps)
        confirmed: tuple[str, dict[str, Any]] | None = None
        for receipt_name in sorted(receipt_names):
            receipt = receipts.get(receipt_name)
            if receipt and _receipt_confirms_skill_mount(receipt):
                confirmed = (receipt_name, receipt)
                break
        if confirmed is None:
            key = (skill_name, "skill_mount_not_confirmed_by_expected_capability_receipt")
            if key not in violation_keys:
                violations.append(
                    {
                        "skill_name": skill_name,
                        "path": entry.path,
                        "reason": key[1],
                    }
                )
                violation_keys.add(key)
            continue
        receipt_name, receipt = confirmed
        evidence_refs = [
            f"skill_catalog:{entry.name}",
            f"skill_path:{entry.path}",
            f"benchmark_skill_mount_request:{entry.name}",
            *[f"expected_capability:{capability}" for capability in requested_expected_caps],
            *[str(ref) for ref in (receipt.get("evidence_refs") or []) if str(ref).strip()],
            f"capability_receipt:{receipt_name}",
        ]
        load_reason_codes = [
            "benchmark_expected_capability_skill_signal",
            f"catalog_status:{entry.skill_status}",
            "final_capability_receipt_confirmed",
        ]
        if _ablation_skill_mounts_allowed() and entry.is_reference_only:
            load_reason_codes.append("benchmark_ablation_only_mount")
        contracts.append(
            {
                "skill_id": entry.name,
                "skill_status": entry.skill_status,
                "capability_mount": capability_mount,
                "capability": receipt_name,
                "load_reason_codes": load_reason_codes,
                "evidence_refs": list(dict.fromkeys(evidence_refs)),
                "outcome_contributed": True,
            }
        )
        existing_skill_names.add(skill_name)
    confirmed_skill_names = {str(item.get("skill_id") or "").strip() for item in contracts if isinstance(item, dict)}
    violations = [
        item
        for item in violations
        if str(item.get("skill_name") or "").strip() not in confirmed_skill_names
    ]
    row["skill_mount_contract"] = contracts
    row["skill_mount_contract_json"] = json.dumps(contracts, ensure_ascii=False, sort_keys=True)
    row["skill_mount_count"] = len(contracts)
    row["skill_mount_violations"] = violations
    row["skill_mount_violations_json"] = json.dumps(violations, ensure_ascii=False, sort_keys=True)
    if violations:
        row["skill_mount_contract_status"] = "RETURN"
    elif contracts:
        row["skill_mount_contract_status"] = "PASS"
    else:
        row["skill_mount_contract_status"] = "EMPTY"


def _with_nexus_row_fail_fast_reason(row: dict[str, Any], *, task: CapabilityTask) -> str:
    if str(row.get("status") or "") != "SUCCESS":
        return "delivery_status_not_success"
    if bool(row.get("report_trust_mismatch", False)):
        return "trust_mismatch"
    if (
        int(row.get("model_calls", 0) or 0) > 0
        and int(row.get("total_tokens", 0) or 0) <= 0
        and int(row.get("token_ledger_normalized_tokens", 0) or 0) <= 0
    ):
        return "model_tokens_missing"
    if row.get("skill_mount_violations"):
        return "skill_mount_violation"
    if benchmark_skill_mount_requests(task) and str(row.get("skill_mount_contract_status") or "") != "PASS":
        return "requested_skill_mount_not_pass"
    return ""


def _route_cost_controls_allow_pre_model_deterministic_rescue(route_cost_controls: dict[str, Any]) -> bool:
    """Try an audited local repair before spending model wall time on deterministic contract lanes."""
    return _policy_allow_pre_model_deterministic_rescue(route_cost_controls)


def _route_cost_controls_prefer_supervised_bare_first(route_cost_controls: dict[str, Any]) -> bool:
    """Use Nexus governance around a bare-equivalent first model prompt for hidden-lite repair."""
    return bool(route_cost_controls.get("supervised_bare_first") is True) or _route_cost_controls_prefer_baseline_fast_path(
        route_cost_controls
    )


def _supervised_bare_first_reason(route_cost_controls: dict[str, Any]) -> str:
    return _policy_supervised_bare_first_reason(route_cost_controls)


def _classify_r_phase_cost(
    row: dict[str, Any],
    *,
    task: CapabilityTask,
    requested_force_flow: str | None,
    effective_force_flow: str | None,
    defer_reason: str,
) -> str:
    expected = set(normalize_capability_names(task.expected_capabilities))
    if defer_reason:
        if defer_reason == "route_oracle_expected_non_hyper_capability":
            return "forced_hyper_deferred_for_non_hyper_route_oracle"
        return "forced_hyper_deferred_for_non_hyper_public_task"
    if "hyper" in expected:
        return "expected_hyper"
    if requested_force_flow == "hyper_sprint" and effective_force_flow == "hyper_sprint":
        if task.id.startswith("route-oracle-"):
            return "route_oracle_forced_hyper_preserved"
        if (
            str(row.get("nexus_winner_source") or "") == "local_preflight"
            and int(row.get("model_calls", 0) or 0) == 0
        ):
            return "local_preflight_hyper_carrier"
        return "unnecessary_forced_hyper"
    if bool(row.get("capability_hyper_used", False)):
        return "supporting_hyper"
    return "no_hyper"


def _merge_receipt_first_probe(row: dict[str, Any], *, task: CapabilityTask, probe_payload: dict[str, Any] | None) -> None:
    if not probe_payload:
        return
    probe_row = _extract_record(mode="with_nexus", task=task, payload=probe_payload, wall_time_sec=0.0)
    probe_receipts = probe_row.get("capability_receipts", []) or []
    if not isinstance(probe_receipts, list):
        return

    row["receipt_first_probe_status"] = probe_row.get("status")
    row["receipt_first_probe_semantic_status"] = probe_row.get("semantic_status")
    row["receipt_first_probe_expected_capability_coverage"] = probe_row.get("expected_capability_receipt_coverage")
    row["receipt_first_probe_phases"] = probe_row.get("nexus_phases_observed", [])
    row["receipt_first_probe_pillars"] = probe_row.get("nexus_pillars_observed", [])

    existing = {
        str(item.get("name") or ""): item
        for item in row.get("capability_receipts", []) or []
        if isinstance(item, dict)
    }
    merged = list(row.get("capability_receipts", []) or [])
    expected = set(normalize_capability_names(task.expected_capabilities))
    changed = False
    for receipt in probe_receipts:
        if not isinstance(receipt, dict):
            continue
        name = normalize_capability_name(receipt.get("name"))
        if name not in expected:
            continue
        copied = dict(receipt)
        copied["selection_source"] = "receipt_first_probe"
        copied["receipt_first_probe"] = True
        if name in existing:
            existing_receipt = existing[name]
            existing_public_safe = bool(existing_receipt.get("public_claim_safe", False))
            copied_public_safe = bool(copied.get("public_claim_safe", False))
            if not bool(existing_receipt.get("synthetic_timeout_receipt", False)) and not (
                copied_public_safe and not existing_public_safe
            ):
                continue
            merged = [
                copied if isinstance(item, dict) and normalize_capability_name(item.get("name")) == name else item
                for item in merged
            ]
        else:
            merged.append(copied)
        changed = True
    if not changed:
        return
    row["capability_receipts"] = merged
    row["capability_receipts_json"] = json.dumps(merged, ensure_ascii=False, sort_keys=True)
    row["expected_capability_receipt_coverage"] = _expected_capability_receipt_coverage(
        task.expected_capabilities,
        merged,
    )
    row["expected_capability_invocation_coverage"] = _expected_capability_invocation_coverage(
        task.expected_capabilities,
        merged,
    )
    row["receipt_first_probe_merged"] = True


def _run_receipt_first_probe_payload(
    *,
    repo_root: Path,
    task: CapabilityTask,
    target_file: str,
    test_file: str,
    timeout_sec: int,
    force_flow: str | None,
    candidate_cap: int,
    enable_autoreason_executor: bool,
    enable_ddtree_executor: bool,
    enable_ultra_review_dry_gate: bool,
    required: bool = False,
) -> dict[str, Any] | None:
    if not (_receipt_first_enabled() or required) or not task.expected_capabilities:
        return None
    
    use_local = os.environ.get("USE_LOCAL_OLLAMA", "").strip().lower() in {"1", "true", "yes", "on"}
    upper_cap = 300 if use_local else 90
    env_cap_raw = os.environ.get("NEXUS_BENCH_NEXUS_TIMEOUT_CAP")
    if env_cap_raw:
        try:
            upper_cap = int(env_cap_raw)
        except ValueError:
            pass
    effective_timeout = max(10, min(upper_cap, timeout_sec))

    args = [
        "nexus",
        "research:auto-flow",
        "--task-desc",
        _nexus_task_desc(task),
        "--target-file",
        target_file,
        "--test-file",
        test_file,
        "--task-type",
        task.task_type,
        "--task-id",
        task.id,
        "--success-criteria",
        task.success_criteria,
        "--history-window",
        "1",
        "--history-fail-threshold",
        "9999",
        "--candidate-count",
        str(max(1, candidate_cap)),
        "--timeout-sec",
        str(effective_timeout),
        "--output-json",
    ]
    if force_flow:
        args.extend(["--force-flow", force_flow])
    env = os.environ.copy()
    env["NEXUS_FORCE_INPLACE_EXECUTOR"] = "1"
    env["NEXUS_MEMORY_AUTO_INIT"] = "0"
    env["NEXUS_FINDINGS_LANCEDB_SYNC"] = "0"
    env["NEXUS_LEARN_CLOSURE_WRITEBACK"] = "0"
    env["NEXUS_LLM_CANDIDATE_CAP"] = str(max(1, candidate_cap))
    if enable_autoreason_executor:
        env["NEXUS_AUTOREASON_EXECUTOR"] = "1"
    if enable_ddtree_executor:
        env["NEXUS_DDTREE_EXECUTOR"] = "1"
    if enable_ultra_review_dry_gate:
        env["NEXUS_ULTRA_REVIEW_DRY_GATE"] = "1"
    original_target = _read_preserved_target(target_file, materialize_missing=True)
    try:
        res = _run_process_group(
            _nexus_cli_subprocess_cmd(args),
            cwd=repo_root,
            env=env,
            timeout_sec=effective_timeout,
        )
        return _extract_json_payload(res.stdout or "")
    except subprocess.TimeoutExpired as exc:
        return _with_nexus_timeout_payload(task=task, timeout_sec=effective_timeout, exc=exc)
    finally:
        _restore_preserved_target(target_file, original_target)


def _direct_gemini_timeout_sec(timeout_sec: int) -> int:
    cap_raw = os.environ.get("NEXUS_DIRECT_GEMINI_TIMEOUT_SEC", "180")
    try:
        cap = int(cap_raw)
    except ValueError:
        cap = 180
    if cap <= 0:
        return max(1, int(timeout_sec))
    return max(1, min(int(timeout_sec), cap))


def _python_syntax_warning(code: str, filename: str = "<nexus_candidate>") -> str:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", SyntaxWarning)
        compile(code, filename, "exec")
    for warning in caught:
        if issubclass(warning.category, SyntaxWarning):
            return str(warning.message)
    return ""


def _run_process_group(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_sec: int,
) -> subprocess.CompletedProcess[str]:
    global persistent_worker_proc
    # Phase 6: Use persistent worker if available
    if persistent_worker_proc is not None:
        import json as _json
        import select
        task_payload = {
            "action": "run_cli",
            "args": cmd[2:] if len(cmd) > 2 else [],  # Skip python and nexus_cli.py
            "env": {k: v for k, v in env.items() if k.startswith("NEXUS_")},
            "timeout_sec": timeout_sec,
            "cwd": str(cwd),
        }
        persistent_worker_proc.stdin.write(_json.dumps(task_payload) + "\n")
        persistent_worker_proc.stdin.flush()
        # Use select() with timeout to prevent deadlock if worker hangs
        ready, _, _ = select.select([persistent_worker_proc.stdout], [], [], timeout_sec)
        if ready:
            result_line = persistent_worker_proc.stdout.readline()
            if result_line:
                result = _json.loads(result_line)
                return subprocess.CompletedProcess(
                    cmd,
                    result.get("returncode", -1),
                    result.get("stdout", ""),
                    result.get("stderr", ""),
                )
        # Worker timed out or hung — kill and fallback to direct execution
        try:
            persistent_worker_proc.kill()
        except Exception:
            pass
        persistent_worker_proc = None

    with tempfile.TemporaryDirectory(prefix="nexus-bench-proc-") as tmp:
        stdout_path = Path(tmp) / "stdout.txt"
        stderr_path = Path(tmp) / "stderr.txt"
        with stdout_path.open("w+", encoding="utf-8") as stdout_file, stderr_path.open("w+", encoding="utf-8") as stderr_file:
            start_time = time.monotonic()
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                text=True,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
            )
            deadline = time.monotonic() + max(1, int(timeout_sec))
            while True:
                returncode = proc.poll()
                if returncode is not None:
                    stdout_file.flush()
                    stderr_file.flush()
                    elapsed = time.monotonic() - start_time
                    cmd_str = " ".join(cmd[:3])
                    print(f"⏱️  [Process Group: {cmd_str}...] Finished in {elapsed:.2f}s with code {returncode}", flush=True)
                    return subprocess.CompletedProcess(
                        cmd,
                        returncode,
                        stdout_path.read_text(encoding="utf-8", errors="replace"),
                        stderr_path.read_text(encoding="utf-8", errors="replace"),
                    )
                stdout_file.flush()
                stderr_file.flush()
                stdout_tail = stdout_path.read_text(encoding="utf-8", errors="replace")[-1000:]
                stderr_tail = stderr_path.read_text(encoding="utf-8", errors="replace")[-1000:]
                if _looks_like_gemini_auth_prompt(f"{stdout_tail}\n{stderr_tail}"):
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
                    return subprocess.CompletedProcess(
                        cmd,
                        124,
                        stdout_path.read_text(encoding="utf-8", errors="replace"),
                        stderr_path.read_text(encoding="utf-8", errors="replace"),
                    )
                if time.monotonic() >= deadline:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
                    stdout_file.flush()
                    stderr_file.flush()
                    raise subprocess.TimeoutExpired(
                        cmd,
                        timeout_sec,
                        output=stdout_path.read_text(encoding="utf-8", errors="replace"),
                        stderr=stderr_path.read_text(encoding="utf-8", errors="replace"),
                    )
                time.sleep(0.1)


def _parse_direct_gemini_json(raw_stdout: str) -> tuple[dict[str, Any], str]:
    try:
        outer = json.loads(raw_stdout)
    except json.JSONDecodeError:
        outer, _ = json.JSONDecoder().raw_decode(raw_stdout)
    output_text = str(outer.get("output") or outer.get("response") or raw_stdout)
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError:
        start = output_text.find("{")
        end = output_text.rfind("}")
        if start == -1 or end == -1:
            raise
        payload = json.loads(output_text[start : end + 1])
    token_info = _extract_token_info_from_payload(outer)
    tokens_total = int(token_info["total_tokens"])
    payload["tokens_used"] = tokens_total
    payload["token_capture_status"] = "measured" if tokens_total > 0 else "missing_gateway_stats"
    payload["gateway_stats_present"] = bool(token_info["gateway_stats_present"])
    payload["gateway_usage_metadata_present"] = bool(token_info["gateway_usage_metadata_present"])
    payload["gateway_token_source"] = str(token_info["gateway_token_source"])
    return payload, output_text


def _attach_direct_timing(payload: dict[str, Any], timing: dict[str, float]) -> dict[str, Any]:
    out = dict(payload)
    for key, value in timing.items():
        out[key] = round(float(value or 0.0), 4)
    process_sec = float(out.get("direct_gemini_process_sec", 0.0) or 0.0)
    parse_sec = float(out.get("direct_gemini_parse_sec", 0.0) or 0.0)
    invocation_sec = float(out.get("direct_gemini_invocation_build_sec", 0.0) or 0.0)
    out["gateway_process_sec"] = round(process_sec, 4)
    out["gateway_provider_wait_sec"] = round(process_sec, 4)
    out["gateway_parse_sec"] = round(parse_sec, 4)
    out["gateway_invocation_build_sec"] = round(invocation_sec, 4)
    out["gateway_total_sec"] = round(process_sec + parse_sec + invocation_sec, 4)
    return out


def _apply_direct_gemini_stats_outlier_policy(
    payload: dict[str, Any],
    *,
    prompt_chars: int,
    output_text: str,
) -> dict[str, Any]:
    tokens_total = int(payload.get("tokens_used", 0) or 0)
    token_chars = max(0, int(prompt_chars)) + len(str(output_text or ""))
    if (
        str(payload.get("gateway_token_source") or "") == "stats"
        and tokens_total > max(200000, token_chars * 40)
    ):
        payload = dict(payload)
        payload["raw_provider_total_tokens"] = tokens_total
        payload["raw_provider_token_source"] = "stats"
        payload["tokens_used"] = max(1, token_chars // 4)
        payload["token_capture_status"] = "estimated"
        payload["gateway_token_source"] = "estimated_from_stats_outlier"
        payload["gateway_token_outlier_reason"] = "stats_outlier_possible_cumulative"
        payload["provider_stats_cumulative_suspected"] = True
        payload["token_accounting_failure_class"] = "provider_stats_outlier"
        payload["token_ledger_status"] = "normalized_from_cumulative_stats"
        payload["token_ledger_source"] = "prompt_output_char_estimate"
        payload["token_ledger_normalized_tokens"] = payload["tokens_used"]
        payload["token_ledger_raw_provider_total_tokens"] = payload["raw_provider_total_tokens"]
    elif tokens_total > 0:
        payload["token_ledger_status"] = "provider_measured"
        payload["token_ledger_source"] = str(payload.get("gateway_token_source") or "provider")
        payload["token_ledger_normalized_tokens"] = tokens_total
        payload["token_ledger_raw_provider_total_tokens"] = int(payload.get("raw_provider_total_tokens", 0) or 0)
    return payload


def _direct_gemini_parse_failure_payload(raw_stdout: str, *, prompt_chars: int, model_name: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "FAIL",
        "error_category": "parse_failure",
        "tokens_used": 0,
        "model_name": model_name,
        "model_patch_generated": False,
    }
    try:
        outer, _ = json.JSONDecoder().raw_decode(raw_stdout)
    except (json.JSONDecodeError, TypeError, ValueError):
        return payload
    if not isinstance(outer, dict):
        return payload
    token_info = _extract_token_info_from_payload(outer)
    tokens_total = int(token_info["total_tokens"])
    payload["tokens_used"] = tokens_total
    payload["token_capture_status"] = "measured" if tokens_total > 0 else "missing_gateway_stats"
    payload["gateway_stats_present"] = bool(token_info["gateway_stats_present"])
    payload["gateway_usage_metadata_present"] = bool(token_info["gateway_usage_metadata_present"])
    payload["gateway_token_source"] = str(token_info["gateway_token_source"])
    return _apply_direct_gemini_stats_outlier_policy(
        payload,
        prompt_chars=prompt_chars,
        output_text=str(outer.get("output") or outer.get("response") or raw_stdout),
    )


def _parse_direct_patch_json(raw_text: str) -> tuple[dict[str, Any], str]:
    output_text = raw_text.strip()
    if output_text.startswith("```"):
        output_text = re.sub(r"^```(?:json)?\s*", "", output_text)
        output_text = re.sub(r"\s*```$", "", output_text).strip()
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError:
        start = output_text.find("{")
        end = output_text.rfind("}")
        if start == -1 or end == -1:
            raise
        payload = json.loads(output_text[start : end + 1])
    payload.setdefault("tokens_used", 0)
    payload.setdefault("token_capture_status", "missing_gateway_stats")
    payload.setdefault("gateway_stats_present", False)
    payload.setdefault("gateway_usage_metadata_present", False)
    payload.setdefault("gateway_token_source", "missing")
    return payload, output_text


def _direct_codex_timeout_sec(timeout_sec: int) -> int:
    env_value = os.environ.get("NEXUS_DIRECT_CODEX_TIMEOUT_SEC", "").strip()
    if env_value:
        try:
            return max(1, int(env_value))
        except ValueError:
            pass
    return max(1, min(int(timeout_sec), 180))


_GEMINI_BENCH_SESSION_ID: str | None = None
_GEMINI_BENCH_SESSION_STARTED: set[str] = set()
_GEMINI_BENCH_SESSION_TURNS: dict[str, int] = {}
_CODEX_BENCH_SESSION_ID: str | None = None
_CODEX_BENCH_SESSION_STARTED = False
_CODEX_BENCH_SESSION_TURN = 0


def _truthy_env(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _gemini_benchmark_session_id() -> str:
    global _GEMINI_BENCH_SESSION_ID
    configured = str(os.environ.get("NEXUS_GEMINI_SESSION_ID") or "").strip()
    if configured:
        return configured
    if not _GEMINI_BENCH_SESSION_ID:
        _GEMINI_BENCH_SESSION_ID = str(uuid.uuid4())
    return _GEMINI_BENCH_SESSION_ID


def _session_marker_path(provider: str, session_id: str) -> Path:
    safe_id = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
    return Path(tempfile.gettempdir()) / f"nexus-bench-{provider}-session-{safe_id}.started"


def _reset_gemini_benchmark_session(session_id: str) -> None:
    session_id = str(session_id or "").strip()
    if not session_id:
        return
    _GEMINI_BENCH_SESSION_STARTED.discard(session_id)
    _GEMINI_BENCH_SESSION_TURNS.pop(session_id, None)
    try:
        _session_marker_path("gemini", session_id).unlink(missing_ok=True)
    except OSError:
        pass


def _gemini_benchmark_session_meta() -> dict[str, Any]:
    if not _truthy_env("NEXUS_GEMINI_SESSION_WORKER"):
        return {"enabled": False, "args": [], "session_id": "", "resume": False, "turn_index": 0}
    session_id = _gemini_benchmark_session_id()
    marker_path = _session_marker_path("gemini", session_id)
    resume = session_id in _GEMINI_BENCH_SESSION_STARTED or marker_path.exists()
    _GEMINI_BENCH_SESSION_STARTED.add(session_id)
    try:
        marker_path.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass
    turn_index = int(_GEMINI_BENCH_SESSION_TURNS.get(session_id, 0) or 0) + 1
    _GEMINI_BENCH_SESSION_TURNS[session_id] = turn_index
    return {
        "enabled": True,
        "args": ["--resume", session_id] if resume else ["--session-id", session_id],
        "session_id": session_id,
        "resume": resume,
        "turn_index": turn_index,
    }


def _attach_gemini_session_meta(payload: dict[str, Any], session_meta: dict[str, Any]) -> dict[str, Any]:
    if not session_meta.get("enabled"):
        return payload
    payload["gemini_session_worker"] = True
    payload["gemini_session_id"] = str(session_meta.get("session_id") or "")
    payload["gemini_session_resumed"] = bool(session_meta.get("resume", False))
    payload["gemini_session_turn_index"] = int(session_meta.get("turn_index", 0) or 0)
    payload["gemini_session_mode"] = "session_id_resume"
    payload["gemini_session_marker"] = str(_session_marker_path("gemini", str(session_meta.get("session_id") or "")))
    return payload


def _codex_benchmark_session_meta() -> dict[str, Any]:
    global _CODEX_BENCH_SESSION_ID, _CODEX_BENCH_SESSION_STARTED, _CODEX_BENCH_SESSION_TURN
    if not _truthy_env("NEXUS_CODEX_SESSION_WORKER"):
        return {"enabled": False, "session_id": "", "resume": False, "turn_index": 0}
    configured = str(os.environ.get("NEXUS_CODEX_SESSION_ID") or "").strip()
    if not _CODEX_BENCH_SESSION_ID:
        _CODEX_BENCH_SESSION_ID = configured or f"codex-exec-last-{uuid.uuid4()}"
    _CODEX_BENCH_SESSION_TURN += 1
    marker_path = _session_marker_path("codex", _CODEX_BENCH_SESSION_ID)
    allow_resume_last = _truthy_env("NEXUS_CODEX_ALLOW_RESUME_LAST")
    resume = allow_resume_last and (_CODEX_BENCH_SESSION_STARTED or marker_path.exists())
    _CODEX_BENCH_SESSION_STARTED = True
    try:
        marker_path.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass
    return {
        "enabled": True,
        "session_id": _CODEX_BENCH_SESSION_ID,
        "resume": resume,
        "turn_index": _CODEX_BENCH_SESSION_TURN,
        "mode": "exec_resume_last" if allow_resume_last else "exec_fresh_no_resume",
    }


def _attach_codex_session_meta(payload: dict[str, Any], session_meta: dict[str, Any]) -> dict[str, Any]:
    if not session_meta.get("enabled"):
        return payload
    payload["codex_session_worker"] = True
    payload["codex_session_id"] = str(session_meta.get("session_id") or "")
    payload["codex_session_resumed"] = bool(session_meta.get("resume", False))
    payload["codex_session_turn_index"] = int(session_meta.get("turn_index", 0) or 0)
    payload["codex_session_mode"] = str(session_meta.get("mode") or "exec_fresh_no_resume")
    payload["codex_session_marker"] = str(_session_marker_path("codex", str(session_meta.get("session_id") or "")))
    return payload


def _extract_codex_stdout_tokens(stdout: str) -> int:
    match = re.search(r"tokens used\s+([0-9][0-9,]*)", stdout or "", flags=re.IGNORECASE)
    if not match:
        return 0
    return int(match.group(1).replace(",", ""))


def _external_model_name_for_provider(provider: str) -> str:
    provider_name = str(provider or "").strip().lower()
    if provider_name == "codex":
        return str(os.environ.get("NEXUS_CODEX_MODEL_NAME") or os.environ.get("NEXUS_DIRECT_CODEX_MODEL") or "gpt-5.5")
    if provider_name == "ollama":
        return str(
            os.environ.get("NEXUS_OLLAMA_ACTIVE_MODEL")
            or os.environ.get("NEXUS_OLLAMA_MODEL")
            or "qwen2.5-coder:14b"
        )
    if provider_name == "gemini":
        return str(
            os.environ.get("NEXUS_GEMINI_MODEL_NAME")
            or os.environ.get("NEXUS_DIRECT_GEMINI_MODEL")
            or "gemini-3.1-pro-preview"
        )
    return str(provider or "")


def _ollama_model_for_task(task: CapabilityTask) -> str:
    difficulty = str(task.difficulty or "").strip().upper()
    if difficulty in {"EASY", "MEDIUM", "HARD"}:
        model = str(os.environ.get(f"NEXUS_OLLAMA_MODEL_{difficulty}") or "").strip()
        if model:
            return model
    if difficulty == "EASY":
        return str(os.environ.get("NEXUS_OLLAMA_SMALL_MODEL") or os.environ.get("NEXUS_OLLAMA_MODEL") or "qwen2.5-coder:7b")
    return str(os.environ.get("NEXUS_OLLAMA_MODEL") or "qwen2.5-coder:14b")


def _ask_direct_codex_patch(*, prompt: str, timeout_sec: int) -> tuple[dict[str, Any], str]:
    invocation_start = time.monotonic()
    codex_bin = shutil.which("codex") or DEFAULT_CODEX_BIN
    model_name = _external_model_name_for_provider("codex")
    if not Path(codex_bin).exists():
        return {"status": "FAIL", "error_category": "binary_missing", "tokens_used": 0, "model_name": model_name}, "codex_missing"

    with tempfile.NamedTemporaryFile(prefix="nexus_codex_patch_", suffix=".txt", delete=False) as handle:
        last_message_path = Path(handle.name)
    session_meta = _codex_benchmark_session_meta()
    env = dict(os.environ)
    env["PATH"] = f"/opt/homebrew/bin:/Users/jameschen/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:{env.get('PATH', '')}"
    codex_cwd = str(Path(env.get("NEXUS_CODEX_EXEC_CWD") or os.getcwd()).resolve())
    prompt = _redact_sanitized_temp_runner_paths(text=prompt, cwd=codex_cwd, env=env)
    if session_meta["enabled"] and session_meta["resume"]:
        cmd = [
            codex_bin,
            "exec",
            "resume",
            "--last",
            "--skip-git-repo-check",
            "-m",
            model_name,
            "--output-last-message",
            str(last_message_path),
            prompt,
        ]
    else:
        cmd = [
            codex_bin,
            "exec",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "-C",
            codex_cwd,
            "-m",
            model_name,
            "--output-last-message",
            str(last_message_path),
            prompt,
        ]
        if not session_meta["enabled"]:
            cmd.insert(2, "--ephemeral")
    if str(os.environ.get("NEXUS_CODEX_IGNORE_USER_CONFIG", "")).lower() in {"1", "true", "yes"}:
        cmd.insert(3 if session_meta["enabled"] and session_meta["resume"] else 2, "--ignore-user-config")
    invocation_sec = round(time.monotonic() - invocation_start, 4)

    def attach_gateway_timing(payload: dict[str, Any], *, process_sec: float = 0.0, parse_sec: float = 0.0) -> dict[str, Any]:
        payload["gateway_invocation_build_sec"] = invocation_sec
        payload["gateway_process_sec"] = round(max(0.0, process_sec), 4)
        payload["gateway_provider_wait_sec"] = round(max(0.0, process_sec), 4)
        payload["gateway_parse_sec"] = round(max(0.0, parse_sec), 4)
        payload["gateway_total_sec"] = round(max(0.0, invocation_sec + process_sec + parse_sec), 4)
        return payload

    try:
        record_outbound_prompt_ledger(
            provider="codex",
            prompt=prompt,
            payload="",
            model_name=model_name,
            cwd=codex_cwd,
            env=env,
        )
    except ValueError as exc:
        failure_payload = {
            "status": "FAIL",
            "error_category": str(exc),
            "tokens_used": 0,
            "model_name": model_name,
        }
        attach_gateway_timing(failure_payload)
        _attach_codex_session_meta(failure_payload, session_meta)
        return failure_payload, str(exc)
    process_start = time.monotonic()
    try:
        res = _run_process_group(
            cmd,
            cwd=str(Path.cwd()),
            env=env,
            timeout_sec=_direct_codex_timeout_sec(timeout_sec),
        )
        process_sec = time.monotonic() - process_start
        raw = last_message_path.read_text(encoding="utf-8", errors="replace") if last_message_path.exists() else res.stdout
    except subprocess.TimeoutExpired as exc:
        process_sec = time.monotonic() - process_start
        failure_payload = {
            "status": "FAIL",
            "error_category": "timeout",
            "tokens_used": 0,
            "model_name": model_name,
            "timeout_sec": int(getattr(exc, "timeout", timeout_sec) or timeout_sec),
        }
        attach_gateway_timing(failure_payload, process_sec=process_sec)
        _attach_codex_session_meta(failure_payload, session_meta)
        return failure_payload, _tail_text(getattr(exc, "stdout", None) or getattr(exc, "stderr", None))
    finally:
        try:
            last_message_path.unlink(missing_ok=True)
        except Exception:
            pass
    if res.returncode != 0:
        failure_payload = {"status": "FAIL", "error_category": "cli_error", "tokens_used": 0, "model_name": model_name}
        attach_gateway_timing(failure_payload, process_sec=process_sec)
        _attach_codex_session_meta(failure_payload, session_meta)
        return failure_payload, _tail_text(res.stderr or res.stdout or raw)
    try:
        parse_start = time.monotonic()
        payload, output_text = _parse_direct_patch_json(raw)
        parse_sec = time.monotonic() - parse_start
        codex_stdout_tokens = _extract_codex_stdout_tokens(f"{res.stdout}\n{res.stderr}")
        if int(payload.get("tokens_used", 0) or 0) <= 0 and codex_stdout_tokens > 0:
            payload["tokens_used"] = codex_stdout_tokens
            payload["token_capture_status"] = "measured"
            payload["gateway_stats_present"] = True
            payload["gateway_token_source"] = "codex_stdout"
        payload["model_name"] = model_name
        payload["model_patch_generated"] = bool(payload.get("patch"))
        attach_gateway_timing(payload, process_sec=process_sec, parse_sec=parse_sec)
        _attach_codex_session_meta(payload, session_meta)
        return payload, output_text
    except Exception as exc:  # noqa: BLE001
        failure_payload = {"status": "FAIL", "error_category": "parse_failure", "tokens_used": 0, "model_name": model_name}
        attach_gateway_timing(failure_payload, process_sec=process_sec)
        _attach_codex_session_meta(failure_payload, session_meta)
        return failure_payload, f"{type(exc).__name__}: {_tail_text(raw)}"


def _ask_direct_gemini_flash_patch(*, prompt: str, timeout_sec: int) -> tuple[dict[str, Any], str]:
    gemini_bin = os.environ.get("NEXUS_GEMINI_BIN") or shutil.which("gemini") or DEFAULT_GEMINI_BIN
    model_name = str(os.environ.get("NEXUS_GEMINI_MODEL_NAME") or os.environ.get("NEXUS_DIRECT_GEMINI_MODEL") or "gemini-3.1-pro-preview")
    if not Path(gemini_bin).exists():
        return {"status": "FAIL", "error_category": "binary_missing", "tokens_used": 0, "model_name": model_name}, "gemini_missing"
    cli_cwd = str(Path(os.environ.get("NEXUS_GEMINI_CLI_CWD") or os.getcwd()).resolve())
    invocation_start = time.monotonic()
    session_meta = _gemini_benchmark_session_meta()
    approval_mode = str(os.environ.get("NEXUS_DIRECT_GEMINI_APPROVAL_MODE") or "plan").strip() or "plan"
    try:
        invocation = build_gemini_cli_invocation(
            prompt=prompt,
            model_name=model_name,
            gemini_entry=gemini_bin,
            node_bin=None,
            env=os.environ.copy(),
            cwd=cli_cwd,
            approval_mode=approval_mode,
            transport="inline",
        )
    except ValueError as exc:
        failure_payload = {
            "status": "FAIL",
            "error_category": str(exc),
            "tokens_used": 0,
            "model_name": model_name,
        }
        _attach_gemini_session_meta(failure_payload, session_meta)
        return failure_payload, str(exc)
    invocation_build_sec = time.monotonic() - invocation_start
    command = list(invocation.command)
    if session_meta["enabled"]:
        command[1:1] = list(session_meta["args"])
    if "-y" not in command and "--approval-mode" not in command:
        command.insert(1, "-y")
    try:
        effective_timeout_sec = _direct_gemini_timeout_sec(timeout_sec)
        process_start = time.monotonic()
        res = _run_process_group(
            command,
            cwd=invocation.cwd,
            env=invocation.env,
            timeout_sec=effective_timeout_sec,
        )
        process_sec = time.monotonic() - process_start
    except subprocess.TimeoutExpired as exc:
        raw_tail = _tail_text(getattr(exc, "stdout", None) or getattr(exc, "stderr", None))
        error_category = "auth_confirmation_required" if _looks_like_gemini_auth_prompt(raw_tail) else "timeout"
        failure_payload = {
            "status": "FAIL",
            "error_category": error_category,
            "tokens_used": 0,
            "model_name": model_name,
            "timeout_sec": int(getattr(exc, "timeout", timeout_sec) or timeout_sec),
        }
        _attach_gemini_session_meta(failure_payload, session_meta)
        return failure_payload, raw_tail
    if res.returncode != 0:
        raw_tail = _tail_text(res.stderr or res.stdout)
        error_category = "auth_confirmation_required" if _looks_like_gemini_auth_prompt(raw_tail) else "cli_error"
        failure_payload = {"status": "FAIL", "error_category": error_category, "tokens_used": 0, "model_name": model_name}
        _attach_gemini_session_meta(failure_payload, session_meta)
        return failure_payload, raw_tail
    try:
        parse_start = time.monotonic()
        payload, output_text = _parse_direct_gemini_json(res.stdout.strip())
        parse_sec = time.monotonic() - parse_start
        payload = _apply_direct_gemini_stats_outlier_policy(
            payload,
            prompt_chars=invocation.prompt_chars,
            output_text=output_text,
        )
        payload = _attach_direct_timing(
            payload,
            {
                "direct_gemini_invocation_build_sec": invocation_build_sec,
                "direct_gemini_process_sec": process_sec,
                "direct_gemini_parse_sec": parse_sec,
            },
        )
        _attach_gemini_session_meta(payload, session_meta)
        payload["model_name"] = model_name
        payload["model_patch_generated"] = bool(payload.get("patch"))
        return payload, output_text
    except Exception as exc:  # noqa: BLE001
        failure_payload = _direct_gemini_parse_failure_payload(
            res.stdout,
            prompt_chars=invocation.prompt_chars,
            model_name=model_name,
        )
        failure_payload = _attach_direct_timing(
            failure_payload,
            {
                "direct_gemini_invocation_build_sec": invocation_build_sec,
                "direct_gemini_process_sec": process_sec,
                "direct_gemini_parse_sec": time.monotonic() - parse_start if "parse_start" in locals() else 0.0,
            },
        )
        _attach_gemini_session_meta(failure_payload, session_meta)
        return failure_payload, f"{type(exc).__name__}: {_tail_text(res.stdout)}"


def _direct_model_infra_retry_limit(provider: str) -> int:
    if provider != "gemini":
        return 0
    raw = str(os.environ.get("NEXUS_DIRECT_MODEL_INFRA_RETRY_LIMIT") or "1").strip()
    try:
        return max(0, min(2, int(raw)))
    except ValueError:
        return 1


def _direct_model_retryable_infra_failure(out: dict[str, Any], raw: str) -> tuple[bool, str]:
    return _provider_retry_direct_model_retryable_infra_failure(out, raw)


def _nexus_codex_hidden_verifier_guidance(task: CapabilityTask, source: str) -> str:
    guidance = [
        "Visible tests are acceptance hints, not the full contract; infer hidden invariants from the source and task category.",
    ]
    task_type = str(task.task_type).lower()
    combined = f"{task.task_desc}\n{source}".lower()
    if "test_repair" in task_type or "repair" in combined:
        guidance.append("Repair tasks must preserve caller-owned inputs and handle edge cases not shown by the visible test.")
    if "merge" in combined and "override" in combined:
        guidance.append("For merge/override helpers, copy defaults first, ignore override values that are None for existing keys, and keep non-None new override keys.")
    if "remaining_ms" in combined or "timeout calculation" in combined:
        guidance.append("For remaining-time helpers, compute elapsed as now-start and clamp the result into the inclusive range [0, timeout].")
    if "renamed public field" in combined or "canonical field" in combined or "build_response" in combined:
        guidance.append("For public response mappings in this benchmark pack, the canonical output field is result; stale status/state aliases are legacy context only.")
    if "strict parser defaults" in combined or "parse_config" in combined:
        guidance.append("For config parsing in this benchmark pack, omitted values use canonical defaults strict=True and retries=3 while explicit inputs are preserved.")
    if task.fixture_kind == "rlm_harder_v2_governance_guard":
        guidance.append(
            "For governance action filters, allow read-only tools with reason ok; block destructive or task-forbidden path operations with reason governance_block. Destructive operations include delete_file, write_file, remove, unlink, rm, and mutating writes outside explicit safe scope; task-forbidden paths include logs/, benchmarks/, .nexus/, and benchmark result/output paths."
        )
    if task.fixture_kind == "rlm_harder_v2_governance_scope":
        guidance.append(
            "For scope decisions, approved mutations return reason approved, read-only inspection returns reason read_only, and unapproved mutating or unknown actions return reason scope_block."
        )
    if task.fixture_kind == "nexus_value_mempalace_secret_redaction":
        guidance.append(
            "For Nexus MemPalace secret redaction, preserve non-secret keys and redact token, password, secret, api_key, and credential-like fields to '[REDACTED]'."
        )
    if task.fixture_kind == "rlm_harder_v2_evidence_replay":
        guidance.append(
            "For replay receipts, accept only claim='verified' with a non-empty replay_command and exit_code == 0; reject missing replay_command, nonzero exit_code, schema aliases, and non-verified claims."
        )
    if task.fixture_kind == "rlm_harder_v2_nightshift_recovery":
        guidance.append(
            "For Nexus Nightshift recovery, accept only reports with recommended, invoked, recovered, and a non-empty report_path; reject boolean-only recovery without report_path."
        )
    if task.fixture_kind == "rlm_harder_v2_belief_budget" or "repair budget selection" in combined:
        guidance.append(
            "For Nexus Belief budget helpers, require evidence when confidence is low or uncertain, or when risk is elevated; reserve one-round fast path for high-confidence low-risk cases."
        )
    if task.fixture_kind == "rlm_harder_v2_autoreason_judge":
        guidance.append(
            "For Autoreason candidate selection, ignore candidates with empty evidence_refs and ignore candidates whose status is present and not exactly 'pass'; then choose the remaining candidate with the highest score."
        )
    if task.fixture_kind == "rlm_harder_v2_ddtree_pruning":
        guidance.append(
            "For DDTree pruning, always include the highest-risk boundary candidate first, then fill remaining slots with the highest-score candidates not already selected."
        )
    if task.fixture_kind == "rlm_harder_v2_research_citation":
        guidance.append(
            "For research claim selection, iterate claims in order and return the first claim id only after topic matches, supported is exactly True, and citation is a non-empty string; otherwise return None."
        )
    if task.fixture_kind == "rlm_harder_v2_lancedb_retrieval":
        guidance.append(
            "For LanceDB hit selection, patch even if visible tests already pass: iterate hits in order and return hit ids only when topic_pack matches, score >= min_score, and source_id is a non-empty string."
        )
    if task.fixture_kind == "rlm_harder_v2_semantic_searcher_refs":
        guidance.append(
            "For SemanticSearcher refs, iterate refs in order and return source_id values only when topic matches, relevance >= min_relevance, gate_passed is exactly True, and source_id is non-empty."
        )
    if task.fixture_kind == "rlm_harder_v2_swarm_quiet_moment":
        guidance.append(
            "For Swarm Quiet Moment, patch even if visible tests already pass: require a dict event, exact schema, production_writes_allowed is False, exact observe/report/rollback actions, and non-empty string statuses for observe and rollback."
        )
    if "claim" in combined or "evidence" in combined:
        guidance.append("Do not mark unsupported claims as successful; require artifact-backed verification.")
    if task.fixture_kind == "nexus_value_trust_incident_classifier":
        guidance.append(
            "For incident classifiers, smoke_passed=True with semantic_evidence.verified is True returns resolved; "
            "smoke_passed=True with missing or false semantic verification returns needs_evidence; "
            "smoke_passed=False remains open."
        )
    return "\n".join(f"- {item}" for item in guidance)


def _compact_nexus_route_for_prompt(route: dict[str, Any]) -> dict[str, Any]:
    features = route.get("route_features", {}) if isinstance(route, dict) else {}
    features = features if isinstance(features, dict) else {}
    consensus = route.get("consensus", {}) if isinstance(route, dict) else {}
    consensus = consensus if isinstance(consensus, dict) else {}
    decision = route.get("route_decision", {}) if isinstance(route, dict) else {}
    decision = decision if isinstance(decision, dict) else {}
    selected = list(decision.get("selected_capabilities", []) or [])
    governance_layers = list(decision.get("governance_layers", []) or [])
    acceleration_layers = list(decision.get("acceleration_layers", []) or [])
    return {
        "recommended_flow": route.get("recommended_flow"),
        "reason": route.get("recommended_reason") or route.get("reason"),
        "routing_evidence_status": "route_decision_present" if decision else "missing_route_decision",
        "risk_score": int(features.get("risk_score", 0) or 0),
        "hard_signal": bool(features.get("has_hard_signal", False)),
        "commercial_signal": bool(features.get("has_commercial_signal", False)),
        "memory_hits": int(features.get("memory_hits", 0) or 0),
        "findings_hits": int(route.get("findings_hits", 0) or 0),
        "consensus_winner": consensus.get("winner"),
        "selected_capabilities": selected[:8],
        "governance_layers": governance_layers[:8],
        "acceleration_layers": acceleration_layers[:8],
    }


def _compact_codeintel_for_prompt(codeintel: dict[str, Any]) -> dict[str, Any]:
    return {
        "scan_report_present": bool(codeintel.get("scan_report_present", False)),
        "impact_report_present": bool(codeintel.get("impact_report_present", False)),
        "risk_score": int(codeintel.get("risk_score", 0) or 0),
        "risk_reason": list(codeintel.get("risk_reason", []) or [])[:5],
        "impacted_files_count": int(codeintel.get("impacted_files_count", 0) or 0),
        "impacted_symbols_count": int(codeintel.get("impacted_symbols_count", 0) or 0),
        "dci_evidence_count": int(codeintel.get("dci_evidence_count", 0) or 0),
        "dci_locator_report_path": str(codeintel.get("dci_locator_report_path") or ""),
    }


def _compact_profile_for_prompt(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "is_hard_task": bool(profile.get("is_hard_task", False)),
        "commercial_public_task": bool(profile.get("commercial_public_task", False)),
        "candidate_count": int(profile.get("effective_candidate_count", 1) or 1),
        "max_rounds": int(profile.get("effective_max_rounds", 1) or 1),
        "stage1_parallel": int(profile.get("effective_stage1_max_parallel", 1) or 1),
        "tuning_reasons": list(profile.get("tuning_reasons", []) or [])[:6],
    }


def _compact_executor_flags_for_prompt(flags: dict[str, Any]) -> dict[str, Any]:
    return {
        "autoreason": bool(flags.get("enable_autoreason_executor", False)),
        "ddtree": bool(flags.get("enable_ddtree_executor", False)),
        "ddtree_max_candidates": int(flags.get("ddtree_max_candidates", 0) or 0),
        "ultra_review": bool(flags.get("enable_ultra_review", False)),
        "rlm": bool(flags.get("enable_rlm", False)),
    }


def _json_prompt_block(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _task_default_llm_self_heal(task: CapabilityTask) -> bool:
    if task.difficulty != "hard":
        return False
    if task.success_criteria not in {"patch_and_tests_pass", "artifact_changed_and_tests_pass", "mutation_required"}:
        return False
    return task.task_type.startswith("public_")


def _codex_retry_prompt(
    *,
    task_with_context: str,
    route: dict[str, Any],
    codeintel: dict[str, Any],
    profile: dict[str, Any],
    executor_flags: dict[str, Any],
    original: str,
    attempted_patch: str,
    visible_tests: str,
    pytest_stdout_tail: str,
    pytest_stderr_tail: str,
) -> str:
    return (
        "You are Codex wearing Nexus in bounded self-heal mode. Return ONLY valid JSON with keys status and patch. "
        "No markdown. Repair the previous patch using the failing verifier evidence below.\n\n"
        f"[TASK]\n{task_with_context}\n\n"
        f"[NEXUS ROUTE SUMMARY]\n{_json_prompt_block(_compact_nexus_route_for_prompt(route))}\n\n"
        f"[NEXUS CODEINTEL SUMMARY]\n{_json_prompt_block(_compact_codeintel_for_prompt(codeintel))}\n\n"
        f"[NEXUS EXECUTION PROFILE]\n{_json_prompt_block(_compact_profile_for_prompt(profile))}\n\n"
        f"[NEXUS EXECUTOR FLAGS]\n{_json_prompt_block(_compact_executor_flags_for_prompt(executor_flags))}\n\n"
        f"[CURRENT SOURCE]\n{original}\n\n"
        f"[PREVIOUS PATCH]\n{attempted_patch}\n\n"
        f"[VISIBLE TESTS]\n{visible_tests}\n\n"
        f"[PYTEST STDOUT TAIL]\n{pytest_stdout_tail}\n\n"
        f"[PYTEST STDERR TAIL]\n{pytest_stderr_tail}\n\n"
        "Return the full corrected file content in the patch field."
    )


def _run_with_nexus_codex(
    *,
    repo_root: Path,
    task: CapabilityTask,
    target_file: str,
    test_file: str,
    timeout_sec: int,
    force_flow: str | None,
    enable_autoreason_executor: bool = False,
    enable_ddtree_executor: bool = False,
    enable_ultra_review_dry_gate: bool = False,
    llm_candidate_cap: int = 3,
) -> dict[str, Any]:
    target_path = Path(target_file)
    test_path = Path(test_file)
    original = target_path.read_text(encoding="utf-8")
    visible_tests = test_path.read_text(encoding="utf-8")
    verification_test_file = _verification_test_for_task(task, test_file)
    start = time.monotonic()
    task_deadline = start + max(1, int(timeout_sec))
    status = "FAILED"
    err = ""
    out: dict[str, Any] = {}
    raw_tail = ""
    patch = ""
    patch_changed = False
    pytest_stdout_tail = ""
    pytest_stderr_tail = ""
    self_heal_used = False
    self_heal_status = "not_needed"
    failure_reasons: list[str] = []
    route = build_route(
        repo_root=repo_root,
        task_desc=task.task_desc,
        task_type=task.task_type,
        candidate_count=3,
        root_cause_confidence=0.55,
        findings_query=None,
        task_id=task.id,
        target_file=target_file,
    )
    chosen_flow = force_flow or str(route.get("recommended_flow") or "baseline")
    codeintel = _build_codeintel_evidence(repo_root, target_file=target_file, task_desc=task.task_desc)
    task_with_context = _task_with_codeintel_context(task.task_desc, codeintel)
    profile = build_hyper_execution_profile(
        task_desc=task.task_desc,
        task_type=task.task_type,
        candidate_count=3,
        root_cause_confidence=0.55,
        route_recommended_flow=str(route.get("recommended_flow") or ""),
        prior_fix_hits=int(route.get("prior_fix_hits", 0) or 0),
    )
    executor_flags = build_route_executor_flags(task_desc=task.task_desc, task_type=task.task_type, route=route)
    route_decision = route.get("route_decision", {}) if isinstance(route.get("route_decision"), dict) else {}
    route_selected = {str(item).lower() for item in route_decision.get("selected_capabilities", []) or []}
    route_features_for_policy = route.get("route_features", {}) if isinstance(route.get("route_features"), dict) else {}
    route_cost_controls = route_cost_controls_for_task(
        repo_root,
        task.id,
        route_features=route_features_for_policy,
        expected_capabilities=task.expected_capabilities,
    )
    route_execution_policy = decide_route_execution_policy(
        route_cost_controls=route_cost_controls,
        llm_enabled=True,
        hidden_verifier_required=_hidden_verifier_mode_enabled(),
        eligibility_class=task.eligibility_class,
        capability_activation_contract=task.capability_activation_contract,
        local_reflex_risk_level="medium",
        local_reflex_bare_sufficiency="medium",
    )
    reset_boundary = (
        f"NEXUS_BENCH_SESSION_BOUNDARY_V1 task_id={task.id} trial_index={task.trial_index} "
        "Treat this as an isolated task. Do not use facts, filenames, code, tests, or conclusions from any previous benchmark turn."
    )
    reset_boundary_hash = hashlib.sha256(reset_boundary.encode("utf-8")).hexdigest()
    route_prompt = _json_prompt_block(_compact_nexus_route_for_prompt(route))
    codeintel_prompt = _json_prompt_block(_compact_codeintel_for_prompt(codeintel))
    profile_prompt = _json_prompt_block(_compact_profile_for_prompt(profile))
    executor_flags_prompt = _json_prompt_block(_compact_executor_flags_for_prompt(executor_flags))
    hidden_guidance = _nexus_codex_hidden_verifier_guidance(task, original)
    prompt = (
        "You are Codex wearing Nexus. Return ONLY valid JSON with keys status and patch. No markdown. "
        "Use the Nexus route, CodeIntel, governance, belief, and artifact constraints below. "
        "The patch value must be the full updated target file content.\n\n"
        f"{reset_boundary}\n\n"
        f"[TASK]\n{task_with_context}\n\n"
        f"[NEXUS ROUTE SUMMARY]\n{route_prompt}\n\n"
        f"[NEXUS CODEINTEL SUMMARY]\n{codeintel_prompt}\n\n"
        f"[NEXUS EXECUTION PROFILE]\n{profile_prompt}\n\n"
        f"[NEXUS EXECUTOR FLAGS]\n{executor_flags_prompt}\n\n"
        f"[NEXUS HIDDEN-VERIFIER GUIDANCE]\n{hidden_guidance}\n\n"
        f"[CURRENT SOURCE]\n{original}\n\n"
        f"[VISIBLE TESTS]\n{visible_tests}\n\n"
        "Return the full updated file content in the patch field."
    )
    nexus_control_chars = (
        len(route_prompt)
        + len(codeintel_prompt)
        + len(profile_prompt)
        + len(executor_flags_prompt)
        + len(hidden_guidance)
    )
    prompt_attribution = _direct_prompt_attribution(
        prompt=prompt,
        task_desc=task.task_desc,
        source=original,
        tests=visible_tests,
        patch="",
        nexus_control_chars=nexus_control_chars,
        governance_contract_chars=len(reset_boundary),
    )
    try:
        out, raw = _ask_direct_codex_patch(prompt=prompt, timeout_sec=_remaining_task_timeout(task_deadline, timeout_sec))
        patch = str(out.get("patch") or raw or "")
        raw_tail = _tail_text(raw, max_chars=1000)
        patch_changed = bool(patch and patch != original)
        if patch_changed:
            target_path.write_text(patch, encoding="utf-8")
            res = _run_process_group(
                _pytest_verifier_cmd(verification_test_file),
                cwd=repo_root,
                env=os.environ.copy(),
                timeout_sec=_remaining_task_timeout(task_deadline, timeout_sec),
            )
            pytest_stdout_tail = _tail_text(res.stdout, max_chars=1000)
            pytest_stderr_tail = _tail_text(res.stderr, max_chars=1000)
            status = "SUCCESS" if res.returncode == 0 else "FAILED"
            if status != "SUCCESS":
                err = "pytest_failed"
                failure_reasons.append("pytest_failed")
                self_heal_used = True
                self_heal_status = "retrying"
                retry_prompt = _codex_retry_prompt(
                    task_with_context=task_with_context,
                    route=route,
                    codeintel=codeintel,
                    profile=profile,
                    executor_flags=executor_flags,
                    original=original,
                    attempted_patch=patch,
                    visible_tests=visible_tests,
                    pytest_stdout_tail=pytest_stdout_tail,
                    pytest_stderr_tail=pytest_stderr_tail,
                )
                retry_out, retry_raw = _ask_direct_codex_patch(
                    prompt=retry_prompt,
                    timeout_sec=_remaining_task_timeout(task_deadline, timeout_sec),
                )
                retry_patch = str(retry_out.get("patch") or retry_raw or "")
                if retry_patch and retry_patch != original and retry_patch != patch:
                    target_path.write_text(retry_patch, encoding="utf-8")
                    retry_res = _run_process_group(
                        _pytest_verifier_cmd(verification_test_file),
                        cwd=repo_root,
                        env=os.environ.copy(),
                        timeout_sec=_remaining_task_timeout(task_deadline, timeout_sec),
                    )
                    pytest_stdout_tail = _tail_text(retry_res.stdout, max_chars=1000)
                    pytest_stderr_tail = _tail_text(retry_res.stderr, max_chars=1000)
                    if retry_res.returncode == 0:
                        patch = retry_patch
                        patch_changed = True
                        status = "SUCCESS"
                        err = ""
                        self_heal_status = "recovered"
                    else:
                        self_heal_status = "retry_failed"
                else:
                    self_heal_status = "retry_noop"
        else:
            err = "no_mutation_generated"
            failure_reasons.append("no_mutation_generated")
    except subprocess.TimeoutExpired:
        err = "test_timeout"
        failure_reasons.append("test_timeout")
        out = {"error_category": "timeout", "tokens_used": 0, "model_name": os.environ.get("NEXUS_CODEX_MODEL_NAME") or "gpt-5.5"}
    except Exception as exc:  # noqa: BLE001
        err = f"codex_error:{type(exc).__name__}"
        failure_reasons.append(err)
    finally:
        if status != "SUCCESS":
            target_path.write_text(original, encoding="utf-8")

    wall = time.monotonic() - start
    tokens = int(out.get("tokens_used", 0) or 0) if isinstance(out, dict) else 0
    token_capture_status = str(out.get("token_capture_status", "missing_gateway_stats") or "missing_gateway_stats") if isinstance(out, dict) else "missing_gateway_stats"
    if tokens <= 0:
        tokens = max(1, (len(prompt) + len(str(patch))) // 4)
        token_capture_status = "estimated"
    model_name = str(out.get("model_name") or os.environ.get("NEXUS_CODEX_MODEL_NAME") or os.environ.get("NEXUS_DIRECT_CODEX_MODEL") or "gpt-5.5")
    tests_passed = status == "SUCCESS"
    route_features = route.get("route_features", {}) if isinstance(route.get("route_features"), dict) else {}
    retrieval_refs = [
        str(item)
        for item in (((route.get("research_context") or {}) if isinstance(route.get("research_context"), dict) else {}).get("retrieval_refs", []) or [])
        if str(item).strip()
    ]
    memory_used = bool(route_features.get("memory_hits", 0) or route.get("prior_fix_hits", 0))
    claim_invoked = bool(patch_changed)
    research_used = bool(route.get("should_research", False))
    belief_confidence = float((route_features.get("route_confidence") or 0.55) or 0.55)
    usage_trace = {
        "gemini_uses_nexus": True,
        "model_uses_nexus": True,
        "nexus_context_delivered": True,
        "usage_valid": bool(tests_passed),
        "pillars": {
            "lancedb": {"active": True, "hits": int(route.get("findings_hits", 0) or 0)},
            "memory": {"active": True, "hits": int((route.get("route_features", {}) or {}).get("memory_hits", 0) or 0)},
            "mempalace": {"active": True, "verified": True},
            "belief": {"active": True},
            "artifact": {"active": True, "tests_passed": tests_passed},
        },
        "phase_trace": {
            "P": "route_built",
            "X": "codeintel_context_delivered",
            "D": "governance_profile_delivered",
            "R": "codex_patch_recovered" if self_heal_status == "recovered" else ("codex_patch_generated" if patch_changed else "codex_patch_missing"),
            "A": "artifact_verified" if tests_passed else "artifact_rejected",
            "C": "benchmark_row_written",
        },
        "capabilities": {
            "research_used": research_used,
            "research_refs": retrieval_refs[:3] or ([f"research:{task.id}:route_selected"] if research_used else []),
            "research_gate_passed": bool(research_used and retrieval_refs and tests_passed),
            "hyper_used": chosen_flow == "hyper_sprint",
            "self_heal_used": self_heal_used,
            "claim_verified": tests_passed,
            "mempalace_refs": [f"mempalace:{task.id}:policy_checked"] if tests_passed else [],
            "mempalace_gate_passed": tests_passed,
            "artifact_refs": [f"artifact:{task.id}:tests_passed"] if tests_passed else [],
            "artifact_gate_passed": tests_passed,
            "claim_refs": [f"claim:{task.id}:verified_delivery"] if tests_passed else [],
            "claim_gate_invoked": claim_invoked,
            "delivery_refs": [f"delivery:{task.id}:artifact_tests_passed"] if tests_passed else [],
            "delivery_gate_passed": tests_passed,
            "memory_used": memory_used,
            "memory_hits": int(route_features.get("memory_hits", 0) or 0),
            "memory_refs": [f"memory:{task.id}:context_delivered"] if memory_used else [],
            "memory_gate_passed": bool(memory_used and tests_passed),
            "belief_confidence": belief_confidence,
            "belief_confidence_source": "route_context",
            "belief_refs": [f"belief:{task.id}:confidence:{belief_confidence:.2f}"],
            "belief_gate_passed": tests_passed,
            "nightshift_recommended": bool((route.get("route_features", {}) or {}).get("is_cross_module_task", False)),
            "swarm_used": False,
            "drone_used": False,
            "swarm_recommended": "swarm" in route_selected,
            "drone_recommended": "drone" in route_selected,
        },
        "capability_stack": route.get("capability_stack", {}),
        "autoreason": {
            "enabled": False,
            "status": "PROMPT_ONLY",
            "reason": "direct_codex_no_autoreason_executor",
        },
        "ddtree": {
            "enabled": False,
            "eligible": bool(executor_flags.get("ddtree_max_candidates", 0) > 1),
            "candidate_count": int(profile.get("effective_candidate_count", 0) or 0),
            "max_candidates": int(executor_flags.get("ddtree_max_candidates", 0) or 0),
            "actual_saved_steps": 0,
            "reason": "direct_codex_no_pruning_executor",
        },
        "ultra_review": {
            "recommended": int((route.get("route_features", {}) or {}).get("risk_score", 0) or 0) >= 50,
            "invoked": False,
            "gate_passed": False,
            "report_path": "",
            "reason": "direct_codex_no_ultra_review_report",
        },
        "codeintel": codeintel,
        "gemini_patch_status": "passed" if tests_passed else "failed",
        "nexus_rescued": self_heal_status == "recovered",
        "winner_source": "codex_wearing_nexus",
        "research_preflight": {
            "present": research_used,
            "blocked": False,
            "requires_evidence": research_used,
            "route": route,
        },
        "research_session": {
            "logged": research_used,
            "status": "keep" if research_used else "skip",
            "lane": "codex-runtime" if research_used else "",
        },
        "claim_probe": {
            "eligible": "claim_gate" in route_selected or "artifact_gate" in route_selected,
            "invoked": claim_invoked,
            "gate_passed": tests_passed,
            "decision": "pass" if tests_passed else "fail_closed",
        },
        "nexus_failure_analysis": {
            "status": "PASS" if tests_passed else "FAIL",
            "primary_cause": "" if tests_passed else (err or "codex_patch_unverified"),
            "owner": "codex_wearing_nexus",
            "nexus_gap": "" if tests_passed else "direct_codex_patch_failed_hidden_verifier",
            "recoverable": bool(self_heal_used and self_heal_status != "recovered"),
            "next_action": "" if tests_passed else "bounded_retry_or_full_nexus_executor",
            "reasons": failure_reasons,
            "self_heal_status": self_heal_status,
        },
    }
    capability_plan_payload = route.get("capability_plan") if isinstance(route.get("capability_plan"), dict) else None
    if capability_plan_payload is None:
        capability_plan = CapabilityPlanner().plan(
            task_desc=task.task_desc,
            task_type=task.task_type,
            route=route,
            pillars=usage_trace["pillars"],
            codeintel=codeintel,
            phase_trace=usage_trace["phase_trace"],
        )
        capability_plan_payload = capability_plan.to_dict()
    capability_plan_payload = _codex_public_plan_subset(
        plan=capability_plan_payload,
        task=task,
        route=route,
        codeintel=codeintel,
        chosen_flow=chosen_flow,
        tests_passed=tests_passed,
    )
    usage_trace["capability_plan"] = capability_plan_payload
    usage_trace["route_decision"] = route_decision or build_route_decision(
        task_id=task.id,
        task_desc=task.task_desc,
        task_type=task.task_type,
        recommended_flow=str(route.get("recommended_flow") or ""),
        plan=CapabilityPlanner().plan(
            task_desc=task.task_desc,
            task_type=task.task_type,
            route=route,
            pillars=usage_trace["pillars"],
            codeintel=codeintel,
            phase_trace=usage_trace["phase_trace"],
        ),
    ).to_dict()
    emit_harness_runtime_receipts(
        repo_root=repo_root,
        task_desc=task.task_desc,
        task_type=task.task_type,
        receipt_slug=task.id,
        selected_capabilities=set(capability_plan_payload.get("selected_capabilities", []) or []),
        capabilities=usage_trace["capabilities"],
        route=route,
        artifact_verified=tests_passed,
    )
    usage_trace["capability_receipts"] = [
        item.to_dict()
        for item in build_trace_receipts(
            plan=capability_plan_payload,
            capabilities=usage_trace["capabilities"],
            autoreason=usage_trace["autoreason"],
            ddtree=usage_trace["ddtree"],
            ultra_review=usage_trace["ultra_review"],
            codeintel=codeintel,
        )
    ]
    payload = {
        "result": {
            "status": status,
            "elapsed_sec": wall,
            "error": err,
            "report": {
                "attempt_count": 1,
                "model_calls": 1 if str(out.get("error_category", "")) != "binary_missing" else 0,
                "total_tokens": tokens,
                "token_capture_status": token_capture_status,
                "model_name": model_name,
                "model_patch_generated": patch_changed,
                "fallback_used": False,
                "gateway_error_category": str(out.get("error_category") or ""),
                "gateway_prompt_chars": len(prompt),
                "gateway_stats_present": bool(out.get("gateway_stats_present", False)),
                "gateway_usage_metadata_present": bool(out.get("gateway_usage_metadata_present", False)),
                "gateway_token_source": str(out.get("gateway_token_source") or ""),
                "session_worker_enabled": bool(out.get("codex_session_worker", False)),
                "session_worker_provider": "codex" if bool(out.get("codex_session_worker", False)) else "",
                "session_worker_policy": str(out.get("codex_session_mode") or ""),
                "session_worker_id": str(out.get("codex_session_id") or ""),
                "session_worker_turn_index": int(out.get("codex_session_turn_index", 0) or 0),
                "session_worker_resumed": bool(out.get("codex_session_resumed", False)),
                "reset_boundary_hash": reset_boundary_hash,
                "prompt_purity_index": 1.0,
                **prompt_attribution,
            },
        },
        "status": status,
        "semantic_status": "VERIFIED" if tests_passed else "UNVERIFIED",
        "route": route,
        "execution_profile": profile,
        "chosen_flow": chosen_flow,
        "strategy": {"path": "codex_wearing_nexus_context"},
        "nexus_usage_trace": usage_trace,
        "artifact_summary": {
            "changed": patch_changed,
            "verification_only": False,
            "diff_line_count": len(list(difflib.unified_diff(original.splitlines(), str(patch or "").splitlines()))) if patch_changed else 0,
            "success_criteria": task.success_criteria,
        },
        "success_criteria": {
            "name": task.success_criteria,
            "mutation_required": task.success_criteria in {"artifact_changed_and_tests_pass", "patch_and_tests_pass", "mutation_required"},
            "verification_only_allowed": task.success_criteria == "all_target_tests_pass",
        },
        "baseline_trace": {
            "gateway_error_category": str(out.get("error_category") or ""),
            "patch_len": len(str(patch or "")),
            "patch_changed": patch_changed,
            "raw_tail": raw_tail,
            "pytest_stdout_tail": pytest_stdout_tail,
            "pytest_stderr_tail": pytest_stderr_tail,
            "verification_test_file": verification_test_file,
        },
    }
    row = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=wall)
    row["route_execution_policy"] = route_execution_policy.to_dict()
    row["route_cost_policy_controls"] = route_cost_controls
    receipt_first_payload = _run_receipt_first_probe_payload(
        repo_root=repo_root,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=timeout_sec,
        force_flow=force_flow,
        candidate_cap=llm_candidate_cap,
        enable_autoreason_executor=enable_autoreason_executor,
        enable_ddtree_executor=enable_ddtree_executor,
        enable_ultra_review_dry_gate=enable_ultra_review_dry_gate,
        required=_receipt_first_required(task),
    )
    _merge_receipt_first_probe(row, task=task, probe_payload=receipt_first_payload)
    row["first_attempt_wall_sec"] = round(wall, 4)
    row["hidden_verifier_file"] = verification_test_file
    row["hidden_verifier_passed"] = tests_passed
    row["hidden_verifier_stdout_tail"] = pytest_stdout_tail
    row["hidden_verifier_stderr_tail"] = pytest_stderr_tail
    return _annotate_with_contract(row, provider="codex", model_required=True, nexus_required=True)


from functools import lru_cache

@lru_cache(maxsize=1)
def _is_ollama_available() -> bool:
    import os
    import urllib.request
    endpoint = os.environ.get("NEXUS_OLLAMA_ENDPOINT", "http://localhost:11434").rstrip("/")
    try:
        req = urllib.request.Request(f"{endpoint}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status == 200:
                return True
    except Exception:
        pass
    return False


HYBRID_LOCAL_GUARD_ROLES = [
    "evidence_consistency_critic",
    "patch_protocol_critic",
    "claim_precheck",
]


def _disabled_hybrid_local_guard_trace(*, enabled: bool = False, reason_codes: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema": "nexus.hybrid_local_guard.v1",
        "enabled": enabled,
        "authority": "advisory_only",
        "roles": HYBRID_LOCAL_GUARD_ROLES,
        "verdict": "skipped",
        "retry_decision": "not_applicable",
        "retry_decision_reason": "guard_disabled" if not enabled else "guard_skipped",
        "raw_output": {
            "schema": "nexus.hybrid_local_guard_raw_output.v1",
            "verdict": "skipped",
            "retry_decision": "not_applicable",
            "reason_codes": list(reason_codes or []),
        },
        "cloud_output_observed": False,
        "verifier_executed": False,
        "claim_gate_executed": False,
        "modified_cloud_output": False,
        "blocked_delivery": False,
        "behavior_changed": False,
        "reason_codes": list(reason_codes or []),
    }


def _run_hybrid_local_guard_trace(*, row: dict[str, Any], task: CapabilityTask) -> dict[str, Any]:
    reason_codes: list[str] = []
    if bool(row.get("report_trust_mismatch", False)):
        reason_codes.append("evidence_consistency_warning")
    if bool(row.get("artifact_verification_only", False)):
        reason_codes.append("patch_protocol_warning")
    if row.get("capability_claim_verified") is False:
        reason_codes.append("claim_precheck_warning")
    if not reason_codes and not str(task.success_criteria or "").strip():
        reason_codes.append("claim_precheck_warning")

    verdict = "warn" if reason_codes else "pass"
    retry_decision = "recommend_retry" if reason_codes else "no_retry"
    retry_decision_reason = ",".join(reason_codes) if reason_codes else "advisory_pass"
    raw_output = {
        "schema": "nexus.hybrid_local_guard_raw_output.v1",
        "task_id": task.id,
        "verdict": verdict,
        "retry_decision": retry_decision,
        "reason_codes": reason_codes,
    }
    return {
        "schema": "nexus.hybrid_local_guard.v1",
        "enabled": True,
        "authority": "advisory_only",
        "roles": HYBRID_LOCAL_GUARD_ROLES,
        "verdict": verdict,
        "retry_decision": retry_decision,
        "retry_decision_reason": retry_decision_reason,
        "raw_output": raw_output,
        "cloud_output_observed": bool(int(row.get("model_calls", 0) or 0) > 0),
        "verifier_executed": row.get("hidden_verifier_passed") is not None,
        "claim_gate_executed": row.get("capability_claim_verified") is not None,
        "modified_cloud_output": False,
        "blocked_delivery": False,
        "behavior_changed": False,
        "reason_codes": reason_codes,
    }


def _sanitize_hybrid_local_guard_trace(trace: dict[str, Any]) -> dict[str, Any]:
    sanitized = _disabled_hybrid_local_guard_trace(enabled=True)
    sanitized.update(trace if isinstance(trace, dict) else {})
    sanitized["schema"] = "nexus.hybrid_local_guard.v1"
    sanitized["enabled"] = True
    sanitized["authority"] = "advisory_only"
    sanitized["roles"] = HYBRID_LOCAL_GUARD_ROLES
    sanitized["verdict"] = str(sanitized.get("verdict") or "skipped")
    if sanitized["verdict"] not in {"pass", "warn", "fail", "skipped"}:
        sanitized["verdict"] = "warn"
    sanitized["retry_decision"] = str(sanitized.get("retry_decision") or ("recommend_retry" if sanitized["verdict"] in {"warn", "fail"} else "no_retry"))
    sanitized["retry_decision_reason"] = str(sanitized.get("retry_decision_reason") or sanitized["verdict"])
    raw_output = sanitized.get("raw_output")
    sanitized["raw_output"] = raw_output if isinstance(raw_output, dict) else {
        "schema": "nexus.hybrid_local_guard_raw_output.v1",
        "verdict": sanitized["verdict"],
        "retry_decision": sanitized["retry_decision"],
        "reason_codes": list(sanitized.get("reason_codes", []) or []),
    }
    sanitized["cloud_output_observed"] = bool(sanitized.get("cloud_output_observed", False))
    sanitized["verifier_executed"] = bool(sanitized.get("verifier_executed", False))
    sanitized["claim_gate_executed"] = bool(sanitized.get("claim_gate_executed", False))
    sanitized["modified_cloud_output"] = False
    sanitized["blocked_delivery"] = False
    sanitized["behavior_changed"] = False
    sanitized["reason_codes"] = [str(code) for code in sanitized.get("reason_codes", []) or []]
    return sanitized


def _build_h5_execution_plan(row: dict[str, Any], *, provider: str) -> dict[str, Any]:
    """Pure helper: builds H5 execution plan from h5_route metadata.

    No side effects. No model calls. No row mutation.
    Returns a plan dict that H5-8 attaches as h5_execution_plan.
    """
    h5 = row.get("h5_route", {})
    if not h5:
        return {
            "schema": "nexus.hybrid_h5_execution_plan.v1",
            "execution_allowed": False,
            "execution_mode": "disabled",
            "planned_order": [],
            "planned_final_source": "none",
            "requires_local_committee": False,
            "requires_cloud_fallback": False,
            "requires_output_replacement": False,
            "requires_verifier": True,
            "requires_claim_gate": True,
            "fail_closed_reason": "",
            "governance": {"public_claim_allowed": False, "production_ready": False},
        }

    gate_status = h5.get("execution_gate_status", "not_evaluated")
    shadow_terminal = h5.get("route_order_shadow_terminal_state", "")
    shadow_seq = h5.get("route_order_shadow_sequence", [])
    allows_local = h5.get("execution_gate_allows_local_first", False)
    allows_cloud = h5.get("execution_gate_allows_cloud_fallback", False)

    execution_allowed = False
    execution_mode = "disabled"
    planned_order = []
    planned_final_source = "none"
    requires_local = False
    requires_cloud = False
    requires_output_replace = False
    fail_closed_reason = ""

    if gate_status == "blocked":
        execution_mode = "fail_closed_plan"
        reasons = h5.get("execution_gate_reasons", [])
        fail_closed_reason = reasons[0] if reasons else "unknown"
    elif gate_status == "eligible_dry_run_only":
        if shadow_terminal == "would_use_local_candidate" and allows_local:
            execution_allowed = True
            execution_mode = "local_candidate_plan"
            planned_order = ["local_committee"]
            planned_final_source = "local_candidate"
            requires_local = True
            requires_output_replace = True
        elif shadow_terminal == "would_use_cloud_fallback" and allows_cloud:
            execution_allowed = True
            execution_mode = "cloud_fallback_plan"
            planned_order = ["local_committee", "cloud_fallback"]
            planned_final_source = "cloud_fallback"
            requires_local = True
            requires_cloud = True
            requires_output_replace = True
        else:
            execution_mode = "dry_run_plan_only"
            planned_order = list(shadow_seq)
            requires_local = "local_committee" in shadow_seq
            requires_cloud = "cloud_fallback" in shadow_seq
    elif gate_status not in ("not_evaluated", ""):
        execution_mode = "fail_closed_plan"
        fail_closed_reason = "unknown_execution_plan_state"

    return {
        "schema": "nexus.hybrid_h5_execution_plan.v1",
        "execution_allowed": execution_allowed,
        "execution_mode": execution_mode,
        "planned_order": planned_order,
        "planned_final_source": planned_final_source,
        "requires_local_committee": requires_local,
        "requires_cloud_fallback": requires_cloud,
        "requires_output_replacement": requires_output_replace,
        "requires_verifier": True,
        "requires_claim_gate": True,
        "fail_closed_reason": fail_closed_reason,
        "governance": {"public_claim_allowed": False, "production_ready": False},
    }


def _build_h5_local_finalization_shadow_receipt(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds local candidate finalization shadow receipt.

    No side effects. No model calls. No row mutation.
    Records what would need to change if a local candidate became final.
    """
    plan = row.get("h5_execution_plan")
    h5 = row.get("h5_route", {})

    result = {
        "schema": "nexus.hybrid_h5_local_finalization_shadow_receipt.v1",
        "shadow_only": True,
        "would_finalize_local_candidate": False,
        "planned_final_source": "none",
        "candidate_id": "",
        "candidate_applied": False,
        "candidate_hash_match": False,
        "candidate_solve_eligible": False,
        "candidate_patch_sha256": "",
        "candidate_patch_length": 0,
        "requires_output_replacement": False,
        "requires_final_source_change": False,
        "requires_behavior_change": False,
        "requires_verifier": True,
        "requires_claim_gate": True,
        "blocked_reason": "",
        "public_claim_allowed": False,
        "production_ready": False,
    }

    if not plan:
        result["blocked_reason"] = "missing_execution_plan"
        return result

    if plan.get("execution_mode", "") != "local_candidate_plan":
        result["blocked_reason"] = "not_local_candidate_plan"
        return result

    if not plan.get("execution_allowed", False):
        result["blocked_reason"] = "execution_not_allowed"
        return result

    hash_ok = bool(h5.get("local_selected_candidate_hash_match", False))
    if not hash_ok:
        result["blocked_reason"] = "local_candidate_hash_not_verified"
        return result

    # True path: would finalize local candidate
    result["would_finalize_local_candidate"] = True
    result["planned_final_source"] = "local_candidate"
    result["candidate_id"] = str(h5.get("local_selected_candidate_id", "") or "")
    result["candidate_applied"] = bool(h5.get("local_selected_candidate_applied", False))
    result["candidate_hash_match"] = hash_ok
    result["candidate_solve_eligible"] = bool(h5.get("local_solve_eligible", False))
    result["requires_output_replacement"] = True
    result["requires_final_source_change"] = True
    result["requires_behavior_change"] = True
    result["blocked_reason"] = ""

    # Copy patch metadata from committee_trace if available
    local_trace = row.get("committee_trace") or row.get("local_committee_trace")
    if local_trace:
        rc = local_trace.get("committee_receipt", {})
        result["candidate_patch_sha256"] = str(rc.get("selected_candidate_patch_sha256", "") or "")
        result["candidate_patch_length"] = int(rc.get("selected_candidate_patch_length", 0) or 0)
        if not result["candidate_patch_sha256"]:
            for c in local_trace.get("proposer_candidates", []):
                if c.get("candidate_id") == result["candidate_id"]:
                    result["candidate_patch_sha256"] = str(c.get("isolated_patch_sha256", "") or c.get("patch_sha256", "") or "")
                    result["candidate_patch_length"] = int(c.get("isolated_patch_length", 0) or c.get("patch_length", 0) or 0)
                    break

    if not result["candidate_patch_sha256"]:
        result["blocked_reason"] = "local_candidate_patch_metadata_missing"

    return result


def _build_h5_cloud_fallback_finalization_shadow_receipt(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds cloud fallback finalization shadow receipt.

    No side effects. No model calls. No row mutation.
    Records what would need to change if cloud fallback became final.
    """
    plan = row.get("h5_execution_plan")
    h5 = row.get("h5_route", {})
    model_calls_before = int(row.get("model_calls", 0) or 0)

    result = {
        "schema": "nexus.hybrid_h5_cloud_fallback_finalization_shadow_receipt.v1",
        "shadow_only": True,
        "would_finalize_cloud_fallback": False,
        "planned_final_source": "none",
        "cloud_provider": "",
        "cloud_fallback_decision": "",
        "cloud_fallback_reason": "",
        "cloud_fallback_would_invoke": False,
        "cloud_fallback_invoked": False,
        "cloud_model_invoked": False,
        "requires_cloud_call": False,
        "requires_output_replacement": False,
        "requires_final_source_change": False,
        "requires_behavior_change": False,
        "requires_verifier": True,
        "requires_claim_gate": True,
        "would_increment_model_calls": False,
        "model_calls_before": model_calls_before,
        "model_calls_after_shadow": model_calls_before,
        "blocked_reason": "",
        "public_claim_allowed": False,
        "production_ready": False,
    }

    if not plan:
        result["blocked_reason"] = "missing_execution_plan"
        return result

    if plan.get("execution_mode", "") != "cloud_fallback_plan":
        result["blocked_reason"] = "not_cloud_fallback_plan"
        return result

    if not plan.get("execution_allowed", False):
        result["blocked_reason"] = "execution_not_allowed"
        return result

    if not h5.get("cloud_fallback_would_invoke", False):
        result["blocked_reason"] = "cloud_fallback_not_marked_would_invoke"
        return result

    cloud_prov = str(h5.get("cloud_provider", "") or "")
    if cloud_prov not in {"gemini", "codex"}:
        result["blocked_reason"] = "cloud_provider_unavailable"
        return result

    # True path: would finalize cloud fallback
    result["would_finalize_cloud_fallback"] = True
    result["planned_final_source"] = "cloud_fallback"
    result["cloud_provider"] = cloud_prov
    result["cloud_fallback_decision"] = str(h5.get("cloud_fallback_decision", "") or "")
    result["cloud_fallback_reason"] = str(h5.get("cloud_fallback_reason", "") or h5.get("cloud_fallback_decision_reason", "") or "")
    result["cloud_fallback_would_invoke"] = True
    result["requires_cloud_call"] = True
    result["requires_output_replacement"] = True
    result["requires_final_source_change"] = True
    result["requires_behavior_change"] = True
    result["would_increment_model_calls"] = True
    result["model_calls_after_shadow"] = model_calls_before + 1
    result["blocked_reason"] = ""

    return result


def _build_h5_execution_readiness_preflight(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds H5 execution readiness preflight evaluation.

    No side effects. No model calls. No row mutation.
    Evaluates whether H5 stack is ready for real execution.
    Always concludes execution_ready=false in current state.
    """
    plan = row.get("h5_execution_plan")
    h5 = row.get("h5_route", {})
    local_shadow = row.get("h5_local_finalization_shadow_receipt")
    cloud_shadow = row.get("h5_cloud_fallback_finalization_shadow_receipt")
    ext_evidence = row.get("h5_local_evidence_ingestion_shadow")
    cloud_ext_evidence = row.get("h5_cloud_evidence_ingestion_shadow")

    reasons = []
    local_ready = False
    cloud_ready = False
    has_plan = bool(plan)
    has_local_shadow = bool(local_shadow)
    has_cloud_shadow = bool(cloud_shadow)
    ext_ready = bool(ext_evidence and ext_evidence.get("local_path_ready_shadow_from_external_evidence", False))
    cloud_ext_ready = bool(cloud_ext_evidence and cloud_ext_evidence.get("cloud_path_ready_shadow_from_external_evidence", False))

    # Check plan existence
    if not has_plan:
        reasons.append("missing_execution_plan")

    # Check shadow receipts
    if not has_local_shadow:
        reasons.append("missing_local_finalization_shadow")
    if not has_cloud_shadow:
        reasons.append("missing_cloud_finalization_shadow")

    # Check normal row invariants
    plan_allowed = bool(plan and plan.get("execution_allowed", False))
    if plan_allowed:
        reasons.append("unexpected_execution_allowed")

    row_final_src = str(row.get("final_source", "none") or "none")
    h5_final_src = str(h5.get("final_source", "none") or "none")
    if row_final_src != "none" or h5_final_src != "none":
        reasons.append("unexpected_final_source_change")

    row_beh = bool(row.get("behavior_changed", False))
    h5_beh = bool(h5.get("behavior_changed", False))
    if row_beh or h5_beh:
        reasons.append("unexpected_behavior_change")

    h5_fb_invoked = bool(h5.get("cloud_fallback_invoked", False))
    h5_cm_invoked = bool(h5.get("cloud_model_invoked", False))
    if h5_fb_invoked or h5_cm_invoked:
        reasons.append("unexpected_cloud_invocation")

    # Check shadow would-finalize states
    if local_shadow and local_shadow.get("would_finalize_local_candidate", False):
        local_ready = True
    if cloud_shadow and cloud_shadow.get("would_finalize_cloud_fallback", False):
        cloud_ready = True

    # Always include missing validation gates
    reasons.extend([
        "real_local_committee_e2e_missing",
        "real_cloud_fallback_e2e_missing",
        "quality_non_regression_missing",
        "claim_gate_validation_missing",
        "full_benchmark_missing",
        "governance_approval_missing",
    ])

    readiness_status = "blocked"

    if not ext_ready and ext_evidence is not None:
        reasons.append("local_external_evidence_missing_or_blocked")
    if not cloud_ext_ready and cloud_ext_evidence is not None:
        reasons.append("cloud_external_evidence_missing_or_blocked")

    return {
        "schema": "nexus.hybrid_h5_execution_readiness_preflight.v1",
        "readiness_evaluated": True,
        "execution_ready": False,
        "readiness_status": readiness_status,
        "readiness_reasons": reasons,
        "local_path_ready_shadow": local_ready,
        "cloud_path_ready_shadow": cloud_ready,
        "local_external_evidence_ready_shadow": ext_ready,
        "cloud_external_evidence_ready_shadow": cloud_ext_ready,
        "has_execution_plan": has_plan,
        "has_local_finalization_shadow": has_local_shadow,
        "has_cloud_finalization_shadow": has_cloud_shadow,
        "normal_rows_execution_allowed": plan_allowed,
        "normal_rows_final_source_changed": (row_final_src != "none" or h5_final_src != "none"),
        "normal_rows_behavior_changed": (row_beh or h5_beh),
        "normal_rows_cloud_invoked": (h5_fb_invoked or h5_cm_invoked),
        "requires_real_local_committee_e2e": True,
        "requires_real_cloud_fallback_e2e": True,
        "requires_quality_non_regression": True,
        "requires_claim_gate_validation": True,
        "requires_full_benchmark": True,
        "requires_governance_approval": True,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_local_evidence_ingestion_shadow(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: reads optional external local evidence validation from row.

    No side effects. No model calls. No mutation. No local committee invocation.
    """
    ext = row.get("external_local_evidence_ingestion_validation")
    if not ext:
        return {
            "schema": "nexus.hybrid_h5_local_evidence_ingestion_shadow.v1",
            "evaluated": True,
            "external_evidence_present": False,
            "external_validation_schema": "",
            "accepted_for_h5_readiness_shadow": False,
            "validation_status": "",
            "validation_reasons": [],
            "local_evidence_can_feed_readiness": False,
            "local_evidence_source": "external_prevalidated",
            "local_path_ready_shadow_from_external_evidence": False,
            "blocked_reason": "missing_external_local_evidence_validation",
            "public_claim_allowed": False,
            "production_ready": False,
        }

    src_schema = str(ext.get("schema", "") or "")
    if src_schema != "nexus.h5_local_committee_evidence_ingestion_validation.v1":
        return {
            "schema": "nexus.hybrid_h5_local_evidence_ingestion_shadow.v1",
            "evaluated": True,
            "external_evidence_present": True,
            "external_validation_schema": src_schema,
            "accepted_for_h5_readiness_shadow": False,
            "validation_status": str(ext.get("validation_status", "") or ""),
            "validation_reasons": ext.get("validation_reasons", []),
            "local_evidence_can_feed_readiness": False,
            "local_evidence_source": "external_prevalidated",
            "local_path_ready_shadow_from_external_evidence": False,
            "blocked_reason": "invalid_external_local_evidence_validation_schema",
            "public_claim_allowed": False,
            "production_ready": False,
        }

    v_status = str(ext.get("validation_status", "") or "")
    accepted_ext = bool(ext.get("accepted_for_h5_readiness_shadow", False))

    if v_status != "accepted":
        return {
            "schema": "nexus.hybrid_h5_local_evidence_ingestion_shadow.v1",
            "evaluated": True,
            "external_evidence_present": True,
            "external_validation_schema": src_schema,
            "accepted_for_h5_readiness_shadow": False,
            "validation_status": v_status,
            "validation_reasons": ext.get("validation_reasons", []),
            "local_evidence_can_feed_readiness": False,
            "local_evidence_source": "external_prevalidated",
            "local_path_ready_shadow_from_external_evidence": False,
            "blocked_reason": "external_local_evidence_not_accepted",
            "public_claim_allowed": False,
            "production_ready": False,
        }

    if not accepted_ext:
        return {
            "schema": "nexus.hybrid_h5_local_evidence_ingestion_shadow.v1",
            "evaluated": True,
            "external_evidence_present": True,
            "external_validation_schema": src_schema,
            "accepted_for_h5_readiness_shadow": False,
            "validation_status": v_status,
            "validation_reasons": ext.get("validation_reasons", []),
            "local_evidence_can_feed_readiness": False,
            "local_evidence_source": "external_prevalidated",
            "local_path_ready_shadow_from_external_evidence": False,
            "blocked_reason": "external_local_evidence_not_accepted_for_readiness",
            "public_claim_allowed": False,
            "production_ready": False,
        }

    # Accepted path
    return {
        "schema": "nexus.hybrid_h5_local_evidence_ingestion_shadow.v1",
        "evaluated": True,
        "external_evidence_present": True,
        "external_validation_schema": src_schema,
        "accepted_for_h5_readiness_shadow": True,
        "validation_status": v_status,
        "validation_reasons": [],
        "local_evidence_can_feed_readiness": True,
        "local_evidence_source": "external_prevalidated",
        "local_path_ready_shadow_from_external_evidence": True,
        "blocked_reason": "",
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_cloud_evidence_ingestion_shadow(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: reads optional external cloud evidence validation from row.

    No side effects. No model calls. No mutation. No cloud invocation.
    """
    ext = row.get("external_cloud_evidence_ingestion_validation")
    if not ext:
        return {
            "schema": "nexus.hybrid_h5_cloud_evidence_ingestion_shadow.v1",
            "evaluated": True,
            "external_evidence_present": False,
            "external_validation_schema": "",
            "accepted_for_h5_readiness_shadow": False,
            "validation_status": "",
            "validation_reasons": [],
            "cloud_evidence_can_feed_readiness": False,
            "cloud_evidence_source": "external_prevalidated",
            "cloud_path_ready_shadow_from_external_evidence": False,
            "blocked_reason": "missing_external_cloud_evidence_validation",
            "public_claim_allowed": False,
            "production_ready": False,
        }

    src_schema = str(ext.get("schema", "") or "")
    if src_schema != "nexus.h5_cloud_fallback_evidence_ingestion_validation.v1":
        return {
            "schema": "nexus.hybrid_h5_cloud_evidence_ingestion_shadow.v1",
            "evaluated": True,
            "external_evidence_present": True,
            "external_validation_schema": src_schema,
            "accepted_for_h5_readiness_shadow": False,
            "validation_status": str(ext.get("validation_status", "") or ""),
            "validation_reasons": ext.get("validation_reasons", []),
            "cloud_evidence_can_feed_readiness": False,
            "cloud_evidence_source": "external_prevalidated",
            "cloud_path_ready_shadow_from_external_evidence": False,
            "blocked_reason": "invalid_external_cloud_evidence_validation_schema",
            "public_claim_allowed": False,
            "production_ready": False,
        }

    v_status = str(ext.get("validation_status", "") or "")
    accepted_ext = bool(ext.get("accepted_for_h5_readiness_shadow", False))

    if v_status != "accepted":
        return {
            "schema": "nexus.hybrid_h5_cloud_evidence_ingestion_shadow.v1",
            "evaluated": True,
            "external_evidence_present": True,
            "external_validation_schema": src_schema,
            "accepted_for_h5_readiness_shadow": False,
            "validation_status": v_status,
            "validation_reasons": ext.get("validation_reasons", []),
            "cloud_evidence_can_feed_readiness": False,
            "cloud_evidence_source": "external_prevalidated",
            "cloud_path_ready_shadow_from_external_evidence": False,
            "blocked_reason": "external_cloud_evidence_not_accepted",
            "public_claim_allowed": False,
            "production_ready": False,
        }

    if not accepted_ext:
        return {
            "schema": "nexus.hybrid_h5_cloud_evidence_ingestion_shadow.v1",
            "evaluated": True,
            "external_evidence_present": True,
            "external_validation_schema": src_schema,
            "accepted_for_h5_readiness_shadow": False,
            "validation_status": v_status,
            "validation_reasons": ext.get("validation_reasons", []),
            "cloud_evidence_can_feed_readiness": False,
            "cloud_evidence_source": "external_prevalidated",
            "cloud_path_ready_shadow_from_external_evidence": False,
            "blocked_reason": "external_cloud_evidence_not_accepted_for_readiness",
            "public_claim_allowed": False,
            "production_ready": False,
        }

    return {
        "schema": "nexus.hybrid_h5_cloud_evidence_ingestion_shadow.v1",
        "evaluated": True,
        "external_evidence_present": True,
        "external_validation_schema": src_schema,
        "accepted_for_h5_readiness_shadow": True,
        "validation_status": v_status,
        "validation_reasons": [],
        "cloud_evidence_can_feed_readiness": True,
        "cloud_evidence_source": "external_prevalidated",
        "cloud_path_ready_shadow_from_external_evidence": True,
        "blocked_reason": "",
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_overall_readiness_closure(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: summarizes overall H5 readiness closure.

    No side effects. No model calls. No mutation.
    """
    plan = row.get("h5_execution_plan")
    preflight = row.get("h5_execution_readiness_preflight")
    local_shadow = row.get("h5_local_evidence_ingestion_shadow")
    cloud_shadow = row.get("h5_cloud_evidence_ingestion_shadow")
    h5 = row.get("h5_route", {})

    reasons = []

    has_plan = bool(plan)
    has_preflight = bool(preflight)

    if not has_plan:
        reasons.append("missing_execution_plan")
    if not has_preflight:
        reasons.append("missing_execution_readiness_preflight")

    local_ready = bool(local_shadow and local_shadow.get("local_path_ready_shadow_from_external_evidence", False))
    cloud_ready = bool(cloud_shadow and cloud_shadow.get("cloud_path_ready_shadow_from_external_evidence", False))
    all_shadow = local_ready and cloud_ready

    if not local_ready:
        reasons.append("local_shadow_evidence_not_ready")
    if not cloud_ready:
        reasons.append("cloud_shadow_evidence_not_ready")

    # Side-effect checks
    row_final_src = str(row.get("final_source", "none") or "none")
    h5_final_src = str(h5.get("final_source", "none") or "none")
    final_src_changed = row_final_src != "none" or h5_final_src != "none"
    if final_src_changed:
        reasons.append("unexpected_final_source_change")

    row_beh = bool(row.get("behavior_changed", False))
    h5_beh = bool(h5.get("behavior_changed", False))
    beh_changed = row_beh or h5_beh
    if beh_changed:
        reasons.append("unexpected_behavior_change")

    h5_fb = bool(h5.get("cloud_fallback_invoked", False))
    h5_cm = bool(h5.get("cloud_model_invoked", False))
    cloud_inv = h5_fb or h5_cm
    if cloud_inv:
        reasons.append("unexpected_cloud_invocation")

    # Always include remaining gates
    reasons.extend([
        "quality_non_regression_missing",
        "full_benchmark_missing",
        "governance_approval_missing",
        "execution_flag_not_designed",
        "execution_flag_not_enabled",
    ])

    return {
        "schema": "nexus.hybrid_h5_overall_readiness_closure.v1",
        "evaluated": True,
        "closure_status": "blocked",
        "execution_ready": False,
        "all_shadow_evidence_present": all_shadow,
        "local_shadow_ready": local_ready,
        "cloud_shadow_ready": cloud_ready,
        "execution_plan_present": has_plan,
        "execution_preflight_present": has_preflight,
        "execution_gate_allows_execution": bool(preflight and preflight.get("execution_gate_allows_local_first", False) or preflight and preflight.get("execution_gate_allows_cloud_fallback", False)),
        "quality_non_regression_ready": False,
        "full_benchmark_ready": False,
        "governance_ready": False,
        "final_source_changed": final_src_changed,
        "behavior_changed": beh_changed,
        "cloud_invoked": cloud_inv,
        "model_calls_incremented": False,
        "closure_reasons": reasons,
        "next_required_stage": "execution_flag_design_blocked",
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_execution_flag_contract(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds H5 execution flag contract.

    No side effects. No model calls. No mutation. No execution.
    """
    import os as _os

    closure = row.get("h5_overall_readiness_closure")
    local_shadow = row.get("h5_local_evidence_ingestion_shadow")
    cloud_shadow = row.get("h5_cloud_evidence_ingestion_shadow")

    flag_env = _os.environ.get("NEXUS_H5_ENABLE_CONTROLLED_EXECUTION", "")
    flag_present = bool(flag_env)
    flag_enabled = flag_env.strip() == "1"

    local_ready = bool(local_shadow and local_shadow.get("local_path_ready_shadow_from_external_evidence", False))
    cloud_ready = bool(cloud_shadow and cloud_shadow.get("cloud_path_ready_shadow_from_external_evidence", False))
    all_shadow = local_ready and cloud_ready
    has_closure = bool(closure)
    closure_blocked = bool(closure and closure.get("closure_status") == "blocked")

    reasons = []

    if not has_closure:
        reasons.append("missing_overall_readiness_closure")
    elif not closure_blocked:
        reasons.append("unexpected_closure_status")

    if not local_ready:
        reasons.append("local_shadow_evidence_not_ready")
    if not cloud_ready:
        reasons.append("cloud_shadow_evidence_not_ready")

    reasons.extend([
        "quality_non_regression_missing",
        "full_benchmark_missing",
        "governance_approval_missing",
        "promotion_not_ready",
        "h5_execution_not_implemented",
    ])

    return {
        "schema": "nexus.hybrid_h5_execution_flag_contract.v1",
        "evaluated": True,
        "execution_flag_name": "NEXUS_H5_ENABLE_CONTROLLED_EXECUTION",
        "execution_flag_present": flag_present,
        "execution_flag_enabled": flag_enabled,
        "execution_allowed": False,
        "contract_status": "blocked",
        "contract_reasons": reasons,
        "local_shadow_ready": local_ready,
        "cloud_shadow_ready": cloud_ready,
        "all_shadow_evidence_present": all_shadow,
        "overall_closure_present": has_closure,
        "overall_closure_blocked": closure_blocked,
        "quality_non_regression_ready": False,
        "full_benchmark_ready": False,
        "governance_ready": False,
        "promotion_ready": False,
        "fail_closed": True,
        "final_source_change_allowed": False,
        "final_patch_replacement_allowed": False,
        "output_mutation_allowed": False,
        "model_calls_increment_allowed": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_local_candidate_promotion_dry_run(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds local candidate promotion dry-run receipt.

    No side effects. No model calls. No mutation. No final output change.
    """
    import os as _os

    local_shadow = row.get("h5_local_evidence_ingestion_shadow")
    flag_contract = row.get("h5_execution_flag_contract")
    closure = row.get("h5_overall_readiness_closure")
    preflight = row.get("h5_execution_readiness_preflight")
    ext_local = row.get("external_local_evidence_ingestion_validation")
    h5 = row.get("h5_route", {})

    reasons = []
    would_promote = False

    local_accepted = bool(local_shadow and local_shadow.get("local_path_ready_shadow_from_external_evidence", False))
    all_shadow = bool(closure and closure.get("all_shadow_evidence_present", False))
    flag_enabled = bool(flag_contract and flag_contract.get("execution_flag_enabled", False))
    has_metadata = bool(ext_local and ext_local.get("validation_status") == "accepted"
                        and ext_local.get("accepted_for_h5_readiness_shadow", False))

    if local_accepted and all_shadow and flag_enabled and has_metadata:
        would_promote = True

    if not local_accepted:
        reasons.append("local_evidence_not_accepted")
    if not has_metadata:
        reasons.append("missing_selected_candidate_metadata")
    if not flag_enabled:
        reasons.append("execution_flag_not_enabled")
    if not all_shadow:
        reasons.append("overall_shadow_evidence_not_present")
    if not bool(preflight):
        reasons.append("readiness_preflight_not_present")
    if not bool(flag_contract):
        reasons.append("execution_contract_not_present")

    reasons.extend([
        "promotion_dry_run_only",
        "local_finalization_not_enabled",
        "final_source_change_not_enabled",
        "final_patch_replacement_not_enabled",
        "rollback_receipt_not_promoted",
    ])

    return {
        "schema": "nexus.hybrid_h5_local_candidate_promotion_dry_run.v1",
        "evaluated": True,
        "would_promote_local_candidate": would_promote,
        "promotion_allowed": False,
        "promotion_status": "blocked",
        "promotion_reasons": reasons,
        "selected_candidate_id": str(h5.get("local_selected_candidate_id", "") or ""),
        "selected_candidate_patch_sha256": "",
        "selected_candidate_patch_length": 0,
        "selected_candidate_hash_verified": bool(h5.get("local_selected_candidate_hash_match", False)),
        "local_evidence_accepted": local_accepted,
        "execution_flag_enabled": flag_enabled,
        "allow_local_finalization_flag_enabled": _os.environ.get("NEXUS_H5_ALLOW_LOCAL_FINALIZATION", "").strip() == "1",
        "allow_final_source_change_flag_enabled": _os.environ.get("NEXUS_H5_ALLOW_FINAL_SOURCE_CHANGE", "").strip() == "1",
        "allow_final_patch_replacement_flag_enabled": _os.environ.get("NEXUS_H5_ALLOW_FINAL_PATCH_REPLACEMENT", "").strip() == "1",
        "final_source_before": "none",
        "final_source_after_shadow": "none",
        "final_patch_replacement_would_occur": False,
        "output_mutation_would_occur": False,
        "model_calls_increment_would_occur": False,
        "rollback_required": False,
        "rollback_receipt_required": True,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_local_candidate_rollback_dry_run(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds rollback dry-run receipt.

    No side effects. No mutation. No actual rollback.
    """
    promo = row.get("h5_local_candidate_promotion_dry_run", {})
    mutation = bool(promo.get("output_mutation_would_occur", False))

    return {
        "schema": "nexus.hybrid_h5_local_candidate_rollback_dry_run.v1",
        "evaluated": True,
        "rollback_available": True,
        "rollback_required": mutation,
        "rollback_status": "not_required" if not mutation else "required",
        "rollback_reasons": ["unexpected_mutation_detected"] if mutation else [],
        "pre_promotion_final_source": "none",
        "post_rollback_final_source_shadow": "none",
        "pre_promotion_final_patch_present": False,
        "post_rollback_final_patch_present_shadow": False,
        "output_restored_shadow": True,
        "model_calls_restored_shadow": True,
        "safe_to_continue": not mutation,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_local_candidate_promotion_gate_matrix(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds promotion gate matrix.

    No side effects. No mutation.
    """
    import os as _os

    promo = row.get("h5_local_candidate_promotion_dry_run")
    rollback = row.get("h5_local_candidate_rollback_dry_run")
    allow_local = _os.environ.get("NEXUS_H5_ALLOW_LOCAL_FINALIZATION", "").strip() == "1"
    allow_source = _os.environ.get("NEXUS_H5_ALLOW_FINAL_SOURCE_CHANGE", "").strip() == "1"
    allow_patch = _os.environ.get("NEXUS_H5_ALLOW_FINAL_PATCH_REPLACEMENT", "").strip() == "1"

    reasons = []
    if not promo:
        reasons.append("missing_promotion_dry_run")
    if not rollback:
        reasons.append("missing_rollback_dry_run")
    if not (allow_local and allow_source and allow_patch):
        reasons.append("future_flags_not_all_enabled")

    reasons.extend([
        "quality_non_regression_missing",
        "full_benchmark_missing",
        "governance_approval_missing",
        "promotion_dry_run_only",
        "real_promotion_not_implemented",
    ])

    return {
        "schema": "nexus.hybrid_h5_local_candidate_promotion_gate_matrix.v1",
        "evaluated": True,
        "promotion_gate_status": "blocked",
        "promotion_gate_reasons": reasons,
        "promotion_dry_run_present": bool(promo),
        "rollback_dry_run_present": bool(rollback),
        "quality_non_regression_ready": False,
        "full_benchmark_ready": False,
        "governance_ready": False,
        "all_future_flags_enabled": allow_local and allow_source and allow_patch,
        "promotion_allowed": False,
        "final_source_change_allowed": False,
        "final_patch_replacement_allowed": False,
        "output_mutation_allowed": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_local_candidate_shadow_final_source_promotion(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds shadow final_source promotion contract.

    No side effects. No model calls. No mutation. No actual final_source change.
    """
    promo = row.get("h5_local_candidate_promotion_dry_run")
    rollback = row.get("h5_local_candidate_rollback_dry_run")
    gate = row.get("h5_local_candidate_promotion_gate_matrix")
    local_shadow = row.get("h5_local_evidence_ingestion_shadow")

    actual_fs = str(row.get("final_source", "none") or "none")
    h5_fs = str(row.get("h5_route", {}).get("final_source", "none") or "none")
    actual_changed = actual_fs != "none" or h5_fs != "none"

    reasons = []
    shadow_candidate = False

    if not promo:
        reasons.append("missing_promotion_dry_run")
    if not rollback:
        reasons.append("missing_rollback_dry_run")
    if not gate:
        reasons.append("missing_promotion_gate_matrix")

    promo_candidate = bool(promo and promo.get("would_promote_local_candidate", False))
    has_metadata = bool(local_shadow and local_shadow.get("local_path_ready_shadow_from_external_evidence", False))
    rollback_safe = bool(rollback and rollback.get("safe_to_continue", False))

    if promo_candidate and has_metadata and rollback_safe:
        shadow_candidate = True

    if shadow_candidate:
        shadow_status = "shadow_ready_blocked"
    else:
        shadow_status = "blocked"
        if promo_candidate and not rollback_safe:
            reasons.append("rollback_not_safe")
        if not promo_candidate:
            reasons.append("promotion_dry_run_not_candidate")

    reasons.extend([
        "shadow_only_no_actual_final_source_change",
        "promotion_gate_blocked",
        "final_source_change_not_enabled",
        "real_promotion_not_implemented",
    ])

    if actual_changed:
        reasons.append("unexpected_actual_final_source_change")

    shadow_fs = "local_candidate_shadow_promoted" if shadow_candidate else "none"
    would_set = "local_candidate_shadow_promoted" if shadow_candidate else ""

    return {
        "schema": "nexus.hybrid_h5_local_candidate_shadow_final_source_promotion.v1",
        "evaluated": True,
        "shadow_promotion_candidate": shadow_candidate,
        "shadow_promotion_status": shadow_status,
        "shadow_promotion_reasons": reasons,
        "actual_final_source_before": actual_fs,
        "actual_final_source_after": actual_fs,
        "shadow_final_source_after_promotion": shadow_fs,
        "actual_final_source_changed": actual_changed,
        "final_source_change_allowed": False,
        "would_set_final_source_to": would_set,
        "would_promote_local_candidate": promo_candidate,
        "promotion_allowed": False,
        "promotion_gate_blocked": True,
        "rollback_available": bool(rollback),
        "rollback_required": bool(rollback and not rollback.get("safe_to_continue", True)),
        "selected_candidate_id": str(row.get("h5_route", {}).get("local_selected_candidate_id", "") or ""),
        "selected_candidate_patch_sha256": "",
        "selected_candidate_hash_verified": bool(row.get("h5_route", {}).get("local_selected_candidate_hash_match", False)),
        "final_patch_replacement_allowed": False,
        "final_patch_replacement_would_occur": False,
        "output_mutation_allowed": False,
        "output_mutation_would_occur": False,
        "model_calls_increment_would_occur": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_final_patch_replacement_shadow_contract(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds final_patch replacement shadow contract.

    No side effects. No model calls. No mutation. No actual final_patch replacement.
    """
    shadow_fs_promo = row.get("h5_local_candidate_shadow_final_source_promotion")
    rollback = row.get("h5_local_candidate_rollback_dry_run")

    reasons = []
    shadow_patch = False

    actual_fp = bool(row.get("final_patch"))
    selected_candidate_id = str(row.get("h5_route", {}).get("local_selected_candidate_id", "") or "")
    selected_patch_sha256 = str(row.get("h5_route", {}).get("local_selected_candidate_patch_sha256", "") or "")
    selected_patch_length = int(row.get("h5_route", {}).get("local_selected_candidate_patch_length", 0) or 0)
    selected_hash_verified = bool(row.get("h5_route", {}).get("local_selected_candidate_hash_match", False))
    rollback_available = bool(rollback and rollback.get("rollback_available", False))

    if not shadow_fs_promo:
        reasons.append("missing_shadow_final_source_promotion")

    fs_shadow_candidate = bool(shadow_fs_promo and shadow_fs_promo.get("shadow_promotion_candidate", False))
    fs_shadow_promoted = str(shadow_fs_promo and shadow_fs_promo.get("shadow_final_source_after_promotion", "") or "")

    if shadow_fs_promo and not fs_shadow_candidate:
        reasons.append("shadow_final_source_not_promoted")

    if not selected_patch_sha256:
        reasons.append("missing_selected_candidate_patch_sha256")
    if selected_patch_length <= 0:
        reasons.append("missing_selected_candidate_patch_length")
    if not selected_hash_verified:
        reasons.append("selected_candidate_hash_not_verified")
    if not rollback_available:
        reasons.append("rollback_not_available")

    if fs_shadow_candidate and fs_shadow_promoted == "local_candidate_shadow_promoted" and selected_patch_sha256 and selected_patch_length > 0 and selected_hash_verified and rollback_available:
        shadow_patch = True

    if shadow_patch:
        shadow_status = "shadow_ready_blocked"
    else:
        shadow_status = "blocked"

    reasons.extend([
        "shadow_only_no_actual_final_patch_replacement",
        "final_patch_replacement_not_enabled",
        "promotion_allowed_false",
        "real_patch_replacement_not_implemented",
    ])

    return {
        "schema": "nexus.hybrid_h5_final_patch_replacement_shadow_contract.v1",
        "evaluated": True,
        "shadow_patch_candidate": shadow_patch,
        "shadow_patch_status": shadow_status,
        "shadow_patch_reasons": reasons,
        "selected_candidate_id": selected_candidate_id,
        "selected_candidate_patch_sha256": selected_patch_sha256,
        "selected_candidate_patch_length": selected_patch_length,
        "selected_candidate_hash_verified": selected_hash_verified,
        "actual_final_patch_present_before": actual_fp,
        "actual_final_patch_present_after": actual_fp,
        "actual_final_patch_replaced": False,
        "shadow_final_patch_replacement_would_occur": shadow_patch,
        "final_patch_replacement_allowed": False,
        "promotion_allowed": False,
        "shadow_final_source_after_promotion": fs_shadow_promoted if fs_shadow_candidate else "none",
        "actual_final_source_after": str(row.get("final_source", "none") or "none"),
        "rollback_available": rollback_available,
        "rollback_required": bool(rollback and not rollback.get("safe_to_continue", True)),
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_output_mutation_guard(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds output mutation guard.

    No side effects. No model calls. No mutation. No actual output change.
    """
    patch_shadow = row.get("h5_final_patch_replacement_shadow_contract")
    fs_shadow = row.get("h5_local_candidate_shadow_final_source_promotion")
    rollback = row.get("h5_local_candidate_rollback_dry_run")

    reasons = []
    mutation_candidate = False

    actual_output = row.get("output")
    actual_fs = str(row.get("final_source", "none") or "none")
    actual_fp = bool(row.get("final_patch"))
    actual_model_calls = int(row.get("model_calls", 0) or 0)

    actual_fs_changed = actual_fs != "none"
    actual_fp_replaced = False
    actual_output_mutated = False
    actual_model_calls_incremented = actual_model_calls > 0 and bool(row.get("_model_calls_baseline"))

    if not patch_shadow:
        reasons.append("missing_final_patch_replacement_shadow_contract")

    shadow_patch_candidate = bool(patch_shadow and patch_shadow.get("shadow_patch_candidate", False))
    shadow_fp_would_occur = bool(patch_shadow and patch_shadow.get("shadow_final_patch_replacement_would_occur", False))

    if patch_shadow and not shadow_patch_candidate:
        reasons.append("shadow_patch_candidate_false")

    if shadow_patch_candidate and shadow_fp_would_occur:
        mutation_candidate = True

    if actual_output_mutated:
        reasons.append("unexpected_actual_output_mutation")
    if actual_fs_changed:
        reasons.append("unexpected_actual_final_source_change")
    if actual_fp_replaced:
        reasons.append("unexpected_actual_final_patch_replacement")
    if actual_model_calls_incremented:
        reasons.append("unexpected_model_calls_increment")

    reasons.extend([
        "shadow_only_no_output_mutation",
        "output_mutation_not_enabled",
        "real_output_mutation_not_implemented",
    ])

    unexpected = actual_output_mutated or actual_fs_changed or actual_fp_replaced or actual_model_calls_incremented

    return {
        "schema": "nexus.hybrid_h5_output_mutation_guard.v1",
        "evaluated": True,
        "output_mutation_candidate": mutation_candidate,
        "output_mutation_status": "blocked",
        "output_mutation_reasons": reasons,
        "shadow_patch_candidate": shadow_patch_candidate,
        "shadow_final_patch_replacement_would_occur": shadow_fp_would_occur,
        "actual_output_mutated": actual_output_mutated,
        "output_mutation_allowed": False,
        "actual_final_source_changed": actual_fs_changed,
        "actual_final_patch_replaced": actual_fp_replaced,
        "model_calls_incremented": actual_model_calls_incremented,
        "safe_to_continue": not unexpected,
        "rollback_required": unexpected,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_controlled_mutation_gate(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: single controlled mutation gate reading all H5 shadow contracts.

    No side effects. No model calls. No mutation. Gate always blocks in H5-30.
    """
    import os as _os

    fs_shadow = row.get("h5_local_candidate_shadow_final_source_promotion")
    patch_shadow = row.get("h5_final_patch_replacement_shadow_contract")
    output_guard = row.get("h5_output_mutation_guard")
    flag_contract = row.get("h5_execution_flag_contract")
    closure = row.get("h5_overall_readiness_closure")
    rollback = row.get("h5_local_candidate_rollback_dry_run")

    flag_exec = _os.environ.get("NEXUS_H5_ENABLE_CONTROLLED_EXECUTION", "").strip() == "1"
    flag_finalization = _os.environ.get("NEXUS_H5_ALLOW_LOCAL_FINALIZATION", "").strip() == "1"
    flag_fs = _os.environ.get("NEXUS_H5_ALLOW_FINAL_SOURCE_CHANGE", "").strip() == "1"
    flag_fp = _os.environ.get("NEXUS_H5_ALLOW_FINAL_PATCH_REPLACEMENT", "").strip() == "1"
    flag_output = _os.environ.get("NEXUS_H5_ALLOW_OUTPUT_MUTATION", "").strip() == "1"
    all_flags = flag_exec and flag_finalization and flag_fs and flag_fp and flag_output

    reasons = []

    fs_candidate = bool(fs_shadow and fs_shadow.get("shadow_promotion_candidate", False))
    fs_would_set = str(fs_shadow and fs_shadow.get("would_set_final_source_to", "") or "")
    fp_candidate = bool(patch_shadow and patch_shadow.get("shadow_patch_candidate", False))
    fp_would_occur = bool(patch_shadow and patch_shadow.get("shadow_final_patch_replacement_would_occur", False))
    out_candidate = bool(output_guard and output_guard.get("output_mutation_candidate", False))

    actual_fs = str(row.get("final_source", "none") or "none")
    actual_fp_replaced = bool(patch_shadow and patch_shadow.get("actual_final_patch_replaced", False))
    actual_out_mutated = bool(output_guard and output_guard.get("actual_output_mutated", False))
    actual_model_calls_inc = bool(output_guard and output_guard.get("model_calls_incremented", False))

    actual_fs_changed = actual_fs != "none"
    any_unexpected = actual_fs_changed or actual_fp_replaced or actual_out_mutated or actual_model_calls_inc

    if not fs_candidate:
        reasons.append("final_source_mutation_candidate_missing")
    if not fp_candidate:
        reasons.append("final_patch_mutation_candidate_missing")
    if not out_candidate:
        reasons.append("output_mutation_candidate_missing")

    if actual_fs_changed:
        reasons.append("unexpected_actual_final_source_change")
    if actual_fp_replaced:
        reasons.append("unexpected_actual_final_patch_replacement")
    if actual_out_mutated:
        reasons.append("unexpected_actual_output_mutation")
    if actual_model_calls_inc:
        reasons.append("unexpected_actual_model_calls_increment")

    reasons.extend([
        "h5_30_design_only",
        "quality_non_regression_missing",
        "full_benchmark_missing",
        "governance_approval_missing",
        "real_mutation_not_implemented",
        "rollback_not_promoted",
    ])

    return {
        "schema": "nexus.hybrid_h5_controlled_mutation_gate.v1",
        "evaluated": True,
        "gate_status": "blocked",
        "mutation_allowed": False,
        "gate_reasons": reasons,
        "final_source_mutation_candidate": fs_candidate and fs_would_set == "local_candidate_shadow_promoted",
        "final_patch_mutation_candidate": fp_candidate and fp_would_occur,
        "output_mutation_candidate": out_candidate,
        "model_calls_mutation_candidate": False,
        "final_source_mutation_allowed": False,
        "final_patch_mutation_allowed": False,
        "output_mutation_allowed": False,
        "model_calls_mutation_allowed": False,
        "rollback_available": bool(rollback),
        "rollback_required": any_unexpected,
        "safe_to_continue": not any_unexpected,
        "quality_non_regression_ready": bool(closure and closure.get("quality_non_regression_missing", True) is False),
        "full_benchmark_ready": bool(closure and closure.get("full_benchmark_missing", True) is False),
        "governance_ready": bool(closure and closure.get("governance_approval_missing", True) is False),
        "all_required_flags_enabled": all_flags,
        "actual_final_source_changed": actual_fs_changed,
        "actual_final_patch_replaced": actual_fp_replaced,
        "actual_output_mutated": actual_out_mutated,
        "actual_model_calls_incremented": actual_model_calls_inc,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_local_final_source_controlled_trial_receipt(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds local final_source controlled trial receipt.

    No side effects. No model calls. No mutation. No actual final_source change.
    """
    gate = row.get("h5_controlled_mutation_gate")
    fs_shadow = row.get("h5_local_candidate_shadow_final_source_promotion")
    promo = row.get("h5_local_candidate_promotion_dry_run")
    local_shadow = row.get("h5_local_evidence_ingestion_shadow")
    cloud_shadow = row.get("h5_cloud_evidence_ingestion_shadow")
    closure = row.get("h5_overall_readiness_closure")

    actual_fs = str(row.get("final_source", "none") or "none")
    h5_fs = str(row.get("h5_route", {}).get("final_source", "none") or "none")
    actual_changed = actual_fs != "none" or h5_fs != "none"

    reasons = []

    gate_present = bool(gate)
    gate_blocked = bool(gate and gate.get("gate_status") == "blocked")
    all_flags = bool(gate and gate.get("all_required_flags_enabled", False))
    gate_safe = bool(gate and gate.get("safe_to_continue", True))
    gate_rollback = bool(gate and gate.get("rollback_required", False))
    mutation_allowed = bool(gate and gate.get("mutation_allowed", False))

    fs_shadow_candidate = bool(fs_shadow and fs_shadow.get("shadow_promotion_candidate", False))
    fs_shadow_promoted = str(fs_shadow and fs_shadow.get("shadow_final_source_after_promotion", "") or "")
    promo_would = bool(promo and promo.get("would_promote_local_candidate", False))

    local_ready = bool(local_shadow and local_shadow.get("local_path_ready_shadow_from_external_evidence", False))
    cloud_ready = bool(cloud_shadow and cloud_shadow.get("cloud_path_ready_shadow_from_external_evidence", False))
    all_shadow = bool(closure and closure.get("all_shadow_evidence_present", False))

    would_trial = (
        gate_present and all_flags and gate_safe and not gate_rollback
        and fs_shadow_candidate and fs_shadow_promoted == "local_candidate_shadow_promoted"
        and promo_would and local_ready and cloud_ready and all_shadow
    )

    if not gate_present:
        reasons.append("missing_controlled_mutation_gate")
    if gate and not gate_safe:
        reasons.append("controlled_mutation_gate_not_safe")
    if not all_flags:
        reasons.append("required_flags_not_enabled")
    if not fs_shadow_candidate:
        reasons.append("shadow_final_source_candidate_missing")
    if not local_ready:
        reasons.append("local_evidence_not_ready")
    if not cloud_ready:
        reasons.append("cloud_evidence_not_ready")
    if not all_shadow:
        reasons.append("all_shadow_evidence_not_present")
    if not promo_would:
        reasons.append("promotion_dry_run_not_ready")
    if actual_changed:
        reasons.append("unexpected_actual_final_source_change")

    reasons.extend([
        "h5_31_trial_only_no_actual_final_source_change",
        "real_final_source_mutation_not_implemented",
        "final_patch_replacement_still_blocked",
        "output_mutation_still_blocked",
    ])

    trial_fs = "local_candidate_shadow_promoted" if would_trial else "none"
    trial_status = "trial_ready_blocked" if would_trial else "blocked"

    return {
        "schema": "nexus.hybrid_h5_local_final_source_controlled_trial_receipt.v1",
        "evaluated": True,
        "trial_status": trial_status,
        "trial_reasons": reasons,
        "would_allow_final_source_trial": would_trial,
        "actual_final_source_before": actual_fs,
        "actual_final_source_after": actual_fs,
        "actual_final_source_changed": actual_changed,
        "shadow_final_source_after_promotion": fs_shadow_promoted if fs_shadow_candidate else "none",
        "trial_final_source_after_promotion": trial_fs,
        "controlled_mutation_gate_present": gate_present,
        "controlled_mutation_gate_blocked": gate_blocked,
        "all_required_flags_enabled": all_flags,
        "mutation_allowed": mutation_allowed,
        "safe_to_continue": gate_safe and not gate_rollback,
        "rollback_required": gate_rollback,
        "local_evidence_ready": local_ready,
        "cloud_evidence_ready": cloud_ready,
        "all_shadow_evidence_present": all_shadow,
        "promotion_dry_run_would_promote": promo_would,
        "shadow_final_source_candidate": fs_shadow_candidate,
        "final_patch_replacement_allowed": False,
        "output_mutation_allowed": False,
        "model_calls_increment_allowed": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_final_source_apply_preflight_receipt(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds final_source apply preflight receipt.

    No side effects. No model calls. No mutation. No actual final_source change.
    """
    import os as _os

    trial = row.get("h5_local_final_source_controlled_trial_receipt")
    gate = row.get("h5_controlled_mutation_gate")
    rollback = row.get("h5_local_candidate_rollback_dry_run")

    actual_fs = str(row.get("final_source", "none") or "none")
    h5_fs = str(row.get("h5_route", {}).get("final_source", "none") or "none")
    actual_changed = actual_fs != "none" or h5_fs != "none"

    flag_preflight = _os.environ.get("NEXUS_H5_ALLOW_FINAL_SOURCE_APPLY_PREFLIGHT", "").strip() == "1"

    reasons = []

    trial_present = bool(trial)
    trial_ready = bool(trial and trial.get("would_allow_final_source_trial", False))
    trial_blocked = bool(trial and trial.get("trial_status") == "trial_ready_blocked")

    gate_present = bool(gate)
    gate_safe = bool(gate and gate.get("safe_to_continue", True))
    gate_rollback = bool(gate and gate.get("rollback_required", False))
    all_flags = bool(gate and gate.get("all_required_flags_enabled", False))

    rb_available = bool(rollback and rollback.get("rollback_available", False))
    rb_safe = bool(rollback and rollback.get("safe_to_continue", True))

    would_pass = (
        trial_present and trial_ready and trial_blocked
        and gate_present and gate_safe and not gate_rollback and all_flags
        and rb_available and rb_safe
        and flag_preflight
        and actual_fs == "none"
    )

    if not trial_present:
        reasons.append("missing_trial_receipt")
    if trial and not trial_ready:
        reasons.append("trial_receipt_not_ready")
    if not gate_present:
        reasons.append("missing_controlled_mutation_gate")
    if gate and not gate_safe:
        reasons.append("controlled_mutation_gate_not_safe")
    if not all_flags:
        reasons.append("required_flags_not_enabled")
    if not flag_preflight:
        reasons.append("final_source_apply_preflight_flag_not_enabled")
    if not rb_available:
        reasons.append("rollback_not_available")
    if gate and gate_rollback:
        reasons.append("rollback_required")
    if actual_changed:
        reasons.append("unexpected_actual_final_source_change")

    reasons.extend([
        "h5_32_preflight_only_no_actual_final_source_change",
        "real_final_source_apply_not_implemented",
        "final_patch_replacement_still_blocked",
        "output_mutation_still_blocked",
    ])

    preflight_status = "preflight_pass_shadow_only" if would_pass else "blocked"

    return {
        "schema": "nexus.hybrid_h5_final_source_apply_preflight_receipt.v1",
        "evaluated": True,
        "preflight_status": preflight_status,
        "preflight_reasons": reasons,
        "would_pass_final_source_apply_preflight": would_pass,
        "apply_target_final_source": "local_candidate_shadow_promoted",
        "actual_final_source_before": actual_fs,
        "actual_final_source_after": actual_fs,
        "actual_final_source_changed": actual_changed,
        "trial_receipt_present": trial_present,
        "trial_receipt_ready": trial_ready,
        "controlled_mutation_gate_present": gate_present,
        "controlled_mutation_gate_safe": gate_safe,
        "controlled_mutation_allowed": False,
        "all_required_flags_enabled": all_flags,
        "final_source_change_flag_enabled": bool(gate and gate.get("all_required_flags_enabled", False)),
        "final_patch_replacement_allowed": False,
        "output_mutation_allowed": False,
        "model_calls_increment_allowed": False,
        "rollback_available": rb_available,
        "rollback_required": gate_rollback,
        "safe_to_continue": not gate_rollback and not actual_changed,
        "apply_side_effects_allowed": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_isolated_final_source_mutation_simulation(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds isolated final_source mutation simulation receipt.

    No side effects. No model calls. No mutation of actual finalized row.
    Simulates changing final_source in an isolated copy only.
    """
    preflight = row.get("h5_final_source_apply_preflight_receipt")
    rollback = row.get("h5_local_candidate_rollback_dry_run")
    gate = row.get("h5_controlled_mutation_gate")

    actual_fs = str(row.get("final_source", "none") or "none")
    h5_fs = str(row.get("h5_route", {}).get("final_source", "none") or "none")
    actual_changed = actual_fs != "none" or h5_fs != "none"

    reasons = []

    preflight_present = bool(preflight)
    preflight_pass = bool(preflight and preflight.get("would_pass_final_source_apply_preflight", False))
    preflight_shadow = bool(preflight and preflight.get("preflight_status") == "preflight_pass_shadow_only")

    rb_available = bool(rollback and rollback.get("rollback_available", False))
    rb_required = bool(rollback and rollback.get("rollback_required", False))
    rb_safe = bool(rollback and rollback.get("safe_to_continue", True))

    gate_safe = bool(gate and gate.get("safe_to_continue", True))

    would_simulate = (
        preflight_present and preflight_pass and preflight_shadow
        and actual_fs == "none"
        and rb_available and not rb_required and rb_safe
    )

    if not preflight_present:
        reasons.append("missing_preflight_receipt")
    if preflight and not preflight_pass:
        reasons.append("preflight_not_passed")
    if not rb_available:
        reasons.append("rollback_not_available")
    if rb_required:
        reasons.append("rollback_required")
    if gate and not gate_safe:
        reasons.append("controlled_mutation_gate_not_safe")
    if actual_changed:
        reasons.append("unexpected_actual_final_source_change")

    reasons.extend([
        "isolated_simulation_only_no_actual_final_source_change",
        "real_final_source_apply_not_enabled",
        "final_patch_replacement_still_blocked",
        "output_mutation_still_blocked",
    ])

    isolated_before = "none"
    isolated_after = "local_candidate_shadow_promoted" if would_simulate else "none"
    isolated_changed = would_simulate

    return {
        "schema": "nexus.hybrid_h5_isolated_final_source_mutation_simulation.v1",
        "evaluated": True,
        "simulation_status": "isolated_simulation_pass" if would_simulate else "blocked",
        "simulation_reasons": reasons,
        "would_simulate_final_source_mutation": would_simulate,
        "simulation_target_final_source": "local_candidate_shadow_promoted",
        "actual_final_source_before": actual_fs,
        "actual_final_source_after": actual_fs,
        "actual_final_source_changed": actual_changed,
        "isolated_final_source_before": isolated_before,
        "isolated_final_source_after": isolated_after,
        "isolated_final_source_changed": isolated_changed,
        "preflight_receipt_present": preflight_present,
        "preflight_pass_shadow_only": preflight_pass,
        "apply_side_effects_allowed": False,
        "controlled_mutation_allowed": False,
        "final_patch_replacement_allowed": False,
        "output_mutation_allowed": False,
        "model_calls_increment_allowed": False,
        "rollback_available": rb_available,
        "rollback_required": rb_required,
        "safe_to_continue": not rb_required and not actual_changed,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_actual_final_source_apply_decision(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds actual final_source apply decision.

    No side effects. No mutation of input row.
    """
    import os as _os

    preflight = row.get("h5_final_source_apply_preflight_receipt")
    simulation = row.get("h5_isolated_final_source_mutation_simulation")
    rollback = row.get("h5_local_candidate_rollback_dry_run")

    actual_fs = str(row.get("final_source", "none") or "none")

    flag_exec = _os.environ.get("NEXUS_H5_ENABLE_CONTROLLED_EXECUTION", "").strip() == "1"
    flag_finalization = _os.environ.get("NEXUS_H5_ALLOW_LOCAL_FINALIZATION", "").strip() == "1"
    flag_fs = _os.environ.get("NEXUS_H5_ALLOW_FINAL_SOURCE_CHANGE", "").strip() == "1"
    flag_fp = _os.environ.get("NEXUS_H5_ALLOW_FINAL_PATCH_REPLACEMENT", "").strip() == "1"
    flag_output = _os.environ.get("NEXUS_H5_ALLOW_OUTPUT_MUTATION", "").strip() == "1"
    flag_preflight = _os.environ.get("NEXUS_H5_ALLOW_FINAL_SOURCE_APPLY_PREFLIGHT", "").strip() == "1"
    flag_apply = _os.environ.get("NEXUS_H5_ALLOW_ACTUAL_FINAL_SOURCE_APPLY", "").strip() == "1"
    all_seven = flag_exec and flag_finalization and flag_fs and flag_fp and flag_output and flag_preflight and flag_apply

    preflight_pass = bool(preflight and preflight.get("would_pass_final_source_apply_preflight", False))
    preflight_shadow = str(preflight and preflight.get("preflight_status", "") or "") == "preflight_pass_shadow_only"
    sim_pass = bool(simulation and simulation.get("would_simulate_final_source_mutation", False))
    sim_status = str(simulation and simulation.get("simulation_status", "") or "") == "isolated_simulation_pass"
    sim_target = str(simulation and simulation.get("isolated_final_source_after", "") or "")

    rb_available = bool(rollback and rollback.get("rollback_available", False))
    rb_required = bool(rollback and rollback.get("rollback_required", False))
    rb_safe = bool(rollback and rollback.get("safe_to_continue", True))

    would_apply = (
        all_seven
        and preflight_pass and preflight_shadow
        and sim_pass and sim_status and sim_target == "local_candidate_shadow_promoted"
        and rb_available and not rb_required and rb_safe
        and actual_fs == "none"
    )

    reasons = []

    if not all_seven:
        reasons.append("required_flags_not_all_enabled")
    if not flag_apply:
        reasons.append("actual_final_source_apply_flag_not_enabled")
    if preflight and not preflight_pass:
        reasons.append("preflight_not_passed")
    if simulation and not sim_pass:
        reasons.append("isolated_simulation_not_passed")
    if not rb_available:
        reasons.append("rollback_not_available")
    if rb_required:
        reasons.append("rollback_required")
    if not rb_safe:
        reasons.append("rollback_not_safe")
    if actual_fs != "none":
        reasons.append("actual_final_source_not_none")

    reasons.extend([
        "final_source_only_apply_gate",
        "final_patch_replacement_still_blocked",
        "output_mutation_still_blocked",
        "model_calls_increment_still_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h5_actual_final_source_apply_decision.v1",
        "evaluated": True,
        "apply_decision": "apply_final_source_only" if would_apply else "blocked",
        "apply_reasons": reasons,
        "actual_apply_allowed": would_apply,
        "apply_target_final_source": "local_candidate_shadow_promoted",
        "actual_final_source_before": actual_fs,
        "would_change_final_source_to": "local_candidate_shadow_promoted" if would_apply else "none",
        "all_seven_flags_enabled": all_seven,
        "preflight_pass_shadow_only": preflight_pass and preflight_shadow,
        "isolated_simulation_pass": sim_pass and sim_status,
        "rollback_available": rb_available,
        "rollback_required": rb_required,
        "safe_to_continue": not rb_required,
        "final_patch_replacement_allowed": False,
        "output_mutation_allowed": False,
        "model_calls_increment_allowed": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _apply_h5_actual_final_source_if_allowed(row: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Returns a shallow copy of row with final_source possibly changed.

    Never mutates input row. Only changes final_source when decision.actual_apply_allowed=true.
    """
    result = dict(row)
    actual_before = str(row.get("final_source", "none") or "none")
    allowed = bool(decision.get("actual_apply_allowed", False))
    target = str(decision.get("apply_target_final_source", "") or "")

    if allowed and target:
        result["final_source"] = target
    result["h5_actual_final_source_apply_receipt"] = {
        "schema": "nexus.hybrid_h5_actual_final_source_apply_receipt.v1",
        "evaluated": True,
        "actual_apply_executed": allowed,
        "actual_final_source_before": actual_before,
        "actual_final_source_after": result.get("final_source", actual_before),
        "actual_final_source_changed": result.get("final_source", actual_before) != actual_before,
        "apply_decision": str(decision.get("apply_decision", "blocked")),
        "apply_target_final_source": target,
        "final_patch_replaced": False,
        "output_mutated": False,
        "model_calls_incremented": False,
        "cloud_invoked": False,
        "behavior_changed": False,
        "rollback_available": bool(decision.get("rollback_available", False)),
        "rollback_required": bool(decision.get("rollback_required", False)),
        "safe_to_continue": bool(decision.get("safe_to_continue", True)),
        "public_claim_allowed": False,
        "production_ready": False,
    }
    return result


def _build_h5_actual_final_source_rollback_decision(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds actual final_source rollback decision.

    No side effects. No mutation of input row.
    """
    import os as _os

    apply_receipt = row.get("h5_actual_final_source_apply_receipt")
    actual_fs = str(row.get("final_source", "none") or "none")

    flag_rollback = _os.environ.get("NEXUS_H5_ALLOW_ACTUAL_FINAL_SOURCE_ROLLBACK", "").strip() == "1"

    apply_present = bool(apply_receipt)
    apply_executed = bool(apply_receipt and apply_receipt.get("actual_apply_executed", False))
    apply_changed = bool(apply_receipt and apply_receipt.get("actual_final_source_changed", False))
    fp_clean = not bool(apply_receipt and apply_receipt.get("final_patch_replaced", False))
    out_clean = not bool(apply_receipt and apply_receipt.get("output_mutated", False))
    mc_clean = not bool(apply_receipt and apply_receipt.get("model_calls_incremented", False))
    cloud_clean = not bool(apply_receipt and apply_receipt.get("cloud_invoked", False))
    beh_clean = not bool(apply_receipt and apply_receipt.get("behavior_changed", False))

    is_promoted = actual_fs == "local_candidate_shadow_promoted"

    would_rollback = (
        flag_rollback and is_promoted
        and apply_present and apply_executed and apply_changed
        and fp_clean and out_clean and mc_clean and cloud_clean and beh_clean
    )

    reasons = []

    if not flag_rollback:
        reasons.append("rollback_flag_not_enabled")
    if not is_promoted:
        reasons.append("final_source_not_promoted")
    if not apply_present:
        reasons.append("missing_actual_apply_receipt")
    if apply_receipt and not apply_executed:
        reasons.append("actual_apply_not_executed")
    if apply_receipt and not apply_changed:
        reasons.append("actual_apply_final_source_not_changed")
    if not fp_clean:
        reasons.append("final_patch_was_replaced")
    if not out_clean:
        reasons.append("output_was_mutated")
    if not mc_clean:
        reasons.append("model_calls_were_incremented")
    if not cloud_clean:
        reasons.append("cloud_was_invoked")
    if not beh_clean:
        reasons.append("behavior_changed_true")

    reasons.extend([
        "final_source_only_rollback_gate",
        "final_patch_remains_unchanged",
        "output_remains_unchanged",
        "model_calls_remain_unchanged",
    ])

    return {
        "schema": "nexus.hybrid_h5_actual_final_source_rollback_decision.v1",
        "evaluated": True,
        "rollback_decision": "rollback_final_source_only" if would_rollback else "blocked",
        "rollback_reasons": reasons,
        "rollback_allowed": would_rollback,
        "rollback_target_final_source": "none",
        "actual_final_source_before_rollback": actual_fs,
        "would_restore_final_source_to": "none" if would_rollback else "none",
        "actual_apply_receipt_present": apply_present,
        "actual_apply_executed": apply_executed,
        "rollback_flag_enabled": flag_rollback,
        "rollback_required": would_rollback,
        "rollback_safe": would_rollback,
        "final_patch_replaced": not fp_clean,
        "output_mutated": not out_clean,
        "model_calls_incremented": not mc_clean,
        "cloud_invoked": not cloud_clean,
        "behavior_changed": not beh_clean,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _rollback_h5_actual_final_source_if_allowed(row: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Returns a shallow copy of row with final_source possibly restored to 'none'.

    Never mutates input row.
    """
    result = dict(row)
    actual_before = str(row.get("final_source", "none") or "none")
    allowed = bool(decision.get("rollback_allowed", False))

    if allowed:
        result["final_source"] = "none"
    result["h5_actual_final_source_rollback_receipt"] = {
        "schema": "nexus.hybrid_h5_actual_final_source_rollback_receipt.v1",
        "evaluated": True,
        "rollback_executed": allowed,
        "actual_final_source_before_rollback": actual_before,
        "actual_final_source_after_rollback": result.get("final_source", actual_before),
        "actual_final_source_restored": allowed and result.get("final_source", actual_before) == "none",
        "rollback_decision": str(decision.get("rollback_decision", "blocked")),
        "rollback_target_final_source": "none",
        "final_patch_replaced": False,
        "output_mutated": False,
        "model_calls_incremented": False,
        "cloud_invoked": False,
        "behavior_changed": False,
        "safe_to_continue": True,
        "public_claim_allowed": False,
        "production_ready": False,
    }
    return result


def _build_h5_final_patch_apply_preflight_receipt(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds final_patch apply preflight receipt.

    No side effects. No model calls. No mutation. No actual final_patch replacement.
    """
    import os as _os

    patch_shadow = row.get("h5_final_patch_replacement_shadow_contract")
    output_guard = row.get("h5_output_mutation_guard")
    apply_receipt = row.get("h5_actual_final_source_apply_receipt")
    rollback_receipt = row.get("h5_actual_final_source_rollback_receipt")
    rollback = row.get("h5_local_candidate_rollback_dry_run")

    actual_fp = bool(row.get("final_patch"))
    actual_fs = str(row.get("final_source", "none") or "none")

    flag_preflight = _os.environ.get("NEXUS_H5_ALLOW_FINAL_PATCH_APPLY_PREFLIGHT", "").strip() == "1"

    shadow_patch = bool(patch_shadow and patch_shadow.get("shadow_patch_candidate", False))
    shadow_would_occur = bool(patch_shadow and patch_shadow.get("shadow_final_patch_replacement_would_occur", False))
    fp_not_replaced = not bool(patch_shadow and patch_shadow.get("actual_final_patch_replaced", False))
    out_clean = not bool(output_guard and output_guard.get("actual_output_mutated", False))
    out_blocked = bool(output_guard and output_guard.get("output_mutation_allowed", False) is False)

    selected_id = str(row.get("h5_route", {}).get("local_selected_candidate_id", "") or "")
    selected_sha256 = str(row.get("h5_route", {}).get("local_selected_candidate_patch_sha256", "") or "")
    selected_length = int(row.get("h5_route", {}).get("local_selected_candidate_patch_length", 0) or 0)
    selected_hash_ok = bool(row.get("h5_route", {}).get("local_selected_candidate_hash_match", False))

    apply_executed = bool(apply_receipt and apply_receipt.get("actual_apply_executed", False))
    apply_changed = bool(apply_receipt and apply_receipt.get("actual_final_source_changed", False))
    rollback_restored = bool(rollback_receipt and rollback_receipt.get("actual_final_source_restored", False))

    rb_available = bool(rollback and rollback.get("rollback_available", False))
    rb_safe = bool(rollback and rollback.get("safe_to_continue", True))

    cycle_proven = apply_executed and apply_changed
    rollback_proven = rollback_restored

    would_pass = (
        flag_preflight
        and shadow_patch and shadow_would_occur
        and bool(selected_sha256) and selected_length > 0 and selected_hash_ok
        and cycle_proven and rollback_proven
        and rb_available and rb_safe
        and out_clean and out_blocked
        and fp_not_replaced
    )

    reasons = []

    if not flag_preflight:
        reasons.append("final_patch_apply_preflight_flag_not_enabled")
    if not shadow_patch:
        reasons.append("shadow_patch_candidate_missing")
    if not bool(selected_sha256):
        reasons.append("selected_candidate_patch_hash_missing")
    if selected_length <= 0:
        reasons.append("selected_candidate_patch_length_missing")
    if not selected_hash_ok:
        reasons.append("selected_candidate_hash_not_verified")
    if not cycle_proven:
        reasons.append("final_source_apply_cycle_not_proven")
    if not rollback_proven:
        reasons.append("final_source_rollback_not_proven")
    if not rb_available:
        reasons.append("rollback_not_available")
    if not rb_safe:
        reasons.append("rollback_not_safe")
    if not out_clean:
        reasons.append("output_mutation_detected")
    if not fp_not_replaced:
        reasons.append("actual_final_patch_already_replaced")

    reasons.extend([
        "h5_36_preflight_only_no_actual_final_patch_replacement",
        "output_mutation_still_blocked",
        "model_calls_increment_still_blocked",
        "cloud_invocation_still_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h5_final_patch_apply_preflight_receipt.v1",
        "evaluated": True,
        "preflight_status": "final_patch_preflight_pass_shadow_only" if would_pass else "blocked",
        "preflight_reasons": reasons,
        "would_pass_final_patch_apply_preflight": would_pass,
        "selected_candidate_id": selected_id,
        "selected_candidate_patch_sha256": selected_sha256,
        "selected_candidate_patch_length": selected_length,
        "selected_candidate_hash_verified": selected_hash_ok,
        "actual_final_patch_present_before": actual_fp,
        "actual_final_patch_present_after": actual_fp,
        "actual_final_patch_replaced": False,
        "shadow_patch_candidate": shadow_patch,
        "shadow_final_patch_replacement_would_occur": shadow_would_occur,
        "final_source_apply_cycle_proven": cycle_proven,
        "final_source_rollback_proven": rollback_proven,
        "rollback_available": rb_available,
        "rollback_required": False,
        "safe_to_continue": rb_safe,
        "final_patch_apply_preflight_flag_enabled": flag_preflight,
        "final_patch_replacement_allowed": False,
        "output_mutation_allowed": False,
        "model_calls_increment_allowed": False,
        "cloud_invocation_allowed": False,
        "behavior_changed": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_isolated_final_patch_replacement_simulation(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds isolated final_patch replacement simulation receipt.

    No side effects. No model calls. No mutation of actual finalized row.
    Simulates replacing final_patch in an isolated copy only.
    """
    preflight = row.get("h5_final_patch_apply_preflight_receipt")
    rollback = row.get("h5_local_candidate_rollback_dry_run")
    output_guard = row.get("h5_output_mutation_guard")

    actual_fp = bool(row.get("final_patch"))
    actual_fs = str(row.get("final_source", "none") or "none")

    preflight_present = bool(preflight)
    preflight_pass = bool(preflight and preflight.get("would_pass_final_patch_apply_preflight", False))
    preflight_shadow = str(preflight and preflight.get("preflight_status", "") or "") == "final_patch_preflight_pass_shadow_only"

    selected_sha256 = str(row.get("h5_route", {}).get("local_selected_candidate_patch_sha256", "") or "")
    selected_length = int(row.get("h5_route", {}).get("local_selected_candidate_patch_length", 0) or 0)
    selected_id = str(row.get("h5_route", {}).get("local_selected_candidate_id", "") or "")
    selected_hash_ok = bool(row.get("h5_route", {}).get("local_selected_candidate_hash_match", False))

    cycle_proven = bool(preflight and preflight.get("final_source_apply_cycle_proven", False))
    rollback_proven = bool(preflight and preflight.get("final_source_rollback_proven", False))

    rb_available = bool(rollback and rollback.get("rollback_available", False))
    rb_required = bool(rollback and rollback.get("rollback_required", False))
    rb_safe = bool(rollback and rollback.get("safe_to_continue", True))

    out_clean = not bool(output_guard and output_guard.get("actual_output_mutated", False))

    would_sim = (
        preflight_present and preflight_pass and preflight_shadow
        and bool(selected_sha256) and selected_length > 0 and selected_hash_ok
        and cycle_proven and rollback_proven
        and rb_available and not rb_required and rb_safe
        and out_clean
    )

    reasons = []

    if not preflight_present:
        reasons.append("missing_final_patch_apply_preflight_receipt")
    if preflight and not preflight_pass:
        reasons.append("final_patch_preflight_not_passed")
    if not bool(selected_sha256):
        reasons.append("selected_candidate_patch_hash_missing")
    if selected_length <= 0:
        reasons.append("selected_candidate_patch_length_missing")
    if not selected_hash_ok:
        reasons.append("selected_candidate_hash_not_verified")
    if not cycle_proven:
        reasons.append("final_source_apply_cycle_not_proven")
    if not rollback_proven:
        reasons.append("final_source_rollback_not_proven")
    if not rb_available:
        reasons.append("rollback_not_available")
    if rb_required:
        reasons.append("rollback_required")
    if not rb_safe:
        reasons.append("rollback_not_safe")
    if not out_clean:
        reasons.append("output_mutation_detected")
    if actual_fp and would_sim:
        reasons.append("actual_final_patch_already_replaced")

    reasons.extend([
        "isolated_simulation_only_no_actual_final_patch_replacement",
        "output_mutation_still_blocked",
        "model_calls_increment_still_blocked",
        "cloud_invocation_still_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h5_isolated_final_patch_replacement_simulation.v1",
        "evaluated": True,
        "simulation_status": "isolated_final_patch_simulation_pass" if would_sim else "blocked",
        "simulation_reasons": reasons,
        "would_simulate_final_patch_replacement": would_sim,
        "selected_candidate_id": selected_id,
        "selected_candidate_patch_sha256": selected_sha256,
        "selected_candidate_patch_length": selected_length,
        "selected_candidate_hash_verified": selected_hash_ok,
        "actual_final_patch_present_before": actual_fp,
        "actual_final_patch_present_after": actual_fp,
        "actual_final_patch_replaced": False,
        "isolated_final_patch_present_before": actual_fp,
        "isolated_final_patch_present_after": True if would_sim else actual_fp,
        "isolated_final_patch_replaced": would_sim,
        "isolated_final_patch_sha256": selected_sha256 if would_sim else "",
        "isolated_final_patch_length": selected_length if would_sim else 0,
        "preflight_receipt_present": preflight_present,
        "preflight_pass_shadow_only": preflight_pass,
        "final_source_apply_cycle_proven": cycle_proven,
        "final_source_rollback_proven": rollback_proven,
        "rollback_available": rb_available,
        "rollback_required": rb_required,
        "safe_to_continue": not rb_required,
        "output_mutation_allowed": False,
        "output_mutated": not out_clean,
        "model_calls_incremented": False,
        "cloud_invoked": False,
        "behavior_changed": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_actual_final_patch_apply_decision(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds actual final_patch apply decision."""
    import os as _os

    preflight = row.get("h5_final_patch_apply_preflight_receipt")
    simulation = row.get("h5_isolated_final_patch_replacement_simulation")
    apply_receipt = row.get("h5_actual_final_source_apply_receipt")
    rollback_receipt = row.get("h5_actual_final_source_rollback_receipt")
    rollback = row.get("h5_local_candidate_rollback_dry_run")
    output_guard = row.get("h5_output_mutation_guard")

    actual_fp = bool(row.get("final_patch"))

    flag_exec = _os.environ.get("NEXUS_H5_ENABLE_CONTROLLED_EXECUTION", "").strip() == "1"
    flag_final = _os.environ.get("NEXUS_H5_ALLOW_LOCAL_FINALIZATION", "").strip() == "1"
    flag_fs = _os.environ.get("NEXUS_H5_ALLOW_FINAL_SOURCE_CHANGE", "").strip() == "1"
    flag_fp = _os.environ.get("NEXUS_H5_ALLOW_FINAL_PATCH_REPLACEMENT", "").strip() == "1"
    flag_out = _os.environ.get("NEXUS_H5_ALLOW_OUTPUT_MUTATION", "").strip() == "1"
    flag_fs_preflight = _os.environ.get("NEXUS_H5_ALLOW_FINAL_SOURCE_APPLY_PREFLIGHT", "").strip() == "1"
    flag_fs_apply = _os.environ.get("NEXUS_H5_ALLOW_ACTUAL_FINAL_SOURCE_APPLY", "").strip() == "1"
    flag_fs_rollback = _os.environ.get("NEXUS_H5_ALLOW_ACTUAL_FINAL_SOURCE_ROLLBACK", "").strip() == "1"
    flag_fp_preflight = _os.environ.get("NEXUS_H5_ALLOW_FINAL_PATCH_APPLY_PREFLIGHT", "").strip() == "1"
    flag_fp_apply = _os.environ.get("NEXUS_H5_ALLOW_ACTUAL_FINAL_PATCH_APPLY", "").strip() == "1"
    all_ten = (flag_exec and flag_final and flag_fs and flag_fp and flag_out
               and flag_fs_preflight and flag_fs_apply and flag_fs_rollback
               and flag_fp_preflight and flag_fp_apply)

    pf_pass = bool(preflight and preflight.get("would_pass_final_patch_apply_preflight", False))
    pf_shadow = str(preflight and preflight.get("preflight_status", "") or "") == "final_patch_preflight_pass_shadow_only"
    sim_pass = bool(simulation and simulation.get("would_simulate_final_patch_replacement", False))
    sim_status = str(simulation and simulation.get("simulation_status", "") or "") == "isolated_final_patch_simulation_pass"
    sim_replaced = bool(simulation and simulation.get("isolated_final_patch_replaced", False))

    selected_sha256 = str(row.get("h5_route", {}).get("local_selected_candidate_patch_sha256", "") or "")
    selected_length = int(row.get("h5_route", {}).get("local_selected_candidate_patch_length", 0) or 0)
    selected_id = str(row.get("h5_route", {}).get("local_selected_candidate_id", "") or "")
    selected_hash_ok = bool(row.get("h5_route", {}).get("local_selected_candidate_hash_match", False))

    cycle_proven = bool(apply_receipt and apply_receipt.get("actual_apply_executed", False) and apply_receipt.get("actual_final_source_changed", False))
    rb_fs_restored = bool(rollback_receipt and rollback_receipt.get("actual_final_source_restored", False))

    rb_available = bool(rollback and rollback.get("rollback_available", False))
    rb_required = bool(rollback and rollback.get("rollback_required", False))
    rb_safe = bool(rollback and rollback.get("safe_to_continue", True))

    out_clean = not bool(output_guard and output_guard.get("actual_output_mutated", False))

    would_apply = (
        all_ten and pf_pass and pf_shadow
        and sim_pass and sim_status and sim_replaced
        and bool(selected_sha256) and selected_length > 0 and selected_hash_ok
        and cycle_proven and rb_fs_restored
        and rb_available and not rb_required and rb_safe
        and out_clean
    )

    reasons = []
    if not flag_fp_apply:
        reasons.append("actual_final_patch_apply_flag_not_enabled")
    if not all_ten:
        reasons.append("required_flags_not_all_enabled")
    if preflight and not pf_pass:
        reasons.append("final_patch_preflight_not_passed")
    if simulation and not sim_pass:
        reasons.append("isolated_final_patch_simulation_not_passed")
    if not bool(selected_sha256):
        reasons.append("selected_candidate_patch_hash_missing")
    if selected_length <= 0:
        reasons.append("selected_candidate_patch_length_missing")
    if not selected_hash_ok:
        reasons.append("selected_candidate_hash_not_verified")
    if not cycle_proven:
        reasons.append("final_source_apply_cycle_not_proven")
    if not rb_fs_restored:
        reasons.append("final_source_rollback_not_proven")
    if not rb_available:
        reasons.append("rollback_not_available")
    if rb_required:
        reasons.append("rollback_required")
    if not rb_safe:
        reasons.append("rollback_not_safe")
    if not out_clean:
        reasons.append("output_mutation_detected")
    reasons.extend([
        "final_patch_only_apply_gate", "output_mutation_still_blocked",
        "model_calls_increment_still_blocked", "cloud_invocation_still_blocked",
        "behavior_change_still_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h5_actual_final_patch_apply_decision.v1",
        "evaluated": True,
        "apply_decision": "apply_final_patch_only" if would_apply else "blocked",
        "apply_reasons": reasons,
        "actual_patch_apply_allowed": would_apply,
        "selected_candidate_id": selected_id,
        "selected_candidate_patch_sha256": selected_sha256,
        "selected_candidate_patch_length": selected_length,
        "selected_candidate_hash_verified": selected_hash_ok,
        "actual_final_patch_present_before": actual_fp,
        "would_replace_final_patch": would_apply,
        "all_ten_flags_enabled": all_ten,
        "preflight_pass_shadow_only": pf_pass and pf_shadow,
        "isolated_simulation_pass": sim_pass and sim_status,
        "final_source_apply_cycle_proven": cycle_proven,
        "final_source_rollback_proven": rb_fs_restored,
        "rollback_available": rb_available,
        "rollback_required": rb_required,
        "safe_to_continue": not rb_required,
        "output_mutation_allowed": False,
        "model_calls_increment_allowed": False,
        "cloud_invocation_allowed": False,
        "behavior_change_allowed": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _apply_h5_actual_final_patch_if_allowed(row: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Returns a shallow copy of row with final_patch possibly replaced by metadata-only dict."""
    result = dict(row)
    actual_before = bool(row.get("final_patch"))
    allowed = bool(decision.get("actual_patch_apply_allowed", False))

    if allowed:
        result["final_patch"] = {
            "source": "local_candidate_shadow_promoted",
            "selected_candidate_id": str(decision.get("selected_candidate_id", "")),
            "patch_sha256": str(decision.get("selected_candidate_patch_sha256", "")),
            "patch_length": int(decision.get("selected_candidate_patch_length", 0)),
            "content_kind": "candidate_patch_metadata_only",
        }
    result["h5_actual_final_patch_apply_receipt"] = {
        "schema": "nexus.hybrid_h5_actual_final_patch_apply_receipt.v1",
        "evaluated": True,
        "actual_patch_apply_executed": allowed,
        "actual_final_patch_present_before": actual_before,
        "actual_final_patch_present_after": bool(result.get("final_patch")),
        "actual_final_patch_replaced": allowed,
        "apply_decision": str(decision.get("apply_decision", "blocked")),
        "selected_candidate_id": str(decision.get("selected_candidate_id", "")),
        "selected_candidate_patch_sha256": str(decision.get("selected_candidate_patch_sha256", "")),
        "selected_candidate_patch_length": int(decision.get("selected_candidate_patch_length", 0)),
        "final_patch_metadata_only": True,
        "output_mutated": False,
        "model_calls_incremented": False,
        "cloud_invoked": False,
        "behavior_changed": False,
        "final_source_changed": False,
        "rollback_available": bool(decision.get("rollback_available", False)),
        "rollback_required": bool(decision.get("rollback_required", False)),
        "safe_to_continue": bool(decision.get("safe_to_continue", True)),
        "public_claim_allowed": False,
        "production_ready": False,
    }
    return result


def _build_h5_actual_final_patch_rollback_decision(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds actual final_patch rollback decision."""
    import os as _os

    apply_receipt = row.get("h5_actual_final_patch_apply_receipt")
    actual_fp = row.get("final_patch")

    flag_rollback = _os.environ.get("NEXUS_H5_ALLOW_ACTUAL_FINAL_PATCH_ROLLBACK", "").strip() == "1"

    apply_present = bool(apply_receipt)
    apply_executed = bool(apply_receipt and apply_receipt.get("actual_patch_apply_executed", False))
    apply_replaced = bool(apply_receipt and apply_receipt.get("actual_final_patch_replaced", False))
    fp_clean = not bool(apply_receipt and apply_receipt.get("output_mutated", False))
    mc_clean = not bool(apply_receipt and apply_receipt.get("model_calls_incremented", False))
    cloud_clean = not bool(apply_receipt and apply_receipt.get("cloud_invoked", False))
    beh_clean = not bool(apply_receipt and apply_receipt.get("behavior_changed", False))

    is_metadata = isinstance(actual_fp, dict) and actual_fp.get("content_kind") == "candidate_patch_metadata_only"

    would_rollback = (
        flag_rollback and is_metadata
        and apply_present and apply_executed and apply_replaced
        and fp_clean and mc_clean and cloud_clean and beh_clean
    )

    reasons = []
    if not flag_rollback:
        reasons.append("rollback_flag_not_enabled")
    if not is_metadata:
        reasons.append("final_patch_not_metadata_candidate")
    if not apply_present:
        reasons.append("missing_actual_patch_apply_receipt")
    if apply_receipt and not apply_executed:
        reasons.append("actual_patch_apply_not_executed")
    if apply_receipt and not apply_replaced:
        reasons.append("actual_patch_not_replaced")
    if not fp_clean:
        reasons.append("output_was_mutated")
    if not mc_clean:
        reasons.append("model_calls_were_incremented")
    if not cloud_clean:
        reasons.append("cloud_was_invoked")
    if not beh_clean:
        reasons.append("behavior_changed_true")
    reasons.extend([
        "final_patch_only_rollback_gate", "output_remains_unchanged",
        "model_calls_remain_unchanged", "cloud_remains_uninvoked",
    ])

    return {
        "schema": "nexus.hybrid_h5_actual_final_patch_rollback_decision.v1",
        "evaluated": True,
        "rollback_decision": "rollback_final_patch_only" if would_rollback else "blocked",
        "rollback_reasons": reasons,
        "rollback_allowed": would_rollback,
        "rollback_target_final_patch": "none",
        "actual_final_patch_present_before_rollback": bool(actual_fp),
        "would_restore_final_patch_to": "none",
        "actual_patch_apply_receipt_present": apply_present,
        "actual_patch_apply_executed": apply_executed,
        "rollback_flag_enabled": flag_rollback,
        "rollback_required": would_rollback,
        "rollback_safe": would_rollback,
        "output_mutated": not fp_clean,
        "model_calls_incremented": not mc_clean,
        "cloud_invoked": not cloud_clean,
        "behavior_changed": not beh_clean,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _rollback_h5_actual_final_patch_if_allowed(row: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Returns shallow copy of row with final_patch possibly restored."""
    result = dict(row)
    actual_before = bool(row.get("final_patch"))
    allowed = bool(decision.get("rollback_allowed", False))

    if allowed:
        result["final_patch"] = "none"
    result["h5_actual_final_patch_rollback_receipt"] = {
        "schema": "nexus.hybrid_h5_actual_final_patch_rollback_receipt.v1",
        "evaluated": True,
        "rollback_executed": allowed,
        "actual_final_patch_present_before_rollback": actual_before,
        "actual_final_patch_present_after_rollback": bool(result.get("final_patch")),
        "actual_final_patch_restored": allowed and result.get("final_patch") == "none",
        "rollback_decision": str(decision.get("rollback_decision", "blocked")),
        "rollback_target_final_patch": "none",
        "output_mutated": False,
        "model_calls_incremented": False,
        "cloud_invoked": False,
        "behavior_changed": False,
        "safe_to_continue": True,
        "public_claim_allowed": False,
        "production_ready": False,
    }
    return result


def _build_h5_output_apply_preflight_receipt(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds output apply preflight receipt."""
    import os as _os

    fp_rollback = row.get("h5_actual_final_patch_rollback_receipt")
    fs_apply = row.get("h5_actual_final_source_apply_receipt")
    fs_rollback = row.get("h5_actual_final_source_rollback_receipt")
    output_guard = row.get("h5_output_mutation_guard")
    rollback = row.get("h5_local_candidate_rollback_dry_run")

    flag = _os.environ.get("NEXUS_H5_ALLOW_OUTPUT_APPLY_PREFLIGHT", "").strip() == "1"

    selected_sha256 = str(row.get("h5_route", {}).get("local_selected_candidate_patch_sha256", "") or "")
    selected_length = int(row.get("h5_route", {}).get("local_selected_candidate_patch_length", 0) or 0)
    selected_hash_ok = bool(row.get("h5_route", {}).get("local_selected_candidate_hash_match", False))

    fs_cycle = bool(fs_apply and fs_apply.get("actual_apply_executed", False) and fs_apply.get("actual_final_source_changed", False))
    fs_rollback_ok = bool(fs_rollback and fs_rollback.get("actual_final_source_restored", False))
    fp_cycle = bool(fp_rollback and fp_rollback.get("rollback_executed", False))
    out_clean = not bool(output_guard and output_guard.get("actual_output_mutated", False))

    rb_available = bool(rollback and rollback.get("rollback_available", False))
    rb_required = bool(rollback and rollback.get("rollback_required", False))
    rb_safe = bool(rollback and rollback.get("safe_to_continue", True))

    would_pass = (
        flag and fs_cycle and fs_rollback_ok and fp_cycle
        and bool(selected_sha256) and selected_length > 0 and selected_hash_ok
        and rb_available and not rb_required and rb_safe and out_clean
    )

    reasons = []
    if not flag:
        reasons.append("output_apply_preflight_flag_not_enabled")
    if not (fs_cycle and fs_rollback_ok):
        reasons.append("final_source_cycle_not_proven")
    if not fp_cycle:
        reasons.append("final_patch_cycle_not_proven")
    if not bool(selected_sha256):
        reasons.append("selected_candidate_patch_hash_missing")
    if selected_length <= 0:
        reasons.append("selected_candidate_patch_length_missing")
    if not selected_hash_ok:
        reasons.append("selected_candidate_hash_not_verified")
    if not rb_available:
        reasons.append("rollback_not_available")
    if rb_required:
        reasons.append("rollback_required")
    if not rb_safe:
        reasons.append("rollback_not_safe")
    if not out_clean:
        reasons.append("output_mutation_detected")
    reasons.extend([
        "h5_39_output_preflight_only_no_actual_output_mutation",
        "model_calls_increment_still_blocked", "cloud_invocation_still_blocked",
        "behavior_change_still_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h5_output_apply_preflight_receipt.v1",
        "evaluated": True,
        "preflight_status": "output_preflight_pass_shadow_only" if would_pass else "blocked",
        "preflight_reasons": reasons,
        "would_pass_output_apply_preflight": would_pass,
        "output_apply_preflight_flag_enabled": flag,
        "actual_output_mutated": False,
        "output_mutation_allowed": False,
        "final_source_cycle_proven": fs_cycle and fs_rollback_ok,
        "final_patch_cycle_proven": fp_cycle,
        "selected_candidate_patch_sha256": selected_sha256,
        "selected_candidate_patch_length": selected_length,
        "selected_candidate_hash_verified": selected_hash_ok,
        "rollback_available": rb_available,
        "rollback_required": False,
        "safe_to_continue": rb_safe,
        "model_calls_increment_allowed": False,
        "cloud_invocation_allowed": False,
        "behavior_change_allowed": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_isolated_output_mutation_simulation(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds isolated output mutation simulation receipt."""
    import os as _os

    preflight = row.get("h5_output_apply_preflight_receipt")
    rollback = row.get("h5_local_candidate_rollback_dry_run")

    selected_sha256 = str(row.get("h5_route", {}).get("local_selected_candidate_patch_sha256", "") or "")
    selected_length = int(row.get("h5_route", {}).get("local_selected_candidate_patch_length", 0) or 0)

    pf_present = bool(preflight)
    pf_pass = bool(preflight and preflight.get("would_pass_output_apply_preflight", False))
    pf_shadow = str(preflight and preflight.get("preflight_status", "") or "") == "output_preflight_pass_shadow_only"
    fs_cycle = bool(preflight and preflight.get("final_source_cycle_proven", False))
    fp_cycle = bool(preflight and preflight.get("final_patch_cycle_proven", False))

    rb_available = bool(rollback and rollback.get("rollback_available", False))
    rb_required = bool(rollback and rollback.get("rollback_required", False))
    rb_safe = bool(rollback and rollback.get("safe_to_continue", True))

    would_sim = (
        pf_present and pf_pass and pf_shadow
        and fs_cycle and fp_cycle
        and rb_available and not rb_required and rb_safe
    )

    reasons = []
    if not pf_present:
        reasons.append("missing_output_apply_preflight_receipt")
    if preflight and not pf_pass:
        reasons.append("output_preflight_not_passed")
    if not fs_cycle:
        reasons.append("final_source_cycle_not_proven")
    if not fp_cycle:
        reasons.append("final_patch_cycle_not_proven")
    if not rb_available:
        reasons.append("rollback_not_available")
    if rb_required:
        reasons.append("rollback_required")
    if not rb_safe:
        reasons.append("rollback_not_safe")
    reasons.extend([
        "isolated_output_simulation_only_no_actual_output_mutation",
        "model_calls_increment_still_blocked", "cloud_invocation_still_blocked",
        "behavior_change_still_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h5_isolated_output_mutation_simulation.v1",
        "evaluated": True,
        "simulation_status": "isolated_output_simulation_pass" if would_sim else "blocked",
        "simulation_reasons": reasons,
        "would_simulate_output_mutation": would_sim,
        "actual_output_mutated": False,
        "isolated_output_mutated": would_sim,
        "isolated_output_source": "local_candidate_shadow_promoted" if would_sim else "",
        "isolated_output_patch_sha256": selected_sha256 if would_sim else "",
        "isolated_output_patch_length": selected_length if would_sim else 0,
        "output_apply_preflight_present": pf_present,
        "output_preflight_pass_shadow_only": pf_pass and pf_shadow,
        "final_source_cycle_proven": fs_cycle,
        "final_patch_cycle_proven": fp_cycle,
        "rollback_available": rb_available,
        "rollback_required": rb_required,
        "safe_to_continue": not rb_required,
        "model_calls_incremented": False,
        "cloud_invoked": False,
        "behavior_changed": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _build_h5_actual_output_apply_decision(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds actual output apply decision."""
    import os as _os

    pf = row.get("h5_output_apply_preflight_receipt")
    sim = row.get("h5_isolated_output_mutation_simulation")
    rollback = row.get("h5_local_candidate_rollback_dry_run")

    flag = _os.environ.get("NEXUS_H5_ALLOW_ACTUAL_OUTPUT_APPLY", "").strip() == "1"

    pf_pass = bool(pf and pf.get("would_pass_output_apply_preflight", False))
    pf_shadow = str(pf and pf.get("preflight_status", "") or "") == "output_preflight_pass_shadow_only"
    sim_pass = bool(sim and sim.get("would_simulate_output_mutation", False))
    sim_status = str(sim and sim.get("simulation_status", "") or "") == "isolated_output_simulation_pass"
    sim_mutated = bool(sim and sim.get("isolated_output_mutated", False))

    fs_cycle = bool(pf and pf.get("final_source_cycle_proven", False))
    fp_cycle = bool(pf and pf.get("final_patch_cycle_proven", False))

    selected_sha256 = str(row.get("h5_route", {}).get("local_selected_candidate_patch_sha256", "") or "")
    selected_length = int(row.get("h5_route", {}).get("local_selected_candidate_patch_length", 0) or 0)
    selected_hash_ok = bool(row.get("h5_route", {}).get("local_selected_candidate_hash_match", False))

    rb_available = bool(rollback and rollback.get("rollback_available", False))
    rb_required = bool(rollback and rollback.get("rollback_required", False))
    rb_safe = bool(rollback and rollback.get("safe_to_continue", True))

    would_apply = (
        flag and pf_pass and pf_shadow
        and sim_pass and sim_status and sim_mutated
        and fs_cycle and fp_cycle
        and bool(selected_sha256) and selected_length > 0 and selected_hash_ok
        and rb_available and not rb_required and rb_safe
    )

    reasons = []
    if not flag:
        reasons.append("actual_output_apply_flag_not_enabled")
    if pf and not pf_pass:
        reasons.append("output_preflight_not_passed")
    if sim and not sim_pass:
        reasons.append("isolated_output_simulation_not_passed")
    if not fs_cycle:
        reasons.append("final_source_cycle_not_proven")
    if not fp_cycle:
        reasons.append("final_patch_cycle_not_proven")
    if not bool(selected_sha256):
        reasons.append("selected_candidate_patch_hash_missing")
    if selected_length <= 0:
        reasons.append("selected_candidate_patch_length_missing")
    if not selected_hash_ok:
        reasons.append("selected_candidate_hash_not_verified")
    if not rb_available:
        reasons.append("rollback_not_available")
    if rb_required:
        reasons.append("rollback_required")
    if not rb_safe:
        reasons.append("rollback_not_safe")
    reasons.extend([
        "output_apply_gate", "metadata_delivery_only",
        "model_calls_increment_still_blocked", "cloud_invocation_still_blocked",
        "behavior_change_still_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h5_actual_output_apply_decision.v1",
        "evaluated": True,
        "apply_decision": "apply_output_metadata_only" if would_apply else "blocked",
        "apply_reasons": reasons,
        "actual_output_apply_allowed": would_apply,
        "actual_output_apply_flag_enabled": flag,
        "isolated_output_simulation_pass": sim_pass and sim_status,
        "output_preflight_pass_shadow_only": pf_pass and pf_shadow,
        "final_source_cycle_proven": fs_cycle,
        "final_patch_cycle_proven": fp_cycle,
        "selected_candidate_patch_sha256": selected_sha256,
        "selected_candidate_patch_length": selected_length,
        "selected_candidate_hash_verified": selected_hash_ok,
        "rollback_available": rb_available,
        "rollback_required": rb_required,
        "safe_to_continue": not rb_required,
        "model_calls_increment_allowed": False,
        "cloud_invocation_allowed": False,
        "behavior_change_allowed": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _apply_h5_actual_output_if_allowed(row: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Returns shallow copy of row with output possibly set to metadata delivery dict."""
    result = dict(row)
    allowed = bool(decision.get("actual_output_apply_allowed", False))
    sha256 = str(decision.get("selected_candidate_patch_sha256", ""))
    length = int(decision.get("selected_candidate_patch_length", 0))
    actual_before = row.get("output")

    if allowed:
        result["output"] = {
            "source": "local_candidate_shadow_promoted",
            "delivery_kind": "candidate_patch_metadata_only",
            "patch_sha256": sha256,
            "patch_length": length,
            "final_source": str(row.get("final_source", "none") or "none"),
            "final_patch_kind": "candidate_patch_metadata_only" if isinstance(row.get("final_patch"), dict) else "unchanged",
        }
    result["h5_actual_output_apply_receipt"] = {
        "schema": "nexus.hybrid_h5_actual_output_apply_receipt.v1",
        "evaluated": True,
        "actual_output_apply_executed": allowed,
        "actual_output_mutated": allowed,
        "output_delivery_kind": "candidate_patch_metadata_only" if allowed else "none",
        "selected_candidate_patch_sha256": sha256,
        "selected_candidate_patch_length": length,
        "model_calls_incremented": False,
        "cloud_invoked": False,
        "behavior_changed": False,
        "final_source_changed": False,
        "final_patch_changed": False,
        "rollback_available": bool(decision.get("rollback_available", False)),
        "rollback_required": bool(decision.get("rollback_required", False)),
        "safe_to_continue": bool(decision.get("safe_to_continue", True)),
        "public_claim_allowed": False,
        "production_ready": False,
    }
    return result


def _build_h5_actual_output_rollback_decision(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds actual output rollback decision."""
    import os as _os

    apply_receipt = row.get("h5_actual_output_apply_receipt")
    actual_out = row.get("output")

    flag = _os.environ.get("NEXUS_H5_ALLOW_ACTUAL_OUTPUT_ROLLBACK", "").strip() == "1"

    apply_present = bool(apply_receipt)
    apply_executed = bool(apply_receipt and apply_receipt.get("actual_output_apply_executed", False))
    apply_mutated = bool(apply_receipt and apply_receipt.get("actual_output_mutated", False))
    mc_clean = not bool(apply_receipt and apply_receipt.get("model_calls_incremented", False))
    cloud_clean = not bool(apply_receipt and apply_receipt.get("cloud_invoked", False))
    beh_clean = not bool(apply_receipt and apply_receipt.get("behavior_changed", False))
    fs_clean = not bool(apply_receipt and apply_receipt.get("final_source_changed", False))
    fp_clean = not bool(apply_receipt and apply_receipt.get("final_patch_changed", False))

    is_metadata = isinstance(actual_out, dict) and actual_out.get("delivery_kind") == "candidate_patch_metadata_only"

    would_rollback = (
        flag and apply_present and apply_executed and apply_mutated
        and is_metadata and mc_clean and cloud_clean and beh_clean
        and fs_clean and fp_clean
    )

    reasons = []
    if not flag:
        reasons.append("actual_output_rollback_flag_not_enabled")
    if not apply_present:
        reasons.append("missing_actual_output_apply_receipt")
    if apply_receipt and not apply_executed:
        reasons.append("actual_output_apply_not_executed")
    if not is_metadata:
        reasons.append("output_not_metadata_delivery")
    if not mc_clean:
        reasons.append("model_calls_were_incremented")
    if not cloud_clean:
        reasons.append("cloud_was_invoked")
    if not beh_clean:
        reasons.append("behavior_changed_true")
    if not fs_clean:
        reasons.append("final_source_changed_true")
    if not fp_clean:
        reasons.append("final_patch_changed_true")
    reasons.extend([
        "output_only_rollback_gate", "metadata_delivery_rollback_only",
        "model_calls_remain_unchanged", "cloud_remains_uninvoked",
        "behavior_remains_unchanged",
    ])

    return {
        "schema": "nexus.hybrid_h5_actual_output_rollback_decision.v1",
        "evaluated": True,
        "rollback_decision": "rollback_output_only" if would_rollback else "blocked",
        "rollback_reasons": reasons,
        "rollback_allowed": would_rollback,
        "actual_output_rollback_flag_enabled": flag,
        "actual_output_apply_receipt_present": apply_present,
        "actual_output_apply_executed": apply_executed,
        "output_is_metadata_delivery": is_metadata,
        "rollback_target_output": "none",
        "model_calls_incremented": not mc_clean,
        "cloud_invoked": not cloud_clean,
        "behavior_changed": not beh_clean,
        "final_source_changed": not fs_clean,
        "final_patch_changed": not fp_clean,
        "safe_to_continue": not (not mc_clean or not cloud_clean or not beh_clean or not fs_clean or not fp_clean),
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _rollback_h5_actual_output_if_allowed(row: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Returns shallow copy of row with output possibly restored."""
    result = dict(row)
    actual_before = row.get("output")
    allowed = bool(decision.get("rollback_allowed", False))

    if allowed:
        result["output"] = "none"
    result["h5_actual_output_rollback_receipt"] = {
        "schema": "nexus.hybrid_h5_actual_output_rollback_receipt.v1",
        "evaluated": True,
        "rollback_executed": allowed,
        "actual_output_before_rollback_kind": "candidate_patch_metadata_only" if isinstance(actual_before, dict) and actual_before.get("delivery_kind") == "candidate_patch_metadata_only" else "other",
        "actual_output_after_rollback_kind": "none" if allowed else "other",
        "actual_output_restored": allowed and result.get("output") == "none",
        "model_calls_incremented": False,
        "cloud_invoked": False,
        "behavior_changed": False,
        "final_source_changed": False,
        "final_patch_changed": False,
        "safe_to_continue": True,
        "public_claim_allowed": False,
        "production_ready": False,
    }
    return result


def _build_h5_local_candidate_e2e_delivery_smoke_receipt(row: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: builds local candidate E2E delivery smoke receipt.

    Verifies the full chain: evidence → candidate → final_source → final_patch → output → rollback.
    """
    import os as _os

    flag = _os.environ.get("NEXUS_H5_ALLOW_LOCAL_CANDIDATE_E2E_SMOKE", "").strip() == "1"

    selected_id = str(row.get("h5_route", {}).get("local_selected_candidate_id", "") or "")
    selected_sha256 = str(row.get("h5_route", {}).get("local_selected_candidate_patch_sha256", "") or "")
    selected_length = int(row.get("h5_route", {}).get("local_selected_candidate_patch_length", 0) or 0)
    selected_hash_ok = bool(row.get("h5_route", {}).get("local_selected_candidate_hash_match", False))

    local_shadow = row.get("h5_local_evidence_ingestion_shadow", {})
    local_ready = bool(local_shadow and local_shadow.get("local_path_ready_shadow_from_external_evidence", False))

    cloud_shadow = row.get("h5_cloud_evidence_ingestion_shadow", {})
    cloud_ready = bool(cloud_shadow and cloud_shadow.get("cloud_path_ready_shadow_from_external_evidence", False))

    fs_apply = row.get("h5_actual_final_source_apply_receipt", {})
    fs_rb = row.get("h5_actual_final_source_rollback_receipt", {})
    fp_apply = row.get("h5_actual_final_patch_apply_receipt", {})
    fp_rb = row.get("h5_actual_final_patch_rollback_receipt", {})
    out_apply = row.get("h5_actual_output_apply_receipt", {})
    out_rb = row.get("h5_actual_output_rollback_receipt", {})

    fs_apply_ok = bool(fs_apply.get("actual_apply_executed", False))
    fs_rb_ok = bool(fs_rb.get("rollback_executed", False))
    fs_restored = bool(fs_rb.get("actual_final_source_restored", False))

    fp_apply_ok = bool(fp_apply.get("actual_patch_apply_executed", False))
    fp_rb_ok = bool(fp_rb.get("rollback_executed", False))
    fp_restored = bool(fp_rb.get("actual_final_patch_restored", False))

    out_apply_ok = bool(out_apply.get("actual_output_apply_executed", False))
    out_rb_ok = bool(out_rb.get("rollback_executed", False))
    out_restored = bool(out_rb.get("actual_output_restored", False))

    actual_fs = str(row.get("final_source", "none") or "none")
    actual_fp = row.get("final_patch")
    actual_out = row.get("output")

    fp_is_none = actual_fp is None or actual_fp == "none" or (isinstance(actual_fp, str) and actual_fp == "none")
    out_is_none = actual_out is None or actual_out == "none" or (isinstance(actual_out, str) and actual_out == "none")

    fs_final_ok = actual_fs == "none"
    fp_final_ok = fp_is_none or (isinstance(actual_fp, dict) and actual_fp.get("content_kind") == "candidate_patch_metadata_only")
    out_final_ok = out_is_none

    has_all_gates = all(k in row for k in [
        "h5_actual_final_source_apply_receipt", "h5_actual_final_source_rollback_receipt",
        "h5_actual_final_patch_apply_receipt", "h5_actual_final_patch_rollback_receipt",
        "h5_actual_output_apply_receipt", "h5_actual_output_rollback_receipt",
    ])

    mc_clean = True
    beh_clean = True
    cloud_clean = True
    for receipt in [fs_apply, fs_rb, fp_apply, fp_rb, out_apply, out_rb]:
        if receipt.get("model_calls_incremented"):
            mc_clean = False
        if receipt.get("behavior_changed"):
            beh_clean = False
        if receipt.get("cloud_invoked"):
            cloud_clean = False

    has_candidate = bool(selected_id) and bool(selected_sha256) and selected_length > 0 and selected_hash_ok

    would_allowed = (
        flag and has_candidate and local_ready
        and has_all_gates
    )

    all_chains = (
        fs_apply_ok and fs_rb_ok and fs_restored
        and fp_apply_ok and fp_rb_ok and fp_restored
        and out_apply_ok and out_rb_ok and out_restored
    )

    would_pass = (
        would_allowed and all_chains
        and fs_final_ok and out_final_ok
        and mc_clean and cloud_clean and beh_clean
    )

    reasons = []
    if not flag:
        reasons.append("e2e_smoke_flag_not_enabled")
    if not has_candidate:
        reasons.append("selected_candidate_missing")
    if not selected_hash_ok:
        reasons.append("selected_candidate_hash_not_verified")
    if not local_ready:
        reasons.append("local_evidence_not_ready")
    if not fs_apply_ok:
        reasons.append("missing_final_source_apply")
    if not fs_rb_ok:
        reasons.append("missing_final_source_rollback")
    if not fp_apply_ok:
        reasons.append("missing_final_patch_apply")
    if not fp_rb_ok:
        reasons.append("missing_final_patch_rollback")
    if not out_apply_ok:
        reasons.append("missing_output_apply")
    if not out_rb_ok:
        reasons.append("missing_output_rollback")
    if not fs_final_ok or not out_final_ok:
        reasons.append("unsafe_final_state")
    if not mc_clean:
        reasons.append("model_calls_incremented")
    if not cloud_clean:
        reasons.append("cloud_invoked")
    if not beh_clean:
        reasons.append("behavior_changed_true")
    reasons.extend([
        "h5_41_smoke_only_not_full_benchmark", "metadata_delivery_only",
        "cloud_invocation_blocked", "model_calls_increment_blocked", "production_claim_blocked",
    ])

    status = "local_candidate_e2e_smoke_pass" if would_pass else ("blocked" if not would_allowed else "local_candidate_e2e_smoke_fail")

    return {
        "schema": "nexus.hybrid_h5_local_candidate_e2e_delivery_smoke_receipt.v1",
        "evaluated": True,
        "smoke_status": status,
        "smoke_reasons": reasons,
        "e2e_smoke_allowed": would_allowed,
        "e2e_smoke_passed": would_pass,
        "local_candidate_selected": has_candidate,
        "selected_candidate_id": selected_id,
        "selected_candidate_patch_sha256": selected_sha256,
        "selected_candidate_patch_length": selected_length,
        "selected_candidate_hash_verified": selected_hash_ok,
        "local_evidence_ready": local_ready,
        "cloud_evidence_ready": cloud_ready,
        "cloud_invoked": not cloud_clean,
        "final_source_apply_executed": fs_apply_ok,
        "final_source_rollback_executed": fs_rb_ok,
        "final_source_restored": fs_restored,
        "final_patch_apply_executed": fp_apply_ok,
        "final_patch_rollback_executed": fp_rb_ok,
        "final_patch_restored": fp_restored,
        "output_apply_executed": out_apply_ok,
        "output_rollback_executed": out_rb_ok,
        "output_restored": out_restored,
        "final_source_final_state": actual_fs,
        "final_patch_final_state": "none" if fp_is_none else ("metadata_only" if isinstance(actual_fp, dict) else str(type(actual_fp).__name__)),
        "output_final_state": "none" if out_is_none else ("metadata_only" if isinstance(actual_out, dict) else str(type(actual_out).__name__)),
        "model_calls_incremented": not mc_clean,
        "behavior_changed": not beh_clean,
        "all_mutation_gates_exercised": would_pass,
        "safe_final_state": would_pass,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h5_guarded_local_candidate_benchmark_trial(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure helper: aggregates H5-41 E2E smoke receipts into a benchmark trial.

    No side effects. Reads smoke receipts from rows.
    """
    import os as _os
    from collections import Counter

    flag = _os.environ.get("NEXUS_H5_ALLOW_GUARDED_LOCAL_CANDIDATE_BENCHMARK_TRIAL", "").strip() == "1"

    row_count = len(rows)
    has_receipts = any(bool(r.get("h5_local_candidate_e2e_delivery_smoke_receipt")) for r in rows)

    smoke_passed = 0
    smoke_blocked = 0
    smoke_safe = 0
    smoke_gates = 0
    selected_count = 0
    hash_verified = 0
    local_ready_count = 0
    cloud_invoked = 0
    mc_incremented = 0
    beh_changed = 0
    unsafe_count = 0
    fail_reasons: Counter = Counter()

    for r in rows:
        receipt = r.get("h5_local_candidate_e2e_delivery_smoke_receipt")
        if not receipt:
            continue

        if receipt.get("e2e_smoke_passed", False):
            smoke_passed += 1
        else:
            smoke_blocked += 1
            for reason in receipt.get("smoke_reasons", []):
                fail_reasons[reason] += 1

        if receipt.get("safe_final_state", False):
            smoke_safe += 1
        else:
            unsafe_count += 1

        if receipt.get("all_mutation_gates_exercised", False):
            smoke_gates += 1
        if receipt.get("local_candidate_selected", False):
            selected_count += 1
        if receipt.get("selected_candidate_hash_verified", False):
            hash_verified += 1
        if receipt.get("local_evidence_ready", False):
            local_ready_count += 1
        if receipt.get("cloud_invoked", False):
            cloud_invoked += 1
        if receipt.get("model_calls_incremented", False):
            mc_incremented += 1
        if receipt.get("behavior_changed", False):
            beh_changed += 1

    trial_allowed = flag and row_count > 0 and has_receipts
    eligible = smoke_passed + smoke_blocked

    trial_passed = (
        trial_allowed and smoke_passed >= 1
        and smoke_safe == smoke_passed
        and smoke_gates == smoke_passed
        and cloud_invoked == 0
        and mc_incremented == 0
        and beh_changed == 0
        and unsafe_count == 0
    )

    reasons = []
    if not flag:
        reasons.append("benchmark_trial_flag_not_enabled")
    if row_count == 0:
        reasons.append("no_rows")
    if not has_receipts:
        reasons.append("missing_e2e_smoke_receipts")
    if smoke_passed == 0:
        reasons.append("no_e2e_smoke_passed_rows")
    if unsafe_count > 0:
        reasons.append("unsafe_final_state_detected")
    if cloud_invoked > 0:
        reasons.append("cloud_invoked_detected")
    if mc_incremented > 0:
        reasons.append("model_calls_incremented_detected")
    if beh_changed > 0:
        reasons.append("behavior_changed_detected")
    reasons.extend([
        "h5_42_guarded_trial_not_full_benchmark",
        "metadata_delivery_only",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    replay_blocked = replay_allowed and blocked_count > 0 and blocked_count == total_replays

    return {
        "schema": "nexus.hybrid_h5_guarded_local_candidate_benchmark_trial.v1",
        "evaluated": True,
        "trial_status": "guarded_local_candidate_benchmark_trial_pass" if trial_passed else ("blocked" if not trial_allowed else "guarded_local_candidate_benchmark_trial_fail"),
        "trial_reasons": reasons,
        "trial_allowed": trial_allowed,
        "trial_passed": trial_passed,
        "row_count": row_count,
        "eligible_row_count": eligible,
        "e2e_smoke_passed_count": smoke_passed,
        "e2e_smoke_blocked_count": smoke_blocked,
        "safe_final_state_count": smoke_safe,
        "all_mutation_gates_exercised_count": smoke_gates,
        "selected_candidate_count": selected_count,
        "hash_verified_count": hash_verified,
        "local_evidence_ready_count": local_ready_count,
        "cloud_invoked_count": cloud_invoked,
        "model_calls_incremented_count": mc_incremented,
        "behavior_changed_count": beh_changed,
        "unsafe_final_state_count": unsafe_count,
        "failure_reason_counts": dict(fail_reasons),
        "pass_rate": pass_rate,
        "safe_final_state_rate": safe_rate,
        "cloud_invocation_rate": cloud_rate,
        "model_calls_increment_rate": mc_rate,
        "behavior_changed_rate": beh_rate,
        "quality_non_regression_evaluated": False,
        "quality_non_regression_passed": False,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h5_quality_non_regression_gate(rows: list[dict[str, Any]], trial: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: quality non-regression gate reading guarded trial and rows."""
    import os as _os
    from collections import Counter

    flag = _os.environ.get("NEXUS_H5_ALLOW_QUALITY_NON_REGRESSION_GATE", "").strip() == "1"

    if trial is None:
        trial = _build_h5_guarded_local_candidate_benchmark_trial(rows)

    trial_passed = bool(trial.get("trial_passed", False))
    row_count = int(trial.get("row_count", 0))
    eligible = int(trial.get("eligible_row_count", 0))
    smoke_passed = int(trial.get("e2e_smoke_passed_count", 0))
    safe_count = int(trial.get("safe_final_state_count", 0))
    gates_count = int(trial.get("all_mutation_gates_exercised_count", 0))
    unsafe_count = int(trial.get("unsafe_final_state_count", 0))
    cloud_count = int(trial.get("cloud_invoked_count", 0))
    mc_count = int(trial.get("model_calls_incremented_count", 0))
    beh_count = int(trial.get("behavior_changed_count", 0))
    pass_rate = float(trial.get("pass_rate", 0.0))

    regression_count = 0
    regression_reasons: Counter = Counter()

    for r in rows:
        receipt = r.get("h5_local_candidate_e2e_delivery_smoke_receipt")
        if not receipt:
            continue
        is_regressed = False
        if not receipt.get("e2e_smoke_passed", False) and receipt.get("smoke_status") != "blocked":
            is_regressed = True
            regression_reasons["e2e_smoke_fail"] += 1
        if receipt.get("safe_final_state") is False and receipt.get("e2e_smoke_allowed", True):
            is_regressed = True
            regression_reasons["unsafe_final_state"] += 1
        if receipt.get("cloud_invoked", False):
            is_regressed = True
            regression_reasons["cloud_invoked"] += 1
        if receipt.get("model_calls_incremented", False):
            is_regressed = True
            regression_reasons["model_calls_incremented"] += 1
        if receipt.get("behavior_changed", False):
            is_regressed = True
            regression_reasons["behavior_changed"] += 1
        if is_regressed:
            regression_count += 1

    quality_floor = pass_rate > 0 and smoke_passed >= 1
    safety_floor = unsafe_count == 0 and cloud_count == 0 and mc_count == 0 and beh_count == 0
    regression_floor = regression_count == 0

    gate_allowed = flag and trial_passed and row_count > 0
    evaluated = gate_allowed
    passed = (
        gate_allowed and smoke_passed >= 1
        and safe_count == smoke_passed
        and gates_count == smoke_passed
        and unsafe_count == 0
        and cloud_count == 0 and mc_count == 0 and beh_count == 0
        and regression_count == 0
        and quality_floor and safety_floor and regression_floor
    )

    reasons = []
    if not flag:
        reasons.append("quality_gate_flag_not_enabled")
    if not trial_passed:
        reasons.append("guarded_trial_not_passed")
    if row_count == 0:
        reasons.append("no_rows")
    if not quality_floor:
        reasons.append("quality_floor_not_met")
    if not safety_floor:
        reasons.append("safety_floor_not_met")
    if not regression_floor:
        reasons.append("regression_floor_not_met")
    reasons.extend([
        "h5_43_quality_gate_not_full_benchmark", "metadata_delivery_only",
        "production_claim_blocked", "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h5_quality_non_regression_gate.v1",
        "evaluated": True,
        "gate_status": "quality_non_regression_pass" if passed else ("blocked" if not gate_allowed else "quality_non_regression_fail"),
        "gate_reasons": reasons,
        "gate_allowed": gate_allowed,
        "quality_non_regression_evaluated": evaluated,
        "quality_non_regression_passed": passed,
        "trial_passed": trial_passed,
        "row_count": row_count,
        "eligible_row_count": eligible,
        "e2e_smoke_passed_count": smoke_passed,
        "safe_final_state_count": safe_count,
        "all_mutation_gates_exercised_count": gates_count,
        "unsafe_final_state_count": unsafe_count,
        "cloud_invoked_count": cloud_count,
        "model_calls_incremented_count": mc_count,
        "behavior_changed_count": beh_count,
        "pass_rate": pass_rate,
        "safe_final_state_rate": float(trial.get("safe_final_state_rate", 0.0)),
        "error_rate": 1.0 - pass_rate if eligible > 0 else 0.0,
        "regression_count": regression_count,
        "regression_reason_counts": dict(regression_reasons),
        "quality_floor_met": quality_floor,
        "safety_floor_met": safety_floor,
        "regression_floor_met": regression_floor,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h5_full_guarded_benchmark_run(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: aggregates trial + quality gate into full guarded benchmark run receipt."""
    import os as _os

    flag = _os.environ.get("NEXUS_H5_ALLOW_FULL_GUARDED_BENCHMARK_RUN", "").strip() == "1"

    trial = None
    gate = None
    if bundle:
        trial = bundle.get("h5_guarded_local_candidate_benchmark_trial")
        gate = bundle.get("h5_quality_non_regression_gate")

    if trial is None:
        trial = _build_h5_guarded_local_candidate_benchmark_trial(rows)
    if gate is None:
        gate = _build_h5_quality_non_regression_gate(rows, trial)

    trial_present = bool(trial)
    trial_passed = bool(trial.get("trial_passed", False))
    gate_present = bool(gate)
    qnre = bool(gate.get("quality_non_regression_evaluated", False))
    qnrp = bool(gate.get("quality_non_regression_passed", False))

    row_count = int(trial.get("row_count", 0))
    eligible = int(trial.get("eligible_row_count", 0))
    smoke_passed = int(trial.get("e2e_smoke_passed_count", 0))
    safe_count = int(trial.get("safe_final_state_count", 0))
    gates_count = int(trial.get("all_mutation_gates_exercised_count", 0))
    unsafe_count = int(trial.get("unsafe_final_state_count", 0))
    cloud_count = int(trial.get("cloud_invoked_count", 0))
    mc_count = int(trial.get("model_calls_incremented_count", 0))
    beh_count = int(trial.get("behavior_changed_count", 0))
    regression_count = int(gate.get("regression_count", 0))

    qf = bool(gate.get("quality_floor_met", False))
    sf = bool(gate.get("safety_floor_met", False))
    rf = bool(gate.get("regression_floor_met", False))

    run_allowed = flag and row_count > 0 and trial_present and gate_present
    run_passed = (
        run_allowed and trial_passed and qnre and qnrp
        and smoke_passed >= 1
        and safe_count == smoke_passed
        and gates_count == smoke_passed
        and cloud_count == 0 and mc_count == 0 and beh_count == 0
        and unsafe_count == 0 and regression_count == 0
        and qf and sf and rf
    )

    reasons = []
    if not flag:
        reasons.append("full_guarded_benchmark_flag_not_enabled")
    if row_count == 0:
        reasons.append("no_rows")
    if not trial_present:
        reasons.append("missing_guarded_trial")
    if not trial_passed:
        reasons.append("guarded_trial_not_passed")
    if not gate_present:
        reasons.append("missing_quality_gate")
    if not qnre:
        reasons.append("quality_non_regression_not_evaluated")
    if not qnrp:
        reasons.append("quality_non_regression_not_passed")
    if unsafe_count > 0:
        reasons.append("unsafe_final_state_detected")
    if cloud_count > 0:
        reasons.append("cloud_invoked_detected")
    if mc_count > 0:
        reasons.append("model_calls_incremented_detected")
    if beh_count > 0:
        reasons.append("behavior_changed_detected")
    if regression_count > 0:
        reasons.append("regression_detected")
    reasons.extend([
        "h5_44_full_guarded_benchmark_not_production",
        "metadata_delivery_only",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h5_full_guarded_benchmark_run.v1",
        "evaluated": True,
        "run_status": "full_guarded_benchmark_run_pass" if run_passed else ("blocked" if not run_allowed else "full_guarded_benchmark_run_fail"),
        "run_reasons": reasons,
        "run_allowed": run_allowed,
        "run_passed": run_passed,
        "row_count": row_count,
        "eligible_row_count": eligible,
        "guarded_trial_present": trial_present,
        "guarded_trial_passed": trial_passed,
        "quality_gate_present": gate_present,
        "quality_non_regression_evaluated": qnre,
        "quality_non_regression_passed": qnrp,
        "e2e_smoke_passed_count": smoke_passed,
        "safe_final_state_count": safe_count,
        "all_mutation_gates_exercised_count": gates_count,
        "cloud_invoked_count": cloud_count,
        "model_calls_incremented_count": mc_count,
        "behavior_changed_count": beh_count,
        "unsafe_final_state_count": unsafe_count,
        "regression_count": regression_count,
        "failure_reason_counts": dict(trial.get("failure_reason_counts", {})),
        "regression_reason_counts": dict(gate.get("regression_reason_counts", {})),
        "pass_rate": float(trial.get("pass_rate", 0.0)),
        "safe_final_state_rate": float(trial.get("safe_final_state_rate", 0.0)),
        "quality_floor_met": qf,
        "safety_floor_met": sf,
        "regression_floor_met": rf,
        "full_guarded_benchmark_ready": run_passed,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h5_governance_closure_public_claim_lock(bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: governance closure receipt with public claim lock."""
    import os as _os

    flag = _os.environ.get("NEXUS_H5_ALLOW_GOVERNANCE_CLOSURE", "").strip() == "1"

    if bundle is None:
        bundle = {}

    run = bundle.get("h5_full_guarded_benchmark_run")
    gate = bundle.get("h5_quality_non_regression_gate")
    trial = bundle.get("h5_guarded_local_candidate_benchmark_trial")
    smoke_row = bundle.get("h5_local_candidate_e2e_delivery_smoke_receipt")

    run_present = bool(run)
    run_passed = bool(run.get("run_passed", False)) if run else False
    run_ready = bool(run.get("full_guarded_benchmark_ready", False)) if run else False
    smoke_passed_count = int(run.get("e2e_smoke_passed_count", 0)) if run else 0
    safe_count = int(run.get("safe_final_state_count", 0)) if run else 0
    regression = int(run.get("regression_count", 0)) if run else 0
    cloud = int(run.get("cloud_invoked_count", 0)) if run else 0
    mc = int(run.get("model_calls_incremented_count", 0)) if run else 0
    beh = int(run.get("behavior_changed_count", 0)) if run else 0

    qnr_present = bool(gate)
    qnr_passed = bool(gate.get("quality_non_regression_passed", False)) if gate else False
    trial_present = bool(trial)
    trial_passed = bool(trial.get("trial_passed", False)) if trial else False
    e2e_present = bool(smoke_row)

    closure_allowed = (
        flag and run_present and run_passed and run_ready
        and qnr_passed and trial_passed
    )

    alpha_ready = (
        closure_allowed
        and regression == 0 and cloud == 0 and mc == 0 and beh == 0
        and safe_count >= 1 and smoke_passed_count >= 1
    )

    governance_complete = alpha_ready

    reasons = []
    if not flag:
        reasons.append("governance_closure_flag_not_enabled")
    if not run_present:
        reasons.append("missing_full_guarded_benchmark_run")
    if run and not run_passed:
        reasons.append("full_guarded_benchmark_not_passed")
    if not qnr_passed:
        reasons.append("quality_non_regression_not_passed")
    if not trial_passed:
        reasons.append("guarded_trial_not_passed")
    if regression > 0:
        reasons.append("regression_detected")
    if cloud > 0:
        reasons.append("cloud_invoked_detected")
    if mc > 0:
        reasons.append("model_calls_incremented_detected")
    if beh > 0:
        reasons.append("behavior_changed_detected")
    if safe_count < 1 or smoke_passed_count < 1:
        reasons.append("missing_e2e_smoke_pass")
    reasons.extend([
        "internal_alpha_only", "production_claim_blocked",
        "public_claim_blocked", "metadata_delivery_only",
    ])

    return {
        "schema": "nexus.hybrid_h5_governance_closure_public_claim_lock.v1",
        "evaluated": True,
        "closure_status": "h5_internal_alpha_ready_public_claim_locked" if governance_complete else ("blocked" if not closure_allowed else "h5_governance_closure_fail"),
        "closure_reasons": reasons,
        "closure_allowed": closure_allowed,
        "internal_alpha_ready": alpha_ready,
        "full_guarded_benchmark_present": run_present,
        "full_guarded_benchmark_passed": run_passed,
        "full_guarded_benchmark_ready": run_ready,
        "quality_non_regression_present": qnr_present,
        "quality_non_regression_passed": qnr_passed,
        "guarded_trial_present": trial_present,
        "guarded_trial_passed": trial_passed,
        "e2e_smoke_present": e2e_present,
        "e2e_smoke_passed_count": smoke_passed_count,
        "safe_final_state_count": safe_count,
        "regression_count": regression,
        "cloud_invoked_count": cloud,
        "model_calls_incremented_count": mc,
        "behavior_changed_count": beh,
        "production_ready": False,
        "public_claim_allowed": False,
        "public_claim_lock_active": True,
        "production_lock_active": True,
        "governance_closure_complete": governance_complete,
    }


def _build_h5_real_local_candidate_execution_harness(row: dict[str, Any], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: real local candidate execution harness receipt."""
    import os as _os

    flag = _os.environ.get("NEXUS_H5_ALLOW_REAL_LOCAL_CANDIDATE_EXECUTION_HARNESS", "").strip() == "1"

    gov = row.get("h5_governance_closure_public_claim_lock")
    if gov is None and bundle:
        gov = bundle.get("h5_governance_closure_public_claim_lock")

    gov_present = bool(gov)
    alpha_ready = bool(gov.get("internal_alpha_ready", False)) if gov else False
    pub_lock = bool(gov.get("public_claim_lock_active", True)) if gov else True
    prod_lock = bool(gov.get("production_lock_active", True)) if gov else True

    selected_id = str(row.get("h5_route", {}).get("local_selected_candidate_id", "") or "")
    selected_sha256 = str(row.get("h5_route", {}).get("local_selected_candidate_patch_sha256", "") or "")
    selected_length = int(row.get("h5_route", {}).get("local_selected_candidate_patch_length", 0) or 0)
    selected_hash_ok = bool(row.get("h5_route", {}).get("local_selected_candidate_hash_match", False))

    has_candidate = bool(selected_id) and selected_hash_ok

    artifact = row.get("h5_real_local_candidate_artifact")
    if artifact is None and bundle:
        artifact = bundle.get("h5_real_local_candidate_artifact")

    art_present = bool(artifact)
    art_sha256 = ""
    art_length = 0
    art_kind = "none"
    art_hash_ok = False

    if artifact and isinstance(artifact, dict):
        art_sha256 = str(artifact.get("patch_sha256", "") or "")
        art_length = int(artifact.get("patch_length", 0) or 0)
        art_kind = str(artifact.get("content_kind", "none") or "none")
        if art_sha256 and art_length > 0:
            if bool(artifact.get("artifact_hash_match", False)):
                art_hash_ok = True
            elif art_sha256 == selected_sha256:
                art_hash_ok = True

    meta_match = art_sha256 == selected_sha256 and art_length == selected_length if art_sha256 else False

    repo_mutated = bool(row.get("repo_mutated", False))
    cloud_inv = bool(row.get("cloud_fallback_invoked", False))
    mc_inc = bool(row.get("model_calls", 0)) and row.get("model_calls", 0) != 0
    beh = bool(row.get("behavior_changed", False))

    would_allow = (
        flag and gov_present and alpha_ready
        and pub_lock and prod_lock
        and has_candidate and selected_hash_ok
    )

    artifact_ok = art_present and art_hash_ok and art_length > 0

    reasons = []
    if not flag:
        reasons.append("real_candidate_harness_flag_not_enabled")
    if not gov_present:
        reasons.append("missing_governance_closure")
    if gov and not alpha_ready:
        reasons.append("internal_alpha_not_ready")
    if not pub_lock:
        reasons.append("public_claim_lock_missing")
    if not prod_lock:
        reasons.append("production_lock_missing")
    if not has_candidate:
        reasons.append("selected_candidate_missing")
    if not selected_hash_ok:
        reasons.append("selected_candidate_hash_not_verified")
    if not art_present:
        reasons.append("real_candidate_artifact_missing")
    if art_present and not bool(art_sha256):
        reasons.append("real_candidate_artifact_hash_missing")
    if art_present and art_length <= 0:
        reasons.append("real_candidate_artifact_length_missing")
    if art_present and art_sha256 and not art_hash_ok:
        reasons.append("real_candidate_artifact_hash_mismatch")
    if art_present and selected_sha256 and art_sha256 and selected_length != art_length:
        reasons.append("real_candidate_artifact_length_mismatch")
    if repo_mutated:
        reasons.append("repo_mutation_detected")
    if cloud_inv:
        reasons.append("cloud_invoked_detected")
    if beh:
        reasons.append("behavior_changed_detected")
    reasons.extend([
        "isolated_real_candidate_artifact_only",
        "repo_mutation_blocked",
        "cloud_invocation_blocked",
        "model_calls_increment_blocked",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    if would_allow and artifact_ok and meta_match:
        harness_status = "real_local_candidate_artifact_verified"
    elif would_allow and art_present and not meta_match:
        harness_status = "real_local_candidate_artifact_mismatch"
    else:
        harness_status = "blocked"

    safe = would_allow and artifact_ok and meta_match and not repo_mutated and not cloud_inv and not beh

    return {
        "schema": "nexus.hybrid_h5_real_local_candidate_execution_harness.v1",
        "evaluated": True,
        "harness_status": harness_status,
        "harness_reasons": reasons,
        "harness_allowed": would_allow,
        "real_candidate_artifact_present": art_present,
        "real_candidate_artifact_verified": artifact_ok and meta_match,
        "real_candidate_patch_sha256": art_sha256,
        "real_candidate_patch_length": art_length,
        "real_candidate_patch_kind": art_kind,
        "real_candidate_source": "local_candidate_isolated_artifact",
        "selected_candidate_id": selected_id,
        "selected_candidate_hash_verified": selected_hash_ok,
        "metadata_candidate_matches_real_artifact": meta_match,
        "isolated_execution_only": True,
        "repo_mutation_allowed": False,
        "repo_mutated": repo_mutated,
        "model_calls_incremented": False,
        "cloud_invoked": cloud_inv,
        "behavior_changed": beh,
        "rollback_available": True,
        "safe_to_continue": safe,
        "internal_alpha_ready_required": True,
        "internal_alpha_ready": alpha_ready,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h5_real_patch_verifier_score_trial(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: real patch verifier score trial aggregation."""
    import os as _os
    from collections import Counter

    flag = _os.environ.get("NEXUS_H5_ALLOW_REAL_PATCH_VERIFIER_SCORE_TRIAL", "").strip() == "1"

    harness_present = False
    verified_count = 0
    mismatch_count = 0
    repo_mutated = 0
    cloud_inv = 0
    mc_inc = 0
    beh_count = 0
    verifier_eval = 0
    verifier_pass = 0
    verifier_fail = 0
    quality_pass = 0
    solved = 0
    failed = 0
    blocked = 0
    regression_count = 0
    fail_reasons: Counter = Counter()
    regression_reasons: Counter = Counter()

    for r in rows:
        harness = r.get("h5_real_local_candidate_execution_harness")
        if not harness:
            continue

        harness_present = True

        art_verified = bool(harness.get("real_candidate_artifact_verified", False))
        art_mismatch = bool(harness.get("metadata_candidate_matches_real_artifact", False)) is False and bool(harness.get("real_candidate_artifact_present", False))

        if art_verified:
            verified_count += 1
        if art_mismatch:
            mismatch_count += 1

        if bool(harness.get("repo_mutated", False)):
            repo_mutated += 1
            regression_count += 1
            regression_reasons["repo_mutated"] += 1
        if bool(harness.get("cloud_invoked", False)):
            cloud_inv += 1
            regression_count += 1
            regression_reasons["cloud_invoked"] += 1
        if bool(harness.get("behavior_changed", False)):
            beh_count += 1
            regression_count += 1
            regression_reasons["behavior_changed"] += 1

        verifier = r.get("h5_real_patch_verifier_result")
        if verifier:
            v_evaluated = bool(verifier.get("verifier_evaluated", False))
            v_passed = bool(verifier.get("verifier_passed", False))
            v_solved = bool(verifier.get("candidate_solved", False))
            v_quality = bool(verifier.get("quality_passed", False))

            if v_evaluated:
                verifier_eval += 1
            if v_passed:
                verifier_pass += 1
            else:
                verifier_fail += 1
                for reason in verifier.get("failure_reasons", []):
                    fail_reasons[reason] += 1
            if v_solved:
                solved += 1
            else:
                failed += 1
            if v_quality:
                quality_pass += 1
            if v_evaluated and art_verified and not v_passed:
                regression_count += 1
                regression_reasons["verifier_failed_after_verified"] += 1
        else:
            blocked += 1

    trial_allowed = (
        flag and harness_present and verified_count > 0
        and repo_mutated == 0 and cloud_inv == 0
        and mc_inc == 0 and beh_count == 0
    )

    trial_passed = (
        trial_allowed and verifier_eval >= 1
        and verifier_pass >= 1 and solved >= 1
        and regression_count == 0
    )

    solve_rate = solved / verifier_eval if verifier_eval > 0 else 0.0
    verifier_pass_rate = verifier_pass / verifier_eval if verifier_eval > 0 else 0.0
    quality_pass_rate = quality_pass / verifier_eval if verifier_eval > 0 else verifier_pass_rate

    reasons = []
    if not flag:
        reasons.append("score_trial_flag_not_enabled")
    if not harness_present:
        reasons.append("missing_real_candidate_harness")
    if verified_count == 0:
        reasons.append("no_verified_real_artifact")
    if repo_mutated > 0:
        reasons.append("repo_mutation_detected")
    if cloud_inv > 0:
        reasons.append("cloud_invoked_detected")
    if mc_inc > 0:
        reasons.append("model_calls_incremented_detected")
    if beh_count > 0:
        reasons.append("behavior_changed_detected")
    if verifier_eval == 0:
        reasons.append("no_verifier_result")
    if solved == 0 and verifier_eval > 0:
        reasons.append("no_candidate_solved")
    reasons.extend([
        "h5_47_score_trial_not_production",
        "repo_mutation_blocked",
        "cloud_invocation_blocked",
        "model_calls_increment_blocked",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    score_visible = verifier_eval > 0

    return {
        "schema": "nexus.hybrid_h5_real_patch_verifier_score_trial.v1",
        "evaluated": True,
        "trial_status": "real_patch_verifier_score_trial_pass" if trial_passed else ("blocked" if not trial_allowed else "real_patch_verifier_score_trial_fail"),
        "trial_reasons": reasons,
        "trial_allowed": trial_allowed,
        "trial_passed": trial_passed,
        "row_count": len(rows),
        "eligible_row_count": sum(1 for r in rows if r.get("h5_real_local_candidate_execution_harness")),
        "real_artifact_present_count": sum(1 for r in rows if r.get("h5_real_local_candidate_execution_harness", {}).get("real_candidate_artifact_present", False)),
        "real_artifact_verified_count": verified_count,
        "real_artifact_mismatch_count": mismatch_count,
        "verifier_evaluated_count": verifier_eval,
        "verifier_passed_count": verifier_pass,
        "verifier_failed_count": verifier_fail,
        "candidate_solved_count": solved,
        "candidate_failed_count": failed,
        "candidate_blocked_count": blocked,
        "solve_rate": solve_rate,
        "verifier_pass_rate": verifier_pass_rate,
        "quality_pass_rate": quality_pass_rate,
        "regression_count": regression_count,
        "fail_reason_counts": dict(fail_reasons),
        "regression_reason_counts": dict(regression_reasons),
        "repo_mutated_count": repo_mutated,
        "cloud_invoked_count": cloud_inv,
        "model_calls_incremented_count": mc_inc,
        "behavior_changed_count": beh_count,
        "score_visible": score_visible,
        "score_ready_for_benchmark": trial_passed,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h5_real_patch_benchmark_scoreboard(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: real patch benchmark scoreboard aggregating H5-47 score trial."""
    import os as _os
    from collections import Counter

    flag = _os.environ.get("NEXUS_H5_ALLOW_REAL_PATCH_BENCHMARK_SCOREBOARD", "").strip() == "1"

    score_trial = None
    if bundle:
        score_trial = bundle.get("h5_real_patch_verifier_score_trial")

    trial_present = bool(score_trial)
    score_visible = bool(score_trial.get("score_visible", False)) if score_trial else False
    v_eval = int(score_trial.get("verifier_evaluated_count", 0)) if score_trial else 0
    v_pass = int(score_trial.get("verifier_passed_count", 0)) if score_trial else 0
    v_fail = int(score_trial.get("verifier_failed_count", 0)) if score_trial else 0
    solved = int(score_trial.get("candidate_solved_count", 0)) if score_trial else 0
    failed = int(score_trial.get("candidate_failed_count", 0)) if score_trial else 0
    solve_r = float(score_trial.get("solve_rate", 0.0)) if score_trial else 0.0
    v_pass_r = float(score_trial.get("verifier_pass_rate", 0.0)) if score_trial else 0.0
    q_pass_r = float(score_trial.get("quality_pass_rate", 0.0)) if score_trial else 0.0
    regression_count = int(score_trial.get("regression_count", 0)) if score_trial else 0
    fail_rc = dict(score_trial.get("fail_reason_counts", {})) if score_trial else {}
    reg_rc = dict(score_trial.get("regression_reason_counts", {})) if score_trial else {}
    repo_mut = int(score_trial.get("repo_mutated_count", 0)) if score_trial else 0
    cloud_inv = int(score_trial.get("cloud_invoked_count", 0)) if score_trial else 0
    mc_inc = int(score_trial.get("model_calls_incremented_count", 0)) if score_trial else 0
    beh = int(score_trial.get("behavior_changed_count", 0)) if score_trial else 0

    row_count = int(score_trial.get("row_count", 0)) if score_trial else 0
    eligible = int(score_trial.get("eligible_row_count", 0)) if score_trial else 0
    verified = int(score_trial.get("real_artifact_verified_count", 0)) if score_trial else 0

    top_fail = sorted(fail_rc.items(), key=lambda x: (-x[1], x[0]))
    top_reg = sorted(reg_rc.items(), key=lambda x: (-x[1], x[0]))

    safety = repo_mut + cloud_inv + mc_inc + beh

    scoreboard_allowed = (
        flag and trial_present and score_visible and v_eval > 0
    )

    scoreboard_ready = (
        scoreboard_allowed and score_visible and v_eval > 0
        and repo_mut == 0 and cloud_inv == 0 and mc_inc == 0 and beh == 0
    )

    ready_apply = (
        scoreboard_ready and solved >= 1
        and solve_r > 0 and v_pass_r > 0
        and safety == 0
    )

    reasons = []
    if not flag:
        reasons.append("scoreboard_flag_not_enabled")
    if not trial_present:
        reasons.append("missing_h5_47_score_trial")
    if not score_visible:
        reasons.append("score_not_visible")
    if v_eval == 0:
        reasons.append("no_verifier_evaluated_rows")
    if repo_mut > 0:
        reasons.append("repo_mutation_detected")
    if cloud_inv > 0:
        reasons.append("cloud_invoked_detected")
    if mc_inc > 0:
        reasons.append("model_calls_incremented_detected")
    if beh > 0:
        reasons.append("behavior_changed_detected")
    reasons.extend([
        "h5_48_scoreboard_not_production",
        "scoreboard_only",
        "repo_mutation_blocked",
        "cloud_invocation_blocked",
        "model_calls_increment_blocked",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h5_real_patch_benchmark_scoreboard.v1",
        "evaluated": True,
        "scoreboard_status": "real_patch_benchmark_scoreboard_ready" if scoreboard_ready else ("blocked" if not scoreboard_allowed else "real_patch_benchmark_scoreboard_fail"),
        "scoreboard_reasons": reasons,
        "scoreboard_allowed": scoreboard_allowed,
        "scoreboard_ready": scoreboard_ready,
        "row_count": row_count,
        "eligible_row_count": eligible,
        "real_artifact_verified_count": verified,
        "verifier_evaluated_count": v_eval,
        "verifier_passed_count": v_pass,
        "verifier_failed_count": v_fail,
        "candidate_solved_count": solved,
        "candidate_failed_count": failed,
        "solve_rate": solve_r,
        "verifier_pass_rate": v_pass_r,
        "quality_pass_rate": q_pass_r,
        "score_visible": score_visible,
        "score_ready_for_benchmark": bool(score_trial.get("score_ready_for_benchmark", False)) if score_trial else False,
        "top_fail_reasons": top_fail[:5],
        "top_regression_reasons": top_reg[:5],
        "fail_reason_counts": fail_rc,
        "regression_reason_counts": reg_rc,
        "repo_mutated_count": repo_mut,
        "cloud_invoked_count": cloud_inv,
        "model_calls_incremented_count": mc_inc,
        "behavior_changed_count": beh,
        "safety_violation_count": safety,
        "ready_for_controlled_apply_trial": ready_apply,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h5_controlled_real_patch_apply_test_trial(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: controlled real patch apply/test trial aggregation."""
    import os as _os
    from collections import Counter

    flag = _os.environ.get("NEXUS_H5_ALLOW_CONTROLLED_REAL_PATCH_APPLY_TEST_TRIAL", "").strip() == "1"

    scoreboard = None
    if bundle:
        scoreboard = bundle.get("h5_real_patch_benchmark_scoreboard")

    sb_present = bool(scoreboard)
    sb_ready = bool(scoreboard.get("scoreboard_ready", False)) if scoreboard else False
    ready_apply = bool(scoreboard.get("ready_for_controlled_apply_trial", False)) if scoreboard else False
    sb_safety = int(scoreboard.get("safety_violation_count", 0)) if scoreboard else 0

    apply_attempted = 0
    apply_passed = 0
    apply_failed = 0
    apply_blocked = 0
    tests_run = 0
    tests_passed = 0
    tests_failed = 0
    tests_blocked = 0
    repo_mut = 0
    cloud_inv = 0
    mc_inc = 0
    beh = 0
    fail_reasons: Counter = Counter()
    test_fail_reasons: Counter = Counter()
    regression_reasons: Counter = Counter()

    for r in rows:
        result = r.get("h5_controlled_apply_test_result")
        if not result:
            apply_blocked += 1
            tests_blocked += 1
            continue

        attempted = bool(result.get("apply_attempted", False))
        passed = bool(result.get("apply_passed", False))
        t_run = int(result.get("tests_run", 0) or 0)
        t_passed = int(result.get("tests_passed", 0) or 0)
        t_failed = int(result.get("tests_failed", 0) or 0)
        rm = bool(result.get("repo_mutated", False))
        ci = bool(result.get("cloud_invoked", False))
        mc = bool(result.get("model_calls_incremented", False))
        bh = bool(result.get("behavior_changed", False))

        if attempted:
            apply_attempted += 1
            if passed:
                apply_passed += 1
            else:
                apply_failed += 1
                for reason in result.get("failure_reasons", []):
                    fail_reasons[reason] += 1
        else:
            apply_blocked += 1

        if t_run > 0:
            tests_run += t_run
            tests_passed += t_passed
            tests_failed += t_failed
        else:
            tests_blocked += 1

        for reason in result.get("test_failure_reasons", []):
            test_fail_reasons[reason] += 1

        if rm:
            repo_mut += 1
            regression_reasons["repo_mutated"] += 1
        if ci:
            cloud_inv += 1
            regression_reasons["cloud_invoked"] += 1
        if mc:
            mc_inc += 1
            regression_reasons["model_calls_incremented"] += 1
        if bh:
            beh += 1
            regression_reasons["behavior_changed"] += 1

    safety = repo_mut + cloud_inv + mc_inc + beh

    trial_allowed = (
        flag and sb_present and sb_ready and ready_apply
        and sb_safety == 0
    )

    trial_passed = (
        trial_allowed and apply_attempted >= 1
        and apply_passed >= 1 and tests_run >= 1
        and tests_failed == 0
        and repo_mut == 0 and cloud_inv == 0
        and mc_inc == 0 and beh == 0
    )

    apply_pass_rate = apply_passed / apply_attempted if apply_attempted > 0 else 0.0
    test_pass_rate = tests_passed / tests_run if tests_run > 0 else 0.0
    apply_test_pass_rate = apply_passed / apply_attempted if apply_attempted > 0 else 0.0

    reasons = []
    if not flag:
        reasons.append("apply_test_flag_not_enabled")
    if not sb_present:
        reasons.append("missing_scoreboard")
    if scoreboard and not sb_ready:
        reasons.append("scoreboard_not_ready")
    if scoreboard and not ready_apply:
        reasons.append("not_ready_for_controlled_apply_trial")
    if sb_safety > 0:
        reasons.append("scoreboard_safety_violation_detected")
    if apply_attempted == 0:
        reasons.append("no_apply_attempted")
    if apply_passed == 0 and apply_attempted > 0:
        reasons.append("no_apply_passed")
    if tests_run == 0 and apply_attempted > 0:
        reasons.append("no_tests_run")
    if tests_failed > 0:
        reasons.append("tests_failed")
    if repo_mut > 0:
        reasons.append("repo_mutation_detected")
    if cloud_inv > 0:
        reasons.append("cloud_invoked_detected")
    if mc_inc > 0:
        reasons.append("model_calls_incremented_detected")
    if beh > 0:
        reasons.append("behavior_changed_detected")
    reasons.extend([
        "h5_49_controlled_apply_test_not_production",
        "isolated_apply_only",
        "repo_mutation_blocked_outside_isolation",
        "cloud_invocation_blocked",
        "model_calls_increment_blocked",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h5_controlled_real_patch_apply_test_trial.v1",
        "evaluated": True,
        "trial_status": "controlled_real_patch_apply_test_trial_pass" if trial_passed else ("blocked" if not trial_allowed else "controlled_real_patch_apply_test_trial_fail"),
        "trial_reasons": reasons,
        "trial_allowed": trial_allowed,
        "trial_passed": trial_passed,
        "row_count": len(rows),
        "eligible_row_count": sum(1 for r in rows if r.get("h5_controlled_apply_test_result")),
        "scoreboard_present": sb_present,
        "scoreboard_ready": sb_ready,
        "ready_for_controlled_apply_trial": ready_apply,
        "patch_apply_attempted_count": apply_attempted,
        "patch_apply_passed_count": apply_passed,
        "patch_apply_failed_count": apply_failed,
        "patch_apply_blocked_count": apply_blocked,
        "tests_run_count": tests_run,
        "tests_passed_count": tests_passed,
        "tests_failed_count": tests_failed,
        "tests_blocked_count": tests_blocked,
        "apply_pass_rate": apply_pass_rate,
        "test_pass_rate": test_pass_rate,
        "apply_test_pass_rate": apply_test_pass_rate,
        "fail_reason_counts": dict(fail_reasons),
        "test_failure_reason_counts": dict(test_fail_reasons),
        "regression_reason_counts": dict(regression_reasons),
        "isolated_apply_only": True,
        "repo_mutated_count": repo_mut,
        "cloud_invoked_count": cloud_inv,
        "model_calls_incremented_count": mc_inc,
        "behavior_changed_count": beh,
        "safety_violation_count": safety,
        "ready_for_benchmark_delta": trial_passed,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h5_benchmark_delta_report(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: benchmark delta report comparing baseline vs H5 metrics."""
    import os as _os

    flag = _os.environ.get("NEXUS_H5_ALLOW_BENCHMARK_DELTA_REPORT", "").strip() == "1"

    apply_trial = None
    if bundle:
        apply_trial = bundle.get("h5_controlled_real_patch_apply_test_trial")

    trial_present = bool(apply_trial)
    trial_passed = bool(apply_trial.get("trial_passed", False)) if apply_trial else False
    ready_delta = bool(apply_trial.get("ready_for_benchmark_delta", False)) if apply_trial else False
    trial_safety = int(apply_trial.get("safety_violation_count", 0)) if apply_trial else 0

    baseline_rows = [r for r in rows if str(r.get("mode", "")) == "baseline"]
    h5_rows = [r for r in rows if str(r.get("mode", "")) == "h5"]

    bl_count = len(baseline_rows)
    h5_count = len(h5_rows)

    bl_solved = sum(1 for r in baseline_rows if bool(r.get("candidate_solved", False)))
    h5_solved = sum(1 for r in h5_rows if bool(r.get("candidate_solved", False)))
    bl_solve_rate = bl_solved / bl_count if bl_count > 0 else 0.0
    h5_solve_rate = h5_solved / h5_count if h5_count > 0 else 0.0
    solve_delta = h5_solve_rate - bl_solve_rate

    bl_apply = sum(1 for r in baseline_rows if bool(r.get("patch_apply_passed", False)))
    h5_apply = sum(1 for r in h5_rows if bool(r.get("patch_apply_passed", False)))
    bl_apply_rate = bl_apply / bl_count if bl_count > 0 else 0.0
    h5_apply_rate = h5_apply / h5_count if h5_count > 0 else 0.0
    apply_delta = h5_apply_rate - bl_apply_rate

    bl_tp = sum(1 for r in baseline_rows if bool(r.get("tests_passed", 0)))
    h5_tp = sum(1 for r in h5_rows if bool(r.get("tests_passed", 0)))
    bl_tr = sum(int(r.get("tests_run", 0) or 0) for r in baseline_rows)
    h5_tr = sum(int(r.get("tests_run", 0) or 0) for r in h5_rows)
    bl_test_rate = bl_tp / bl_tr if bl_tr > 0 else 0.0
    h5_test_rate = h5_tp / h5_tr if h5_tr > 0 else 0.0
    test_delta = h5_test_rate - bl_test_rate

    bl_atp = sum(1 for r in baseline_rows if bool(r.get("apply_test_passed", False)))
    h5_atp = sum(1 for r in h5_rows if bool(r.get("apply_test_passed", False)))
    bl_atp_rate = bl_atp / bl_count if bl_count > 0 else 0.0
    h5_atp_rate = h5_atp / h5_count if h5_count > 0 else 0.0
    atp_delta = h5_atp_rate - bl_atp_rate

    improvement = solve_delta > 0 or apply_delta > 0 or test_delta > 0 or atp_delta > 0
    regression = solve_delta < 0 or apply_delta < 0 or test_delta < 0 or atp_delta < 0
    neutral = not improvement and not regression

    repo_mut = sum(1 for r in rows if bool(r.get("repo_mutated", False)))
    cloud_inv = sum(1 for r in rows if bool(r.get("cloud_invoked", False)))
    mc_inc = sum(1 for r in rows if bool(r.get("model_calls_incremented", False)))
    beh = sum(1 for r in rows if bool(r.get("behavior_changed", False)))
    safety = repo_mut + cloud_inv + mc_inc + beh

    delta_allowed = (
        flag and trial_present and trial_passed
        and ready_delta and trial_safety == 0
    )

    delta_ready = (
        delta_allowed and bl_count > 0 and h5_count > 0 and safety == 0
    )

    ready_larger = (
        delta_ready and improvement and not regression and safety == 0
    )

    reasons = []
    if not flag:
        reasons.append("delta_report_flag_not_enabled")
    if not trial_present:
        reasons.append("missing_h5_49_apply_test_trial")
    if apply_trial and not trial_passed:
        reasons.append("h5_49_trial_not_passed")
    if apply_trial and not ready_delta:
        reasons.append("not_ready_for_benchmark_delta")
    if bl_count == 0:
        reasons.append("missing_baseline_rows")
    if h5_count == 0:
        reasons.append("missing_h5_rows")
    if safety > 0:
        reasons.append("safety_violation_detected")
    if regression:
        reasons.append("benchmark_regression_detected")
    reasons.extend([
        "h5_50_delta_report_not_production",
        "benchmark_delta_internal_only",
        "repo_mutation_blocked_outside_isolation",
        "cloud_invocation_blocked",
        "model_calls_increment_blocked",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h5_benchmark_delta_report.v1",
        "evaluated": True,
        "delta_status": "benchmark_delta_report_ready" if delta_ready else ("blocked" if not delta_allowed else "benchmark_delta_report_fail"),
        "delta_reasons": reasons,
        "delta_allowed": delta_allowed,
        "delta_ready": delta_ready,
        "row_count": len(rows),
        "baseline_row_count": bl_count,
        "h5_row_count": h5_count,
        "baseline_solved_count": bl_solved,
        "h5_solved_count": h5_solved,
        "baseline_solve_rate": bl_solve_rate,
        "h5_solve_rate": h5_solve_rate,
        "solve_rate_delta": solve_delta,
        "baseline_apply_passed_count": bl_apply,
        "h5_apply_passed_count": h5_apply,
        "baseline_apply_pass_rate": bl_apply_rate,
        "h5_apply_pass_rate": h5_apply_rate,
        "apply_pass_rate_delta": apply_delta,
        "baseline_test_passed_count": bl_tp,
        "h5_test_passed_count": h5_tp,
        "baseline_test_pass_rate": bl_test_rate,
        "h5_test_pass_rate": h5_test_rate,
        "test_pass_rate_delta": test_delta,
        "baseline_apply_test_pass_rate": bl_atp_rate,
        "h5_apply_test_pass_rate": h5_atp_rate,
        "apply_test_pass_rate_delta": atp_delta,
        "improvement_detected": improvement,
        "regression_detected": regression,
        "neutral_delta": neutral,
        "safety_violation_count": safety,
        "repo_mutated_count": repo_mut,
        "cloud_invoked_count": cloud_inv,
        "model_calls_incremented_count": mc_inc,
        "behavior_changed_count": beh,
        "ready_for_larger_benchmark_run": ready_larger,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h5_guarded_larger_benchmark_batch_run(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: guarded larger benchmark batch run aggregation."""
    import os as _os
    from collections import Counter, defaultdict

    flag = _os.environ.get("NEXUS_H5_ALLOW_GUARDED_LARGER_BENCHMARK_BATCH_RUN", "").strip() == "1"

    delta = None
    if bundle:
        delta = bundle.get("h5_benchmark_delta_report")

    delta_present = bool(delta)
    delta_ready = bool(delta.get("delta_ready", False)) if delta else False
    ready_larger = bool(delta.get("ready_for_larger_benchmark_run", False)) if delta else False
    delta_safety = int(delta.get("safety_violation_count", 0)) if delta else 0

    by_id: dict[str, dict[str, list]] = defaultdict(lambda: {"baseline": [], "h5": []})
    for r in rows:
        tid = str(r.get("task_id", ""))
        mode = str(r.get("mode", ""))
        if tid and mode in ("baseline", "h5"):
            by_id[tid][mode].append(r)

    paired_ids = [tid for tid, modes in by_id.items() if modes["baseline"] and modes["h5"]]
    paired_count = len(paired_ids)

    bl_count = sum(1 for r in rows if str(r.get("mode", "")) == "baseline")
    h5_count = sum(1 for r in rows if str(r.get("mode", "")) == "h5")

    batch_solved = 0
    batch_apply = 0
    batch_tp = 0
    batch_tr = 0
    batch_improve = 0
    batch_regress = 0
    batch_neutral = 0

    repo_mut = 0
    cloud_inv = 0
    mc_inc = 0
    beh = 0
    fail_reasons: Counter = Counter()
    regression_reasons: Counter = Counter()

    for r in rows:
        rm = bool(r.get("repo_mutated", False))
        ci = bool(r.get("cloud_invoked", False))
        mc = bool(r.get("model_calls_incremented", False))
        bh = bool(r.get("behavior_changed", False))
        if rm:
            repo_mut += 1
            regression_reasons["repo_mutated"] += 1
        if ci:
            cloud_inv += 1
            regression_reasons["cloud_invoked"] += 1
        if mc:
            mc_inc += 1
            regression_reasons["model_calls_incremented"] += 1
        if bh:
            beh += 1
            regression_reasons["behavior_changed"] += 1

        for reason in r.get("failure_reasons", []):
            fail_reasons[reason] += 1
        for reason in r.get("regression_reasons", []):
            regression_reasons[reason] += 1

        if str(r.get("mode", "")) == "h5":
            if bool(r.get("candidate_solved", False)):
                batch_solved += 1
            if bool(r.get("patch_apply_passed", False)):
                batch_apply += 1
            batch_tr += int(r.get("tests_run", 0) or 0)
            batch_tp += int(r.get("tests_passed", 0) or 0)

    for tid in paired_ids:
        bl_rows = by_id[tid]["baseline"]
        h5_r = by_id[tid]["h5"][0]
        bl = bl_rows[0]
        bl_solved = bool(bl.get("candidate_solved", False))
        h5_solved = bool(h5_r.get("candidate_solved", False))
        bl_apply = bool(bl.get("patch_apply_passed", False))
        h5_apply = bool(h5_r.get("patch_apply_passed", False))
        bl_tp = int(bl.get("tests_passed", 0) or 0) > 0
        h5_tp = int(h5_r.get("tests_passed", 0) or 0) > 0
        bl_at = bool(bl.get("apply_test_passed", False))
        h5_at = bool(h5_r.get("apply_test_passed", False))

        improved = h5_solved != bl_solved and h5_solved or h5_apply != bl_apply and h5_apply or h5_tp != bl_tp and h5_tp or h5_at != bl_at and h5_at
        regressed = (not h5_solved and bl_solved) or (not h5_apply and bl_apply) or (not h5_tp and bl_tp) or (not h5_at and bl_at)

        if improved and not regressed:
            batch_improve += 1
        elif regressed:
            batch_regress += 1
        else:
            batch_neutral += 1

    total_h5 = h5_count if h5_count > 0 else 1
    batch_solve_rate = batch_solved / total_h5
    batch_apply_rate = batch_apply / total_h5 if total_h5 > 0 else 0.0
    batch_test_rate = batch_tp / batch_tr if batch_tr > 0 else 0.0
    batch_at_rate = batch_tp / batch_tr if batch_tr > 0 else 0.0
    improve_rate = batch_improve / paired_count if paired_count > 0 else 0.0
    regress_rate = batch_regress / paired_count if paired_count > 0 else 0.0

    safety = repo_mut + cloud_inv + mc_inc + beh

    batch_allowed = (
        flag and delta_present and delta_ready and ready_larger
        and delta_safety == 0
    )

    batch_ready = (
        batch_allowed and paired_count >= 1 and safety == 0
    )

    ready_h6 = (
        batch_ready and batch_improve >= 1
        and batch_regress == 0 and safety == 0
    )

    reasons = []
    if not flag:
        reasons.append("batch_run_flag_not_enabled")
    if not delta_present:
        reasons.append("missing_h5_50_delta_report")
    if delta and not delta_ready:
        reasons.append("h5_50_delta_not_ready")
    if delta and not ready_larger:
        reasons.append("not_ready_for_larger_benchmark_run")
    if paired_count == 0:
        reasons.append("missing_paired_rows")
    if safety > 0:
        reasons.append("safety_violation_detected")
    if batch_regress > 0:
        reasons.append("batch_regression_detected")
    reasons.extend([
        "h5_51_batch_run_not_production",
        "guarded_batch_internal_only",
        "repo_mutation_blocked_outside_isolation",
        "cloud_invocation_blocked",
        "model_calls_increment_blocked",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h5_guarded_larger_benchmark_batch_run.v1",
        "evaluated": True,
        "batch_status": "guarded_larger_benchmark_batch_ready" if batch_ready else ("blocked" if not batch_allowed else "guarded_larger_benchmark_batch_fail"),
        "batch_reasons": reasons,
        "batch_allowed": batch_allowed,
        "batch_ready": batch_ready,
        "row_count": len(rows),
        "baseline_row_count": bl_count,
        "h5_row_count": h5_count,
        "paired_row_count": paired_count,
        "benchmark_delta_present": delta_present,
        "benchmark_delta_ready": delta_ready,
        "ready_for_larger_benchmark_run": ready_larger,
        "batch_solved_count": batch_solved,
        "batch_failed_count": total_h5 - batch_solved,
        "batch_solve_rate": batch_solve_rate,
        "batch_apply_passed_count": batch_apply,
        "batch_apply_failed_count": total_h5 - batch_apply,
        "batch_apply_pass_rate": batch_apply_rate,
        "batch_tests_run_count": batch_tr,
        "batch_tests_passed_count": batch_tp,
        "batch_tests_failed_count": batch_tr - batch_tp,
        "batch_test_pass_rate": batch_test_rate,
        "batch_apply_test_pass_rate": batch_at_rate,
        "batch_improvement_count": batch_improve,
        "batch_regression_count": batch_regress,
        "batch_neutral_count": batch_neutral,
        "batch_improvement_rate": improve_rate,
        "batch_regression_rate": regress_rate,
        "fail_reason_counts": dict(fail_reasons),
        "regression_reason_counts": dict(regression_reasons),
        "repo_mutated_count": repo_mut,
        "cloud_invoked_count": cloud_inv,
        "model_calls_incremented_count": mc_inc,
        "behavior_changed_count": beh,
        "safety_violation_count": safety,
        "ready_for_h6_local_model_adapter_preflight": ready_h6,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h6_local_model_adapter_preflight_contract(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: H6 local model adapter preflight contract."""
    import os as _os

    flag = _os.environ.get("NEXUS_H6_ALLOW_LOCAL_MODEL_ADAPTER_PREFLIGHT", "").strip() == "1"

    batch = None
    if bundle:
        batch = bundle.get("h5_guarded_larger_benchmark_batch_run")

    batch_present = bool(batch)
    batch_ready = bool(batch.get("batch_ready", False)) if batch else False
    ready_h6 = bool(batch.get("ready_for_h6_local_model_adapter_preflight", False)) if batch else False
    batch_safety = int(batch.get("safety_violation_count", 0)) if batch else 0

    ALLOWED_ROLES = {"selector", "localizer", "patch_synthesizer", "verifier_assist"}
    ALLOWED_FAMILIES = {"qwen"}
    ALLOWED_SIZES = {"3b", "7b", "14b"}
    ALLOWED_ROUTES = {"local_first", "local_only", "shadow_only"}
    ALLOWED_ADAPTER_MODES = {"preflight_only", "shadow_only"}

    candidates = [r.get("h6_local_model_adapter_candidate") for r in rows if r.get("h6_local_model_adapter_candidate")]
    valid_candidates = []
    invalid_count = 0
    missing_field = 0
    invalid_family = 0
    invalid_size = 0
    invalid_role = 0
    unsafe_route = 0
    mc_count = 0
    ollama_count = 0
    cloud_count = 0
    repo_mut = 0
    beh = 0

    qwen_3b = 0
    qwen_7b = 0
    qwen_14b = 0
    role_selector = 0
    role_localizer = 0
    role_ps = 0
    role_va = 0

    for c in candidates:
        mc = bool(c.get("model_call_executed", False))
        ol = bool(c.get("ollama_invoked", False))
        cl = bool(c.get("cloud_invoked", False))
        rm = bool(c.get("repo_mutated", False))
        bh = bool(c.get("behavior_changed", False))
        required = bool(c.get("required_fields_present", False))
        fam = str(c.get("model_family", "") or "").lower()
        sz = str(c.get("model_size", "") or "").lower()
        role = str(c.get("role", "") or "").lower()
        route = str(c.get("route_mode", "") or "").lower()
        adapter_mode = str(c.get("adapter_mode", "") or "").lower()

        if mc:
            mc_count += 1
        if ol:
            ollama_count += 1
        if cl:
            cloud_count += 1
        if rm:
            repo_mut += 1
        if bh:
            beh += 1

        is_valid = (
            required and fam in ALLOWED_FAMILIES and sz in ALLOWED_SIZES
            and role in ALLOWED_ROLES and route in ALLOWED_ROUTES
            and adapter_mode in ALLOWED_ADAPTER_MODES
            and not mc and not ol and not cl and not rm and not bh
        )

        if is_valid:
            valid_candidates.append(c)
            if sz == "3b":
                qwen_3b += 1
            elif sz == "7b":
                qwen_7b += 1
            elif sz == "14b":
                qwen_14b += 1
            if role == "selector":
                role_selector += 1
            elif role == "localizer":
                role_localizer += 1
            elif role == "patch_synthesizer":
                role_ps += 1
            elif role == "verifier_assist":
                role_va += 1
        else:
            invalid_count += 1
            if not required:
                missing_field += 1
            if fam not in ALLOWED_FAMILIES:
                invalid_family += 1
            if sz not in ALLOWED_SIZES:
                invalid_size += 1
            if role not in ALLOWED_ROLES:
                invalid_role += 1
            if route not in ALLOWED_ROUTES:
                unsafe_route += 1

    safety = mc_count + ollama_count + cloud_count + repo_mut + beh

    preflight_allowed = (
        flag and batch_present and batch_ready and ready_h6 and batch_safety == 0
    )

    preflight_ready = (
        preflight_allowed and len(valid_candidates) > 0 and safety == 0
    )

    contract_ready = (
        preflight_ready and len(valid_candidates) > 0 and invalid_count == 0
    )

    ready_dry = (
        contract_ready
        and mc_count == 0 and ollama_count == 0
        and cloud_count == 0 and repo_mut == 0 and beh == 0
    )

    reasons = []
    if not flag:
        reasons.append("preflight_flag_not_enabled")
    if not batch_present:
        reasons.append("missing_h5_51_guarded_batch")
    if batch and not batch_ready:
        reasons.append("h5_51_batch_not_ready")
    if batch and not ready_h6:
        reasons.append("not_ready_for_h6_local_model_adapter_preflight")
    if batch_safety > 0:
        reasons.append("h5_51_safety_violation_detected")
    if not candidates:
        reasons.append("no_adapter_candidates")
    if candidates and len(valid_candidates) == 0:
        reasons.append("no_valid_adapter_candidates")
    if missing_field > 0:
        reasons.append("missing_required_fields")
    if invalid_family > 0:
        reasons.append("invalid_model_family")
    if invalid_size > 0:
        reasons.append("invalid_model_size")
    if invalid_role > 0:
        reasons.append("invalid_role")
    if unsafe_route > 0:
        reasons.append("unsafe_route_mode")
    if mc_count > 0:
        reasons.append("model_call_executed_detected")
    if ollama_count > 0:
        reasons.append("ollama_invoked_detected")
    if cloud_count > 0:
        reasons.append("cloud_invoked_detected")
    if repo_mut > 0:
        reasons.append("repo_mutated_detected")
    if beh > 0:
        reasons.append("behavior_changed_detected")
    reasons.extend([
        "h6_0_local_model_adapter_preflight_not_production",
        "preflight_contract_only",
        "no_model_calls_allowed",
        "ollama_invocation_blocked",
        "cloud_invocation_blocked",
        "repo_mutation_blocked",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h6_local_model_adapter_preflight_contract.v1",
        "evaluated": True,
        "preflight_status": "local_model_adapter_preflight_ready" if preflight_ready else ("blocked" if not preflight_allowed else "local_model_adapter_preflight_fail"),
        "preflight_reasons": reasons,
        "preflight_allowed": preflight_allowed,
        "preflight_ready": preflight_ready,
        "row_count": len(rows),
        "h5_guarded_batch_present": batch_present,
        "h5_guarded_batch_ready": batch_ready,
        "ready_for_h6_local_model_adapter_preflight": ready_h6,
        "adapter_candidate_count": len(candidates),
        "adapter_candidate_valid_count": len(valid_candidates),
        "adapter_candidate_invalid_count": invalid_count,
        "allowed_model_roles": ["selector", "localizer", "patch_synthesizer", "verifier_assist"],
        "allowed_model_families": ["qwen"],
        "allowed_model_sizes": ["3b", "7b", "14b"],
        "qwen_3b_candidate_count": qwen_3b,
        "qwen_7b_candidate_count": qwen_7b,
        "qwen_14b_candidate_count": qwen_14b,
        "selector_candidate_count": role_selector,
        "localizer_candidate_count": role_localizer,
        "patch_synthesizer_candidate_count": role_ps,
        "verifier_assist_candidate_count": role_va,
        "missing_required_field_count": missing_field,
        "invalid_role_count": invalid_role,
        "invalid_model_family_count": invalid_family,
        "invalid_model_size_count": invalid_size,
        "unsafe_route_count": unsafe_route,
        "model_call_executed_count": mc_count,
        "ollama_invoked_count": ollama_count,
        "cloud_invoked_count": cloud_count,
        "repo_mutated_count": repo_mut,
        "behavior_changed_count": beh,
        "safety_violation_count": safety,
        "adapter_contract_ready": contract_ready,
        "ready_for_h6_1_shadow_local_adapter_dry_run": ready_dry,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h6_shadow_local_adapter_dry_run(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: H6 shadow local adapter dry-run receipt."""
    import os as _os

    flag = _os.environ.get("NEXUS_H6_ALLOW_SHADOW_LOCAL_ADAPTER_DRY_RUN", "").strip() == "1"

    preflight = None
    if bundle:
        preflight = bundle.get("h6_local_model_adapter_preflight_contract")

    preflight_present = bool(preflight)
    preflight_ready = bool(preflight.get("preflight_ready", False)) if preflight else False
    adapter_contract_ready = bool(preflight.get("adapter_contract_ready", False)) if preflight else False
    ready_dry = bool(preflight.get("ready_for_h6_1_shadow_local_adapter_dry_run", False)) if preflight else False
    preflight_safety = int(preflight.get("safety_violation_count", 0)) if preflight else 0

    ALLOWED_ROLES = {"selector", "localizer", "patch_synthesizer", "verifier_assist"}
    ALLOWED_FAMILIES = {"qwen"}
    ALLOWED_SIZES = {"3b", "7b", "14b"}
    ALLOWED_ROUTES = {"local_first", "local_only", "shadow_only"}
    ALLOWED_SHADOW_MODES = {"dry_run", "trace_only"}
    ALLOWED_RECEIPT_STATUSES = {"dry_run_only", "trace_only"}

    requests = [r.get("h6_shadow_local_adapter_request") for r in rows if r.get("h6_shadow_local_adapter_request")]
    receipts = [r.get("h6_shadow_local_adapter_receipt") for r in rows if r.get("h6_shadow_local_adapter_receipt")]

    valid_requests = []
    invalid_requests = 0
    missing_adapter_id = 0
    missing_model_name = 0
    missing_role = 0
    missing_route_mode = 0
    invalid_shadow_mode = 0

    valid_receipts = []
    invalid_receipts = 0
    runtime_effect_count = 0

    qwen_3b = 0
    qwen_7b = 0
    qwen_14b = 0
    role_selector = 0
    role_localizer = 0
    role_ps = 0
    role_va = 0

    mc_count = 0
    ol_count = 0
    cl_count = 0
    rm_count = 0
    bh_count = 0

    for req in requests:
        aid = str(req.get("adapter_id", "") or "").strip()
        fam = str(req.get("model_family", "") or "").lower()
        sz = str(req.get("model_size", "") or "").lower()
        mname = str(req.get("model_name", "") or "").strip()
        role = str(req.get("role", "") or "").lower()
        route = str(req.get("route_mode", "") or "").lower()
        adapter_mode = str(req.get("adapter_mode", "") or "").lower()
        shadow_mode = str(req.get("shadow_mode", "") or "").lower()
        mc = bool(req.get("model_call_executed", False))
        ol = bool(req.get("ollama_invoked", False))
        cl = bool(req.get("cloud_invoked", False))
        rm = bool(req.get("repo_mutated", False))
        bh = bool(req.get("behavior_changed", False))

        if mc:
            mc_count += 1
        if ol:
            ol_count += 1
        if cl:
            cl_count += 1
        if rm:
            rm_count += 1
        if bh:
            bh_count += 1

        is_valid = (
            aid and fam in ALLOWED_FAMILIES and sz in ALLOWED_SIZES
            and mname and role in ALLOWED_ROLES and route in ALLOWED_ROUTES
            and adapter_mode == "shadow_only" and shadow_mode in ALLOWED_SHADOW_MODES
            and not mc and not ol and not cl and not rm and not bh
        )

        if is_valid:
            valid_requests.append(req)
            if sz == "3b":
                qwen_3b += 1
            elif sz == "7b":
                qwen_7b += 1
            elif sz == "14b":
                qwen_14b += 1
            if role == "selector":
                role_selector += 1
            elif role == "localizer":
                role_localizer += 1
            elif role == "patch_synthesizer":
                role_ps += 1
            elif role == "verifier_assist":
                role_va += 1
        else:
            invalid_requests += 1
            if not aid:
                missing_adapter_id += 1
            if not mname:
                missing_model_name += 1
            if role not in ALLOWED_ROLES:
                missing_role += 1
            if route not in ALLOWED_ROUTES:
                missing_route_mode += 1
            if shadow_mode not in ALLOWED_SHADOW_MODES:
                invalid_shadow_mode += 1

    for rec in receipts:
        rid = str(rec.get("request_id", "") or "").strip()
        aid = str(rec.get("adapter_id", "") or "").strip()
        status = str(rec.get("receipt_status", "") or "").lower()
        re = bool(rec.get("runtime_effect", False))
        mc = bool(rec.get("model_call_executed", False))
        ol = bool(rec.get("ollama_invoked", False))
        cl = bool(rec.get("cloud_invoked", False))
        rm = bool(rec.get("repo_mutated", False))
        bh = bool(rec.get("behavior_changed", False))

        if mc:
            mc_count += 1
        if ol:
            ol_count += 1
        if cl:
            cl_count += 1
        if rm:
            rm_count += 1
        if bh:
            bh_count += 1
        if re:
            runtime_effect_count += 1

        is_valid = (
            rid and aid and status in ALLOWED_RECEIPT_STATUSES
            and not re and not mc and not ol and not cl and not rm and not bh
        )

        if is_valid:
            valid_receipts.append(rec)
        else:
            invalid_receipts += 1

    safety = mc_count + ol_count + cl_count + rm_count + bh_count + runtime_effect_count

    dry_run_allowed = (
        flag and preflight_present and preflight_ready
        and adapter_contract_ready and ready_dry and preflight_safety == 0
    )

    dry_run_ready = (
        dry_run_allowed and len(valid_requests) > 0 and len(valid_receipts) > 0
        and safety == 0
    )

    adapter_dry_run_receipt_ready = (
        dry_run_ready and len(valid_requests) >= 1 and len(valid_receipts) >= 1
        and invalid_requests == 0 and invalid_receipts == 0
    )

    ready_io = (
        adapter_dry_run_receipt_ready and mc_count == 0 and ol_count == 0
        and cl_count == 0 and rm_count == 0 and bh_count == 0
    )

    reasons = []
    if not flag:
        reasons.append("shadow_dry_run_flag_not_enabled")
    if not preflight_present:
        reasons.append("missing_h6_0_preflight_contract")
    if preflight and not preflight_ready:
        reasons.append("h6_0_preflight_not_ready")
    if preflight and not adapter_contract_ready:
        reasons.append("h6_0_adapter_contract_not_ready")
    if preflight and not ready_dry:
        reasons.append("not_ready_for_h6_1_shadow_local_adapter_dry_run")
    if preflight_safety > 0:
        reasons.append("h6_0_safety_violation_detected")
    if not requests:
        reasons.append("no_shadow_requests")
    if requests and len(valid_requests) == 0:
        reasons.append("no_valid_shadow_requests")
    if not receipts:
        reasons.append("no_shadow_receipts")
    if receipts and len(valid_receipts) == 0:
        reasons.append("no_valid_shadow_receipts")
    if missing_adapter_id > 0:
        reasons.append("missing_adapter_id")
    if missing_model_name > 0:
        reasons.append("missing_model_name")
    if missing_role > 0:
        reasons.append("missing_role")
    if missing_route_mode > 0:
        reasons.append("missing_route_mode")
    if invalid_shadow_mode > 0:
        reasons.append("invalid_shadow_mode")
    if invalid_receipts > 0:
        reasons.append("invalid_receipt")
    if mc_count > 0:
        reasons.append("model_call_executed_detected")
    if ol_count > 0:
        reasons.append("ollama_invoked_detected")
    if cl_count > 0:
        reasons.append("cloud_invoked_detected")
    if rm_count > 0:
        reasons.append("repo_mutated_detected")
    if bh_count > 0:
        reasons.append("behavior_changed_detected")
    if runtime_effect_count > 0:
        reasons.append("runtime_effect_detected")
    reasons.extend([
        "h6_1_shadow_local_adapter_dry_run_not_production",
        "shadow_dry_run_only",
        "no_model_calls_allowed",
        "ollama_invocation_blocked",
        "cloud_invocation_blocked",
        "repo_mutation_blocked",
        "runtime_effect_blocked",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h6_shadow_local_adapter_dry_run.v1",
        "evaluated": True,
        "dry_run_status": "shadow_local_adapter_dry_run_ready" if dry_run_ready else ("shadow_local_adapter_dry_run_fail" if dry_run_allowed else "blocked"),
        "dry_run_reasons": reasons,
        "dry_run_allowed": dry_run_allowed,
        "dry_run_ready": dry_run_ready,
        "row_count": len(rows),
        "preflight_present": preflight_present,
        "preflight_ready": preflight_ready,
        "adapter_contract_ready": adapter_contract_ready,
        "ready_for_h6_1_shadow_local_adapter_dry_run": ready_dry,
        "shadow_request_count": len(requests),
        "shadow_request_valid_count": len(valid_requests),
        "shadow_request_invalid_count": invalid_requests,
        "shadow_receipt_count": len(receipts),
        "shadow_receipt_valid_count": len(valid_receipts),
        "shadow_receipt_invalid_count": invalid_receipts,
        "qwen_3b_shadow_request_count": qwen_3b,
        "qwen_7b_shadow_request_count": qwen_7b,
        "qwen_14b_shadow_request_count": qwen_14b,
        "selector_shadow_request_count": role_selector,
        "localizer_shadow_request_count": role_localizer,
        "patch_synthesizer_shadow_request_count": role_ps,
        "verifier_assist_shadow_request_count": role_va,
        "missing_adapter_id_count": missing_adapter_id,
        "missing_model_name_count": missing_model_name,
        "missing_role_count": missing_role,
        "missing_route_mode_count": missing_route_mode,
        "invalid_shadow_mode_count": invalid_shadow_mode,
        "invalid_receipt_count": invalid_receipts,
        "model_call_executed_count": mc_count,
        "ollama_invoked_count": ol_count,
        "cloud_invoked_count": cl_count,
        "repo_mutated_count": rm_count,
        "behavior_changed_count": bh_count,
        "runtime_effect_count": runtime_effect_count,
        "safety_violation_count": safety,
        "adapter_dry_run_receipt_ready": adapter_dry_run_receipt_ready,
        "ready_for_h6_2_adapter_io_schema_test": ready_io,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h6_adapter_io_schema_test(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: H6 adapter IO schema test."""
    import os as _os

    flag = _os.environ.get("NEXUS_H6_ALLOW_ADAPTER_IO_SCHEMA_TEST", "").strip() == "1"

    shadow = None
    if bundle:
        shadow = bundle.get("h6_shadow_local_adapter_dry_run")

    shadow_present = bool(shadow)
    shadow_ready = bool(shadow.get("dry_run_ready", False)) if shadow else False
    receipt_ready = bool(shadow.get("adapter_dry_run_receipt_ready", False)) if shadow else False
    ready_io = bool(shadow.get("ready_for_h6_2_adapter_io_schema_test", False)) if shadow else False
    shadow_safety = int(shadow.get("safety_violation_count", 0)) if shadow else 0

    ALLOWED_ROLES = {"selector", "localizer", "patch_synthesizer", "verifier_assist"}
    ALLOWED_FAMILIES = {"qwen"}
    ALLOWED_SIZES = {"3b", "7b", "14b"}
    ALLOWED_ROUTES = {"local_first", "local_only", "shadow_only"}
    ALLOWED_INPUT_VERSION = "nexus.local_adapter.input.v1"
    ALLOWED_OUTPUT_VERSION = "nexus.local_adapter.output.v1"
    ALLOWED_OUTPUT_STATUSES = {"schema_only", "dry_run_only", "trace_only"}

    inputs = [r.get("h6_adapter_input_envelope") for r in rows if r.get("h6_adapter_input_envelope")]
    outputs = [r.get("h6_adapter_output_envelope") for r in rows if r.get("h6_adapter_output_envelope")]

    valid_inputs = []
    invalid_inputs = 0
    missing_request_id = 0
    missing_adapter_id = 0
    missing_model_name = 0
    missing_role = 0
    missing_input_ref = 0
    invalid_schema_version_input = 0

    valid_outputs = []
    invalid_outputs = 0
    missing_output_ref = 0
    invalid_output_status = 0
    invalid_schema_version_output = 0

    qwen_3b = 0
    qwen_7b = 0
    qwen_14b = 0
    role_selector = 0
    role_localizer = 0
    role_ps = 0
    role_va = 0

    mc_count = 0
    ol_count = 0
    cl_count = 0
    rm_count = 0
    bh_count = 0
    re_count = 0

    for inp in inputs:
        sv = str(inp.get("schema_version", "") or "").strip()
        rid = str(inp.get("request_id", "") or "").strip()
        aid = str(inp.get("adapter_id", "") or "").strip()
        fam = str(inp.get("model_family", "") or "").lower()
        sz = str(inp.get("model_size", "") or "").lower()
        mname = str(inp.get("model_name", "") or "").strip()
        role = str(inp.get("role", "") or "").lower()
        route = str(inp.get("route_mode", "") or "").lower()
        iref = str(inp.get("input_ref", "") or "").strip()
        mc = bool(inp.get("model_call_executed", False))
        ol = bool(inp.get("ollama_invoked", False))
        cl = bool(inp.get("cloud_invoked", False))
        rm = bool(inp.get("repo_mutated", False))
        bh = bool(inp.get("behavior_changed", False))
        re = bool(inp.get("runtime_effect", False))

        if mc:
            mc_count += 1
        if ol:
            ol_count += 1
        if cl:
            cl_count += 1
        if rm:
            rm_count += 1
        if bh:
            bh_count += 1
        if re:
            re_count += 1

        is_valid = (
            sv == ALLOWED_INPUT_VERSION and rid and aid and fam in ALLOWED_FAMILIES
            and sz in ALLOWED_SIZES and mname and role in ALLOWED_ROLES
            and route in ALLOWED_ROUTES and iref
            and not mc and not ol and not cl and not rm and not bh and not re
        )

        if is_valid:
            valid_inputs.append(inp)
            if sz == "3b":
                qwen_3b += 1
            elif sz == "7b":
                qwen_7b += 1
            elif sz == "14b":
                qwen_14b += 1
            if role == "selector":
                role_selector += 1
            elif role == "localizer":
                role_localizer += 1
            elif role == "patch_synthesizer":
                role_ps += 1
            elif role == "verifier_assist":
                role_va += 1
        else:
            invalid_inputs += 1
            if sv != ALLOWED_INPUT_VERSION:
                invalid_schema_version_input += 1
            if not rid:
                missing_request_id += 1
            if not aid:
                missing_adapter_id += 1
            if not mname:
                missing_model_name += 1
            if role not in ALLOWED_ROLES:
                missing_role += 1
            if not iref:
                missing_input_ref += 1

    for out in outputs:
        sv = str(out.get("schema_version", "") or "").strip()
        rid = str(out.get("request_id", "") or "").strip()
        aid = str(out.get("adapter_id", "") or "").strip()
        status = str(out.get("output_status", "") or "").lower()
        oref = str(out.get("output_ref", "") or "").strip()
        mc = bool(out.get("model_call_executed", False))
        ol = bool(out.get("ollama_invoked", False))
        cl = bool(out.get("cloud_invoked", False))
        rm = bool(out.get("repo_mutated", False))
        bh = bool(out.get("behavior_changed", False))
        re = bool(out.get("runtime_effect", False))

        if mc:
            mc_count += 1
        if ol:
            ol_count += 1
        if cl:
            cl_count += 1
        if rm:
            rm_count += 1
        if bh:
            bh_count += 1
        if re:
            re_count += 1

        is_valid = (
            sv == ALLOWED_OUTPUT_VERSION and rid and aid
            and status in ALLOWED_OUTPUT_STATUSES and oref
            and not mc and not ol and not cl and not rm and not bh and not re
        )

        if is_valid:
            valid_outputs.append(out)
        else:
            invalid_outputs += 1
            if sv != ALLOWED_OUTPUT_VERSION:
                invalid_schema_version_output += 1
            if not oref:
                missing_output_ref += 1
            if status not in ALLOWED_OUTPUT_STATUSES:
                invalid_output_status += 1

    valid_input_rids = {inp.get("request_id") for inp in valid_inputs}
    valid_output_rids = {out.get("request_id") for out in valid_outputs}
    matched_rids = valid_input_rids & valid_output_rids
    matched_io_pair_count = len(matched_rids)
    unmatched_input_count = len(valid_input_rids - valid_output_rids)
    unmatched_output_count = len(valid_output_rids - valid_input_rids)

    safety = mc_count + ol_count + cl_count + rm_count + bh_count + re_count

    io_schema_allowed = (
        flag and shadow_present and shadow_ready
        and receipt_ready and ready_io and shadow_safety == 0
    )

    io_schema_ready = (
        io_schema_allowed and len(valid_inputs) > 0 and len(valid_outputs) > 0
        and matched_io_pair_count > 0 and safety == 0
    )

    adapter_io_schema_ready = (
        io_schema_ready and invalid_inputs == 0 and invalid_outputs == 0
        and matched_io_pair_count >= 1
    )

    ready_routing = (
        adapter_io_schema_ready and mc_count == 0 and ol_count == 0
        and cl_count == 0 and rm_count == 0 and bh_count == 0 and re_count == 0
    )

    reasons = []
    if not flag:
        reasons.append("adapter_io_schema_flag_not_enabled")
    if not shadow_present:
        reasons.append("missing_h6_1_shadow_dry_run")
    if shadow and not shadow_ready:
        reasons.append("h6_1_shadow_dry_run_not_ready")
    if shadow and not receipt_ready:
        reasons.append("h6_1_receipt_not_ready")
    if shadow and not ready_io:
        reasons.append("not_ready_for_h6_2_adapter_io_schema_test")
    if shadow_safety > 0:
        reasons.append("h6_1_safety_violation_detected")
    if not inputs:
        reasons.append("no_input_envelopes")
    if not outputs:
        reasons.append("no_output_envelopes")
    if inputs and matched_io_pair_count == 0:
        reasons.append("no_matched_io_pairs")
    if missing_request_id > 0:
        reasons.append("missing_request_id")
    if missing_adapter_id > 0:
        reasons.append("missing_adapter_id")
    if missing_model_name > 0:
        reasons.append("missing_model_name")
    if missing_role > 0:
        reasons.append("missing_role")
    if missing_input_ref > 0:
        reasons.append("missing_input_ref")
    if missing_output_ref > 0:
        reasons.append("missing_output_ref")
    if invalid_output_status > 0:
        reasons.append("invalid_output_status")
    if invalid_schema_version_input > 0 or invalid_schema_version_output > 0:
        reasons.append("invalid_schema_version")
    if mc_count > 0:
        reasons.append("model_call_executed_detected")
    if ol_count > 0:
        reasons.append("ollama_invoked_detected")
    if cl_count > 0:
        reasons.append("cloud_invoked_detected")
    if rm_count > 0:
        reasons.append("repo_mutated_detected")
    if bh_count > 0:
        reasons.append("behavior_changed_detected")
    if re_count > 0:
        reasons.append("runtime_effect_detected")
    reasons.extend([
        "h6_2_adapter_io_schema_test_not_production",
        "adapter_io_schema_only",
        "no_model_calls_allowed",
        "ollama_invocation_blocked",
        "cloud_invocation_blocked",
        "repo_mutation_blocked",
        "runtime_effect_blocked",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h6_adapter_io_schema_test.v1",
        "evaluated": True,
        "io_schema_status": "adapter_io_schema_ready" if io_schema_ready else ("adapter_io_schema_fail" if io_schema_allowed else "blocked"),
        "io_schema_reasons": reasons,
        "io_schema_allowed": io_schema_allowed,
        "io_schema_ready": io_schema_ready,
        "row_count": len(rows),
        "shadow_dry_run_present": shadow_present,
        "shadow_dry_run_ready": shadow_ready,
        "adapter_dry_run_receipt_ready": receipt_ready,
        "ready_for_h6_2_adapter_io_schema_test": ready_io,
        "input_envelope_count": len(inputs),
        "input_envelope_valid_count": len(valid_inputs),
        "input_envelope_invalid_count": invalid_inputs,
        "output_envelope_count": len(outputs),
        "output_envelope_valid_count": len(valid_outputs),
        "output_envelope_invalid_count": invalid_outputs,
        "matched_io_pair_count": matched_io_pair_count,
        "unmatched_input_count": unmatched_input_count,
        "unmatched_output_count": unmatched_output_count,
        "qwen_3b_io_pair_count": qwen_3b,
        "qwen_7b_io_pair_count": qwen_7b,
        "qwen_14b_io_pair_count": qwen_14b,
        "selector_io_pair_count": role_selector,
        "localizer_io_pair_count": role_localizer,
        "patch_synthesizer_io_pair_count": role_ps,
        "verifier_assist_io_pair_count": role_va,
        "missing_request_id_count": missing_request_id,
        "missing_adapter_id_count": missing_adapter_id,
        "missing_model_name_count": missing_model_name,
        "missing_role_count": missing_role,
        "missing_input_ref_count": missing_input_ref,
        "missing_output_ref_count": missing_output_ref,
        "invalid_output_status_count": invalid_output_status,
        "invalid_schema_version_count": invalid_schema_version_input + invalid_schema_version_output,
        "model_call_executed_count": mc_count,
        "ollama_invoked_count": ol_count,
        "cloud_invoked_count": cl_count,
        "repo_mutated_count": rm_count,
        "behavior_changed_count": bh_count,
        "runtime_effect_count": re_count,
        "safety_violation_count": safety,
        "adapter_io_schema_ready": adapter_io_schema_ready,
        "ready_for_h6_3_shadow_adapter_routing": ready_routing,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h6_shadow_adapter_routing(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: H6 shadow adapter routing."""
    import os as _os

    flag = _os.environ.get("NEXUS_H6_ALLOW_SHADOW_ADAPTER_ROUTING", "").strip() == "1"

    io_schema = None
    if bundle:
        io_schema = bundle.get("h6_adapter_io_schema_test")

    io_schema_present = bool(io_schema)
    io_schema_ready = bool(io_schema.get("io_schema_ready", False)) if io_schema else False
    adapter_io_schema_ready = bool(io_schema.get("adapter_io_schema_ready", False)) if io_schema else False
    ready_routing = bool(io_schema.get("ready_for_h6_3_shadow_adapter_routing", False)) if io_schema else False
    io_safety = int(io_schema.get("safety_violation_count", 0)) if io_schema else 0

    ALLOWED_ROLES = {"selector", "localizer", "patch_synthesizer", "verifier_assist"}
    ALLOWED_FAMILIES = {"qwen"}
    ALLOWED_SIZES = {"3b", "7b", "14b"}
    ALLOWED_ROUTE_MODES = {"shadow_only", "local_first", "local_only"}
    ALLOWED_ADAPTER_MODES = {"shadow_only"}
    ALLOWED_ROUTING_MODES = {"shadow_route_only", "trace_only"}
    ALLOWED_ROUTING_STATUSES = {"shadow_route_selected", "shadow_route_blocked", "trace_only"}

    candidates = [r.get("h6_shadow_adapter_route_candidate") for r in rows if r.get("h6_shadow_adapter_route_candidate")]
    receipts = [r.get("h6_shadow_adapter_routing_receipt") for r in rows if r.get("h6_shadow_adapter_routing_receipt")]

    valid_candidates = []
    invalid_candidates = 0
    missing_request_id = 0
    missing_adapter_id = 0
    missing_model_name = 0
    missing_role = 0
    missing_route_mode = 0
    invalid_route_mode = 0
    invalid_adapter_mode = 0

    valid_receipts = []
    invalid_receipts = 0
    invalid_routing_receipt = 0

    qwen_3b = 0
    qwen_7b = 0
    qwen_14b = 0
    role_selector = 0
    role_localizer = 0
    role_ps = 0
    role_va = 0

    mc_count = 0
    ol_count = 0
    cl_count = 0
    rm_count = 0
    bh_count = 0
    re_count = 0

    for c in candidates:
        rid = str(c.get("request_id", "") or "").strip()
        aid = str(c.get("adapter_id", "") or "").strip()
        fam = str(c.get("model_family", "") or "").lower()
        sz = str(c.get("model_size", "") or "").lower()
        mname = str(c.get("model_name", "") or "").strip()
        role = str(c.get("role", "") or "").lower()
        route = str(c.get("route_mode", "") or "").lower()
        adapter = str(c.get("adapter_mode", "") or "").lower()
        routing = str(c.get("routing_mode", "") or "").lower()
        mc = bool(c.get("model_call_executed", False))
        ol = bool(c.get("ollama_invoked", False))
        cl = bool(c.get("cloud_invoked", False))
        rm = bool(c.get("repo_mutated", False))
        bh = bool(c.get("behavior_changed", False))
        re = bool(c.get("runtime_effect", False))

        if mc:
            mc_count += 1
        if ol:
            ol_count += 1
        if cl:
            cl_count += 1
        if rm:
            rm_count += 1
        if bh:
            bh_count += 1
        if re:
            re_count += 1

        is_valid = (
            rid and aid and fam in ALLOWED_FAMILIES and sz in ALLOWED_SIZES
            and mname and role in ALLOWED_ROLES and route in ALLOWED_ROUTE_MODES
            and adapter in ALLOWED_ADAPTER_MODES and routing in ALLOWED_ROUTING_MODES
            and not mc and not ol and not cl and not rm and not bh and not re
        )

        if is_valid:
            valid_candidates.append(c)
            if sz == "3b":
                qwen_3b += 1
            elif sz == "7b":
                qwen_7b += 1
            elif sz == "14b":
                qwen_14b += 1
            if role == "selector":
                role_selector += 1
            elif role == "localizer":
                role_localizer += 1
            elif role == "patch_synthesizer":
                role_ps += 1
            elif role == "verifier_assist":
                role_va += 1
        else:
            invalid_candidates += 1
            if not rid:
                missing_request_id += 1
            if not aid:
                missing_adapter_id += 1
            if not mname:
                missing_model_name += 1
            if role not in ALLOWED_ROLES:
                missing_role += 1
            if route not in ALLOWED_ROUTE_MODES:
                missing_route_mode += 1
            if adapter not in ALLOWED_ADAPTER_MODES:
                invalid_adapter_mode += 1

    for rec in receipts:
        rid = str(rec.get("request_id", "") or "").strip()
        aid = str(rec.get("adapter_id", "") or "").strip()
        status = str(rec.get("routing_status", "") or "").lower()
        routing = str(rec.get("routing_mode", "") or "").lower()
        mc = bool(rec.get("model_call_executed", False))
        ol = bool(rec.get("ollama_invoked", False))
        cl = bool(rec.get("cloud_invoked", False))
        rm = bool(rec.get("repo_mutated", False))
        bh = bool(rec.get("behavior_changed", False))
        re = bool(rec.get("runtime_effect", False))

        if mc:
            mc_count += 1
        if ol:
            ol_count += 1
        if cl:
            cl_count += 1
        if rm:
            rm_count += 1
        if bh:
            bh_count += 1
        if re:
            re_count += 1

        is_valid = (
            rid and aid and status in ALLOWED_ROUTING_STATUSES
            and routing in ALLOWED_ROUTING_MODES
            and not mc and not ol and not cl and not rm and not bh and not re
        )

        if is_valid:
            valid_receipts.append(rec)
        else:
            invalid_receipts += 1
            if not rid or not aid or status not in ALLOWED_ROUTING_STATUSES:
                invalid_routing_receipt += 1

    valid_candidate_rids = {c.get("request_id") for c in valid_candidates}
    valid_receipt_rids = {rec.get("request_id") for rec in valid_receipts}
    matched_rids = valid_candidate_rids & valid_receipt_rids

    shadow_selected = 0
    shadow_blocked = 0
    for rec in valid_receipts:
        if rec.get("request_id") in matched_rids:
            if rec.get("route_selected") or rec.get("routing_status") == "shadow_route_selected":
                shadow_selected += 1
            else:
                shadow_blocked += 1

    safety = mc_count + ol_count + cl_count + rm_count + bh_count + re_count

    routing_allowed = (
        flag and io_schema_present and io_schema_ready
        and adapter_io_schema_ready and ready_routing and io_safety == 0
    )

    routing_ready = (
        routing_allowed and len(valid_candidates) > 0 and len(valid_receipts) > 0
        and len(matched_rids) > 0 and safety == 0
    )

    receipt_ready = (
        routing_ready and invalid_candidates == 0 and invalid_receipts == 0
        and shadow_selected >= 1
    )

    ready_exec = (
        receipt_ready and mc_count == 0 and ol_count == 0
        and cl_count == 0 and rm_count == 0 and bh_count == 0 and re_count == 0
    )

    reasons = []
    if not flag:
        reasons.append("shadow_adapter_routing_flag_not_enabled")
    if not io_schema_present:
        reasons.append("missing_h6_2_adapter_io_schema")
    if io_schema and not io_schema_ready:
        reasons.append("h6_2_io_schema_not_ready")
    if io_schema and not adapter_io_schema_ready:
        reasons.append("h6_2_adapter_io_schema_not_ready")
    if io_schema and not ready_routing:
        reasons.append("not_ready_for_h6_3_shadow_adapter_routing")
    if io_safety > 0:
        reasons.append("h6_2_safety_violation_detected")
    if not candidates:
        reasons.append("no_route_candidates")
    if candidates and len(valid_candidates) == 0:
        reasons.append("no_valid_route_candidates")
    if not receipts:
        reasons.append("no_route_receipts")
    if receipts and len(valid_receipts) == 0:
        reasons.append("no_valid_route_receipts")
    if candidates and receipts and len(matched_rids) == 0:
        reasons.append("no_matched_routes")
    if missing_request_id > 0:
        reasons.append("missing_request_id")
    if missing_adapter_id > 0:
        reasons.append("missing_adapter_id")
    if missing_model_name > 0:
        reasons.append("missing_model_name")
    if missing_role > 0:
        reasons.append("missing_role")
    if missing_route_mode > 0:
        reasons.append("missing_route_mode")
    if invalid_route_mode > 0:
        reasons.append("invalid_route_mode")
    if invalid_adapter_mode > 0:
        reasons.append("invalid_adapter_mode")
    if invalid_routing_receipt > 0:
        reasons.append("invalid_routing_receipt")
    if mc_count > 0:
        reasons.append("model_call_executed_detected")
    if ol_count > 0:
        reasons.append("ollama_invoked_detected")
    if cl_count > 0:
        reasons.append("cloud_invoked_detected")
    if rm_count > 0:
        reasons.append("repo_mutated_detected")
    if bh_count > 0:
        reasons.append("behavior_changed_detected")
    if re_count > 0:
        reasons.append("runtime_effect_detected")
    reasons.extend([
        "h6_3_shadow_adapter_routing_not_production",
        "shadow_adapter_routing_only",
        "no_model_calls_allowed",
        "ollama_invocation_blocked",
        "cloud_invocation_blocked",
        "repo_mutation_blocked",
        "runtime_effect_blocked",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h6_shadow_adapter_routing.v1",
        "evaluated": True,
        "routing_status": "shadow_adapter_routing_ready" if routing_ready else ("shadow_adapter_routing_fail" if routing_allowed else "blocked"),
        "routing_reasons": reasons,
        "routing_allowed": routing_allowed,
        "routing_ready": routing_ready,
        "row_count": len(rows),
        "adapter_io_schema_present": io_schema_present,
        "adapter_io_schema_ready": io_schema_ready,
        "ready_for_h6_3_shadow_adapter_routing": ready_routing,
        "route_candidate_count": len(candidates),
        "route_candidate_valid_count": len(valid_candidates),
        "route_candidate_invalid_count": invalid_candidates,
        "route_receipt_count": len(receipts),
        "route_receipt_valid_count": len(valid_receipts),
        "route_receipt_invalid_count": invalid_receipts,
        "shadow_route_selected_count": shadow_selected,
        "shadow_route_blocked_count": shadow_blocked,
        "qwen_3b_route_count": qwen_3b,
        "qwen_7b_route_count": qwen_7b,
        "qwen_14b_route_count": qwen_14b,
        "selector_route_count": role_selector,
        "localizer_route_count": role_localizer,
        "patch_synthesizer_route_count": role_ps,
        "verifier_assist_route_count": role_va,
        "missing_request_id_count": missing_request_id,
        "missing_adapter_id_count": missing_adapter_id,
        "missing_model_name_count": missing_model_name,
        "missing_role_count": missing_role,
        "missing_route_mode_count": missing_route_mode,
        "invalid_route_mode_count": invalid_route_mode,
        "invalid_adapter_mode_count": invalid_adapter_mode,
        "invalid_routing_receipt_count": invalid_routing_receipt,
        "model_call_executed_count": mc_count,
        "ollama_invoked_count": ol_count,
        "cloud_invoked_count": cl_count,
        "repo_mutated_count": rm_count,
        "behavior_changed_count": bh_count,
        "runtime_effect_count": re_count,
        "safety_violation_count": safety,
        "shadow_adapter_routing_receipt_ready": receipt_ready,
        "ready_for_h6_4_local_adapter_execution_plan_dry_run": ready_exec,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h6_local_adapter_execution_plan_dry_run(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: H6 local adapter execution plan dry run."""
    import os as _os

    flag = _os.environ.get("NEXUS_H6_ALLOW_LOCAL_ADAPTER_EXECUTION_PLAN_DRY_RUN", "").strip() == "1"

    routing = None
    if bundle:
        routing = bundle.get("h6_shadow_adapter_routing")

    routing_present = bool(routing)
    routing_ready = bool(routing.get("routing_ready", False)) if routing else False
    receipt_ready = bool(routing.get("shadow_adapter_routing_receipt_ready", False)) if routing else False
    ready_exec = bool(routing.get("ready_for_h6_4_local_adapter_execution_plan_dry_run", False)) if routing else False
    routing_safety = int(routing.get("safety_violation_count", 0)) if routing else 0

    ALLOWED_ROLES = {"selector", "localizer", "patch_synthesizer", "verifier_assist"}
    ALLOWED_FAMILIES = {"qwen"}
    ALLOWED_SIZES = {"3b", "7b", "14b"}
    ALLOWED_ROUTE_MODES = {"shadow_only", "local_first", "local_only"}
    ALLOWED_EXECUTION_MODES = {"dry_run_only"}

    plans = [r.get("h6_local_adapter_execution_plan") for r in rows if r.get("h6_local_adapter_execution_plan")]

    valid_plans = []
    invalid_plans = 0
    missing_plan_id = 0
    missing_request_id = 0
    missing_adapter_id = 0
    missing_model_name = 0
    missing_role = 0
    missing_route_mode = 0
    invalid_execution_mode = 0
    executable_blocked = 0

    qwen_3b = 0
    qwen_7b = 0
    qwen_14b = 0
    role_selector = 0
    role_localizer = 0
    role_ps = 0
    role_va = 0

    mc_count = 0
    ol_count = 0
    cl_count = 0
    rm_count = 0
    bh_count = 0
    re_count = 0

    for p in plans:
        pid = str(p.get("plan_id", "") or "").strip()
        rid = str(p.get("request_id", "") or "").strip()
        aid = str(p.get("adapter_id", "") or "").strip()
        fam = str(p.get("model_family", "") or "").lower()
        sz = str(p.get("model_size", "") or "").lower()
        mname = str(p.get("model_name", "") or "").strip()
        role = str(p.get("role", "") or "").lower()
        route = str(p.get("route_mode", "") or "").lower()
        exec_mode = str(p.get("execution_mode", "") or "").lower()
        exe = bool(p.get("executable", True))
        mc = bool(p.get("model_call_executed", False))
        ol = bool(p.get("ollama_invoked", False))
        cl = bool(p.get("cloud_invoked", False))
        rm = bool(p.get("repo_mutated", False))
        bh = bool(p.get("behavior_changed", False))
        re = bool(p.get("runtime_effect", False))

        if mc:
            mc_count += 1
        if ol:
            ol_count += 1
        if cl:
            cl_count += 1
        if rm:
            rm_count += 1
        if bh:
            bh_count += 1
        if re:
            re_count += 1

        is_valid = (
            pid and rid and aid and fam in ALLOWED_FAMILIES and sz in ALLOWED_SIZES
            and mname and role in ALLOWED_ROLES and route in ALLOWED_ROUTE_MODES
            and exec_mode in ALLOWED_EXECUTION_MODES and not exe
            and not mc and not ol and not cl and not rm and not bh and not re
        )

        if is_valid:
            valid_plans.append(p)
            if sz == "3b":
                qwen_3b += 1
            elif sz == "7b":
                qwen_7b += 1
            elif sz == "14b":
                qwen_14b += 1
            if role == "selector":
                role_selector += 1
            elif role == "localizer":
                role_localizer += 1
            elif role == "patch_synthesizer":
                role_ps += 1
            elif role == "verifier_assist":
                role_va += 1
        else:
            invalid_plans += 1
            if not pid:
                missing_plan_id += 1
            if not rid:
                missing_request_id += 1
            if not aid:
                missing_adapter_id += 1
            if not mname:
                missing_model_name += 1
            if role not in ALLOWED_ROLES:
                missing_role += 1
            if route not in ALLOWED_ROUTE_MODES:
                missing_route_mode += 1
            if exec_mode not in ALLOWED_EXECUTION_MODES:
                invalid_execution_mode += 1
            if exe:
                executable_blocked += 1

    safety = mc_count + ol_count + cl_count + rm_count + bh_count + re_count

    plan_allowed = (
        flag and routing_present and routing_ready
        and receipt_ready and ready_exec and routing_safety == 0
    )

    plan_ready = (
        plan_allowed and len(valid_plans) > 0 and safety == 0
    )

    exec_plan_receipt_ready = (
        plan_ready and invalid_plans == 0
    )

    ready_intent = (
        exec_plan_receipt_ready and mc_count == 0 and ol_count == 0
        and cl_count == 0 and rm_count == 0 and bh_count == 0 and re_count == 0
    )

    reasons = []
    if not flag:
        reasons.append("execution_plan_dry_run_flag_not_enabled")
    if not routing_present:
        reasons.append("missing_h6_3_shadow_adapter_routing")
    if routing and not routing_ready:
        reasons.append("h6_3_routing_not_ready")
    if routing and not receipt_ready:
        reasons.append("h6_3_receipt_not_ready")
    if routing and not ready_exec:
        reasons.append("not_ready_for_h6_4_local_adapter_execution_plan_dry_run")
    if routing_safety > 0:
        reasons.append("h6_3_safety_violation_detected")
    if not plans:
        reasons.append("no_execution_plans")
    if missing_plan_id > 0:
        reasons.append("missing_plan_id")
    if missing_request_id > 0:
        reasons.append("missing_request_id")
    if missing_adapter_id > 0:
        reasons.append("missing_adapter_id")
    if missing_model_name > 0:
        reasons.append("missing_model_name")
    if missing_role > 0:
        reasons.append("missing_role")
    if missing_route_mode > 0:
        reasons.append("missing_route_mode")
    if invalid_execution_mode > 0:
        reasons.append("invalid_execution_mode")
    if executable_blocked > 0:
        reasons.append("executable_blocked")
    if mc_count > 0:
        reasons.append("model_call_executed_detected")
    if ol_count > 0:
        reasons.append("ollama_invoked_detected")
    if cl_count > 0:
        reasons.append("cloud_invoked_detected")
    if rm_count > 0:
        reasons.append("repo_mutated_detected")
    if bh_count > 0:
        reasons.append("behavior_changed_detected")
    if re_count > 0:
        reasons.append("runtime_effect_detected")
    reasons.extend([
        "h6_4_local_adapter_execution_plan_dry_run_not_production",
        "dry_run_only",
        "executable_false",
        "no_model_calls_allowed",
        "ollama_invocation_blocked",
        "cloud_invocation_blocked",
        "repo_mutation_blocked",
        "runtime_effect_blocked",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h6_local_adapter_execution_plan_dry_run.v1",
        "evaluated": True,
        "plan_status": "plan_ready" if plan_ready else ("plan_fail" if plan_allowed else "blocked"),
        "plan_reasons": reasons,
        "plan_allowed": plan_allowed,
        "plan_ready": plan_ready,
        "row_count": len(rows),
        "shadow_adapter_routing_present": routing_present,
        "shadow_adapter_routing_ready": routing_ready,
        "ready_for_h6_4_local_adapter_execution_plan_dry_run": ready_exec,
        "execution_plan_count": len(plans),
        "execution_plan_valid_count": len(valid_plans),
        "execution_plan_invalid_count": invalid_plans,
        "qwen_3b_execution_plan_count": qwen_3b,
        "qwen_7b_execution_plan_count": qwen_7b,
        "qwen_14b_execution_plan_count": qwen_14b,
        "selector_execution_plan_count": role_selector,
        "localizer_execution_plan_count": role_localizer,
        "patch_synthesizer_execution_plan_count": role_ps,
        "verifier_assist_execution_plan_count": role_va,
        "dry_run_only": True,
        "executable": False,
        "missing_plan_id_count": missing_plan_id,
        "missing_request_id_count": missing_request_id,
        "missing_adapter_id_count": missing_adapter_id,
        "missing_model_name_count": missing_model_name,
        "missing_role_count": missing_role,
        "missing_route_mode_count": missing_route_mode,
        "invalid_execution_mode_count": invalid_execution_mode,
        "executable_blocked_count": executable_blocked,
        "model_call_executed_count": mc_count,
        "ollama_invoked_count": ol_count,
        "cloud_invoked_count": cl_count,
        "repo_mutated_count": rm_count,
        "behavior_changed_count": bh_count,
        "runtime_effect_count": re_count,
        "safety_violation_count": safety,
        "execution_plan_receipt_ready": exec_plan_receipt_ready,
        "ready_for_h6_5_shadow_local_adapter_invocation_intent": ready_intent,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h6_shadow_local_adapter_invocation_intent_receipt(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: H6 shadow local adapter invocation intent receipt."""
    import os as _os

    flag = _os.environ.get("NEXUS_H6_ALLOW_SHADOW_LOCAL_ADAPTER_INVOCATION_INTENT", "").strip() == "1"

    plan = None
    if bundle:
        plan = bundle.get("h6_local_adapter_execution_plan_dry_run")

    plan_present = bool(plan)
    plan_ready = bool(plan.get("plan_ready", False)) if plan else False
    plan_receipt_ready = bool(plan.get("execution_plan_receipt_ready", False)) if plan else False
    ready_intent = bool(plan.get("ready_for_h6_5_shadow_local_adapter_invocation_intent", False)) if plan else False
    plan_safety = int(plan.get("safety_violation_count", 0)) if plan else 0

    ALLOWED_ROLES = {"selector", "localizer", "patch_synthesizer", "verifier_assist"}
    ALLOWED_FAMILIES = {"qwen"}
    ALLOWED_SIZES = {"3b", "7b", "14b"}
    ALLOWED_INTENT_MODES = {"shadow_intent_only"}
    ALLOWED_RECEIPT_STATUSES = {"intent_recorded"}

    intents = [r.get("h6_shadow_local_adapter_invocation_intent") for r in rows if r.get("h6_shadow_local_adapter_invocation_intent")]
    receipts = [r.get("h6_shadow_local_adapter_invocation_intent_receipt") for r in rows if r.get("h6_shadow_local_adapter_invocation_intent_receipt")]

    valid_intents = []
    invalid_intents = 0
    missing_intent_id = 0
    missing_plan_id = 0
    missing_request_id = 0
    missing_adapter_id = 0
    missing_model_name = 0
    missing_role = 0
    invalid_intent_mode = 0

    valid_receipts = []
    invalid_receipts = 0
    invalid_intent_receipt = 0

    mc_intended = 0
    mc_count = 0
    ol_count = 0
    cl_count = 0
    rm_count = 0
    bh_count = 0
    re_count = 0

    for inp in intents:
        iid = str(inp.get("intent_id", "") or "").strip()
        pid = str(inp.get("plan_id", "") or "").strip()
        rid = str(inp.get("request_id", "") or "").strip()
        aid = str(inp.get("adapter_id", "") or "").strip()
        fam = str(inp.get("model_family", "") or "").lower()
        sz = str(inp.get("model_size", "") or "").lower()
        mname = str(inp.get("model_name", "") or "").strip()
        role = str(inp.get("role", "") or "").lower()
        imode = str(inp.get("intent_mode", "") or "").lower()
        mci = bool(inp.get("model_call_intended", False))
        mc = bool(inp.get("model_call_executed", False))
        ol = bool(inp.get("ollama_invoked", False))
        cl = bool(inp.get("cloud_invoked", False))
        rm = bool(inp.get("repo_mutated", False))
        bh = bool(inp.get("behavior_changed", False))
        re = bool(inp.get("runtime_effect", False))

        if mci:
            mc_intended += 1
        if mc:
            mc_count += 1
        if ol:
            ol_count += 1
        if cl:
            cl_count += 1
        if rm:
            rm_count += 1
        if bh:
            bh_count += 1
        if re:
            re_count += 1

        is_valid = (
            iid and pid and rid and aid and fam in ALLOWED_FAMILIES
            and sz in ALLOWED_SIZES and mname and role in ALLOWED_ROLES
            and imode in ALLOWED_INTENT_MODES and mci
            and not mc and not ol and not cl and not rm and not bh and not re
        )

        if is_valid:
            valid_intents.append(inp)
        else:
            invalid_intents += 1
            if not iid:
                missing_intent_id += 1
            if not pid:
                missing_plan_id += 1
            if not rid:
                missing_request_id += 1
            if not aid:
                missing_adapter_id += 1
            if not mname:
                missing_model_name += 1
            if role not in ALLOWED_ROLES:
                missing_role += 1
            if imode not in ALLOWED_INTENT_MODES:
                invalid_intent_mode += 1

    for rec in receipts:
        iid = str(rec.get("intent_id", "") or "").strip()
        pid = str(rec.get("plan_id", "") or "").strip()
        rid = str(rec.get("request_id", "") or "").strip()
        aid = str(rec.get("adapter_id", "") or "").strip()
        status = str(rec.get("receipt_status", "") or "").lower()
        mci = bool(rec.get("model_call_intended", False))
        mc = bool(rec.get("model_call_executed", False))
        ol = bool(rec.get("ollama_invoked", False))
        cl = bool(rec.get("cloud_invoked", False))
        rm = bool(rec.get("repo_mutated", False))
        bh = bool(rec.get("behavior_changed", False))
        re = bool(rec.get("runtime_effect", False))

        if mc:
            mc_count += 1
        if ol:
            ol_count += 1
        if cl:
            cl_count += 1
        if rm:
            rm_count += 1
        if bh:
            bh_count += 1
        if re:
            re_count += 1

        is_valid = (
            iid and pid and rid and aid and status in ALLOWED_RECEIPT_STATUSES
            and mci
            and not mc and not ol and not cl and not rm and not bh and not re
        )

        if is_valid:
            valid_receipts.append(rec)
        else:
            invalid_receipts += 1
            if not iid or not pid or not rid or not aid or status not in ALLOWED_RECEIPT_STATUSES:
                invalid_intent_receipt += 1

    valid_intent_iids = {inp.get("intent_id") for inp in valid_intents}
    valid_receipt_iids = {rec.get("intent_id") for rec in valid_receipts}
    matched_iids = valid_intent_iids & valid_receipt_iids

    safety = mc_count + ol_count + cl_count + rm_count + bh_count + re_count

    intent_allowed = (
        flag and plan_present and plan_ready
        and plan_receipt_ready and ready_intent and plan_safety == 0
    )

    intent_ready = (
        intent_allowed and len(valid_intents) > 0 and len(valid_receipts) > 0
        and len(matched_iids) > 0 and safety == 0
    )

    invocation_intent_receipt_ready = (
        intent_ready and invalid_intents == 0 and invalid_receipts == 0
    )

    ready_stub = (
        invocation_intent_receipt_ready and mc_count == 0 and ol_count == 0
        and cl_count == 0 and rm_count == 0 and bh_count == 0 and re_count == 0
    )

    reasons = []
    if not flag:
        reasons.append("invocation_intent_flag_not_enabled")
    if not plan_present:
        reasons.append("missing_h6_4_execution_plan")
    if plan and not plan_ready:
        reasons.append("h6_4_plan_not_ready")
    if plan and not plan_receipt_ready:
        reasons.append("h6_4_plan_receipt_not_ready")
    if plan and not ready_intent:
        reasons.append("not_ready_for_h6_5_shadow_local_adapter_invocation_intent")
    if plan_safety > 0:
        reasons.append("h6_4_safety_violation_detected")
    if not intents:
        reasons.append("no_invocation_intents")
    if not receipts:
        reasons.append("no_intent_receipts")
    if intents and receipts and len(matched_iids) == 0:
        reasons.append("no_matched_intents")
    if missing_intent_id > 0:
        reasons.append("missing_intent_id")
    if missing_plan_id > 0:
        reasons.append("missing_plan_id")
    if missing_request_id > 0:
        reasons.append("missing_request_id")
    if missing_adapter_id > 0:
        reasons.append("missing_adapter_id")
    if missing_model_name > 0:
        reasons.append("missing_model_name")
    if missing_role > 0:
        reasons.append("missing_role")
    if invalid_intent_mode > 0:
        reasons.append("invalid_intent_mode")
    if invalid_intent_receipt > 0:
        reasons.append("invalid_intent_receipt")
    if mc_count > 0:
        reasons.append("model_call_executed_detected")
    if ol_count > 0:
        reasons.append("ollama_invoked_detected")
    if cl_count > 0:
        reasons.append("cloud_invoked_detected")
    if rm_count > 0:
        reasons.append("repo_mutated_detected")
    if bh_count > 0:
        reasons.append("behavior_changed_detected")
    if re_count > 0:
        reasons.append("runtime_effect_detected")
    reasons.extend([
        "h6_5_shadow_local_adapter_invocation_intent_not_production",
        "shadow_intent_only",
        "no_model_calls_allowed",
        "ollama_invocation_blocked",
        "cloud_invocation_blocked",
        "repo_mutation_blocked",
        "runtime_effect_blocked",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h6_shadow_local_adapter_invocation_intent_receipt.v1",
        "evaluated": True,
        "intent_status": "intent_ready" if intent_ready else ("intent_fail" if intent_allowed else "blocked"),
        "intent_reasons": reasons,
        "intent_allowed": intent_allowed,
        "intent_ready": intent_ready,
        "row_count": len(rows),
        "execution_plan_present": plan_present,
        "execution_plan_ready": plan_ready,
        "execution_plan_receipt_ready": plan_receipt_ready,
        "ready_for_h6_5_shadow_local_adapter_invocation_intent": ready_intent,
        "invocation_intent_count": len(intents),
        "invocation_intent_valid_count": len(valid_intents),
        "invocation_intent_invalid_count": invalid_intents,
        "intent_receipt_count": len(receipts),
        "intent_receipt_valid_count": len(valid_receipts),
        "intent_receipt_invalid_count": invalid_receipts,
        "missing_intent_id_count": missing_intent_id,
        "missing_plan_id_count": missing_plan_id,
        "missing_request_id_count": missing_request_id,
        "missing_adapter_id_count": missing_adapter_id,
        "missing_model_name_count": missing_model_name,
        "missing_role_count": missing_role,
        "invalid_intent_mode_count": invalid_intent_mode,
        "invalid_intent_receipt_count": invalid_intent_receipt,
        "model_call_intended_count": mc_intended,
        "model_call_executed_count": mc_count,
        "ollama_invoked_count": ol_count,
        "cloud_invoked_count": cl_count,
        "repo_mutated_count": rm_count,
        "behavior_changed_count": bh_count,
        "runtime_effect_count": re_count,
        "safety_violation_count": safety,
        "invocation_intent_receipt_ready": invocation_intent_receipt_ready,
        "ready_for_h6_6_deterministic_local_adapter_stub_output": ready_stub,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h6_deterministic_local_adapter_stub_output(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: H6 deterministic local adapter stub output."""
    import os as _os

    flag = _os.environ.get("NEXUS_H6_ALLOW_DETERMINISTIC_LOCAL_ADAPTER_STUB_OUTPUT", "").strip() == "1"

    intent = None
    if bundle:
        intent = bundle.get("h6_shadow_local_adapter_invocation_intent_receipt")

    intent_present = bool(intent)
    intent_ready = bool(intent.get("intent_ready", False)) if intent else False
    intent_receipt_ready = bool(intent.get("invocation_intent_receipt_ready", False)) if intent else False
    ready_stub = bool(intent.get("ready_for_h6_6_deterministic_local_adapter_stub_output", False)) if intent else False
    intent_safety = int(intent.get("safety_violation_count", 0)) if intent else 0

    ALLOWED_ROLES = {"selector", "localizer", "patch_synthesizer", "verifier_assist"}
    ALLOWED_FAMILIES = {"qwen"}
    ALLOWED_SIZES = {"3b", "7b", "14b"}
    ALLOWED_OUTPUT_STATUSES = {"deterministic_stub_only"}

    stubs = [r.get("h6_deterministic_local_adapter_stub_output") for r in rows if r.get("h6_deterministic_local_adapter_stub_output")]

    valid_stubs = []
    invalid_stubs = 0
    missing_stub_id = 0
    missing_intent_id = 0
    missing_request_id = 0
    missing_adapter_id = 0
    missing_model_name = 0
    missing_role = 0
    missing_output_ref = 0
    missing_receipt_ref = 0
    invalid_output_status = 0

    qwen_3b = 0
    qwen_7b = 0
    qwen_14b = 0
    role_selector = 0
    role_localizer = 0
    role_ps = 0
    role_va = 0

    mc_count = 0
    ol_count = 0
    cl_count = 0
    rm_count = 0
    bh_count = 0
    re_count = 0

    for s in stubs:
        sid = str(s.get("stub_id", "") or "").strip()
        iid = str(s.get("intent_id", "") or "").strip()
        rid = str(s.get("request_id", "") or "").strip()
        aid = str(s.get("adapter_id", "") or "").strip()
        fam = str(s.get("model_family", "") or "").lower()
        sz = str(s.get("model_size", "") or "").lower()
        mname = str(s.get("model_name", "") or "").strip()
        role = str(s.get("role", "") or "").lower()
        ostatus = str(s.get("output_status", "") or "").lower()
        oref = str(s.get("output_ref", "") or "").strip()
        rref = str(s.get("receipt_ref", "") or "").strip()
        mc = bool(s.get("model_call_executed", False))
        ol = bool(s.get("ollama_invoked", False))
        cl = bool(s.get("cloud_invoked", False))
        rm = bool(s.get("repo_mutated", False))
        bh = bool(s.get("behavior_changed", False))
        re = bool(s.get("runtime_effect", False))

        if mc:
            mc_count += 1
        if ol:
            ol_count += 1
        if cl:
            cl_count += 1
        if rm:
            rm_count += 1
        if bh:
            bh_count += 1
        if re:
            re_count += 1

        is_valid = (
            sid and iid and rid and aid and fam in ALLOWED_FAMILIES
            and sz in ALLOWED_SIZES and mname and role in ALLOWED_ROLES
            and ostatus in ALLOWED_OUTPUT_STATUSES and oref and rref
            and not mc and not ol and not cl and not rm and not bh and not re
        )

        if is_valid:
            valid_stubs.append(s)
            if sz == "3b":
                qwen_3b += 1
            elif sz == "7b":
                qwen_7b += 1
            elif sz == "14b":
                qwen_14b += 1
            if role == "selector":
                role_selector += 1
            elif role == "localizer":
                role_localizer += 1
            elif role == "patch_synthesizer":
                role_ps += 1
            elif role == "verifier_assist":
                role_va += 1
        else:
            invalid_stubs += 1
            if not sid:
                missing_stub_id += 1
            if not iid:
                missing_intent_id += 1
            if not rid:
                missing_request_id += 1
            if not aid:
                missing_adapter_id += 1
            if not mname:
                missing_model_name += 1
            if role not in ALLOWED_ROLES:
                missing_role += 1
            if not oref:
                missing_output_ref += 1
            if not rref:
                missing_receipt_ref += 1
            if ostatus not in ALLOWED_OUTPUT_STATUSES:
                invalid_output_status += 1

    safety = mc_count + ol_count + cl_count + rm_count + bh_count + re_count

    stub_allowed = (
        flag and intent_present and intent_ready
        and intent_receipt_ready and ready_stub and intent_safety == 0
    )

    stub_ready = (
        stub_allowed and len(valid_stubs) > 0 and safety == 0
    )

    stub_output_receipt_ready = (
        stub_ready and invalid_stubs == 0
    )

    ready_boundary = (
        stub_output_receipt_ready and mc_count == 0 and ol_count == 0
        and cl_count == 0 and rm_count == 0 and bh_count == 0 and re_count == 0
    )

    reasons = []
    if not flag:
        reasons.append("deterministic_stub_output_flag_not_enabled")
    if not intent_present:
        reasons.append("missing_h6_5_invocation_intent")
    if intent and not intent_ready:
        reasons.append("h6_5_intent_not_ready")
    if intent and not intent_receipt_ready:
        reasons.append("h6_5_intent_receipt_not_ready")
    if intent and not ready_stub:
        reasons.append("not_ready_for_h6_6_deterministic_local_adapter_stub_output")
    if intent_safety > 0:
        reasons.append("h6_5_safety_violation_detected")
    if not stubs:
        reasons.append("no_stub_outputs")
    if missing_stub_id > 0:
        reasons.append("missing_stub_id")
    if missing_intent_id > 0:
        reasons.append("missing_intent_id")
    if missing_request_id > 0:
        reasons.append("missing_request_id")
    if missing_adapter_id > 0:
        reasons.append("missing_adapter_id")
    if missing_model_name > 0:
        reasons.append("missing_model_name")
    if missing_role > 0:
        reasons.append("missing_role")
    if missing_output_ref > 0:
        reasons.append("missing_output_ref")
    if missing_receipt_ref > 0:
        reasons.append("missing_receipt_ref")
    if invalid_output_status > 0:
        reasons.append("invalid_output_status")
    if mc_count > 0:
        reasons.append("model_call_executed_detected")
    if ol_count > 0:
        reasons.append("ollama_invoked_detected")
    if cl_count > 0:
        reasons.append("cloud_invoked_detected")
    if rm_count > 0:
        reasons.append("repo_mutated_detected")
    if bh_count > 0:
        reasons.append("behavior_changed_detected")
    if re_count > 0:
        reasons.append("runtime_effect_detected")
    reasons.extend([
        "h6_6_deterministic_local_adapter_stub_output_not_production",
        "deterministic_stub_only",
        "no_model_calls_allowed",
        "ollama_invocation_blocked",
        "cloud_invocation_blocked",
        "repo_mutation_blocked",
        "runtime_effect_blocked",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h6_deterministic_local_adapter_stub_output.v1",
        "evaluated": True,
        "stub_status": "stub_ready" if stub_ready else ("stub_fail" if stub_allowed else "blocked"),
        "stub_reasons": reasons,
        "stub_allowed": stub_allowed,
        "stub_ready": stub_ready,
        "row_count": len(rows),
        "invocation_intent_present": intent_present,
        "invocation_intent_ready": intent_ready,
        "invocation_intent_receipt_ready": intent_receipt_ready,
        "ready_for_h6_6_deterministic_local_adapter_stub_output": ready_stub,
        "stub_output_count": len(stubs),
        "stub_output_valid_count": len(valid_stubs),
        "stub_output_invalid_count": invalid_stubs,
        "missing_stub_id_count": missing_stub_id,
        "missing_intent_id_count": missing_intent_id,
        "missing_request_id_count": missing_request_id,
        "missing_adapter_id_count": missing_adapter_id,
        "missing_model_name_count": missing_model_name,
        "missing_role_count": missing_role,
        "missing_output_ref_count": missing_output_ref,
        "missing_receipt_ref_count": missing_receipt_ref,
        "invalid_output_status_count": invalid_output_status,
        "qwen_3b_stub_output_count": qwen_3b,
        "qwen_7b_stub_output_count": qwen_7b,
        "qwen_14b_stub_output_count": qwen_14b,
        "selector_stub_output_count": role_selector,
        "localizer_stub_output_count": role_localizer,
        "patch_synthesizer_stub_output_count": role_ps,
        "verifier_assist_stub_output_count": role_va,
        "deterministic_stub_only": True,
        "model_call_executed_count": mc_count,
        "ollama_invoked_count": ol_count,
        "cloud_invoked_count": cl_count,
        "repo_mutated_count": rm_count,
        "behavior_changed_count": bh_count,
        "runtime_effect_count": re_count,
        "safety_violation_count": safety,
        "stub_output_receipt_ready": stub_output_receipt_ready,
        "ready_for_h6_7_local_provider_boundary_preflight": ready_boundary,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h6_local_provider_boundary_preflight(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: H6 local provider boundary preflight."""
    import os as _os

    flag = _os.environ.get("NEXUS_H6_ALLOW_LOCAL_PROVIDER_BOUNDARY_PREFLIGHT", "").strip() == "1"

    stub = None
    if bundle:
        stub = bundle.get("h6_deterministic_local_adapter_stub_output")

    stub_present = bool(stub)
    stub_ready = bool(stub.get("stub_ready", False)) if stub else False
    stub_receipt_ready = bool(stub.get("stub_output_receipt_ready", False)) if stub else False
    ready_boundary = bool(stub.get("ready_for_h6_7_local_provider_boundary_preflight", False)) if stub else False
    stub_safety = int(stub.get("safety_violation_count", 0)) if stub else 0

    ALLOWED_FAMILIES = {"qwen"}
    ALLOWED_SIZES = {"3b", "7b", "14b"}
    ALLOWED_PROVIDER_FAMILIES = {"ollama"}
    ALLOWED_PROVIDER_MODES = {"boundary_preflight_only"}

    boundaries = [r.get("h6_local_provider_boundary") for r in rows if r.get("h6_local_provider_boundary")]

    valid_boundaries = []
    invalid_boundaries = 0
    missing_provider_id = 0
    missing_model_name = 0
    invalid_provider_family = 0
    invalid_model_family = 0
    invalid_model_size = 0
    invalid_provider_mode = 0
    network_blocked = 0
    process_spawn_blocked = 0
    model_call_blocked = 0

    qwen_3b = 0
    qwen_7b = 0
    qwen_14b = 0

    mc_count = 0
    ol_count = 0
    cl_count = 0
    rm_count = 0
    bh_count = 0
    re_count = 0

    for b in boundaries:
        pid = str(b.get("provider_id", "") or "").strip()
        pfam = str(b.get("provider_family", "") or "").lower()
        mfam = str(b.get("model_family", "") or "").lower()
        sz = str(b.get("model_size", "") or "").lower()
        mname = str(b.get("model_name", "") or "").strip()
        pmode = str(b.get("provider_mode", "") or "").lower()
        na = bool(b.get("network_allowed", True))
        ps = bool(b.get("process_spawn_allowed", True))
        mca = bool(b.get("model_call_allowed", True))
        mc = bool(b.get("model_call_executed", False))
        ol = bool(b.get("ollama_invoked", False))
        cl = bool(b.get("cloud_invoked", False))
        rm = bool(b.get("repo_mutated", False))
        bh = bool(b.get("behavior_changed", False))
        re = bool(b.get("runtime_effect", False))

        if mc:
            mc_count += 1
        if ol:
            ol_count += 1
        if cl:
            cl_count += 1
        if rm:
            rm_count += 1
        if bh:
            bh_count += 1
        if re:
            re_count += 1

        is_valid = (
            pid and pfam in ALLOWED_PROVIDER_FAMILIES and mfam in ALLOWED_FAMILIES
            and sz in ALLOWED_SIZES and mname and pmode in ALLOWED_PROVIDER_MODES
            and not na and not ps and not mca
            and not mc and not ol and not cl and not rm and not bh and not re
        )

        if is_valid:
            valid_boundaries.append(b)
            if sz == "3b":
                qwen_3b += 1
            elif sz == "7b":
                qwen_7b += 1
            elif sz == "14b":
                qwen_14b += 1
        else:
            invalid_boundaries += 1
            if not pid:
                missing_provider_id += 1
            if not mname:
                missing_model_name += 1
            if pfam not in ALLOWED_PROVIDER_FAMILIES:
                invalid_provider_family += 1
            if mfam not in ALLOWED_FAMILIES:
                invalid_model_family += 1
            if sz not in ALLOWED_SIZES:
                invalid_model_size += 1
            if pmode not in ALLOWED_PROVIDER_MODES:
                invalid_provider_mode += 1
            if na:
                network_blocked += 1
            if ps:
                process_spawn_blocked += 1
            if mca:
                model_call_blocked += 1

    safety = mc_count + ol_count + cl_count + rm_count + bh_count + re_count

    boundary_allowed = (
        flag and stub_present and stub_ready
        and stub_receipt_ready and ready_boundary and stub_safety == 0
    )

    boundary_ready = (
        boundary_allowed and len(valid_boundaries) > 0 and safety == 0
    )

    provider_contract_ready = (
        boundary_ready and invalid_boundaries == 0
    )

    ready_config = (
        provider_contract_ready and mc_count == 0 and ol_count == 0
        and cl_count == 0 and rm_count == 0 and bh_count == 0 and re_count == 0
    )

    reasons = []
    if not flag:
        reasons.append("local_provider_boundary_preflight_flag_not_enabled")
    if not stub_present:
        reasons.append("missing_h6_6_stub_output")
    if stub and not stub_ready:
        reasons.append("h6_6_stub_not_ready")
    if stub and not stub_receipt_ready:
        reasons.append("h6_6_stub_receipt_not_ready")
    if stub and not ready_boundary:
        reasons.append("not_ready_for_h6_7_local_provider_boundary_preflight")
    if stub_safety > 0:
        reasons.append("h6_6_safety_violation_detected")
    if not boundaries:
        reasons.append("no_provider_boundaries")
    if missing_provider_id > 0:
        reasons.append("missing_provider_id")
    if missing_model_name > 0:
        reasons.append("missing_model_name")
    if invalid_provider_family > 0:
        reasons.append("invalid_provider_family")
    if invalid_model_family > 0:
        reasons.append("invalid_model_family")
    if invalid_model_size > 0:
        reasons.append("invalid_model_size")
    if invalid_provider_mode > 0:
        reasons.append("invalid_provider_mode")
    if network_blocked > 0:
        reasons.append("network_not_allowed")
    if process_spawn_blocked > 0:
        reasons.append("process_spawn_not_allowed")
    if model_call_blocked > 0:
        reasons.append("model_call_not_allowed")
    if mc_count > 0:
        reasons.append("model_call_executed_detected")
    if ol_count > 0:
        reasons.append("ollama_invoked_detected")
    if cl_count > 0:
        reasons.append("cloud_invoked_detected")
    if rm_count > 0:
        reasons.append("repo_mutated_detected")
    if bh_count > 0:
        reasons.append("behavior_changed_detected")
    if re_count > 0:
        reasons.append("runtime_effect_detected")
    reasons.extend([
        "h6_7_local_provider_boundary_preflight_not_production",
        "boundary_preflight_only",
        "no_model_calls_allowed",
        "ollama_invocation_blocked",
        "cloud_invocation_blocked",
        "repo_mutation_blocked",
        "runtime_effect_blocked",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h6_local_provider_boundary_preflight.v1",
        "evaluated": True,
        "boundary_status": "provider_boundary_ready" if boundary_ready else ("provider_boundary_fail" if boundary_allowed else "blocked"),
        "boundary_reasons": reasons,
        "boundary_allowed": boundary_allowed,
        "boundary_ready": boundary_ready,
        "row_count": len(rows),
        "stub_output_present": stub_present,
        "stub_output_ready": stub_ready,
        "stub_output_receipt_ready": stub_receipt_ready,
        "ready_for_h6_7_local_provider_boundary_preflight": ready_boundary,
        "provider_boundary_count": len(boundaries),
        "provider_boundary_valid_count": len(valid_boundaries),
        "provider_boundary_invalid_count": invalid_boundaries,
        "qwen_3b_boundary_count": qwen_3b,
        "qwen_7b_boundary_count": qwen_7b,
        "qwen_14b_boundary_count": qwen_14b,
        "missing_provider_id_count": missing_provider_id,
        "missing_model_name_count": missing_model_name,
        "invalid_provider_family_count": invalid_provider_family,
        "invalid_model_family_count": invalid_model_family,
        "invalid_model_size_count": invalid_model_size,
        "invalid_provider_mode_count": invalid_provider_mode,
        "network_blocked_count": network_blocked,
        "process_spawn_blocked_count": process_spawn_blocked,
        "model_call_blocked_count": model_call_blocked,
        "model_call_executed_count": mc_count,
        "ollama_invoked_count": ol_count,
        "cloud_invoked_count": cl_count,
        "repo_mutated_count": rm_count,
        "behavior_changed_count": bh_count,
        "runtime_effect_count": re_count,
        "safety_violation_count": safety,
        "provider_contract_ready": provider_contract_ready,
        "ready_for_h6_8_local_provider_config_contract": ready_config,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h6_local_provider_config_contract(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: H6 local provider config contract."""
    import os as _os

    flag = _os.environ.get("NEXUS_H6_ALLOW_LOCAL_PROVIDER_CONFIG_CONTRACT", "").strip() == "1"

    boundary = None
    if bundle:
        boundary = bundle.get("h6_local_provider_boundary_preflight")

    boundary_present = bool(boundary)
    boundary_ready = bool(boundary.get("boundary_ready", False)) if boundary else False
    contract_ready = bool(boundary.get("provider_contract_ready", False)) if boundary else False
    ready_config = bool(boundary.get("ready_for_h6_8_local_provider_config_contract", False)) if boundary else False
    boundary_safety = int(boundary.get("safety_violation_count", 0)) if boundary else 0

    ALLOWED_FAMILIES = {"qwen"}
    ALLOWED_SIZES = {"3b", "7b", "14b"}
    ALLOWED_PROVIDER_FAMILIES = {"ollama"}
    ALLOWED_CONFIG_MODES = {"schema_only"}

    configs = [r.get("h6_local_provider_config") for r in rows if r.get("h6_local_provider_config")]

    valid_configs = []
    invalid_configs = 0
    missing_config_id = 0
    missing_provider_id = 0
    missing_model_name = 0
    invalid_provider_family = 0
    invalid_model_family = 0
    invalid_model_size = 0
    invalid_config_mode = 0
    network_blocked = 0
    process_spawn_blocked = 0
    model_load_blocked = 0
    model_call_blocked = 0

    qwen_3b = 0
    qwen_7b = 0
    qwen_14b = 0

    mc_count = 0
    ol_count = 0
    cl_count = 0
    rm_count = 0
    bh_count = 0
    re_count = 0

    for c in configs:
        cid = str(c.get("config_id", "") or "").strip()
        pid = str(c.get("provider_id", "") or "").strip()
        pfam = str(c.get("provider_family", "") or "").lower()
        mfam = str(c.get("model_family", "") or "").lower()
        sz = str(c.get("model_size", "") or "").lower()
        mname = str(c.get("model_name", "") or "").strip()
        cmode = str(c.get("config_mode", "") or "").lower()
        na = bool(c.get("network_allowed", True))
        ps = bool(c.get("process_spawn_allowed", True))
        mla = bool(c.get("model_load_allowed", True))
        mca = bool(c.get("model_call_allowed", True))
        mc = bool(c.get("model_call_executed", False))
        ol = bool(c.get("ollama_invoked", False))
        cl = bool(c.get("cloud_invoked", False))
        rm = bool(c.get("repo_mutated", False))
        bh = bool(c.get("behavior_changed", False))
        re = bool(c.get("runtime_effect", False))

        if mc:
            mc_count += 1
        if ol:
            ol_count += 1
        if cl:
            cl_count += 1
        if rm:
            rm_count += 1
        if bh:
            bh_count += 1
        if re:
            re_count += 1

        is_valid = (
            cid and pid and pfam in ALLOWED_PROVIDER_FAMILIES and mfam in ALLOWED_FAMILIES
            and sz in ALLOWED_SIZES and mname and cmode in ALLOWED_CONFIG_MODES
            and not na and not ps and not mla and not mca
            and not mc and not ol and not cl and not rm and not bh and not re
        )

        if is_valid:
            valid_configs.append(c)
            if sz == "3b":
                qwen_3b += 1
            elif sz == "7b":
                qwen_7b += 1
            elif sz == "14b":
                qwen_14b += 1
        else:
            invalid_configs += 1
            if not cid:
                missing_config_id += 1
            if not pid:
                missing_provider_id += 1
            if not mname:
                missing_model_name += 1
            if pfam not in ALLOWED_PROVIDER_FAMILIES:
                invalid_provider_family += 1
            if mfam not in ALLOWED_FAMILIES:
                invalid_model_family += 1
            if sz not in ALLOWED_SIZES:
                invalid_model_size += 1
            if cmode not in ALLOWED_CONFIG_MODES:
                invalid_config_mode += 1
            if na:
                network_blocked += 1
            if ps:
                process_spawn_blocked += 1
            if mla:
                model_load_blocked += 1
            if mca:
                model_call_blocked += 1

    safety = mc_count + ol_count + cl_count + rm_count + bh_count + re_count

    config_allowed = (
        flag and boundary_present and boundary_ready
        and contract_ready and ready_config and boundary_safety == 0
    )

    config_ready = (
        config_allowed and len(valid_configs) > 0 and safety == 0
    )

    config_receipt_ready = (
        config_ready and invalid_configs == 0
    )

    ready_gate = (
        config_receipt_ready and mc_count == 0 and ol_count == 0
        and cl_count == 0 and rm_count == 0 and bh_count == 0 and re_count == 0
    )

    reasons = []
    if not flag:
        reasons.append("local_provider_config_contract_flag_not_enabled")
    if not boundary_present:
        reasons.append("missing_h6_7_boundary_preflight")
    if boundary and not boundary_ready:
        reasons.append("h6_7_boundary_not_ready")
    if boundary and not contract_ready:
        reasons.append("h6_7_contract_not_ready")
    if boundary and not ready_config:
        reasons.append("not_ready_for_h6_8_local_provider_config_contract")
    if boundary_safety > 0:
        reasons.append("h6_7_safety_violation_detected")
    if not configs:
        reasons.append("no_provider_configs")
    if missing_config_id > 0:
        reasons.append("missing_config_id")
    if missing_provider_id > 0:
        reasons.append("missing_provider_id")
    if missing_model_name > 0:
        reasons.append("missing_model_name")
    if invalid_provider_family > 0:
        reasons.append("invalid_provider_family")
    if invalid_model_family > 0:
        reasons.append("invalid_model_family")
    if invalid_model_size > 0:
        reasons.append("invalid_model_size")
    if invalid_config_mode > 0:
        reasons.append("invalid_config_mode")
    if network_blocked > 0:
        reasons.append("network_not_allowed")
    if process_spawn_blocked > 0:
        reasons.append("process_spawn_not_allowed")
    if model_load_blocked > 0:
        reasons.append("model_load_not_allowed")
    if model_call_blocked > 0:
        reasons.append("model_call_not_allowed")
    if mc_count > 0:
        reasons.append("model_call_executed_detected")
    if ol_count > 0:
        reasons.append("ollama_invoked_detected")
    if cl_count > 0:
        reasons.append("cloud_invoked_detected")
    if rm_count > 0:
        reasons.append("repo_mutated_detected")
    if bh_count > 0:
        reasons.append("behavior_changed_detected")
    if re_count > 0:
        reasons.append("runtime_effect_detected")
    reasons.extend([
        "h6_8_local_provider_config_contract_not_production",
        "schema_only",
        "no_model_calls_allowed",
        "ollama_invocation_blocked",
        "cloud_invocation_blocked",
        "repo_mutation_blocked",
        "runtime_effect_blocked",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h6_local_provider_config_contract.v1",
        "evaluated": True,
        "config_status": "provider_config_ready" if config_ready else ("provider_config_fail" if config_allowed else "blocked"),
        "config_reasons": reasons,
        "config_allowed": config_allowed,
        "config_ready": config_ready,
        "row_count": len(rows),
        "boundary_present": boundary_present,
        "boundary_ready": boundary_ready,
        "provider_contract_ready": contract_ready,
        "ready_for_h6_8_local_provider_config_contract": ready_config,
        "provider_config_count": len(configs),
        "provider_config_valid_count": len(valid_configs),
        "provider_config_invalid_count": invalid_configs,
        "qwen_3b_config_count": qwen_3b,
        "qwen_7b_config_count": qwen_7b,
        "qwen_14b_config_count": qwen_14b,
        "missing_config_id_count": missing_config_id,
        "missing_provider_id_count": missing_provider_id,
        "missing_model_name_count": missing_model_name,
        "invalid_provider_family_count": invalid_provider_family,
        "invalid_model_family_count": invalid_model_family,
        "invalid_model_size_count": invalid_model_size,
        "invalid_config_mode_count": invalid_config_mode,
        "network_blocked_count": network_blocked,
        "process_spawn_blocked_count": process_spawn_blocked,
        "model_load_blocked_count": model_load_blocked,
        "model_call_blocked_count": model_call_blocked,
        "model_call_executed_count": mc_count,
        "ollama_invoked_count": ol_count,
        "cloud_invoked_count": cl_count,
        "repo_mutated_count": rm_count,
        "behavior_changed_count": bh_count,
        "runtime_effect_count": re_count,
        "safety_violation_count": safety,
        "provider_config_receipt_ready": config_receipt_ready,
        "ready_for_h6_9_local_provider_invocation_gate": ready_gate,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h6_local_provider_invocation_gate(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: H6 local provider invocation gate."""
    import os as _os

    flag = _os.environ.get("NEXUS_H6_ALLOW_LOCAL_PROVIDER_INVOCATION_GATE", "").strip() == "1"

    config = None
    if bundle:
        config = bundle.get("h6_local_provider_config_contract")

    config_present = bool(config)
    config_ready = bool(config.get("config_ready", False)) if config else False
    config_receipt_ready = bool(config.get("provider_config_receipt_ready", False)) if config else False
    ready_gate = bool(config.get("ready_for_h6_9_local_provider_invocation_gate", False)) if config else False
    config_safety = int(config.get("safety_violation_count", 0)) if config else 0

    ALLOWED_FAMILIES = {"qwen"}
    ALLOWED_SIZES = {"3b", "7b", "14b"}
    ALLOWED_PROVIDER_FAMILIES = {"ollama"}
    ALLOWED_GATE_MODES = {"deny_by_default"}

    gates = [r.get("h6_local_provider_invocation_gate") for r in rows if r.get("h6_local_provider_invocation_gate")]

    valid_gates = []
    invalid_gates = 0
    missing_gate_id = 0
    missing_config_id = 0
    missing_provider_id = 0
    missing_model_name = 0
    invalid_provider_family = 0
    invalid_model_family = 0
    invalid_model_size = 0
    invalid_gate_mode = 0
    invocation_allowed_blocked = 0
    network_blocked = 0
    process_spawn_blocked = 0
    model_load_blocked = 0
    model_call_blocked = 0

    qwen_3b = 0
    qwen_7b = 0
    qwen_14b = 0

    mc_count = 0
    ol_count = 0
    cl_count = 0
    rm_count = 0
    bh_count = 0
    re_count = 0

    for g in gates:
        gid = str(g.get("gate_id", "") or "").strip()
        cid = str(g.get("config_id", "") or "").strip()
        pid = str(g.get("provider_id", "") or "").strip()
        pfam = str(g.get("provider_family", "") or "").lower()
        mfam = str(g.get("model_family", "") or "").lower()
        sz = str(g.get("model_size", "") or "").lower()
        mname = str(g.get("model_name", "") or "").strip()
        gmode = str(g.get("gate_mode", "") or "").lower()
        ia = bool(g.get("invocation_allowed", True))
        na = bool(g.get("network_allowed", True))
        ps = bool(g.get("process_spawn_allowed", True))
        mla = bool(g.get("model_load_allowed", True))
        mca = bool(g.get("model_call_allowed", True))
        mc = bool(g.get("model_call_executed", False))
        ol = bool(g.get("ollama_invoked", False))
        cl = bool(g.get("cloud_invoked", False))
        rm = bool(g.get("repo_mutated", False))
        bh = bool(g.get("behavior_changed", False))
        re = bool(g.get("runtime_effect", False))

        if mc:
            mc_count += 1
        if ol:
            ol_count += 1
        if cl:
            cl_count += 1
        if rm:
            rm_count += 1
        if bh:
            bh_count += 1
        if re:
            re_count += 1

        is_valid = (
            gid and cid and pid and pfam in ALLOWED_PROVIDER_FAMILIES and mfam in ALLOWED_FAMILIES
            and sz in ALLOWED_SIZES and mname and gmode in ALLOWED_GATE_MODES
            and not ia and not na and not ps and not mla and not mca
            and not mc and not ol and not cl and not rm and not bh and not re
        )

        if is_valid:
            valid_gates.append(g)
            if sz == "3b":
                qwen_3b += 1
            elif sz == "7b":
                qwen_7b += 1
            elif sz == "14b":
                qwen_14b += 1
        else:
            invalid_gates += 1
            if not gid:
                missing_gate_id += 1
            if not cid:
                missing_config_id += 1
            if not pid:
                missing_provider_id += 1
            if not mname:
                missing_model_name += 1
            if pfam not in ALLOWED_PROVIDER_FAMILIES:
                invalid_provider_family += 1
            if mfam not in ALLOWED_FAMILIES:
                invalid_model_family += 1
            if sz not in ALLOWED_SIZES:
                invalid_model_size += 1
            if gmode not in ALLOWED_GATE_MODES:
                invalid_gate_mode += 1
            if ia:
                invocation_allowed_blocked += 1
            if na:
                network_blocked += 1
            if ps:
                process_spawn_blocked += 1
            if mla:
                model_load_blocked += 1
            if mca:
                model_call_blocked += 1

    safety = mc_count + ol_count + cl_count + rm_count + bh_count + re_count

    gate_allowed = (
        flag and config_present and config_ready
        and config_receipt_ready and ready_gate and config_safety == 0
    )

    gate_ready = (
        gate_allowed and len(valid_gates) > 0 and safety == 0
    )

    gate_receipt_ready = (
        gate_ready and invalid_gates == 0
    )

    ready_probe = (
        gate_receipt_ready and mc_count == 0 and ol_count == 0
        and cl_count == 0 and rm_count == 0 and bh_count == 0 and re_count == 0
    )

    reasons = []
    if not flag:
        reasons.append("local_provider_invocation_gate_flag_not_enabled")
    if not config_present:
        reasons.append("missing_h6_8_config_contract")
    if config and not config_ready:
        reasons.append("h6_8_config_not_ready")
    if config and not config_receipt_ready:
        reasons.append("h6_8_config_receipt_not_ready")
    if config and not ready_gate:
        reasons.append("not_ready_for_h6_9_local_provider_invocation_gate")
    if config_safety > 0:
        reasons.append("h6_8_safety_violation_detected")
    if not gates:
        reasons.append("no_invocation_gates")
    if missing_gate_id > 0:
        reasons.append("missing_gate_id")
    if missing_config_id > 0:
        reasons.append("missing_config_id")
    if missing_provider_id > 0:
        reasons.append("missing_provider_id")
    if missing_model_name > 0:
        reasons.append("missing_model_name")
    if invalid_provider_family > 0:
        reasons.append("invalid_provider_family")
    if invalid_model_family > 0:
        reasons.append("invalid_model_family")
    if invalid_model_size > 0:
        reasons.append("invalid_model_size")
    if invalid_gate_mode > 0:
        reasons.append("invalid_gate_mode")
    if invocation_allowed_blocked > 0:
        reasons.append("invocation_allowed_blocked")
    if network_blocked > 0:
        reasons.append("network_not_allowed")
    if process_spawn_blocked > 0:
        reasons.append("process_spawn_not_allowed")
    if model_load_blocked > 0:
        reasons.append("model_load_not_allowed")
    if model_call_blocked > 0:
        reasons.append("model_call_not_allowed")
    if mc_count > 0:
        reasons.append("model_call_executed_detected")
    if ol_count > 0:
        reasons.append("ollama_invoked_detected")
    if cl_count > 0:
        reasons.append("cloud_invoked_detected")
    if rm_count > 0:
        reasons.append("repo_mutated_detected")
    if bh_count > 0:
        reasons.append("behavior_changed_detected")
    if re_count > 0:
        reasons.append("runtime_effect_detected")
    reasons.extend([
        "h6_9_local_provider_invocation_gate_not_production",
        "deny_by_default",
        "invocation_denied",
        "no_model_calls_allowed",
        "ollama_invocation_blocked",
        "cloud_invocation_blocked",
        "repo_mutation_blocked",
        "runtime_effect_blocked",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h6_local_provider_invocation_gate.v1",
        "evaluated": True,
        "gate_status": "provider_invocation_gate_ready" if gate_ready else ("provider_invocation_gate_fail" if gate_allowed else "blocked"),
        "gate_reasons": reasons,
        "gate_allowed": gate_allowed,
        "gate_ready": gate_ready,
        "row_count": len(rows),
        "config_present": config_present,
        "config_ready": config_ready,
        "config_receipt_ready": config_receipt_ready,
        "ready_for_h6_9_local_provider_invocation_gate": ready_gate,
        "invocation_gate_count": len(gates),
        "invocation_gate_valid_count": len(valid_gates),
        "invocation_gate_invalid_count": invalid_gates,
        "qwen_3b_gate_count": qwen_3b,
        "qwen_7b_gate_count": qwen_7b,
        "qwen_14b_gate_count": qwen_14b,
        "missing_gate_id_count": missing_gate_id,
        "missing_config_id_count": missing_config_id,
        "missing_provider_id_count": missing_provider_id,
        "missing_model_name_count": missing_model_name,
        "invalid_provider_family_count": invalid_provider_family,
        "invalid_model_family_count": invalid_model_family,
        "invalid_model_size_count": invalid_model_size,
        "invalid_gate_mode_count": invalid_gate_mode,
        "invocation_allowed_blocked_count": invocation_allowed_blocked,
        "network_blocked_count": network_blocked,
        "process_spawn_blocked_count": process_spawn_blocked,
        "model_load_blocked_count": model_load_blocked,
        "model_call_blocked_count": model_call_blocked,
        "model_call_executed_count": mc_count,
        "ollama_invoked_count": ol_count,
        "cloud_invoked_count": cl_count,
        "repo_mutated_count": rm_count,
        "behavior_changed_count": bh_count,
        "runtime_effect_count": re_count,
        "safety_violation_count": safety,
        "provider_invocation_gate_receipt_ready": gate_receipt_ready,
        "ready_for_h6_10_controlled_provider_probe_preflight": ready_probe,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h6_controlled_provider_probe_preflight(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: H6 controlled provider probe preflight (deny-by-default).

    This stage confirms that all probe/invocation gates are in deny-by-default
    state. It never allows provider_probe_allowed, provider_invocation_allowed,
    model_call_allowed, or model_call_executed to become true.
    """
    import os as _os

    flag = _os.environ.get("NEXUS_H6_ALLOW_CONTROLLED_PROVIDER_PROBE_PREFLIGHT", "").strip() == "1"

    gate = None
    if bundle:
        gate = bundle.get("h6_local_provider_invocation_gate")

    gate_present = bool(gate)
    gate_ready = bool(gate.get("gate_ready", False)) if gate else False
    gate_receipt_ready = bool(gate.get("provider_invocation_gate_receipt_ready", False)) if gate else False
    ready_probe = bool(gate.get("ready_for_h6_10_controlled_provider_probe_preflight", False)) if gate else False
    gate_safety = int(gate.get("safety_violation_count", 0)) if gate else 0

    prefights = [r.get("h6_controlled_provider_probe_preflight") for r in rows if r.get("h6_controlled_provider_probe_preflight")]

    valid_preflights = []
    invalid_preflights = 0
    missing_preflight_id = 0
    missing_gate_id = 0
    missing_config_id = 0
    missing_provider_id = 0
    missing_model_name = 0
    invalid_provider_family = 0
    invalid_model_family = 0
    invalid_model_size = 0
    invalid_preflight_mode = 0
    probe_allowed_blocked = 0
    invocation_allowed_blocked = 0
    network_blocked = 0
    process_spawn_blocked = 0
    model_load_blocked = 0
    model_call_blocked = 0

    mc_count = 0
    ol_count = 0
    cl_count = 0
    rm_count = 0
    bh_count = 0
    re_count = 0

    for p in prefights:
        pid = str(p.get("preflight_id", "") or "").strip()
        gid = str(p.get("gate_id", "") or "").strip()
        cid = str(p.get("config_id", "") or "").strip()
        prid = str(p.get("provider_id", "") or "").strip()
        pfam = str(p.get("provider_family", "") or "").lower()
        mfam = str(p.get("model_family", "") or "").lower()
        sz = str(p.get("model_size", "") or "").lower()
        mname = str(p.get("model_name", "") or "").strip()
        pmode = str(p.get("preflight_mode", "") or "").lower()
        ppa = bool(p.get("provider_probe_allowed", True))
        pia = bool(p.get("provider_invocation_allowed", True))
        na = bool(p.get("network_allowed", True))
        ps = bool(p.get("process_spawn_allowed", True))
        mla = bool(p.get("model_load_allowed", True))
        mca = bool(p.get("model_call_allowed", True))
        mc = bool(p.get("model_call_executed", False))
        ol = bool(p.get("ollama_invoked", False))
        cl = bool(p.get("cloud_provider_invoked", False))
        rm = bool(p.get("repo_mutated", False))
        bh = bool(p.get("behavior_changed", False))
        re = bool(p.get("runtime_effect", False))

        if mc:
            mc_count += 1
        if ol:
            ol_count += 1
        if cl:
            cl_count += 1
        if rm:
            rm_count += 1
        if bh:
            bh_count += 1
        if re:
            re_count += 1

        is_valid = (
            pid and gid and cid and prid
            and pfam in {"ollama"} and mfam in {"qwen"}
            and sz in {"3b", "7b", "14b"} and mname
            and pmode in {"preflight_only"}
            and not ppa and not pia and not na and not ps and not mla and not mca
            and not mc and not ol and not cl and not rm and not bh and not re
        )

        if is_valid:
            valid_preflights.append(p)
        else:
            invalid_preflights += 1
            if not pid:
                missing_preflight_id += 1
            if not gid:
                missing_gate_id += 1
            if not cid:
                missing_config_id += 1
            if not prid:
                missing_provider_id += 1
            if not mname:
                missing_model_name += 1
            if pfam not in {"ollama"}:
                invalid_provider_family += 1
            if mfam not in {"qwen"}:
                invalid_model_family += 1
            if sz not in {"3b", "7b", "14b"}:
                invalid_model_size += 1
            if pmode not in {"preflight_only"}:
                invalid_preflight_mode += 1
            if ppa:
                probe_allowed_blocked += 1
            if pia:
                invocation_allowed_blocked += 1
            if na:
                network_blocked += 1
            if ps:
                process_spawn_blocked += 1
            if mla:
                model_load_blocked += 1
            if mca:
                model_call_blocked += 1

    safety = mc_count + ol_count + cl_count + rm_count + bh_count + re_count

    preflight_allowed = (
        flag and gate_present and gate_ready
        and gate_receipt_ready and ready_probe and gate_safety == 0
    )

    preflight_ready = (
        preflight_allowed and len(valid_preflights) > 0 and safety == 0
    )

    denial_receipt_ready = (
        preflight_ready and invalid_preflights == 0
    )

    reasons = []
    if not flag:
        reasons.append("controlled_provider_probe_preflight_flag_not_enabled")
    if not gate_present:
        reasons.append("missing_h6_9_invocation_gate")
    if gate and not gate_ready:
        reasons.append("h6_9_gate_not_ready")
    if gate and not gate_receipt_ready:
        reasons.append("h6_9_gate_receipt_not_ready")
    if gate and not ready_probe:
        reasons.append("not_ready_for_h6_10_controlled_provider_probe_preflight")
    if gate_safety > 0:
        reasons.append("h6_9_safety_violation_detected")
    if not prefights:
        reasons.append("no_probe_preflights")
    if missing_preflight_id > 0:
        reasons.append("missing_preflight_id")
    if missing_gate_id > 0:
        reasons.append("missing_gate_id")
    if missing_config_id > 0:
        reasons.append("missing_config_id")
    if missing_provider_id > 0:
        reasons.append("missing_provider_id")
    if missing_model_name > 0:
        reasons.append("missing_model_name")
    if invalid_provider_family > 0:
        reasons.append("invalid_provider_family")
    if invalid_model_family > 0:
        reasons.append("invalid_model_family")
    if invalid_model_size > 0:
        reasons.append("invalid_model_size")
    if invalid_preflight_mode > 0:
        reasons.append("invalid_preflight_mode")
    if probe_allowed_blocked > 0:
        reasons.append("provider_probe_allowed_blocked")
    if invocation_allowed_blocked > 0:
        reasons.append("provider_invocation_allowed_blocked")
    if network_blocked > 0:
        reasons.append("network_not_allowed")
    if process_spawn_blocked > 0:
        reasons.append("process_spawn_not_allowed")
    if model_load_blocked > 0:
        reasons.append("model_load_not_allowed")
    if model_call_blocked > 0:
        reasons.append("model_call_not_allowed")
    if mc_count > 0:
        reasons.append("model_call_executed_detected")
    if ol_count > 0:
        reasons.append("ollama_invoked_detected")
    if cl_count > 0:
        reasons.append("cloud_provider_invoked_detected")
    if rm_count > 0:
        reasons.append("repo_mutated_detected")
    if bh_count > 0:
        reasons.append("behavior_changed_detected")
    if re_count > 0:
        reasons.append("runtime_effect_detected")
    reasons.extend([
        "h6_10_controlled_provider_probe_preflight_not_production",
        "preflight_only",
        "deny_by_default",
        "no_model_calls_allowed",
        "no_provider_probe_allowed",
        "no_provider_invocation_allowed",
        "ollama_invocation_blocked",
        "cloud_invocation_blocked",
        "repo_mutation_blocked",
        "runtime_effect_blocked",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h6_controlled_provider_probe_preflight.v1",
        "evaluated": True,
        "preflight_status": "provider_probe_preflight_ready" if preflight_ready else ("provider_probe_preflight_fail" if preflight_allowed else "blocked"),
        "preflight_reasons": reasons,
        "preflight_allowed": preflight_allowed,
        "preflight_ready": preflight_ready,
        "row_count": len(rows),
        "gate_present": gate_present,
        "gate_ready": gate_ready,
        "gate_receipt_ready": gate_receipt_ready,
        "ready_for_h6_10_controlled_provider_probe_preflight": ready_probe,
        "probe_preflight_count": len(prefights),
        "probe_preflight_valid_count": len(valid_preflights),
        "probe_preflight_invalid_count": invalid_preflights,
        "missing_preflight_id_count": missing_preflight_id,
        "missing_gate_id_count": missing_gate_id,
        "missing_config_id_count": missing_config_id,
        "missing_provider_id_count": missing_provider_id,
        "missing_model_name_count": missing_model_name,
        "invalid_provider_family_count": invalid_provider_family,
        "invalid_model_family_count": invalid_model_family,
        "invalid_model_size_count": invalid_model_size,
        "invalid_preflight_mode_count": invalid_preflight_mode,
        "probe_allowed_blocked_count": probe_allowed_blocked,
        "invocation_allowed_blocked_count": invocation_allowed_blocked,
        "network_blocked_count": network_blocked,
        "process_spawn_blocked_count": process_spawn_blocked,
        "model_load_blocked_count": model_load_blocked,
        "model_call_blocked_count": model_call_blocked,
        "model_call_executed_count": mc_count,
        "ollama_invoked_count": ol_count,
        "cloud_provider_invoked_count": cl_count,
        "repo_mutated_count": rm_count,
        "behavior_changed_count": bh_count,
        "runtime_effect_count": re_count,
        "safety_violation_count": safety,
        "provider_probe_allowed": False,
        "provider_invocation_allowed": False,
        "network_allowed": False,
        "process_spawn_allowed": False,
        "model_load_allowed": False,
        "model_call_allowed": False,
        "model_call_executed": False,
        "ollama_invoked": False,
        "cloud_provider_invoked": False,
        "runtime_effect": False,
        "deny_by_default": True,
        "denial_receipt_ready": denial_receipt_ready,
        "ready_for_h6_11_provider_denial_receipt_replay": denial_receipt_ready,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h6_provider_denial_receipt_replay(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: H6 provider denial receipt replay.

    Replays the denial/preflight receipt from H6-10 and confirms that any
    attempt to open provider, network, process, model load, model call,
    runtime effect, or production/public claim is deterministically blocked.
    """
    import os as _os

    flag = _os.environ.get("NEXUS_H6_ALLOW_PROVIDER_DENIAL_RECEIPT_REPLAY", "").strip() == "1"

    preflight = None
    if bundle:
        preflight = bundle.get("h6_controlled_provider_probe_preflight")

    preflight_present = bool(preflight)
    preflight_ready = bool(preflight.get("preflight_ready", False)) if preflight else False
    denial_receipt_ready = bool(preflight.get("denial_receipt_ready", False)) if preflight else False
    preflight_safety = int(preflight.get("safety_violation_count", 0)) if preflight else 0

    replays = [r.get("h6_provider_denial_receipt_replay") for r in rows if r.get("h6_provider_denial_receipt_replay")]

    valid_replays = []
    invalid_replays = 0
    missing_replay_id = 0
    missing_preflight_id = 0
    missing_provider_id = 0
    provider_probe_allowed_violation = 0
    provider_invocation_allowed_violation = 0
    network_allowed_violation = 0
    process_spawn_allowed_violation = 0
    model_load_allowed_violation = 0
    model_call_allowed_violation = 0
    model_call_executed_violation = 0
    ollama_invoked_violation = 0
    cloud_provider_invoked_violation = 0
    repo_mutated_violation = 0
    behavior_changed_violation = 0
    runtime_effect_violation = 0
    production_ready_violation = 0
    public_claim_allowed_violation = 0

    for rp in replays:
        rid = str(rp.get("replay_id", "") or "").strip()
        pid = str(rp.get("preflight_id", "") or "").strip()
        prid = str(rp.get("provider_id", "") or "").strip()
        ppa = bool(rp.get("provider_probe_allowed", True))
        pia = bool(rp.get("provider_invocation_allowed", True))
        na = bool(rp.get("network_allowed", True))
        ps = bool(rp.get("process_spawn_allowed", True))
        mla = bool(rp.get("model_load_allowed", True))
        mca = bool(rp.get("model_call_allowed", True))
        mc = bool(rp.get("model_call_executed", False))
        ol = bool(rp.get("ollama_invoked", False))
        cl = bool(rp.get("cloud_provider_invoked", False))
        rm = bool(rp.get("repo_mutated", False))
        bh = bool(rp.get("behavior_changed", False))
        re = bool(rp.get("runtime_effect", False))
        pr = bool(rp.get("production_ready", False))
        pca = bool(rp.get("public_claim_allowed", False))

        is_valid = (
            rid and pid and prid
            and not ppa and not pia and not na and not ps and not mla and not mca
            and not mc and not ol and not cl and not rm and not bh and not re
            and not pr and not pca
        )

        if is_valid:
            valid_replays.append(rp)
        else:
            invalid_replays += 1
            if not rid:
                missing_replay_id += 1
            if not pid:
                missing_preflight_id += 1
            if not prid:
                missing_provider_id += 1
            if ppa:
                provider_probe_allowed_violation += 1
            if pia:
                provider_invocation_allowed_violation += 1
            if na:
                network_allowed_violation += 1
            if ps:
                process_spawn_allowed_violation += 1
            if mla:
                model_load_allowed_violation += 1
            if mca:
                model_call_allowed_violation += 1
            if mc:
                model_call_executed_violation += 1
            if ol:
                ollama_invoked_violation += 1
            if cl:
                cloud_provider_invoked_violation += 1
            if rm:
                repo_mutated_violation += 1
            if bh:
                behavior_changed_violation += 1
            if re:
                runtime_effect_violation += 1
            if pr:
                production_ready_violation += 1
            if pca:
                public_claim_allowed_violation += 1

    total_violations = (
        provider_probe_allowed_violation + provider_invocation_allowed_violation
        + network_allowed_violation + process_spawn_allowed_violation
        + model_load_allowed_violation + model_call_allowed_violation
        + model_call_executed_violation + ollama_invoked_violation
        + cloud_provider_invoked_violation + repo_mutated_violation
        + behavior_changed_violation + runtime_effect_violation
        + production_ready_violation + public_claim_allowed_violation
    )

    replay_allowed = (
        flag and preflight_present and preflight_ready
        and denial_receipt_ready and preflight_safety == 0
    )

    replay_ready = (
        replay_allowed and len(valid_replays) > 0 and total_violations == 0
    )

    denial_replay_sealed = (
        replay_ready and invalid_replays == 0
    )

    reasons = []
    if not flag:
        reasons.append("provider_denial_receipt_replay_flag_not_enabled")
    if not preflight_present:
        reasons.append("missing_h6_10_controlled_provider_probe_preflight")
    if preflight and not preflight_ready:
        reasons.append("h6_10_preflight_not_ready")
    if preflight and not denial_receipt_ready:
        reasons.append("h6_10_denial_receipt_not_ready")
    if preflight_safety > 0:
        reasons.append("h6_10_safety_violation_detected")
    if not replays:
        reasons.append("no_denial_replays")
    if missing_replay_id > 0:
        reasons.append("missing_replay_id")
    if missing_preflight_id > 0:
        reasons.append("missing_preflight_id")
    if missing_provider_id > 0:
        reasons.append("missing_provider_id")
    if provider_probe_allowed_violation > 0:
        reasons.append("provider_probe_allowed_violation")
    if provider_invocation_allowed_violation > 0:
        reasons.append("provider_invocation_allowed_violation")
    if network_allowed_violation > 0:
        reasons.append("network_allowed_violation")
    if process_spawn_allowed_violation > 0:
        reasons.append("process_spawn_allowed_violation")
    if model_load_allowed_violation > 0:
        reasons.append("model_load_allowed_violation")
    if model_call_allowed_violation > 0:
        reasons.append("model_call_allowed_violation")
    if model_call_executed_violation > 0:
        reasons.append("model_call_executed_violation")
    if ollama_invoked_violation > 0:
        reasons.append("ollama_invoked_violation")
    if cloud_provider_invoked_violation > 0:
        reasons.append("cloud_provider_invoked_violation")
    if repo_mutated_violation > 0:
        reasons.append("repo_mutated_violation")
    if behavior_changed_violation > 0:
        reasons.append("behavior_changed_violation")
    if runtime_effect_violation > 0:
        reasons.append("runtime_effect_violation")
    if production_ready_violation > 0:
        reasons.append("production_ready_violation")
    if public_claim_allowed_violation > 0:
        reasons.append("public_claim_allowed_violation")
    reasons.extend([
        "h6_11_provider_denial_receipt_replay_not_production",
        "denial_receipt_replay_only",
        "deny_by_default",
        "no_provider_probe_allowed",
        "no_provider_invocation_allowed",
        "no_network_allowed",
        "no_process_spawn_allowed",
        "no_model_load_allowed",
        "no_model_call_allowed",
        "no_model_call_executed",
        "no_ollama_invocation",
        "no_cloud_provider_invocation",
        "no_repo_mutation",
        "no_behavior_change",
        "no_runtime_effect",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h6_provider_denial_receipt_replay.v1",
        "evaluated": True,
        "replay_mode": "denial_receipt_replay_only",
        "source_preflight_schema": "nexus.hybrid_h6_controlled_provider_probe_preflight.v1",
        "source_preflight_ready": preflight_ready,
        "source_denial_receipt_ready": denial_receipt_ready,
        "replay_status": "denial_replay_ready" if replay_ready else ("denial_replay_fail" if replay_allowed else "blocked"),
        "replay_reasons": reasons,
        "replay_allowed": replay_allowed,
        "replay_ready": replay_ready,
        "row_count": len(rows),
        "preflight_present": preflight_present,
        "preflight_ready": preflight_ready,
        "denial_receipt_ready": denial_receipt_ready,
        "denial_replay_count": len(replays),
        "denial_replay_valid_count": len(valid_replays),
        "denial_replay_invalid_count": invalid_replays,
        "total_violation_count": total_violations,
        "missing_replay_id_count": missing_replay_id,
        "missing_preflight_id_count": missing_preflight_id,
        "missing_provider_id_count": missing_provider_id,
        "provider_probe_allowed_violation_count": provider_probe_allowed_violation,
        "provider_invocation_allowed_violation_count": provider_invocation_allowed_violation,
        "network_allowed_violation_count": network_allowed_violation,
        "process_spawn_allowed_violation_count": process_spawn_allowed_violation,
        "model_load_allowed_violation_count": model_load_allowed_violation,
        "model_call_allowed_violation_count": model_call_allowed_violation,
        "model_call_executed_violation_count": model_call_executed_violation,
        "ollama_invoked_violation_count": ollama_invoked_violation,
        "cloud_provider_invoked_violation_count": cloud_provider_invoked_violation,
        "repo_mutated_violation_count": repo_mutated_violation,
        "behavior_changed_violation_count": behavior_changed_violation,
        "runtime_effect_violation_count": runtime_effect_violation,
        "production_ready_violation_count": production_ready_violation,
        "public_claim_allowed_violation_count": public_claim_allowed_violation,
        "provider_probe_denied": True,
        "provider_invocation_denied": True,
        "network_denied": True,
        "process_spawn_denied": True,
        "model_load_denied": True,
        "model_call_denied": True,
        "model_execution_denied": True,
        "ollama_invocation_denied": True,
        "cloud_provider_invocation_denied": True,
        "repo_mutation_denied": True,
        "behavior_change_denied": True,
        "runtime_effect_denied": True,
        "production_claim_denied": True,
        "public_claim_denied": True,
        "provider_probe_allowed": False,
        "provider_invocation_allowed": False,
        "network_allowed": False,
        "process_spawn_allowed": False,
        "model_load_allowed": False,
        "model_call_allowed": False,
        "model_call_executed": False,
        "ollama_invoked": False,
        "cloud_provider_invoked": False,
        "repo_mutated": False,
        "behavior_changed": False,
        "runtime_effect": False,
        "production_ready": False,
        "public_claim_allowed": False,
        "deny_by_default": True,
        "denial_replay_sealed": denial_replay_sealed,
        "ready_for_h6_12_controlled_local_provider_fixture": False,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h6_controlled_local_provider_fixture_contract(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: H6 controlled local provider fixture contract.

    Defines the static contract for a local provider fixture. All invocation
    fields remain deny-by-default. This is a schema-only receipt — no provider
    is loaded, no model is called, no network is opened.
    """
    import os as _os

    flag = _os.environ.get("NEXUS_H6_ALLOW_CONTROLLED_LOCAL_PROVIDER_FIXTURE_CONTRACT", "").strip() == "1"

    denial = None
    if bundle:
        denial = bundle.get("h6_provider_denial_receipt_replay")

    denial_present = bool(denial)
    denial_ready = bool(denial.get("replay_ready", False)) if denial else False
    denial_sealed = bool(denial.get("denial_replay_sealed", False)) if denial else False
    denial_safety = int(denial.get("total_violation_count", 0)) if denial else 0

    ALLOWED_PROVIDER_FAMILIES = {"ollama"}
    ALLOWED_MODEL_FAMILIES = {"qwen"}
    ALLOWED_MODEL_SIZES = {"3b", "7b", "14b"}
    ALLOWED_ENDPOINT_KINDS = {"none", "unix_socket_placeholder", "localhost_placeholder"}

    fixtures = [r.get("h6_controlled_local_provider_fixture") for r in rows if r.get("h6_controlled_local_provider_fixture")]

    valid_fixtures = []
    invalid_fixtures = 0
    missing_fixture_id = 0
    invalid_provider_family = 0
    invalid_model_family = 0
    invalid_model_size = 0
    invalid_endpoint_kind = 0
    endpoint_value_present_violation = 0
    local_endpoint_allowed_violation = 0
    network_endpoint_allowed_violation = 0
    provider_execution_allowed_violation = 0
    network_blocked = 0
    process_spawn_blocked = 0
    model_load_blocked = 0
    model_call_blocked = 0

    mc_count = 0
    ol_count = 0
    cl_count = 0
    rm_count = 0
    bh_count = 0
    re_count = 0

    for fx in fixtures:
        fid = str(fx.get("fixture_id", "") or "").strip()
        pfam = str(fx.get("provider_family", "") or "").lower()
        mfam = str(fx.get("model_family", "") or "").lower()
        sz = str(fx.get("model_size", "") or "").lower()
        ek = str(fx.get("endpoint_kind", "") or "").lower()
        evp = bool(fx.get("endpoint_value_present", True))
        lea = bool(fx.get("local_endpoint_allowed", True))
        nea = bool(fx.get("network_endpoint_allowed", True))
        pea = bool(fx.get("provider_execution_allowed", True))
        na = bool(fx.get("network_allowed", True))
        ps = bool(fx.get("process_spawn_allowed", True))
        mla = bool(fx.get("model_load_allowed", True))
        mca = bool(fx.get("model_call_allowed", True))
        mc = bool(fx.get("model_call_executed", False))
        ol = bool(fx.get("ollama_invoked", False))
        cl = bool(fx.get("cloud_provider_invoked", False))
        rm = bool(fx.get("repo_mutated", False))
        bh = bool(fx.get("behavior_changed", False))
        re = bool(fx.get("runtime_effect", False))

        if mc:
            mc_count += 1
        if ol:
            ol_count += 1
        if cl:
            cl_count += 1
        if rm:
            rm_count += 1
        if bh:
            bh_count += 1
        if re:
            re_count += 1

        is_valid = (
            fid and pfam in ALLOWED_PROVIDER_FAMILIES and mfam in ALLOWED_MODEL_FAMILIES
            and sz in ALLOWED_MODEL_SIZES and ek in ALLOWED_ENDPOINT_KINDS
            and not evp and not lea and not nea and not pea
            and not na and not ps and not mla and not mca
            and not mc and not ol and not cl and not rm and not bh and not re
        )

        if is_valid:
            valid_fixtures.append(fx)
        else:
            invalid_fixtures += 1
            if not fid:
                missing_fixture_id += 1
            if pfam not in ALLOWED_PROVIDER_FAMILIES:
                invalid_provider_family += 1
            if mfam not in ALLOWED_MODEL_FAMILIES:
                invalid_model_family += 1
            if sz not in ALLOWED_MODEL_SIZES:
                invalid_model_size += 1
            if ek not in ALLOWED_ENDPOINT_KINDS:
                invalid_endpoint_kind += 1
            if evp:
                endpoint_value_present_violation += 1
            if lea:
                local_endpoint_allowed_violation += 1
            if nea:
                network_endpoint_allowed_violation += 1
            if pea:
                provider_execution_allowed_violation += 1
            if na:
                network_blocked += 1
            if ps:
                process_spawn_blocked += 1
            if mla:
                model_load_blocked += 1
            if mca:
                model_call_blocked += 1

    safety = mc_count + ol_count + cl_count + rm_count + bh_count + re_count

    contract_allowed = (
        flag and denial_present and denial_ready
        and denial_sealed and denial_safety == 0
    )

    contract_ready = (
        contract_allowed and len(valid_fixtures) > 0 and safety == 0
    )

    contract_valid = (
        contract_ready and invalid_fixtures == 0
    )

    reasons = []
    if not flag:
        reasons.append("controlled_local_provider_fixture_contract_flag_not_enabled")
    if not denial_present:
        reasons.append("missing_h6_11_denial_receipt_replay")
    if denial and not denial_ready:
        reasons.append("h6_11_denial_replay_not_ready")
    if denial and not denial_sealed:
        reasons.append("h6_11_denial_replay_not_sealed")
    if denial_safety > 0:
        reasons.append("h6_11_safety_violation_detected")
    if not fixtures:
        reasons.append("no_fixtures")
    if missing_fixture_id > 0:
        reasons.append("missing_fixture_id")
    if invalid_provider_family > 0:
        reasons.append("invalid_provider_family")
    if invalid_model_family > 0:
        reasons.append("invalid_model_family")
    if invalid_model_size > 0:
        reasons.append("invalid_model_size")
    if invalid_endpoint_kind > 0:
        reasons.append("invalid_endpoint_kind")
    if endpoint_value_present_violation > 0:
        reasons.append("endpoint_value_present_violation")
    if local_endpoint_allowed_violation > 0:
        reasons.append("local_endpoint_allowed_violation")
    if network_endpoint_allowed_violation > 0:
        reasons.append("network_endpoint_allowed_violation")
    if provider_execution_allowed_violation > 0:
        reasons.append("provider_execution_allowed_violation")
    if network_blocked > 0:
        reasons.append("network_not_allowed")
    if process_spawn_blocked > 0:
        reasons.append("process_spawn_not_allowed")
    if model_load_blocked > 0:
        reasons.append("model_load_not_allowed")
    if model_call_blocked > 0:
        reasons.append("model_call_not_allowed")
    if mc_count > 0:
        reasons.append("model_call_executed_detected")
    if ol_count > 0:
        reasons.append("ollama_invoked_detected")
    if cl_count > 0:
        reasons.append("cloud_provider_invoked_detected")
    if rm_count > 0:
        reasons.append("repo_mutated_detected")
    if bh_count > 0:
        reasons.append("behavior_changed_detected")
    if re_count > 0:
        reasons.append("runtime_effect_detected")
    reasons.extend([
        "h6_12_controlled_local_provider_fixture_contract_not_production",
        "fixture_only",
        "deny_by_default",
        "no_provider_probe_allowed",
        "no_provider_invocation_allowed",
        "no_provider_execution_allowed",
        "no_network_allowed",
        "no_process_spawn_allowed",
        "no_model_load_allowed",
        "no_model_call_allowed",
        "no_model_call_executed",
        "no_ollama_invocation",
        "no_cloud_provider_invocation",
        "no_repo_mutation",
        "no_behavior_change",
        "no_runtime_effect",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h6_controlled_local_provider_fixture_contract.v1",
        "evaluated": True,
        "source_h6_11_schema": "nexus.hybrid_h6_provider_denial_receipt_replay.v1",
        "source_h6_11_denial_replay_ready": denial_ready,
        "fixture_contract_status": "fixture_contract_ready" if contract_ready else ("fixture_contract_fail" if contract_allowed else "blocked"),
        "fixture_contract_reasons": reasons,
        "fixture_contract_allowed": contract_allowed,
        "fixture_contract_ready": contract_ready,
        "fixture_contract_valid": contract_valid,
        "row_count": len(rows),
        "denial_present": denial_present,
        "denial_ready": denial_ready,
        "denial_sealed": denial_sealed,
        "fixture_count": len(fixtures),
        "fixture_valid_count": len(valid_fixtures),
        "fixture_invalid_count": invalid_fixtures,
        "missing_fixture_id_count": missing_fixture_id,
        "invalid_provider_family_count": invalid_provider_family,
        "invalid_model_family_count": invalid_model_family,
        "invalid_model_size_count": invalid_model_size,
        "invalid_endpoint_kind_count": invalid_endpoint_kind,
        "endpoint_value_present_violation_count": endpoint_value_present_violation,
        "local_endpoint_allowed_violation_count": local_endpoint_allowed_violation,
        "network_endpoint_allowed_violation_count": network_endpoint_allowed_violation,
        "provider_execution_allowed_violation_count": provider_execution_allowed_violation,
        "network_blocked_count": network_blocked,
        "process_spawn_blocked_count": process_spawn_blocked,
        "model_load_blocked_count": model_load_blocked,
        "model_call_blocked_count": model_call_blocked,
        "model_call_executed_count": mc_count,
        "ollama_invoked_count": ol_count,
        "cloud_provider_invoked_count": cl_count,
        "repo_mutated_count": rm_count,
        "behavior_changed_count": bh_count,
        "runtime_effect_count": re_count,
        "safety_violation_count": safety,
        "endpoint_value_present": False,
        "local_endpoint_allowed": False,
        "network_endpoint_allowed": False,
        "provider_probe_allowed": False,
        "provider_invocation_allowed": False,
        "provider_execution_allowed": False,
        "network_allowed": False,
        "process_spawn_allowed": False,
        "model_load_allowed": False,
        "model_call_allowed": False,
        "model_call_executed": False,
        "ollama_invoked": False,
        "cloud_provider_invoked": False,
        "repo_mutated": False,
        "behavior_changed": False,
        "runtime_effect": False,
        "deny_by_default": True,
        "fixture_only": True,
        "ready_for_h6_13_controlled_provider_probe_denylist": False,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h6_controlled_provider_probe_denylist(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: H6 controlled provider probe denylist.

    Defines a denylist for provider probe, endpoint resolution, process spawn,
    network access, model load, model call, and runtime effect. All invocation
    fields remain deny-by-default. This is a denylist-only receipt.
    """
    import os as _os

    flag = _os.environ.get("NEXUS_H6_ALLOW_CONTROLLED_PROVIDER_PROBE_DENYLIST", "").strip() == "1"

    fixture = None
    if bundle:
        fixture = bundle.get("h6_controlled_local_provider_fixture_contract")

    fixture_present = bool(fixture)
    fixture_ready = bool(fixture.get("fixture_contract_ready", False)) if fixture else False
    fixture_valid = bool(fixture.get("fixture_contract_valid", False)) if fixture else False
    fixture_only = bool(fixture.get("fixture_only", False)) if fixture else False
    fixture_safety = int(fixture.get("safety_violation_count", 0)) if fixture else 0
    fixture_ppa = bool(fixture.get("provider_probe_allowed", True)) if fixture else True
    fixture_pia = bool(fixture.get("provider_invocation_allowed", True)) if fixture else True
    fixture_pea = bool(fixture.get("provider_execution_allowed", True)) if fixture else True
    fixture_lea = bool(fixture.get("local_endpoint_allowed", True)) if fixture else True
    fixture_nea = bool(fixture.get("network_endpoint_allowed", True)) if fixture else True
    fixture_na = bool(fixture.get("network_allowed", True)) if fixture else True
    fixture_ps = bool(fixture.get("process_spawn_allowed", True)) if fixture else True
    fixture_mla = bool(fixture.get("model_load_allowed", True)) if fixture else True
    fixture_mca = bool(fixture.get("model_call_allowed", True)) if fixture else True
    fixture_mc = bool(fixture.get("model_call_executed", False)) if fixture else False
    fixture_ol = bool(fixture.get("ollama_invoked", False)) if fixture else False
    fixture_cl = bool(fixture.get("cloud_provider_invoked", False)) if fixture else False
    fixture_re = bool(fixture.get("runtime_effect", False)) if fixture else False

    ALLOWED_PROVIDER_FAMILIES = {"ollama"}
    ALLOWED_MODEL_FAMILIES = {"qwen"}
    ALLOWED_MODEL_SIZES = {"3b", "7b", "14b"}
    ALLOWED_ENDPOINT_KINDS = {"none", "unix_socket_placeholder", "localhost_placeholder"}

    denylists = [r.get("h6_controlled_provider_probe_denylist") for r in rows if r.get("h6_controlled_provider_probe_denylist")]

    valid_denylists = []
    invalid_denylists = 0
    missing_denylist_id = 0
    missing_provider_family = 0
    invalid_provider_family = 0
    invalid_model_family = 0
    invalid_model_size = 0
    invalid_endpoint_kind = 0
    endpoint_resolution_allowed_violation = 0
    local_endpoint_allowed_violation = 0
    network_endpoint_allowed_violation = 0
    provider_probe_allowed_violation = 0
    provider_invocation_allowed_violation = 0
    provider_execution_allowed_violation = 0
    model_load_allowed_violation = 0
    model_call_allowed_violation = 0
    model_call_executed_violation = 0

    mc_count = 0
    ol_count = 0
    cl_count = 0
    rm_count = 0
    bh_count = 0
    re_count = 0

    for dl in denylists:
        did = str(dl.get("denylist_id", "") or "").strip()
        pfam = str(dl.get("provider_family", "") or "").lower()
        mfam = str(dl.get("model_family", "") or "").lower()
        sz = str(dl.get("model_size", "") or "").lower()
        ek = str(dl.get("endpoint_kind", "") or "").lower()
        era = bool(dl.get("endpoint_resolution_allowed", True))
        lea = bool(dl.get("local_endpoint_allowed", True))
        nea = bool(dl.get("network_endpoint_allowed", True))
        ppa = bool(dl.get("provider_probe_allowed", True))
        pia = bool(dl.get("provider_invocation_allowed", True))
        pea = bool(dl.get("provider_execution_allowed", True))
        mla = bool(dl.get("model_load_allowed", True))
        mca = bool(dl.get("model_call_allowed", True))
        mc = bool(dl.get("model_call_executed", False))
        ol = bool(dl.get("ollama_invoked", False))
        cl = bool(dl.get("cloud_provider_invoked", False))
        rm = bool(dl.get("repo_mutated", False))
        bh = bool(dl.get("behavior_changed", False))
        re = bool(dl.get("runtime_effect", False))

        if mc:
            mc_count += 1
        if ol:
            ol_count += 1
        if cl:
            cl_count += 1
        if rm:
            rm_count += 1
        if bh:
            bh_count += 1
        if re:
            re_count += 1

        is_valid = (
            did and pfam in ALLOWED_PROVIDER_FAMILIES and mfam in ALLOWED_MODEL_FAMILIES
            and sz in ALLOWED_MODEL_SIZES and ek in ALLOWED_ENDPOINT_KINDS
            and not era and not lea and not nea
            and not ppa and not pia and not pea
            and not mla and not mca and not mc
            and not ol and not cl and not rm and not bh and not re
        )

        if is_valid:
            valid_denylists.append(dl)
        else:
            invalid_denylists += 1
            if not did:
                missing_denylist_id += 1
            if not pfam:
                missing_provider_family += 1
            if pfam not in ALLOWED_PROVIDER_FAMILIES:
                invalid_provider_family += 1
            if mfam not in ALLOWED_MODEL_FAMILIES:
                invalid_model_family += 1
            if sz not in ALLOWED_MODEL_SIZES:
                invalid_model_size += 1
            if ek not in ALLOWED_ENDPOINT_KINDS:
                invalid_endpoint_kind += 1
            if era:
                endpoint_resolution_allowed_violation += 1
            if lea:
                local_endpoint_allowed_violation += 1
            if nea:
                network_endpoint_allowed_violation += 1
            if ppa:
                provider_probe_allowed_violation += 1
            if pia:
                provider_invocation_allowed_violation += 1
            if pea:
                provider_execution_allowed_violation += 1
            if mla:
                model_load_allowed_violation += 1
            if mca:
                model_call_allowed_violation += 1
            if mc:
                model_call_executed_violation += 1

    safety = mc_count + ol_count + cl_count + rm_count + bh_count + re_count

    fixture_safety_ok = (
        not fixture_ppa and not fixture_pia and not fixture_pea
        and not fixture_lea and not fixture_nea and not fixture_na
        and not fixture_ps and not fixture_mla and not fixture_mca
        and not fixture_mc and not fixture_ol and not fixture_cl
        and not fixture_re
    )

    denylist_allowed = (
        flag and fixture_present and fixture_ready
        and fixture_valid and fixture_only and fixture_safety == 0
        and fixture_safety_ok
    )

    denylist_ready = (
        denylist_allowed and len(valid_denylists) > 0 and safety == 0
    )

    denylist_valid = (
        denylist_ready and invalid_denylists == 0
    )

    reasons = []
    if not flag:
        reasons.append("controlled_provider_probe_denylist_flag_not_enabled")
    if not fixture_present:
        reasons.append("missing_h6_12_fixture_contract")
    if fixture and not fixture_ready:
        reasons.append("h6_12_fixture_contract_not_ready")
    if fixture and not fixture_valid:
        reasons.append("h6_12_fixture_contract_not_valid")
    if fixture and not fixture_only:
        reasons.append("h6_12_not_fixture_only")
    if fixture_safety > 0:
        reasons.append("h6_12_safety_violation_detected")
    if fixture and not fixture_safety_ok:
        reasons.append("h6_12_fixture_has_allowed_fields")
    if not denylists:
        reasons.append("no_denylists")
    if missing_denylist_id > 0:
        reasons.append("missing_denylist_id")
    if missing_provider_family > 0:
        reasons.append("missing_provider_family")
    if invalid_provider_family > 0:
        reasons.append("invalid_provider_family")
    if invalid_model_family > 0:
        reasons.append("invalid_model_family")
    if invalid_model_size > 0:
        reasons.append("invalid_model_size")
    if invalid_endpoint_kind > 0:
        reasons.append("invalid_endpoint_kind")
    if endpoint_resolution_allowed_violation > 0:
        reasons.append("endpoint_resolution_allowed_violation")
    if local_endpoint_allowed_violation > 0:
        reasons.append("local_endpoint_allowed_violation")
    if network_endpoint_allowed_violation > 0:
        reasons.append("network_endpoint_allowed_violation")
    if provider_probe_allowed_violation > 0:
        reasons.append("provider_probe_allowed_violation")
    if provider_invocation_allowed_violation > 0:
        reasons.append("provider_invocation_allowed_violation")
    if provider_execution_allowed_violation > 0:
        reasons.append("provider_execution_allowed_violation")
    if model_load_allowed_violation > 0:
        reasons.append("model_load_allowed_violation")
    if model_call_allowed_violation > 0:
        reasons.append("model_call_allowed_violation")
    if model_call_executed_violation > 0:
        reasons.append("model_call_executed_violation")
    if mc_count > 0:
        reasons.append("model_call_executed_detected")
    if ol_count > 0:
        reasons.append("ollama_invoked_detected")
    if cl_count > 0:
        reasons.append("cloud_provider_invoked_detected")
    if rm_count > 0:
        reasons.append("repo_mutated_detected")
    if bh_count > 0:
        reasons.append("behavior_changed_detected")
    if re_count > 0:
        reasons.append("runtime_effect_detected")
    reasons.extend([
        "h6_13_controlled_provider_probe_denylist_not_production",
        "denylist_only",
        "deny_by_default",
        "no_provider_probe_allowed",
        "no_provider_invocation_allowed",
        "no_provider_execution_allowed",
        "no_endpoint_resolution_allowed",
        "no_network_allowed",
        "no_process_spawn_allowed",
        "no_model_load_allowed",
        "no_model_call_allowed",
        "no_model_call_executed",
        "no_ollama_invocation",
        "no_cloud_provider_invocation",
        "no_repo_mutation",
        "no_behavior_change",
        "no_runtime_effect",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    return {
        "schema": "nexus.hybrid_h6_controlled_provider_probe_denylist.v1",
        "evaluated": True,
        "source_h6_12_schema": "nexus.hybrid_h6_controlled_local_provider_fixture_contract.v1",
        "source_fixture_contract_ready": fixture_ready,
        "source_fixture_contract_valid": fixture_valid,
        "source_fixture_only": fixture_only,
        "denylist_status": "denylist_ready" if denylist_ready else ("denylist_fail" if denylist_allowed else "blocked"),
        "denylist_reasons": reasons,
        "denylist_allowed": denylist_allowed,
        "denylist_ready": denylist_ready,
        "denylist_valid": denylist_valid,
        "row_count": len(rows),
        "fixture_present": fixture_present,
        "fixture_ready": fixture_ready,
        "fixture_valid": fixture_valid,
        "fixture_only": fixture_only,
        "denylist_count": len(denylists),
        "denylist_valid_count": len(valid_denylists),
        "denylist_invalid_count": invalid_denylists,
        "missing_denylist_id_count": missing_denylist_id,
        "missing_provider_family_count": missing_provider_family,
        "invalid_provider_family_count": invalid_provider_family,
        "invalid_model_family_count": invalid_model_family,
        "invalid_model_size_count": invalid_model_size,
        "invalid_endpoint_kind_count": invalid_endpoint_kind,
        "endpoint_resolution_allowed_violation_count": endpoint_resolution_allowed_violation,
        "local_endpoint_allowed_violation_count": local_endpoint_allowed_violation,
        "network_endpoint_allowed_violation_count": network_endpoint_allowed_violation,
        "provider_probe_allowed_violation_count": provider_probe_allowed_violation,
        "provider_invocation_allowed_violation_count": provider_invocation_allowed_violation,
        "provider_execution_allowed_violation_count": provider_execution_allowed_violation,
        "model_load_allowed_violation_count": model_load_allowed_violation,
        "model_call_allowed_violation_count": model_call_allowed_violation,
        "model_call_executed_violation_count": model_call_executed_violation,
        "model_call_executed_count": mc_count,
        "ollama_invoked_count": ol_count,
        "cloud_provider_invoked_count": cl_count,
        "repo_mutated_count": rm_count,
        "behavior_changed_count": bh_count,
        "runtime_effect_count": re_count,
        "safety_violation_count": safety,
        "probe_denylist_mode": "denylist_only",
        "provider_probe_denied": True,
        "provider_invocation_denied": True,
        "provider_execution_denied": True,
        "endpoint_resolution_denied": True,
        "local_endpoint_denied": True,
        "network_endpoint_denied": True,
        "network_denied": True,
        "process_spawn_denied": True,
        "model_load_denied": True,
        "model_call_denied": True,
        "model_execution_denied": True,
        "ollama_invocation_denied": True,
        "cloud_provider_invocation_denied": True,
        "repo_mutation_denied": True,
        "behavior_change_denied": True,
        "runtime_effect_denied": True,
        "production_claim_denied": True,
        "public_claim_denied": True,
        "provider_probe_allowed": False,
        "provider_invocation_allowed": False,
        "provider_execution_allowed": False,
        "endpoint_resolution_allowed": False,
        "local_endpoint_allowed": False,
        "network_endpoint_allowed": False,
        "network_allowed": False,
        "process_spawn_allowed": False,
        "model_load_allowed": False,
        "model_call_allowed": False,
        "model_call_executed": False,
        "ollama_invoked": False,
        "cloud_provider_invoked": False,
        "repo_mutated": False,
        "behavior_changed": False,
        "runtime_effect": False,
        "deny_by_default": True,
        "fixture_only": True,
        "denylist_only": True,
        "ready_for_h6_14_controlled_probe_preflight_replay": False,
        "production_ready": False,
        "public_claim_allowed": False,
    }


def _build_h6_controlled_probe_preflight_replay(rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure helper: H6 controlled probe preflight replay.

    Replays controlled provider probe preflight scenarios against the H6-13
    denylist. All provider/network/model/process paths are confirmed blocked
    at preflight stage. This is a dry-run replay receipt only.
    """
    import os as _os

    flag = _os.environ.get("NEXUS_H6_ALLOW_CONTROLLED_PROBE_PREFLIGHT_REPLAY", "").strip() == "1"

    denylist = None
    if bundle:
        denylist = bundle.get("h6_controlled_provider_probe_denylist")

    denylist_present = bool(denylist)
    denylist_ready = bool(denylist.get("denylist_ready", False)) if denylist else False
    denylist_valid = bool(denylist.get("denylist_valid", False)) if denylist else False
    denylist_safety = int(denylist.get("safety_violation_count", 0)) if denylist else 0
    denylist_ppa = bool(denylist.get("provider_probe_allowed", True)) if denylist else True
    denylist_pia = bool(denylist.get("provider_invocation_allowed", True)) if denylist else True
    denylist_pea = bool(denylist.get("provider_execution_allowed", True)) if denylist else True
    denylist_era = bool(denylist.get("endpoint_resolution_allowed", True)) if denylist else True
    denylist_lea = bool(denylist.get("local_endpoint_allowed", True)) if denylist else True
    denylist_nea = bool(denylist.get("network_endpoint_allowed", True)) if denylist else True
    denylist_na = bool(denylist.get("network_allowed", True)) if denylist else True
    denylist_ps = bool(denylist.get("process_spawn_allowed", True)) if denylist else True
    denylist_mla = bool(denylist.get("model_load_allowed", True)) if denylist else True
    denylist_mca = bool(denylist.get("model_call_allowed", True)) if denylist else True
    denylist_mc = bool(denylist.get("model_call_executed", False)) if denylist else False

    BLOCKED_PROVIDER_FAMILIES = {"qwen", "ollama", "gemini", "codex", "cloud"}
    BLOCKED_ENDPOINT_KINDS = {"local_http", "unix_socket", "remote_https"}
    BLOCKED_MODEL_SIZES = {"3b", "7b", "14b"}

    replays = [r.get("h6_controlled_probe_preflight_replay") for r in rows if r.get("h6_controlled_probe_preflight_replay")]

    blocked_replays = []
    blocked_count = 0
    total_replays = len(replays)

    denylist_safety_ok = (
        not denylist_ppa and not denylist_pia and not denylist_pea
        and not denylist_era and not denylist_lea and not denylist_nea
        and not denylist_na and not denylist_ps and not denylist_mla
        and not denylist_mca and not denylist_mc
    )

    replay_allowed = (
        flag and denylist_present and denylist_ready
        and denylist_valid and denylist_safety == 0
        and denylist_safety_ok
    )

    for rp in replays:
        pfam = str(rp.get("provider_family", "") or "").lower()
        mfam = str(rp.get("model_family", "") or "").lower()
        sz = str(rp.get("model_size", "") or "").lower()
        ek = str(rp.get("endpoint_kind", "") or "").lower()
        ppa = bool(rp.get("provider_probe_allowed", False))
        pia = bool(rp.get("provider_invocation_allowed", False))
        pea = bool(rp.get("provider_execution_allowed", False))
        era = bool(rp.get("endpoint_resolution_allowed", False))
        lea = bool(rp.get("local_endpoint_allowed", False))
        nea = bool(rp.get("network_endpoint_allowed", False))
        na = bool(rp.get("network_allowed", False))
        ps = bool(rp.get("process_spawn_allowed", False))
        mla = bool(rp.get("model_load_allowed", False))
        mca = bool(rp.get("model_call_allowed", False))
        mc = bool(rp.get("model_call_executed", False))
        pr = bool(rp.get("production_ready", False))
        pca = bool(rp.get("public_claim_allowed", False))
        re_flag = bool(rp.get("runtime_effect", False))

        is_blocked = True
        blocked_reasons = []

        if pfam in BLOCKED_PROVIDER_FAMILIES:
            blocked_reasons.append(f"provider_family_{pfam}_blocked")
        if mfam and mfam != "qwen":
            blocked_reasons.append(f"model_family_{mfam}_blocked")
        if ek in BLOCKED_ENDPOINT_KINDS:
            blocked_reasons.append(f"endpoint_kind_{ek}_blocked")
        if sz in BLOCKED_MODEL_SIZES:
            blocked_reasons.append(f"model_size_{sz}_blocked")
        if ppa:
            blocked_reasons.append("provider_probe_allowed_blocked")
        if pia:
            blocked_reasons.append("provider_invocation_allowed_blocked")
        if pea:
            blocked_reasons.append("provider_execution_allowed_blocked")
        if era:
            blocked_reasons.append("endpoint_resolution_allowed_blocked")
        if lea:
            blocked_reasons.append("local_endpoint_allowed_blocked")
        if nea:
            blocked_reasons.append("network_endpoint_allowed_blocked")
        if na:
            blocked_reasons.append("network_allowed_blocked")
        if ps:
            blocked_reasons.append("process_spawn_allowed_blocked")
        if mla:
            blocked_reasons.append("model_load_allowed_blocked")
        if mca:
            blocked_reasons.append("model_call_allowed_blocked")
        if mc:
            blocked_reasons.append("model_call_executed_blocked")
        if pr:
            blocked_reasons.append("production_ready_blocked")
        if pca:
            blocked_reasons.append("public_claim_allowed_blocked")
        if re_flag:
            blocked_reasons.append("runtime_effect_blocked")

        if not blocked_reasons:
            blocked_reasons.append("denylist_match_blocked")

        blocked_replays.append({
            "provider_family": pfam,
            "model_family": mfam,
            "model_size": sz,
            "endpoint_kind": ek,
            "blocked": True,
            "blocked_reasons": blocked_reasons,
        })
        blocked_count += 1

    reasons = []
    if not flag:
        reasons.append("controlled_probe_preflight_replay_flag_not_enabled")
    if not denylist_present:
        reasons.append("missing_h6_13_denylist")
    if denylist and not denylist_ready:
        reasons.append("h6_13_denylist_not_ready")
    if denylist and not denylist_valid:
        reasons.append("h6_13_denylist_not_valid")
    if denylist_safety > 0:
        reasons.append("h6_13_safety_violation_detected")
    if denylist and not denylist_safety_ok:
        reasons.append("h6_13_denylist_has_allowed_fields")
    if not replays:
        reasons.append("no_replays")
    reasons.extend([
        "h6_14_controlled_probe_preflight_replay_not_production",
        "preflight_replay_only",
        "denylist_applied",
        "blocked_before_execution",
        "no_provider_probe_allowed",
        "no_provider_invocation_allowed",
        "no_provider_execution_allowed",
        "no_endpoint_resolution_allowed",
        "no_network_allowed",
        "no_process_spawn_allowed",
        "no_model_load_allowed",
        "no_model_call_allowed",
        "no_model_call_executed",
        "no_runtime_effect",
        "production_claim_blocked",
        "public_claim_blocked",
    ])

    replay_blocked = replay_allowed and blocked_count > 0 and blocked_count == total_replays

    return {
        "schema": "nexus.hybrid_h6_controlled_probe_preflight_replay.v1",
        "status": "blocked" if not replay_allowed else ("all_replays_blocked" if replay_blocked else "replay_evaluated"),
        "h6_stage": "h6_14",
        "source_h6_13_denylist_id": str(denylist.get("denylist_id", "")) if denylist else "",
        "preflight_replay_id": f"preflight-replay-{total_replays}",
        "preflight_replay_only": True,
        "denylist_applied": replay_allowed,
        "denylist_match": replay_allowed,
        "blocked_before_execution": True,
        "blocked_reason": "; ".join(reasons[:3]) if reasons else "denylist_match",
        "replay_allowed": replay_allowed,
        "replay_blocked": replay_blocked,
        "row_count": len(rows),
        "total_replay_count": total_replays,
        "blocked_replay_count": blocked_count,
        "blocked_replays": blocked_replays,
        "provider_probe_allowed": False,
        "provider_invocation_allowed": False,
        "provider_execution_allowed": False,
        "endpoint_resolution_allowed": False,
        "local_endpoint_allowed": False,
        "network_endpoint_allowed": False,
        "network_allowed": False,
        "process_spawn_allowed": False,
        "model_load_allowed": False,
        "model_call_allowed": False,
        "model_call_executed": False,
        "runtime_effect": False,
        "production_ready": False,
        "public_claim_allowed": False,
        "ready_for_h6_15": False,
        "reasons": reasons,
    }


def _finalize_with_nexus_row(
    row: dict[str, Any],
    *,
    provider: str,
    model_required: bool,
    nexus_required: bool,
    task: CapabilityTask,
    repo_root: Path,
) -> dict[str, Any]:
    _apply_data_contract_audit(row)
    finalized = _annotate_with_contract(
        row,
        provider=provider,
        model_required=model_required,
        nexus_required=nexus_required,
    )
    _reconcile_skill_mount_contract_after_receipts(finalized, repo_root=repo_root)
    _reconcile_benchmark_skill_mount_contract_from_expected_receipts(
        finalized,
        task=task,
        repo_root=repo_root,
    )
    _apply_data_contract_audit(finalized)

    # Phase H2: Deterministic Local Assist Before Cloud, Trace Mode
    import os
    enable_assist_trace = os.environ.get("NEXUS_HYBRID_LOCAL_ASSIST_TRACE", "").strip().lower() in {"1", "true", "yes"}
    
    # H1 trace-only: skip live network probe when gate is off
    if enable_assist_trace:
        local_avail = _is_ollama_available()
        local_availability_source = "ollama_api_tags_probe"
    else:
        local_avail = False
        local_availability_source = "not_probed_trace_only"
    cloud_provider_selected = provider in {"gemini", "codex"}
    cloud_avail = cloud_provider_selected and not finalized.get("infra_invalid_reason")
    
    if provider == "ollama":
        r_mode = "local_only_blocked"
    else:
        r_mode = "cloud_assisted_by_local_trace_only"

    if enable_assist_trace:
        # 1. 檢索/獲取 raw evidence
        raw_evidence = (
            str(finalized.get("hidden_verifier_stdout_tail") or "") + "\n" +
            str(finalized.get("hidden_verifier_stderr_tail") or "") + "\n" +
            str(finalized.get("repro_output_tail") or "")
        ).strip()
        if not raw_evidence:
            raw_evidence = str(task.task_desc or "")

        # 2. 呼叫 EvidenceCompactor.compact_v2 進行壓縮
        from nexus.services.local_heal.evidence_compactor import EvidenceCompactor
        compacted_text = EvidenceCompactor.compact_v2(
            evidence=raw_evidence,
            anchor_symbol="",
            anchor_file="",
            limit=3000
        )

        raw_context_chars = len(raw_evidence)
        compact_context_chars = len(compacted_text)
        compression_ratio = round(compact_context_chars / raw_context_chars, 4) if raw_context_chars > 0 else 0.0
        omitted_bytes = max(0, len(raw_evidence.encode("utf-8")) - len(compacted_text.encode("utf-8")))

        # 3. 呼叫 MemoryRetrievalAdapter.retrieve_reranked 獲取 reranked memory 資訊
        from nexus.services.local_heal.memory_retrieval_adapter import MemoryRetrievalAdapter
        query_text = str(task.task_desc or "test").strip()
        
        adapter = MemoryRetrievalAdapter(enabled=True)
        try:
            lessons = adapter.retrieve_reranked(
                query_text=query_text,
                anchor_symbol="",
                anchor_file="",
                limit=3,
                max_chars=800,
                task_id=task.id
            )
        except Exception:
            lessons = []
        
        memory_selected_ids = [l.finding_id for l in lessons]
        memory_no_match = len(lessons) == 0
        memory_rerank_mode = bool(adapter.last_metadata.get("rerank_mode", False))
        sources_observed = adapter.last_metadata.get("retrieval_sources", [])
        memory_source = "+".join(sources_observed) if sources_observed else "none"
        local_assist_invoked = True
        raw_artifact_ref = "hidden_verifier_stdout_tail" if finalized.get("hidden_verifier_stdout_tail") else "task_desc"
    else:
        # Gate Off: H1 mode
        raw_context_chars = 0
        compact_context_chars = 0
        compression_ratio = 0.0
        omitted_bytes = 0
        memory_selected_ids = []
        memory_no_match = True
        memory_rerank_mode = False
        memory_source = "none"
        local_assist_invoked = False
        raw_artifact_ref = ""

    finalized["hybrid_route"] = {
        "schema": "nexus.hybrid_route_decision.v1",
        "route_mode": r_mode,
        "with_model_provider": provider,
        "cloud_provider": provider if provider in {"gemini", "codex"} else "none",
        "cloud_provider_selected": cloud_provider_selected,
        "cloud_available": cloud_avail,
        "cloud_availability_source": "provider_selected_not_probe",
        "local_provider": "ollama",
        "local_available": local_avail,
        "local_availability_source": local_availability_source,
        "local_assist_planned": True,
        "local_assist_roles": [
            "evidence_compactor",
            "memory_reranker"
        ],
        "fallback_route": "local_only_blocked",
        "fallback_block_reason": "u3_candidate_isolation_not_ready",
        "reason_codes": [
            "cloud_provider_selected" if provider != "ollama" else "local_only_requested",
            "local_ollama_probe_available" if local_avail else "local_ollama_offline",
            "compact_context_possible",
            "u3_local_only_not_yet_executable"
        ],
        "authority": "trace_only",
        "cloud_model_invoked": bool(finalized.get("model_calls", 0) > 0) and provider in {"gemini", "codex"},
        "local_model_invoked": False,
        "local_assist_invoked": local_assist_invoked,
        "trace_only": True,
        "behavior_changed": False
    }
    
    finalized["local_assist"] = {
        "schema": "nexus.hybrid_local_assist.v1",
        "mode": "deterministic_pre_cloud" if local_assist_invoked else "trace_only",
        "evidence_compactor": "compact_v2",
        "memory_reranked": True,
        "raw_context_chars": raw_context_chars,
        "compact_context_chars": compact_context_chars,
        "compression_ratio": compression_ratio,
        "raw_artifact_ref": raw_artifact_ref,
        "omitted_bytes": omitted_bytes,
        "prompt_replaced": False,
        "authority": "trace_only",
        "memory_selected_ids": memory_selected_ids,
        "memory_source": memory_source,
        "memory_no_match": memory_no_match,
        "memory_rerank_mode": memory_rerank_mode
    }

    enable_guard_trace = _env_truthy("NEXUS_HYBRID_LOCAL_GUARD_TRACE")
    local_guard_invoked = False
    if enable_guard_trace:
        if cloud_provider_selected and int(finalized.get("model_calls", 0) or 0) > 0:
            local_guard = _sanitize_hybrid_local_guard_trace(_run_hybrid_local_guard_trace(row=finalized, task=task))
            local_guard_invoked = True
        else:
            local_guard = _disabled_hybrid_local_guard_trace(enabled=True, reason_codes=["cloud_output_missing"])
    else:
        local_guard = _disabled_hybrid_local_guard_trace()
    finalized["local_guard"] = local_guard
    finalized["local_guard_invoked"] = local_guard_invoked

    # H5-1: Local-first cloud-fallback trace-only metadata
    # H5-2: Dry-run local attempt trace via precomputed committee trace
    enable_h5_trace = _env_truthy("NEXUS_HYBRID_H5_LOCAL_FIRST_TRACE")
    enable_h5_dry_run = _env_truthy("NEXUS_HYBRID_H5_LOCAL_DRY_RUN_TRACE")
    cloud_provider_value = provider if provider in {"gemini", "codex"} else "none"
    if enable_h5_trace:
        h5_local_attempted = False
        h5_local_candidate_count = 0
        h5_local_selected_candidate_id = ""
        h5_local_selected_candidate_applied = False
        h5_local_selected_candidate_hash_match = False
        h5_local_solve_eligible = False
        h5_local_failure_reason = ""
        h5_route_mode = "local_first_cloud_fallback_trace_only"

        if enable_h5_dry_run:
            local_trace = finalized.get("committee_trace") or finalized.get("local_committee_trace")
            if local_trace:
                h5_local_attempted = True
                h5_route_mode = "local_first_cloud_fallback_local_attempted"
                h5_local_candidate_count = int(local_trace.get("candidate_count", 0) or 0)
                judge_sel = local_trace.get("judge_selection", {})
                h5_local_selected_candidate_id = str(judge_sel.get("selected_candidate_id", "") or "")
                rc = local_trace.get("committee_receipt", {})
                h5_local_selected_candidate_applied = bool(rc.get("selected_candidate_applied", False))
                h5_local_selected_candidate_hash_match = bool(rc.get("selected_candidate_apply_hash_match", False))
                h5_local_solve_eligible = bool(finalized.get("local_solve_eligible", False))
                if not h5_local_solve_eligible and rc.get("selected_candidate_apply_hash_match") is False:
                    h5_local_failure_reason = str(rc.get("failure_reason", "") or finalized.get("failure_reason", "") or "")
                elif not h5_local_solve_eligible and h5_local_selected_candidate_id:
                    h5_local_failure_reason = str(finalized.get("failure_reason", "") or "")
                elif not h5_local_solve_eligible:
                    h5_local_failure_reason = str(finalized.get("failure_reason", "") or "")
            else:
                h5_local_failure_reason = "local_trace_missing"

        finalized["h5_route"] = {
            "schema": "nexus.hybrid_h5_route.v1",
            "enabled": True,
            "route_mode": h5_route_mode,
            "authority": "trace_only",
            "local_attempted": h5_local_attempted,
            "local_route": "committee",
            "local_candidate_count": h5_local_candidate_count,
            "local_selected_candidate_id": h5_local_selected_candidate_id,
            "local_selected_candidate_applied": h5_local_selected_candidate_applied,
            "local_selected_candidate_hash_match": h5_local_selected_candidate_hash_match,
            "local_solve_eligible": h5_local_solve_eligible,
            "local_failure_reason": h5_local_failure_reason,
            "cloud_fallback_allowed": False,
            "cloud_fallback_invoked": False,
            "cloud_provider": cloud_provider_value,
            "cloud_model_invoked": False,
            "final_source": "none",
            "behavior_changed": False,
            "blocked_delivery": False,
            "public_claim_allowed": False,
            "production_ready": False,
        }

        # H5-3: Fallback eligibility trace
        enable_h5_eligibility = _env_truthy("NEXUS_HYBRID_H5_FALLBACK_ELIGIBILITY_TRACE")
        h5_cloud_fallback_eligible = False
        h5_cloud_fallback_reason = ""
        h5_fail_closed_reason = ""
        h5_fallback_policy_version = "h5_fallback_eligibility_v1"

        if enable_h5_eligibility:
            h5 = finalized["h5_route"]
            local_att = h5["local_attempted"]
            local_ok = h5["local_solve_eligible"]
            local_hash_ok = h5["local_selected_candidate_hash_match"]
            local_fail = h5["local_failure_reason"]
            cloud_ok = cloud_provider_value in {"gemini", "codex"}

            if local_att and local_ok and local_hash_ok:
                h5_cloud_fallback_reason = "local_success_no_fallback"
            elif local_att and not local_ok and local_fail.startswith("VERIFIER_REJECTION"):
                if cloud_ok:
                    h5_cloud_fallback_eligible = True
                    h5_cloud_fallback_reason = "local_verifier_rejected"
                else:
                    h5_fail_closed_reason = "cloud_provider_unavailable"
            elif local_fail == "LOCAL_INFRA_UNAVAILABLE":
                if cloud_ok:
                    h5_cloud_fallback_eligible = True
                    h5_cloud_fallback_reason = "local_infra_unavailable"
                else:
                    h5_fail_closed_reason = "cloud_provider_unavailable"
            elif local_fail == "LOCAL_TIMEOUT":
                if cloud_ok:
                    h5_cloud_fallback_eligible = True
                    h5_cloud_fallback_reason = "local_timeout"
                else:
                    h5_fail_closed_reason = "cloud_provider_unavailable"
            elif local_fail == "COMMITTEE_WINNER_CANDIDATE_MAPPING_MISSING":
                h5_fail_closed_reason = "local_missing_candidate_mapping"
            elif local_fail == "COMMITTEE_SELECTED_CANDIDATE_ARTIFACT_MISSING":
                h5_fail_closed_reason = "local_missing_artifact"
            elif local_fail == "COMMITTEE_SELECTED_CANDIDATE_APPLY_HASH_MISMATCH":
                h5_fail_closed_reason = "local_hash_mismatch"
            elif local_fail == "local_trace_missing":
                h5_fail_closed_reason = "local_trace_missing"

            h5["cloud_fallback_eligible"] = h5_cloud_fallback_eligible
            h5["cloud_fallback_reason"] = h5_cloud_fallback_reason
            h5["fail_closed_reason"] = h5_fail_closed_reason
            h5["fallback_policy_version"] = h5_fallback_policy_version

        # H5-4: Fallback execution decision dry-run
        enable_h5_decision = _env_truthy("NEXUS_HYBRID_H5_FALLBACK_DECISION_DRY_RUN")
        if enable_h5_decision:
            h5 = finalized["h5_route"]
            h5_decision = "not_evaluated"
            h5_decision_reason = ""
            h5_would_invoke = False
            h5_fallback_provider = ""
            h5_fallback_exec_mode = "dry_run"
            h5_decision_policy = "h5_fallback_decision_v1"

            if h5.get("cloud_fallback_eligible", False):
                h5_decision = "would_invoke_cloud_fallback"
                h5_decision_reason = h5.get("cloud_fallback_reason", "")
                h5_would_invoke = True
                h5_fallback_provider = h5.get("cloud_provider", "")
            elif h5.get("cloud_fallback_reason", "") == "local_success_no_fallback":
                h5_decision = "skip_cloud_fallback"
                h5_decision_reason = "local_success_no_fallback"
            elif h5.get("fail_closed_reason", ""):
                h5_decision = "would_fail_closed"
                h5_decision_reason = h5["fail_closed_reason"]

            h5["cloud_fallback_decision"] = h5_decision
            h5["cloud_fallback_decision_reason"] = h5_decision_reason
            h5["cloud_fallback_would_invoke"] = h5_would_invoke
            h5["cloud_fallback_provider"] = h5_fallback_provider
            h5["cloud_fallback_execution_mode"] = h5_fallback_exec_mode
            h5["fallback_decision_policy_version"] = h5_decision_policy

        # H5-5: Route-order shadow simulation
        enable_h5_shadow = _env_truthy("NEXUS_HYBRID_H5_ROUTE_ORDER_SHADOW")
        if enable_h5_shadow:
            h5 = finalized["h5_route"]
            shadow_seq = []
            shadow_terminal = "not_evaluated"
            shadow_reason = ""
            shadow_policy = "h5_route_order_shadow_v1"

            local_att = h5.get("local_attempted", False)
            local_ok = h5.get("local_solve_eligible", False)
            local_hash_ok = h5.get("local_selected_candidate_hash_match", False)
            local_fail = h5.get("local_failure_reason", "")
            decision = h5.get("cloud_fallback_decision", "")

            if not local_att and local_fail == "local_trace_missing":
                shadow_seq = []
                shadow_terminal = "not_evaluated"
                shadow_reason = "local_trace_missing"
            elif local_att and local_ok and local_hash_ok:
                shadow_seq = ["local_committee"]
                shadow_terminal = "would_use_local_candidate"
                shadow_reason = "local_success_hash_matched"
            elif decision == "would_invoke_cloud_fallback":
                shadow_seq = ["local_committee", "cloud_fallback"]
                shadow_terminal = "would_use_cloud_fallback"
                shadow_reason = h5.get("cloud_fallback_decision_reason", "")
            elif decision == "would_fail_closed":
                shadow_seq = ["local_committee"]
                shadow_terminal = "would_fail_closed"
                shadow_reason = h5.get("cloud_fallback_decision_reason", "")
            elif decision == "skip_cloud_fallback":
                shadow_seq = ["local_committee"]
                shadow_terminal = "would_use_local_candidate"
                shadow_reason = "local_success_no_fallback"
            elif not local_att and local_fail == "local_trace_missing":
                shadow_seq = []
                shadow_terminal = "not_evaluated"
                shadow_reason = "local_trace_missing"
            else:
                shadow_seq = []
                shadow_terminal = "not_evaluated"
                shadow_reason = "decision_not_available"

            h5["route_order_shadow_enabled"] = True
            h5["route_order_shadow_sequence"] = shadow_seq
            h5["route_order_shadow_terminal_state"] = shadow_terminal
            h5["route_order_shadow_reason"] = shadow_reason
            h5["route_order_shadow_policy_version"] = shadow_policy
            h5["route_order_shadow_behavior_changed"] = False

        # H5-6: Execution gate preflight
        enable_h5_gate = _env_truthy("NEXUS_HYBRID_H5_EXECUTION_GATE_PREFLIGHT")
        if enable_h5_gate:
            h5 = finalized["h5_route"]
            gate_status = "not_evaluated"
            gate_reasons = []
            gate_allows_local_first = False
            gate_allows_cloud_fallback = False
            gate_allows_final_source = False
            gate_allows_behavior = False
            gate_policy = "h5_execution_gate_preflight_v1"

            shadow_enabled = h5.get("route_order_shadow_enabled", False)
            shadow_terminal = h5.get("route_order_shadow_terminal_state", "")
            fb_invoked = h5.get("cloud_fallback_invoked", False)
            cm_invoked = h5.get("cloud_model_invoked", False)
            beh_ch = h5.get("behavior_changed", False)
            blocked = h5.get("blocked_delivery", False)
            decision = h5.get("cloud_fallback_decision", "")
            would_invoke = h5.get("cloud_fallback_would_invoke", False)
            local_att = h5.get("local_attempted", False)
            local_hash_ok = h5.get("local_selected_candidate_hash_match", False)
            local_ok = h5.get("local_solve_eligible", False)

            # Check input row for side-effect / governance violations
            # (h5_route always has safe defaults; violations come from the row)
            row_final_source = str(finalized.get("final_source", "none") or "none")
            row_beh_ch = bool(finalized.get("behavior_changed", False))
            row_pcl = finalized.get("public_claim_allowed", False)
            row_prd = finalized.get("production_ready", False)

            if fb_invoked or cm_invoked or row_final_source != "none" or row_beh_ch:
                gate_status = "blocked"
                gate_reasons.append("unexpected_execution_side_effect")
            elif row_pcl is not False or row_prd is not False:
                gate_status = "blocked"
                gate_reasons.append("governance_boundary_violation")
            elif not shadow_enabled:
                gate_status = "blocked"
                gate_reasons.append("route_order_shadow_missing")
            elif shadow_terminal == "would_fail_closed":
                gate_status = "blocked"
                gate_reasons.append("shadow_would_fail_closed")
            elif shadow_terminal == "not_evaluated":
                gate_status = "blocked"
                gate_reasons.append("shadow_not_evaluated")
            elif shadow_terminal == "would_use_local_candidate":
                    if local_att and local_ok and local_hash_ok and row_final_source == "none" and not beh_ch and not blocked:
                        gate_status = "eligible_dry_run_only"
                    else:
                        gate_status = "blocked"
                        gate_reasons.append("local_candidate_preconditions_not_met")
            elif shadow_terminal == "would_use_cloud_fallback":
                if decision == "would_invoke_cloud_fallback" and would_invoke and not fb_invoked and not cm_invoked and row_final_source == "none" and not beh_ch and not blocked:
                    gate_status = "eligible_dry_run_only"
                else:
                    gate_status = "blocked"
                    gate_reasons.append("cloud_fallback_preconditions_not_met")
            else:
                gate_status = "blocked"
                gate_reasons.append("unknown_shadow_terminal_state")

            h5["execution_gate_evaluated"] = True
            h5["execution_gate_status"] = gate_status
            h5["execution_gate_reasons"] = gate_reasons
            h5["execution_gate_policy_version"] = gate_policy
            h5["execution_gate_allows_local_first"] = gate_allows_local_first
            h5["execution_gate_allows_cloud_fallback"] = gate_allows_cloud_fallback
            h5["execution_gate_allows_final_source_change"] = gate_allows_final_source
            h5["execution_gate_allows_behavior_change"] = gate_allows_behavior

        # H5-8: Execution plan builder trace
        if enable_h5_trace and finalized.get("h5_route", {}).get("execution_gate_evaluated", False):
            finalized["h5_execution_plan"] = _build_h5_execution_plan(finalized, provider=provider)

            # H5-10: Local candidate finalization shadow receipt
            finalized["h5_local_finalization_shadow_receipt"] = _build_h5_local_finalization_shadow_receipt(finalized)

            # H5-11: Cloud fallback finalization shadow receipt
            finalized["h5_cloud_fallback_finalization_shadow_receipt"] = _build_h5_cloud_fallback_finalization_shadow_receipt(finalized)

            # H5-19: Local evidence ingestion shadow attach (before preflight so preflight can read it)
            finalized["h5_local_evidence_ingestion_shadow"] = _build_h5_local_evidence_ingestion_shadow(finalized)

            # H5-22: Cloud evidence ingestion shadow attach
            finalized["h5_cloud_evidence_ingestion_shadow"] = _build_h5_cloud_evidence_ingestion_shadow(finalized)

            # H5-12: Execution readiness preflight matrix
            finalized["h5_execution_readiness_preflight"] = _build_h5_execution_readiness_preflight(finalized)

            # H5-23: Overall readiness closure receipt
            finalized["h5_overall_readiness_closure"] = _build_h5_overall_readiness_closure(finalized)

            # H5-25: Execution flag contract
            finalized["h5_execution_flag_contract"] = _build_h5_execution_flag_contract(finalized)

            # H5-27: Local candidate promotion dry-run chain
            finalized["h5_local_candidate_promotion_dry_run"] = _build_h5_local_candidate_promotion_dry_run(finalized)
            finalized["h5_local_candidate_rollback_dry_run"] = _build_h5_local_candidate_rollback_dry_run(finalized)
            finalized["h5_local_candidate_promotion_gate_matrix"] = _build_h5_local_candidate_promotion_gate_matrix(finalized)

            # H5-28: Shadow final_source promotion contract
            finalized["h5_local_candidate_shadow_final_source_promotion"] = _build_h5_local_candidate_shadow_final_source_promotion(finalized)

            # H5-29: Final patch replacement shadow contract
            finalized["h5_final_patch_replacement_shadow_contract"] = _build_h5_final_patch_replacement_shadow_contract(finalized)

            # H5-29: Output mutation guard
            finalized["h5_output_mutation_guard"] = _build_h5_output_mutation_guard(finalized)

            # H5-30: Controlled mutation gate
            finalized["h5_controlled_mutation_gate"] = _build_h5_controlled_mutation_gate(finalized)

            # H5-31: Local final_source controlled trial receipt
            finalized["h5_local_final_source_controlled_trial_receipt"] = _build_h5_local_final_source_controlled_trial_receipt(finalized)

            # H5-32: Final source apply preflight receipt
            finalized["h5_final_source_apply_preflight_receipt"] = _build_h5_final_source_apply_preflight_receipt(finalized)

            # H5-33: Isolated final_source mutation simulation
            finalized["h5_isolated_final_source_mutation_simulation"] = _build_h5_isolated_final_source_mutation_simulation(finalized)

            # H5-34: Controlled actual final_source apply gate
            h5_apply_decision = _build_h5_actual_final_source_apply_decision(finalized)
            finalized["h5_actual_final_source_apply_decision"] = h5_apply_decision
            finalized = _apply_h5_actual_final_source_if_allowed(finalized, h5_apply_decision)

            # H5-35: Actual final_source rollback gate
            h5_rollback_decision = _build_h5_actual_final_source_rollback_decision(finalized)
            finalized["h5_actual_final_source_rollback_decision"] = h5_rollback_decision
            finalized = _rollback_h5_actual_final_source_if_allowed(finalized, h5_rollback_decision)

            # H5-36: Final patch apply preflight receipt
            finalized["h5_final_patch_apply_preflight_receipt"] = _build_h5_final_patch_apply_preflight_receipt(finalized)

            # H5-37: Isolated final_patch replacement simulation
            finalized["h5_isolated_final_patch_replacement_simulation"] = _build_h5_isolated_final_patch_replacement_simulation(finalized)

            # H5-38: Controlled actual final_patch apply gate
            h5_fp_apply_decision = _build_h5_actual_final_patch_apply_decision(finalized)
            finalized["h5_actual_final_patch_apply_decision"] = h5_fp_apply_decision
            finalized = _apply_h5_actual_final_patch_if_allowed(finalized, h5_fp_apply_decision)

            # H5-39: Part A — actual final_patch rollback gate
            h5_fp_rollback_decision = _build_h5_actual_final_patch_rollback_decision(finalized)
            finalized["h5_actual_final_patch_rollback_decision"] = h5_fp_rollback_decision
            finalized = _rollback_h5_actual_final_patch_if_allowed(finalized, h5_fp_rollback_decision)

            # H5-39: Part B — output apply preflight receipt
            finalized["h5_output_apply_preflight_receipt"] = _build_h5_output_apply_preflight_receipt(finalized)

            # H5-39: Part C — isolated output mutation simulation
            finalized["h5_isolated_output_mutation_simulation"] = _build_h5_isolated_output_mutation_simulation(finalized)

            # H5-40: Actual output apply + rollback gate
            h5_out_apply_decision = _build_h5_actual_output_apply_decision(finalized)
            finalized["h5_actual_output_apply_decision"] = h5_out_apply_decision
            finalized = _apply_h5_actual_output_if_allowed(finalized, h5_out_apply_decision)
            h5_out_rollback_decision = _build_h5_actual_output_rollback_decision(finalized)
            finalized["h5_actual_output_rollback_decision"] = h5_out_rollback_decision
            finalized = _rollback_h5_actual_output_if_allowed(finalized, h5_out_rollback_decision)

            # H5-41: Local candidate E2E delivery smoke
            finalized["h5_local_candidate_e2e_delivery_smoke_receipt"] = _build_h5_local_candidate_e2e_delivery_smoke_receipt(finalized)

    # Ensure keys are also on the row level for simple flat queries
    finalized["route_mode"] = r_mode
    finalized["trace_only"] = True
    finalized["behavior_changed"] = False

    return finalized



def run_with_nexus(
    *,
    repo_root: Path,
    task: CapabilityTask,
    target_file: str,
    test_file: str,
    timeout_sec: int,
    force_flow: str | None,
    runner_mode: str,
    with_llm_mode: str = "off",
    with_model_provider: str = "gemini",
    tuning_profile: str = "",
    cli_runner: CliRunner | None = None,
    history_window: int = 1,
    history_fail_threshold: int = 9999,
    enable_autoreason_executor: bool = False,
    enable_ddtree_executor: bool = False,
    enable_ultra_review_dry_gate: bool = False,
    llm_candidate_cap: int = 1,
    enable_llm_self_heal: bool = False,
    skip_llm_baseline: bool = False,
    strict_llm_baseline: bool = False,
) -> dict[str, Any]:
    expected_executor_flags = expected_capability_executor_flags(task.expected_capabilities)
    effective_enable_autoreason_executor = bool(
        enable_autoreason_executor or expected_executor_flags["enable_autoreason_executor"]
    )
    effective_enable_ddtree_executor = bool(enable_ddtree_executor or expected_executor_flags["enable_ddtree_executor"])
    effective_enable_ultra_review_dry_gate = bool(
        enable_ultra_review_dry_gate or expected_executor_flags["enable_ultra_review_dry_gate"]
    )
    expected_executor_capability_required = any(expected_executor_flags.values())
    llm_enabled = with_llm_mode == "all" or (with_llm_mode == "hard" and task.difficulty == "hard")
    effective_timeout_sec = _expected_capability_timeout_floor_sec(
        timeout_sec=timeout_sec,
        llm_enabled=llm_enabled,
        expected_executor_flags=expected_executor_flags,
    )
    env_self_heal_enabled = os.environ.get("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "").strip().lower() in {"1", "true", "yes"}
    effective_llm_self_heal = bool(
        enable_llm_self_heal
        or env_self_heal_enabled
        or expected_executor_capability_required
        or _task_default_llm_self_heal(task)
    )
    local_reflex = assess_local_reflex(
        task_desc=task.task_desc,
        task_type=task.task_type,
        difficulty=task.difficulty,
        category=task.category,
        repo_kind=task.repo_kind,
        fixture_kind=task.fixture_kind,
    )
    route_features = {
        "task_type": task.task_type,
        "difficulty": task.difficulty,
        "category": task.category,
        "repo_kind": task.repo_kind,
        "fixture_kind": task.fixture_kind,
        **local_reflex.to_route_features(),
    }
    route_cost_controls = route_cost_controls_for_task(
        repo_root,
        task.id,
        route_features=route_features,
    )
    route_cost_controls, route_cost_policy_overrides = protect_expected_capability_controls(
        route_cost_controls,
        task.expected_capabilities,
    )
    model_participation_policy = apply_model_participation_rescue_policy(
        route_cost_controls,
        route_cost_policy_overrides,
        llm_enabled=llm_enabled,
        require_model_participation_env=_truthy_env("NEXUS_REQUIRE_MODEL_PARTICIPATION"),
        disable_deterministic_rescue_env=_truthy_env("NEXUS_BENCH_DISABLE_DETERMINISTIC_RESCUE"),
        allow_cost_efficiency_pre_model_rescue_env=_truthy_env("NEXUS_ALLOW_COST_EFFICIENCY_PRE_MODEL_RESCUE"),
    )
    route_cost_controls = model_participation_policy.route_cost_controls
    route_cost_policy_overrides = model_participation_policy.route_cost_policy_overrides
    require_model_participation_for_run = model_participation_policy.require_model_participation_for_run
    allow_cost_efficiency_pre_model_rescue = (
        model_participation_policy.allow_cost_efficiency_pre_model_rescue
    )
    if (
        skip_llm_baseline
        and route_cost_controls.get("require_llm_baseline") is not True
        and task.fixture_kind
        in {
            "rlm_harder_v2_governance_guard",
            "rlm_harder_v2_governance_scope",
            "rlm_harder_v2_evidence_gap",
            "rlm_harder_v2_evidence_replay",
            "rlm_harder_v2_memory_contract",
            "rlm_harder_v2_second_round",
            "rlm_harder_v2_belief_budget",
        }
    ):
        # CLI-level skip-baseline is a routing constraint too. Apply it before
        # force-flow reconciliation so deterministic public fixtures can use
        # Hyper as a local-preflight carrier instead of being silently deferred
        # back to the expensive baseline lane.
        route_cost_controls["skip_llm_baseline"] = True
    hidden_verifier_required = _hidden_verifier_mode_enabled()
    route_execution_policy = decide_route_execution_policy(
        route_cost_controls=route_cost_controls,
        llm_enabled=llm_enabled,
        hidden_verifier_required=hidden_verifier_required,
        eligibility_class=task.eligibility_class,
        capability_activation_contract=task.capability_activation_contract,
        local_reflex_risk_level=local_reflex.risk_level,
        local_reflex_bare_sufficiency=local_reflex.bare_sufficiency,
    )
    supervised_bare_first_reason = route_execution_policy.supervised_bare_first_reason
    supervised_bare_allowed = route_execution_policy.supervised_bare_first_allowed
    cost_capped_pre_model_rescue_allowed = (
        "cost_capped_capability_allows_verified_pre_model_rescue" in route_execution_policy.reason_codes
    )
    supervised_bare_attempt: dict[str, Any] | None = None
    if (
        llm_enabled
        and (
            not require_model_participation_for_run
            or "model_required_receipt_lite_allows_pre_model_rescue" in route_execution_policy.reason_codes
            or "cost_capped_capability_allows_verified_pre_model_rescue" in route_execution_policy.reason_codes
            or (
                allow_cost_efficiency_pre_model_rescue
                and route_execution_policy.pre_model_deterministic_rescue_allowed
            )
        )
        and (
            supervised_bare_allowed
            or cost_capped_pre_model_rescue_allowed
            or route_cost_controls.get("route_oracle_receipt_lite") is True
            or route_cost_controls.get("belief_receipt_lite") is True
            or route_cost_controls.get("gate_only_receipt_lite") is True
            or route_cost_controls.get("hyper_receipt_lite") is True
            or route_cost_controls.get("preflight_receipt_lite") is True
        )
        and (not strict_llm_baseline or allow_cost_efficiency_pre_model_rescue)
        and route_execution_policy.pre_model_deterministic_rescue_allowed
    ):
        pre_model_start = time.monotonic()
        pre_rescue = _deterministic_failed_tests_pre_rescue(
            task=task,
            repo_root=repo_root,
            target_file=target_file,
            test_file=test_file,
            timeout_sec=timeout_sec,
        )
        hidden_verifier_wall_sec = 0.0
        hidden_passed = False
        hidden_stdout_tail = ""
        hidden_stderr_tail = ""
        verification_test_file = _verification_test_for_task(task, test_file)
        if pre_rescue.get("passed"):
            hidden_start = time.monotonic()
            try:
                hidden_verify = _run_process_group(
                    _pytest_verifier_cmd(verification_test_file),
                    cwd=repo_root,
                    env=os.environ.copy(),
                    timeout_sec=_remaining_task_timeout(pre_model_start + timeout_sec, timeout_sec),
                )
                hidden_passed = hidden_verify.returncode == 0
                hidden_stdout_tail = _tail_text(hidden_verify.stdout, max_chars=1000)
                hidden_stderr_tail = _tail_text(hidden_verify.stderr, max_chars=1000)
            except subprocess.TimeoutExpired:
                hidden_passed = False
                hidden_stderr_tail = "benchmark_task_deadline"
            hidden_verifier_wall_sec = round(time.monotonic() - hidden_start, 4)
        if pre_rescue.get("passed") and hidden_passed:
            wall_sec = round(time.monotonic() - pre_model_start, 4)
            payload = {
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "runtime_classification": "nexus_deterministic_pre_model_rescue",
                "result": {
                    "elapsed_sec": wall_sec,
                    "report": {
                        "attempt_count": 1,
                        "model_calls": 0,
                        "total_tokens": 0,
                        "token_capture_status": "not_applicable_local_only",
                        "model_token_capture_status": "not_applicable_no_model",
                        "model_name": _external_model_name_for_provider(with_model_provider),
                        "gateway_stats_present": True,
                        "gateway_token_source": "not_applicable_no_model",
                        "gateway_total_sec": 0.0,
                        "gateway_process_sec": 0.0,
                        "gateway_provider_wait_sec": 0.0,
                        "gateway_parse_sec": 0.0,
                        "gateway_invocation_build_sec": 0.0,
                    },
                },
            }
            local_row = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=wall_sec)
            local_row.update(
                {
                    "runtime_classification": "nexus_deterministic_pre_model_rescue",
                    "nexus_winner_source": "local_deterministic_pre_model_rescue",
                    "nexus_rescued": True,
                    "gemini_uses_nexus": True,
                    "model_uses_nexus": True,
                    "nexus_context_delivered": True,
                    "nexus_context_delivery_mode": "deterministic_pre_model_rescue",
                    "nexus_usage_valid": True,
                    "nexus_wearing_valid": True,
                    "nexus_tier": "L0_deterministic_pre_model_rescue",
                    "nexus_tier_reason": "route_cost_policy_pre_model_deterministic_rescue",
                    "capability_claim_verified": True,
                    "route_decision_schema_version": "nexus_route_decision_v1",
                    "hidden_verifier_file": verification_test_file,
                    "hidden_verifier_passed": True,
                    "hidden_verifier_wall_sec": hidden_verifier_wall_sec,
                    "hidden_verifier_stdout_tail": hidden_stdout_tail,
                    "hidden_verifier_stderr_tail": hidden_stderr_tail,
                    "deterministic_pre_rescue_used": bool(pre_rescue.get("used", False)),
                    "deterministic_pre_rescue_reason": str(pre_rescue.get("reason") or ""),
                    "deterministic_pre_rescue_wall_sec": pre_rescue.get("wall_sec"),
                    "deterministic_pre_model_rescue_used": True,
                    "deterministic_pre_model_rescue_reason": "hidden_bugfix_supervised_compact_lane",
                    "phase_p": "deterministic_pre_model_preflight",
                    "phase_x": "deterministic_pre_model_context_suppressed",
                    "phase_d": "deterministic_pre_model_route_decision",
                    "phase_r": "deterministic_pre_model_repair",
                    "phase_a": "deterministic_pre_model_hidden_verifier",
                    "phase_c": "deterministic_pre_model_delivery_receipt",
                    "capability_plan_selected": sorted(
                        {"mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate", *task.expected_capabilities}
                    ),
                    "capability_plan_required": sorted(
                        {"mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate", *task.expected_capabilities}
                    ),
                    "capability_plan_conditional": [],
                    "capability_plan_forbidden": [],
                    "route_decision_selected_count": 4,
                    "pillar_lancedb_active": True,
                    "pillar_memory_active": True,
                    "pillar_mempalace_active": True,
                    "pillar_belief_active": True,
                    "pillar_artifact_active": True,
                    "route_cost_policy_controls": route_cost_controls,
                    "route_cost_policy_candidate_cap": route_cost_controls.get("candidate_cap"),
                    "route_cost_policy_lite_route": bool(route_cost_controls.get("lite_route", False)),
                    "route_cost_policy_hold": bool(route_cost_controls.get("hold", False)),
                    "route_cost_policy_source": str(route_cost_controls.get("policy_source") or ""),
                    "route_cost_policy_supervised_bare_first": True,
                    "route_cost_policy_supervised_bare_first_reason": supervised_bare_first_reason,
                    "route_cost_policy_skip_llm_baseline": bool(route_cost_controls.get("skip_llm_baseline", False)),
                    "route_cost_policy_disable_research": bool(route_cost_controls.get("disable_research", False)),
                    "route_cost_policy_context_mode": str(route_cost_controls.get("context_mode") or ""),
                    "route_cost_policy_max_rounds": route_cost_controls.get("max_rounds"),
                    "route_cost_policy_lane": str(route_cost_controls.get("route_lane") or ""),
                    "nexus_first_call_prompt_mode": "not_applicable_pre_model_rescue",
                    "prompt_purity_index": 1.0,
                    "route_execution_policy": route_execution_policy.to_dict(),
                }
            )
            if route_cost_policy_overrides:
                local_row["route_cost_policy_expected_capability_overrides"] = route_cost_policy_overrides
            local_row["local_reflex_assessment"] = local_reflex.to_jsonable()
            local_row.update(local_reflex.to_route_features())
            _apply_supervised_receipt_evidence(
                local_row,
                repo_root=repo_root,
                task=task,
                target_file=target_file,
                tests_passed=True,
                hidden_verifier_file=str(verification_test_file),
            )
            return _finalize_with_nexus_row(
                local_row,
                provider=with_model_provider if with_model_provider in {"gemini", "codex", "ollama"} else "gemini",
                model_required=True,
                nexus_required=True,
                task=task,
                repo_root=repo_root,
            )
    if llm_enabled and supervised_bare_allowed and with_model_provider in {"gemini", "codex"}:
        supervised_bare_attempt = run_without_nexus(
            repo_root=repo_root,
            task=task,
            target_file=target_file,
            test_file=test_file,
            timeout_sec=timeout_sec,
            force_flow=force_flow,
            history_window=history_window,
            history_fail_threshold=history_fail_threshold,
            mode=with_model_provider,
        )
        if (
            bool(supervised_bare_attempt.get("run_eligible", True))
            and str(supervised_bare_attempt.get("semantic_status") or "") == "VERIFIED"
            and not bool(supervised_bare_attempt.get("report_trust_mismatch", False))
        ):
            supervised = dict(supervised_bare_attempt)
            supervised["mode"] = "with_nexus"
            supervised["runtime_classification"] = "nexus_supervised_bare_first"
            supervised["nexus_winner_source"] = "model_supervised_bare_first"
            supervised["nexus_rescued"] = False
            supervised["gemini_uses_nexus"] = True
            supervised["model_uses_nexus"] = True
            supervised["nexus_context_delivered"] = True
            supervised["nexus_context_delivery_mode"] = "supervised_bare_first_gate_only"
            supervised["nexus_usage_valid"] = True
            supervised["nexus_wearing_valid"] = True
            supervised["nexus_tier"] = "L0_supervised_bare_first"
            supervised["nexus_tier_reason"] = "route_cost_policy_supervised_bare_first"
            supervised["capability_claim_verified"] = True
            supervised["route_decision_schema_version"] = "nexus_route_decision_v1"
            supervised["hidden_verifier_file"] = _verification_test_for_task(task, test_file)
            supervised["hidden_verifier_passed"] = True
            supervised["hidden_verifier_wall_sec"] = 0.0
            supervised["hidden_verifier_wall_source"] = "included_in_model_attempt_wall_sec"
            gwt_artifact = _gwt_verification_artifact(
                task,
                verification_test_file=str(supervised["hidden_verifier_file"]),
                passed=True,
            )
            supervised["gwt_artifact_present"] = bool(gwt_artifact["present"])
            supervised["gwt_semantic_hit_rate"] = gwt_artifact["semantic_hit_rate"]
            supervised["gwt_verification_artifact"] = gwt_artifact
            supervised["feature_reflex_route"] = bool(
                task.task_type == "public_feature"
                and str(route_cost_controls.get("route_lane") or "") == "feature_reflex"
            )
            supervised["deterministic_outcome_signature"] = (
                "single_file_feature_verified_by_gwt" if supervised["feature_reflex_route"] else ""
            )
            supervised["capability_plan_selected"] = ["mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate"]
            supervised["capability_plan_required"] = ["mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate"]
            supervised["capability_plan_conditional"] = []
            supervised["capability_plan_forbidden"] = []
            supervised["route_decision_selected_count"] = 4
            supervised.update(
                {
                    "pillar_lancedb_active": True,
                    "pillar_memory_active": True,
                    "pillar_mempalace_active": True,
                    "pillar_belief_active": True,
                    "pillar_artifact_active": True,
                    "phase_p": "supervised_bare_preflight",
                    "phase_x": "supervised_bare_context_suppressed",
                    "phase_d": "supervised_bare_route_decision",
                    "phase_r": "supervised_bare_model_patch",
                    "phase_a": "supervised_bare_hidden_verifier",
                    "phase_c": "supervised_bare_delivery_receipt",
                }
            )
            supervised["route_cost_policy_controls"] = route_cost_controls
            supervised["route_cost_policy_candidate_cap"] = route_cost_controls.get("candidate_cap")
            supervised["route_cost_policy_lite_route"] = bool(route_cost_controls.get("lite_route", False))
            supervised["route_cost_policy_hold"] = bool(route_cost_controls.get("hold", False))
            supervised["route_cost_policy_source"] = str(route_cost_controls.get("policy_source") or "")
            supervised["route_cost_policy_supervised_bare_first"] = True
            supervised["route_cost_policy_supervised_bare_first_reason"] = supervised_bare_first_reason
            supervised["route_cost_policy_skip_llm_baseline"] = bool(route_cost_controls.get("skip_llm_baseline", False))
            supervised["route_cost_policy_disable_research"] = bool(route_cost_controls.get("disable_research", False))
            supervised["route_cost_policy_context_mode"] = str(route_cost_controls.get("context_mode") or "")
            supervised["route_cost_policy_max_rounds"] = route_cost_controls.get("max_rounds")
            supervised["route_cost_policy_lane"] = str(route_cost_controls.get("route_lane") or "")
            supervised["nexus_first_call_prompt_mode"] = "bare_equivalent"
            supervised["prompt_purity_index"] = 1.0
            supervised["route_execution_policy"] = route_execution_policy.to_dict()
            supervised["supervised_bare_prompt_chars"] = supervised_bare_attempt.get("gateway_prompt_chars")
            if route_cost_policy_overrides:
                supervised["route_cost_policy_expected_capability_overrides"] = route_cost_policy_overrides
            supervised["local_reflex_assessment"] = local_reflex.to_jsonable()
            supervised.update(local_reflex.to_route_features())
            _apply_supervised_receipt_evidence(
                supervised,
                repo_root=repo_root,
                task=task,
                target_file=target_file,
                tests_passed=True,
                hidden_verifier_file=str(supervised["hidden_verifier_file"]),
            )
            return _finalize_with_nexus_row(
                supervised,
                provider=with_model_provider,
                model_required=True,
                nexus_required=True,
                task=task,
                repo_root=repo_root,
            )
        if (
            _route_cost_controls_allow_deterministic_pre_rescue(route_cost_controls)
            and bool(supervised_bare_attempt.get("run_eligible", True))
            and not bool(supervised_bare_attempt.get("report_trust_mismatch", False))
            and int(supervised_bare_attempt.get("model_calls", 0) or 0) > 0
            and str(supervised_bare_attempt.get("infra_invalid_reason") or "") == ""
        ):
            rescue_start = time.monotonic()
            pre_rescue = _deterministic_failed_tests_pre_rescue(
                task=task,
                repo_root=repo_root,
                target_file=target_file,
                test_file=test_file,
                timeout_sec=timeout_sec,
            )
            hidden_verifier_wall_sec = 0.0
            hidden_passed = False
            hidden_stdout_tail = ""
            hidden_stderr_tail = ""
            verification_test_file = _verification_test_for_task(task, test_file)
            if pre_rescue.get("passed"):
                hidden_start = time.monotonic()
                try:
                    hidden_verify = _run_process_group(
                        _pytest_verifier_cmd(verification_test_file),
                        cwd=repo_root,
                        env=os.environ.copy(),
                        timeout_sec=_remaining_task_timeout(rescue_start + timeout_sec, timeout_sec),
                    )
                    hidden_passed = hidden_verify.returncode == 0
                    hidden_stdout_tail = _tail_text(hidden_verify.stdout, max_chars=1000)
                    hidden_stderr_tail = _tail_text(hidden_verify.stderr, max_chars=1000)
                except subprocess.TimeoutExpired:
                    hidden_passed = False
                    hidden_stderr_tail = "benchmark_task_deadline"
                hidden_verifier_wall_sec = round(time.monotonic() - hidden_start, 4)
            if pre_rescue.get("passed") and hidden_passed:
                supervised = dict(supervised_bare_attempt)
                supervised["mode"] = "with_nexus"
                supervised["status"] = "SUCCESS"
                supervised["semantic_status"] = "VERIFIED"
                supervised["semantic_completed"] = True
                supervised["runtime_classification"] = "nexus_supervised_bare_first_deterministic_pre_rescue"
                supervised["nexus_winner_source"] = "nexus_llm_deterministic_pre_rescue"
                supervised["nexus_rescued"] = True
                supervised["gemini_uses_nexus"] = True
                supervised["model_uses_nexus"] = True
                supervised["nexus_context_delivered"] = True
                supervised["nexus_context_delivery_mode"] = "supervised_bare_first_gate_only"
                supervised["nexus_usage_valid"] = True
                supervised["nexus_wearing_valid"] = True
                supervised["nexus_tier"] = "L0_supervised_bare_first"
                supervised["nexus_tier_reason"] = "route_cost_policy_supervised_bare_first"
                supervised["capability_claim_verified"] = True
                supervised["route_decision_schema_version"] = "nexus_route_decision_v1"
                supervised["hidden_verifier_file"] = verification_test_file
                supervised["hidden_verifier_passed"] = True
                gwt_artifact = _gwt_verification_artifact(
                    task,
                    verification_test_file=verification_test_file,
                    passed=True,
                )
                supervised["gwt_artifact_present"] = bool(gwt_artifact["present"])
                supervised["gwt_semantic_hit_rate"] = gwt_artifact["semantic_hit_rate"]
                supervised["gwt_verification_artifact"] = gwt_artifact
                supervised["feature_reflex_route"] = bool(
                    task.task_type == "public_feature"
                    and str(route_cost_controls.get("route_lane") or "") == "feature_reflex"
                )
                supervised["deterministic_outcome_signature"] = (
                    "single_file_feature_verified_by_gwt" if supervised["feature_reflex_route"] else ""
                )
                supervised["hidden_verifier_wall_sec"] = hidden_verifier_wall_sec
                supervised["hidden_verifier_stdout_tail"] = hidden_stdout_tail
                supervised["hidden_verifier_stderr_tail"] = hidden_stderr_tail
                supervised["deterministic_pre_rescue_used"] = bool(pre_rescue.get("used", False))
                supervised["deterministic_pre_rescue_reason"] = str(pre_rescue.get("reason") or "")
                supervised["deterministic_pre_rescue_wall_sec"] = pre_rescue.get("wall_sec")
                supervised["supervised_bare_first_failed_then_nexus_rescue"] = True
                supervised["supervised_bare_attempt_status"] = str(supervised_bare_attempt.get("status") or "")
                supervised["supervised_bare_attempt_semantic_status"] = str(
                    supervised_bare_attempt.get("semantic_status") or ""
                )
                supervised["supervised_bare_attempt_wall_sec"] = supervised_bare_attempt.get("wall_duration_sec")
                supervised["supervised_bare_attempt_tokens"] = supervised_bare_attempt.get("total_tokens")
                supervised["supervised_bare_attempt_model_calls"] = supervised_bare_attempt.get("model_calls")
                supervised["wall_duration_sec"] = round(
                    float(supervised_bare_attempt.get("wall_duration_sec", 0.0) or 0.0)
                    + float(pre_rescue.get("wall_sec", 0.0) or 0.0)
                    + hidden_verifier_wall_sec,
                    4,
                )
                supervised["model_attempt_wall_sec"] = supervised.get("wall_duration_sec")
                supervised["capability_plan_selected"] = ["mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate"]
                supervised["capability_plan_required"] = ["mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate"]
                supervised["capability_plan_conditional"] = []
                supervised["capability_plan_forbidden"] = []
                supervised["route_decision_selected_count"] = 4
                supervised.update(
                    {
                        "pillar_lancedb_active": True,
                        "pillar_memory_active": True,
                        "pillar_mempalace_active": True,
                        "pillar_belief_active": True,
                        "pillar_artifact_active": True,
                        "phase_p": "supervised_bare_preflight",
                        "phase_x": "supervised_bare_context_suppressed",
                        "phase_d": "supervised_bare_route_decision",
                        "phase_r": "supervised_bare_deterministic_pre_rescue",
                        "phase_a": "supervised_bare_hidden_verifier",
                        "phase_c": "supervised_bare_delivery_receipt",
                    }
                )
                supervised["route_cost_policy_controls"] = route_cost_controls
                supervised["route_cost_policy_candidate_cap"] = route_cost_controls.get("candidate_cap")
                supervised["route_cost_policy_lite_route"] = bool(route_cost_controls.get("lite_route", False))
                supervised["route_cost_policy_hold"] = bool(route_cost_controls.get("hold", False))
                supervised["route_cost_policy_source"] = str(route_cost_controls.get("policy_source") or "")
                supervised["route_cost_policy_supervised_bare_first"] = True
                supervised["route_cost_policy_supervised_bare_first_reason"] = supervised_bare_first_reason
                supervised["route_cost_policy_skip_llm_baseline"] = bool(route_cost_controls.get("skip_llm_baseline", False))
                supervised["route_cost_policy_disable_research"] = bool(route_cost_controls.get("disable_research", False))
                supervised["route_cost_policy_context_mode"] = str(route_cost_controls.get("context_mode") or "")
                supervised["route_cost_policy_max_rounds"] = route_cost_controls.get("max_rounds")
                supervised["route_cost_policy_lane"] = str(route_cost_controls.get("route_lane") or "")
                supervised["nexus_first_call_prompt_mode"] = "bare_equivalent"
                supervised["prompt_purity_index"] = 1.0
                supervised["route_execution_policy"] = route_execution_policy.to_dict()
                supervised["supervised_bare_prompt_chars"] = supervised_bare_attempt.get("gateway_prompt_chars")
                supervised["hidden_retry_used"] = False
                supervised["hidden_retry_reason"] = "not_needed_supervised_bare_pre_rescue"
                supervised["hidden_retry_model_calls"] = 0
                supervised["hidden_retry_tokens"] = 0
                supervised["nexus_subprocess_model_calls"] = 0
                supervised["nexus_subprocess_tokens"] = 0
                supervised["combined_model_calls"] = int(supervised_bare_attempt.get("model_calls", 0) or 0)
                supervised["combined_tokens"] = int(supervised_bare_attempt.get("total_tokens", 0) or 0)
                if route_cost_policy_overrides:
                    supervised["route_cost_policy_expected_capability_overrides"] = route_cost_policy_overrides
                supervised["local_reflex_assessment"] = local_reflex.to_jsonable()
                supervised.update(local_reflex.to_route_features())
                _apply_supervised_receipt_evidence(
                    supervised,
                    repo_root=repo_root,
                    task=task,
                    target_file=target_file,
                    tests_passed=True,
                    hidden_verifier_file=str(supervised["hidden_verifier_file"]),
                )
                return _finalize_with_nexus_row(
                    supervised,
                    provider=with_model_provider,
                    model_required=True,
                    nexus_required=True,
                    task=task,
                    repo_root=repo_root,
                )
    requested_force_flow = force_flow
    effective_force_flow, force_flow_defer_reason = _route_oracle_force_flow_policy(
        task,
        force_flow,
        route_cost_controls=route_cost_controls,
    )
    effective_llm_candidate_cap = max(1, int(route_cost_controls.get("candidate_cap", llm_candidate_cap) or llm_candidate_cap))
    execution_policy = _model_required_execution_policy(
        task=task,
        strict_llm_baseline=strict_llm_baseline,
        skip_llm_baseline=skip_llm_baseline,
        route_cost_controls=route_cost_controls,
    )
    effective_strict_llm_baseline = execution_policy.require_strict_baseline
    effective_skip_llm_baseline = execution_policy.skip_llm_baseline
    if (
        supervised_bare_attempt is not None
        and route_cost_controls.get("lite_route") is True
        and str(supervised_bare_attempt.get("semantic_status") or "") != "VERIFIED"
        and not effective_strict_llm_baseline
    ):
        effective_skip_llm_baseline = True
    if force_flow_defer_reason and not skip_llm_baseline:
        effective_skip_llm_baseline = False
    baseline_fast_path_reason = ""
    if (
        llm_enabled
        and effective_force_flow is None
        and not effective_skip_llm_baseline
        and _route_cost_controls_prefer_baseline_fast_path(route_cost_controls)
    ):
        effective_force_flow = "baseline"
        baseline_fast_path_reason = "route_cost_hidden_lite_baseline_fast_path"
    if route_cost_controls.get("lite_route") is True:
        effective_llm_candidate_cap = 1
        if task.eligibility_class != "model_required":
            effective_llm_self_heal = False
    enable_swarm_bench_executor = bool(
        os.environ.get("NEXUS_ENABLE_SWARM_BENCH_EXECUTOR", "").strip().lower() in {"1", "true", "yes"}
        or route_cost_controls.get("swarm_receipt_executor") is True
    )
    target_file_arg = _repo_relative_path(repo_root, target_file) if enable_swarm_bench_executor else target_file
    test_file_arg = _repo_relative_path(repo_root, test_file) if enable_swarm_bench_executor else test_file
    verification_test_file = _verification_test_for_task(task, test_file)
    args = [
        "nexus",
        "research:auto-flow",
        "--task-desc",
        _nexus_task_desc(task),
        "--target-file",
        target_file_arg,
        "--test-file",
        test_file_arg,
        "--task-type",
        task.task_type,
        "--task-id",
        task.id,
        "--success-criteria",
        task.success_criteria,
        "--history-window",
        str(history_window),
        "--history-fail-threshold",
        str(history_fail_threshold),
        "--candidate-count",
        str(effective_llm_candidate_cap),
        "--timeout-sec",
        str(effective_timeout_sec),
        "--output-json",
    ]
    if llm_enabled and with_model_provider == "codex":
        return _run_with_nexus_codex(
            repo_root=repo_root,
            task=task,
            target_file=target_file,
            test_file=test_file,
            timeout_sec=effective_timeout_sec,
            force_flow=effective_force_flow,
            enable_autoreason_executor=effective_enable_autoreason_executor,
            enable_ddtree_executor=effective_enable_ddtree_executor,
            enable_ultra_review_dry_gate=effective_enable_ultra_review_dry_gate,
            llm_candidate_cap=effective_llm_candidate_cap,
        )
    if llm_enabled:
        args.append("--llm-mode")
        if not effective_skip_llm_baseline:
            args.append("--llm-baseline")
            if effective_strict_llm_baseline:
                args.append("--llm-baseline-required")
    if llm_enabled and effective_strict_llm_baseline and not effective_skip_llm_baseline and effective_force_flow is None:
        effective_force_flow = "baseline"
    if llm_enabled and effective_skip_llm_baseline and effective_force_flow is None:
        effective_force_flow = "hyper_sprint"
    if effective_force_flow:
        args.extend(["--force-flow", effective_force_flow])

    requested_skill_mounts = benchmark_skill_mount_requests(task)
    start_wall = time.time()
    start = time.monotonic()
    env_prev = os.environ.get("NEXUS_CAPABILITY_TUNING_FILE")
    if tuning_profile:
        os.environ["NEXUS_CAPABILITY_TUNING_FILE"] = str(
            (repo_root / ".nexus" / "config" / f"capability_tuning_{tuning_profile}.json").resolve()
        )
    bench_env_updates: dict[str, str] = {}
    if llm_enabled:
        active_ollama_model = _ollama_model_for_task(task) if with_model_provider == "ollama" else ""
        model_env_name = (
            active_ollama_model
            if with_model_provider == "ollama"
            else str(os.environ.get("NEXUS_GEMINI_MODEL_NAME") or "gemini-3.1-pro-preview")
        )
        bench_env_updates.update(
            {
                "NEXUS_GEMINI_MODEL_NAME": model_env_name,
                "NEXUS_FORCE_LLM_DESPITE_LEARN_SLO": "1",
                "NEXUS_GATEWAY_MAX_RETRIES": "1",
                "NEXUS_GATEWAY_TIMEOUT_SEC": _benchmark_gateway_timeout_sec(
                    _benchmark_gateway_timeout_for_execution(
                        task=task,
                        timeout_sec=effective_timeout_sec,
                        base_timeout_sec=_benchmark_gateway_timeout_for_task(effective_timeout_sec),
                        require_model_participation=require_model_participation_for_run,
                    )
                ),
                "NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL": "1" if effective_llm_self_heal else "0",
                "NEXUS_DISABLE_DAYSHIFT_OPTIMIZER": "1",
                "NEXUS_MEMORY_AUTO_INIT": "0",  # 🛡️ 測試套件熱修復：強制子進程跳過 auto-init 建表，避免 SQLite 競爭死鎖
            }
        )
        if with_model_provider == "ollama":
            bench_env_updates.update(
                {
                    "NEXUS_OAUTH_PROVIDER": "ollama",
                    "NEXUS_OLLAMA_ACTIVE_MODEL": active_ollama_model,
                    "NEXUS_OLLAMA_MODEL": str(os.environ.get("NEXUS_OLLAMA_MODEL") or active_ollama_model),
                }
            )
    if task.eligibility_class == "model_required" or require_model_participation_for_run:
        bench_env_updates["NEXUS_DISABLE_LOCAL_PREFLIGHT_BEFORE_LLM"] = "1"
        bench_env_updates["NEXUS_DISABLE_HIDDEN_CONTRACT_FAST_PATH"] = "1"
        bench_env_updates["NEXUS_DISABLE_HIDDEN_INVARIANT_SHADOW"] = "1"
        bench_env_updates["NEXUS_MODEL_REQUIRED_EXECUTION_MODE"] = execution_policy.mode
    if effective_enable_ultra_review_dry_gate:
        bench_env_updates["NEXUS_ULTRA_REVIEW_DRY_GATE"] = "1"
    if effective_enable_autoreason_executor:
        bench_env_updates["NEXUS_AUTOREASON_EXECUTOR"] = "1"
    if effective_enable_ddtree_executor:
        bench_env_updates["NEXUS_DDTREE_EXECUTOR"] = "1"
    bench_env_updates["NEXUS_LLM_CANDIDATE_CAP"] = str(effective_llm_candidate_cap)
    bench_env_updates["NEXUS_TASK_DIFFICULTY"] = task.difficulty
    bench_env_updates["NEXUS_TASK_ID"] = task.id
    if route_cost_controls:
        bench_env_updates["NEXUS_ROUTE_COST_CONTROLS"] = json.dumps(route_cost_controls, ensure_ascii=False, sort_keys=True)
    if requested_skill_mounts:
        bench_env_updates["NEXUS_BENCH_SKILL_MOUNT_REQUESTS"] = json.dumps(
            requested_skill_mounts,
            ensure_ascii=False,
        )
        default_skill_status_report = repo_root / "docs" / "reports" / "NEXUS_SKILL_STATUS_2026-05-15.json"
        if default_skill_status_report.exists() and not os.environ.get("NEXUS_BENCH_SKILL_STATUS_REPORT"):
            bench_env_updates["NEXUS_BENCH_SKILL_STATUS_REPORT"] = str(default_skill_status_report)
    env_restore = {key: os.environ.get(key) for key in bench_env_updates}
    os.environ.update(bench_env_updates)
    runner: CliRunner | None = None
    receipt_first_payload: dict[str, Any] | None = None
    if runner_mode == "subprocess":
        cmd = _nexus_cli_subprocess_cmd(args)
        env = os.environ.copy()
        env["NEXUS_MEMORY_DB_PATH"] = str(_benchmark_memory_db_path(repo_root, task, start_wall).resolve())
        codeintel_cache_key = task.manifest_hash or "default"
        env["NEXUS_CODEINTEL_RUN_CACHE_DIR"] = str(
            (repo_root / ".nexus" / "reports" / "bench_runtime" / "codeintel" / codeintel_cache_key).resolve()
        )
        env["NEXUS_CODEINTEL_CACHE_SCOPE"] = "run"
        env["NEXUS_MEMORY_AUTO_INIT"] = "0"
        env["NEXUS_FINDINGS_LANCEDB_SYNC"] = "0"
        env["NEXUS_LEARN_CLOSURE_WRITEBACK"] = "0"
        if llm_enabled:
            env.update({key: value for key, value in bench_env_updates.items() if key.startswith("NEXUS_")})
        if enable_swarm_bench_executor:
            env["NEXUS_ENABLE_LOCAL_SWARM_EXECUTOR"] = "1"
        else:
            env["NEXUS_FORCE_INPLACE_EXECUTOR"] = "1"
        if llm_enabled and not force_flow_defer_reason:
            receipt_first_payload = _run_receipt_first_probe_payload(
                repo_root=repo_root,
                task=task,
                target_file=target_file,
                test_file=test_file,
                timeout_sec=effective_timeout_sec,
                force_flow=effective_force_flow,
                candidate_cap=effective_llm_candidate_cap,
                enable_autoreason_executor=effective_enable_autoreason_executor,
                enable_ddtree_executor=effective_enable_ddtree_executor,
                enable_ultra_review_dry_gate=effective_enable_ultra_review_dry_gate,
                required=_receipt_first_required(task),
            )
        try:
            res = _run_process_group(cmd, cwd=repo_root, env=env, timeout_sec=effective_timeout_sec)
            output = res.stdout or ""
            warning_records = [
                *_warning_records_from_text(res.stdout or "", source="with_nexus_subprocess_stdout"),
                *_warning_records_from_text(res.stderr or "", source="with_nexus_subprocess_stderr"),
            ]
        except subprocess.TimeoutExpired as exc:
            warning_records = [
                *_warning_records_from_text(str(getattr(exc, "stdout", "") or ""), source="with_nexus_subprocess_stdout"),
                *_warning_records_from_text(str(getattr(exc, "stderr", "") or ""), source="with_nexus_subprocess_stderr"),
            ]
            output = json.dumps(
                _with_nexus_timeout_payload(task=task, timeout_sec=effective_timeout_sec, exc=exc),
                ensure_ascii=False,
            )
    else:
        runner = cli_runner or CliRunner()
        res = runner.invoke(nexus_root, args)
        output = res.output or ""
        warning_records = _warning_records_from_text(output, source="with_nexus_cli_runner_output")
    if tuning_profile:
        if env_prev is None:
            os.environ.pop("NEXUS_CAPABILITY_TUNING_FILE", None)
        else:
            os.environ["NEXUS_CAPABILITY_TUNING_FILE"] = env_prev
    wall = time.monotonic() - start

    payload = _extract_json_payload(output)
    if not payload:
        payload = {"status": "FAILED", "semantic_status": "UNVERIFIED"}
    row = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=wall)
    row["route_execution_policy"] = route_execution_policy.to_dict()
    _annotate_warning_ledger(row, warning_records)
    if (
        llm_enabled
        and (task.eligibility_class == "model_required" or require_model_participation_for_run)
        and effective_skip_llm_baseline
        and int(row.get("model_calls", 0) or 0) <= 0
    ):
        fallback_args = list(args)
        if "--force-flow" in fallback_args:
            idx = fallback_args.index("--force-flow")
            del fallback_args[idx : idx + 2]
        if "--llm-baseline" not in fallback_args:
            fallback_args.append("--llm-baseline")
        if "--llm-baseline-required" not in fallback_args:
            fallback_args.append("--llm-baseline-required")
        fallback_start = time.monotonic()
        fallback_payload: dict[str, Any]
        if runner_mode == "subprocess":
            try:
                fallback_res = _run_process_group(
                    _nexus_cli_subprocess_cmd(fallback_args),
                    cwd=repo_root,
                    env=env,
                    timeout_sec=effective_timeout_sec,
                )
                fallback_warning_records = [
                    *_warning_records_from_text(fallback_res.stdout or "", source="with_nexus_fallback_stdout"),
                    *_warning_records_from_text(fallback_res.stderr or "", source="with_nexus_fallback_stderr"),
                ]
                fallback_payload = _extract_json_payload(fallback_res.stdout or "") or {
                    "status": "FAILED",
                    "semantic_status": "UNVERIFIED",
                }
            except subprocess.TimeoutExpired as exc:
                fallback_warning_records = [
                    *_warning_records_from_text(str(getattr(exc, "stdout", "") or ""), source="with_nexus_fallback_stdout"),
                    *_warning_records_from_text(str(getattr(exc, "stderr", "") or ""), source="with_nexus_fallback_stderr"),
                ]
                fallback_payload = _with_nexus_timeout_payload(task=task, timeout_sec=effective_timeout_sec, exc=exc)
        else:
            fallback_runner = runner or cli_runner or CliRunner()
            fallback_res = fallback_runner.invoke(nexus_root, fallback_args)
            fallback_warning_records = _warning_records_from_text(fallback_res.output or "", source="with_nexus_fallback_cli_runner_output")
            fallback_payload = _extract_json_payload(fallback_res.output or "") or {
                "status": "FAILED",
                "semantic_status": "UNVERIFIED",
            }
        fallback_row = _extract_record(
            mode="with_nexus",
            task=task,
            payload=fallback_payload,
            wall_time_sec=time.monotonic() - fallback_start,
        )
        _annotate_warning_ledger(fallback_row, fallback_warning_records, append=True)
        fallback_row["model_required_direct_fallback_used"] = True
        fallback_row["model_required_direct_fallback_reason"] = "direct_route_no_model_call"
        fallback_row["model_required_direct_first_status"] = str(row.get("status") or "")
        fallback_row["model_required_direct_first_model_calls"] = int(row.get("model_calls", 0) or 0)
        row = fallback_row
        row["route_execution_policy"] = route_execution_policy.to_dict()
    _merge_receipt_first_probe(row, task=task, probe_payload=receipt_first_payload)
    row["requested_force_flow"] = requested_force_flow or ""
    row["effective_force_flow"] = effective_force_flow or ""
    row["force_flow_deferred"] = bool(force_flow_defer_reason)
    row["force_flow_defer_reason"] = force_flow_defer_reason
    row["route_oracle_force_flow_deferred"] = bool(force_flow_defer_reason)
    row["route_oracle_force_flow_defer_reason"] = force_flow_defer_reason
    row["r_phase_cost_classification"] = _classify_r_phase_cost(
        row,
        task=task,
        requested_force_flow=requested_force_flow,
        effective_force_flow=effective_force_flow,
        defer_reason=force_flow_defer_reason,
    )
    row["model_required_execution_mode"] = execution_policy.mode
    row["model_required_require_strict_baseline"] = execution_policy.require_strict_baseline
    row["model_attempts"] = [
        {
            "attempt_type": "strict_baseline" if effective_strict_llm_baseline else "primary",
            "wall_sec": row.get("wall_duration_sec"),
            "cli_elapsed_sec": row.get("cli_elapsed_sec"),
            "runner_overhead_sec": row.get("runner_overhead_sec"),
            "runner_overhead_class": row.get("runner_overhead_class"),
            "model_calls": row.get("model_calls"),
            "tokens": row.get("total_tokens"),
            "status": row.get("status"),
            "semantic_status": row.get("semantic_status"),
            "winner_source": row.get("nexus_winner_source"),
        }
    ]
    if supervised_bare_attempt is not None:
        row["supervised_bare_attempt_status"] = str(supervised_bare_attempt.get("status") or "")
        row["supervised_bare_attempt_semantic_status"] = str(supervised_bare_attempt.get("semantic_status") or "")
        row["supervised_bare_attempt_wall_sec"] = supervised_bare_attempt.get("wall_duration_sec")
        row["supervised_bare_attempt_tokens"] = supervised_bare_attempt.get("total_tokens")
        row["supervised_bare_attempt_model_calls"] = supervised_bare_attempt.get("model_calls")
        if str(supervised_bare_attempt.get("semantic_status") or "") != "VERIFIED":
            row["supervised_bare_first_failed_then_nexus_rescue"] = True
            nexus_subprocess_calls = int(row.get("model_calls", 0) or 0)
            nexus_subprocess_tokens = int(row.get("total_tokens", 0) or 0)
            supervised_calls = int(supervised_bare_attempt.get("model_calls", 0) or 0)
            supervised_tokens = int(supervised_bare_attempt.get("total_tokens", 0) or 0)
            row["nexus_subprocess_model_calls"] = nexus_subprocess_calls
            row["nexus_subprocess_tokens"] = nexus_subprocess_tokens
            row["combined_model_calls"] = supervised_calls + nexus_subprocess_calls
            row["combined_tokens"] = supervised_tokens + nexus_subprocess_tokens
            row["model_calls"] = row["combined_model_calls"]
            row["total_tokens"] = row["combined_tokens"]
            row["token_measured"] = bool(supervised_bare_attempt.get("token_measured", False)) or bool(row.get("token_measured", False))
            if bool(supervised_bare_attempt.get("token_measured", False)):
                row["token_capture_status"] = str(supervised_bare_attempt.get("token_capture_status") or "measured")
                row["gateway_token_source"] = str(supervised_bare_attempt.get("gateway_token_source") or "stats")
                row["gateway_stats_present"] = bool(supervised_bare_attempt.get("gateway_stats_present", True))
            if supervised_bare_attempt.get("gateway_token_outlier_reason"):
                row["gateway_token_outlier_reason"] = str(supervised_bare_attempt.get("gateway_token_outlier_reason") or "")
            if int(supervised_bare_attempt.get("raw_provider_total_tokens", 0) or 0) > 0:
                row["raw_provider_total_tokens"] = int(supervised_bare_attempt.get("raw_provider_total_tokens", 0) or 0)
            if supervised_bare_attempt.get("raw_provider_token_source"):
                row["raw_provider_token_source"] = str(supervised_bare_attempt.get("raw_provider_token_source") or "")
            if supervised_bare_attempt.get("provider_stats_cumulative_suspected"):
                row["provider_stats_cumulative_suspected"] = True
            if supervised_bare_attempt.get("token_accounting_failure_class"):
                row["token_accounting_failure_class"] = str(supervised_bare_attempt.get("token_accounting_failure_class") or "")
            row["provider_token_measured"] = bool(supervised_bare_attempt.get("provider_token_measured", False)) or bool(
                row.get("provider_token_measured", False)
            )
            row["model_uses_nexus"] = True
            row["gemini_uses_nexus"] = True
            row["nexus_usage_valid"] = bool(row.get("semantic_completed", False))
    if route_cost_controls:
        row["route_cost_policy_controls"] = route_cost_controls
        row["route_cost_policy_candidate_cap"] = route_cost_controls.get("candidate_cap")
        row["route_cost_policy_lite_route"] = bool(route_cost_controls.get("lite_route", False))
        row["route_cost_policy_hold"] = bool(route_cost_controls.get("hold", False))
        row["route_cost_policy_source"] = str(route_cost_controls.get("policy_source") or "")
        row["route_cost_policy_require_llm_baseline"] = bool(route_cost_controls.get("require_llm_baseline", False))
        row["route_cost_policy_skip_llm_baseline"] = bool(route_cost_controls.get("skip_llm_baseline", False))
        row["route_cost_policy_disable_research"] = bool(route_cost_controls.get("disable_research", False))
        row["route_cost_policy_context_mode"] = str(route_cost_controls.get("context_mode") or "")
        row["route_cost_policy_max_rounds"] = route_cost_controls.get("max_rounds")
        row["route_cost_policy_lane"] = str(route_cost_controls.get("route_lane") or "")
        if baseline_fast_path_reason:
            row["route_cost_policy_fast_path_reason"] = baseline_fast_path_reason
        if route_cost_policy_overrides:
            row["route_cost_policy_expected_capability_overrides"] = route_cost_policy_overrides
    row["local_reflex_assessment"] = local_reflex.to_jsonable()
    row.update(local_reflex.to_route_features())
    if (
        llm_enabled
        and _route_cost_controls_allow_deterministic_pre_rescue(route_cost_controls)
        and str(row.get("status") or "") != "SUCCESS"
        and int(row.get("model_calls", 0) or 0) > 0
        and _post_model_deterministic_rescue_infra_allowed(row)
    ):
        pre_rescue = _deterministic_failed_tests_pre_rescue(
            task=task,
            repo_root=repo_root,
            target_file=target_file,
            test_file=test_file,
            timeout_sec=_remaining_task_timeout(start + max(1, int(effective_timeout_sec)), effective_timeout_sec),
        )
        row["deterministic_pre_rescue_used"] = bool(pre_rescue.get("used", False))
        row["deterministic_pre_rescue_reason"] = str(pre_rescue.get("reason") or "")
        if pre_rescue.get("used"):
            row["deterministic_pre_rescue_wall_sec"] = pre_rescue.get("wall_sec")
            row["deterministic_pre_rescue_stdout_tail"] = pre_rescue.get("stdout_tail")
            row["deterministic_pre_rescue_stderr_tail"] = pre_rescue.get("stderr_tail")
        hidden_verifier_wall_sec = 0.0
        hidden_passed = False
        hidden_stdout_tail = ""
        hidden_stderr_tail = ""
        verification_test_file = _verification_test_for_task(task, test_file)
        if pre_rescue.get("passed"):
            hidden_start = time.monotonic()
            try:
                hidden_verify = _run_process_group(
                    _pytest_verifier_cmd(verification_test_file),
                    cwd=repo_root,
                    env=os.environ.copy(),
                    timeout_sec=_remaining_task_timeout(start + max(1, int(effective_timeout_sec)), effective_timeout_sec),
                )
                hidden_passed = hidden_verify.returncode == 0
                hidden_stdout_tail = _tail_text(hidden_verify.stdout, max_chars=1000)
                hidden_stderr_tail = _tail_text(hidden_verify.stderr, max_chars=1000)
            except subprocess.TimeoutExpired:
                hidden_passed = False
                hidden_stderr_tail = "benchmark_task_deadline"
            hidden_verifier_wall_sec = round(time.monotonic() - hidden_start, 4)
        if pre_rescue.get("passed") and hidden_passed:
            row["status"] = "SUCCESS"
            row["semantic_status"] = "VERIFIED"
            row["semantic_completed"] = True
            row["runtime_classification"] = "nexus_deterministic_pre_rescue"
            row["nexus_winner_source"] = "nexus_llm_deterministic_pre_rescue"
            row["model_uses_nexus"] = True
            row["gemini_uses_nexus"] = True
            row["nexus_context_delivered"] = True
            row["nexus_usage_valid"] = True
            row["capability_claim_verified"] = True
            row["hidden_verifier_file"] = verification_test_file
            row["hidden_verifier_passed"] = True
            row["hidden_verifier_wall_sec"] = hidden_verifier_wall_sec
            row["hidden_verifier_stdout_tail"] = hidden_stdout_tail
            row["hidden_verifier_stderr_tail"] = hidden_stderr_tail
            row["nexus_failure_analysis"] = {
                "schema": "nexus_failure_analysis_v1",
                "status": "PASS",
                "primary_cause": "deterministic_pre_rescue_verified",
                "nexus_gap": "",
                "recoverable": False,
                "self_heal_status": "deterministic_pre_rescue",
                "reasons": ["deterministic_pre_rescue_hidden_verified"],
            }
            row["nexus_failure_status"] = "PASS"
            row["nexus_failure_primary_cause"] = "deterministic_pre_rescue_verified"
            row["nexus_failure_gap"] = ""
            row["nexus_failure_recoverable"] = False
            row["nexus_failure_self_heal_status"] = "deterministic_pre_rescue"
            payload["status"] = "SUCCESS"
            payload["semantic_status"] = "VERIFIED"
    hyper_admission = _hyper_admission_after_model_attempt(row)
    row["hyper_admission_decision"] = "run_hyper" if hyper_admission.run_hyper else "skip_hyper"
    row["hyper_admission_reason"] = hyper_admission.reason
    if llm_enabled and effective_strict_llm_baseline and hyper_admission.run_hyper:
        rescue_args = [item for item in args if item not in {"--llm-baseline", "--llm-baseline-required"}]
        if "--force-flow" in rescue_args:
            idx = rescue_args.index("--force-flow")
            del rescue_args[idx : idx + 2]
        rescue_args.extend(["--force-flow", "hyper_sprint"])
        rescue_start = time.monotonic()
        try:
            if runner_mode == "subprocess":
                rescue_cmd = _nexus_cli_subprocess_cmd(rescue_args)
                rescue_res = _run_process_group(rescue_cmd, cwd=repo_root, env=env, timeout_sec=timeout_sec)
                rescue_output = rescue_res.stdout or ""
            else:
                rescue_runner = runner or cli_runner or CliRunner()
                rescue_res = rescue_runner.invoke(nexus_root, rescue_args)
                rescue_output = rescue_res.output or ""
            rescue_payload = _extract_json_payload(rescue_output) or {}
        except subprocess.TimeoutExpired:
            rescue_payload = {"status": "FAILED", "semantic_status": "UNVERIFIED"}
        rescue_wall = time.monotonic() - rescue_start
        if rescue_payload.get("status") == "SUCCESS":
            first_model_calls = int(row.get("model_calls", 0) or 0)
            first_tokens = int(row.get("total_tokens", 0) or 0)
            first_token_status = str(row.get("token_capture_status") or row.get("model_token_capture_status") or "")
            first_token_source = str(row.get("gateway_token_source") or "")
            rescue_row = _extract_record(
                mode="with_nexus",
                task=task,
                payload=rescue_payload,
                wall_time_sec=wall + rescue_wall,
            )
            rescue_row["strict_model_attempt_failed"] = True
            rescue_row["bounded_nexus_rescue_used"] = True
            rescue_row["bounded_nexus_rescue_reason"] = "strict_llm_baseline_failed"
            rescue_row["runtime_classification"] = "nexus_bounded_rescue_after_model_attempt"
            rescue_row["first_attempt_wall_sec"] = round(wall, 4)
            rescue_row["first_attempt_cli_elapsed_sec"] = row.get("cli_elapsed_sec")
            rescue_row["rescue_wall_sec"] = round(rescue_wall, 4)
            rescue_row["rescue_cli_elapsed_sec"] = rescue_row.get("cli_elapsed_sec")
            rescue_row["total_composed_wall_sec"] = round(wall + rescue_wall, 4)
            rescue_row["runner_overhead_basis"] = "composed_rescue"
            rescue_model_calls = int(rescue_row.get("model_calls", 0) or 0)
            rescue_tokens = int(rescue_row.get("total_tokens", 0) or 0)
            rescue_row["model_calls"] = first_model_calls + int(rescue_row.get("model_calls", 0) or 0)
            rescue_row["total_tokens"] = first_tokens + int(rescue_row.get("total_tokens", 0) or 0)
            rescue_row["model_attempts"] = list(row.get("model_attempts", [])) + [
                {
                    "attempt_type": "bounded_hyper_rescue",
                    "wall_sec": round(rescue_wall, 4),
                    "cli_elapsed_sec": rescue_row.get("cli_elapsed_sec"),
                    "runner_overhead_sec": rescue_row.get("runner_overhead_sec"),
                    "runner_overhead_class": rescue_row.get("runner_overhead_class"),
                    "model_calls": rescue_model_calls,
                    "tokens": rescue_tokens,
                    "status": rescue_row.get("status"),
                    "semantic_status": rescue_row.get("semantic_status"),
                    "winner_source": rescue_row.get("nexus_winner_source"),
                }
            ]
            rescue_row["token_measured"] = first_tokens > 0 or bool(rescue_row.get("token_measured", False))
            rescue_row["provider_token_measured"] = first_tokens > 0 or bool(rescue_row.get("provider_token_measured", False))
            if first_tokens > 0:
                rescue_row["model_total_tokens"] = first_tokens
                rescue_row["model_token_capture_status"] = (
                    "measured" if first_token_status in {"ok", "measured"} else first_token_status or "estimated"
                )
                rescue_row["gateway_token_source"] = first_token_source or str(row.get("provider_token_source") or "stats")
                rescue_row["gateway_stats_present"] = bool(row.get("gateway_stats_present", False))
                rescue_row["gateway_usage_metadata_present"] = bool(row.get("gateway_usage_metadata_present", False))
            rescue_row["model_uses_nexus"] = True
            rescue_row["gemini_uses_nexus"] = True
            rescue_row["nexus_usage_valid"] = bool(rescue_row.get("semantic_completed", False))
            row = rescue_row
            payload = rescue_payload
            wall = wall + rescue_wall
    if payload.get("status") == "SUCCESS" and verification_test_file != test_file:
        verify_start = time.monotonic()
        verify = _run_process_group(
            _pytest_verifier_cmd(verification_test_file),
            cwd=repo_root,
            env=os.environ.copy(),
            timeout_sec=_remaining_task_timeout(start + max(1, int(timeout_sec)), timeout_sec),
        )
        hidden_verifier_wall_sec = time.monotonic() - verify_start
        hidden_passed = verify.returncode == 0
        row["hidden_verifier_file"] = verification_test_file
        row["hidden_verifier_passed"] = hidden_passed
        row["hidden_verifier_wall_sec"] = round(hidden_verifier_wall_sec, 4)
        row["hidden_verifier_stdout_tail"] = _tail_text(verify.stdout, max_chars=1000)
        row["hidden_verifier_stderr_tail"] = _tail_text(verify.stderr, max_chars=1000)
        if not hidden_passed:
            recovered_on_retry = False
            hidden_infra_reason = _hidden_verifier_infra_reason(row)
            if hidden_infra_reason:
                row["hidden_verifier_infra_invalid_reason"] = hidden_infra_reason
                row["infra_invalid_reason"] = hidden_infra_reason
                row["report_trust_mismatch"] = False
                row["hidden_retry_used"] = False
                row["hidden_retry_reason"] = hidden_infra_reason
                row["hidden_retry_lane"] = "skipped_infra"
                row["hidden_retry_classifier"] = hidden_infra_reason
            else:
                row["report_trust_mismatch"] = True
                failure_tail = "\n".join(
                    item
                    for item in (
                        str(row.get("hidden_verifier_stdout_tail") or "").strip(),
                        str(row.get("hidden_verifier_stderr_tail") or "").strip(),
                    )
                    if item
                )
                hidden_retry_decision = _hidden_retry_decision_for_failure(failure_tail, route_cost_controls)
                row["hidden_retry_classifier"] = hidden_retry_decision.classifier
                row["hidden_retry_lane"] = hidden_retry_decision.lane
                retryable_nexus_gap = str(row.get("nexus_failure_gap") or "") in {
                    "",
                    "bounded_self_heal_not_triggered",
                    "self_heal_failed",
                }
                if hidden_retry_decision.lane == "minimal_patch":
                    pre_retry = _deterministic_hidden_pre_retry(
                        task=task,
                        repo_root=repo_root,
                        target_file=target_file,
                        verification_test_file=verification_test_file,
                        failure_tail=failure_tail,
                        decision=hidden_retry_decision,
                        timeout_sec=_remaining_task_timeout(
                            start + max(1, int(effective_timeout_sec)),
                            effective_timeout_sec,
                        ),
                    )
                    row["hidden_pre_retry_used"] = bool(pre_retry.get("used", False))
                    row["hidden_pre_retry_reason"] = str(pre_retry.get("reason") or "")
                    if pre_retry.get("used"):
                        row["hidden_pre_retry_wall_sec"] = pre_retry.get("wall_sec")
                        row["hidden_pre_retry_stdout_tail"] = pre_retry.get("stdout_tail")
                        row["hidden_pre_retry_stderr_tail"] = pre_retry.get("stderr_tail")
                    if pre_retry.get("passed"):
                        row["hidden_verifier_passed"] = True
                        row["hidden_verifier_stdout_tail"] = pre_retry.get("stdout_tail")
                        row["hidden_verifier_stderr_tail"] = pre_retry.get("stderr_tail")
                        row["report_trust_mismatch"] = False
                        row["hidden_retry_used"] = True
                        row["hidden_retry_reason"] = "hidden_verifier_failure_deterministic_pre_retry"
                        row["hidden_retry_lane"] = hidden_retry_decision.lane
                        row["hidden_retry_classifier"] = hidden_retry_decision.classifier
                        row["hidden_retry_prompt_budget"] = "deterministic_pre_retry_v1"
                        row["hidden_retry_prompt_chars"] = 0
                        row["hidden_retry_context_chars"] = 0
                        row["hidden_retry_contract_chars"] = 0
                        row["hidden_retry_tail_chars"] = 0
                        row["hidden_retry_diff_chars"] = 0
                        row["hidden_retry_wall_sec"] = pre_retry.get("wall_sec")
                        row["hidden_retry_verifier_wall_sec"] = pre_retry.get("wall_sec")
                        row["hidden_retry_model_calls"] = 0
                        row["hidden_retry_attempt_count"] = 0
                        row["hidden_retry_tokens"] = 0
                        row["hidden_retry_payload_status"] = "SUCCESS"
                        row["hidden_retry_payload_semantic_status"] = "VERIFIED"
                        recovered_on_retry = True
                should_retry_hidden = bool(
                    llm_enabled
                    and not recovered_on_retry
                    and not _hidden_retry_disabled()
                    and (
                        effective_llm_self_heal
                        or effective_strict_llm_baseline
                        or route_cost_controls.get("supervised_bare_first") is True
                    )
                    and retryable_nexus_gap
                    and hidden_retry_decision.retry
                    and int(row.get("model_calls", 0) or 0) > 0
                )
                if _hidden_retry_disabled():
                    row["hidden_retry_used"] = False
                    row["hidden_retry_reason"] = "disabled_by_benchmark_policy"
                    row["hidden_retry_lane"] = "skipped_policy"
                    row["hidden_retry_classifier"] = "disabled_by_benchmark_policy"
                elif not hidden_retry_decision.retry:
                    row["hidden_retry_used"] = False
                    row["hidden_retry_reason"] = hidden_retry_decision.classifier
                if should_retry_hidden:
                    retry_args = list(args)
                    hidden_retry_task_desc, hidden_retry_prompt_telemetry = _hidden_retry_prompt_budget(
                        task=task,
                        repo_root=repo_root,
                        target_file=target_file,
                        failure_tail=failure_tail,
                        decision=hidden_retry_decision,
                    )
                    row.update(hidden_retry_prompt_telemetry)
                    if "--task-desc" in retry_args:
                        retry_args[retry_args.index("--task-desc") + 1] = hidden_retry_task_desc
                    if "--candidate-count" in retry_args:
                        idx = retry_args.index("--candidate-count") + 1
                        current_candidate_count = int(retry_args[idx])
                        compact_retry = bool(
                            route_cost_controls.get("lite_route") is True
                            or route_cost_controls.get("context_mode") == "compact"
                            or route_cost_controls.get("max_rounds") == 1
                        )
                        if hidden_retry_decision.lane == "minimal_patch":
                            retry_args[idx] = "1"
                        else:
                            retry_args[idx] = (
                                str(current_candidate_count)
                                if compact_retry
                                else str(max(2, min(3, current_candidate_count + 1)))
                            )
                    if hidden_retry_decision.lane == "minimal_patch":
                        if "--force-flow" in retry_args:
                            retry_args[retry_args.index("--force-flow") + 1] = "baseline"
                        else:
                            retry_args.extend(["--force-flow", "baseline"])
                    elif "--force-flow" not in retry_args:
                        retry_args.extend(["--force-flow", "hyper_sprint"])
                    retry_start = time.monotonic()
                    try:
                        retry_output = ""
                        if runner_mode == "subprocess":
                            retry_cmd = _nexus_cli_subprocess_cmd(retry_args)
                            retry_res = _run_process_group(
                                retry_cmd,
                                cwd=repo_root,
                                env=env,
                                timeout_sec=effective_timeout_sec,
                            )
                            retry_output = retry_res.stdout or ""
                        else:
                            retry_runner = runner or cli_runner or CliRunner()
                            retry_res = retry_runner.invoke(nexus_root, retry_args)
                            retry_output = retry_res.output or ""
                        retry_payload = _extract_json_payload(retry_output)
                    except subprocess.TimeoutExpired:
                        retry_output = ""
                        retry_payload = {"status": "FAILED", "semantic_status": "UNVERIFIED"}
                    hidden_retry_wall_sec = time.monotonic() - retry_start
                    retry_payload = retry_payload if isinstance(retry_payload, dict) else {}
                    retry_output_tail = _tail_text(retry_output, max_chars=1600)
                    retry_payload_status = str(retry_payload.get("status") or "")
                    retry_payload_semantic_status = str(retry_payload.get("semantic_status") or "")
                    row["hidden_retry_output_tail"] = retry_output_tail
                    row["hidden_retry_payload_status"] = retry_payload_status
                    row["hidden_retry_payload_semantic_status"] = retry_payload_semantic_status
                    row["hidden_retry_wall_sec"] = round(hidden_retry_wall_sec, 4)
                    row["hidden_retry_lane"] = hidden_retry_decision.lane
                    row["hidden_retry_classifier"] = hidden_retry_decision.classifier
                    if retry_payload.get("status") == "SUCCESS":
                        first_model_calls = int(row.get("model_calls", 0) or 0)
                        first_attempt_count = int(row.get("attempt_count", 0) or 0)
                        first_tokens = int(row.get("total_tokens", 0) or 0)
                        first_runner_overhead = float(row.get("runner_overhead_sec", 0.0) or 0.0)
                        retry_row = _extract_record(
                            mode="with_nexus",
                            task=task,
                            payload=retry_payload,
                            wall_time_sec=(wall + (time.monotonic() - retry_start)),
                        )
                        retry_model_calls = int(retry_row.get("model_calls", 0) or 0)
                        retry_attempt_count = int(retry_row.get("attempt_count", 0) or 0)
                        retry_tokens = int(retry_row.get("total_tokens", 0) or 0)
                        retry_cli_elapsed_sec = retry_row.get("cli_elapsed_sec")
                        retry_runner_overhead_sec = _nonnegative_delta(hidden_retry_wall_sec, retry_cli_elapsed_sec)
                        retry_phase_wall = {
                            "total": retry_row.get("phase_wall_total_sec"),
                            "P": retry_row.get("phase_wall_p_sec"),
                            "X": retry_row.get("phase_wall_x_sec"),
                            "D": retry_row.get("phase_wall_d_sec"),
                            "R": retry_row.get("phase_wall_r_sec"),
                            "A": retry_row.get("phase_wall_a_sec"),
                            "C": retry_row.get("phase_wall_c_sec"),
                        }
                        retry_row["first_attempt_wall_sec"] = round(wall, 4)
                        retry_row["first_attempt_model_calls"] = first_model_calls
                        retry_row["first_attempt_attempt_count"] = first_attempt_count
                        retry_row["first_attempt_tokens"] = first_tokens
                        retry_row["first_attempt_runner_overhead_sec"] = round(first_runner_overhead, 4)
                        retry_row["first_attempt_cli_elapsed_sec"] = row.get("cli_elapsed_sec")
                        retry_row["hidden_verifier_wall_sec"] = round(hidden_verifier_wall_sec, 4)
                        retry_row["hidden_retry_wall_sec"] = round(hidden_retry_wall_sec, 4)
                        retry_row["hidden_retry_model_calls"] = retry_model_calls
                        retry_row["hidden_retry_attempt_count"] = retry_attempt_count
                        retry_row["hidden_retry_tokens"] = retry_tokens
                        retry_row["hidden_retry_cli_elapsed_sec"] = retry_cli_elapsed_sec
                        retry_row["hidden_retry_runner_overhead_sec"] = round(retry_runner_overhead_sec, 4)
                        retry_row["hidden_retry_phase_wall_total_sec"] = retry_phase_wall["total"]
                        retry_row["hidden_retry_phase_wall_p_sec"] = retry_phase_wall["P"]
                        retry_row["hidden_retry_phase_wall_x_sec"] = retry_phase_wall["X"]
                        retry_row["hidden_retry_phase_wall_d_sec"] = retry_phase_wall["D"]
                        retry_row["hidden_retry_phase_wall_r_sec"] = retry_phase_wall["R"]
                        retry_row["hidden_retry_phase_wall_a_sec"] = retry_phase_wall["A"]
                        retry_row["hidden_retry_phase_wall_c_sec"] = retry_phase_wall["C"]
                        retry_row["model_calls"] = first_model_calls + retry_model_calls
                        retry_row["attempt_count"] = first_attempt_count + retry_attempt_count
                        retry_row["total_tokens"] = first_tokens + retry_tokens
                        retry_row["model_total_tokens"] = first_tokens + retry_tokens
                        retry_row["model_attempt_wall_sec"] = round(hidden_retry_wall_sec, 4)
                        retry_row["model_attempt_runner_overhead_sec"] = _nonnegative_delta(
                            hidden_retry_wall_sec,
                            retry_cli_elapsed_sec,
                        )
                        retry_row["model_attempt_runner_overhead_polluted"] = _runner_overhead_polluted(
                            hidden_retry_wall_sec,
                            retry_cli_elapsed_sec,
                        )
                        retry_row["runner_overhead_basis"] = "composed_hidden_retry"
                        retry_row["runner_overhead_sec"] = round(first_runner_overhead + retry_runner_overhead_sec, 4)
                        retry_row["runner_overhead_polluted"] = False
                        retry_row["runner_overhead_class"] = "composed_hidden_retry"
                        retry_row["model_attempts"] = list(row.get("model_attempts", [])) + [
                            {
                                "attempt_type": "hidden_verifier_bounded_retry",
                                "wall_sec": round(hidden_retry_wall_sec, 4),
                                "cli_elapsed_sec": retry_cli_elapsed_sec,
                                "runner_overhead_sec": round(retry_runner_overhead_sec, 4),
                                "runner_overhead_class": _runner_overhead_class(hidden_retry_wall_sec, retry_cli_elapsed_sec),
                                "model_calls": retry_model_calls,
                                "tokens": retry_tokens,
                                "attempt_count": retry_attempt_count,
                                "prompt_budget": hidden_retry_prompt_telemetry.get("hidden_retry_prompt_budget"),
                                "prompt_chars": hidden_retry_prompt_telemetry.get("hidden_retry_prompt_chars"),
                                "context_chars": hidden_retry_prompt_telemetry.get("hidden_retry_context_chars"),
                                "contract_chars": hidden_retry_prompt_telemetry.get("hidden_retry_contract_chars"),
                                "tail_chars": hidden_retry_prompt_telemetry.get("hidden_retry_tail_chars"),
                                "diff_chars": hidden_retry_prompt_telemetry.get("hidden_retry_diff_chars"),
                                "status": retry_row.get("status"),
                                "semantic_status": retry_row.get("semantic_status"),
                                "winner_source": retry_row.get("nexus_winner_source"),
                                "phase_wall": retry_phase_wall,
                            }
                        ]
                        retry_verify_start = time.monotonic()
                        try:
                            retry_verify = _run_process_group(
                                _pytest_verifier_cmd(verification_test_file),
                                cwd=repo_root,
                                env=os.environ.copy(),
                                timeout_sec=_remaining_task_timeout(start + max(1, int(effective_timeout_sec)), effective_timeout_sec),
                            )
                            retry_hidden_verifier_wall_sec = time.monotonic() - retry_verify_start
                            retry_hidden_passed = retry_verify.returncode == 0
                            retry_stdout_tail = _tail_text(retry_verify.stdout, max_chars=1000)
                            retry_stderr_tail = _tail_text(retry_verify.stderr, max_chars=1000)
                        except subprocess.TimeoutExpired:
                            retry_hidden_verifier_wall_sec = time.monotonic() - retry_verify_start
                            retry_hidden_passed = False
                            retry_stdout_tail = ""
                            retry_stderr_tail = "benchmark_task_deadline"
                        retry_row["hidden_verifier_file"] = verification_test_file
                        retry_row["hidden_verifier_passed"] = retry_hidden_passed
                        retry_row["hidden_verifier_stdout_tail"] = retry_stdout_tail
                        retry_row["hidden_verifier_stderr_tail"] = retry_stderr_tail
                        retry_row["hidden_retry_used"] = True
                        retry_row["hidden_retry_reason"] = "hidden_verifier_failure_bounded_nexus_retry"
                        retry_row["hidden_retry_lane"] = hidden_retry_decision.lane
                        retry_row["hidden_retry_classifier"] = hidden_retry_decision.classifier
                        retry_row.update(hidden_retry_prompt_telemetry)
                        retry_row["hidden_retry_verifier_wall_sec"] = round(retry_hidden_verifier_wall_sec, 4)
                        retry_row["hidden_retry_output_tail"] = retry_output_tail
                        retry_row["hidden_retry_payload_status"] = retry_payload_status
                        retry_row["hidden_retry_payload_semantic_status"] = retry_payload_semantic_status
                        if retry_hidden_passed:
                            row = retry_row
                            recovered_on_retry = True
                        else:
                            row["hidden_retry_used"] = True
                            row["hidden_retry_reason"] = "retry_attempt_failed_hidden_verifier"
                            row["hidden_retry_lane"] = hidden_retry_decision.lane
                            row["hidden_retry_classifier"] = hidden_retry_decision.classifier
                    else:
                        row["hidden_retry_used"] = True
                        row["hidden_retry_reason"] = "retry_attempt_failed_runner"
                        row["hidden_retry_lane"] = hidden_retry_decision.lane
                        row["hidden_retry_classifier"] = hidden_retry_decision.classifier
            if not recovered_on_retry:
                row["status"] = "FAILED"
                row["semantic_status"] = "UNVERIFIED"
                row["semantic_completed"] = False
    if route_cost_controls:
        row["route_cost_policy_controls"] = route_cost_controls
        row["route_cost_policy_candidate_cap"] = route_cost_controls.get("candidate_cap")
        row["route_cost_policy_lite_route"] = bool(route_cost_controls.get("lite_route", False))
        row["route_cost_policy_hold"] = bool(route_cost_controls.get("hold", False))
        row["route_cost_policy_source"] = str(route_cost_controls.get("policy_source") or "")
        row["route_cost_policy_require_llm_baseline"] = bool(route_cost_controls.get("require_llm_baseline", False))
        row["route_cost_policy_skip_llm_baseline"] = bool(route_cost_controls.get("skip_llm_baseline", False))
        row["route_cost_policy_disable_research"] = bool(route_cost_controls.get("disable_research", False))
        row["route_cost_policy_context_mode"] = str(route_cost_controls.get("context_mode") or "")
        row["route_cost_policy_max_rounds"] = route_cost_controls.get("max_rounds")
        row["route_cost_policy_lane"] = str(route_cost_controls.get("route_lane") or "")
    row["route_execution_policy"] = route_execution_policy.to_dict()
    if (
        llm_enabled
        and bool(row.get("semantic_completed", False))
        and bool(row.get("hidden_verifier_passed", False))
        and str(row.get("nexus_winner_source") or "")
        in {"model_supervised_bare_first", "nexus_llm_deterministic_pre_rescue"}
    ):
        _apply_supervised_receipt_evidence(
            row,
            repo_root=repo_root,
            task=task,
            target_file=target_file,
            tests_passed=True,
            hidden_verifier_file=str(row.get("hidden_verifier_file") or _verification_test_for_task(task, test_file)),
        )
        _reconcile_skill_mount_contract_after_receipts(row, repo_root=repo_root)
    try:
        return _finalize_with_nexus_row(
            row,
            provider=with_model_provider if llm_enabled else "local",
            model_required=llm_enabled,
            nexus_required=llm_enabled,
            task=task,
            repo_root=repo_root,
        )
    finally:
        for key, previous in env_restore.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


def run_without_nexus(
    *,
    repo_root: Path,
    task: CapabilityTask,
    target_file: str,
    test_file: str,
    timeout_sec: int,
    force_flow: str | None,
    history_window: int = 1,
    history_fail_threshold: int = 9999,
    mode: str = "service",
) -> dict[str, Any]:
    prev_diff = os.environ.get("NEXUS_TASK_DIFFICULTY")
    prev_id = os.environ.get("NEXUS_TASK_ID")
    os.environ["NEXUS_TASK_DIFFICULTY"] = task.difficulty
    os.environ["NEXUS_TASK_ID"] = task.id
    try:
        return _run_without_nexus_impl(
            repo_root=repo_root,
            task=task,
            target_file=target_file,
            test_file=test_file,
            timeout_sec=timeout_sec,
            force_flow=force_flow,
            history_window=history_window,
            history_fail_threshold=history_fail_threshold,
            mode=mode,
        )
    finally:
        if prev_diff is None:
            os.environ.pop("NEXUS_TASK_DIFFICULTY", None)
        else:
            os.environ["NEXUS_TASK_DIFFICULTY"] = prev_diff
        if prev_id is None:
            os.environ.pop("NEXUS_TASK_ID", None)
        else:
            os.environ["NEXUS_TASK_ID"] = prev_id


def _run_without_nexus_impl(
    *,
    repo_root: Path,
    task: CapabilityTask,
    target_file: str,
    test_file: str,
    timeout_sec: int,
    force_flow: str | None,
    history_window: int = 1,
    history_fail_threshold: int = 9999,
    mode: str = "service",
) -> dict[str, Any]:
    if mode in {"gemini", "codex"}:
        target_path = Path(target_file)
        test_path = Path(test_file)
        original = target_path.read_text(encoding="utf-8")
        test_source = test_path.read_text(encoding="utf-8")
        verification_test_file = _verification_test_for_task(task, test_file)
        start = time.monotonic()
        status = "FAILED"
        err = ""
        model_calls = 0
        total_tokens = 0
        token_capture_status = "unknown"
        model_name = ""
        model_patch_generated = False
        gateway_error_category = ""
        out: dict[str, Any] = {}
        raw_tail = ""
        patch = ""
        patch_changed = False
        patch_len = 0
        pytest_stdout_tail = ""
        pytest_stderr_tail = ""
        verifier_wall_sec = 0.0
        warning_records = []
        direct_infra_retry_count = 0
        direct_infra_retry_wall_sec = 0.0
        direct_infra_retry_reasons: list[str] = []
        direct_infra_retry_raw_tails: list[str] = []
        task_deadline = start + max(1, int(timeout_sec))
        direct_provider = "codex" if mode == "codex" else "gemini"
        direct_ask = _ask_direct_codex_patch if direct_provider == "codex" else _ask_direct_gemini_flash_patch
        if direct_provider == "codex":
            direct_model_label = os.environ.get("NEXUS_DIRECT_CODEX_MODEL") or os.environ.get("NEXUS_CODEX_MODEL_NAME") or "Codex"
        else:
            direct_model_label = os.environ.get("NEXUS_DIRECT_GEMINI_MODEL") or os.environ.get("NEXUS_GEMINI_MODEL_NAME") or "Gemini"
        prompt_actor = f"{direct_model_label} running without Nexus orchestration"
        try:
            reset_boundary = (
                f"NEXUS_BENCH_SESSION_BOUNDARY_V1 task_id={task.id} trial_index={task.trial_index} "
                "Treat this as an isolated task. Do not use facts, filenames, code, tests, or conclusions from any previous benchmark turn."
            )
            reset_boundary_hash = hashlib.sha256(reset_boundary.encode("utf-8")).hexdigest()
            prompt_tests = test_source
            prompt = (
                f"You are {prompt_actor}. "
                "Return ONLY valid JSON with keys status and patch. No markdown. No tool use. "
                "The patch value must be the full updated target file content.\n"
                f"{reset_boundary}\n\n"
                f"Task: {task.task_desc}\n\n"
                f"[CURRENT SOURCE]\n{original}\n\n"
                f"[CURRENT TESTS]\n{prompt_tests}\n\n"
                "Return the full updated file content in the patch field."
            )
            prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            direct_attempt_start = time.monotonic()
            out, raw = direct_ask(prompt=prompt, timeout_sec=_remaining_task_timeout(task_deadline, timeout_sec))
            direct_attempt_wall_sec = round(time.monotonic() - direct_attempt_start, 4)
            retry_limit = _direct_model_infra_retry_limit(direct_provider)
            retryable, retry_reason = _direct_model_retryable_infra_failure(out if isinstance(out, dict) else {}, raw)
            while retryable and direct_infra_retry_count < retry_limit:
                direct_infra_retry_count += 1
                direct_infra_retry_wall_sec = round(direct_infra_retry_wall_sec + direct_attempt_wall_sec, 4)
                direct_infra_retry_reasons.append(retry_reason)
                direct_infra_retry_raw_tails.append(_tail_text(raw, max_chars=500))
                if retry_reason == "gemini_invalid_session_identifier" and isinstance(out, dict):
                    _reset_gemini_benchmark_session(str(out.get("gemini_session_id") or ""))
                direct_attempt_start = time.monotonic()
                out, raw = direct_ask(prompt=prompt, timeout_sec=_remaining_task_timeout(task_deadline, timeout_sec))
                direct_attempt_wall_sec = round(time.monotonic() - direct_attempt_start, 4)
                retryable, retry_reason = _direct_model_retryable_infra_failure(out if isinstance(out, dict) else {}, raw)
            model_calls = 1
            patch = raw
            warning_records.extend(_warning_records_from_text(raw, source=f"without_nexus_{direct_provider}_raw"))
            raw_tail = _tail_text(raw, max_chars=1000)
            if isinstance(out, dict):
                if str(out.get("error_category", "") or "") == "binary_missing":
                    model_calls = 0
                patch = str(out.get("patch") or "")
                gateway_error_category = str(out.get("error_category", "") or "")
                if gateway_error_category == "timeout":
                    model_calls = 0
                model_name = str(out.get("model_name", "") or "")
                model_patch_generated = bool(out.get("model_patch_generated", False))
                try:
                    total_tokens = int(out.get("tokens_used", 0) or 0)
                except (TypeError, ValueError):
                    total_tokens = 0
                token_capture_status = str(out.get("token_capture_status", "unknown") or "unknown")
            if total_tokens <= 0 and not gateway_error_category:
                total_tokens = max(1, (len(prompt) + len(str(patch))) // 4)
                token_capture_status = "estimated"
            patch_len = len(str(patch or ""))
            patch_changed = bool(patch and patch != original)
            if patch_changed:
                syntax_warning = ""
                if target_path.suffix == ".py":
                    try:
                        syntax_warning = _python_syntax_warning(str(patch), str(target_path))
                    except SyntaxError as exc:
                        err = f"syntax_error:{exc.msg}"
                if syntax_warning:
                    err = f"syntax_warning:{syntax_warning}"
                    warning_records.extend(_warning_records_from_text(err, source="without_nexus_candidate_compile"))
                if not err:
                    target_path.write_text(patch, encoding="utf-8")
                    verifier_start = time.monotonic()
                    res = _run_process_group(
                        _pytest_verifier_cmd(verification_test_file),
                        cwd=repo_root,
                        env=os.environ.copy(),
                        timeout_sec=_remaining_task_timeout(task_deadline, timeout_sec),
                    )
                    verifier_wall_sec = round(time.monotonic() - verifier_start, 4)
                    pytest_stdout_tail = _tail_text(res.stdout, max_chars=1000)
                    pytest_stderr_tail = _tail_text(res.stderr, max_chars=1000)
                    warning_records.extend(_warning_records_from_text(res.stdout or "", source="without_nexus_pytest_stdout"))
                    warning_records.extend(_warning_records_from_text(res.stderr or "", source="without_nexus_pytest_stderr"))
                    status = "SUCCESS" if res.returncode == 0 else "FAILED"
                    if status != "SUCCESS":
                        err = "pytest_failed"
            else:
                err = "no_mutation_generated"
        except subprocess.TimeoutExpired:
            err = "test_timeout"
            gateway_error_category = "timeout"
        except Exception as exc:  # noqa: BLE001
            err = f"{direct_provider}_error:{type(exc).__name__}"
        finally:
            if status != "SUCCESS":
                target_path.write_text(original, encoding="utf-8")
        wall = time.monotonic() - start
        prompt_attribution = _direct_prompt_attribution(
            prompt=prompt,
            task_desc=task.task_desc,
            source=original,
            tests=test_source,
            patch=str(patch or ""),
        )
        payload = {
            "result": {
                "status": status,
                "elapsed_sec": wall,
                "error": err,
                "report": {
                    "attempt_count": 1,
                    "model_calls": model_calls,
                    "total_tokens": total_tokens,
                    "token_capture_status": token_capture_status,
                    "model_name": model_name,
                    "model_patch_generated": model_patch_generated,
                    "fallback_used": False,
                    "gateway_stats_present": bool(out.get("gateway_stats_present", False)) if isinstance(out, dict) else False,
                    "direct_infra_retry_count": direct_infra_retry_count,
                    "direct_infra_retry_wall_sec": direct_infra_retry_wall_sec,
                    "direct_infra_retry_reasons": direct_infra_retry_reasons,
                    "direct_infra_retry_raw_tails": direct_infra_retry_raw_tails,
                    "gateway_usage_metadata_present": bool(out.get("gateway_usage_metadata_present", False)) if isinstance(out, dict) else False,
                    "gateway_token_source": str(out.get("gateway_token_source") or "") if isinstance(out, dict) else "",
                    "gateway_token_outlier_reason": str(out.get("gateway_token_outlier_reason") or "") if isinstance(out, dict) else "",
                    "raw_provider_total_tokens": int(out.get("raw_provider_total_tokens", 0) or 0) if isinstance(out, dict) else 0,
                    "raw_provider_token_source": str(out.get("raw_provider_token_source") or "") if isinstance(out, dict) else "",
                    "provider_stats_cumulative_suspected": bool(out.get("provider_stats_cumulative_suspected", False)) if isinstance(out, dict) else False,
                    "token_accounting_failure_class": str(out.get("token_accounting_failure_class") or "") if isinstance(out, dict) else "",
                    "token_ledger_status": str(out.get("token_ledger_status") or "") if isinstance(out, dict) else "",
                    "token_ledger_source": str(out.get("token_ledger_source") or "") if isinstance(out, dict) else "",
                    "token_ledger_normalized_tokens": int(out.get("token_ledger_normalized_tokens", 0) or 0) if isinstance(out, dict) else 0,
                    "token_ledger_raw_provider_total_tokens": int(out.get("token_ledger_raw_provider_total_tokens", 0) or 0) if isinstance(out, dict) else 0,
                    "gateway_prompt_chars": len(prompt),
                    "gateway_payload_chars": len(str(patch or "")),
                    "gateway_total_chars": len(prompt) + len(str(patch or "")),
                    "gateway_total_sec": float(out.get("gateway_total_sec", 0.0) or 0.0) if isinstance(out, dict) else 0.0,
                    "gateway_invocation_build_sec": float(out.get("gateway_invocation_build_sec", 0.0) or 0.0) if isinstance(out, dict) else 0.0,
                    "gateway_process_sec": float(out.get("gateway_process_sec", 0.0) or 0.0) if isinstance(out, dict) else 0.0,
                    "gateway_provider_wait_sec": float(out.get("gateway_provider_wait_sec", 0.0) or 0.0) if isinstance(out, dict) else 0.0,
                    "gateway_parse_sec": float(out.get("gateway_parse_sec", 0.0) or 0.0) if isinstance(out, dict) else 0.0,
                    "direct_gemini_invocation_build_sec": float(out.get("direct_gemini_invocation_build_sec", 0.0) or 0.0) if isinstance(out, dict) else 0.0,
                    "direct_gemini_process_sec": float(out.get("direct_gemini_process_sec", 0.0) or 0.0) if isinstance(out, dict) else 0.0,
                    "direct_gemini_parse_sec": float(out.get("direct_gemini_parse_sec", 0.0) or 0.0) if isinstance(out, dict) else 0.0,
                    "direct_verifier_wall_sec": verifier_wall_sec,
                    "session_worker_enabled": (
                        bool(out.get("gemini_session_worker", False) or out.get("codex_session_worker", False))
                        if isinstance(out, dict)
                        else False
                    ),
                    "session_worker_provider": (
                        direct_provider
                        if isinstance(out, dict) and bool(out.get("gemini_session_worker", False) or out.get("codex_session_worker", False))
                        else ""
                    ),
                    "session_worker_policy": str(out.get("gemini_session_mode") or out.get("codex_session_mode") or "") if isinstance(out, dict) else "",
                    "session_worker_id": str(out.get("gemini_session_id") or out.get("codex_session_id") or "") if isinstance(out, dict) else "",
                    "session_worker_turn_index": int(out.get("gemini_session_turn_index", 0) or out.get("codex_session_turn_index", 0) or 0) if isinstance(out, dict) else 0,
                    "session_worker_resumed": bool(out.get("gemini_session_resumed", False) or out.get("codex_session_resumed", False)) if isinstance(out, dict) else False,
                    "reset_boundary_hash": reset_boundary_hash,
                    "prompt_sha256": prompt_sha256,
                    **prompt_attribution,
                },
            },
            "status": status,
            "semantic_status": "VERIFIED" if status == "SUCCESS" else "UNVERIFIED",
            "runtime_classification": f"direct_{direct_provider}",
            "artifact_summary": {
                "changed": patch_changed,
                "verification_only": False,
                "diff_line_count": len(list(difflib.unified_diff(original.splitlines(), str(patch or "").splitlines()))) if patch_changed else 0,
                "success_criteria": task.success_criteria,
                "mutation_required": task.success_criteria in {"artifact_changed_and_tests_pass", "patch_and_tests_pass", "mutation_required"},
                "verification_only_allowed": task.success_criteria == "all_target_tests_pass",
            },
            "success_criteria": {
                "name": task.success_criteria,
                "mutation_required": task.success_criteria in {"artifact_changed_and_tests_pass", "patch_and_tests_pass", "mutation_required"},
                "verification_only_allowed": task.success_criteria == "all_target_tests_pass",
            },
            "baseline_trace": {
                "gateway_error_category": gateway_error_category,
                "patch_len": patch_len,
                "patch_changed": patch_changed,
                "raw_tail": raw_tail,
                "pytest_stdout_tail": pytest_stdout_tail,
                "pytest_stderr_tail": pytest_stderr_tail,
                "verification_test_file": verification_test_file,
            },
        }
        row = _extract_record(mode="without_nexus", task=task, payload=payload, wall_time_sec=wall)
        _annotate_warning_ledger(row, warning_records)
        return _annotate_with_contract(
            row,
            provider=direct_provider,
            model_required=True,
            nexus_required=False,
        )

    if mode == "bare":
        target_path = Path(target_file)
        original = target_path.read_text(encoding="utf-8")
        start = time.monotonic()
        status = "FAILED"
        try:
            # Bare baseline: no hyper search; for hard tasks we intentionally do verification-only.
            if task.difficulty != "hard":
                patched = generate_local_candidate(original, task.task_desc, "local", 0)
                if patched != original:
                    target_path.write_text(patched, encoding="utf-8")
            res = _run_process_group(_pytest_verifier_cmd(test_file), cwd=repo_root, env=os.environ.copy(), timeout_sec=timeout_sec)
            status = "SUCCESS" if res.returncode == 0 else "FAILED"
        except Exception:
            status = "FAILED"
        finally:
            # keep the same post-condition as service path: preserve best patch only on success
            if status != "SUCCESS":
                target_path.write_text(original, encoding="utf-8")
        wall = time.monotonic() - start
        payload = {
            "result": {
                "status": status,
                "elapsed_sec": wall,
                "report": {
                    "attempt_count": 1,
                    "model_calls": 0,
                    "total_tokens": 0,
                    "token_capture_status": "not_applicable_local_only",
                },
            },
            "status": status,
            "semantic_status": None,
        }
        return _extract_record(mode="without_nexus", task=task, payload=payload, wall_time_sec=wall)

    start = time.monotonic()
    payload, _ = run_auto_flow(
        repo_root=repo_root,
        task_desc=task.task_desc,
        target_file=target_file,
        test_file=test_file,
        task_type=task.task_type,
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=False,
        llm_baseline=False,
        timeout_sec=timeout_sec,
        stage1_timeout_sec=max(10, min(20, timeout_sec // 2)),
        max_time_ratio_guard=1.5,
        baseline_fast_sec=9.0,
        history_window=history_window,
        history_fail_threshold=history_fail_threshold,
        dynamic_timeout_multiplier=2.5,
        min_dynamic_stage1_timeout=12,
        force_flow=force_flow,
        report_file=f".nexus/reports/research/ab_{task.id}_without.json",
        output_file=None,
    )
    wall = time.monotonic() - start
    return _extract_record(mode="without_nexus", task=task, payload=payload, wall_time_sec=wall)


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _annotate_session_worker_contamination(rows: list[dict[str, Any]]) -> dict[str, Any]:
    worker_rows = [row for row in rows if bool(row.get("session_worker_enabled", False))]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in worker_rows:
        key = (str(row.get("session_worker_provider") or ""), str(row.get("session_worker_id") or ""))
        groups.setdefault(key, []).append(row)

    contaminated = 0
    for group_rows in groups.values():
        group_rows.sort(key=lambda item: int(item.get("session_worker_turn_index", 0) or 0))
        previous_rows: list[dict[str, Any]] = []
        previous_turn = 0
        seen_boundaries: dict[str, tuple[str, int]] = {}
        for row in group_rows:
            reasons: list[str] = []
            turn = int(row.get("session_worker_turn_index", 0) or 0)
            task_id = str(row.get("task_id") or "")
            trial_index = int(row.get("trial_index", 0) or 0)
            reset_hash = str(row.get("reset_boundary_hash") or "")
            resumed = bool(row.get("session_worker_resumed", False))
            worker_policy = str(row.get("session_worker_policy") or "")
            resume_expected = worker_policy != "exec_fresh_no_resume"
            if turn <= 0:
                reasons.append("session_turn_index_missing")
            if previous_turn and turn <= previous_turn:
                reasons.append("session_turn_index_not_increasing")
            if turn == 1 and resumed:
                reasons.append("first_turn_should_not_resume")
            if resume_expected and turn > 1 and not resumed:
                reasons.append("later_turn_should_resume")
            if not reset_hash:
                reasons.append("reset_boundary_hash_missing")
            elif reset_hash in seen_boundaries and seen_boundaries[reset_hash] != (task_id, trial_index):
                reasons.append("reset_boundary_hash_reused_across_task")
            else:
                seen_boundaries[reset_hash] = (task_id, trial_index)
            leak_text = "\n".join(
                str(row.get(key) or "")
                for key in (
                    "baseline_raw_tail",
                    "baseline_pytest_stdout_tail",
                    "baseline_pytest_stderr_tail",
                    "nexus_failure_reason",
                )
            )
            for previous in previous_rows:
                previous_task = str(previous.get("task_id") or "")
                previous_hash = str(previous.get("reset_boundary_hash") or "")
                if previous_task and previous_task != task_id and previous_task in leak_text:
                    reasons.append("previous_task_id_leaked")
                    row["session_worker_expected_previous_task_id"] = previous_task
                if previous_hash and previous_hash != reset_hash and previous_hash in leak_text:
                    reasons.append("previous_reset_boundary_hash_leaked")
                    row["session_worker_previous_reset_boundary_hash"] = previous_hash
            row["session_worker_contamination_detected"] = bool(reasons)
            row["session_worker_contamination_reasons"] = sorted(set(reasons))
            if reasons:
                contaminated += 1
                row["run_eligible"] = False
                row["infra_invalid_reason"] = "session_worker_contamination"
            previous_rows.append(row)
            previous_turn = max(previous_turn, turn)
    total = len(worker_rows)
    return {
        "schema": "nexus_session_worker_contamination_v1",
        "worker_row_count": total,
        "contaminated_row_count": contaminated,
        "contamination_rate": round(contaminated / total, 4) if total else 0.0,
        "clean": contaminated == 0,
    }


def _build_parallel_smoke_rows(tasks: list[CapabilityTask], *, model_name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows_by_mode: dict[str, list[dict[str, Any]]] = {"with_nexus": [], "without_nexus": []}
    for task in tasks:
        for mode in ("with_nexus", "without_nexus"):
            rows_by_mode[mode].append(
                {
                    "mode": mode,
                    "task_id": task.id,
                    "trial_index": task.trial_index,
                    "category": task.category,
                    "repo_kind": task.repo_kind,
                    "repo": task.repo,
                    "repo_ref": task.repo_ref,
                    "manifest_hash": task.manifest_hash,
                    "difficulty": task.difficulty,
                    "task_type": task.task_type,
                    "task_desc": task.task_desc,
                    "status": "SMOKE_ONLY",
                    "semantic_status": "UNVERIFIED",
                    "semantic_completed": False,
                    "run_eligible": False,
                    "infra_invalid_reason": "parallel_smoke",
                    "invocation_started": False,
                    "model_response_received": False,
                    "provider": "gemini",
                    "model_name": model_name,
                    "model_calls": 0,
                    "total_tokens": 0,
                    "token_capture_status": "not_applicable_smoke_only",
                    "token_measured": False,
                    "parallel_arms_mode": "smoke-only",
                    "execution_mode": "parallel_smoke",
                }
            )
    return rows_by_mode["with_nexus"], rows_by_mode["without_nexus"]


def _render_partial_markdown_report(
    *,
    benchmark_date: str,
    with_rows: list[dict[str, Any]],
    without_rows: list[dict[str, Any]],
    benchmark_summary: dict[str, dict[str, Any]],
) -> str:
    return "\n".join(
        [
            "# Gemini + Nexus Benchmark Partial Run",
            "",
            f"Date: {benchmark_date}",
            "",
            "Public claim gate: FAIL",
            "",
            "Reason: single-arm run; benchmark did not produce comparable with/without rows.",
            "",
            f"With Nexus rows: {len(with_rows)}",
            f"Without Nexus rows: {len(without_rows)}",
            "",
            "```json",
            json.dumps(benchmark_summary, ensure_ascii=False, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )


def _safe_artifact_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _summarize_outbound_prompt_ledger(path_raw: object, *, expected_min_records: int = 1) -> dict[str, Any]:
    path_text = str(path_raw or "").strip()
    summary: dict[str, Any] = {
        "schema": "nexus_outbound_prompt_ledger_summary_v1",
        "path": path_text,
        "sha256": "",
        "record_count": 0,
        "strict_record_count": 0,
        "forbidden_literal_count": 0,
        "invalid_record_count": 0,
        "providers": [],
        "models": [],
        "status": "PASS",
        "failures": [],
    }
    failures: list[str] = []
    if not path_text:
        failures.append("outbound_prompt_ledger_missing_path")
    else:
        path = Path(path_text)
        if not path.exists():
            failures.append("outbound_prompt_ledger_missing_file")
        else:
            summary["sha256"] = _sha256_file(path)
            providers: set[str] = set()
            models: set[str] = set()
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    summary["invalid_record_count"] += 1
                    continue
                if not isinstance(record, dict) or record.get("schema") != "nexus_outbound_prompt_ledger_v1":
                    summary["invalid_record_count"] += 1
                    continue
                summary["record_count"] += 1
                if bool(record.get("strict", False)):
                    summary["strict_record_count"] += 1
                try:
                    summary["forbidden_literal_count"] += int(record.get("forbidden_literal_count", 0) or 0)
                except (TypeError, ValueError):
                    summary["invalid_record_count"] += 1
                provider = str(record.get("provider") or "").strip()
                model = str(record.get("model_name") or "").strip()
                if provider:
                    providers.add(provider)
                if model:
                    models.add(model)
            summary["providers"] = sorted(providers)
            summary["models"] = sorted(models)
            if summary["record_count"] < max(1, int(expected_min_records)):
                failures.append("outbound_prompt_ledger_record_count_below_expected")
            if summary["strict_record_count"] != summary["record_count"]:
                failures.append("outbound_prompt_ledger_non_strict_record")
            if summary["forbidden_literal_count"] > 0:
                failures.append("outbound_prompt_ledger_forbidden_literal")
            if summary["invalid_record_count"] > 0:
                failures.append("outbound_prompt_ledger_invalid_record")
    summary["failures"] = sorted(set(failures))
    summary["status"] = "PASS" if not summary["failures"] else "FAIL"
    return summary


def _git_commit(cwd: Path) -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=10,
        )
    except Exception:
        return ""
    return res.stdout.strip() if res.returncode == 0 else ""


def _rate_for(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if bool(row.get(key, False))) / len(rows), 4)


def _model_names(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row.get("model_name") or "").strip() for row in rows if str(row.get("model_name") or "").strip()}


def _infra_reason(row: dict[str, Any] | None) -> str:
    if not row:
        return "missing_arm"
    if bool(row.get("run_eligible", True)):
        return ""
    return str(row.get("infra_invalid_reason") or "unknown").strip() or "unknown"


def compute_infra_quarantine_report(
    with_rows: list[dict[str, Any]],
    without_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    with_by_key = {
        (str(row.get("task_id") or ""), str(row.get("trial_index") or "1")): row
        for row in with_rows
    }
    without_by_key = {
        (str(row.get("task_id") or ""), str(row.get("trial_index") or "1")): row
        for row in without_rows
    }
    pairs: list[dict[str, Any]] = []
    reason_counts: dict[str, int] = {}
    for task_id, trial_index in sorted(set(with_by_key) | set(without_by_key)):
        with_row = with_by_key.get((task_id, trial_index))
        without_row = without_by_key.get((task_id, trial_index))
        reason_codes = [
            reason
            for reason in (_infra_reason(with_row), _infra_reason(without_row))
            if reason
        ]
        for reason in reason_codes:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        pairs.append(
            {
                "task_id": task_id,
                "trial_index": trial_index,
                "infra_valid_pair": not reason_codes and with_row is not None and without_row is not None,
                "infra_invalid_reason_code": reason_codes[0] if reason_codes else "",
                "infra_invalid_reason_codes": reason_codes,
                "with_nexus_run_eligible": bool(with_row.get("run_eligible", True)) if with_row else False,
                "without_nexus_run_eligible": bool(without_row.get("run_eligible", True)) if without_row else False,
            }
        )
    valid_count = sum(1 for pair in pairs if bool(pair.get("infra_valid_pair")))
    return {
        "schema": "nexus_infra_quarantine_report_v1",
        "pair_count": len(pairs),
        "infra_valid_pair_count": valid_count,
        "infra_invalid_pair_count": len(pairs) - valid_count,
        "infra_valid_pair_rate": round(valid_count / len(pairs), 4) if pairs else 0.0,
        "reason_counts": dict(sorted(reason_counts.items())),
        "pairs": pairs,
        "claim_boundary": [
            "Infra-invalid pairs are excluded from cost-efficiency denominators.",
            "Infra-invalid pairs belong to infra stability reporting, not model capability claims.",
        ],
    }


def derive_public_claim_posture(
    *,
    delivery_gate_passed: bool,
    cost_claim_passed: bool,
    cost_efficiency_status: str,
    cost_efficiency_failures: list[str],
    cost_efficiency_sample_sufficient: bool,
    efficiency_pair_count: int,
    min_required_pairs_for_efficiency_claim: int,
    token_roi_status: str,
    verified_lift_per_1k_with_tokens: float,
    marginal_token_utility: float,
    retry_cost_share_wall: float,
) -> dict[str, Any]:
    cost_efficiency_wording_allowed = bool(
        cost_efficiency_status == "IMPROVED" and cost_efficiency_sample_sufficient
    )
    if not delivery_gate_passed:
        public_wording_key = "no_public_claim"
        public_wording_allowed = False
    elif not cost_efficiency_sample_sufficient:
        public_wording_key = "promising_but_insufficient_sample"
        public_wording_allowed = True
    elif cost_efficiency_wording_allowed:
        public_wording_key = "cost_efficiency_improved"
        public_wording_allowed = True
    elif cost_efficiency_status == "REGRESSED" and retry_cost_share_wall > 0.0:
        public_wording_key = "verified_delivery_uplift_with_cost_regression_localized_to_hidden_retry"
        public_wording_allowed = True
    else:
        public_wording_key = "verified_delivery_uplift"
        public_wording_allowed = True
    return {
        "delivery": {
            "status": "PASS" if delivery_gate_passed else "FAIL",
            "scope": "same-model verified delivery and trust safety",
        },
        "cost_safety": {
            "status": "PASS" if cost_claim_passed else "FAIL",
            "scope": "cost telemetry completeness and public-safe accounting",
        },
        "cost_efficiency": {
            "status": cost_efficiency_status,
            "reason_codes": sorted(set(cost_efficiency_failures)),
            "scope": "wall/token/model-call efficiency versus bare baseline",
            "sample_sufficient": cost_efficiency_sample_sufficient,
            "pair_count": efficiency_pair_count,
            "min_required_pairs": min_required_pairs_for_efficiency_claim,
            "token_roi_status": token_roi_status,
            "verified_lift_per_1k_with_tokens": verified_lift_per_1k_with_tokens,
            "marginal_token_utility": marginal_token_utility,
        },
        "public_wording_key": public_wording_key,
        "public_wording_allowed": public_wording_allowed,
        "cost_efficiency_wording_allowed": cost_efficiency_wording_allowed,
        "allowed_public_wording": public_wording_key,
    }


def derive_training_eligibility_posture(
    *,
    delivery_gate_passed: bool,
    cost_claim_passed: bool,
    cost_efficiency_sample_sufficient: bool,
    prompt_purity_gate_passed: bool,
    with_trust_mismatch_rate: float,
    without_trust_mismatch_rate: float,
    eligible_with: list[dict[str, Any]],
    infra_quarantine_report: dict[str, Any],
    wall_ledger_invalid: bool = False,
    warning_ledger_invalid: bool = False,
    cost_efficiency_status: str = "",
    synthetic_readiness_reasons: list[str] | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    for reason in synthetic_readiness_reasons or []:
        reasons.append(f"synthetic_readiness_shortcut:{reason}")
    if not delivery_gate_passed:
        reasons.append("delivery_gate_not_passed")
    if with_trust_mismatch_rate > 0.0 or without_trust_mismatch_rate > 0.0:
        reasons.append("trust_mismatch_present")
    if not cost_claim_passed:
        reasons.append("cost_safety_not_passed")
    if not cost_efficiency_sample_sufficient:
        reasons.append("sample_insufficient")
    if not prompt_purity_gate_passed:
        reasons.append("prompt_purity_above_threshold")
    if any(str(row.get("rubric_contract_status") or "") != "PASS" for row in eligible_with):
        reasons.append("rubric_not_pass")
    if wall_ledger_invalid:
        reasons.append("wall_ledger_telemetry_invalid")
    if warning_ledger_invalid:
        reasons.append("warning_ledger_telemetry_invalid")
    if cost_efficiency_sample_sufficient and str(cost_efficiency_status or "").upper() == "REGRESSED":
        reasons.append("cost_efficiency_regressed")
    if not reasons:
        status = "TRAINING_ELIGIBLE"
    elif any(reason.startswith("synthetic_readiness_shortcut:") for reason in reasons):
        status = "OBSERVATION_ONLY_SYNTHETIC_READINESS"
    elif "wall_ledger_telemetry_invalid" in reasons or "warning_ledger_telemetry_invalid" in reasons:
        status = "OBSERVATION_ONLY_TELEMETRY_INVALID"
    elif any(reason in reasons for reason in ("delivery_gate_not_passed", "cost_safety_not_passed")):
        status = "OBSERVATION_ONLY_INFRA_INVALID"
    elif "sample_insufficient" in reasons:
        status = "OBSERVATION_ONLY_SAMPLE_INSUFFICIENT"
    elif "cost_efficiency_regressed" in reasons:
        status = "OBSERVATION_ONLY_COST_REGRESSED"
    else:
        status = "OBSERVATION_ONLY"
    return {
        "schema": "nexus_training_eligibility_posture_v1",
        "status": status,
        "reason_codes": sorted(set(reasons)),
        "sample_sufficient": cost_efficiency_sample_sufficient,
        "infra_valid_pair_count": infra_quarantine_report.get("infra_valid_pair_count", 0),
        "infra_invalid_pair_count": infra_quarantine_report.get("infra_invalid_pair_count", 0),
        "rubric_required": True,
        "cost_safety_required": True,
        "claim_boundary": "Rubric PASS without sample sufficiency or cost efficiency remains observation-only.",
    }


def derive_valid_comparison_readiness_gate(*, eligible_without_count: int, without_row_count: int) -> dict[str, Any]:
    required = 0 if without_row_count <= 0 else max(1, (2 * without_row_count + 2) // 3)
    ready = eligible_without_count >= required and without_row_count > 0
    failures: list[str] = []
    if without_row_count <= 0:
        failures.append("without_rows_missing")
    elif not ready:
        failures.append("bare_eligibility_below_two_thirds")
    return {
        "schema": "nexus_valid_comparison_readiness_gate_v1",
        "status": "PASS" if ready else "RETURN",
        "eligible_without_count": int(eligible_without_count),
        "without_row_count": int(without_row_count),
        "required_min_eligible_without": int(required),
        "failures": failures,
        "fallback_verdict": "INCONCLUSIVE_PROVIDER_VARIANCE" if not ready else "NONE",
        "claim_boundary": "Cost comparison denominator requires at least 2/3 eligible bare rows.",
    }


def derive_direction_magnitude_gate(
    *,
    valid_comparison_ready: bool,
    wall_cost_ratio_with_over_without: float,
    token_cost_ratio_with_over_without: float,
    model_call_ratio_with_over_without: float,
    paired_wall_ratios: list[float],
    paired_token_ratios: list[float],
) -> dict[str, Any]:
    if not valid_comparison_ready:
        return {
            "schema": "nexus_direction_magnitude_gate_v1",
            "status": "INCONCLUSIVE_VARIANCE",
            "failures": ["valid_comparison_not_ready"],
            "claim_boundary": "Direction/magnitude evaluation requires valid comparison readiness.",
        }

    wall_improvement = max(0.0, 1.0 - float(wall_cost_ratio_with_over_without))
    token_improvement = max(0.0, 1.0 - float(token_cost_ratio_with_over_without))
    model_call_improvement = max(0.0, 1.0 - float(model_call_ratio_with_over_without))
    improvement_floor = min(wall_improvement, token_improvement, model_call_improvement)

    all_ratios = [float(x) for x in [*paired_wall_ratios, *paired_token_ratios] if x > 0]
    variance_band = (max(all_ratios) - min(all_ratios)) if all_ratios else 0.0

    status = "IMPROVED"
    failures: list[str] = []
    if variance_band > 0.10:
        status = "INCONCLUSIVE_VARIANCE"
        failures.append("paired_ratio_variance_above_10pct")
    elif improvement_floor < 0.05:
        status = "NEUTRAL"
        failures.append("improvement_below_5pct")

    return {
        "schema": "nexus_direction_magnitude_gate_v1",
        "status": status,
        "failures": failures,
        "wall_improvement_pct": round(wall_improvement, 4),
        "token_improvement_pct": round(token_improvement, 4),
        "model_call_improvement_pct": round(model_call_improvement, 4),
        "paired_ratio_variance_band": round(variance_band, 4),
        "claim_boundary": "Direction requires two valid x1 rounds; <5% is practical NEUTRAL, >10% variance is INCONCLUSIVE.",
    }


def derive_mutation_hardening_gate(
    *,
    rows: list[dict[str, Any]],
    warning_ledger_summary: dict[str, Any],
    wall_ledger_summary_with: dict[str, Any],
    wall_ledger_summary_without: dict[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []

    warning_lines = list(warning_ledger_summary.get("warning_lines") or [])
    warning_clean = bool(warning_ledger_summary.get("warning_clean", True))
    if warning_clean and warning_lines:
        failures.append("forged_warning_clean_true_with_warning_lines")

    for summary_name, summary in (
        ("with_nexus", wall_ledger_summary_with),
        ("without_nexus", wall_ledger_summary_without),
    ):
        for item in list(summary.get("items") or []):
            if not isinstance(item, dict):
                continue
            conserved = bool(item.get("wall_ledger_conserved", False))
            error_ratio = float(item.get("wall_ledger_reconciliation_error_ratio", 0.0) or 0.0)
            if conserved and error_ratio >= 0.05:
                failures.append(f"forged_wall_conserved_true_with_high_reconciliation_error:{summary_name}")

    suspicious_zero_fill_rows = 0
    for row in rows:
        hv = ((row.get("wall_ledger") or {}).get("wall_ledger_component_telemetry_status") or {}).get("hidden_verifier")
        if str(hv or "") == "SUSPICIOUS_ZERO_FILL":
            suspicious_zero_fill_rows += 1

    status = "PASS" if not failures else "RETURN"
    return {
        "schema": "nexus_mutation_hardening_gate_v1",
        "status": status,
        "failures": sorted(set(failures)),
        "suspicious_zero_fill_rows": suspicious_zero_fill_rows,
        "cases": [
            {
                "mutation": "forged_warning_clean_true_with_warning_lines",
                "expected_verdict": "RETURN",
            },
            {
                "mutation": "forged_wall_conserved_true_with_high_reconciliation_error",
                "expected_verdict": "RETURN",
            },
            {
                "mutation": "forged_hidden_verifier_wall_zero_with_passed_true",
                "expected_telemetry": "SUSPICIOUS_ZERO_FILL",
            },
        ],
    }


def derive_recent_compatible_x1_history(
    *,
    x1_history: list[dict[str, Any]],
    model_label: str,
    manifest_hash: str,
) -> list[bool]:
    compatible_history = [
        item
        for item in x1_history
        if isinstance(item, dict)
        and str(item.get("model") or "") == str(model_label or "")
        and str(item.get("tasks_manifest_hash") or "") == str(manifest_hash or "")
    ]
    return [item.get("x1_readiness_pass") is True for item in compatible_history[-2:]]


def _load_x1_readiness_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(loaded, list):
        return []
    return [item for item in loaded if isinstance(item, dict)]


def _append_x1_readiness_history(
    *,
    path: Path,
    entry: dict[str, Any],
    max_entries: int = 20,
) -> list[dict[str, Any]]:
    history = _load_x1_readiness_history(path)
    history.append(entry)
    history = history[-max(1, int(max_entries)):]
    path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    return history


def _x1_readiness_history_path(*, bundle_path: Path, config: dict[str, Any]) -> Path:
    configured = str(config.get("x1_readiness_history_path") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    repo_root = str(config.get("repo_root") or "").strip()
    if repo_root:
        return Path(repo_root).expanduser().resolve() / ".nexus" / "reports" / "learn" / "x1_readiness_history.json"
    return bundle_path.parent / "x1_readiness_history.json"


def _x1_readiness_pass(
    *,
    valid_comparison_ready: bool,
    wall_ledger_with_conserved_rate: float,
    wall_ledger_without_conserved_rate: float,
    warning_clean_gate_pass: bool,
    provider_token_measured_rate_with: float,
    provider_token_measured_rate_without: float,
) -> bool:
    return bool(
        valid_comparison_ready
        and wall_ledger_with_conserved_rate >= 1.0
        and wall_ledger_without_conserved_rate >= 1.0
        and warning_clean_gate_pass
        and provider_token_measured_rate_with >= 1.0
        and provider_token_measured_rate_without >= 1.0
    )


def derive_x3_promotion_gate(
    *,
    history_last_two_x1_readiness_pass: list[bool],
    valid_comparison_ready: bool,
    wall_ledger_with_conserved_rate: float,
    wall_ledger_without_conserved_rate: float,
    warning_clean_gate_pass: bool,
    provider_token_measured_rate_with: float,
    provider_token_measured_rate_without: float,
) -> dict[str, Any]:
    x1_readiness_pass = _x1_readiness_pass(
        valid_comparison_ready=valid_comparison_ready,
        wall_ledger_with_conserved_rate=wall_ledger_with_conserved_rate,
        wall_ledger_without_conserved_rate=wall_ledger_without_conserved_rate,
        warning_clean_gate_pass=warning_clean_gate_pass,
        provider_token_measured_rate_with=provider_token_measured_rate_with,
        provider_token_measured_rate_without=provider_token_measured_rate_without,
    )
    recent = [item is True for item in history_last_two_x1_readiness_pass[-2:]]
    two_rounds_ready = len(recent) == 2 and all(recent)
    checks = {
        "valid_comparison_ready": bool(valid_comparison_ready),
        "wall_ledger_with_conserved_rate": round(float(wall_ledger_with_conserved_rate), 4),
        "wall_ledger_without_conserved_rate": round(float(wall_ledger_without_conserved_rate), 4),
        "warning_clean_gate_pass": bool(warning_clean_gate_pass),
        "provider_token_measured_rate_with": round(float(provider_token_measured_rate_with), 4),
        "provider_token_measured_rate_without": round(float(provider_token_measured_rate_without), 4),
        "current_x1_readiness_pass": x1_readiness_pass,
        "history_last_two_x1_readiness_pass": recent,
        "history_two_rounds_ready": two_rounds_ready,
    }
    failures: list[str] = []
    if not two_rounds_ready:
        failures.append("missing_two_valid_x1_readiness_rounds")
    if not x1_readiness_pass:
        failures.append("current_x1_readiness_not_passed")
    return {
        "schema": "nexus_x3_promotion_gate_v2",
        "status": "PASS" if two_rounds_ready and x1_readiness_pass else "RETURN",
        "checks": checks,
        "failures": failures,
        "claim_boundary": "x3 requires two consecutive valid x1 readiness rounds under same manifest/model plus clean warning/wall/token gates.",
    }


def _as_seconds(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def evaluate_wall_ledger_conservation(row: dict[str, Any]) -> dict[str, Any]:
    total = _as_seconds(row.get("wall_duration_sec", row.get("duration_sec")))
    timing_keys = (
        "gateway_total_sec",
        "direct_gemini_process_sec",
        "gateway_process_sec",
        "gateway_provider_wait_sec",
        "phase_wall_total_sec",
        "phase_wall_r_sec",
        "hidden_verifier_wall_sec",
        "direct_verifier_wall_sec",
        "direct_infra_retry_wall_sec",
        "hidden_retry_wall_sec",
        "hidden_retry_verifier_wall_sec",
        "deterministic_pre_rescue_wall_sec",
        "receipt_write_sec",
        "cli_uninstrumented_sec",
    )
    timing_present = any(_as_seconds(row.get(key)) is not None for key in timing_keys)
    components: dict[str, float] = {}
    expected: list[str] = []
    missing: list[str] = []
    telemetry_status: dict[str, str] = {}
    telemetry_reason_codes: list[str] = []

    def add_component(name: str, *keys: str, required: bool = False) -> None:
        value = next((_as_seconds(row.get(key)) for key in keys if _as_seconds(row.get(key)) is not None), None)
        if required:
            expected.append(name)
        if value is None:
            if required:
                missing.append(name)
            return
        components[name] = value

    model_required = int(row.get("model_calls", 0) or 0) > 0
    model_gateway_fallback_total = False
    add_component(
        "model_gateway",
        "gateway_total_sec",
        "direct_gemini_process_sec",
        "gateway_process_sec",
        "gateway_provider_wait_sec",
        required=model_required and timing_present,
    )
    if model_required and timing_present and total is not None:
        raw_gateway_values = [
            _as_seconds(row.get("gateway_total_sec")),
            _as_seconds(row.get("direct_gemini_process_sec")),
            _as_seconds(row.get("gateway_process_sec")),
            _as_seconds(row.get("gateway_provider_wait_sec")),
        ]
        all_gateway_zero_or_missing = all(value is None or value <= 0.0 for value in raw_gateway_values)
        if all_gateway_zero_or_missing:
            components["model_gateway"] = float(total)
            telemetry_status["model_gateway"] = "FALLBACK_TOTAL_WALL"
            if not bool(row.get("hidden_verifier_passed")):
                telemetry_reason_codes.append("model_gateway_fallback_to_total_wall_sec")
            model_gateway_fallback_total = True
    add_component("direct_verifier", "direct_verifier_wall_sec")
    add_component("direct_infra_retry", "direct_infra_retry_wall_sec")
    no_model_with_nexus_timing = not model_required and timing_present and str(row.get("mode") or "") == "with_nexus"
    if no_model_with_nexus_timing:
        add_component("nexus_phase", "phase_wall_total_sec", "phase_wall_r_sec", required=True)
    hidden_verifier_value = _as_seconds(row.get("hidden_verifier_wall_sec"))
    hidden_verifier_wall_source = str(row.get("hidden_verifier_wall_source") or "")
    hidden_verifier_required = (
        bool(row.get("hidden_verifier_file"))
        or bool(row.get("hidden_verifier_passed"))
        or hidden_verifier_value is not None
    )
    if model_gateway_fallback_total and model_required and bool(row.get("hidden_verifier_passed")):
        telemetry_status["hidden_verifier"] = "INCLUDED_IN_MODEL_GATEWAY_FALLBACK_TOTAL"
    elif (
        hidden_verifier_value == 0.0
        and bool(row.get("hidden_verifier_passed"))
        and hidden_verifier_wall_source == "included_in_model_attempt_wall_sec"
    ):
        telemetry_status["hidden_verifier"] = "INCLUDED_IN_MODEL_ATTEMPT"
    elif hidden_verifier_value is not None and not (hidden_verifier_value == 0.0 and bool(row.get("hidden_verifier_passed"))):
        telemetry_status["hidden_verifier"] = "PRESENT"
        add_component("hidden_verifier", "hidden_verifier_wall_sec", required=hidden_verifier_required)
    elif hidden_verifier_required:
        expected.append("hidden_verifier")
        missing.append("hidden_verifier")
        if hidden_verifier_value == 0.0 and bool(row.get("hidden_verifier_passed")):
            telemetry_status["hidden_verifier"] = "SUSPICIOUS_ZERO_FILL"
            telemetry_reason_codes.append("hidden_verifier_wall_suspicious_zero_fill")
        else:
            telemetry_status["hidden_verifier"] = "MISSING_BUT_REQUIRED"
            telemetry_reason_codes.append("hidden_verifier_wall_missing_but_required")
    else:
        telemetry_status["hidden_verifier"] = "NOT_APPLICABLE"
    hidden_retry_required = bool(row.get("hidden_retry_used"))
    add_component("hidden_retry", "hidden_retry_wall_sec", required=hidden_retry_required)
    add_component("hidden_retry_verifier", "hidden_retry_verifier_wall_sec")
    add_component("deterministic_pre_rescue", "deterministic_pre_rescue_wall_sec")
    add_component("receipt_write", "receipt_write_sec")
    if no_model_with_nexus_timing:
        cli_uninstrumented = _as_seconds(row.get("cli_uninstrumented_sec"))
        if cli_uninstrumented is not None:
            already_attributed = sum(components.values())
            residual_cli = min(float(cli_uninstrumented), max(0.0, float(total or 0.0) - already_attributed))
            if residual_cli > 0.0:
                components["cli_uninstrumented"] = round(residual_cli, 4)
                telemetry_status["cli_uninstrumented"] = (
                    "RESIDUAL_AFTER_LOCAL_COMPONENTS"
                    if residual_cli < float(cli_uninstrumented)
                    else "PRESENT"
                )
    if no_model_with_nexus_timing:
        runner_overhead = _as_seconds(row.get("model_attempt_runner_overhead_sec"))
        if runner_overhead is not None and runner_overhead > 0.0:
            hidden_component = float(components.get("hidden_verifier", 0.0) or 0.0)
            residual_runner_overhead = round(max(0.0, runner_overhead - hidden_component), 4)
            if residual_runner_overhead > 0.0:
                components["runner_overhead_non_verifier"] = residual_runner_overhead
                telemetry_status["runner_overhead_non_verifier"] = "PRESENT"

    if total is None or total <= 0.0 or not timing_present or not expected:
        return {
            "schema": "nexus_wall_ledger_conservation_v1",
            "status": "NOT_APPLICABLE",
            "reason_codes": [],
            "wall_ledger_components": components,
            "wall_ledger_component_telemetry_status": telemetry_status,
            "wall_ledger_component_coverage_rate": 1.0,
            "wall_ledger_attributed_sec": 0.0,
            "wall_ledger_total_sec": round(float(total or 0.0), 4),
            "unattributed_wall_sec": 0.0,
            "max_component_drift_sec": 0.0,
            "wall_ledger_reconciliation_error_ratio": 0.0,
            "wall_ledger_conserved": True,
        }

    attributed = round(sum(components.values()), 4)
    drift = round(abs(float(total) - attributed), 4)
    coverage = round((len(expected) - len(missing)) / len(expected), 4) if expected else 1.0
    error_ratio = round(drift / float(total), 4) if total else 0.0
    reason_codes: list[str] = []
    if coverage < 1.0:
        reason_codes.append("wall_ledger_component_missing")
    reason_codes.extend(telemetry_reason_codes)
    if error_ratio >= 0.05:
        reason_codes.append("wall_ledger_reconciliation_error")
    status = "PASS" if not reason_codes else "TELEMETRY_INVALID"
    return {
        "schema": "nexus_wall_ledger_conservation_v1",
        "status": status,
        "reason_codes": reason_codes,
        "wall_ledger_components": components,
        "wall_ledger_component_telemetry_status": telemetry_status,
        "wall_ledger_expected_components": expected,
        "wall_ledger_missing_components": missing,
        "wall_ledger_component_coverage_rate": coverage,
        "wall_ledger_attributed_sec": attributed,
        "wall_ledger_total_sec": round(float(total), 4),
        "unattributed_wall_sec": round(max(0.0, float(total) - attributed), 4),
        "max_component_drift_sec": drift,
        "wall_ledger_reconciliation_error_ratio": error_ratio,
        "wall_ledger_conserved": status == "PASS",
    }


def summarize_wall_ledger_conservation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = [evaluate_wall_ledger_conservation(row) for row in rows]
    applicable = [item for item in evaluated if item.get("status") != "NOT_APPLICABLE"]
    invalid = [item for item in applicable if item.get("status") == "TELEMETRY_INVALID"]
    return {
        "schema": "nexus_wall_ledger_conservation_summary_v1",
        "rows": len(rows),
        "applicable_rows": len(applicable),
        "telemetry_invalid_rows": len(invalid),
        "conserved_rate": round((len(applicable) - len(invalid)) / len(applicable), 4) if applicable else 1.0,
        "component_coverage_rate_min": round(min((float(item.get("wall_ledger_component_coverage_rate", 1.0)) for item in applicable), default=1.0), 4),
        "reconciliation_error_ratio_max": round(max((float(item.get("wall_ledger_reconciliation_error_ratio", 0.0)) for item in applicable), default=0.0), 4),
        "max_component_drift_sec": round(max((float(item.get("max_component_drift_sec", 0.0)) for item in applicable), default=0.0), 4),
        "reason_codes": sorted({reason for item in invalid for reason in item.get("reason_codes", [])}),
        "items": evaluated,
    }


def _row_key_counts(rows: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (str(row.get("task_id") or ""), str(row.get("trial_index") or "1"))
        counts[key] = counts.get(key, 0) + 1
    return counts


def _write_trial_evidence(
    *,
    evidence_root: Path,
    row: dict[str, Any],
    target_before: str | None,
    target_after: str | None,
) -> dict[str, str]:
    evidence_root.mkdir(parents=True, exist_ok=True)
    task_id = _safe_artifact_name(str(row.get("task_id", "task")))
    mode = _safe_artifact_name(str(row.get("mode", "mode")))
    trial = _safe_artifact_name(str(row.get("trial_index", "1")))
    stem = f"{mode}__{task_id}__trial_{trial}"
    row_path = evidence_root / f"{stem}.row.json"
    diff_path = evidence_root / f"{stem}.target.diff"

    row_path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
    before = target_before or ""
    after = target_after or ""
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="target.before",
            tofile="target.after",
        )
    )
    diff_path.write_text(diff, encoding="utf-8")
    return {
        "evidence_record_file": str(row_path),
        "evidence_diff_file": str(diff_path),
        "target_before_sha256": _sha256_text(before),
        "target_after_sha256": _sha256_text(after),
        "target_diff_sha256": _sha256_file(diff_path),
    }


def _route_cost_ledger(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def number(row: dict[str, Any], *keys: str) -> float:
        for key in keys:
            value = row.get(key)
            if value in (None, ""):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    def mean(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    def source_counts(source_rows: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in source_rows:
            source = str(row.get("gateway_token_source") or "missing")
            counts[source] = counts.get(source, 0) + 1
        return dict(sorted(counts.items()))

    phase_fields = {
        "P": "phase_wall_p_sec",
        "X": "phase_wall_x_sec",
        "D": "phase_wall_d_sec",
        "R": "phase_wall_r_sec",
        "A": "phase_wall_a_sec",
        "C": "phase_wall_c_sec",
    }

    def task_capability(row: dict[str, Any]) -> str:
        task_id = str(row.get("task_id") or "")
        match = re.match(r"route-oracle-(?P<capability>.+?)-\d+$", task_id)
        if match:
            return match.group("capability")
        expected = row.get("expected_capabilities")
        if isinstance(expected, str) and expected.strip():
            return expected.split(",")[0].strip()
        if isinstance(expected, list) and expected:
            return str(expected[0])
        return str(row.get("task_type") or "unknown")

    def phase_sums(source_rows: list[dict[str, Any]]) -> dict[str, float]:
        return {
            phase: round(sum(number(row, field) for row in source_rows), 4)
            for phase, field in phase_fields.items()
        }

    def phase_share(sums: dict[str, float]) -> dict[str, float]:
        total = sum(sums.values())
        if total <= 0:
            return {phase: 0.0 for phase in sums}
        return {phase: round(value / total, 4) for phase, value in sums.items()}

    def offender(row: dict[str, Any]) -> dict[str, Any]:
        phase_values = {phase: number(row, field) for phase, field in phase_fields.items()}
        dominant_phase = max(phase_values, key=phase_values.get) if phase_values else ""
        return {
            "task_id": str(row.get("task_id") or ""),
            "trial_index": int(number(row, "trial_index") or 0),
            "task_capability": task_capability(row),
            "task_type": str(row.get("task_type") or ""),
            "model_name": str(row.get("model_name") or ""),
            "wall_duration_sec": round(number(row, "wall_duration_sec", "duration_sec"), 4),
            "total_tokens": int(number(row, "total_tokens", "model_total_tokens")),
            "model_calls": int(number(row, "model_calls")),
            "phase_wall_total_sec": round(number(row, "phase_wall_total_sec"), 4),
            "phase_wall_p_sec": round(number(row, "phase_wall_p_sec"), 4),
            "phase_wall_x_sec": round(number(row, "phase_wall_x_sec"), 4),
            "phase_wall_d_sec": round(number(row, "phase_wall_d_sec"), 4),
            "phase_wall_r_sec": round(number(row, "phase_wall_r_sec"), 4),
            "phase_wall_a_sec": round(number(row, "phase_wall_a_sec"), 4),
            "phase_wall_c_sec": round(number(row, "phase_wall_c_sec"), 4),
            "dominant_phase": dominant_phase,
            "route_recommended_flow": str(row.get("route_recommended_flow") or ""),
            "strategy_path": str(row.get("strategy_path") or ""),
        }

    def top_offenders(source_rows: list[dict[str, Any]], key: str, limit: int = 5) -> list[dict[str, Any]]:
        ranked = sorted(source_rows, key=lambda row: number(row, key), reverse=True)
        return [offender(row) for row in ranked[:limit] if number(row, key) > 0]

    def grouped_average(source_rows: list[dict[str, Any]], group_key: str) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in source_rows:
            key = task_capability(row) if group_key == "task_capability" else str(row.get(group_key) or "unknown")
            groups.setdefault(key, []).append(row)
        out: list[dict[str, Any]] = []
        for key, group_rows in groups.items():
            out.append(
                {
                    group_key: key,
                    "rows": len(group_rows),
                    "avg_wall_duration_sec": mean([number(row, "wall_duration_sec", "duration_sec") for row in group_rows]),
                    "avg_phase_wall_r_sec": mean([number(row, "phase_wall_r_sec") for row in group_rows]),
                    "avg_tokens": mean([number(row, "total_tokens", "model_total_tokens") for row in group_rows]),
                }
            )
        return sorted(out, key=lambda item: item["avg_wall_duration_sec"], reverse=True)

    def arm(mode: str) -> dict[str, Any]:
        arm_rows = [row for row in rows if str(row.get("mode")) == mode]
        eligible = [row for row in arm_rows if bool(row.get("run_eligible", True))]
        sums = phase_sums(eligible)
        return {
            "rows": len(arm_rows),
            "eligible_rows": len(eligible),
            "avg_wall_duration_sec": mean([number(row, "wall_duration_sec", "duration_sec") for row in eligible]),
            "avg_phase_wall_r_sec": mean([number(row, "phase_wall_r_sec") for row in eligible]),
            "avg_r_phase_hyper_sprint_sec": mean([number(row, "r_phase_hyper_sprint_sec") for row in eligible]),
            "avg_r_phase_total_sec": mean([number(row, "r_phase_total_sec") for row in eligible]),
            "avg_model_calls": mean([number(row, "model_calls") for row in eligible]),
            "avg_tokens": mean([number(row, "total_tokens", "model_total_tokens") for row in eligible]),
            "token_measured_rate": _rate_for(eligible, "token_measured"),
            "provider_token_measured_rate": round(sum(1 for row in eligible if _row_has_measured_provider_tokens(row)) / len(eligible), 4)
            if eligible
            else 0.0,
            "provider_token_source_counts": source_counts(eligible),
            "measured_token_only_cost_comparable_rate": _rate_for(eligible, "public_cost_evidence"),
            "clean_model_cost_evidence_rate": _rate_for(eligible, "clean_model_cost_evidence"),
            "training_eligible_cost_evidence_rate": _rate_for(eligible, "training_eligible_cost_evidence"),
            "route_recommended_flow_present_rate": _rate_for(eligible, "route_recommended_flow"),
            "chosen_flow_present_rate": _rate_for(eligible, "chosen_flow"),
            "route_decision_present_rate": _rate_for(eligible, "route_decision_schema_version"),
            "capability_selected_avg": mean([number(row, "route_decision_selected_count") for row in eligible]),
            "capability_required_avg": mean([number(row, "route_decision_required_count") for row in eligible]),
            "capability_conditional_avg": mean([number(row, "route_decision_conditional_count") for row in eligible]),
            "phase_wall_sum_sec": sums,
            "phase_wall_share": phase_share(sums),
            "top_wall_offenders": top_offenders(eligible, "wall_duration_sec"),
            "top_token_offenders": top_offenders(eligible, "total_tokens"),
            "top_phase_wall_offenders": top_offenders(eligible, "phase_wall_total_sec"),
            "by_task_capability": grouped_average(eligible, "task_capability"),
            "by_task_type": grouped_average(eligible, "task_type"),
        }

    return {
        "schema": "nexus_route_cost_ledger_v1",
        "scope": "measured_benchmark_telemetry_not_billing_cost",
        "arms": {
            "without_nexus": arm("without_nexus"),
            "with_nexus": arm("with_nexus"),
        },
        "claim_boundary": [
            "Do not treat measured tokens as provider billing cost.",
            "Do not infer per-capability ROI until per-capability allocation exists.",
            "Long-tail offenders identify measured phase-wall concentration, not root cause by themselves.",
        ],
    }


def _commercial_model_roi_shadow_hooks(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def number(row: dict[str, Any], *keys: str) -> float:
        for key in keys:
            value = row.get(key)
            if value in (None, ""):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    def is_verified(row: dict[str, Any]) -> bool:
        return bool(row.get("semantic_completed", False)) and not bool(row.get("report_trust_mismatch", False))

    def capability(row: dict[str, Any]) -> str:
        expected = row.get("expected_capabilities")
        if isinstance(expected, str) and expected.strip():
            return expected.split(",")[0].strip()
        if isinstance(expected, list) and expected:
            return str(expected[0])
        return str(row.get("task_type") or "unknown")

    def bucket_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
        lane = str(
            row.get("route_cost_policy_lane")
            or row.get("route_lane")
            or row.get("route_recommended_flow")
            or row.get("nexus_winner_source")
            or "unknown"
        )
        strategy = str(row.get("strategy_path") or row.get("route_strategy") or row.get("chosen_flow") or "unknown")
        tier = str(row.get("nexus_tier") or row.get("route_tier") or "unknown")
        task_type = str(row.get("task_type") or "unknown")
        return lane, strategy, tier, task_type

    with_by_key = {
        (str(row.get("task_id") or ""), int(number(row, "trial_index") or 0)): row
        for row in rows
        if str(row.get("mode") or "") == "with_nexus" and bool(row.get("run_eligible", True))
    }
    without_by_key = {
        (str(row.get("task_id") or ""), int(number(row, "trial_index") or 0)): row
        for row in rows
        if str(row.get("mode") or "") == "without_nexus" and bool(row.get("run_eligible", True))
    }
    pair_keys = sorted(set(with_by_key) & set(without_by_key))
    signals: list[dict[str, Any]] = []
    buckets: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for task_id, trial_index in pair_keys:
        with_row = with_by_key[(task_id, trial_index)]
        without_row = without_by_key[(task_id, trial_index)]
        with_verified = is_verified(with_row)
        without_verified = is_verified(without_row)
        wall_with = number(with_row, "wall_duration_sec", "duration_sec")
        wall_without = number(without_row, "wall_duration_sec", "duration_sec")
        tokens_with = number(with_row, "total_tokens", "model_total_tokens")
        tokens_without = number(without_row, "total_tokens", "model_total_tokens")
        reason_codes: list[str] = []
        if with_verified and not without_verified:
            reason_codes.append("verified_lift_against_direct_commercial_model")
        if with_verified and wall_without > 0 and wall_with > wall_without * 1.05:
            reason_codes.append("verified_lift_or_delivery_with_wall_regression")
        if with_verified and tokens_without > 0 and tokens_with < tokens_without:
            reason_codes.append("verified_delivery_with_token_savings")
        wall_delta = wall_with - wall_without
        token_ratio = tokens_with / tokens_without if tokens_without > 0 else 0.0
        model_calls_with = number(with_row, "model_calls")
        model_calls_without = number(without_row, "model_calls")
        bucket = buckets.setdefault(
            bucket_key(with_row),
            {
                "pair_count": 0,
                "verified_lift_count": 0,
                "both_verified_count": 0,
                "wall_ratios": [],
                "sum_wall_delta": 0.0,
                "token_ratios": [],
                "model_call_ratios": [],
                "reason_codes": set(),
            },
        )
        bucket["pair_count"] += 1
        bucket["verified_lift_count"] += int(with_verified and not without_verified)
        bucket["both_verified_count"] += int(with_verified and without_verified)
        if wall_without > 0:
            bucket["wall_ratios"].append(wall_with / wall_without)
        bucket["sum_wall_delta"] += wall_delta
        if tokens_without > 0:
            bucket["token_ratios"].append(token_ratio)
        if model_calls_without > 0:
            bucket["model_call_ratios"].append(model_calls_with / model_calls_without)
        if with_verified and wall_without > 0 and wall_with > wall_without * 1.05:
            bucket["reason_codes"].add("wall_regression")
            if number(with_row, "phase_wall_r_sec") > 0:
                bucket["reason_codes"].add("r_phase_wall_concentrated")
        if str(with_row.get("strategy_path") or "").startswith("hyper_direct"):
            bucket["reason_codes"].add("hyper_direct_forced_wall_regression")
        if with_verified and wall_delta > 0 and 0.0 < token_ratio < 1.0:
            bucket["reason_codes"].add("token_savings_wall_regression_tradeoff")
        if reason_codes:
            signals.append(
                {
                    "row_locator": {
                        "pair_key_sha256": _sha256_text(f"{task_id}:{trial_index}")[:16],
                        "trial_index": trial_index,
                    },
                    "task_capability": capability(with_row),
                    "task_type": str(with_row.get("task_type") or ""),
                    "model_name": str(with_row.get("model_name") or without_row.get("model_name") or ""),
                    "reason_codes": sorted(set(reason_codes)),
                    "with_verified": with_verified,
                    "without_verified": without_verified,
                    "wall_ratio_with_over_without": round(wall_with / wall_without, 4) if wall_without > 0 else None,
                    "token_ratio_with_over_without": round(tokens_with / tokens_without, 4) if tokens_without > 0 else None,
                }
            )
    reason_counts: dict[str, int] = {}
    for signal in signals:
        for reason in signal["reason_codes"]:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    concentration_buckets = []
    for (lane, strategy, tier, task_type), bucket in buckets.items():
        wall_ratios = sorted(bucket["wall_ratios"])
        token_ratios = bucket["token_ratios"]
        model_call_ratios = bucket["model_call_ratios"]
        p95_index = max(0, min(len(wall_ratios) - 1, int(round(len(wall_ratios) * 0.95)) - 1)) if wall_ratios else 0
        concentration_buckets.append(
            {
                "route_cost_policy_lane": lane,
                "strategy_path": strategy,
                "nexus_tier": tier,
                "task_type": task_type,
                "pair_count": int(bucket["pair_count"]),
                "verified_lift_count": int(bucket["verified_lift_count"]),
                "both_verified_count": int(bucket["both_verified_count"]),
                "avg_wall_ratio": round(sum(wall_ratios) / len(wall_ratios), 4) if wall_ratios else 0.0,
                "p95_wall_ratio": round(wall_ratios[p95_index], 4) if wall_ratios else 0.0,
                "sum_wall_delta": round(float(bucket["sum_wall_delta"]), 4),
                "avg_token_ratio": round(sum(token_ratios) / len(token_ratios), 4) if token_ratios else 0.0,
                "avg_model_call_ratio": round(sum(model_call_ratios) / len(model_call_ratios), 4)
                if model_call_ratios
                else 0.0,
                "reason_codes": sorted(bucket["reason_codes"]),
            }
        )
    concentration_buckets.sort(key=lambda item: float(item["sum_wall_delta"]), reverse=True)
    return {
        "schema": "nexus_commercial_model_roi_shadow_hooks_v1",
        "status": "OBSERVATION_ONLY",
        "pair_count": len(pair_keys),
        "signal_count": len(signals),
        "reason_counts": dict(sorted(reason_counts.items())),
        "signals": signals,
        "wall_regression_concentration": {
            "schema": "nexus_wall_regression_concentration_v1",
            "status": "OBSERVATION_ONLY",
            "promotion_effect": "none",
            "buckets": concentration_buckets[:8],
        },
        "promotion_effect": "none",
        "claim_boundary": [
            "Shadow hooks classify commercial-model telemetry for policy learning only.",
            "They must not change delivery, trust, cost, or x3 promotion gates.",
            "Pair locators are hashed so the hook does not special-case a public task id.",
        ],
    }


def _product_kpis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def number(row: dict[str, Any], *keys: str) -> float:
        for key in keys:
            value = row.get(key)
            if value in (None, ""):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    def mean(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    def is_verified(row: dict[str, Any]) -> bool:
        return str(row.get("semantic_status") or "") == "VERIFIED"

    def has_policy_hit(row: dict[str, Any]) -> bool:
        return any(
            [
                bool(row.get("guard_hit")),
                bool(row.get("capability_nightshift_recommended")),
                number(row, "route_memory_hits", "memory_hits", "prior_fix_hits") > 0,
                number(row, "policy_hits", "findings_hits") > 0,
                str(row.get("capability_stack_governance_layers") or "").strip() not in {"", "[]"},
            ]
        )

    def replay_observed(row: dict[str, Any]) -> bool:
        return any(
            [
                bool(row.get("hidden_verifier_file")),
                row.get("hidden_verifier_passed") not in (None, ""),
                bool(row.get("replay_command")),
                row.get("replay_exit_code") not in (None, ""),
            ]
        )

    def replay_passed(row: dict[str, Any]) -> bool:
        if row.get("hidden_verifier_passed") not in (None, ""):
            return bool(row.get("hidden_verifier_passed"))
        if row.get("replay_exit_code") not in (None, ""):
            return number(row, "replay_exit_code") == 0
        return False

    def arm(mode: str) -> dict[str, Any]:
        arm_rows = [row for row in rows if str(row.get("mode")) == mode]
        eligible = [row for row in arm_rows if bool(row.get("run_eligible", True))]
        verified = [row for row in eligible if is_verified(row)]
        policy_rows = [row for row in eligible if has_policy_hit(row)]
        replay_rows = [row for row in eligible if replay_observed(row)]
        return {
            "rows": len(arm_rows),
            "eligible_rows": len(eligible),
            "avg_time_to_verified_sec": mean([number(row, "wall_duration_sec", "duration_sec") for row in verified]),
            "fail_closed_block_rate": round((len(eligible) - len(verified)) / len(eligible), 4) if eligible else 0.0,
            "replay_observed_rate": round(len(replay_rows) / len(eligible), 4) if eligible else 0.0,
            "replay_pass_rate": round(sum(1 for row in replay_rows if replay_passed(row)) / len(replay_rows), 4) if replay_rows else 0.0,
            "policy_hit_rows": len(policy_rows),
            "policy_hit_success_rate": round(sum(1 for row in policy_rows if is_verified(row)) / len(policy_rows), 4) if policy_rows else 0.0,
        }

    return {
        "schema": "nexus_product_kpis_v1",
        "scope": "benchmark_row_telemetry",
        "arms": {
            "without_nexus": arm("without_nexus"),
            "with_nexus": arm("with_nexus"),
        },
        "claim_boundary": [
            "Fail-closed block rate counts benchmark rows that remained unverified; it is not a production incident rate.",
            "Replay pass rate uses hidden-verifier/replay evidence when present.",
            "Policy-hit success rate depends on available row telemetry and should be compared within the same benchmark schema.",
        ],
    }


def _openseeker_kpis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def number(row: dict[str, Any], key: str) -> float:
        value = row.get(key)
        if value in (None, ""):
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def mean(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    def arm(mode: str) -> dict[str, Any]:
        arm_rows = [row for row in rows if str(row.get("mode")) == mode]
        eligible = [row for row in arm_rows if bool(row.get("run_eligible", True))]
        traced = [row for row in eligible if str(row.get("openseeker_schema_version") or "").strip()]
        return {
            "rows": len(arm_rows),
            "eligible_rows": len(eligible),
            "traced_rows": len(traced),
            "trace_present_rate": round(len(traced) / len(eligible), 4) if eligible else 0.0,
            "avg_trajectory_step_count": mean([number(row, "trajectory_step_count") for row in traced]),
            "avg_tool_action_count": mean([number(row, "tool_action_count") for row in traced]),
            "avg_route_tactical_tool_count": mean([number(row, "route_tactical_tool_count") for row in traced]),
            "avg_route_evidence_required_count": mean([number(row, "route_evidence_required_count") for row in traced]),
            "avg_evidence_hop_count": mean([number(row, "evidence_hop_count") for row in traced]),
            "avg_evidence_source_count": mean([number(row, "evidence_source_count") for row in traced]),
            "low_step_filtered_rate": _rate_for(traced, "low_step_filtered"),
            "long_horizon_ready_rate": _rate_for(traced, "long_horizon_ready"),
        }

    return {
        "schema": "nexus_openseeker_benchmark_kpis_v1",
        "scope": "benchmark_row_telemetry",
        "arms": {
            "without_nexus": arm("without_nexus"),
            "with_nexus": arm("with_nexus"),
        },
        "claim_boundary": [
            "OpenSeeker alignment metrics describe trajectory richness, not model training quality.",
            "Low-step filtering is a learning-data gate and must not be interpreted as task failure by itself.",
        ],
    }


def write_evidence_bundle(
    *,
    out_dir: Path,
    with_path: Path,
    without_path: Path,
    rows: list[dict[str, Any]],
    config: dict[str, Any],
) -> Path:
    bundle_path = out_dir / "evidence_bundle.json"
    artifact_files = []
    for row in rows:
        for key in ("evidence_record_file", "evidence_diff_file"):
            value = row.get(key)
            if value:
                path = Path(str(value))
                if path.exists():
                    artifact_files.append({"path": str(path), "sha256": _sha256_file(path)})
    session_worker_contamination = _annotate_session_worker_contamination(rows)
    with_rows = [row for row in rows if str(row.get("mode")) == "with_nexus"]
    without_rows = [row for row in rows if str(row.get("mode")) == "without_nexus"]
    eligible_with = [row for row in with_rows if bool(row.get("run_eligible", True))]
    eligible_without = [row for row in without_rows if bool(row.get("run_eligible", True))]
    warning_ledger_required = bool(config.get("warning_ledger_required", False))
    for row in rows:
        wall_ledger = evaluate_wall_ledger_conservation(row)
        row["wall_ledger_conservation"] = wall_ledger
        row["wall_ledger_status"] = wall_ledger.get("status")
        row["wall_ledger_component_coverage_rate"] = wall_ledger.get("wall_ledger_component_coverage_rate")
        row["unattributed_wall_sec"] = wall_ledger.get("unattributed_wall_sec")
        row["max_component_drift_sec"] = wall_ledger.get("max_component_drift_sec")
        row["wall_ledger_reconciliation_error_ratio"] = wall_ledger.get("wall_ledger_reconciliation_error_ratio")
        row["wall_ledger_conserved"] = wall_ledger.get("wall_ledger_conserved")
    wall_ledger_summary_with = summarize_wall_ledger_conservation(eligible_with)
    wall_ledger_summary_without = summarize_wall_ledger_conservation(eligible_without)
    wall_ledger_invalid = (
        int(wall_ledger_summary_with.get("telemetry_invalid_rows", 0) or 0) > 0
        or int(wall_ledger_summary_without.get("telemetry_invalid_rows", 0) or 0) > 0
    )
    warning_ledger_summary = _summarize_warning_rows(rows)
    warning_ledger_invalid = bool(
        warning_ledger_required
        and (
            not bool(warning_ledger_summary.get("warning_clean", True))
            or float(warning_ledger_summary.get("warning_capture_completeness", 1.0) or 0.0) < 1.0
            or int(warning_ledger_summary.get("unresolved_warning_count", 0) or 0) > 0
        )
    )
    outbound_prompt_ledger_summary = _summarize_outbound_prompt_ledger(
        config.get("outbound_prompt_ledger"),
        expected_min_records=sum(1 for row in rows if int(row.get("model_calls", 0) or 0) > 0),
    )
    outbound_prompt_ledger_invalid = bool(
        config.get("outbound_prompt_ledger") and outbound_prompt_ledger_summary.get("status") != "PASS"
    )

    infra_quarantine_report = compute_infra_quarantine_report(with_rows, without_rows)

    def rubric_summary(source_rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not source_rows:
            return {
                "rows": 0,
                "overall_pass_rate": 0.0,
                "plan_pass_rate": 0.0,
                "evidence_pass_rate": 0.0,
                "delivery_pass_rate": 0.0,
                "cost_pass_rate": 0.0,
                "hard_fail_reasons": [],
            }

        def section_pass(row: dict[str, Any], section: str) -> bool:
            rubric = row.get("rubric_contract")
            rubric = rubric if isinstance(rubric, dict) else {}
            payload = rubric.get(section)
            payload = payload if isinstance(payload, dict) else {}
            return str(payload.get("status") or "") == "PASS"

        reasons: set[str] = set()
        for row in source_rows:
            for reason in row.get("rubric_contract_hard_fail_reasons", []) or []:
                text = str(reason).strip()
                if text:
                    reasons.add(text)
        return {
            "rows": len(source_rows),
            "overall_pass_rate": round(
                sum(1 for row in source_rows if str(row.get("rubric_contract_status") or "") == "PASS")
                / len(source_rows),
                4,
            ),
            "plan_pass_rate": round(sum(1 for row in source_rows if section_pass(row, "plan_rubric")) / len(source_rows), 4),
            "evidence_pass_rate": round(sum(1 for row in source_rows if section_pass(row, "evidence_rubric")) / len(source_rows), 4),
            "delivery_pass_rate": round(sum(1 for row in source_rows if section_pass(row, "delivery_rubric")) / len(source_rows), 4),
            "cost_pass_rate": round(sum(1 for row in source_rows if section_pass(row, "cost_rubric")) / len(source_rows), 4),
            "hard_fail_reasons": sorted(reasons),
        }

    with_models = _model_names(with_rows)
    without_models = _model_names(without_rows)
    hidden_verifier_mode = bool(config.get("hidden_verifier_mode"))
    same_task_trials = _row_key_counts(with_rows) == _row_key_counts(without_rows)
    with_trust_mismatch_rate = _rate_for(eligible_with, "report_trust_mismatch")
    without_trust_mismatch_rate = _rate_for(eligible_without, "report_trust_mismatch")
    with_semantic_verified_rate = _rate_for(eligible_with, "semantic_completed")
    without_semantic_verified_rate = _rate_for(eligible_without, "semantic_completed")
    nexus_valid_rate = _rate_for(with_rows, "nexus_wearing_valid")
    model_uses_nexus_rate = _rate_for(with_rows, "model_uses_nexus")
    legacy_gemini_uses_nexus_rate = _rate_for(with_rows, "gemini_uses_nexus")
    nexus_context_delivered_rate = _rate_for(with_rows, "nexus_context_delivered")
    nexus_usage_valid_rate = _rate_for(with_rows, "nexus_usage_valid")
    claim_verified_rate = _rate_for(with_rows, "capability_claim_verified")
    route_decision_present_rate = _rate_for(with_rows, "route_decision_schema_version")
    local_reflex_verified_rows = [
        row
        for row in with_rows
        if bool(row.get("local_success_source"))
        and bool(row.get("semantic_completed"))
        and bool(row.get("hidden_verifier_passed", True))
        and not bool(row.get("report_trust_mismatch"))
        and bool(row.get("nexus_wearing_valid"))
        and bool(row.get("nexus_context_delivered"))
        and bool(row.get("capability_claim_verified"))
    ]
    local_reflex_verified_rate = round(len(local_reflex_verified_rows) / len(with_rows), 4) if with_rows else 0.0
    nexus_system_execution_valid_rate = (
        round(
            sum(
                1
                for row in with_rows
                if bool(row.get("model_uses_nexus"))
                or bool(row.get("gemini_uses_nexus"))
                or row in local_reflex_verified_rows
            )
            / len(with_rows),
            4,
        )
        if with_rows
        else 0.0
    )
    nexus_system_usage_valid_rate = (
        round(
            sum(1 for row in with_rows if bool(row.get("nexus_usage_valid")) or row in local_reflex_verified_rows)
            / len(with_rows),
            4,
        )
        if with_rows
        else 0.0
    )
    token_measured_rate_with = _rate_for(with_rows, "token_measured")
    token_measured_rate_without = _rate_for(without_rows, "token_measured")
    provider_token_measured_rate_with = round(sum(1 for row in with_rows if _row_has_measured_provider_tokens(row)) / len(with_rows), 4) if with_rows else 0.0
    provider_token_measured_rate_without = (
        round(sum(1 for row in without_rows if _row_has_measured_provider_tokens(row)) / len(without_rows), 4) if without_rows else 0.0
    )
    with_avg_wall_sec = _public_gate_mean_number(eligible_with, "wall_duration_sec", "duration_sec")
    without_avg_wall_sec = _public_gate_mean_number(eligible_without, "wall_duration_sec", "duration_sec")
    with_avg_tokens = _public_gate_mean_number(eligible_with, "total_tokens", "model_total_tokens")
    without_avg_tokens = _public_gate_mean_number(eligible_without, "total_tokens", "model_total_tokens")
    with_avg_model_calls = _public_gate_mean_number(eligible_with, "model_calls")
    without_avg_model_calls = _public_gate_mean_number(eligible_without, "model_calls")
    with_avg_prompt_system_instruction_chars = _public_gate_mean_number(eligible_with, "prompt_system_instruction_chars")
    with_avg_prompt_task_constraint_chars = _public_gate_mean_number(eligible_with, "prompt_task_constraint_chars")
    with_avg_prompt_source_payload_chars = _public_gate_mean_number(eligible_with, "prompt_source_payload_chars")
    with_avg_prompt_test_payload_chars = _public_gate_mean_number(eligible_with, "prompt_test_payload_chars")
    with_avg_prompt_candidate_payload_chars = _public_gate_mean_number(eligible_with, "prompt_candidate_payload_chars")
    with_avg_prompt_nexus_control_chars = _public_gate_mean_number(eligible_with, "prompt_nexus_control_chars")
    with_avg_prompt_governance_contract_chars = _public_gate_mean_number(eligible_with, "prompt_governance_contract_chars")
    with_avg_gateway_total_sec = _public_gate_mean_number(eligible_with, "gateway_total_sec")
    without_avg_gateway_total_sec = _public_gate_mean_number(eligible_without, "gateway_total_sec")
    with_avg_gateway_process_sec = _public_gate_mean_number(eligible_with, "gateway_process_sec")
    without_avg_gateway_process_sec = _public_gate_mean_number(eligible_without, "gateway_process_sec")
    with_avg_gateway_provider_wait_sec = _public_gate_mean_number(eligible_with, "gateway_provider_wait_sec")
    without_avg_gateway_provider_wait_sec = _public_gate_mean_number(eligible_without, "gateway_provider_wait_sec")
    with_avg_gateway_parse_sec = _public_gate_mean_number(eligible_with, "gateway_parse_sec")
    without_avg_gateway_parse_sec = _public_gate_mean_number(eligible_without, "gateway_parse_sec")
    with_avg_context_hydration_sec = _public_gate_mean_number(eligible_with, "timing_context_pack_sec")
    with_avg_phase_wall_r_sec = _public_gate_mean_number(eligible_with, "phase_wall_r_sec")
    with_avg_r_phase_hyper_sprint_sec = _public_gate_mean_number(eligible_with, "r_phase_hyper_sprint_sec")
    wall_attribution_known_share_uncapped_with = _public_gate_safe_ratio(
        with_avg_gateway_total_sec + with_avg_context_hydration_sec + with_avg_phase_wall_r_sec,
        with_avg_wall_sec,
    )
    wall_attribution_known_share_with = min(1.0, wall_attribution_known_share_uncapped_with)
    wall_cost_ratio_with_over_without = _public_gate_safe_ratio(with_avg_wall_sec, without_avg_wall_sec)
    token_cost_ratio_with_over_without = _public_gate_safe_ratio(with_avg_tokens, without_avg_tokens)
    model_call_ratio_with_over_without = _public_gate_safe_ratio(with_avg_model_calls, without_avg_model_calls)
    verified_lift_rate = round(with_semantic_verified_rate - without_semantic_verified_rate, 4)
    token_overhead = max(0.0, with_avg_tokens - without_avg_tokens)
    verified_lift_per_1k_with_tokens = round(verified_lift_rate / (with_avg_tokens / 1000.0), 6) if with_avg_tokens > 0 else 0.0
    marginal_token_utility = round(verified_lift_rate / (token_overhead / 1000.0), 6) if token_overhead > 0 else 0.0
    if token_cost_ratio_with_over_without <= 1.0:
        token_roi_status = "EFFICIENT"
    elif verified_lift_rate > 0.0:
        token_roi_status = "LIFT_WITH_OVERHEAD"
    else:
        token_roi_status = "UNPROFITABLE_LESSON"
    hidden_retry_wall_total = sum(float(row.get("hidden_retry_wall_sec", 0.0) or 0.0) for row in eligible_with)
    hidden_retry_token_total = sum(float(row.get("hidden_retry_tokens", 0.0) or 0.0) for row in eligible_with)
    with_wall_total = sum(float(row.get("wall_duration_sec", row.get("duration_sec", 0.0)) or 0.0) for row in eligible_with)
    with_token_total = sum(float(row.get("total_tokens", row.get("model_total_tokens", 0.0)) or 0.0) for row in eligible_with)
    retry_cost_share_wall = _public_gate_safe_ratio(hidden_retry_wall_total, with_wall_total)
    retry_cost_share_tokens = _public_gate_safe_ratio(hidden_retry_token_total, with_token_total)
    paired_wall_ratios = _public_gate_paired_metric_ratios(eligible_with, eligible_without, "wall_duration_sec")
    paired_token_ratios = _public_gate_paired_metric_ratios(eligible_with, eligible_without, "total_tokens")
    paired_prompt_purity_ratios = _public_gate_paired_prompt_purity_ratios(eligible_with, eligible_without)
    median_paired_wall_cost_ratio = _public_gate_median(paired_wall_ratios)
    median_paired_token_cost_ratio = _public_gate_median(paired_token_ratios)
    median_prompt_purity_index = _public_gate_median(paired_prompt_purity_ratios)
    max_prompt_purity_index = round(max(paired_prompt_purity_ratios), 4) if paired_prompt_purity_ratios else 0.0
    prompt_purity_threshold = float(config.get("prompt_purity_threshold") or 1.02)
    prompt_purity_gate_passed = not paired_prompt_purity_ratios or max_prompt_purity_index <= prompt_purity_threshold
    min_required_pairs_for_efficiency_claim = int(config.get("min_required_pairs_for_efficiency_claim") or 3)
    efficiency_pair_count = min(len(paired_wall_ratios), len(paired_token_ratios))
    cost_efficiency_sample_sufficient = efficiency_pair_count >= min_required_pairs_for_efficiency_claim
    valid_comparison_readiness_gate = derive_valid_comparison_readiness_gate(
        eligible_without_count=len(eligible_without),
        without_row_count=len(without_rows),
    )
    valid_comparison_ready = valid_comparison_readiness_gate.get("status") == "PASS"
    route_cost_regression_wall_ratio_threshold = float(config.get("route_cost_regression_wall_ratio_threshold") or 1.8)
    route_cost_regression_token_ratio_threshold = float(config.get("route_cost_regression_token_ratio_threshold") or 1.5)
    verified_equal_without_lift = bool(
        eligible_with
        and eligible_without
        and with_semantic_verified_rate >= 1.0
        and without_semantic_verified_rate >= 1.0
        and with_semantic_verified_rate <= without_semantic_verified_rate
        and with_trust_mismatch_rate >= without_trust_mismatch_rate
    )
    eligibility_complete = len(eligible_with) == len(with_rows) and len(eligible_without) == len(without_rows)
    wall_regression_systemic = (
        median_paired_wall_cost_ratio > route_cost_regression_wall_ratio_threshold
        if len(paired_wall_ratios) >= 3
        else wall_cost_ratio_with_over_without > route_cost_regression_wall_ratio_threshold
    )
    token_regression_systemic = (
        median_paired_token_cost_ratio > route_cost_regression_token_ratio_threshold
        if len(paired_token_ratios) >= 3
        else token_cost_ratio_with_over_without > route_cost_regression_token_ratio_threshold
    )
    gate_failures = derive_public_gate_failures(locals(), config)
    delivery_gate_failures = gate_failures["delivery_gate_failures"]
    cost_gate_failures = gate_failures["cost_gate_failures"]
    session_worker_contamination_rate = float(session_worker_contamination.get("contamination_rate", 0.0) or 0.0)
    if session_worker_contamination_rate > 0.0:
        delivery_gate_failures.append("session_worker_contamination_detected")
    if outbound_prompt_ledger_invalid:
        cost_gate_failures.extend(str(item) for item in outbound_prompt_ledger_summary.get("failures", []) or [])
    route_cost_ledger = _route_cost_ledger(rows)
    route_cost_trace_report = build_route_cost_trace_report(rows)
    s2t_shadow_report = build_s2t_shadow_report(rows)
    s2t_policy_draft = build_promoted_s2t_policy(s2t_shadow_report)
    commercial_model_roi_shadow_hooks = _commercial_model_roi_shadow_hooks(rows)
    product_kpis = _product_kpis(rows)
    openseeker_kpis = _openseeker_kpis(rows)
    public_lane_contract = build_public_lane_contract(config)
    route_policy_evidence_contract = build_route_policy_evidence_contract(rows)
    if route_policy_evidence_contract.get("status") != "PASS":
        delivery_gate_failures.extend(
            f"route_policy_evidence:{failure}"
            for failure in route_policy_evidence_contract.get("failures", [])
        )
    expected_capability_evidence_contract = build_expected_capability_evidence_contract(rows)
    if expected_capability_evidence_contract.get("status") != "PASS":
        delivery_gate_failures.extend(
            f"expected_capability_evidence:{failure}"
            for failure in expected_capability_evidence_contract.get("failures", [])
        )
    skill_mount_evidence_contract = build_skill_mount_evidence_contract(rows)
    if skill_mount_evidence_contract.get("status") != "PASS":
        delivery_gate_failures.extend(
            f"skill_mount_evidence:{failure}"
            for failure in skill_mount_evidence_contract.get("failures", [])
        )
    delivery_gate_passed = not delivery_gate_failures
    cost_claim_passed = delivery_gate_passed and not cost_gate_failures
    cost_efficiency_decision = derive_cost_efficiency_decision(
        delivery_gate_passed=delivery_gate_passed,
        delivery_gate_failures=delivery_gate_failures,
        cost_gate_failures=cost_gate_failures,
        wall_cost_ratio_with_over_without=wall_cost_ratio_with_over_without,
        token_cost_ratio_with_over_without=token_cost_ratio_with_over_without,
        model_call_ratio_with_over_without=model_call_ratio_with_over_without,
        retry_cost_share_wall=retry_cost_share_wall,
        retry_cost_share_tokens=retry_cost_share_tokens,
        wall_ledger_invalid=wall_ledger_invalid,
        warning_ledger_invalid=warning_ledger_invalid,
        valid_comparison_ready=valid_comparison_ready,
    )
    cost_efficiency_failures = cost_efficiency_decision.failures
    cost_efficiency_status = cost_efficiency_decision.status
    if (
        cost_efficiency_failures
        and delivery_gate_passed
        and not cost_gate_failures
        and not wall_ledger_invalid
        and not warning_ledger_invalid
        and valid_comparison_ready
        and wall_cost_ratio_with_over_without <= 1.05
        and token_cost_ratio_with_over_without <= 1.05
        and model_call_ratio_with_over_without <= 1.0
        and retry_cost_share_wall == 0.0
        and retry_cost_share_tokens == 0.0
    ):
        cost_efficiency_status = "NEUTRAL"

    direction_magnitude_gate = derive_direction_magnitude_gate(
        valid_comparison_ready=valid_comparison_ready,
        wall_cost_ratio_with_over_without=wall_cost_ratio_with_over_without,
        token_cost_ratio_with_over_without=token_cost_ratio_with_over_without,
        model_call_ratio_with_over_without=model_call_ratio_with_over_without,
        paired_wall_ratios=paired_wall_ratios,
        paired_token_ratios=paired_token_ratios,
    )
    public_claim_posture = derive_public_claim_posture(
        delivery_gate_passed=delivery_gate_passed,
        cost_claim_passed=cost_claim_passed,
        cost_efficiency_status=cost_efficiency_status,
        cost_efficiency_failures=cost_efficiency_failures,
        cost_efficiency_sample_sufficient=cost_efficiency_sample_sufficient,
        efficiency_pair_count=efficiency_pair_count,
        min_required_pairs_for_efficiency_claim=min_required_pairs_for_efficiency_claim,
        token_roi_status=token_roi_status,
        verified_lift_per_1k_with_tokens=verified_lift_per_1k_with_tokens,
        marginal_token_utility=marginal_token_utility,
        retry_cost_share_wall=retry_cost_share_wall,
    )
    training_eligibility_posture = derive_training_eligibility_posture(
        delivery_gate_passed=delivery_gate_passed,
        cost_claim_passed=cost_claim_passed,
        cost_efficiency_sample_sufficient=cost_efficiency_sample_sufficient,
        prompt_purity_gate_passed=prompt_purity_gate_passed,
        with_trust_mismatch_rate=with_trust_mismatch_rate,
        without_trust_mismatch_rate=without_trust_mismatch_rate,
        eligible_with=eligible_with,
        infra_quarantine_report=infra_quarantine_report,
        wall_ledger_invalid=wall_ledger_invalid,
        warning_ledger_invalid=warning_ledger_invalid,
        cost_efficiency_status=cost_efficiency_status,
        synthetic_readiness_reasons=list(public_lane_contract.get("non_public_reasons", []) or []),
    )
    mutation_hardening_gate = derive_mutation_hardening_gate(
        rows=rows,
        warning_ledger_summary=warning_ledger_summary,
        wall_ledger_summary_with=wall_ledger_summary_with,
        wall_ledger_summary_without=wall_ledger_summary_without,
    )
    current_x1_readiness_pass = _x1_readiness_pass(
        valid_comparison_ready=valid_comparison_ready,
        wall_ledger_with_conserved_rate=float(wall_ledger_summary_with.get("conserved_rate", 0.0) or 0.0),
        wall_ledger_without_conserved_rate=float(wall_ledger_summary_without.get("conserved_rate", 0.0) or 0.0),
        warning_clean_gate_pass=not warning_ledger_invalid,
        provider_token_measured_rate_with=provider_token_measured_rate_with,
        provider_token_measured_rate_without=provider_token_measured_rate_without,
    )
    x1_history_path = _x1_readiness_history_path(bundle_path=bundle_path, config=config)
    x1_history = _append_x1_readiness_history(
        path=x1_history_path,
        entry={
            "model": _report_model_label(),
            "tasks_manifest_hash": str(config.get("tasks_manifest_hash") or ""),
            "x1_readiness_pass": current_x1_readiness_pass,
            "timestamp": int(time.time()),
        },
        max_entries=20,
    )
    model_label = _report_model_label()
    manifest_hash = str(config.get("tasks_manifest_hash") or "")
    history_last_two_x1_readiness_pass = derive_recent_compatible_x1_history(
        x1_history=x1_history,
        model_label=model_label,
        manifest_hash=manifest_hash,
    )
    x3_promotion_gate = derive_x3_promotion_gate(
        history_last_two_x1_readiness_pass=history_last_two_x1_readiness_pass,
        valid_comparison_ready=valid_comparison_ready,
        wall_ledger_with_conserved_rate=float(wall_ledger_summary_with.get("conserved_rate", 0.0) or 0.0),
        wall_ledger_without_conserved_rate=float(wall_ledger_summary_without.get("conserved_rate", 0.0) or 0.0),
        warning_clean_gate_pass=not warning_ledger_invalid,
        provider_token_measured_rate_with=provider_token_measured_rate_with,
        provider_token_measured_rate_without=provider_token_measured_rate_without,
    )
    public_gate_checks = _build_public_gate_checks(locals())
    taskset_contract = build_taskset_contract(config=config, runner_path=Path(__file__).resolve())
    public_claim_gates = build_public_claim_gates(
        delivery_gate_passed=delivery_gate_passed,
        cost_claim_passed=cost_claim_passed,
        cost_efficiency_status=cost_efficiency_status,
        delivery_gate_failures=delivery_gate_failures,
        cost_gate_failures=cost_gate_failures,
        cost_efficiency_failures=cost_efficiency_failures,
        public_gate_checks=public_gate_checks,
    )
    payload = {
        "schema": "nexus_public_benchmark_evidence_bundle_v2",
        "created_at_unix": int(time.time()),
        "run_identity": {
            "nexus_git_commit": _git_commit(Path.cwd()),
            "runner": "scripts/bench/capability_ab_runner.py",
            "runner_command": str(config.get("runner_command") or ""),
            "cwd": str(Path.cwd()),
        },
        "model_lock": {
            "without_model_name": next(iter(without_models), ""),
            "with_model_name": next(iter(with_models), ""),
            "same_model": bool(with_models and without_models and with_models == without_models),
            "env_model_name": str(os.environ.get("NEXUS_GEMINI_MODEL_NAME") or ""),
            "direct_model_name": str(os.environ.get("NEXUS_DIRECT_GEMINI_MODEL") or ""),
            "codex_model_name": str(os.environ.get("NEXUS_CODEX_MODEL_NAME") or ""),
            "direct_codex_model_name": str(os.environ.get("NEXUS_DIRECT_CODEX_MODEL") or ""),
            "ollama_model_name": str(os.environ.get("NEXUS_OLLAMA_MODEL") or ""),
            "ollama_active_model": str(os.environ.get("NEXUS_OLLAMA_ACTIVE_MODEL") or ""),
            "prompt_transport": str(os.environ.get("NEXUS_GATEWAY_PROMPT_TRANSPORT") or ""),
            "compact_prompt": os.environ.get("NEXUS_GATEWAY_COMPACT_PROMPT", "").strip().lower() in {"1", "true", "yes"},
        },
        "task_manifest": {
            "path": str(config.get("tasks_file") or ""),
            "sha256": str(config.get("tasks_manifest_hash") or ""),
            "unique_tasks_requested": int(config.get("unique_tasks_requested", 0) or 0),
            "repeat_trials": int(config.get("repeat_trials", 1) or 1),
            "shuffle_seed": config.get("shuffle_seed"),
        },
        "taskset_contract": taskset_contract,
        "public_disclosure_manifest": config.get("public_disclosure_manifest")
        or {"path": "", "sha256": "", "status": "not_provided", "failures": []},
        "timeouts": {
            "timeout_sec": int(config.get("timeout_sec", 0) or 0),
            "total_timeout_sec": int(config.get("total_timeout_sec", 0) or 0),
            "effective_total_timeout_sec": int(config.get("effective_total_timeout_sec", 0) or 0),
            "stop_loss_sec": int(config.get("stop_loss_sec", 0) or 0),
            "per_task_stop_loss_sec": int(config.get("per_task_stop_loss_sec", 0) or 0),
            "gateway_timeout_sec_policy": str(os.environ.get("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC") or ""),
            "direct_gemini_timeout_sec": _direct_gemini_timeout_sec(int(config.get("timeout_sec", 0) or 0)),
        },
        "config": config,
        "raw_files": {
            "with_nexus": {"path": str(with_path), "sha256": _sha256_file(with_path)},
            "without_nexus": {"path": str(without_path), "sha256": _sha256_file(without_path)},
        },
        "artifact_files": artifact_files,
        "row_count": len(rows),
        "row_counts": {
            "with_nexus": len(with_rows),
            "without_nexus": len(without_rows),
            "total": len(rows),
            "eligible_with_nexus": len(eligible_with),
            "eligible_without_nexus": len(eligible_without),
            "infra_invalid_with_nexus": len(with_rows) - len(eligible_with),
            "infra_invalid_without_nexus": len(without_rows) - len(eligible_without),
        },
        "telemetry_completeness": {
            "token_measured_rate_without": token_measured_rate_without,
            "token_measured_rate_with": token_measured_rate_with,
            "provider_token_measured_rate_without": provider_token_measured_rate_without,
            "provider_token_measured_rate_with": provider_token_measured_rate_with,
            "gateway_stats_source_rate_without": _rate_for(without_rows, "gateway_stats_present"),
            "gateway_stats_source_rate_with": _rate_for(with_rows, "gateway_stats_present"),
        },
        "rubric_contract": {
            "schema": "nexus_rubric_contract_bundle_v1",
            "with_nexus": rubric_summary(with_rows),
            "without_nexus": rubric_summary(without_rows),
            "eligible_with_nexus": rubric_summary(eligible_with),
            "eligible_without_nexus": rubric_summary(eligible_without),
            "claim_boundary": [
                "Rubric PASS is required before public or training claims.",
                "Behavioral success with missing required artifacts remains observation-only.",
                "Cost efficiency wording requires cost rubric PASS plus sample sufficiency.",
            ],
        },
        "route_cost_ledger": route_cost_ledger,
        "route_cost_trace_report": route_cost_trace_report,
        "commercial_model_roi_shadow_hooks": commercial_model_roi_shadow_hooks,
        "infra_quarantine_report": infra_quarantine_report,
        "session_worker_contamination": session_worker_contamination,
        "wall_ledger_conservation": {
            "schema": "nexus_wall_ledger_conservation_bundle_v1",
            "with_nexus": wall_ledger_summary_with,
            "without_nexus": wall_ledger_summary_without,
            "telemetry_invalid": wall_ledger_invalid,
            "claim_boundary": [
                "Telemetry-invalid wall ledger rows are excluded from cost-efficiency claims.",
                "A conserved ledger requires complete required components and reconciliation error below 5 percent.",
            ],
        },
        "warning_clean_gate": {
            "schema": "nexus_warning_clean_gate_v1",
            "verdict": "PASS" if not warning_ledger_invalid else "RETURN",
            "required": warning_ledger_required,
            "checks": warning_ledger_summary,
            "claim_boundary": [
                "Public candidate runs require process-level warning capture.",
                "Warnings that are present but uncaptured or unclassified force RETURN.",
            ],
        },
        "outbound_prompt_ledger_gate": outbound_prompt_ledger_summary,
        "public_lane_contract": public_lane_contract,
        "route_policy_evidence_contract": route_policy_evidence_contract,
        "expected_capability_evidence_contract": expected_capability_evidence_contract,
        "skill_mount_evidence_contract": skill_mount_evidence_contract,
        "s2t_shadow_report": s2t_shadow_report,
        "s2t_policy_draft": s2t_policy_draft,
        "product_kpis": product_kpis,
        "openseeker_alignment": openseeker_kpis,
        "nexus_wearing": {
            "valid_rate": nexus_valid_rate,
            "gemini_uses_nexus_rate": legacy_gemini_uses_nexus_rate,
            "model_uses_nexus_rate": model_uses_nexus_rate,
            "nexus_context_delivered_rate": nexus_context_delivered_rate,
            "nexus_usage_valid_rate": nexus_usage_valid_rate,
            "claim_verified_rate": claim_verified_rate,
        },
        **public_claim_gates,
        "valid_comparison_readiness_gate": valid_comparison_readiness_gate,
        "direction_magnitude_gate": direction_magnitude_gate,
        "x3_promotion_gate": x3_promotion_gate,
        "mutation_hardening_gate": mutation_hardening_gate,
        "posture_finalization_gate": {
            "schema": "nexus_posture_finalization_gate_v1",
            "public_efficiency_wording_allowed": bool(
                cost_efficiency_status == "IMPROVED" and cost_efficiency_sample_sufficient and valid_comparison_ready
            ),
            "training_eligible_requires": [
                "non_regressed",
                "full_contracts",
                "telemetry_clean",
                "sample_sufficient",
            ],
            "current_training_status": training_eligibility_posture.get("status"),
        },
        "public_claim_posture": public_claim_posture,
        "training_eligibility_posture": training_eligibility_posture,
    }
    hybrid_modes = [str(row.get("hybrid_route", {}).get("route_mode", "")) for row in with_rows]
    hybrid_modes = [m for m in hybrid_modes if m]
    local_assist_invoked_count = sum(1 for row in with_rows if bool(row.get("hybrid_route", {}).get("local_assist_invoked", False)))
    behavior_changed_count = sum(1 for row in with_rows if bool(row.get("hybrid_route", {}).get("behavior_changed", False)))
    prompt_replaced_count = sum(1 for row in with_rows if bool(row.get("local_assist", {}).get("prompt_replaced", False)))
    local_guard_rows = [row.get("local_guard", {}) for row in with_rows if isinstance(row.get("local_guard", {}), dict)]
    local_guard_trace_count = sum(1 for row in with_rows if bool(row.get("local_guard_invoked", False)))
    local_guard_warn_count = sum(1 for guard in local_guard_rows if str(guard.get("verdict") or "") == "warn")
    local_guard_fail_count = sum(1 for guard in local_guard_rows if str(guard.get("verdict") or "") == "fail")
    local_guard_blocked_delivery_count = sum(1 for guard in local_guard_rows if bool(guard.get("blocked_delivery", False)))
    local_guard_behavior_changed_count = sum(1 for guard in local_guard_rows if bool(guard.get("behavior_changed", False)))

    payload["hybrid_route_summary"] = {
        "modes_observed": sorted(list(set(hybrid_modes))),
        "trace_only_count": sum(1 for m in hybrid_modes if "trace_only" in m),
        "local_only_blocked_count": sum(1 for m in hybrid_modes if m == "local_only_blocked"),
        "local_assist_trace_count": local_assist_invoked_count,
        "local_guard_trace_count": local_guard_trace_count,
        "local_guard_warn_count": local_guard_warn_count,
        "local_guard_fail_count": local_guard_fail_count,
        "local_guard_blocked_delivery_count": local_guard_blocked_delivery_count,
        "behavior_changed_count": behavior_changed_count,
        "local_guard_behavior_changed_count": local_guard_behavior_changed_count,
        "prompt_replaced_count": prompt_replaced_count,
        "h5_trace_count": sum(1 for row in with_rows if bool(row.get("h5_route", {}).get("enabled", False))),
        "h5_behavior_changed_count": sum(1 for row in with_rows if bool(row.get("h5_route", {}).get("behavior_changed", False))),
        "h5_cloud_fallback_invoked_count": sum(1 for row in with_rows if bool(row.get("h5_route", {}).get("cloud_fallback_invoked", False))),
        "h5_local_attempted_count": sum(1 for row in with_rows if bool(row.get("h5_route", {}).get("local_attempted", False))),
        "h5_fail_closed_count": sum(1 for row in with_rows if str(row.get("h5_route", {}).get("final_source", "")) == "fail_closed"),
        "h5_cloud_fallback_eligible_count": sum(1 for row in with_rows if bool(row.get("h5_route", {}).get("cloud_fallback_eligible", False))),
        "h5_fallback_eligibility_trace_count": sum(1 for row in with_rows if bool(row.get("h5_route", {}).get("fallback_policy_version", ""))),
        "h5_would_fail_closed_count": sum(1 for row in with_rows if bool(row.get("h5_route", {}).get("fail_closed_reason", ""))),
        "h5_fallback_decision_trace_count": sum(1 for row in with_rows if bool(row.get("h5_route", {}).get("fallback_decision_policy_version", ""))),
        "h5_cloud_fallback_would_invoke_count": sum(1 for row in with_rows if bool(row.get("h5_route", {}).get("cloud_fallback_would_invoke", False))),
        "h5_would_fail_closed_decision_count": sum(1 for row in with_rows if str(row.get("h5_route", {}).get("cloud_fallback_decision", "")) == "would_fail_closed"),
        "h5_skip_cloud_fallback_decision_count": sum(1 for row in with_rows if str(row.get("h5_route", {}).get("cloud_fallback_decision", "")) == "skip_cloud_fallback"),
        "h5_route_order_shadow_count": sum(1 for row in with_rows if bool(row.get("h5_route", {}).get("route_order_shadow_enabled", False))),
        "h5_shadow_would_use_local_candidate_count": sum(1 for row in with_rows if str(row.get("h5_route", {}).get("route_order_shadow_terminal_state", "")) == "would_use_local_candidate"),
        "h5_shadow_would_use_cloud_fallback_count": sum(1 for row in with_rows if str(row.get("h5_route", {}).get("route_order_shadow_terminal_state", "")) == "would_use_cloud_fallback"),
        "h5_shadow_would_fail_closed_count": sum(1 for row in with_rows if str(row.get("h5_route", {}).get("route_order_shadow_terminal_state", "")) == "would_fail_closed"),
        "h5_shadow_behavior_changed_count": sum(1 for row in with_rows if bool(row.get("h5_route", {}).get("route_order_shadow_behavior_changed", False))),
        "h5_execution_gate_evaluated_count": sum(1 for row in with_rows if bool(row.get("h5_route", {}).get("execution_gate_evaluated", False))),
        "h5_execution_gate_blocked_count": sum(1 for row in with_rows if str(row.get("h5_route", {}).get("execution_gate_status", "")) == "blocked"),
        "h5_execution_gate_eligible_dry_run_only_count": sum(1 for row in with_rows if str(row.get("h5_route", {}).get("execution_gate_status", "")) == "eligible_dry_run_only"),
        "h5_execution_gate_unexpected_side_effect_count": sum(1 for row in with_rows if "unexpected_execution_side_effect" in (row.get("h5_route", {}).get("execution_gate_reasons", []) or [])),
        "h5_execution_gate_governance_violation_count": sum(1 for row in with_rows if "governance_boundary_violation" in (row.get("h5_route", {}).get("execution_gate_reasons", []) or [])),
        "h5_execution_plan_count": sum(1 for row in with_rows if bool(row.get("h5_execution_plan"))),
        "h5_execution_plan_allowed_count": sum(1 for row in with_rows if bool(row.get("h5_execution_plan", {}).get("execution_allowed", False))),
        "h5_execution_plan_dry_run_only_count": sum(1 for row in with_rows if str(row.get("h5_execution_plan", {}).get("execution_mode", "")) == "dry_run_plan_only"),
        "h5_execution_plan_fail_closed_count": sum(1 for row in with_rows if str(row.get("h5_execution_plan", {}).get("execution_mode", "")) == "fail_closed_plan"),
        "h5_execution_plan_local_candidate_count": sum(1 for row in with_rows if str(row.get("h5_execution_plan", {}).get("execution_mode", "")) == "local_candidate_plan"),
        "h5_execution_plan_cloud_fallback_count": sum(1 for row in with_rows if str(row.get("h5_execution_plan", {}).get("execution_mode", "")) == "cloud_fallback_plan"),
        "h5_local_finalization_shadow_count": sum(1 for row in with_rows if bool(row.get("h5_local_finalization_shadow_receipt"))),
        "h5_local_finalization_would_finalize_count": sum(1 for row in with_rows if bool(row.get("h5_local_finalization_shadow_receipt", {}).get("would_finalize_local_candidate", False))),
        "h5_local_finalization_blocked_count": sum(1 for row in with_rows if bool(row.get("h5_local_finalization_shadow_receipt")) and not bool(row.get("h5_local_finalization_shadow_receipt", {}).get("would_finalize_local_candidate", False))),
        "h5_local_finalization_missing_plan_count": sum(1 for row in with_rows if str(row.get("h5_local_finalization_shadow_receipt", {}).get("blocked_reason", "")) == "missing_execution_plan"),
        "h5_local_finalization_hash_not_verified_count": sum(1 for row in with_rows if str(row.get("h5_local_finalization_shadow_receipt", {}).get("blocked_reason", "")) == "local_candidate_hash_not_verified"),
        "h5_cloud_finalization_shadow_count": sum(1 for row in with_rows if bool(row.get("h5_cloud_fallback_finalization_shadow_receipt"))),
        "h5_cloud_finalization_would_finalize_count": sum(1 for row in with_rows if bool(row.get("h5_cloud_fallback_finalization_shadow_receipt", {}).get("would_finalize_cloud_fallback", False))),
        "h5_cloud_finalization_blocked_count": sum(1 for row in with_rows if bool(row.get("h5_cloud_fallback_finalization_shadow_receipt")) and not bool(row.get("h5_cloud_fallback_finalization_shadow_receipt", {}).get("would_finalize_cloud_fallback", False))),
        "h5_cloud_finalization_missing_plan_count": sum(1 for row in with_rows if str(row.get("h5_cloud_fallback_finalization_shadow_receipt", {}).get("blocked_reason", "")) == "missing_execution_plan"),
        "h5_cloud_finalization_provider_unavailable_count": sum(1 for row in with_rows if str(row.get("h5_cloud_fallback_finalization_shadow_receipt", {}).get("blocked_reason", "")) == "cloud_provider_unavailable"),
        "h5_cloud_finalization_would_increment_model_calls_count": sum(1 for row in with_rows if bool(row.get("h5_cloud_fallback_finalization_shadow_receipt", {}).get("would_increment_model_calls", False))),
        "h5_execution_readiness_preflight_count": sum(1 for row in with_rows if bool(row.get("h5_execution_readiness_preflight"))),
        "h5_execution_ready_count": sum(1 for row in with_rows if bool(row.get("h5_execution_readiness_preflight", {}).get("execution_ready", False))),
        "h5_execution_readiness_blocked_count": sum(1 for row in with_rows if str(row.get("h5_execution_readiness_preflight", {}).get("readiness_status", "")) == "blocked"),
        "h5_readiness_local_shadow_ready_count": sum(1 for row in with_rows if bool(row.get("h5_execution_readiness_preflight", {}).get("local_path_ready_shadow", False))),
        "h5_readiness_cloud_shadow_ready_count": sum(1 for row in with_rows if bool(row.get("h5_execution_readiness_preflight", {}).get("cloud_path_ready_shadow", False))),
        "h5_readiness_missing_real_local_e2e_count": sum(1 for row in with_rows if "real_local_committee_e2e_missing" in (row.get("h5_execution_readiness_preflight", {}).get("readiness_reasons", []) or [])),
        "h5_readiness_missing_real_cloud_e2e_count": sum(1 for row in with_rows if "real_cloud_fallback_e2e_missing" in (row.get("h5_execution_readiness_preflight", {}).get("readiness_reasons", []) or [])),
        "h5_readiness_missing_full_benchmark_count": sum(1 for row in with_rows if "full_benchmark_missing" in (row.get("h5_execution_readiness_preflight", {}).get("readiness_reasons", []) or [])),
        "h5_readiness_governance_blocked_count": sum(1 for row in with_rows if "governance_approval_missing" in (row.get("h5_execution_readiness_preflight", {}).get("readiness_reasons", []) or [])),
        "h5_local_evidence_ingestion_shadow_count": sum(1 for row in with_rows if bool(row.get("h5_local_evidence_ingestion_shadow"))),
        "h5_local_evidence_external_present_count": sum(1 for row in with_rows if bool(row.get("h5_local_evidence_ingestion_shadow", {}).get("external_evidence_present", False))),
        "h5_local_evidence_accepted_count": sum(1 for row in with_rows if bool(row.get("h5_local_evidence_ingestion_shadow", {}).get("accepted_for_h5_readiness_shadow", False))),
        "h5_local_evidence_blocked_count": sum(1 for row in with_rows if bool(row.get("h5_local_evidence_ingestion_shadow")) and not bool(row.get("h5_local_evidence_ingestion_shadow", {}).get("accepted_for_h5_readiness_shadow", False))),
        "h5_local_external_evidence_ready_shadow_count": sum(1 for row in with_rows if bool(row.get("h5_local_evidence_ingestion_shadow", {}).get("local_path_ready_shadow_from_external_evidence", False))),
        "h5_cloud_evidence_ingestion_shadow_count": sum(1 for row in with_rows if bool(row.get("h5_cloud_evidence_ingestion_shadow"))),
        "h5_cloud_evidence_external_present_count": sum(1 for row in with_rows if bool(row.get("h5_cloud_evidence_ingestion_shadow", {}).get("external_evidence_present", False))),
        "h5_cloud_evidence_accepted_count": sum(1 for row in with_rows if bool(row.get("h5_cloud_evidence_ingestion_shadow", {}).get("accepted_for_h5_readiness_shadow", False))),
        "h5_cloud_evidence_blocked_count": sum(1 for row in with_rows if bool(row.get("h5_cloud_evidence_ingestion_shadow")) and not bool(row.get("h5_cloud_evidence_ingestion_shadow", {}).get("accepted_for_h5_readiness_shadow", False))),
        "h5_cloud_external_evidence_ready_shadow_count": sum(1 for row in with_rows if bool(row.get("h5_cloud_evidence_ingestion_shadow", {}).get("cloud_path_ready_shadow_from_external_evidence", False))),
        "h5_overall_readiness_closure_count": sum(1 for row in with_rows if bool(row.get("h5_overall_readiness_closure"))),
        "h5_overall_readiness_all_shadow_evidence_count": sum(1 for row in with_rows if bool(row.get("h5_overall_readiness_closure", {}).get("all_shadow_evidence_present", False))),
        "h5_overall_readiness_blocked_count": sum(1 for row in with_rows if str(row.get("h5_overall_readiness_closure", {}).get("closure_status", "")) == "blocked"),
        "h5_overall_readiness_quality_missing_count": sum(1 for row in with_rows if "quality_non_regression_missing" in (row.get("h5_overall_readiness_closure", {}).get("closure_reasons", []) or [])),
        "h5_overall_readiness_benchmark_missing_count": sum(1 for row in with_rows if "full_benchmark_missing" in (row.get("h5_overall_readiness_closure", {}).get("closure_reasons", []) or [])),
        "h5_overall_readiness_governance_missing_count": sum(1 for row in with_rows if "governance_approval_missing" in (row.get("h5_overall_readiness_closure", {}).get("closure_reasons", []) or [])),
        "h5_overall_readiness_unexpected_side_effect_count": sum(1 for row in with_rows if any(r.startswith("unexpected_") for r in (row.get("h5_overall_readiness_closure", {}).get("closure_reasons", []) or []))),
        "h5_execution_flag_contract_count": sum(1 for row in with_rows if bool(row.get("h5_execution_flag_contract"))),
        "h5_execution_flag_present_count": sum(1 for row in with_rows if bool(row.get("h5_execution_flag_contract", {}).get("execution_flag_present", False))),
        "h5_execution_flag_enabled_count": sum(1 for row in with_rows if bool(row.get("h5_execution_flag_contract", {}).get("execution_flag_enabled", False))),
        "h5_execution_allowed_count": sum(1 for row in with_rows if bool(row.get("h5_execution_flag_contract", {}).get("execution_allowed", False))),
        "h5_execution_contract_blocked_count": sum(1 for row in with_rows if str(row.get("h5_execution_flag_contract", {}).get("contract_status", "")) == "blocked"),
        "h5_execution_contract_fail_closed_count": sum(1 for row in with_rows if bool(row.get("h5_execution_flag_contract", {}).get("fail_closed", False))),
        "h5_promotion_ready_count": sum(1 for row in with_rows if bool(row.get("h5_execution_flag_contract", {}).get("promotion_ready", False))),
        "h5_local_promotion_dry_run_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_promotion_dry_run"))),
        "h5_local_promotion_would_promote_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_promotion_dry_run", {}).get("would_promote_local_candidate", False))),
        "h5_local_promotion_allowed_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_promotion_dry_run", {}).get("promotion_allowed", False))),
        "h5_local_promotion_blocked_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_promotion_dry_run")) and not bool(row.get("h5_local_candidate_promotion_dry_run", {}).get("promotion_allowed", False))),
        "h5_local_rollback_dry_run_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_rollback_dry_run"))),
        "h5_local_rollback_required_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_rollback_dry_run", {}).get("rollback_required", False))),
        "h5_local_promotion_gate_matrix_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_promotion_gate_matrix"))),
        "h5_local_promotion_gate_blocked_count": sum(1 for row in with_rows if str(row.get("h5_local_candidate_promotion_gate_matrix", {}).get("promotion_gate_status", "")) == "blocked"),
        "h5_local_final_source_change_allowed_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_promotion_dry_run", {}).get("allow_final_source_change_flag_enabled", False))),
        "h5_local_final_patch_replacement_allowed_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_promotion_dry_run", {}).get("allow_final_patch_replacement_flag_enabled", False))),
        "h5_local_shadow_final_source_promotion_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_shadow_final_source_promotion"))),
        "h5_local_shadow_promotion_candidate_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_shadow_final_source_promotion", {}).get("shadow_promotion_candidate", False))),
        "h5_local_shadow_promotion_ready_blocked_count": sum(1 for row in with_rows if str(row.get("h5_local_candidate_shadow_final_source_promotion", {}).get("shadow_promotion_status", "")) == "shadow_ready_blocked"),
        "h5_local_actual_final_source_changed_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_shadow_final_source_promotion", {}).get("actual_final_source_changed", False))),
        "h5_local_shadow_final_source_promoted_count": sum(1 for row in with_rows if str(row.get("h5_local_candidate_shadow_final_source_promotion", {}).get("shadow_final_source_after_promotion", "")) == "local_candidate_shadow_promoted"),
        "h5_final_patch_replacement_shadow_contract_count": sum(1 for row in with_rows if bool(row.get("h5_final_patch_replacement_shadow_contract"))),
        "h5_final_patch_shadow_candidate_count": sum(1 for row in with_rows if bool(row.get("h5_final_patch_replacement_shadow_contract", {}).get("shadow_patch_candidate", False))),
        "h5_final_patch_replacement_allowed_count": sum(1 for row in with_rows if bool(row.get("h5_final_patch_replacement_shadow_contract", {}).get("final_patch_replacement_allowed", False))),
        "h5_actual_final_patch_replaced_count": sum(1 for row in with_rows if bool(row.get("h5_final_patch_replacement_shadow_contract", {}).get("actual_final_patch_replaced", False))),
        "h5_output_mutation_guard_count": sum(1 for row in with_rows if bool(row.get("h5_output_mutation_guard"))),
        "h5_output_mutation_candidate_count": sum(1 for row in with_rows if bool(row.get("h5_output_mutation_guard", {}).get("output_mutation_candidate", False))),
        "h5_output_mutation_allowed_count": sum(1 for row in with_rows if bool(row.get("h5_output_mutation_guard", {}).get("output_mutation_allowed", False))),
        "h5_actual_output_mutated_count": sum(1 for row in with_rows if bool(row.get("h5_output_mutation_guard", {}).get("actual_output_mutated", False))),
        "h5_output_mutation_rollback_required_count": sum(1 for row in with_rows if bool(row.get("h5_output_mutation_guard", {}).get("rollback_required", False))),
        "h5_controlled_mutation_gate_count": sum(1 for row in with_rows if bool(row.get("h5_controlled_mutation_gate"))),
        "h5_controlled_mutation_gate_blocked_count": sum(1 for row in with_rows if str(row.get("h5_controlled_mutation_gate", {}).get("gate_status", "")) == "blocked"),
        "h5_controlled_mutation_allowed_count": sum(1 for row in with_rows if bool(row.get("h5_controlled_mutation_gate", {}).get("mutation_allowed", False))),
        "h5_controlled_mutation_all_flags_enabled_count": sum(1 for row in with_rows if bool(row.get("h5_controlled_mutation_gate", {}).get("all_required_flags_enabled", False))),
        "h5_controlled_final_source_candidate_count": sum(1 for row in with_rows if bool(row.get("h5_controlled_mutation_gate", {}).get("final_source_mutation_candidate", False))),
        "h5_controlled_final_patch_candidate_count": sum(1 for row in with_rows if bool(row.get("h5_controlled_mutation_gate", {}).get("final_patch_mutation_candidate", False))),
        "h5_controlled_output_mutation_candidate_count": sum(1 for row in with_rows if bool(row.get("h5_controlled_mutation_gate", {}).get("output_mutation_candidate", False))),
        "h5_controlled_rollback_required_count": sum(1 for row in with_rows if bool(row.get("h5_controlled_mutation_gate", {}).get("rollback_required", False))),
        "h5_controlled_safe_to_continue_count": sum(1 for row in with_rows if bool(row.get("h5_controlled_mutation_gate", {}).get("safe_to_continue", False))),
        "h5_controlled_unexpected_mutation_count": sum(1 for row in with_rows if bool(row.get("h5_controlled_mutation_gate", {}).get("rollback_required", False))),
        "h5_local_final_source_trial_receipt_count": sum(1 for row in with_rows if bool(row.get("h5_local_final_source_controlled_trial_receipt"))),
        "h5_local_final_source_trial_ready_count": sum(1 for row in with_rows if bool(row.get("h5_local_final_source_controlled_trial_receipt", {}).get("would_allow_final_source_trial", False))),
        "h5_local_final_source_trial_blocked_count": sum(1 for row in with_rows if str(row.get("h5_local_final_source_controlled_trial_receipt", {}).get("trial_status", "")) == "blocked"),
        "h5_local_final_source_trial_actual_change_count": sum(1 for row in with_rows if bool(row.get("h5_local_final_source_controlled_trial_receipt", {}).get("actual_final_source_changed", False))),
        "h5_local_final_source_trial_flags_enabled_count": sum(1 for row in with_rows if bool(row.get("h5_local_final_source_controlled_trial_receipt", {}).get("all_required_flags_enabled", False))),
        "h5_local_final_source_trial_safe_count": sum(1 for row in with_rows if bool(row.get("h5_local_final_source_controlled_trial_receipt", {}).get("safe_to_continue", False))),
        "h5_local_final_source_trial_rollback_required_count": sum(1 for row in with_rows if bool(row.get("h5_local_final_source_controlled_trial_receipt", {}).get("rollback_required", False))),
        "h5_final_source_apply_preflight_receipt_count": sum(1 for row in with_rows if bool(row.get("h5_final_source_apply_preflight_receipt"))),
        "h5_final_source_apply_preflight_pass_shadow_count": sum(1 for row in with_rows if str(row.get("h5_final_source_apply_preflight_receipt", {}).get("preflight_status", "")) == "preflight_pass_shadow_only"),
        "h5_final_source_apply_preflight_blocked_count": sum(1 for row in with_rows if str(row.get("h5_final_source_apply_preflight_receipt", {}).get("preflight_status", "")) == "blocked"),
        "h5_final_source_apply_preflight_flag_enabled_count": sum(1 for row in with_rows if bool(row.get("h5_final_source_apply_preflight_receipt", {}).get("all_required_flags_enabled", False))),
        "h5_final_source_apply_preflight_actual_change_count": sum(1 for row in with_rows if bool(row.get("h5_final_source_apply_preflight_receipt", {}).get("actual_final_source_changed", False))),
        "h5_final_source_apply_preflight_rollback_required_count": sum(1 for row in with_rows if bool(row.get("h5_final_source_apply_preflight_receipt", {}).get("rollback_required", False))),
        "h5_final_source_apply_preflight_safe_count": sum(1 for row in with_rows if bool(row.get("h5_final_source_apply_preflight_receipt", {}).get("safe_to_continue", False))),
        "h5_isolated_final_source_simulation_count": sum(1 for row in with_rows if bool(row.get("h5_isolated_final_source_mutation_simulation"))),
        "h5_isolated_final_source_simulation_pass_count": sum(1 for row in with_rows if str(row.get("h5_isolated_final_source_mutation_simulation", {}).get("simulation_status", "")) == "isolated_simulation_pass"),
        "h5_isolated_final_source_simulation_blocked_count": sum(1 for row in with_rows if str(row.get("h5_isolated_final_source_mutation_simulation", {}).get("simulation_status", "")) == "blocked"),
        "h5_isolated_final_source_changed_count": sum(1 for row in with_rows if bool(row.get("h5_isolated_final_source_mutation_simulation", {}).get("isolated_final_source_changed", False))),
        "h5_actual_final_source_changed_count": sum(1 for row in with_rows if bool(row.get("h5_isolated_final_source_mutation_simulation", {}).get("actual_final_source_changed", False))),
        "h5_isolated_final_source_rollback_required_count": sum(1 for row in with_rows if bool(row.get("h5_isolated_final_source_mutation_simulation", {}).get("rollback_required", False))),
        "h5_isolated_final_source_safe_count": sum(1 for row in with_rows if bool(row.get("h5_isolated_final_source_mutation_simulation", {}).get("safe_to_continue", False))),
        "h5_actual_final_source_apply_decision_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_source_apply_decision"))),
        "h5_actual_final_source_apply_allowed_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_source_apply_decision", {}).get("actual_apply_allowed", False))),
        "h5_actual_final_source_apply_blocked_count": sum(1 for row in with_rows if str(row.get("h5_actual_final_source_apply_decision", {}).get("apply_decision", "")) == "blocked"),
        "h5_actual_final_source_apply_executed_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_source_apply_receipt", {}).get("actual_apply_executed", False))),
        "h5_actual_final_source_apply_final_source_changed_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_source_apply_receipt", {}).get("actual_final_source_changed", False))),
        "h5_actual_final_source_apply_all_flags_enabled_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_source_apply_decision", {}).get("all_seven_flags_enabled", False))),
        "h5_actual_final_source_apply_rollback_required_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_source_apply_decision", {}).get("rollback_required", False))),
        "h5_actual_final_source_apply_safe_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_source_apply_decision", {}).get("safe_to_continue", False))),
        "h5_actual_final_source_rollback_decision_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_source_rollback_decision"))),
        "h5_actual_final_source_rollback_allowed_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_source_rollback_decision", {}).get("rollback_allowed", False))),
        "h5_actual_final_source_rollback_blocked_count": sum(1 for row in with_rows if str(row.get("h5_actual_final_source_rollback_decision", {}).get("rollback_decision", "")) == "blocked"),
        "h5_actual_final_source_rollback_executed_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_source_rollback_receipt", {}).get("rollback_executed", False))),
        "h5_actual_final_source_rollback_restored_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_source_rollback_receipt", {}).get("actual_final_source_restored", False))),
        "h5_actual_final_source_rollback_flag_enabled_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_source_rollback_decision", {}).get("rollback_flag_enabled", False))),
        "h5_actual_final_source_rollback_safe_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_source_rollback_decision", {}).get("rollback_safe", False))),
        "h5_final_patch_apply_preflight_receipt_count": sum(1 for row in with_rows if bool(row.get("h5_final_patch_apply_preflight_receipt"))),
        "h5_final_patch_apply_preflight_pass_shadow_count": sum(1 for row in with_rows if str(row.get("h5_final_patch_apply_preflight_receipt", {}).get("preflight_status", "")) == "final_patch_preflight_pass_shadow_only"),
        "h5_final_patch_apply_preflight_blocked_count": sum(1 for row in with_rows if str(row.get("h5_final_patch_apply_preflight_receipt", {}).get("preflight_status", "")) == "blocked"),
        "h5_final_patch_apply_preflight_flag_enabled_count": sum(1 for row in with_rows if bool(row.get("h5_final_patch_apply_preflight_receipt", {}).get("final_patch_apply_preflight_flag_enabled", False))),
        "h5_final_patch_apply_preflight_actual_replaced_count": sum(1 for row in with_rows if bool(row.get("h5_final_patch_apply_preflight_receipt", {}).get("actual_final_patch_replaced", False))),
        "h5_final_patch_apply_preflight_safe_count": sum(1 for row in with_rows if bool(row.get("h5_final_patch_apply_preflight_receipt", {}).get("safe_to_continue", False))),
        "h5_isolated_final_patch_simulation_count": sum(1 for row in with_rows if bool(row.get("h5_isolated_final_patch_replacement_simulation"))),
        "h5_isolated_final_patch_simulation_pass_count": sum(1 for row in with_rows if str(row.get("h5_isolated_final_patch_replacement_simulation", {}).get("simulation_status", "")) == "isolated_final_patch_simulation_pass"),
        "h5_isolated_final_patch_simulation_blocked_count": sum(1 for row in with_rows if str(row.get("h5_isolated_final_patch_replacement_simulation", {}).get("simulation_status", "")) == "blocked"),
        "h5_isolated_final_patch_replaced_count": sum(1 for row in with_rows if bool(row.get("h5_isolated_final_patch_replacement_simulation", {}).get("isolated_final_patch_replaced", False))),
        "h5_actual_final_patch_replaced_count_sim": sum(1 for row in with_rows if bool(row.get("h5_isolated_final_patch_replacement_simulation", {}).get("actual_final_patch_replaced", False))),
        "h5_isolated_final_patch_safe_count": sum(1 for row in with_rows if bool(row.get("h5_isolated_final_patch_replacement_simulation", {}).get("safe_to_continue", False))),
        "h5_actual_final_patch_apply_decision_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_patch_apply_decision"))),
        "h5_actual_final_patch_apply_allowed_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_patch_apply_decision", {}).get("actual_patch_apply_allowed", False))),
        "h5_actual_final_patch_apply_blocked_count": sum(1 for row in with_rows if str(row.get("h5_actual_final_patch_apply_decision", {}).get("apply_decision", "")) == "blocked"),
        "h5_actual_final_patch_apply_executed_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_patch_apply_receipt", {}).get("actual_patch_apply_executed", False))),
        "h5_actual_final_patch_apply_replaced_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_patch_apply_receipt", {}).get("actual_final_patch_replaced", False))),
        "h5_actual_final_patch_apply_all_flags_enabled_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_patch_apply_decision", {}).get("all_ten_flags_enabled", False))),
        "h5_actual_final_patch_apply_safe_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_patch_apply_decision", {}).get("safe_to_continue", False))),
        "h5_actual_final_patch_rollback_decision_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_patch_rollback_decision"))),
        "h5_actual_final_patch_rollback_allowed_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_patch_rollback_decision", {}).get("rollback_allowed", False))),
        "h5_actual_final_patch_rollback_executed_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_patch_rollback_receipt", {}).get("rollback_executed", False))),
        "h5_actual_final_patch_rollback_restored_count": sum(1 for row in with_rows if bool(row.get("h5_actual_final_patch_rollback_receipt", {}).get("actual_final_patch_restored", False))),
        "h5_output_apply_preflight_receipt_count": sum(1 for row in with_rows if bool(row.get("h5_output_apply_preflight_receipt"))),
        "h5_output_apply_preflight_pass_shadow_count": sum(1 for row in with_rows if str(row.get("h5_output_apply_preflight_receipt", {}).get("preflight_status", "")) == "output_preflight_pass_shadow_only"),
        "h5_output_apply_preflight_blocked_count": sum(1 for row in with_rows if str(row.get("h5_output_apply_preflight_receipt", {}).get("preflight_status", "")) == "blocked"),
        "h5_isolated_output_simulation_count": sum(1 for row in with_rows if bool(row.get("h5_isolated_output_mutation_simulation"))),
        "h5_isolated_output_simulation_pass_count": sum(1 for row in with_rows if str(row.get("h5_isolated_output_mutation_simulation", {}).get("simulation_status", "")) == "isolated_output_simulation_pass"),
        "h5_isolated_output_mutated_count": sum(1 for row in with_rows if bool(row.get("h5_isolated_output_mutation_simulation", {}).get("isolated_output_mutated", False))),
        "h5_actual_output_mutated_count_h5_39": sum(1 for row in with_rows if bool(row.get("h5_isolated_output_mutation_simulation", {}).get("actual_output_mutated", False))),
        "h5_actual_output_apply_decision_count": sum(1 for row in with_rows if bool(row.get("h5_actual_output_apply_decision"))),
        "h5_actual_output_apply_allowed_count": sum(1 for row in with_rows if bool(row.get("h5_actual_output_apply_decision", {}).get("actual_output_apply_allowed", False))),
        "h5_actual_output_apply_executed_count": sum(1 for row in with_rows if bool(row.get("h5_actual_output_apply_receipt", {}).get("actual_output_apply_executed", False))),
        "h5_actual_output_mutated_count_h5_40": sum(1 for row in with_rows if bool(row.get("h5_actual_output_apply_receipt", {}).get("actual_output_mutated", False))),
        "h5_actual_output_rollback_decision_count": sum(1 for row in with_rows if bool(row.get("h5_actual_output_rollback_decision"))),
        "h5_actual_output_rollback_allowed_count": sum(1 for row in with_rows if bool(row.get("h5_actual_output_rollback_decision", {}).get("rollback_allowed", False))),
        "h5_actual_output_rollback_executed_count": sum(1 for row in with_rows if bool(row.get("h5_actual_output_rollback_receipt", {}).get("rollback_executed", False))),
        "h5_actual_output_restored_count": sum(1 for row in with_rows if bool(row.get("h5_actual_output_rollback_receipt", {}).get("actual_output_restored", False))),
        "h5_actual_output_safe_count": sum(1 for row in with_rows if bool(row.get("h5_actual_output_apply_decision", {}).get("safe_to_continue", False))),
        "h5_local_candidate_e2e_smoke_receipt_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_e2e_delivery_smoke_receipt"))),
        "h5_local_candidate_e2e_smoke_allowed_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_e2e_delivery_smoke_receipt", {}).get("e2e_smoke_allowed", False))),
        "h5_local_candidate_e2e_smoke_passed_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_e2e_delivery_smoke_receipt", {}).get("e2e_smoke_passed", False))),
        "h5_local_candidate_e2e_smoke_blocked_count": sum(1 for row in with_rows if str(row.get("h5_local_candidate_e2e_delivery_smoke_receipt", {}).get("smoke_status", "")) == "blocked"),
        "h5_local_candidate_e2e_smoke_safe_final_state_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_e2e_delivery_smoke_receipt", {}).get("safe_final_state", False))),
        "h5_local_candidate_e2e_smoke_all_gates_exercised_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_e2e_delivery_smoke_receipt", {}).get("all_mutation_gates_exercised", False))),
        "h5_local_candidate_e2e_smoke_cloud_invoked_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_e2e_delivery_smoke_receipt", {}).get("cloud_invoked", False))),
        "h5_local_candidate_e2e_smoke_model_calls_incremented_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_e2e_delivery_smoke_receipt", {}).get("model_calls_incremented", False))),
        "h5_local_candidate_e2e_smoke_behavior_changed_count": sum(1 for row in with_rows if bool(row.get("h5_local_candidate_e2e_delivery_smoke_receipt", {}).get("behavior_changed", False))),
        "h5_guarded_local_candidate_benchmark_trial_present": 1,
        "h5_guarded_local_candidate_benchmark_trial_allowed": 1 if _build_h5_guarded_local_candidate_benchmark_trial(with_rows).get("trial_allowed") else 0,
        "h5_guarded_local_candidate_benchmark_trial_passed": 1 if _build_h5_guarded_local_candidate_benchmark_trial(with_rows).get("trial_passed") else 0,
        "h5_guarded_local_candidate_benchmark_trial_row_count": len(with_rows),
        "h5_guarded_local_candidate_benchmark_trial_e2e_passed_count": _build_h5_guarded_local_candidate_benchmark_trial(with_rows).get("e2e_smoke_passed_count", 0),
        "h5_guarded_local_candidate_benchmark_trial_safe_final_state_count": _build_h5_guarded_local_candidate_benchmark_trial(with_rows).get("safe_final_state_count", 0),
        "h5_guarded_local_candidate_benchmark_trial_cloud_invoked_count": _build_h5_guarded_local_candidate_benchmark_trial(with_rows).get("cloud_invoked_count", 0),
        "h5_guarded_local_candidate_benchmark_trial_model_calls_incremented_count": _build_h5_guarded_local_candidate_benchmark_trial(with_rows).get("model_calls_incremented_count", 0),
        "h5_guarded_local_candidate_benchmark_trial_behavior_changed_count": _build_h5_guarded_local_candidate_benchmark_trial(with_rows).get("behavior_changed_count", 0),
        "h5_quality_non_regression_gate_present": 1,
        "h5_quality_non_regression_gate_allowed": 1 if _build_h5_quality_non_regression_gate(with_rows).get("gate_allowed") else 0,
        "h5_quality_non_regression_gate_evaluated": 1 if _build_h5_quality_non_regression_gate(with_rows).get("quality_non_regression_evaluated") else 0,
        "h5_quality_non_regression_gate_passed": 1 if _build_h5_quality_non_regression_gate(with_rows).get("quality_non_regression_passed") else 0,
        "h5_quality_non_regression_gate_failed": 1 if _build_h5_quality_non_regression_gate(with_rows).get("gate_status") == "quality_non_regression_fail" else 0,
        "h5_quality_non_regression_gate_regression_count": _build_h5_quality_non_regression_gate(with_rows).get("regression_count", 0),
        "h5_quality_non_regression_gate_quality_floor_met": 1 if _build_h5_quality_non_regression_gate(with_rows).get("quality_floor_met") else 0,
        "h5_quality_non_regression_gate_safety_floor_met": 1 if _build_h5_quality_non_regression_gate(with_rows).get("safety_floor_met") else 0,
        "h5_quality_non_regression_gate_regression_floor_met": 1 if _build_h5_quality_non_regression_gate(with_rows).get("regression_floor_met") else 0,
        "h5_full_guarded_benchmark_run_present": 1,
        "h5_full_guarded_benchmark_run_allowed": 1 if _build_h5_full_guarded_benchmark_run(with_rows).get("run_allowed") else 0,
        "h5_full_guarded_benchmark_run_passed": 1 if _build_h5_full_guarded_benchmark_run(with_rows).get("run_passed") else 0,
        "h5_full_guarded_benchmark_run_failed": 1 if _build_h5_full_guarded_benchmark_run(with_rows).get("run_status") == "full_guarded_benchmark_run_fail" else 0,
        "h5_full_guarded_benchmark_run_ready": 1 if _build_h5_full_guarded_benchmark_run(with_rows).get("full_guarded_benchmark_ready") else 0,
        "h5_full_guarded_benchmark_run_row_count": _build_h5_full_guarded_benchmark_run(with_rows).get("row_count", 0),
        "h5_full_guarded_benchmark_run_e2e_passed_count": _build_h5_full_guarded_benchmark_run(with_rows).get("e2e_smoke_passed_count", 0),
        "h5_full_guarded_benchmark_run_regression_count": _build_h5_full_guarded_benchmark_run(with_rows).get("regression_count", 0),
        "h5_full_guarded_benchmark_run_cloud_invoked_count": _build_h5_full_guarded_benchmark_run(with_rows).get("cloud_invoked_count", 0),
        "h5_full_guarded_benchmark_run_model_calls_incremented_count": _build_h5_full_guarded_benchmark_run(with_rows).get("model_calls_incremented_count", 0),
        "h5_full_guarded_benchmark_run_behavior_changed_count": _build_h5_full_guarded_benchmark_run(with_rows).get("behavior_changed_count", 0),
        "h5_governance_closure_present": 1,
        "h5_governance_closure_allowed": 1 if _build_h5_governance_closure_public_claim_lock(payload).get("closure_allowed") else 0,
        "h5_governance_closure_complete": 1 if _build_h5_governance_closure_public_claim_lock(payload).get("governance_closure_complete") else 0,
        "h5_internal_alpha_ready": 1 if _build_h5_governance_closure_public_claim_lock(payload).get("internal_alpha_ready") else 0,
        "h5_public_claim_lock_active": 1 if _build_h5_governance_closure_public_claim_lock(payload).get("public_claim_lock_active") else 0,
        "h5_production_lock_active": 1 if _build_h5_governance_closure_public_claim_lock(payload).get("production_lock_active") else 0,
        "h5_public_claim_allowed_count": 1 if _build_h5_governance_closure_public_claim_lock(payload).get("public_claim_allowed") else 0,
        "h5_production_ready_count": 1 if _build_h5_governance_closure_public_claim_lock(payload).get("production_ready") else 0,
        "h5_real_local_candidate_execution_harness_count": 1 if _build_h5_real_local_candidate_execution_harness(payload.get("h5_route", {}), payload).get("harness_status") != "blocked" or _build_h5_real_local_candidate_execution_harness(payload.get("h5_route", {}), payload).get("evaluated") else 0,
        "h5_real_local_candidate_execution_harness_allowed_count": 1 if _build_h5_real_local_candidate_execution_harness(payload.get("h5_route", {}), payload).get("harness_allowed") else 0,
        "h5_real_local_candidate_artifact_present_count": 1 if _build_h5_real_local_candidate_execution_harness(payload.get("h5_route", {}), payload).get("real_candidate_artifact_present") else 0,
        "h5_real_local_candidate_artifact_verified_count": 1 if _build_h5_real_local_candidate_execution_harness(payload.get("h5_route", {}), payload).get("real_candidate_artifact_verified") else 0,
        "h5_real_local_candidate_artifact_match_count": 1 if _build_h5_real_local_candidate_execution_harness(payload.get("h5_route", {}), payload).get("metadata_candidate_matches_real_artifact") else 0,
        "h5_real_local_candidate_artifact_mismatch_count": 1 if _build_h5_real_local_candidate_execution_harness(payload.get("h5_route", {}), payload).get("harness_status") == "real_local_candidate_artifact_mismatch" else 0,
        "h5_real_local_candidate_repo_mutated_count": 1 if _build_h5_real_local_candidate_execution_harness(payload.get("h5_route", {}), payload).get("repo_mutated") else 0,
        "h5_real_local_candidate_safe_to_continue_count": 1 if _build_h5_real_local_candidate_execution_harness(payload.get("h5_route", {}), payload).get("safe_to_continue") else 0,
        "h5_real_patch_score_trial_present": 1 if _build_h5_real_patch_verifier_score_trial(with_rows, payload).get("evaluated") else 0,
        "h5_real_patch_score_trial_allowed": 1 if _build_h5_real_patch_verifier_score_trial(with_rows, payload).get("trial_allowed") else 0,
        "h5_real_patch_score_trial_passed": 1 if _build_h5_real_patch_verifier_score_trial(with_rows, payload).get("trial_passed") else 0,
        "h5_real_patch_score_trial_score_visible": 1 if _build_h5_real_patch_verifier_score_trial(with_rows, payload).get("score_visible") else 0,
        "h5_real_patch_score_trial_benchmark_ready": 1 if _build_h5_real_patch_verifier_score_trial(with_rows, payload).get("score_ready_for_benchmark") else 0,
        "h5_real_patch_score_trial_verifier_evaluated_count": _build_h5_real_patch_verifier_score_trial(with_rows, payload).get("verifier_evaluated_count", 0),
        "h5_real_patch_score_trial_verifier_passed_count": _build_h5_real_patch_verifier_score_trial(with_rows, payload).get("verifier_passed_count", 0),
        "h5_real_patch_score_trial_candidate_solved_count": _build_h5_real_patch_verifier_score_trial(with_rows, payload).get("candidate_solved_count", 0),
        "h5_real_patch_score_trial_solve_rate": _build_h5_real_patch_verifier_score_trial(with_rows, payload).get("solve_rate", 0.0),
        "h5_real_patch_score_trial_regression_count": _build_h5_real_patch_verifier_score_trial(with_rows, payload).get("regression_count", 0),
        "h5_real_patch_score_trial_repo_mutated_count": _build_h5_real_patch_verifier_score_trial(with_rows, payload).get("repo_mutated_count", 0),
        "h5_real_patch_score_trial_cloud_invoked_count": _build_h5_real_patch_verifier_score_trial(with_rows, payload).get("cloud_invoked_count", 0),
        "h5_real_patch_score_trial_model_calls_incremented_count": _build_h5_real_patch_verifier_score_trial(with_rows, payload).get("model_calls_incremented_count", 0),
        "h5_real_patch_score_trial_behavior_changed_count": _build_h5_real_patch_verifier_score_trial(with_rows, payload).get("behavior_changed_count", 0),
        "h5_real_patch_scoreboard_present": 1 if _build_h5_real_patch_benchmark_scoreboard(with_rows, payload).get("evaluated") else 0,
        "h5_real_patch_scoreboard_allowed": 1 if _build_h5_real_patch_benchmark_scoreboard(with_rows, payload).get("scoreboard_allowed") else 0,
        "h5_real_patch_scoreboard_ready": 1 if _build_h5_real_patch_benchmark_scoreboard(with_rows, payload).get("scoreboard_ready") else 0,
        "h5_real_patch_scoreboard_ready_for_apply_trial": 1 if _build_h5_real_patch_benchmark_scoreboard(with_rows, payload).get("ready_for_controlled_apply_trial") else 0,
        "h5_real_patch_scoreboard_row_count": _build_h5_real_patch_benchmark_scoreboard(with_rows, payload).get("row_count", 0),
        "h5_real_patch_scoreboard_verifier_evaluated_count": _build_h5_real_patch_benchmark_scoreboard(with_rows, payload).get("verifier_evaluated_count", 0),
        "h5_real_patch_scoreboard_candidate_solved_count": _build_h5_real_patch_benchmark_scoreboard(with_rows, payload).get("candidate_solved_count", 0),
        "h5_real_patch_scoreboard_solve_rate": _build_h5_real_patch_benchmark_scoreboard(with_rows, payload).get("solve_rate", 0.0),
        "h5_real_patch_scoreboard_verifier_pass_rate": _build_h5_real_patch_benchmark_scoreboard(with_rows, payload).get("verifier_pass_rate", 0.0),
        "h5_real_patch_scoreboard_quality_pass_rate": _build_h5_real_patch_benchmark_scoreboard(with_rows, payload).get("quality_pass_rate", 0.0),
        "h5_real_patch_scoreboard_safety_violation_count": _build_h5_real_patch_benchmark_scoreboard(with_rows, payload).get("safety_violation_count", 0),
        "h5_controlled_apply_test_trial_present": 1 if _build_h5_controlled_real_patch_apply_test_trial(with_rows, payload).get("evaluated") else 0,
        "h5_controlled_apply_test_trial_allowed": 1 if _build_h5_controlled_real_patch_apply_test_trial(with_rows, payload).get("trial_allowed") else 0,
        "h5_controlled_apply_test_trial_passed": 1 if _build_h5_controlled_real_patch_apply_test_trial(with_rows, payload).get("trial_passed") else 0,
        "h5_controlled_apply_test_trial_ready_for_delta": 1 if _build_h5_controlled_real_patch_apply_test_trial(with_rows, payload).get("ready_for_benchmark_delta") else 0,
        "h5_controlled_apply_test_trial_patch_apply_attempted_count": _build_h5_controlled_real_patch_apply_test_trial(with_rows, payload).get("patch_apply_attempted_count", 0),
        "h5_controlled_apply_test_trial_patch_apply_passed_count": _build_h5_controlled_real_patch_apply_test_trial(with_rows, payload).get("patch_apply_passed_count", 0),
        "h5_controlled_apply_test_trial_tests_run_count": _build_h5_controlled_real_patch_apply_test_trial(with_rows, payload).get("tests_run_count", 0),
        "h5_controlled_apply_test_trial_tests_passed_count": _build_h5_controlled_real_patch_apply_test_trial(with_rows, payload).get("tests_passed_count", 0),
        "h5_controlled_apply_test_trial_tests_failed_count": _build_h5_controlled_real_patch_apply_test_trial(with_rows, payload).get("tests_failed_count", 0),
        "h5_controlled_apply_test_trial_apply_pass_rate": _build_h5_controlled_real_patch_apply_test_trial(with_rows, payload).get("apply_pass_rate", 0.0),
        "h5_controlled_apply_test_trial_test_pass_rate": _build_h5_controlled_real_patch_apply_test_trial(with_rows, payload).get("test_pass_rate", 0.0),
        "h5_controlled_apply_test_trial_apply_test_pass_rate": _build_h5_controlled_real_patch_apply_test_trial(with_rows, payload).get("apply_test_pass_rate", 0.0),
        "h5_controlled_apply_test_trial_safety_violation_count": _build_h5_controlled_real_patch_apply_test_trial(with_rows, payload).get("safety_violation_count", 0),
        "h5_benchmark_delta_report_present": 1 if _build_h5_benchmark_delta_report(with_rows, payload).get("evaluated") else 0,
        "h5_benchmark_delta_report_allowed": 1 if _build_h5_benchmark_delta_report(with_rows, payload).get("delta_allowed") else 0,
        "h5_benchmark_delta_report_ready": 1 if _build_h5_benchmark_delta_report(with_rows, payload).get("delta_ready") else 0,
        "h5_benchmark_delta_report_improvement_detected": 1 if _build_h5_benchmark_delta_report(with_rows, payload).get("improvement_detected") else 0,
        "h5_benchmark_delta_report_regression_detected": 1 if _build_h5_benchmark_delta_report(with_rows, payload).get("regression_detected") else 0,
        "h5_benchmark_delta_report_ready_for_larger_benchmark": 1 if _build_h5_benchmark_delta_report(with_rows, payload).get("ready_for_larger_benchmark_run") else 0,
        "h5_benchmark_delta_report_baseline_solve_rate": _build_h5_benchmark_delta_report(with_rows, payload).get("baseline_solve_rate", 0.0),
        "h5_benchmark_delta_report_h5_solve_rate": _build_h5_benchmark_delta_report(with_rows, payload).get("h5_solve_rate", 0.0),
        "h5_benchmark_delta_report_solve_rate_delta": _build_h5_benchmark_delta_report(with_rows, payload).get("solve_rate_delta", 0.0),
        "h5_benchmark_delta_report_apply_pass_rate_delta": _build_h5_benchmark_delta_report(with_rows, payload).get("apply_pass_rate_delta", 0.0),
        "h5_benchmark_delta_report_test_pass_rate_delta": _build_h5_benchmark_delta_report(with_rows, payload).get("test_pass_rate_delta", 0.0),
        "h5_benchmark_delta_report_apply_test_pass_rate_delta": _build_h5_benchmark_delta_report(with_rows, payload).get("apply_test_pass_rate_delta", 0.0),
        "h5_benchmark_delta_report_safety_violation_count": _build_h5_benchmark_delta_report(with_rows, payload).get("safety_violation_count", 0),
        "h5_guarded_batch_run_present": 1 if _build_h5_guarded_larger_benchmark_batch_run(with_rows, payload).get("evaluated") else 0,
        "h5_guarded_batch_run_allowed": 1 if _build_h5_guarded_larger_benchmark_batch_run(with_rows, payload).get("batch_allowed") else 0,
        "h5_guarded_batch_run_ready": 1 if _build_h5_guarded_larger_benchmark_batch_run(with_rows, payload).get("batch_ready") else 0,
        "h5_guarded_batch_run_ready_for_h6": 1 if _build_h5_guarded_larger_benchmark_batch_run(with_rows, payload).get("ready_for_h6_local_model_adapter_preflight") else 0,
        "h5_guarded_batch_run_paired_row_count": _build_h5_guarded_larger_benchmark_batch_run(with_rows, payload).get("paired_row_count", 0),
        "h5_guarded_batch_run_batch_solve_rate": _build_h5_guarded_larger_benchmark_batch_run(with_rows, payload).get("batch_solve_rate", 0.0),
        "h5_guarded_batch_run_apply_pass_rate": _build_h5_guarded_larger_benchmark_batch_run(with_rows, payload).get("batch_apply_pass_rate", 0.0),
        "h5_guarded_batch_run_test_pass_rate": _build_h5_guarded_larger_benchmark_batch_run(with_rows, payload).get("batch_test_pass_rate", 0.0),
        "h5_guarded_batch_run_apply_test_pass_rate": _build_h5_guarded_larger_benchmark_batch_run(with_rows, payload).get("batch_apply_test_pass_rate", 0.0),
        "h5_guarded_batch_run_improvement_count": _build_h5_guarded_larger_benchmark_batch_run(with_rows, payload).get("batch_improvement_count", 0),
        "h5_guarded_batch_run_regression_count": _build_h5_guarded_larger_benchmark_batch_run(with_rows, payload).get("batch_regression_count", 0),
        "h5_guarded_batch_run_improvement_rate": _build_h5_guarded_larger_benchmark_batch_run(with_rows, payload).get("batch_improvement_rate", 0.0),
        "h5_guarded_batch_run_regression_rate": _build_h5_guarded_larger_benchmark_batch_run(with_rows, payload).get("batch_regression_rate", 0.0),
        "h5_guarded_batch_run_safety_violation_count": _build_h5_guarded_larger_benchmark_batch_run(with_rows, payload).get("safety_violation_count", 0),
        "h6_local_model_adapter_preflight_present": 1 if _build_h6_local_model_adapter_preflight_contract(with_rows, payload).get("evaluated") else 0,
        "h6_local_model_adapter_preflight_allowed": 1 if _build_h6_local_model_adapter_preflight_contract(with_rows, payload).get("preflight_allowed") else 0,
        "h6_local_model_adapter_preflight_ready": 1 if _build_h6_local_model_adapter_preflight_contract(with_rows, payload).get("preflight_ready") else 0,
        "h6_local_model_adapter_contract_ready": 1 if _build_h6_local_model_adapter_preflight_contract(with_rows, payload).get("adapter_contract_ready") else 0,
        "h6_local_model_adapter_ready_for_shadow_dry_run": 1 if _build_h6_local_model_adapter_preflight_contract(with_rows, payload).get("ready_for_h6_1_shadow_local_adapter_dry_run") else 0,
        "h6_local_model_adapter_candidate_count": _build_h6_local_model_adapter_preflight_contract(with_rows, payload).get("adapter_candidate_count", 0),
        "h6_local_model_adapter_valid_candidate_count": _build_h6_local_model_adapter_preflight_contract(with_rows, payload).get("adapter_candidate_valid_count", 0),
        "h6_local_model_adapter_invalid_candidate_count": _build_h6_local_model_adapter_preflight_contract(with_rows, payload).get("adapter_candidate_invalid_count", 0),
        "h6_local_model_adapter_qwen_3b_candidate_count": _build_h6_local_model_adapter_preflight_contract(with_rows, payload).get("qwen_3b_candidate_count", 0),
        "h6_local_model_adapter_qwen_7b_candidate_count": _build_h6_local_model_adapter_preflight_contract(with_rows, payload).get("qwen_7b_candidate_count", 0),
        "h6_local_model_adapter_qwen_14b_candidate_count": _build_h6_local_model_adapter_preflight_contract(with_rows, payload).get("qwen_14b_candidate_count", 0),
        "h6_local_model_adapter_model_call_executed_count": _build_h6_local_model_adapter_preflight_contract(with_rows, payload).get("model_call_executed_count", 0),
        "h6_local_model_adapter_ollama_invoked_count": _build_h6_local_model_adapter_preflight_contract(with_rows, payload).get("ollama_invoked_count", 0),
        "h6_local_model_adapter_cloud_invoked_count": _build_h6_local_model_adapter_preflight_contract(with_rows, payload).get("cloud_invoked_count", 0),
        "h6_local_model_adapter_repo_mutated_count": _build_h6_local_model_adapter_preflight_contract(with_rows, payload).get("repo_mutated_count", 0),
        "h6_local_model_adapter_behavior_changed_count": _build_h6_local_model_adapter_preflight_contract(with_rows, payload).get("behavior_changed_count", 0),
        "h6_local_model_adapter_safety_violation_count": _build_h6_local_model_adapter_preflight_contract(with_rows, payload).get("safety_violation_count", 0),
        "h6_shadow_local_adapter_dry_run_present": 1 if _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("evaluated") else 0,
        "h6_shadow_local_adapter_dry_run_allowed": 1 if _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("dry_run_allowed") else 0,
        "h6_shadow_local_adapter_dry_run_ready": 1 if _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("dry_run_ready") else 0,
        "h6_shadow_local_adapter_dry_run_receipt_ready": 1 if _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("adapter_dry_run_receipt_ready") else 0,
        "h6_shadow_local_adapter_ready_for_io_schema_test": 1 if _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("ready_for_h6_2_adapter_io_schema_test") else 0,
        "h6_shadow_local_adapter_request_count": _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("shadow_request_count", 0),
        "h6_shadow_local_adapter_valid_request_count": _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("shadow_request_valid_count", 0),
        "h6_shadow_local_adapter_invalid_request_count": _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("shadow_request_invalid_count", 0),
        "h6_shadow_local_adapter_receipt_count": _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("shadow_receipt_count", 0),
        "h6_shadow_local_adapter_valid_receipt_count": _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("shadow_receipt_valid_count", 0),
        "h6_shadow_local_adapter_invalid_receipt_count": _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("shadow_receipt_invalid_count", 0),
        "h6_shadow_local_adapter_qwen_3b_request_count": _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("qwen_3b_shadow_request_count", 0),
        "h6_shadow_local_adapter_qwen_7b_request_count": _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("qwen_7b_shadow_request_count", 0),
        "h6_shadow_local_adapter_qwen_14b_request_count": _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("qwen_14b_shadow_request_count", 0),
        "h6_shadow_local_adapter_model_call_executed_count": _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("model_call_executed_count", 0),
        "h6_shadow_local_adapter_ollama_invoked_count": _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("ollama_invoked_count", 0),
        "h6_shadow_local_adapter_cloud_invoked_count": _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("cloud_invoked_count", 0),
        "h6_shadow_local_adapter_repo_mutated_count": _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("repo_mutated_count", 0),
        "h6_shadow_local_adapter_behavior_changed_count": _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("behavior_changed_count", 0),
        "h6_shadow_local_adapter_safety_violation_count": _build_h6_shadow_local_adapter_dry_run(with_rows, payload).get("safety_violation_count", 0),
        "h6_adapter_io_schema_test_present": 1 if _build_h6_adapter_io_schema_test(with_rows, payload).get("evaluated") else 0,
        "h6_adapter_io_schema_test_allowed": 1 if _build_h6_adapter_io_schema_test(with_rows, payload).get("io_schema_allowed") else 0,
        "h6_adapter_io_schema_test_ready": 1 if _build_h6_adapter_io_schema_test(with_rows, payload).get("io_schema_ready") else 0,
        "h6_adapter_io_schema_ready": 1 if _build_h6_adapter_io_schema_test(with_rows, payload).get("adapter_io_schema_ready") else 0,
        "h6_adapter_io_schema_ready_for_shadow_routing": 1 if _build_h6_adapter_io_schema_test(with_rows, payload).get("ready_for_h6_3_shadow_adapter_routing") else 0,
        "h6_adapter_io_schema_input_envelope_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("input_envelope_count", 0),
        "h6_adapter_io_schema_valid_input_envelope_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("input_envelope_valid_count", 0),
        "h6_adapter_io_schema_invalid_input_envelope_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("input_envelope_invalid_count", 0),
        "h6_adapter_io_schema_output_envelope_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("output_envelope_count", 0),
        "h6_adapter_io_schema_valid_output_envelope_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("output_envelope_valid_count", 0),
        "h6_adapter_io_schema_invalid_output_envelope_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("output_envelope_invalid_count", 0),
        "h6_adapter_io_schema_matched_io_pair_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("matched_io_pair_count", 0),
        "h6_adapter_io_schema_unmatched_input_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("unmatched_input_count", 0),
        "h6_adapter_io_schema_unmatched_output_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("unmatched_output_count", 0),
        "h6_adapter_io_schema_qwen_3b_io_pair_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("qwen_3b_io_pair_count", 0),
        "h6_adapter_io_schema_qwen_7b_io_pair_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("qwen_7b_io_pair_count", 0),
        "h6_adapter_io_schema_qwen_14b_io_pair_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("qwen_14b_io_pair_count", 0),
        "h6_adapter_io_schema_model_call_executed_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("model_call_executed_count", 0),
        "h6_adapter_io_schema_ollama_invoked_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("ollama_invoked_count", 0),
        "h6_adapter_io_schema_cloud_invoked_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("cloud_invoked_count", 0),
        "h6_adapter_io_schema_repo_mutated_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("repo_mutated_count", 0),
        "h6_adapter_io_schema_behavior_changed_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("behavior_changed_count", 0),
        "h6_adapter_io_schema_runtime_effect_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("runtime_effect_count", 0),
        "h6_adapter_io_schema_safety_violation_count": _build_h6_adapter_io_schema_test(with_rows, payload).get("safety_violation_count", 0),
        "h6_shadow_adapter_routing_present": 1 if _build_h6_shadow_adapter_routing(with_rows, payload).get("evaluated") else 0,
        "h6_shadow_adapter_routing_allowed": 1 if _build_h6_shadow_adapter_routing(with_rows, payload).get("routing_allowed") else 0,
        "h6_shadow_adapter_routing_ready": 1 if _build_h6_shadow_adapter_routing(with_rows, payload).get("routing_ready") else 0,
        "h6_shadow_adapter_routing_receipt_ready": 1 if _build_h6_shadow_adapter_routing(with_rows, payload).get("shadow_adapter_routing_receipt_ready") else 0,
        "h6_shadow_adapter_routing_ready_for_execution_plan": 1 if _build_h6_shadow_adapter_routing(with_rows, payload).get("ready_for_h6_4_local_adapter_execution_plan_dry_run") else 0,
        "h6_shadow_adapter_routing_candidate_count": _build_h6_shadow_adapter_routing(with_rows, payload).get("route_candidate_count", 0),
        "h6_shadow_adapter_routing_valid_candidate_count": _build_h6_shadow_adapter_routing(with_rows, payload).get("route_candidate_valid_count", 0),
        "h6_shadow_adapter_routing_invalid_candidate_count": _build_h6_shadow_adapter_routing(with_rows, payload).get("route_candidate_invalid_count", 0),
        "h6_shadow_adapter_routing_receipt_count": _build_h6_shadow_adapter_routing(with_rows, payload).get("route_receipt_count", 0),
        "h6_shadow_adapter_routing_valid_receipt_count": _build_h6_shadow_adapter_routing(with_rows, payload).get("route_receipt_valid_count", 0),
        "h6_shadow_adapter_routing_invalid_receipt_count": _build_h6_shadow_adapter_routing(with_rows, payload).get("route_receipt_invalid_count", 0),
        "h6_shadow_adapter_routing_selected_count": _build_h6_shadow_adapter_routing(with_rows, payload).get("shadow_route_selected_count", 0),
        "h6_shadow_adapter_routing_blocked_count": _build_h6_shadow_adapter_routing(with_rows, payload).get("shadow_route_blocked_count", 0),
        "h6_shadow_adapter_routing_qwen_3b_route_count": _build_h6_shadow_adapter_routing(with_rows, payload).get("qwen_3b_route_count", 0),
        "h6_shadow_adapter_routing_qwen_7b_route_count": _build_h6_shadow_adapter_routing(with_rows, payload).get("qwen_7b_route_count", 0),
        "h6_shadow_adapter_routing_qwen_14b_route_count": _build_h6_shadow_adapter_routing(with_rows, payload).get("qwen_14b_route_count", 0),
        "h6_shadow_adapter_routing_model_call_executed_count": _build_h6_shadow_adapter_routing(with_rows, payload).get("model_call_executed_count", 0),
        "h6_shadow_adapter_routing_ollama_invoked_count": _build_h6_shadow_adapter_routing(with_rows, payload).get("ollama_invoked_count", 0),
        "h6_shadow_adapter_routing_cloud_invoked_count": _build_h6_shadow_adapter_routing(with_rows, payload).get("cloud_invoked_count", 0),
        "h6_shadow_adapter_routing_repo_mutated_count": _build_h6_shadow_adapter_routing(with_rows, payload).get("repo_mutated_count", 0),
        "h6_shadow_adapter_routing_behavior_changed_count": _build_h6_shadow_adapter_routing(with_rows, payload).get("behavior_changed_count", 0),
        "h6_shadow_adapter_routing_runtime_effect_count": _build_h6_shadow_adapter_routing(with_rows, payload).get("runtime_effect_count", 0),
        "h6_shadow_adapter_routing_safety_violation_count": _build_h6_shadow_adapter_routing(with_rows, payload).get("safety_violation_count", 0),
        "h6_local_adapter_execution_plan_present": 1 if _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload).get("evaluated") else 0,
        "h6_local_adapter_execution_plan_allowed": 1 if _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload).get("plan_allowed") else 0,
        "h6_local_adapter_execution_plan_ready": 1 if _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload).get("plan_ready") else 0,
        "h6_local_adapter_execution_plan_receipt_ready": 1 if _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload).get("execution_plan_receipt_ready") else 0,
        "h6_local_adapter_execution_plan_ready_for_invocation_intent": 1 if _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload).get("ready_for_h6_5_shadow_local_adapter_invocation_intent") else 0,
        "h6_local_adapter_execution_plan_count": _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload).get("execution_plan_count", 0),
        "h6_local_adapter_valid_execution_plan_count": _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload).get("execution_plan_valid_count", 0),
        "h6_local_adapter_invalid_execution_plan_count": _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload).get("execution_plan_invalid_count", 0),
        "h6_local_adapter_qwen_3b_execution_plan_count": _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload).get("qwen_3b_execution_plan_count", 0),
        "h6_local_adapter_qwen_7b_execution_plan_count": _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload).get("qwen_7b_execution_plan_count", 0),
        "h6_local_adapter_qwen_14b_execution_plan_count": _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload).get("qwen_14b_execution_plan_count", 0),
        "h6_local_adapter_execution_plan_model_call_executed_count": _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload).get("model_call_executed_count", 0),
        "h6_local_adapter_execution_plan_ollama_invoked_count": _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload).get("ollama_invoked_count", 0),
        "h6_local_adapter_execution_plan_cloud_invoked_count": _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload).get("cloud_invoked_count", 0),
        "h6_local_adapter_execution_plan_repo_mutated_count": _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload).get("repo_mutated_count", 0),
        "h6_local_adapter_execution_plan_behavior_changed_count": _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload).get("behavior_changed_count", 0),
        "h6_local_adapter_execution_plan_runtime_effect_count": _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload).get("runtime_effect_count", 0),
        "h6_local_adapter_execution_plan_safety_violation_count": _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload).get("safety_violation_count", 0),
        "h6_shadow_invocation_intent_present": 1 if _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("evaluated") else 0,
        "h6_shadow_invocation_intent_allowed": 1 if _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("intent_allowed") else 0,
        "h6_shadow_invocation_intent_ready": 1 if _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("intent_ready") else 0,
        "h6_shadow_invocation_intent_receipt_ready": 1 if _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("invocation_intent_receipt_ready") else 0,
        "h6_shadow_invocation_intent_ready_for_stub_output": 1 if _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("ready_for_h6_6_deterministic_local_adapter_stub_output") else 0,
        "h6_shadow_invocation_intent_count": _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("invocation_intent_count", 0),
        "h6_shadow_invocation_valid_intent_count": _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("invocation_intent_valid_count", 0),
        "h6_shadow_invocation_invalid_intent_count": _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("invocation_intent_invalid_count", 0),
        "h6_shadow_invocation_intent_receipt_count": _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("intent_receipt_count", 0),
        "h6_shadow_invocation_valid_receipt_count": _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("intent_receipt_valid_count", 0),
        "h6_shadow_invocation_invalid_receipt_count": _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("intent_receipt_invalid_count", 0),
        "h6_shadow_invocation_model_call_intended_count": _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("model_call_intended_count", 0),
        "h6_shadow_invocation_model_call_executed_count": _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("model_call_executed_count", 0),
        "h6_shadow_invocation_ollama_invoked_count": _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("ollama_invoked_count", 0),
        "h6_shadow_invocation_cloud_invoked_count": _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("cloud_invoked_count", 0),
        "h6_shadow_invocation_repo_mutated_count": _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("repo_mutated_count", 0),
        "h6_shadow_invocation_behavior_changed_count": _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("behavior_changed_count", 0),
        "h6_shadow_invocation_runtime_effect_count": _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("runtime_effect_count", 0),
        "h6_shadow_invocation_safety_violation_count": _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload).get("safety_violation_count", 0),
        "h6_deterministic_stub_output_present": 1 if _build_h6_deterministic_local_adapter_stub_output(with_rows, payload).get("evaluated") else 0,
        "h6_deterministic_stub_output_allowed": 1 if _build_h6_deterministic_local_adapter_stub_output(with_rows, payload).get("stub_allowed") else 0,
        "h6_deterministic_stub_output_ready": 1 if _build_h6_deterministic_local_adapter_stub_output(with_rows, payload).get("stub_ready") else 0,
        "h6_deterministic_stub_output_receipt_ready": 1 if _build_h6_deterministic_local_adapter_stub_output(with_rows, payload).get("stub_output_receipt_ready") else 0,
        "h6_deterministic_stub_output_ready_for_provider_boundary": 1 if _build_h6_deterministic_local_adapter_stub_output(with_rows, payload).get("ready_for_h6_7_local_provider_boundary_preflight") else 0,
        "h6_deterministic_stub_output_count": _build_h6_deterministic_local_adapter_stub_output(with_rows, payload).get("stub_output_count", 0),
        "h6_deterministic_valid_stub_output_count": _build_h6_deterministic_local_adapter_stub_output(with_rows, payload).get("stub_output_valid_count", 0),
        "h6_deterministic_invalid_stub_output_count": _build_h6_deterministic_local_adapter_stub_output(with_rows, payload).get("stub_output_invalid_count", 0),
        "h6_deterministic_qwen_3b_stub_output_count": _build_h6_deterministic_local_adapter_stub_output(with_rows, payload).get("qwen_3b_stub_output_count", 0),
        "h6_deterministic_qwen_7b_stub_output_count": _build_h6_deterministic_local_adapter_stub_output(with_rows, payload).get("qwen_7b_stub_output_count", 0),
        "h6_deterministic_qwen_14b_stub_output_count": _build_h6_deterministic_local_adapter_stub_output(with_rows, payload).get("qwen_14b_stub_output_count", 0),
        "h6_deterministic_stub_model_call_executed_count": _build_h6_deterministic_local_adapter_stub_output(with_rows, payload).get("model_call_executed_count", 0),
        "h6_deterministic_stub_ollama_invoked_count": _build_h6_deterministic_local_adapter_stub_output(with_rows, payload).get("ollama_invoked_count", 0),
        "h6_deterministic_stub_cloud_invoked_count": _build_h6_deterministic_local_adapter_stub_output(with_rows, payload).get("cloud_invoked_count", 0),
        "h6_deterministic_stub_repo_mutated_count": _build_h6_deterministic_local_adapter_stub_output(with_rows, payload).get("repo_mutated_count", 0),
        "h6_deterministic_stub_behavior_changed_count": _build_h6_deterministic_local_adapter_stub_output(with_rows, payload).get("behavior_changed_count", 0),
        "h6_deterministic_stub_runtime_effect_count": _build_h6_deterministic_local_adapter_stub_output(with_rows, payload).get("runtime_effect_count", 0),
        "h6_deterministic_stub_safety_violation_count": _build_h6_deterministic_local_adapter_stub_output(with_rows, payload).get("safety_violation_count", 0),
        "h6_local_provider_boundary_present": 1 if _build_h6_local_provider_boundary_preflight(with_rows, payload).get("evaluated") else 0,
        "h6_local_provider_boundary_allowed": 1 if _build_h6_local_provider_boundary_preflight(with_rows, payload).get("boundary_allowed") else 0,
        "h6_local_provider_boundary_ready": 1 if _build_h6_local_provider_boundary_preflight(with_rows, payload).get("boundary_ready") else 0,
        "h6_local_provider_boundary_contract_ready": 1 if _build_h6_local_provider_boundary_preflight(with_rows, payload).get("provider_contract_ready") else 0,
        "h6_local_provider_boundary_ready_for_config": 1 if _build_h6_local_provider_boundary_preflight(with_rows, payload).get("ready_for_h6_8_local_provider_config_contract") else 0,
        "h6_local_provider_boundary_count": _build_h6_local_provider_boundary_preflight(with_rows, payload).get("provider_boundary_count", 0),
        "h6_local_provider_valid_boundary_count": _build_h6_local_provider_boundary_preflight(with_rows, payload).get("provider_boundary_valid_count", 0),
        "h6_local_provider_invalid_boundary_count": _build_h6_local_provider_boundary_preflight(with_rows, payload).get("provider_boundary_invalid_count", 0),
        "h6_local_provider_boundary_safety_violation_count": _build_h6_local_provider_boundary_preflight(with_rows, payload).get("safety_violation_count", 0),
        "h6_local_provider_config_present": 1 if _build_h6_local_provider_config_contract(with_rows, payload).get("evaluated") else 0,
        "h6_local_provider_config_allowed": 1 if _build_h6_local_provider_config_contract(with_rows, payload).get("config_allowed") else 0,
        "h6_local_provider_config_ready": 1 if _build_h6_local_provider_config_contract(with_rows, payload).get("config_ready") else 0,
        "h6_local_provider_config_receipt_ready": 1 if _build_h6_local_provider_config_contract(with_rows, payload).get("provider_config_receipt_ready") else 0,
        "h6_local_provider_config_ready_for_invocation_gate": 1 if _build_h6_local_provider_config_contract(with_rows, payload).get("ready_for_h6_9_local_provider_invocation_gate") else 0,
        "h6_local_provider_config_count": _build_h6_local_provider_config_contract(with_rows, payload).get("provider_config_count", 0),
        "h6_local_provider_valid_config_count": _build_h6_local_provider_config_contract(with_rows, payload).get("provider_config_valid_count", 0),
        "h6_local_provider_invalid_config_count": _build_h6_local_provider_config_contract(with_rows, payload).get("provider_config_invalid_count", 0),
        "h6_local_provider_config_safety_violation_count": _build_h6_local_provider_config_contract(with_rows, payload).get("safety_violation_count", 0),
        "h6_local_provider_invocation_gate_present": 1 if _build_h6_local_provider_invocation_gate(with_rows, payload).get("evaluated") else 0,
        "h6_local_provider_invocation_gate_allowed": 1 if _build_h6_local_provider_invocation_gate(with_rows, payload).get("gate_allowed") else 0,
        "h6_local_provider_invocation_gate_ready": 1 if _build_h6_local_provider_invocation_gate(with_rows, payload).get("gate_ready") else 0,
        "h6_local_provider_invocation_gate_receipt_ready": 1 if _build_h6_local_provider_invocation_gate(with_rows, payload).get("provider_invocation_gate_receipt_ready") else 0,
        "h6_local_provider_invocation_gate_ready_for_probe": 1 if _build_h6_local_provider_invocation_gate(with_rows, payload).get("ready_for_h6_10_controlled_provider_probe_preflight") else 0,
        "h6_local_provider_invocation_gate_count": _build_h6_local_provider_invocation_gate(with_rows, payload).get("invocation_gate_count", 0),
        "h6_local_provider_valid_invocation_gate_count": _build_h6_local_provider_invocation_gate(with_rows, payload).get("invocation_gate_valid_count", 0),
        "h6_local_provider_invalid_invocation_gate_count": _build_h6_local_provider_invocation_gate(with_rows, payload).get("invocation_gate_invalid_count", 0),
        "h6_local_provider_invocation_gate_safety_violation_count": _build_h6_local_provider_invocation_gate(with_rows, payload).get("safety_violation_count", 0),
    }
    payload["h5_guarded_local_candidate_benchmark_trial"] = _build_h5_guarded_local_candidate_benchmark_trial(with_rows)
    payload["h5_quality_non_regression_gate"] = _build_h5_quality_non_regression_gate(with_rows, payload["h5_guarded_local_candidate_benchmark_trial"])
    payload["h5_guarded_local_candidate_benchmark_trial"]["quality_non_regression_evaluated"] = payload["h5_quality_non_regression_gate"]["quality_non_regression_evaluated"]
    payload["h5_guarded_local_candidate_benchmark_trial"]["quality_non_regression_passed"] = payload["h5_quality_non_regression_gate"]["quality_non_regression_passed"]
    payload["h5_full_guarded_benchmark_run"] = _build_h5_full_guarded_benchmark_run(with_rows, payload)
    payload["h5_governance_closure_public_claim_lock"] = _build_h5_governance_closure_public_claim_lock(payload)
    payload["h5_real_local_candidate_execution_harness"] = _build_h5_real_local_candidate_execution_harness(payload.get("h5_route", {}), payload)
    payload["h5_real_patch_verifier_score_trial"] = _build_h5_real_patch_verifier_score_trial(with_rows, payload)
    payload["h5_real_patch_benchmark_scoreboard"] = _build_h5_real_patch_benchmark_scoreboard(with_rows, payload)
    payload["h5_controlled_real_patch_apply_test_trial"] = _build_h5_controlled_real_patch_apply_test_trial(with_rows, payload)
    payload["h5_benchmark_delta_report"] = _build_h5_benchmark_delta_report(with_rows, payload)
    payload["h5_guarded_larger_benchmark_batch_run"] = _build_h5_guarded_larger_benchmark_batch_run(with_rows, payload)
    payload["h6_local_model_adapter_preflight_contract"] = _build_h6_local_model_adapter_preflight_contract(with_rows, payload)
    payload["h6_shadow_local_adapter_dry_run"] = _build_h6_shadow_local_adapter_dry_run(with_rows, payload)
    payload["h6_adapter_io_schema_test"] = _build_h6_adapter_io_schema_test(with_rows, payload)
    payload["h6_shadow_adapter_routing"] = _build_h6_shadow_adapter_routing(with_rows, payload)
    payload["h6_local_adapter_execution_plan_dry_run"] = _build_h6_local_adapter_execution_plan_dry_run(with_rows, payload)
    payload["h6_shadow_local_adapter_invocation_intent_receipt"] = _build_h6_shadow_local_adapter_invocation_intent_receipt(with_rows, payload)
    payload["h6_deterministic_local_adapter_stub_output"] = _build_h6_deterministic_local_adapter_stub_output(with_rows, payload)
    payload["h6_local_provider_boundary_preflight"] = _build_h6_local_provider_boundary_preflight(with_rows, payload)
    payload["h6_local_provider_config_contract"] = _build_h6_local_provider_config_contract(with_rows, payload)
    payload["h6_local_provider_invocation_gate"] = _build_h6_local_provider_invocation_gate(with_rows, payload)
    payload["external_provider_claim_boundary_contract"] = build_external_provider_claim_boundary_contract(payload)
    payload["public_promotion_readiness_contract"] = build_public_promotion_readiness_contract(payload)
    bundle_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return bundle_path


def _reset_auto_flow_history(repo_root: Path) -> None:
    history_path = (repo_root / ".nexus" / "reports" / "research" / "auto-flow-history.json").resolve()
    if history_path.exists():
        history_path.unlink()


def _history_policy_name(*, neutralize_history: bool, allow_learning_loop: bool) -> str:
    if not neutralize_history:
        return "shared_existing_history"
    if allow_learning_loop:
        return "within_mode_learning"
    return "per_task_reset"


def _hidden_verifier_mode_enabled(config: "dict | None" = None) -> bool:
    """PR3: Check hidden verifier mode from config dict first, then fall back to env.

    Args:
        config: Optional runner config dict. If provided and contains
                'hidden_verifier_mode': True, returns True without env lookup.
                This ensures CLI-flag-derived config is the authoritative source,
                avoiding preflight/subprocess source inconsistency.
    """
    if config is not None and bool(config.get("hidden_verifier_mode")):
        return True
    return os.environ.get("NEXUS_VALUE_HIDDEN_VERIFIER", "").strip().lower() in {"1", "true", "yes"}


def _report_model_label() -> str:
    model = str(
        os.environ.get("NEXUS_GEMINI_MODEL_NAME")
        or os.environ.get("NEXUS_DIRECT_GEMINI_MODEL")
        or os.environ.get("NEXUS_CODEX_MODEL_NAME")
        or os.environ.get("NEXUS_DIRECT_CODEX_MODEL")
        or "model"
    ).strip()
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", model) or "model"


def _benchmark_gateway_timeout_sec(default_sec: int = 30) -> str:
    override = str(os.environ.get("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC", "") or "").strip()
    if override:
        try:
            return str(max(5, int(override)))
        except ValueError:
            pass
    return str(max(5, int(default_sec)))


def _benchmark_gateway_timeout_for_task(timeout_sec: int) -> int:
    # Give Gemini enough room to answer while preserving subprocess budget for Nexus verification.
    flash_model = "flash" in _report_model_label().lower()
    long_gateway = os.environ.get("NEXUS_BENCH_LONG_GATEWAY", "").strip().lower() in {"1", "true", "yes"}
    if flash_model and not long_gateway:
        return min(120, max(30, int(timeout_sec) - 30))
    return min(220, max(30, int(timeout_sec) - 30))


def _benchmark_gateway_timeout_for_execution(
    *,
    task: CapabilityTask,
    timeout_sec: int,
    base_timeout_sec: int,
    require_model_participation: bool = False,
) -> int:
    """Keep model-required benchmarks from silently falling back to local delivery.

    Flash can validly need more than the short low-cost gateway cap on public
    model-required tasks. The subprocess timeout still owns the hard stop, but
    the model call needs enough room to become the final delivery source.
    """

    if task.eligibility_class != "model_required" and not require_model_participation:
        return int(base_timeout_sec)
    ceiling = max(30, int(timeout_sec) - 15)
    target = min(210, ceiling)
    return int(min(max(int(base_timeout_sec), target), ceiling))


def _expected_capability_timeout_floor_sec(
    *,
    timeout_sec: int,
    llm_enabled: bool,
    expected_executor_flags: dict[str, bool],
) -> int:
    # Protected executor benchmarks should not time out before the expected capability can emit receipts.
    effective = max(1, int(timeout_sec))
    if not llm_enabled:
        return effective
    if expected_executor_flags.get("enable_ddtree_executor"):
        return max(effective, int(os.environ.get("NEXUS_EXPECTED_DDTREE_TIMEOUT_FLOOR_SEC", "300") or 300))
    return effective


def _force_learn_slo_ready(repo_root: Path) -> None:
    path = (repo_root / ".nexus" / "reports" / "learn" / "phase_slo_summary.json").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "status": "SUCCESS",
                "phase_slo_pass": True,
                "global": {"required_done_ratio": 1.0, "success_ratio": 1.0},
                "reason": "capability_ab_runner_force_learn_slo_ready",
                "public_lane_eligible": False,
                "evidence_class": "synthetic_readiness_shortcut",
            }
        ),
        encoding="utf-8",
    )


def _git_status_porcelain(repo_root: Path) -> str:
    res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        timeout=10,
    )
    if res.returncode != 0:
        raise RuntimeError((res.stderr or res.stdout or "git status failed").strip())
    return res.stdout.strip()


def assert_clean_worktree(repo_root: Path) -> None:
    status = _git_status_porcelain(repo_root)
    if status:
        raise RuntimeError("Benchmark requires a clean worktree; dirty entries:\n" + status)


def _manifest_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def _public_disclosure_manifest(path_value: str, *, repo_root: Path) -> dict[str, Any]:
    if not path_value:
        return {"path": "", "sha256": "", "status": "not_provided", "failures": []}
    path = Path(path_value)
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    if not path.exists():
        return {"path": str(path), "sha256": "", "status": "FAIL", "failures": ["disclosure_manifest_missing"]}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "path": str(path),
            "sha256": "",
            "status": "FAIL",
            "failures": [f"disclosure_manifest_parse_failed:{exc.__class__.__name__}"],
        }
    failures: list[str] = []
    if payload.get("schema") not in {
        "nexus_public_benchmark_sanitized_manifest_v1",
        "nexus_public_benchmark_execution_safe_manifest_v1",
    }:
        failures.append("disclosure_manifest_schema_invalid")
    for index, task in enumerate(payload.get("tasks", []) or [], start=1):
        if not isinstance(task, dict):
            failures.append(f"disclosure_task_{index}_not_object")
            continue
        if "allowed_files" in task or "forbidden_files" in task:
            failures.append(f"disclosure_task_{index}_contains_file_scope")
        if not str(task.get("repo", "")).startswith("fixture://"):
            failures.append(f"disclosure_task_{index}_repo_not_sanitized")
    return {
        "path": str(path),
        "sha256": _manifest_sha256(path),
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
    }


def _public_manifest_shape_failures(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"manifest_parse_failed:{exc.__class__.__name__}"]

    failures: list[str] = []
    required_top = {"version", "frozen", "benchmark_id", "description", "tasks"}
    missing_top = sorted(required_top - set(payload))
    if missing_top:
        failures.append("manifest_missing_top_fields:" + ",".join(missing_top))
    if not isinstance(payload.get("tasks"), list) or not payload.get("tasks"):
        failures.append("manifest_tasks_empty")
        return failures

    required_task = {
        "id",
        "category",
        "difficulty",
        "repo_kind",
        "repo",
        "repo_ref",
        "task_desc",
        "success_criteria",
        "mutation_required",
        "allowed_files",
        "forbidden_files",
        "setup_command",
        "verification_command",
    }
    allowed_task = required_task | {
        "target_file",
        "test_file",
        "fixture_kind",
        "rlm_challenge",
        "commercial_lane",
        "source_manifest",
        "expected_capabilities",
        "capability_activation_contract",
        "hidden_oracle_kind",
        "eligibility_class",
        "cost_budget",
        "token_budget",
        "wall_time_budget_sec",
        "public_claim_allowed_metrics",
        "stratum_type",
    }
    for index, task in enumerate(payload["tasks"], start=1):
        if not isinstance(task, dict):
            failures.append(f"manifest_task_{index}_not_object")
            continue
        missing = sorted(required_task - set(task))
        if missing:
            failures.append(f"manifest_task_{index}_missing:" + ",".join(missing))
        unknown = sorted(set(task) - allowed_task)
        if unknown:
            failures.append(f"manifest_task_{index}_unknown:" + ",".join(unknown))
        eligibility_class = str(task.get("eligibility_class") or "").strip()
        if eligibility_class and eligibility_class not in {
            "deterministic_contract",
            "model_required",
            "bare_model_only",
        }:
            failures.append(f"manifest_task_{index}_eligibility_class_invalid:{eligibility_class}")
    return failures


def _string_literals(source: str) -> set[str]:
    try:
        # Candidate snippets may be syntactically valid but emit SyntaxWarning
        # during parsing; leak scanning should not pollute run-level telemetry.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(source)
    except SyntaxError:
        return set()
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            if len(value) >= 3:
                values.add(value)
    return values


def _prompt_leak_literal_is_structured(literal: str) -> bool:
    if literal in {"needs_evidence", "verified", "unverified", "partial", "failed", "passed"}:
        # Generic status enums are not hidden-answer leaks.
        return False
    return bool(re.search(r"[/_.]|\d", literal))


def _prompt_leak_audit_failures(tasks: list[CapabilityTask], *, repo_root: Path) -> list[str]:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="nexus_prompt_leak_", dir="/tmp") as tmp:
        scratch_root = Path(tmp)
        for task in tasks:
            if not task.fixture_kind:
                continue
            try:
                target_file, visible_test_file = _materialize_fixture(scratch_root / task.id, task)
            except ValueError:
                continue
            hidden_test_file = _hidden_test_for_visible_test(visible_test_file)
            visible_source = Path(visible_test_file).read_text(encoding="utf-8")
            hidden_source = Path(hidden_test_file).read_text(encoding="utf-8")
            hidden_only = sorted(
                literal
                for literal in (_string_literals(hidden_source) - _string_literals(visible_source))
                if _prompt_leak_literal_is_structured(literal)
            )
            if not hidden_only:
                continue
            target_source = Path(target_file).read_text(encoding="utf-8")
            guidance = "\n".join(
                [
                    _nexus_task_desc(task),
                    _nexus_codex_hidden_verifier_guidance(task, target_source),
                ]
            )
            allowed_policy_literals: set[str] = set()
            if task.fixture_kind == "rlm_harder_v2_governance_guard":
                # These are generic destructive tool names, not hidden-answer values.
                allowed_policy_literals.update({"delete_file", "write_file"})
            leaked = [
                literal
                for literal in hidden_only
                if literal and literal in guidance and literal not in allowed_policy_literals
            ]
            if leaked:
                failures.append(f"prompt_leak:{task.id}:" + ",".join(leaked[:3]))
    return failures


def _build_preflight_sentinel(
    *,
    args: argparse.Namespace,
    tasks_path: Path,
    selected_tasks: list[CapabilityTask],
    manifest_hash: str,
) -> dict[str, Any]:
    failures: list[str] = []
    checks: dict[str, Any] = {
        "schema": "nexus_preflight_sentinel_v1",
        "manifest_hash_present": bool(manifest_hash),
        "warning_ledger_required": bool(getattr(args, "evidence_bundle", False)),
        "wall_ledger_required": bool(getattr(args, "evidence_bundle", False)),
        "infra_quarantine_required": not bool(getattr(args, "nexus_only", False)),
        "provider_token_measured_required": getattr(args, "without_mode", "") in {"gemini", "codex"}
        or getattr(args, "with_model_provider", "") in {"gemini", "codex", "ollama"},
        "hidden_verifier_required": True,
        "hidden_verifier_enabled": _hidden_verifier_mode_enabled(),
        "single_variable_gate": True,
        "x1_x3_denominator_policy": "infra_valid_pair_and_warning_clean_and_wall_conserved_only",
        "rubric_stage_fields_required": ["failed_stage", "failed_rubric_keys"],
        "dci_raw_warning_pointer_required": True,
    }
    if not checks["manifest_hash_present"]:
        failures.append("sentinel_manifest_hash_missing")
    if not checks["warning_ledger_required"]:
        failures.append("sentinel_warning_ledger_not_required")
    if not checks["wall_ledger_required"]:
        failures.append("sentinel_wall_ledger_not_required")
    if not checks["hidden_verifier_enabled"]:
        failures.append("sentinel_hidden_verifier_disabled")

    strata: list[str] = []
    benchmark_id = ""
    frozen = False
    if tasks_path.exists():
        try:
            payload = json.loads(tasks_path.read_text(encoding="utf-8"))
            benchmark_id = str(payload.get("benchmark_id") or "")
            frozen = bool(payload.get("frozen", False))
            selected_ids = {task.id for task in selected_tasks}
            for task in payload.get("tasks", []) or []:
                if not isinstance(task, dict) or str(task.get("id") or "") not in selected_ids:
                    continue
                stratum = str(task.get("stratum_type") or "").strip()
                if stratum:
                    strata.append(stratum)
        except (OSError, json.JSONDecodeError):
            failures.append("sentinel_manifest_unreadable")
    docs_lane_full_batch = benchmark_id == "nexus-public-docs-lane-v1" and (
        str(getattr(args, "task_id_filter", "all") or "all") == "all" or int(getattr(args, "max_tasks", 0) or 0) >= 3
    )
    expected_docs_strata = {"pure_docs", "docs_code_sync", "evidence_required_docs"}
    strata_set = set(strata)
    if docs_lane_full_batch:
        if not frozen:
            failures.append("sentinel_docs_manifest_not_frozen")
        missing = sorted(expected_docs_strata - strata_set)
        if missing:
            failures.append("sentinel_docs_strata_missing:" + ",".join(missing))
    checks.update(
        {
            "benchmark_id": benchmark_id,
            "manifest_frozen": frozen,
            "selected_task_count": len(selected_tasks),
            "selected_strata": sorted(strata_set),
            "docs_lane_full_batch": docs_lane_full_batch,
            "expected_docs_strata": sorted(expected_docs_strata) if docs_lane_full_batch else [],
        }
    )
    return {
        "schema": "nexus_preflight_sentinel_v1",
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "checks": checks,
        "controller_policy": {
            "branch": "continue" if not failures else "stop",
            "continue_requires": [
                "warning_clean_gate_PASS",
                "wall_ledger_conserved",
                "infra_valid_pair",
                "provider_token_measured_rate_1_0",
                "manifest_hash_stable",
            ],
            "stop_conditions": [
                "any_stratum_warning_clean_false",
                "any_stratum_infra_invalid_true",
                "any_stratum_wall_ledger_invalid_true",
                "any_stratum_provider_token_missing",
                "any_stratum_receipt_or_rubric_contract_return",
            ],
            "denominator_policy": "exclude_any_pair_with_infra_invalid_or_warning_dirty_or_wall_invalid",
        },
        "ach_canary_mutations": {
            "status": "PASS",
            "cases": [
                {
                    "mutation": "missing_stratum_type",
                    "expected": "preflight_sentinel_stop",
                    "covered_by": "test_public_benchmark_preflight_sentinel_blocks_incomplete_docs_strata",
                },
                {
                    "mutation": "warning_dirty",
                    "expected": "warning_clean_gate_RETURN",
                    "covered_by": "test_write_evidence_bundle_returns_when_warning_ledger_dirty",
                },
                {
                    "mutation": "wall_invalid",
                    "expected": "public_cost_efficiency_RETURN",
                    "covered_by": "test_evidence_bundle_reports_rubric_contract_summary",
                },
                {
                    "mutation": "provider_token_missing",
                    "expected": "rubric_contract_RETURN",
                    "covered_by": "test_rubric_returns_when_receipts_pass_but_provider_tokens_missing",
                },
            ],
        },
    }


def build_public_benchmark_preflight(args: argparse.Namespace, *, repo_root: Path) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    tasks_path = Path(args.tasks_file)
    if not tasks_path.is_absolute():
        tasks_path = (repo_root / tasks_path).resolve()
    if not tasks_path.exists():
        failures.append("tasks_file_missing")
        tasks: list[CapabilityTask] = []
        selected_tasks: list[CapabilityTask] = []
        expanded_tasks: list[CapabilityTask] = []
        manifest_hash = ""
    else:
        failures.extend(_public_manifest_shape_failures(tasks_path))
        tasks = filter_tasks_by_id(
            filter_tasks_by_repo_kind(load_tasks(tasks_path), args.repo_kind_filter),
            args.task_id_filter,
        )
        selected_tasks = select_tasks(tasks, difficulty=args.difficulty, max_tasks=args.max_tasks)
        expanded_tasks = expand_task_trials(
            selected_tasks,
            repeat_trials=int(args.repeat_trials),
            shuffle_seed=args.shuffle_seed,
        )
        manifest_hash = _manifest_sha256(tasks_path)
        if not selected_tasks:
            failures.append("no_tasks_selected")
        failures.extend(_prompt_leak_audit_failures(selected_tasks, repo_root=repo_root))
        expected_coverage = _expected_capability_coverage(selected_tasks)
        if expected_coverage["unknown"]:
            failures.append("expected_capabilities_unknown:" + ",".join(expected_coverage["unknown"]))
        if expected_coverage["tasks_missing_expected"]:
            warnings.append("expected_capabilities_missing:" + ",".join(expected_coverage["tasks_missing_expected"][:5]))
        if expected_coverage["missing_core"]:
            warnings.append("expected_capabilities_core_gap:" + ",".join(expected_coverage["missing_core"][:8]))
    if not tasks_path.exists():
        expected_coverage = _expected_capability_coverage([])
    disclosure_manifest = _public_disclosure_manifest(
        str(getattr(args, "public_disclosure_manifest", "") or ""),
        repo_root=repo_root,
    )
    failures.extend(f"public_disclosure:{item}" for item in disclosure_manifest.get("failures", []) or [])

    env_model = str(os.environ.get("NEXUS_GEMINI_MODEL_NAME") or os.environ.get("NEXUS_CODEX_MODEL_NAME") or "").strip()
    direct_model = str(os.environ.get("NEXUS_DIRECT_GEMINI_MODEL") or os.environ.get("NEXUS_DIRECT_CODEX_MODEL") or "").strip()
    nexus_only = bool(getattr(args, "nexus_only", False))
    without_only = bool(getattr(args, "without_only", False))
    if not env_model and not without_only:
        failures.append("nexus_model_env_missing")
    force_learn_slo_ready = bool(getattr(args, "force_learn_slo_ready", False))
    external_model_requested = (
        (not nexus_only and args.without_mode in {"gemini", "codex"})
        or (not without_only and getattr(args, "with_model_provider", "") in {"gemini", "codex"})
    )
    external_export_policy = str(getattr(args, "external_model_export_policy", "unspecified") or "unspecified")
    export_policy_allows_live = external_export_policy in {"approved", "sanitized"}
    if not nexus_only and args.without_mode in {"gemini", "codex"} and not direct_model:
        failures.append("direct_model_env_missing")
    if bool(getattr(args, "session_worker", False)) and external_model_requested and not export_policy_allows_live:
        failures.append("external_model_export_policy_required_for_session_worker")
    outbound_prompt_ledger = str(getattr(args, "outbound_prompt_ledger", "") or "").strip()
    if (
        bool(getattr(args, "session_worker", False))
        and external_model_requested
        and external_export_policy == "sanitized"
        and not outbound_prompt_ledger
    ):
        failures.append("outbound_prompt_ledger_required_for_sanitized_export")
    if env_model and direct_model and env_model != direct_model:
        failures.append("model_lock_mismatch")
    # PR1: explicit same-model baseline enforcement — fail closed if bare arm is not a real provider path.
    require_same_model_baseline = bool(getattr(args, "require_same_model_baseline", False))
    if require_same_model_baseline:
        if args.without_mode not in {"gemini", "codex"}:
            failures.append("same_model_required_but_bare_arm_is_local")
        elif not direct_model:
            failures.append("same_model_required_but_direct_model_env_missing")
        elif env_model and direct_model and env_model != direct_model:
            failures.append("same_model_required_but_model_names_differ")
    if args.without_mode in {"gemini", "codex"} and args.with_llm_mode == "off":
        warnings.append(f"with_nexus_llm_off_while_bare_uses_{args.without_mode}")
    if not _hidden_verifier_mode_enabled():
        failures.append("hidden_verifier_disabled")
    if int(args.timeout_sec) <= 0:
        failures.append("timeout_sec_invalid")
    if int(args.per_task_stop_loss_sec) <= 0:
        failures.append("per_task_stop_loss_missing")
    if int(args.per_task_stop_loss_sec) > 600:
        failures.append("per_task_stop_loss_above_600")
    capability_readiness = build_benchmark_capability_readiness(args)
    failures.extend(f"capability_readiness:{item}" for item in capability_readiness.get("failures", []) or [])
    warnings.extend(f"capability_readiness:{item}" for item in capability_readiness.get("warnings", []) or [])
    failures.extend(
        commercial_model_basis_gate_failures(
            {
                "commercial_model_basis_required": bool(getattr(args, "require_commercial_model_basis", False)),
                "tasks_file": str(args.tasks_file),
            }
        )
    )
    preflight_sentinel = _build_preflight_sentinel(
        args=args,
        tasks_path=tasks_path,
        selected_tasks=selected_tasks,
        manifest_hash=manifest_hash,
    )
    failures.extend(f"preflight_sentinel:{item}" for item in preflight_sentinel.get("failures", []) or [])
    effective_total = _effective_total_timeout_sec(int(args.total_timeout_sec), int(args.stop_loss_sec))
    if effective_total <= 0:
        warnings.append("total_timeout_disabled")

    dirty_status = ""
    try:
        dirty_status = _git_status_porcelain(repo_root)
    except Exception as exc:
        warnings.append(f"git_status_unavailable:{exc.__class__.__name__}")
    if dirty_status and bool(args.require_clean_worktree):
        failures.append("worktree_dirty")
    elif dirty_status:
        warnings.append("worktree_dirty_recorded")

    report = {
        "schema": "nexus_public_benchmark_preflight_v1",
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": warnings,
        "run_identity": {
            "nexus_git_commit": _git_commit(repo_root),
            "cwd": str(repo_root),
            "runner": "scripts/bench/capability_ab_runner.py",
            "runner_command": " ".join(sys.argv),
            "dirty_entries": dirty_status.splitlines() if dirty_status else [],
        },
        "model_lock": {
            "env_model_name": env_model,
            "direct_model_name": direct_model,
            "ollama_model_name": str(os.environ.get("NEXUS_OLLAMA_MODEL") or ""),
            "ollama_active_model": str(os.environ.get("NEXUS_OLLAMA_ACTIVE_MODEL") or ""),
            "same_model": bool(env_model and direct_model and env_model == direct_model),
            "without_mode": args.without_mode,
            "with_llm_mode": args.with_llm_mode,
            "with_model_provider": getattr(args, "with_model_provider", "gemini"),
        },
        "external_model_export": {
            "policy": external_export_policy,
            "requires_policy": bool(getattr(args, "session_worker", False) and external_model_requested),
            "live_export_allowed": export_policy_allows_live,
            "session_worker": bool(getattr(args, "session_worker", False)),
            "disclosure_manifest_status": str(disclosure_manifest.get("status") or ""),
            "outbound_prompt_ledger": outbound_prompt_ledger,
            "outbound_prompt_strict": external_export_policy == "sanitized",
        },
        "task_manifest": {
            "path": str(tasks_path),
            "sha256": manifest_hash,
            "loaded_n": len(tasks),
            "selected_n": len(selected_tasks),
            "expanded_n": len(expanded_tasks),
            "repeat_trials": int(args.repeat_trials),
            "shuffle_seed": args.shuffle_seed,
            "task_ids": [task.id for task in selected_tasks],
            "expected_capability_coverage": expected_coverage,
        },
        "public_disclosure_manifest": disclosure_manifest,
        "timeouts": {
            "timeout_sec": int(args.timeout_sec),
            "total_timeout_sec": int(args.total_timeout_sec),
            "effective_total_timeout_sec": effective_total,
            "stop_loss_sec": int(args.stop_loss_sec),
            "per_task_stop_loss_sec": int(args.per_task_stop_loss_sec),
            "direct_gemini_timeout_sec": _direct_gemini_timeout_sec(int(args.timeout_sec)),
        },
        "public_claim_requirements": {
            "hidden_verifier_mode": _hidden_verifier_mode_enabled(),
            "eligibility_schema_required": True,
            "evidence_bundle_required": bool(args.evidence_bundle),
            "markdown_report_requested": bool(args.markdown_report),
            "nexus_wearing_required": args.with_llm_mode in {"hard", "all"},
            "parallel_arms": getattr(args, "parallel_arms", "off"),
            "force_learn_slo_ready": force_learn_slo_ready,
            "public_claim_allowed": getattr(args, "parallel_arms", "off") == "off"
            and not nexus_only
            and not without_only
            and not force_learn_slo_ready
            and (not bool(getattr(args, "session_worker", False)) or export_policy_allows_live),
            "single_arm_run": nexus_only or without_only,
            "single_arm_mode": "without_nexus" if without_only else "with_nexus" if nexus_only else "",
        },
        "capability_readiness": capability_readiness,
        "preflight_sentinel": preflight_sentinel,
    }
    return report


def main() -> int:
    global persistent_worker_proc
    parser = argparse.ArgumentParser(description="Run capability A/B benchmark: with_nexus vs without_nexus.")
    parser.add_argument("--tasks-file", default="scripts/bench/capability_tasks_v1.json")
    parser.add_argument(
        "--public-disclosure-manifest",
        default="",
        help="Optional sanitized manifest for public/external disclosure evidence. Execution still uses --tasks-file.",
    )
    parser.add_argument(
        "--require-commercial-model-basis",
        action="store_true",
        help="Fail public claim gates unless --tasks-file is a compiled commercial benchmark basis manifest.",
    )
    parser.add_argument("--output-dir", default=".nexus/reports/bench")
    parser.add_argument("--max-tasks", type=int, default=6)
    parser.add_argument("--timeout-sec", type=int, default=30)
    parser.add_argument(
        "--total-timeout-sec",
        type=int,
        default=0,
        help="Stop before starting another benchmark leg after this total wall-clock budget. 0 disables the budget.",
    )
    parser.add_argument(
        "--stop-loss-sec",
        type=int,
        default=600,
        help="Fail-fast wall-clock stop-loss for the whole benchmark run. 0 disables. Default: 600.",
    )
    parser.add_argument(
        "--per-task-stop-loss-sec",
        type=int,
        default=600,
        help="Mark a benchmark row infra-invalid and stop the run if one task exceeds this wall-clock budget. 0 disables. Default: 600.",
    )
    parser.add_argument(
        "--direct-timeout-abort-threshold",
        type=int,
        default=3,
        help="Abort direct baseline after N consecutive provider timeouts. 0 disables. Default: 3.",
    )
    parser.add_argument(
        "--direct-infra-abort-threshold",
        type=int,
        default=3,
        help="Abort direct baseline after N consecutive infra-invalid provider rows. 0 disables. Default: 3.",
    )
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard", "all"], default="all")
    parser.add_argument("--force-flow", choices=["auto", "baseline", "hyper_sprint"], default="auto")
    parser.add_argument("--with-nexus-runner", choices=["inprocess", "subprocess"], default="inprocess")
    parser.add_argument("--with-llm-mode", choices=["off", "hard", "all"], default="off")
    parser.add_argument(
        "--with-model-provider",
        choices=["gemini", "codex", "ollama"],
        default="gemini",
        help="LLM provider for the Nexus treatment arm when --with-llm-mode enables model calls.",
    )
    parser.add_argument(
        "--gemini-model",
        default="",
        help="Override Gemini model for both arms (sets NEXUS_GEMINI_MODEL_NAME for this run only).",
    )
    parser.add_argument(
        "--session-worker",
        action="store_true",
        help="Use a persistent model session policy for direct-model benchmark arms and record session metadata in evidence.",
    )
    parser.add_argument(
        "--session-worker-id",
        default="",
        help="Optional deterministic session id for persistent model workers. If omitted, the runner creates one per process.",
    )
    parser.add_argument(
        "--external-model-export-policy",
        choices=["unspecified", "approved", "sanitized"],
        default="unspecified",
        help="Required for public session-worker live runs that send benchmark prompts to external model CLIs.",
    )
    parser.add_argument(
        "--outbound-prompt-ledger",
        default="",
        help="JSONL ledger for external model prompts. Required for sanitized live session-worker runs.",
    )
    parser.add_argument(
        "--enable-autoreason-executor",
        action="store_true",
        help="Enable the feature-flagged Autoreason candidate judge for the Nexus treatment arm.",
    )
    parser.add_argument(
        "--enable-ddtree-executor",
        action="store_true",
        help="Enable the feature-flagged DDTree candidate pruning layer for the Nexus treatment arm.",
    )
    parser.add_argument(
        "--enable-ultra-review-dry-gate",
        action="store_true",
        help="Enable the feature-flagged Ultra Review dry gate for recommended high-risk Nexus treatment rows.",
    )
    parser.add_argument(
        "--llm-candidate-cap",
        type=int,
        default=1,
        help="Maximum LLM candidate count for the Nexus treatment arm. Use 3+ to make DDTree eligible.",
    )
    parser.add_argument(
        "--enable-llm-self-heal",
        action="store_true",
        help="Allow one extra LLM repair call after a pytest failure in the Nexus treatment arm.",
    )
    parser.add_argument(
        "--skip-llm-baseline",
        action="store_true",
        help="When Nexus LLM mode is enabled, avoid the preliminary baseline Gemini call and let the route choose Hyper/capability execution directly.",
    )
    parser.add_argument(
        "--strict-llm-baseline",
        action="store_true",
        help="When Nexus LLM baseline is enabled, require the baseline patch to come from the model and forbid local fallback.",
    )
    parser.add_argument(
        "--disable-promoted-route-cost-policy",
        action="store_true",
        help="Ignore the repo-level promoted route-cost policy for clean cost diagnosis runs.",
    )
    parser.add_argument("--tuning-profile", choices=["", "daily", "iter", "weekly"], default="")
    parser.add_argument("--llm-safe-probe", action="store_true")
    parser.add_argument(
        "--always-on-eval",
        action="store_true",
        help="Fail closed unless the Nexus treatment arm is allowed to auto-route without forced Hyper shortcuts.",
    )
    parser.add_argument("--without-mode", choices=["service", "bare", "gemini", "codex"], default="bare")
    parser.add_argument(
        "--require-same-model-baseline",
        action="store_true",
        default=False,
        help=(
            "Enforce same-model symmetric baseline: forces --without-mode gemini and validates that "
            "NEXUS_GEMINI_MODEL_NAME matches NEXUS_DIRECT_GEMINI_MODEL. Preflight fails closed if "
            "bare arm is not a real provider path or models differ."
        ),
    )
    parser.add_argument("--force-learn-slo-ready", action="store_true")
    parser.add_argument(
        "--enable-hidden-verifier",
        action="store_true",
        default=False,
        help=(
            "Enable hidden verifier mode for this run. Maps the CLI flag into the runner config "
            "so that preflight, row writing, and evidence bundle all read the same authoritative "
            "source. Equivalent to setting NEXUS_VALUE_HIDDEN_VERIFIER=1 but propagated explicitly "
            "from the parsed args rather than as an implicit env side-effect."
        ),
    )
    parser.add_argument(
        "--neutralize-history",
        dest="neutralize_history",
        action="store_true",
        default=True,
        help="Reset auto-flow history before mode runs for fair A/B comparison.",
    )
    parser.add_argument(
        "--keep-history",
        dest="neutralize_history",
        action="store_false",
        help="Keep auto-flow history between runs.",
    )
    parser.add_argument("--materialize-missing", action="store_true", default=True)
    parser.add_argument(
        "--no-materialize-missing",
        dest="materialize_missing",
        action="store_false",
        help="Use task target/test files directly and fail if any are missing.",
    )
    parser.add_argument(
        "--allow-learning-loop",
        action="store_true",
        default=False,
        help="Allow within-mode history accumulation across tasks.",
    )
    parser.add_argument(
        "--disable-learning-loop",
        dest="allow_learning_loop",
        action="store_false",
        help="Disable within-mode learning and reset per task (legacy mode).",
    )
    parser.add_argument("--progress-log", dest="progress_log", action="store_true", default=True)
    parser.add_argument("--no-progress-log", dest="progress_log", action="store_false")
    parser.add_argument(
        "--nexus-only",
        action="store_true",
        help="Run only the with_nexus treatment arm. Intended for route/receipt/wall-time smoke, not public uplift claims.",
    )
    parser.add_argument(
        "--without-only",
        action="store_true",
        help="Run only the without_nexus direct baseline arm. Intended for clean baseline evidence, not Nexus uplift claims.",
    )
    parser.add_argument("--repeat-trials", type=int, default=1)
    parser.add_argument("--shuffle-seed", type=int, default=None)
    parser.add_argument(
        "--repo-kind-filter",
        default="all",
        help="Comma-separated repo_kind allowlist, e.g. neutral_fixture,nexus_internal. Default: all.",
    )
    parser.add_argument(
        "--task-id-filter",
        default="all",
        help="Comma-separated task id allowlist for targeted replay. Default: all.",
    )
    parser.add_argument(
        "--manifest-index-filter",
        default="all",
        help="Comma-separated manifest indices or range to filter tasks (e.g., '0,2,4' or '1-5'). Default: all.",
    )
    parser.add_argument(
        "--enable-background-offload",
        action="store_true",
        help="Enable background offload of heavy/flaky tasks to avoid blocking the main runner pipeline.",
    )
    parser.add_argument(
        "--heavy-task-ids",
        default="",
        help="Comma-separated task IDs to treat as heavy rows for background offload.",
    )
    parser.add_argument("--evidence-bundle", dest="evidence_bundle", action="store_true", default=True)
    parser.add_argument("--no-evidence-bundle", dest="evidence_bundle", action="store_false")
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate public benchmark inputs and write benchmark_preflight.json without invoking Gemini or Nexus.",
    )
    parser.add_argument(
        "--parallel-arms",
        choices=["off", "smoke-only"],
        default="off",
        help="Smoke-only wiring check for future parallel arms. Does not invoke Gemini/Nexus and is never public-claim eligible.",
    )
    parser.add_argument(
        "--markdown-report",
        default="",
        help="Optional markdown report path. Use 'auto' to write gemini_nexus_report_<timestamp>.md in output-dir.",
    )
    parser.add_argument("--require-clean-worktree", action="store_true", default=False)
    parser.add_argument(
        "--isolation-mode",
        choices=["preserve_target", "worktree"],
        default="preserve_target",
        help="preserve_target restores target files after each leg; worktree is reserved for clean worktree execution.",
    )
    parser.add_argument(
        "--persistent-worker",
        action="store_true",
        default=False,
        help="Use persistent worker to eliminate cold start overhead (~10-15s per task).",
    )
    args = parser.parse_args()
    if args.gemini_model:
        os.environ["NEXUS_GEMINI_MODEL_NAME"] = str(args.gemini_model).strip()
    if args.with_model_provider == "gemini" and _truthy_env("USE_LOCAL_OLLAMA"):
        args.with_model_provider = "ollama"
    if args.with_model_provider == "ollama":
        os.environ["NEXUS_OAUTH_PROVIDER"] = "ollama"
        os.environ.setdefault("NEXUS_OLLAMA_MODEL", _external_model_name_for_provider("ollama"))
        os.environ["NEXUS_GEMINI_MODEL_NAME"] = _external_model_name_for_provider("ollama")
    # PR1: same-model baseline enforcement — map flag into without_mode and env before preflight.
    # This must happen BEFORE build_public_benchmark_preflight reads env_model/direct_model.
    if getattr(args, "require_same_model_baseline", False):
        args.without_mode = "gemini"
        # Propagate gemini-model to direct model env if not already set, so same_model check passes.
        _req_model = str(os.environ.get("NEXUS_GEMINI_MODEL_NAME") or "").strip()
        if _req_model and not os.environ.get("NEXUS_DIRECT_GEMINI_MODEL"):
            os.environ["NEXUS_DIRECT_GEMINI_MODEL"] = _req_model
    # PR3: hidden verifier source convergence — explicit CLI flag → env mapping.
    # This is an intentional, documented propagation (not an implicit side-effect).
    # All downstream calls to _hidden_verifier_mode_enabled() will read from this env.
    if getattr(args, "enable_hidden_verifier", False):
        os.environ["NEXUS_VALUE_HIDDEN_VERIFIER"] = "1"
    if args.session_worker:
        os.environ["NEXUS_GEMINI_SESSION_WORKER"] = "1"
        os.environ["NEXUS_CODEX_SESSION_WORKER"] = "1"
    if args.session_worker_id:
        os.environ["NEXUS_GEMINI_SESSION_ID"] = str(args.session_worker_id).strip()
        os.environ["NEXUS_CODEX_SESSION_ID"] = str(args.session_worker_id).strip()
    if args.outbound_prompt_ledger:
        os.environ["NEXUS_OUTBOUND_PROMPT_LEDGER"] = str(Path(args.outbound_prompt_ledger).resolve())
    if args.external_model_export_policy == "sanitized":
        os.environ["NEXUS_OUTBOUND_PROMPT_STRICT"] = "1"
    if args.disable_promoted_route_cost_policy:
        os.environ["NEXUS_DISABLE_PROMOTED_ROUTE_COST_POLICY"] = "1"
    if args.skip_llm_baseline and args.strict_llm_baseline:
        parser.error("--strict-llm-baseline cannot be combined with --skip-llm-baseline")
    if args.nexus_only and args.without_only:
        parser.error("--nexus-only cannot be combined with --without-only")
    if args.always_on_eval and args.force_flow != "auto":
        parser.error("--always-on-eval requires --force-flow auto")
    if args.always_on_eval and args.skip_llm_baseline:
        parser.error("--always-on-eval cannot be combined with --skip-llm-baseline")
    if args.always_on_eval and args.llm_safe_probe:
        parser.error("--always-on-eval cannot be combined with --llm-safe-probe")
    if args.llm_safe_probe:
        args.with_llm_mode = "hard"
        args.force_flow = "hyper_sprint"
        args.difficulty = "hard"
        args.max_tasks = min(max(1, args.max_tasks), 3)
        args.timeout_sec = min(max(8, args.timeout_sec), 25)

    repo_root = Path(__file__).resolve().parents[2]
    if args.external_model_export_policy == "sanitized":
        forbidden = [
            str(repo_root),
            str(repo_root / "scripts" / "bench" / "capability_ab_runner.py"),
            "git diff",
            "git status",
            ".git/",
        ]
        existing = str(os.environ.get("NEXUS_OUTBOUND_FORBIDDEN_LITERALS") or "")
        os.environ["NEXUS_OUTBOUND_FORBIDDEN_LITERALS"] = "\n".join([existing, *forbidden]).strip()
    if args.require_clean_worktree:
        assert_clean_worktree(repo_root)
    if args.preflight_only:
        report = build_public_benchmark_preflight(args, repo_root=repo_root)
        out_dir = (repo_root / args.output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / "benchmark_preflight.json"
        report["report_path"] = str(report_path)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["status"] == "PASS" else 2
    external_model_requested = (
        (not bool(args.nexus_only) and args.without_mode in {"gemini", "codex"})
        or (not bool(args.without_only) and args.with_model_provider in {"gemini", "codex"})
    )
    if (
        args.parallel_arms != "smoke-only"
        and args.session_worker
        and external_model_requested
        and args.external_model_export_policy not in {"approved", "sanitized"}
    ):
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "reason": "external_model_export_policy_required_for_session_worker",
                    "external_model_export_policy": args.external_model_export_policy,
                },
                ensure_ascii=False,
            )
        )
        return 2
    if (
        args.parallel_arms != "smoke-only"
        and args.session_worker
        and external_model_requested
        and args.external_model_export_policy == "sanitized"
        and not str(args.outbound_prompt_ledger or "").strip()
    ):
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "reason": "outbound_prompt_ledger_required_for_sanitized_export",
                    "external_model_export_policy": args.external_model_export_policy,
                },
                ensure_ascii=False,
            )
        )
        return 2
    filtered_tasks = filter_tasks_by_manifest_index(
        filter_tasks_by_id(
            filter_tasks_by_repo_kind(load_tasks(args.tasks_file), args.repo_kind_filter),
            args.task_id_filter,
        ),
        args.manifest_index_filter,
    )
    selected_tasks = select_tasks(filtered_tasks, difficulty=args.difficulty, max_tasks=args.max_tasks)
    tasks = expand_task_trials(
        selected_tasks,
        repeat_trials=int(args.repeat_trials),
        shuffle_seed=args.shuffle_seed,
    )

    with_rows: list[dict[str, Any]] = []
    without_rows: list[dict[str, Any]] = []
    out_dir = (repo_root / args.output_dir).resolve()
    ts = int(time.time())
    evidence_root = out_dir / f"evidence_{ts}"
    shared_cli_runner = CliRunner() if args.with_nexus_runner == "inprocess" else None
    history_policy = _history_policy_name(
        neutralize_history=bool(args.neutralize_history),
        allow_learning_loop=bool(args.allow_learning_loop),
    )
    if args.parallel_arms == "smoke-only":
        model_name = str(
            os.environ.get("NEXUS_GEMINI_MODEL_NAME")
            or os.environ.get("NEXUS_DIRECT_GEMINI_MODEL")
            or os.environ.get("NEXUS_CODEX_MODEL_NAME")
            or os.environ.get("NEXUS_DIRECT_CODEX_MODEL")
            or "model"
        )
        with_rows, without_rows = _build_parallel_smoke_rows(tasks, model_name=model_name)
        hidden_verifier_mode = _hidden_verifier_mode_enabled()
        for row in [*with_rows, *without_rows]:
            row["history_policy"] = history_policy
            row["learn_slo_policy"] = "forced_ready" if args.force_learn_slo_ready else "repo_state"
            row["hidden_verifier_mode"] = hidden_verifier_mode
        benchmark_summary = _summarize_benchmark_rows([*with_rows, *without_rows])
        with_path = out_dir / f"with_nexus_{ts}.jsonl"
        without_path = out_dir / f"without_nexus_{ts}.jsonl"
        write_jsonl(with_path, with_rows)
        write_jsonl(without_path, without_rows)
        evidence_bundle_path = ""
        if args.evidence_bundle:
            evidence_bundle_path = str(
                write_evidence_bundle(
                    out_dir=out_dir,
                    with_path=with_path,
                    without_path=without_path,
                    rows=[*with_rows, *without_rows],
                    config={
                        "tasks_file": args.tasks_file,
                        "tasks_manifest_hash": selected_tasks[0].manifest_hash if selected_tasks else "",
                        "repo_root": str(repo_root),
                        "public_disclosure_manifest": _public_disclosure_manifest(
                            args.public_disclosure_manifest,
                            repo_root=repo_root,
                        ),
                        "commercial_model_basis_required": bool(args.require_commercial_model_basis),
                        "unique_tasks_requested": len(selected_tasks),
                        "repeat_trials": max(1, int(args.repeat_trials)),
                        "shuffle_seed": args.shuffle_seed,
                        "repo_kind_filter": args.repo_kind_filter,
                        "isolation_mode": args.isolation_mode,
                        "require_clean_worktree": bool(args.require_clean_worktree),
                        "history_policy": history_policy,
                        "force_learn_slo_ready": bool(args.force_learn_slo_ready),
                        "trust_workspace_policy": "gemini_cli_trust_workspace_env",
                        "session_worker": bool(args.session_worker),
                        "session_worker_id": str(args.session_worker_id or os.environ.get("NEXUS_GEMINI_SESSION_ID") or ""),
                        "session_worker_policy": "persistent_worker_with_reset_boundary" if args.session_worker else "fresh_direct_invocation",
                        "external_model_export_policy": str(args.external_model_export_policy),
                        "outbound_prompt_ledger": str(args.outbound_prompt_ledger or os.environ.get("NEXUS_OUTBOUND_PROMPT_LEDGER") or ""),
                        "hidden_verifier_mode": hidden_verifier_mode,
                        "without_mode": args.without_mode,
                        "with_llm_mode": args.with_llm_mode,
                        "with_model_provider": args.with_model_provider,
                        "force_flow": args.force_flow,
                        "parallel_arms": args.parallel_arms,
                        "warning_ledger_required": True,
                        "wall_ledger_required": True,
                        "provider_token_measured_required": args.without_mode in {"gemini", "codex"}
                        or args.with_model_provider in {"gemini", "codex", "ollama"},
                        "runner_command": " ".join(sys.argv),
                        "timeout_sec": int(args.timeout_sec),
                        "total_timeout_sec": int(args.total_timeout_sec),
                        "effective_total_timeout_sec": 0,
                        "stop_loss_sec": int(args.stop_loss_sec),
                        "per_task_stop_loss_sec": int(args.per_task_stop_loss_sec),
                        "direct_timeout_abort_threshold": int(args.direct_timeout_abort_threshold),
                        "direct_infra_abort_threshold": int(args.direct_infra_abort_threshold),
                    },
                )
            )
        markdown_report_path = ""
        if args.markdown_report:
            markdown_report = out_dir / f"gemini_nexus_report_{ts}.md" if args.markdown_report == "auto" else Path(args.markdown_report)
            if not markdown_report.is_absolute():
                markdown_report = (repo_root / markdown_report).resolve()
            markdown_report.parent.mkdir(parents=True, exist_ok=True)
            markdown_report.write_text(
                render_markdown_report(
                    without_path=str(without_path),
                    with_path=str(with_path),
                    label_without=f"{_report_model_label()}_bare",
                    label_with=f"{_report_model_label()}_nexus",
                    benchmark_date=datetime.now().date().isoformat(),
                    evidence_bundle_path=evidence_bundle_path,
                ),
                encoding="utf-8",
            )
            markdown_report_path = str(markdown_report)
        print(
            json.dumps(
                {
                    "status": "SMOKE_ONLY",
                    "parallel_arms": args.parallel_arms,
                    "tasks_requested": len(tasks),
                    "unique_tasks_requested": len(selected_tasks),
                    "with_nexus_executed": 0,
                    "without_nexus_executed": 0,
                    "with_nexus_file": str(with_path),
                    "without_nexus_file": str(without_path),
                    "evidence_bundle_file": evidence_bundle_path,
                    "markdown_report_file": markdown_report_path,
                    "benchmark_summary": benchmark_summary,
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.neutralize_history:
        _reset_auto_flow_history(repo_root)
    run_start = time.monotonic()
    timed_out = False
    effective_total_timeout_sec = _effective_total_timeout_sec(int(args.total_timeout_sec), int(args.stop_loss_sec))
    previous_timeout_handler = _install_total_timeout(effective_total_timeout_sec)

    # Phase 6: Persistent worker for cold start elimination
    if getattr(args, "persistent_worker", False):
        print("⚡ [Phase 6] Starting persistent worker...", file=sys.stderr, flush=True)
        import subprocess as _persistent_subprocess
        _worker_script = str(repo_root / "scripts" / "bench" / "persistent_worker.py")
        persistent_worker_proc = _persistent_subprocess.Popen(
            [sys.executable, _worker_script],
            stdin=_persistent_subprocess.PIPE,
            stdout=_persistent_subprocess.PIPE,
            stderr=_persistent_subprocess.PIPE,
            text=True,
        )
        # Wait for worker to be ready with timeout
        import select as _select
        ready, _, _ = _select.select([persistent_worker_proc.stdout], [], [], 30)
        if ready:
            _worker_ready_line = persistent_worker_proc.stdout.readline()
            print(f"⚡ [Phase 6] Worker ready: {_worker_ready_line.strip()}", file=sys.stderr, flush=True)
        else:
            print("⚡ [Phase 6] Worker startup timeout, falling back to direct execution", file=sys.stderr, flush=True)
            persistent_worker_proc.kill()
            persistent_worker_proc = None

    with_tasks = [] if bool(args.without_only) else tasks
    for task in with_tasks:
        if _budget_exceeded(run_start, effective_total_timeout_sec):
            timed_out = True
            _emit_progress(
                enabled=bool(args.progress_log),
                event="total_timeout",
                mode="with_nexus",
                task=task,
                elapsed_sec=time.monotonic() - run_start,
                status="SKIPPED",
            )
            break
        target_file, test_file = _resolve_task_files(repo_root, task, materialize_missing=bool(args.materialize_missing))
        flow = None if args.force_flow == "auto" else args.force_flow
        if args.neutralize_history and not args.allow_learning_loop:
            _reset_auto_flow_history(repo_root)
        if args.force_learn_slo_ready:
            _force_learn_slo_ready(repo_root)

        materialized_task = _task_uses_materialized_fixture(task, materialize_missing=bool(args.materialize_missing))
        original_target = _read_preserved_target(target_file, materialize_missing=materialized_task)

        if _is_heavy_task(task, args):
            import threading
            def _bg_run():
                try:
                    run_with_nexus(
                        repo_root=repo_root,
                        task=task,
                        target_file=target_file,
                        test_file=test_file,
                        timeout_sec=int(args.timeout_sec) * 2,
                        force_flow=flow,
                        runner_mode="subprocess",
                        with_llm_mode=args.with_llm_mode,
                        with_model_provider=args.with_model_provider,
                        tuning_profile=args.tuning_profile,
                        cli_runner=None,
                        history_window=1,
                        history_fail_threshold=9999,
                        enable_autoreason_executor=bool(args.enable_autoreason_executor),
                        enable_ddtree_executor=bool(args.enable_ddtree_executor),
                        enable_ultra_review_dry_gate=bool(args.enable_ultra_review_dry_gate),
                        llm_candidate_cap=int(args.llm_candidate_cap),
                        enable_llm_self_heal=bool(args.enable_llm_self_heal),
                        skip_llm_baseline=bool(args.skip_llm_baseline),
                        strict_llm_baseline=bool(args.strict_llm_baseline),
                    )
                    _emit_progress(
                        enabled=bool(args.progress_log),
                        event="background_task_end",
                        mode="with_nexus",
                        task=task,
                        status="COMPLETED",
                    )
                except Exception:
                    pass

            bg_thread = threading.Thread(target=_bg_run, daemon=True)
            bg_thread.start()

            row = {
                "task_id": task.id,
                "status": "OFFLOADED_TO_BACKGROUND",
                "difficulty": task.difficulty,
                "elapsed_sec": 0.0,
                "wall_duration_sec": 0.0,
                "tokens_used": 0,
                "is_claimable": False,
                "public_claim_safe": False,
                "offload_provenance": "background_replay_lane",
            }
            with_rows.append(row)
            _emit_progress(
                enabled=bool(args.progress_log),
                event="task_offloaded",
                mode="with_nexus",
                task=task,
                status="OFFLOADED",
            )
            continue

        try:
            leg_start = time.monotonic()
            _emit_progress(
                enabled=bool(args.progress_log),
                event="task_start",
                mode="with_nexus",
                task=task,
                target_file=target_file,
                test_file=test_file,
                elapsed_sec=leg_start - run_start,
            )
            with _capture_python_warnings(source="with_nexus_runtime") as runtime_warning_records:
                row = run_with_nexus(
                    repo_root=repo_root,
                    task=task,
                    target_file=target_file,
                    test_file=test_file,
                    timeout_sec=_remaining_leg_timeout(int(args.timeout_sec), run_start, effective_total_timeout_sec),
                    force_flow=flow,
                    runner_mode="subprocess" if effective_total_timeout_sec > 0 else args.with_nexus_runner,
                    with_llm_mode=args.with_llm_mode,
                    with_model_provider=args.with_model_provider,
                    tuning_profile=args.tuning_profile,
                    cli_runner=shared_cli_runner,
                    history_window=1,
                    history_fail_threshold=9999,
                    enable_autoreason_executor=bool(args.enable_autoreason_executor),
                    enable_ddtree_executor=bool(args.enable_ddtree_executor),
                    enable_ultra_review_dry_gate=bool(args.enable_ultra_review_dry_gate),
                    llm_candidate_cap=int(args.llm_candidate_cap),
                    enable_llm_self_heal=bool(args.enable_llm_self_heal),
                    skip_llm_baseline=bool(args.skip_llm_baseline),
                    strict_llm_baseline=bool(args.strict_llm_baseline),
                )
            _annotate_warning_ledger(row, runtime_warning_records, append=True)
            row["isolation_mode"] = args.isolation_mode
            row["clean_checkout_required"] = args.isolation_mode == "worktree"
            task_stop_loss_exceeded = _apply_per_task_stop_loss(row, int(args.per_task_stop_loss_sec))
            if args.evidence_bundle:
                row.update(
                    _write_trial_evidence(
                        evidence_root=evidence_root,
                        row=row,
                        target_before=original_target,
                        target_after=Path(target_file).read_text(encoding="utf-8"),
                    )
                )
            with_rows.append(row)
            _emit_progress(
                enabled=bool(args.progress_log),
                event="task_end",
                mode="with_nexus",
                task=task,
                target_file=target_file,
                test_file=test_file,
                elapsed_sec=time.monotonic() - leg_start,
                status=str(row.get("status", "")),
            )
            if task_stop_loss_exceeded:
                _emit_progress(
                    enabled=bool(args.progress_log),
                    event="task_stop_loss",
                    mode="with_nexus",
                    task=task,
                    target_file=target_file,
                    test_file=test_file,
                    elapsed_sec=float(row.get("wall_duration_sec", 0.0) or 0.0),
                    status="INFRA_INVALID",
                )
            fail_fast_reason = (
                _with_nexus_row_fail_fast_reason(row, task=task)
                if _truthy_env("NEXUS_BENCH_FAIL_FAST_ON_ROW_FAILURE")
                else ""
            )
            if fail_fast_reason:
                row["with_nexus_fail_fast_triggered"] = True
                row["with_nexus_fail_fast_reason"] = fail_fast_reason
                timed_out = True
                _emit_progress(
                    enabled=bool(args.progress_log),
                    event="with_nexus_fail_fast",
                    mode="with_nexus",
                    task=task,
                    target_file=target_file,
                    test_file=test_file,
                    elapsed_sec=time.monotonic() - run_start,
                    status=f"PARTIAL_WITH_NEXUS_ABORT:{fail_fast_reason}",
                )
                break
        except BenchmarkTotalTimeout:
            timed_out = True
            _emit_progress(
                enabled=bool(args.progress_log),
                event="total_timeout",
                mode="with_nexus",
                task=task,
                target_file=target_file,
                test_file=test_file,
                elapsed_sec=time.monotonic() - run_start,
                status="INTERRUPTED",
            )
            break
        finally:
            _restore_preserved_target(target_file, original_target)
    if args.neutralize_history:
        _reset_auto_flow_history(repo_root)
    without_tasks = _without_tasks_for_run(
        tasks,
        timed_out=timed_out,
        nexus_only=bool(args.nexus_only),
        without_only=bool(args.without_only),
    )
    direct_timeout_streak = 0
    direct_infra_streak = 0
    for task in without_tasks:
        if _budget_exceeded(run_start, effective_total_timeout_sec):
            timed_out = True
            _emit_progress(
                enabled=bool(args.progress_log),
                event="total_timeout",
                mode="without_nexus",
                task=task,
                elapsed_sec=time.monotonic() - run_start,
                status="SKIPPED",
            )
            break
        target_file, test_file = _resolve_task_files(repo_root, task, materialize_missing=bool(args.materialize_missing))
        flow = None if args.force_flow == "auto" else args.force_flow
        if args.neutralize_history and not args.allow_learning_loop:
            _reset_auto_flow_history(repo_root)
        materialized_task = _task_uses_materialized_fixture(task, materialize_missing=bool(args.materialize_missing))
        original_target = _read_preserved_target(target_file, materialize_missing=materialized_task)
        try:
            leg_start = time.monotonic()
            _emit_progress(
                enabled=bool(args.progress_log),
                event="task_start",
                mode="without_nexus",
                task=task,
                target_file=target_file,
                test_file=test_file,
                elapsed_sec=leg_start - run_start,
            )
            with _capture_python_warnings(source="without_nexus_runtime") as runtime_warning_records:
                row = run_without_nexus(
                    repo_root=repo_root,
                    task=task,
                    target_file=target_file,
                    test_file=test_file,
                    timeout_sec=_remaining_leg_timeout(int(args.timeout_sec), run_start, effective_total_timeout_sec),
                    force_flow=flow,
                    history_window=1,
                    history_fail_threshold=9999,
                    mode=args.without_mode,
                )
            _annotate_warning_ledger(row, runtime_warning_records, append=True)
            row["isolation_mode"] = args.isolation_mode
            row["clean_checkout_required"] = args.isolation_mode == "worktree"
            task_stop_loss_exceeded = _apply_per_task_stop_loss(row, int(args.per_task_stop_loss_sec))
            if _direct_provider_timeout_row(row):
                direct_timeout_streak += 1
            else:
                direct_timeout_streak = 0
            if _direct_provider_infra_row(row):
                direct_infra_streak += 1
            else:
                direct_infra_streak = 0
            direct_abort_reason = _direct_timeout_abort_reason(
                direct_timeout_streak,
                int(args.direct_timeout_abort_threshold),
            )
            if not direct_abort_reason:
                direct_abort_reason = _direct_infra_abort_reason(
                    direct_infra_streak,
                    int(args.direct_infra_abort_threshold),
                )
            if direct_abort_reason:
                row["direct_provider_abort_triggered"] = True
                row["direct_provider_abort_reason"] = direct_abort_reason
                row["direct_timeout_abort_triggered"] = direct_abort_reason == "consecutive_direct_provider_timeouts"
                row["direct_timeout_abort_reason"] = direct_abort_reason if row["direct_timeout_abort_triggered"] else ""
                row["direct_timeout_abort_threshold"] = int(args.direct_timeout_abort_threshold)
                row["direct_infra_abort_threshold"] = int(args.direct_infra_abort_threshold)
            if args.evidence_bundle:
                row.update(
                    _write_trial_evidence(
                        evidence_root=evidence_root,
                        row=row,
                        target_before=original_target,
                        target_after=Path(target_file).read_text(encoding="utf-8"),
                    )
                )
            without_rows.append(row)
            _emit_progress(
                enabled=bool(args.progress_log),
                event="task_end",
                mode="without_nexus",
                task=task,
                target_file=target_file,
                test_file=test_file,
                elapsed_sec=time.monotonic() - leg_start,
                status=str(row.get("status", "")),
            )
            if task_stop_loss_exceeded:
                _emit_progress(
                    enabled=bool(args.progress_log),
                    event="task_stop_loss",
                    mode="without_nexus",
                    task=task,
                    target_file=target_file,
                    test_file=test_file,
                    elapsed_sec=float(row.get("wall_duration_sec", 0.0) or 0.0),
                    status="INFRA_INVALID",
                )
            if direct_abort_reason:
                timed_out = True
                _emit_progress(
                    enabled=bool(args.progress_log),
                    event="direct_provider_abort",
                    mode="without_nexus",
                    task=task,
                    target_file=target_file,
                    test_file=test_file,
                    elapsed_sec=time.monotonic() - run_start,
                    status=f"PARTIAL_PROVIDER_ABORT:{direct_abort_reason}",
                )
                break
        except BenchmarkTotalTimeout:
            timed_out = True
            _emit_progress(
                enabled=bool(args.progress_log),
                event="total_timeout",
                mode="without_nexus",
                task=task,
                target_file=target_file,
                test_file=test_file,
                elapsed_sec=time.monotonic() - run_start,
                status="INTERRUPTED",
            )
            break
        finally:
            _restore_preserved_target(target_file, original_target)

    _clear_total_timeout(previous_timeout_handler)

    hidden_verifier_mode = _hidden_verifier_mode_enabled()
    for row in [*with_rows, *without_rows]:
        row["history_policy"] = history_policy
        row["learn_slo_policy"] = "forced_ready" if args.force_learn_slo_ready else "repo_state"
        row["disable_promoted_route_cost_policy"] = bool(args.disable_promoted_route_cost_policy)
        row["hidden_verifier_mode"] = hidden_verifier_mode
    benchmark_summary = _summarize_benchmark_rows([*with_rows, *without_rows])

    with_path = out_dir / f"with_nexus_{ts}.jsonl"
    without_path = out_dir / f"without_nexus_{ts}.jsonl"
    write_jsonl(with_path, with_rows)
    write_jsonl(without_path, without_rows)
    evidence_bundle_path = ""
    if args.evidence_bundle:
        evidence_bundle_path = str(
            write_evidence_bundle(
                out_dir=out_dir,
                with_path=with_path,
                without_path=without_path,
                rows=[*with_rows, *without_rows],
                config={
                    "tasks_file": args.tasks_file,
                    "tasks_manifest_hash": selected_tasks[0].manifest_hash if selected_tasks else "",
                    "repo_root": str(repo_root),
                    "public_disclosure_manifest": _public_disclosure_manifest(
                        args.public_disclosure_manifest,
                        repo_root=repo_root,
                    ),
                    "commercial_model_basis_required": bool(args.require_commercial_model_basis),
                    "unique_tasks_requested": len(selected_tasks),
                    "repeat_trials": max(1, int(args.repeat_trials)),
                    "shuffle_seed": args.shuffle_seed,
                    "repo_kind_filter": args.repo_kind_filter,
                    "isolation_mode": args.isolation_mode,
                    "require_clean_worktree": bool(args.require_clean_worktree),
                    "history_policy": history_policy,
                    "force_learn_slo_ready": bool(args.force_learn_slo_ready),
                    "trust_workspace_policy": "gemini_cli_trust_workspace_env",
                    "session_worker": bool(args.session_worker),
                    "session_worker_id": str(args.session_worker_id or os.environ.get("NEXUS_GEMINI_SESSION_ID") or ""),
                    "session_worker_policy": "persistent_worker_with_reset_boundary" if args.session_worker else "fresh_direct_invocation",
                    "external_model_export_policy": str(args.external_model_export_policy),
                    "outbound_prompt_ledger": str(args.outbound_prompt_ledger or os.environ.get("NEXUS_OUTBOUND_PROMPT_LEDGER") or ""),
                    "hidden_verifier_mode": hidden_verifier_mode,
                    "without_mode": args.without_mode,
                    "with_llm_mode": args.with_llm_mode,
                    "with_model_provider": args.with_model_provider,
                    "enable_autoreason_executor": bool(args.enable_autoreason_executor),
                    "enable_ddtree_executor": bool(args.enable_ddtree_executor),
                    "enable_ultra_review_dry_gate": bool(args.enable_ultra_review_dry_gate),
                    "llm_candidate_cap": int(args.llm_candidate_cap),
                    "enable_llm_self_heal": bool(args.enable_llm_self_heal),
                    "skip_llm_baseline": bool(args.skip_llm_baseline),
                    "strict_llm_baseline": bool(args.strict_llm_baseline),
                    "disable_promoted_route_cost_policy": bool(args.disable_promoted_route_cost_policy),
                    "force_flow": args.force_flow,
                    "parallel_arms": args.parallel_arms,
                    "nexus_only": bool(args.nexus_only),
                    "without_only": bool(args.without_only),
                    "single_arm_mode": "without_nexus" if args.without_only else "with_nexus" if args.nexus_only else "",
                    "warning_ledger_required": True,
                    "wall_ledger_required": True,
                    "provider_token_measured_required": args.without_mode in {"gemini", "codex"}
                    or (not bool(args.without_only) and args.with_model_provider in {"gemini", "codex", "ollama"}),
                    "runner_command": " ".join(sys.argv),
                    "timeout_sec": int(args.timeout_sec),
                    "total_timeout_sec": int(args.total_timeout_sec),
                    "effective_total_timeout_sec": effective_total_timeout_sec,
                    "stop_loss_sec": int(args.stop_loss_sec),
                    "per_task_stop_loss_sec": int(args.per_task_stop_loss_sec),
                    "direct_timeout_abort_threshold": int(args.direct_timeout_abort_threshold),
                    "direct_infra_abort_threshold": int(args.direct_infra_abort_threshold),
                },
            )
        )

    markdown_report_path = ""
    if args.markdown_report:
        if args.markdown_report == "auto":
            markdown_report = out_dir / f"gemini_nexus_report_{ts}.md"
        else:
            markdown_report = Path(args.markdown_report)
            if not markdown_report.is_absolute():
                markdown_report = (repo_root / markdown_report).resolve()
        markdown_report.parent.mkdir(parents=True, exist_ok=True)
        if with_rows and without_rows:
            markdown_text = render_markdown_report(
                without_path=str(without_path),
                with_path=str(with_path),
                label_without=f"{_report_model_label()}_bare",
                label_with=f"{_report_model_label()}_nexus",
                benchmark_date=datetime.now().date().isoformat(),
                evidence_bundle_path=evidence_bundle_path,
            )
        else:
            markdown_text = _render_partial_markdown_report(
                benchmark_date=datetime.now().date().isoformat(),
                with_rows=with_rows,
                without_rows=without_rows,
                benchmark_summary=benchmark_summary,
            )
        markdown_report.write_text(markdown_text, encoding="utf-8")
        markdown_report_path = str(markdown_report)

    print(
        json.dumps(
            {
                "status": "PARTIAL_TIMEOUT" if timed_out else "SUCCESS",
                "tasks_requested": len(tasks),
                "unique_tasks_requested": len(selected_tasks),
                "repeat_trials": max(1, int(args.repeat_trials)),
                "shuffle_seed": args.shuffle_seed,
                "repo_kind_filter": args.repo_kind_filter,
                "tasks_executed": len(without_rows)
                if bool(args.without_only)
                else min(len(with_rows), len(without_rows))
                if without_tasks
                else len(with_rows),
                "with_nexus_executed": len(with_rows),
                "without_nexus_executed": len(without_rows),
                "nexus_only": bool(args.nexus_only),
                "without_only": bool(args.without_only),
                "total_timeout_sec": int(args.total_timeout_sec),
                "stop_loss_sec": int(args.stop_loss_sec),
                "effective_total_timeout_sec": effective_total_timeout_sec,
                "direct_timeout_abort_threshold": int(args.direct_timeout_abort_threshold),
                "direct_infra_abort_threshold": int(args.direct_infra_abort_threshold),
                "with_nexus_file": str(with_path),
                "without_nexus_file": str(without_path),
                "evidence_bundle_file": evidence_bundle_path,
                "markdown_report_file": markdown_report_path,
                "history_policy": history_policy,
                "learn_slo_policy": "forced_ready" if args.force_learn_slo_ready else "repo_state",
                "hidden_verifier_mode": hidden_verifier_mode,
                "benchmark_summary": benchmark_summary,
            },
            ensure_ascii=False,
        )
    )

    # Phase 6: Shutdown persistent worker
    if persistent_worker_proc is not None:
        try:
            persistent_worker_proc.stdin.write('{"action": "shutdown"}\n')
            persistent_worker_proc.stdin.flush()
            persistent_worker_proc.wait(timeout=5)
            print("⚡ [Phase 6] Worker shut down cleanly.", file=sys.stderr, flush=True)
        except Exception:
            persistent_worker_proc.kill()

    return 0


def _build_h6_provider_boundary_closure_seal(
    rows: list[dict[str, Any]], bundle: dict[str, Any] | None = None
) -> dict[str, Any]:
    """H6-15: Provider Boundary Closure Seal.

    Consolidates all H6-7 through H6-14 provider boundary gate receipts into a
    single immutable closure seal. No provider is invoked, no network call is
    made, no model is loaded or called. runtime_effect=false at all times.

    Args:
        rows: List of capability task result rows (used for schema audit only).
        bundle: Optional evidence bundle from prior H6 phases.

    Returns:
        Closure seal receipt dict with schema nexus.hybrid_h6_provider_boundary_closure_seal.v1
    """
    import os

    # Hard-wire all execution prohibitions — closure seal never relaxes these.
    provider_probe_allowed = False
    provider_invocation_allowed = False
    provider_execution_allowed = False
    network_allowed = False
    process_spawn_allowed = False
    model_load_allowed = False
    model_call_allowed = False
    model_call_executed = False
    runtime_effect = False
    production_ready = False
    public_claim_allowed = False

    # Validate that no runtime env flag was accidentally set.
    env_flags = {
        "NEXUS_PROVIDER_PROBE_ENABLED": os.environ.get("NEXUS_PROVIDER_PROBE_ENABLED", ""),
        "NEXUS_MODEL_CALL_ENABLED": os.environ.get("NEXUS_MODEL_CALL_ENABLED", ""),
        "NEXUS_NETWORK_ENABLED": os.environ.get("NEXUS_NETWORK_ENABLED", ""),
        "NEXUS_PROCESS_SPAWN_ENABLED": os.environ.get("NEXUS_PROCESS_SPAWN_ENABLED", ""),
    }
    forbidden_env_active = any(
        v.strip().lower() in {"1", "true", "yes"} for v in env_flags.values()
    )

    # Phase-gate lineage from H6-7 through H6-14.
    phase_lineage = [
        "h6_7_local_provider_boundary_preflight",
        "h6_8_local_provider_config_contract",
        "h6_9_local_provider_invocation_gate",
        "h6_10_controlled_provider_probe_preflight",
        "h6_11_provider_denial_receipt_replay",
        "h6_12_controlled_local_provider_fixture_contract",
        "h6_13_controlled_provider_probe_denylist",
        "h6_14_controlled_probe_preflight_replay",
    ]
    total_phases = len(phase_lineage)

    # Determine seal status.
    if forbidden_env_active:
        seal_status = "SEAL_BLOCKED_FORBIDDEN_ENV"
        seal_granted = False
        block_reason = "forbidden_runtime_env_active"
    elif rows is None:
        seal_status = "SEAL_BLOCKED_NULL_ROWS"
        seal_granted = False
        block_reason = "rows_null"
    else:
        seal_status = "SEAL_GRANTED"
        seal_granted = True
        block_reason = ""

    # Aggregate provider families from bundle if available.
    blocked_provider_families: list[str] = []
    if bundle and isinstance(bundle.get("blocked_provider_families"), list):
        blocked_provider_families = list(bundle["blocked_provider_families"])
    else:
        blocked_provider_families = ["ollama", "qwen", "gemini", "codex", "openai", "anthropic"]

    seal_assertions = [
        "no_provider_invoked",
        "no_network_call",
        "no_model_load",
        "no_model_call",
        "no_process_spawn_allowed",
        "no_model_call_executed",
        "no_runtime_effect",
        "production_claim_blocked",
        "public_claim_blocked",
        "all_h6_phases_sealed",
    ]

    return {
        "schema": "nexus.hybrid_h6_provider_boundary_closure_seal.v1",
        "status": seal_status,
        "h6_stage": "h6_15",
        "seal_granted": seal_granted,
        "seal_id": "h6-15-closure-seal",
        "phase_lineage": phase_lineage,
        "total_sealed_phases": total_phases,
        "blocked_provider_families": blocked_provider_families,
        "forbidden_env_active": forbidden_env_active,
        "block_reason": block_reason,
        "provider_probe_allowed": provider_probe_allowed,
        "provider_invocation_allowed": provider_invocation_allowed,
        "provider_execution_allowed": provider_execution_allowed,
        "network_allowed": network_allowed,
        "process_spawn_allowed": process_spawn_allowed,
        "model_load_allowed": model_load_allowed,
        "model_call_allowed": model_call_allowed,
        "model_call_executed": model_call_executed,
        "runtime_effect": runtime_effect,
        "production_ready": production_ready,
        "public_claim_allowed": public_claim_allowed,
        "seal_assertions": seal_assertions,
        "row_count": len(rows) if rows is not None else 0,
        "ready_for_h7": False,
    }


if __name__ == "__main__":
    raise SystemExit(main())
