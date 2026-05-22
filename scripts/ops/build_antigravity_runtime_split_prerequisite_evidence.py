#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ANTIGRAVITY_RUNTIME_SPLIT_PREREQUISITE_EVIDENCE_2026-05-22.json")
RLM_GATE = Path("docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_GATE_2026-05-22.json")
CONTEXTHUB_GATE = Path("docs/reports/NEXUS_CONTEXTHUB_SPLIT_PREGATE_2026-05-22.json")


def _read_text(repo_root: Path, path: str) -> str:
    target = repo_root / path
    if not target.exists():
        return ""
    return target.read_text(encoding="utf-8", errors="ignore")


def _read_json(repo_root: Path, path: Path) -> dict[str, Any]:
    target = repo_root / path
    if not target.exists():
        return {}
    loaded = json.loads(target.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _exists(repo_root: Path, path: str) -> bool:
    return (repo_root / path).exists()


def _reference_map(repo_root: Path, needles: tuple[str, ...], roots: tuple[str, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for root in roots:
        base = repo_root / root
        if base.is_file():
            candidates = [base]
        elif base.exists():
            candidates = sorted(path for path in base.rglob("*.py") if path.is_file())
        else:
            candidates = []
        for candidate in candidates:
            text = candidate.read_text(encoding="utf-8", errors="ignore")
            matched = [needle for needle in needles if needle in text]
            if matched:
                rows.append({"path": candidate.relative_to(repo_root).as_posix(), "matches": matched})
    return rows


def _decision(blockers: list[str]) -> str:
    return "APPROVED" if not blockers else "DEFERRED"


def _gate(
    *,
    item_id: str,
    decision: str,
    blockers: list[str],
    evidence: Mapping[str, Any],
    implementation_allowed: bool = True,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "decision": decision,
        "implementation_allowed": implementation_allowed and decision == "APPROVED",
        "blockers": sorted(set(blockers)),
        "evidence": dict(evidence),
    }


def build_rlm_recursive_dispatch_evidence(repo_root: Path) -> dict[str, Any]:
    gate = _read_json(repo_root, RLM_GATE)
    controller = _read_text(repo_root, "nexus/engine/rlm_controller.py")
    outcome_tests = _read_text(repo_root, "tests/engine/test_rlm_outcome_integration.py")
    backlog_tests = _read_text(repo_root, "tests/contracts/test_routing_spec_v2_backlog.py")
    repair_tests = _read_text(repo_root, "tests/engine/test_recursive_repair_loop.py")
    blockers: list[str] = []
    if str(gate.get("decision") or gate.get("status") or "") != "APPROVED":
        blockers.append("rlm_recursive_dispatch_gate_not_approved")
    if gate.get("runtime_update_allowed") is not True:
        blockers.append("runtime_authorization_missing")
    checks = {
        "bounded_orchestration_receipt_present": "build_bounded_rlm_orchestration_receipt" in controller,
        "runtime_decision_receipt_schema_present": "RLM_RUNTIME_DECISION_RECEIPT_SCHEMA" in controller,
        "bounded_receipt_test_present": "without_runtime_unlock" in outcome_tests,
        "negative_control_test_present": "stops_cleanly" in outcome_tests or "budget_exhaustion" in repair_tests,
        "full_recursive_dispatch_block_test_present": "full_recursive_dispatch_requires_separate_runtime_authorization"
        in backlog_tests,
        "recursive_repair_budget_test_present": "budget_exhaustion_fails_closed" in repair_tests,
    }
    for key, ok in checks.items():
        if not ok:
            blockers.append(key.replace("_present", "_missing"))
    return _gate(
        item_id="rlm_recursive_dispatch_prerequisite",
        decision=_decision(blockers),
        blockers=blockers,
        evidence={
            "source_gate": RLM_GATE.as_posix(),
            "source_gate_decision": str(gate.get("decision") or gate.get("status") or "MISSING"),
            "checks": checks,
            "max_recursion_depth": gate.get("max_recursion_depth"),
        },
    )


def build_pipeline_repair_split_evidence(repo_root: Path) -> dict[str, Any]:
    pipeline = _read_text(repo_root, "nexus/engine/pipeline_repair.py")
    pipeline_tests = _read_text(repo_root, "tests/engine/test_pipeline_repair.py")
    recursive_tests = _read_text(repo_root, "tests/engine/test_recursive_repair_loop.py")
    blockers: list[str] = []
    checks = {
        "pipeline_repair_facade_present": "class PipelineRepairMixin" in pipeline,
        "recursive_repair_loop_consumed": "RecursiveRepairLoop" in pipeline,
        "audit_evaluator_seam_present": _exists(repo_root, "nexus/engine/repair/audit_evaluator.py"),
        "escalation_manager_seam_present": _exists(repo_root, "nexus/engine/repair/escalation_manager.py"),
        "composed_phase_result_seam_present": _exists(repo_root, "nexus/engine/repair/composed_phase_result.py"),
        "composed_phase_result_deletion_test_present": "test_pipeline_repair_reexports_split_composed_phase_results"
        in pipeline_tests,
        "pipeline_repair_test_present": _exists(repo_root, "tests/engine/test_pipeline_repair.py"),
        "recursive_repair_acceptance_tests_present": "test_recursive_repair_" in recursive_tests,
    }
    for key, ok in checks.items():
        if not ok:
            blockers.append(key.replace("_present", "_missing"))
    if not checks["composed_phase_result_seam_present"] or not checks["composed_phase_result_deletion_test_present"]:
        blockers.extend(["failing_rlm_repair_acceptance_evidence_missing", "deletion_test_missing"])
    return _gate(
        item_id="pipeline_repair_split_prerequisite",
        decision=_decision(blockers),
        blockers=blockers,
        evidence={
            "checks": checks,
            "existing_decision_source": "docs/reports/NEXUS_CBO_REPAIR_SPLIT_DECISION_2026-05-20.json",
            "decision_note": "Existing seams are present; no failing acceptance or deletion evidence justifies another split.",
        },
    )


def build_capability_planner_split_evidence(repo_root: Path) -> dict[str, Any]:
    planner = _read_text(repo_root, "nexus/engine/capability_planner.py")
    planner_tests = _read_text(repo_root, "tests/engine/test_capability_planner.py")
    blockers: list[str] = []
    checks = {
        "capability_planner_facade_present": "class CapabilityPlanner" in planner,
        "ab_evaluator_seam_present": _exists(repo_root, "nexus/engine/planner/ab_evaluator.py"),
        "policy_applier_seam_present": _exists(repo_root, "nexus/engine/planner/policy_applier.py"),
        "skill_mount_evidence_seam_present": _exists(repo_root, "nexus/engine/planner/skill_mount_evidence.py"),
        "skill_mount_evidence_injection_test_present": "test_capability_planner_delegates_runtime_policy_overlay_skill_requests_to_split_module"
        in planner_tests,
        "learning_policy_store_present": _exists(repo_root, "nexus/engine/learning_policy_store.py"),
        "decision_trace_imported": "build_decision_trace" in planner,
        "learning_policy_imported": "apply_learning_policy" in planner,
        "capability_planner_tests_present": _exists(repo_root, "tests/engine/test_capability_planner.py"),
        "route_contract_tests_present": _exists(repo_root, "tests/engine/test_route_contracts.py"),
    }
    for key, ok in checks.items():
        if not ok:
            blockers.append(key.replace("_present", "_missing"))
    if not checks["skill_mount_evidence_seam_present"] or not checks["skill_mount_evidence_injection_test_present"]:
        blockers.extend(["failing_policy_order_or_injection_test_missing", "deletion_or_injection_test_missing"])
    return _gate(
        item_id="capability_planner_split_prerequisite",
        decision=_decision(blockers),
        blockers=blockers,
        evidence={
            "checks": checks,
            "decision_note": "Planner seams exist; further split needs a failing policy-order/injection acceptance case.",
        },
    )


def build_contexthub_split_evidence(repo_root: Path) -> dict[str, Any]:
    gate = _read_json(repo_root, CONTEXTHUB_GATE)
    hub = _read_text(repo_root, "nexus/core/context_hub.py")
    view = _read_text(repo_root, "nexus/core/context_view.py")
    strict_deps_test = _read_text(repo_root, "tests/core/test_context_hub_strict_deps.py")
    caller_map = _reference_map(
        repo_root,
        ("ContextHub", "make_pre_routing_decision"),
        (
            "nexus/app",
            "nexus/engine",
            "tests/core",
            "tests/engine",
        ),
    )
    monkeypatch_sensitive = [
        row["path"]
        for row in caller_map
        if row["path"].startswith("tests/") and ("make_pre_routing_decision" in row["matches"] or "ContextHub" in row["matches"])
    ]
    checks = {
        "contexthub_facade_present": "class ContextHub" in hub,
        "context_view_module_present": "class StateView" in view and "class ContextDependencies" in view,
        "context_view_reexport_present": "from nexus.core.context_view import ContextDependencies, StateView" in hub,
        "strict_deps_present": "strict_deps" in hub,
        "context_dependencies_present": "class ContextDependencies" in view,
        "state_view_leaf_candidate_present": "class StateView" in view,
        "caller_map_present": bool(caller_map),
        "deletion_test_present": "test_context_hub_reexports_split_context_view_contracts" in strict_deps_test,
        "strict_deps_test_present": _exists(repo_root, "tests/core/test_context_hub_strict_deps.py"),
        "belief_engine_test_present": _exists(repo_root, "tests/core/test_belief_engine.py"),
    }
    blockers: list[str] = []
    if str(gate.get("decision") or gate.get("status") or "") != "APPROVED":
        blockers.append("contexthub_split_pregate_not_approved")
    for key, ok in checks.items():
        if not ok:
            blockers.append(key.replace("_present", "_missing"))
    if gate.get("physical_split_allowed") is not True:
        blockers.append("leaf_extraction_not_approved")
    if not checks["deletion_test_present"]:
        blockers.append("deletion_test_missing")
    return _gate(
        item_id="contexthub_physical_split_prerequisite",
        decision=_decision(blockers),
        blockers=blockers,
        evidence={
            "source_gate": CONTEXTHUB_GATE.as_posix(),
            "source_gate_decision": str(gate.get("decision") or gate.get("status") or "MISSING"),
            "checks": checks,
            "caller_map": caller_map,
            "monkeypatch_sensitive_tests": monkeypatch_sensitive,
            "leaf_extraction_candidates": ["StateView", "ContextDependencies"],
        },
    )


def build_antigravity_runtime_split_prerequisite_evidence(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    gates = [
        build_rlm_recursive_dispatch_evidence(repo_root),
        build_pipeline_repair_split_evidence(repo_root),
        build_capability_planner_split_evidence(repo_root),
        build_contexthub_split_evidence(repo_root),
    ]
    approved = [gate for gate in gates if gate["decision"] == "APPROVED"]
    return {
        "schema": "nexus.antigravity_runtime_split_prerequisite_evidence.v1",
        "status": "PASS",
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "zero_trust_v2_modification_allowed": False,
        "summary": {
            "gate_count": len(gates),
            "approved_count": len(approved),
            "deferred_count": len(gates) - len(approved),
            "implementation_allowed_count": sum(1 for gate in gates if gate["implementation_allowed"]),
        },
        "gates": gates,
        "claim_boundary": [
            "This evidence report closes prerequisite inspection only.",
            "APPROVED means the prerequisite blocker has been cleared for bounded implementation.",
            "Runtime defaults and public benchmark claims remain locked unless their separate gates explicitly allow them.",
        ],
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Antigravity runtime/split prerequisite evidence.")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = build_antigravity_runtime_split_prerequisite_evidence(repo_root=args.repo_root)
    _write_json(args.output, report)
    print(json.dumps({"output": args.output.as_posix(), **report["summary"], "status": report["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
