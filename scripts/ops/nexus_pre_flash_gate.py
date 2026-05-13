#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.app.research_flow_service import _runtime_receipt_plan_payload, build_route
from nexus.engine.learning_policy_loader import audit_route_cost_policy
from nexus.engine.local_reflex import assess_local_reflex
from nexus.engine.mutation_assurance import (
    build_mutation_assurance_record,
    evaluate_mutation_assurance,
    mutation_assurance_required,
)
from nexus.engine.capability_wiring_audit import build_capability_wiring_audit
from nexus.engine.autodata_forge import DataForgeManifestRow, classify_trajectory_quality, write_data_forge_manifest
from nexus.engine.harness_sensors import (
    build_bdd_acceptance_receipt,
    build_harness_preflight_sensor,
    build_semantic_failure_sensor,
)
from nexus.engine.openseeker_alignment import build_openseeker_trace
from nexus.events.transport import NexusEventBus
from scripts.ops.codex_nexus_ab_smoke import benchmark_env as codex_smoke_env
from scripts.ops.codex_nexus_ab_smoke import build_command as codex_smoke_command
from scripts.ops.codex_nexus_ab_smoke import validate_smoke_plan as validate_codex_smoke_plan
from scripts.ops.render_brain_hub_coverage import build_coverage, validate_coverage_gate
from scripts.ops.brain_hub_audit import scan_brain_hub
from scripts.ops.hallucination_guard_drift import audit_drift
from scripts.ops.pipeline_composition_inventory import build_inventory


REPAIR_TASKS = (
    (
        "nexus-value-repair-001",
        "Repair the implementation after an intentionally tempting first patch breaks an invariant; "
        "success requires using the failure tail to produce a bounded second edit.",
    ),
    (
        "nexus-value-repair-002",
        "Repair a flaky-looking timeout calculation without deleting assertions; "
        "success requires preserving the behavioral contract and validating the actual failing branch.",
    ),
)

WEARING_CONTRACT = """

Nexus wearing contract:
- MemPalace: keep the solution inside the task scope and enforce explicit governance constraints.
- Belief: when evidence is incomplete or confidence is low, prefer a conservative fix backed by tests.
- Artifact/Claim: treat completion claims as valid only when backed by concrete artifacts or passing checks.
"""


def _ok(name: str, **details: Any) -> dict[str, Any]:
    return {"name": name, "passed": True, "details": details}


def _fail(name: str, reason: str, **details: Any) -> dict[str, Any]:
    return {"name": name, "passed": False, "reason": reason, "details": details}


def validate_repair_factory_skipped_routes(repo_root: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for task_id, desc in REPAIR_TASKS:
        route = build_route(
            repo_root=repo_root,
            task_desc=desc + WEARING_CONTRACT,
            task_type="public_test_repair",
            candidate_count=1,
            root_cause_confidence=1.0,
            findings_query=None,
            target_file=f".nexus/bench_cases/{task_id}/target.py",
        )
        stack = route.get("capability_stack", {}) if isinstance(route.get("capability_stack"), dict) else {}
        plan = route.get("capability_plan", {}) if isinstance(route.get("capability_plan"), dict) else {}
        selected_stack = set(stack.get("selected_capabilities", []) or [])
        selected_plan = set(plan.get("selected_capabilities", []) or [])
        readiness = (route.get("route_features", {}) or {}).get("candidate_factory_readiness_estimate", {})
        forbidden = {"autoreason", "judge_panel", "llm_judge_panel"}
        if forbidden & selected_stack:
            checks.append(
                _fail(
                    "repair_factory_skipped_route",
                    "ranking_layer_selected_in_compat_stack",
                    task_id=task_id,
                    readiness=readiness,
                    selected=sorted(selected_stack),
                )
            )
            continue
        if forbidden & selected_plan:
            checks.append(
                _fail(
                    "repair_factory_skipped_route",
                    "ranking_layer_selected_in_capability_plan",
                    task_id=task_id,
                    readiness=readiness,
                    selected=sorted(selected_plan),
                )
            )
            continue
        checks.append(
            _ok(
                "repair_factory_skipped_route",
                task_id=task_id,
                readiness=readiness,
                selected_stack=sorted(selected_stack),
                selected_plan=sorted(selected_plan),
            )
        )
    return checks


def validate_runtime_receipt_reconcile() -> list[dict[str, Any]]:
    pruned_capabilities: dict[str, Any] = {}
    pruned = _runtime_receipt_plan_payload(
        {"selected_capabilities": ["hyper", "autoreason", "judge_panel", "llm_judge_panel"]},
        {
            "capabilities": pruned_capabilities,
            "autoreason": {
                "status": "SKIPPED",
                "stop_reason": "candidate_factory_skipped",
                "judge_votes": [],
            },
        },
    )
    selected_pruned = set(pruned.get("selected_capabilities", []) or [])
    if {"autoreason", "judge_panel", "llm_judge_panel"} & selected_pruned:
        return [_fail("runtime_receipt_reconcile", "skipped_ranking_layer_not_pruned", selected=sorted(selected_pruned))]
    if not pruned_capabilities.get("runtime_pruned_capabilities"):
        return [_fail("runtime_receipt_reconcile", "runtime_pruned_capabilities_missing")]

    restored = _runtime_receipt_plan_payload(
        {"selected_capabilities": ["hyper"]},
        {
            "capabilities": {},
            "autoreason": {
                "enabled": True,
                "status": "SUCCESS",
                "winner": "AB",
                "judge_votes": [{"judge": "deterministic", "ranking": ["AB", "B", "A"]}],
            },
        },
    )
    selected_restored = set(restored.get("selected_capabilities", []) or [])
    if "autoreason" not in selected_restored:
        return [_fail("runtime_receipt_reconcile", "runtime_autoreason_success_not_restored", selected=sorted(selected_restored))]
    return [_ok("runtime_receipt_reconcile", pruned=sorted(selected_pruned), restored=sorted(selected_restored))]


def validate_brain_hub_alignment(repo_root: Path) -> list[dict[str, Any]]:
    drift = audit_drift()
    hub = scan_brain_hub(repo_root, [], manifest_path=repo_root / "docs" / "ops" / "brain_hub_manifest.json")
    checks: list[dict[str, Any]] = []
    if drift.passed:
        checks.append(
            _ok(
                "hallucination_guard_drift",
                runtime_probes=drift.runtime_probes,
                scoring_spec_rules=drift.scoring_spec_rules,
            )
        )
    else:
        checks.append(
            _fail(
                "hallucination_guard_drift",
                "drift_audit_failed",
                failures=drift.failures,
                runtime_probes=drift.runtime_probes,
            )
        )
    if hub.passed:
        checks.append(
            _ok(
                "brain_hub_audit",
                document_count=len(hub.documents),
                s_stage_runtime_contract=hub.runtime_checklist.get("s_stage_runtime_contract", {}),
            )
        )
    else:
        checks.append(
            _fail(
                "brain_hub_audit",
                "brain_hub_audit_failed",
                failures=hub.failures,
                s_stage_runtime_contract=hub.runtime_checklist.get("s_stage_runtime_contract", {}),
            )
        )
    return checks


def validate_event_contracts(repo_root: Path, *, strict_raw: bool | None = None, raw_policy: str | None = None) -> list[dict[str, Any]]:
    NexusEventBus.configure(repo_root)
    strict_raw = os.environ.get("NEXUS_EVENT_RAW_STRICT") == "1" if strict_raw is None else bool(strict_raw)
    if raw_policy is None:
        raw_policy = os.environ.get("NEXUS_EVENT_RAW_POLICY") or ("block" if strict_raw else "warn")
    audit = NexusEventBus.audit_event_contracts(raw_policy=raw_policy)
    if audit.get("passed"):
        return [
            _ok(
                "event_contract_audit",
                events_scanned=audit.get("events_scanned", 0),
                semantic_event_count=audit.get("semantic_event_count", 0),
                raw_event_count=audit.get("raw_event_count", 0),
                transition_status=audit.get("transition_status", ""),
                strict_raw_mode=audit.get("strict_raw_mode", False),
                raw_policy=audit.get("raw_policy", ""),
                warning_reasons=audit.get("warning_reasons", []),
                unknown_event_types=audit.get("unknown_event_types", []),
            )
        ]
    reason = "event_contract_audit_failed"
    failure_reasons = audit.get("failure_reasons", [])
    if "unknown_event_types_present" in failure_reasons:
        reason = "unknown_event_types_present"
    elif "raw_event_types_present" in failure_reasons:
        reason = "raw_event_types_present"
    return [
        _fail(
            "event_contract_audit",
            reason,
            events_scanned=audit.get("events_scanned", 0),
            raw_event_types=audit.get("raw_event_types", []),
            unknown_event_types=audit.get("unknown_event_types", []),
            strict_raw_mode=audit.get("strict_raw_mode", False),
            raw_policy=audit.get("raw_policy", ""),
            warning_reasons=audit.get("warning_reasons", []),
            failure_reasons=failure_reasons,
        )
    ]


def validate_codex_nexus_smoke_plan() -> list[dict[str, Any]]:
    task_ids = (
        "rlm-harder-v2-governance-001",
        "rlm-harder-v2-evidence-001",
        "rlm-harder-v2-belief-001",
        "rlm-harder-v2-memory-001",
    )
    cmd = codex_smoke_command(
        output_dir=".nexus/reports/bench_codex55_nexus_local_smoke",
        task_ids=task_ids,
        preflight_only=True,
    )
    payload = validate_codex_smoke_plan(cmd=cmd, env=codex_smoke_env("gpt-5.5"), task_ids=task_ids)
    if payload.get("passed"):
        return [_ok("codex_nexus_smoke_plan", **payload)]
    return [_fail("codex_nexus_smoke_plan", "codex_nexus_smoke_plan_invalid", **payload)]


def validate_brain_hub_coverage_gate(repo_root: Path) -> list[dict[str, Any]]:
    payload = build_coverage(repo_root, manifest=repo_root / "docs" / "ops" / "brain_hub_manifest.json")
    gate = validate_coverage_gate(payload)
    if gate.get("passed"):
        return [_ok("brain_hub_coverage_gate", **gate)]
    return [_fail("brain_hub_coverage_gate", "brain_hub_coverage_gate_failed", **gate)]


def _data_forge_manifest_summary(
    path: Path,
    rows: list[DataForgeManifestRow],
    *,
    write_manifest: bool,
) -> dict[str, Any]:
    if write_manifest:
        summary = write_data_forge_manifest(path, rows)
        summary["written"] = True
        return summary
    return {
        "schema_version": "nexus_autodata_forge_manifest_write.v1",
        "path": str(path),
        "row_count": len(rows),
        "gold_count": sum(1 for row in rows if row.label.label == "GOLD"),
        "training_eligible_count": sum(1 for row in rows if row.to_dict()["eligible_for_training"]),
        "written": False,
    }


def validate_openseeker_autodata_smoke(repo_root: Path, *, write_manifest: bool = False) -> list[dict[str, Any]]:
    receipts = [
        {"name": "semantic_searcher", "invoked": True, "evidence_refs": ["semantic:route:doc"]},
        {"name": "belief", "invoked": True, "evidence_refs": ["belief:route:confidence:0.8"]},
    ]
    trace = build_openseeker_trace(
        usage_trace={
            "route_decision": {
                "selected_capabilities": ["semantic_searcher", "belief"],
                "stop_policy": {"tactical_sequence": ["semantic_searcher", "belief"]},
            },
            "capabilities": {"claim_verified": True},
        },
        capability_receipts=receipts,
    )
    label = classify_trajectory_quality(strong_score=0.85, weak_score=0.55, audit_passed=True)
    row = DataForgeManifestRow(
        task_id="pre_flash_smoke",
        label=label,
        evidence_refs=tuple(ref for receipt in receipts for ref in receipt["evidence_refs"]),
        trajectory_step_count=max(10, int(trace["trajectory_step_count"])),
    )
    summary = _data_forge_manifest_summary(
        repo_root / ".nexus" / "reports" / "pre_flash_autodata_manifest.json",
        [row],
        write_manifest=write_manifest,
    )
    if trace.get("action_catalog_schema_version") != "nexus_openseeker_action_catalog.v1":
        return [_fail("openseeker_autodata_smoke", "action_catalog_missing", trace=trace)]
    if summary.get("training_eligible_count") != 1:
        return [_fail("openseeker_autodata_smoke", "autodata_training_eligibility_missing", summary=summary)]
    return [
        _ok(
            "openseeker_autodata_smoke",
            trajectory_step_count=trace.get("trajectory_step_count", 0),
            action_catalog_count=len(trace.get("action_catalog", [])),
            autodata_manifest=summary,
        )
    ]


def _autodata_manifest_counts(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "passed": False, "reason": "autodata_manifest_missing"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return {"path": str(path), "passed": False, "reason": "autodata_manifest_rows_invalid"}
    missing_evidence = [row.get("task_id", "") for row in rows if isinstance(row, dict) and not row.get("evidence_refs")]
    return {
        "path": str(path),
        "passed": True,
        "row_count": len(rows),
        "gold_count": sum(1 for row in rows if isinstance(row, dict) and row.get("label", {}).get("label") == "GOLD"),
        "training_eligible_count": sum(1 for row in rows if isinstance(row, dict) and row.get("eligible_for_training")),
        "hard_negative_count": sum(1 for row in rows if isinstance(row, dict) and row.get("hard_negative")),
        "low_step_filtered_count": sum(
            1
            for row in rows
            if isinstance(row, dict) and isinstance(row.get("low_step_filter"), dict) and row["low_step_filter"].get("filtered")
        ),
        "missing_evidence_task_ids": missing_evidence,
    }


def validate_benchmark_autodata_manifest_gate(
    repo_root: Path,
    *,
    manifest_paths: tuple[Path, ...] | None = None,
    min_training_eligible: int = 3,
    min_hard_negative: int = 3,
) -> list[dict[str, Any]]:
    paths = manifest_paths or (
        repo_root / ".nexus" / "reports" / "autodata" / "flash_8x1_autodata_manifest.json",
        repo_root / ".nexus" / "reports" / "autodata" / "pro_8x1_autodata_manifest.json",
    )
    summaries = [_autodata_manifest_counts(path if path.is_absolute() else repo_root / path) for path in paths]
    failures: list[dict[str, Any]] = []
    for summary in summaries:
        if not summary.get("passed"):
            failures.append({"path": summary["path"], "reason": summary.get("reason", "autodata_manifest_invalid")})
            continue
        if int(summary.get("training_eligible_count", 0)) < min_training_eligible:
            failures.append({"path": summary["path"], "reason": "insufficient_training_eligible_rows"})
        if int(summary.get("hard_negative_count", 0)) < min_hard_negative:
            failures.append({"path": summary["path"], "reason": "insufficient_hard_negative_rows"})
        if summary.get("missing_evidence_task_ids"):
            failures.append({"path": summary["path"], "reason": "autodata_rows_missing_evidence_refs"})
    if failures:
        return [
            _fail(
                "benchmark_autodata_manifest_gate",
                "benchmark_autodata_manifest_gate_failed",
                manifests=summaries,
                failures=failures,
                min_training_eligible=min_training_eligible,
                min_hard_negative=min_hard_negative,
            )
        ]
    return [
        _ok(
            "benchmark_autodata_manifest_gate",
            manifests=summaries,
            min_training_eligible=min_training_eligible,
            min_hard_negative=min_hard_negative,
        )
    ]


def validate_pipeline_composition_gate(repo_root: Path) -> list[dict[str, Any]]:
    inventory = build_inventory(repo_root)
    details = {
        "composition_status": inventory.get("composition_status"),
        "phase_ownership_status": inventory.get("phase_ownership_status"),
        "phase_executor_builders": inventory.get("phase_executor_builders", []),
        "registered_executor_phases": inventory.get("registered_executor_phases", []),
        "phase_factory_create_all_phases": inventory.get("phase_factory_create_all_phases", []),
        "runtime_missing_phases": inventory.get("runtime_missing_phases", []),
        "fallback_debt_phases": inventory.get("fallback_debt_phases", []),
        "fallback_debt_count": inventory.get("fallback_debt_count", 0),
        "legacy_mixins": inventory.get("legacy_mixins", []),
        "failures": inventory.get("failures", []),
    }
    fallback_debt_count = int(inventory.get("fallback_debt_count", 0) or 0)
    inventory_passed = bool(inventory.get("passed"))
    if inventory_passed and fallback_debt_count == 0:
        return [_ok("pipeline_composition_gate", **details)]
    reason = "pipeline_composition_fallback_debt_present" if inventory_passed and fallback_debt_count else "pipeline_composition_inventory_failed"
    return [_fail("pipeline_composition_gate", reason, **details)]


def validate_route_cost_policy_audit(repo_root: Path) -> list[dict[str, Any]]:
    audit = audit_route_cost_policy(repo_root)
    if audit.get("passed"):
        return [_ok("route_cost_policy_audit", **audit)]
    return [_fail("route_cost_policy_audit", "task_id_runtime_route_cost_policy_present", **audit)]


def validate_capability_wiring_audit_gate() -> list[dict[str, Any]]:
    audit = build_capability_wiring_audit().to_dict()
    if audit.get("passed"):
        return [_ok("capability_wiring_audit", **audit)]
    return [_fail("capability_wiring_audit", "capability_wiring_audit_failed", **audit)]


def validate_mutation_assurance_gate() -> list[dict[str, Any]]:
    record = build_mutation_assurance_record(
        concern="public_claim_safety",
        mutant_id="public_safe_forced_true",
        original_passed=True,
        mutant_failed=True,
        mutant_diff="- public_claim_safe = gate_passed and evidence_present\n+ public_claim_safe = True",
        evidence_refs=("tests/engine/test_mutation_assurance.py",),
    )
    gate = evaluate_mutation_assurance(
        [record],
        required=mutation_assurance_required(risk_score=90, public_claim=True),
    )
    if gate.get("passed"):
        return [_ok("mutation_assurance_gate", record=record, gate=gate)]
    return [_fail("mutation_assurance_gate", "mutation_assurance_failed", record=record, gate=gate)]


def build_scheduled_heavy_audit_plan() -> dict[str, Any]:
    tasks = [
        {
            "id": "mutation_assurance_high_risk_sweep",
            "capability": "mutation_assurance",
            "lane": "ralph_background",
            "foreground_blocking": False,
            "summary_receipt_required": True,
            "writeback_target": ".nexus/reports/learn/phase_writeback.jsonl",
        },
        {
            "id": "autodata_quality_manifest_refresh",
            "capability": "autodata_forge",
            "lane": "ralph_background",
            "foreground_blocking": False,
            "summary_receipt_required": True,
            "writeback_target": ".nexus/reports/autodata/",
        },
        {
            "id": "nightshift_recovery_audit",
            "capability": "nightshift",
            "lane": "ralph_background",
            "foreground_blocking": False,
            "summary_receipt_required": True,
            "writeback_target": ".nexus/reports/nightshift/",
        },
    ]
    return {
        "schema_version": "nexus_ralph_scheduled_heavy_audit_v1",
        "status": "SCHEDULED",
        "foreground_policy": "summary_receipt_only",
        "tasks": tasks,
        "task_count": len(tasks),
        "all_non_blocking": all(not task["foreground_blocking"] for task in tasks),
        "all_have_writeback": all(bool(task["writeback_target"]) for task in tasks),
    }


def validate_scheduled_heavy_audit_gate() -> list[dict[str, Any]]:
    plan = build_scheduled_heavy_audit_plan()
    required = {"mutation_assurance", "autodata_forge", "nightshift"}
    capabilities = {str(task.get("capability") or "") for task in plan.get("tasks", [])}
    if (
        plan.get("schema_version") == "nexus_ralph_scheduled_heavy_audit_v1"
        and plan.get("all_non_blocking") is True
        and plan.get("all_have_writeback") is True
        and required <= capabilities
    ):
        return [_ok("ralph_scheduled_heavy_audit", **plan)]
    return [_fail("ralph_scheduled_heavy_audit", "scheduled_heavy_audit_contract_failed", **plan)]


def validate_local_reflex_shadow() -> list[dict[str, Any]]:
    low = assess_local_reflex(
        task_desc="Fix a focused public fixture assertion.",
        task_type="public_test_repair",
        difficulty="hard",
        category="test_repair",
        repo_kind="neutral_fixture",
    )
    high = assess_local_reflex(
        task_desc="Refactor core orchestrator routing and remove old policy paths.",
        task_type="public_test_repair",
        difficulty="hard",
        category="test_repair",
        repo_kind="neutral_fixture",
    )
    destructive = assess_local_reflex(
        task_desc="Command rm -rf .git and write_file benchmarks/result.json.",
        task_type="execute",
        difficulty="hard",
        category="governance",
        repo_kind="neutral_fixture",
    )
    ollama = assess_local_reflex(
        task_desc="Probe local Ollama reflex availability.",
        provider="ollama",
        timeout_sec=2.0,
    )
    bonsai = assess_local_reflex(
        task_desc="Probe local Bonsai reflex availability.",
        provider="bonsai",
        timeout_sec=0.1,
    )
    if (
        low.risk_level == "low"
        and low.bare_sufficiency == "high"
        and high.risk_level == "high"
        and destructive.risk_level == "high"
        and destructive.bare_sufficiency == "low"
    ):
        return [
            _ok(
                "local_reflex_shadow",
                low_risk=low.to_jsonable(),
                high_risk=high.to_jsonable(),
                destructive=destructive.to_jsonable(),
                ollama_probe=ollama.to_jsonable(),
                bonsai_probe=bonsai.to_jsonable(),
                actual_local_model_available=bool(low.available or high.available or ollama.available or bonsai.available),
            )
        ]
    return [
        _fail(
            "local_reflex_shadow",
            "local_reflex_contract_mismatch",
            low_risk=low.to_jsonable(),
            high_risk=high.to_jsonable(),
            destructive=destructive.to_jsonable(),
            ollama_probe=ollama.to_jsonable(),
            bonsai_probe=bonsai.to_jsonable(),
        )
    ]


def validate_harness_engineering_gate() -> list[dict[str, Any]]:
    preflight = build_harness_preflight_sensor(
        task_desc="Given-When-Then business acceptance for a low risk docs sync.",
        task_type="business_acceptance",
        route={
            "bdd_acceptance": True,
            "route_features": {"risk_score": 12, "candidate_count": 1, "simple_hidden_bugfix": True},
        },
        pending_capabilities=(),
        selected_capabilities=("harness_preflight_sensor", "bdd_acceptance_skill", "artifact_gate", "claim_gate"),
    )
    failure_sensor = build_semantic_failure_sensor(
        failure_text="Hidden verifier failure: AssertionError expected candidate winner",
        phase="R",
    )
    bdd = build_bdd_acceptance_receipt(
        given="a merchant has a verified delivery claim",
        when="the acceptance skill checks the feature workflow",
        then="the business claim is backed by evidence",
        evidence_refs=("skill://business-acceptance-smoke",),
    )
    if (
        preflight["capability_wired"] is True
        and preflight["bdd_acceptance_required"] is True
        and failure_sensor["retry_policy"]["allow_blind_retry"] is False
        and bdd["business_verified"] is True
    ):
        return [
            _ok(
                "harness_engineering_gate",
                preflight=preflight,
                semantic_failure_sensor=failure_sensor,
                bdd_acceptance=bdd,
            )
        ]
    return [
        _fail(
            "harness_engineering_gate",
            "harness_engineering_contract_failed",
            preflight=preflight,
            semantic_failure_sensor=failure_sensor,
            bdd_acceptance=bdd,
        )
    ]


def repair_subset_command(output_dir: str) -> list[str]:
    return [
        "uv",
        "run",
        "python",
        "scripts/bench/capability_ab_runner.py",
        "--tasks-file",
        "scripts/bench/public_benchmark_nexus_value_v1.json",
        "--nexus-only",
        "--with-nexus-runner",
        "subprocess",
        "--with-llm-mode",
        "all",
        "--force-flow",
        "hyper_sprint",
        "--enable-autoreason-executor",
        "--enable-ddtree-executor",
        "--enable-ultra-review-dry-gate",
        "--llm-candidate-cap",
        "3",
        "--task-id-filter",
        "nexus-value-repair-001,nexus-value-repair-002",
        "--timeout-sec",
        "300",
        "--per-task-stop-loss-sec",
        "600",
        "--total-timeout-sec",
        "1200",
        "--force-learn-slo-ready",
        "--neutralize-history",
        "--disable-learning-loop",
        "--materialize-missing",
        "--isolation-mode",
        "preserve_target",
        "--evidence-bundle",
        "--output-dir",
        output_dir,
        "--markdown-report",
        "auto",
    ]


def _parse_progress_events(stderr: str) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
    parse_errors = 0
    for line in (stderr or "").splitlines():
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            parse_errors += 1
            continue
        if isinstance(payload, dict) and payload.get("event"):
            events.append(payload)
    return events, parse_errors


def _progress_summary(progress_events: list[dict[str, Any]]) -> dict[str, Any]:
    starts = [item for item in progress_events if item.get("event") == "task_start"]
    ends = [item for item in progress_events if item.get("event") == "task_end"]
    stop_losses = [item for item in progress_events if item.get("event") == "task_stop_loss"]
    total_timeouts = [item for item in progress_events if item.get("event") == "total_timeout"]
    started = {str(item.get("task_id")) for item in starts if item.get("task_id")}
    completed = {str(item.get("task_id")) for item in ends if item.get("task_id")}
    last = progress_events[-1] if progress_events else {}
    return {
        "task_start_count": len(starts),
        "task_end_count": len(ends),
        "task_stop_loss_count": len(stop_losses),
        "total_timeout_count": len(total_timeouts),
        "last_event": str(last.get("event") or "") if last else "",
        "last_task_id": str(last.get("task_id") or "") if last else "",
        "last_mode": str(last.get("mode") or "") if last else "",
        "last_status": str(last.get("status") or "") if last else "",
        "completed_task_ids": sorted(completed),
        "active_task_ids": sorted(started - completed),
    }


def _repair_classification(*, returncode: int | None, timed_out: bool, progress_events: list[dict[str, Any]], stdout: str, stderr: str) -> str:
    has_total_timeout = any(item.get("event") == "total_timeout" for item in progress_events)
    if timed_out and not progress_events:
        return "hang"
    if timed_out or has_total_timeout:
        return "timeout"
    if returncode == 0:
        return "success"
    if progress_events:
        return "progress"
    if not stdout.strip() and not stderr.strip():
        return "hang"
    return "failure"


def _repair_failure_category(*, classification: str, progress_events: list[dict[str, Any]]) -> str:
    if classification == "success":
        return ""
    if classification == "hang":
        return "timeout_no_progress" if progress_events == [] else "no_output_failure"
    if classification == "timeout":
        if not progress_events:
            return "timeout_no_progress"
        last = str((progress_events[-1] or {}).get("event") or "")
        return "timeout_after_task_start" if last == "task_start" else "timeout_after_progress"
    if classification == "progress":
        return "runner_failed_after_progress"
    return "runner_failed"


def _repair_subset_payload(
    *,
    cmd: list[str],
    returncode: int | None,
    stdout: str,
    stderr: str,
    duration_sec: float,
    timeout_sec: float,
    timed_out: bool,
) -> dict[str, Any]:
    progress_events, parse_errors = _parse_progress_events(stderr)
    last_event = progress_events[-1] if progress_events else {}
    classification = _repair_classification(
        returncode=returncode,
        timed_out=timed_out,
        progress_events=progress_events,
        stdout=stdout,
        stderr=stderr,
    )
    failure_category = _repair_failure_category(
        classification=classification,
        progress_events=progress_events,
    )
    progress_summary = _progress_summary(progress_events)
    return {
        "name": "flash_style_repair_subset",
        "passed": classification == "success",
        "classification": classification,
        "command": cmd,
        "returncode": returncode,
        "duration_sec": round(duration_sec, 4),
        "timeout_sec": timeout_sec,
        "timed_out": timed_out,
        "failure_category": failure_category,
        "stdout_empty": not bool((stdout or "").strip()),
        "progress_observed": bool(progress_events),
        "progress_event_count": len(progress_events),
        "progress_parse_errors": parse_errors,
        "progress_summary": progress_summary,
        "last_progress_event": last_event,
        "stdout_tail": (stdout or "")[-2000:],
        "stderr_tail": (stderr or "")[-2000:],
    }


def run_repair_subset(repo_root: Path, output_dir: str, *, timeout_sec: float = 1200.0) -> dict[str, Any]:
    cmd = repair_subset_command(output_dir)
    started = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
            timeout=max(1.0, float(timeout_sec or 1200.0)),
        )
        return _repair_subset_payload(
            cmd=cmd,
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            duration_sec=time.monotonic() - started,
            timeout_sec=timeout_sec,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return _repair_subset_payload(
            cmd=cmd,
            returncode=None,
            stdout=stdout,
            stderr=stderr,
            duration_sec=time.monotonic() - started,
            timeout_sec=timeout_sec,
            timed_out=True,
        )


def build_payload(
    repo_root: Path,
    *,
    run_repair: bool,
    output_dir: str,
    repair_timeout_sec: float = 1200.0,
    strict_event_contracts: bool | None = None,
    write_artifacts: bool = False,
) -> dict[str, Any]:
    checks = [
        *validate_repair_factory_skipped_routes(repo_root),
        *validate_runtime_receipt_reconcile(),
        *validate_brain_hub_alignment(repo_root),
        *validate_event_contracts(repo_root, strict_raw=strict_event_contracts),
        *validate_codex_nexus_smoke_plan(),
        *validate_brain_hub_coverage_gate(repo_root),
        *validate_openseeker_autodata_smoke(repo_root, write_manifest=write_artifacts),
        *validate_benchmark_autodata_manifest_gate(repo_root),
        *validate_pipeline_composition_gate(repo_root),
        *validate_route_cost_policy_audit(repo_root),
        *validate_capability_wiring_audit_gate(),
        *validate_mutation_assurance_gate(),
        *validate_scheduled_heavy_audit_gate(),
        *validate_local_reflex_shadow(),
        *validate_harness_engineering_gate(),
    ]
    if run_repair:
        checks.append(run_repair_subset(repo_root, output_dir, timeout_sec=repair_timeout_sec))
    failures = [item for item in checks if not item.get("passed")]
    return {
        "schema_version": "nexus_pre_flash_gate.v1",
        "passed": not failures,
        "checks": checks,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run fast Nexus checks before expensive Flash A/B benchmarks.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--quick", action="store_true", help="Run deterministic local route/receipt checks only.")
    parser.add_argument("--run-repair-subset", action="store_true", help="Run two-task Flash-style Nexus-only repair subset.")
    parser.add_argument("--strict-event-contracts", action="store_true", help="Fail the gate when legacy raw transition events are present.")
    parser.add_argument("--write-artifacts", action="store_true", help="Persist generated pre-Flash smoke artifacts.")
    parser.add_argument("--output-dir", default=".nexus/reports/bench_flash_repair_pruning_prefash")
    parser.add_argument("--repair-timeout-sec", type=float, default=1200.0)
    args = parser.parse_args(argv)

    run_repair = bool(args.run_repair_subset and not args.quick)
    payload = build_payload(
        Path(args.repo_root).resolve(),
        run_repair=run_repair,
        output_dir=args.output_dir,
        repair_timeout_sec=args.repair_timeout_sec,
        strict_event_contracts=True if args.strict_event_contracts else None,
        write_artifacts=bool(args.write_artifacts or not args.quick),
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
