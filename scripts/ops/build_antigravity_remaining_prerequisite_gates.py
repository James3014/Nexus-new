#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ANTIGRAVITY_REMAINING_PREREQUISITE_GATES_2026-05-22.json")
RLM_GATE = Path("docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_GATE_2026-05-22.json")
CONTEXTHUB_GATE = Path("docs/reports/NEXUS_CONTEXTHUB_SPLIT_PREGATE_2026-05-22.json")
SIGNAL_COLLECTOR_GATE = Path("docs/reports/NEXUS_SIGNAL_COLLECTOR_SPLIT_PREGATE_2026-05-22.json")
RUNTIME_SPLIT_EVIDENCE = Path(
    "docs/reports/NEXUS_ANTIGRAVITY_RUNTIME_SPLIT_PREREQUISITE_EVIDENCE_2026-05-22.json"
)


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


def _decision_from_blockers(blockers: list[str]) -> str:
    return "APPROVED" if not blockers else "DEFERRED"


def _runtime_evidence_gate(repo_root: Path, item_id: str) -> dict[str, Any]:
    report = _read_json(repo_root, RUNTIME_SPLIT_EVIDENCE)
    for gate in report.get("gates", []) or []:
        if isinstance(gate, dict) and gate.get("item_id") == item_id:
            return gate
    return {}


def _gate(
    *,
    item_id: str,
    current_status: str,
    decision: str,
    blockers: list[str],
    required_evidence: list[str],
    allowed_files: list[str],
    validation: list[str],
    stop_conditions: list[str],
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "current_status": current_status,
        "decision": decision,
        "implementation_allowed": decision == "APPROVED",
        "blockers": sorted(set(blockers)),
        "required_evidence": required_evidence,
        "allowed_files": allowed_files,
        "validation": validation,
        "stop_conditions": stop_conditions,
    }


def _signal_collector_gate(repo_root: Path) -> dict[str, Any]:
    pregate = _read_json(repo_root, SIGNAL_COLLECTOR_GATE)
    route_decider = _read_text(repo_root, "nexus/research/flow/route_decider.py")
    service = _read_text(repo_root, "nexus/app/research_flow_service.py")
    blockers: list[str] = []
    facade_has_symbol = "def collect_route_signals" in route_decider or "collect_route_signals" in route_decider
    if not facade_has_symbol:
        blockers.append("collect_route_signals_not_found")
    if "collect_route_signals" not in service:
        blockers.append("caller_map_missing_research_flow_service")
    if pregate:
        blockers.extend(str(item) for item in pregate.get("blockers", []) or [])
    else:
        if not _exists(repo_root, "nexus/research/flow/signal_collector.py"):
            blockers.append("signal_collector_module_missing")
        blockers.extend(["deletion_test_missing", "duplicated_signal_block_not_proven"])
    return _gate(
        item_id="clean_code_signal_collector_module",
        current_status="DONE" if not blockers else "PARTIAL",
        decision=_decision_from_blockers(blockers),
        blockers=blockers,
        required_evidence=[
            "caller/import map for route_decider.collect_route_signals",
            "duplicated signal-construction block that can be deleted",
            "deletion test proving the split removes real duplication or improves injection",
        ],
        allowed_files=[
            "nexus/research/flow/signal_collector.py",
            "nexus/research/flow/route_decider.py",
            "tests/research/*route*",
        ],
        validation=["uv run pytest tests/research/test_*route* -q"],
        stop_conditions=[
            "only cosmetic movement is possible",
            "split requires broad ResearchFlowService changes",
        ],
    )


def _rlm_gate_decision(repo_root: Path) -> str:
    gate = _read_json(repo_root, RLM_GATE)
    return str(gate.get("decision") or gate.get("status") or "")


def _orchestrator_gate(repo_root: Path) -> dict[str, Any]:
    blockers: list[str] = []
    evidence_gate = _runtime_evidence_gate(repo_root, "rlm_recursive_dispatch_prerequisite")
    rlm_decision = _rlm_gate_decision(repo_root)
    if evidence_gate:
        blockers.extend(str(item) for item in evidence_gate.get("blockers", []) or [])
    if rlm_decision != "APPROVED":
        blockers.append("rlm_recursive_dispatch_gate_not_approved")
    if not _exists(repo_root, "nexus/research/flow/orchestrator.py"):
        blockers.append("orchestrator_module_missing")
    return _gate(
        item_id="clean_code_orchestrator_module",
        current_status="NOT_FOUND",
        decision=_decision_from_blockers(blockers),
        blockers=blockers,
        required_evidence=[
            "APPROVED RLM recursive dispatch gate",
            "max recursion depth, budget ceiling, stop reasons, and runtime call sites",
            "facade-preserving extraction proof",
        ],
        allowed_files=[
            "docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_GATE_2026-05-22.json",
            "nexus/research/flow/orchestrator.py",
            "tests/ops/*rlm_recursive*",
        ],
        validation=[
            "uv run pytest tests/contracts/test_routing_spec_v2_backlog.py tests/engine/test_rlm_outcome_integration.py -q"
        ],
        stop_conditions=[
            "RLM gate remains DEFERRED or REJECTED",
            "implementation would mutate runtime defaults",
        ],
    )


def _pipeline_repair_gate(repo_root: Path) -> dict[str, Any]:
    blockers: list[str] = []
    evidence_gate = _runtime_evidence_gate(repo_root, "pipeline_repair_split_prerequisite")
    if evidence_gate:
        blockers.extend(str(item) for item in evidence_gate.get("blockers", []) or [])
    if not _exists(repo_root, "nexus/engine/pipeline_repair.py"):
        blockers.append("pipeline_repair_facade_missing")
    if not _exists(repo_root, "nexus/engine/repair/audit_evaluator.py"):
        blockers.append("audit_evaluator_seam_missing")
    if not _exists(repo_root, "nexus/engine/repair/escalation_manager.py"):
        blockers.append("escalation_manager_seam_missing")
    if not evidence_gate:
        blockers.extend(["failing_rlm_repair_acceptance_evidence_missing", "deletion_test_missing"])
    return _gate(
        item_id="clean_code_pipeline_repair_split",
        current_status="PARTIAL_CLOSED_FOR_CBO",
        decision=_decision_from_blockers(blockers),
        blockers=blockers,
        required_evidence=[
            "failing RLM/repair acceptance test or report",
            "exact duplicated logic to delete from pipeline_repair.py",
            "focused regression for extracted repair unit",
        ],
        allowed_files=[
            "nexus/engine/pipeline_repair.py",
            "nexus/engine/repair/*",
            "tests/engine/test_pipeline_repair.py",
            "tests/engine/repair/*",
        ],
        validation=["uv run pytest tests/engine/test_pipeline_repair.py tests/engine/repair -q"],
        stop_conditions=[
            "no failing RLM/repair acceptance evidence exists",
            "compatibility facade cannot be preserved",
        ],
    )


def _capability_planner_gate(repo_root: Path) -> dict[str, Any]:
    blockers: list[str] = []
    evidence_gate = _runtime_evidence_gate(repo_root, "capability_planner_split_prerequisite")
    if evidence_gate:
        blockers.extend(str(item) for item in evidence_gate.get("blockers", []) or [])
    for path, blocker in (
        ("nexus/engine/planner/ab_evaluator.py", "ab_evaluator_seam_missing"),
        ("nexus/engine/planner/policy_applier.py", "policy_applier_seam_missing"),
        ("nexus/engine/learning_policy_store.py", "learning_policy_store_missing"),
    ):
        if not _exists(repo_root, path):
            blockers.append(blocker)
    if not evidence_gate:
        blockers.extend(["failing_policy_order_or_injection_test_missing", "deletion_or_injection_test_missing"])
    return _gate(
        item_id="clean_code_capability_planner_split",
        current_status="PARTIAL_CLOSED_FOR_CLEAN_CODE",
        decision=_decision_from_blockers(blockers),
        blockers=blockers,
        required_evidence=[
            "failing policy-order, injection, or learning-policy test",
            "exact planner responsibility to extract",
            "route policy equivalence proof",
        ],
        allowed_files=[
            "nexus/engine/capability_planner.py",
            "nexus/engine/planner/*",
            "tests/engine/planner/*",
            "tests/engine/test_capability_planner.py",
        ],
        validation=["uv run pytest tests/engine/planner tests/engine/test_learning_policy_store.py -q"],
        stop_conditions=[
            "no policy-order or injection failure exists",
            "extraction changes route policy behavior",
        ],
    )


def _contexthub_gate(repo_root: Path) -> dict[str, Any]:
    blockers: list[str] = []
    evidence_gate = _runtime_evidence_gate(repo_root, "contexthub_physical_split_prerequisite")
    if evidence_gate:
        blockers.extend(str(item) for item in evidence_gate.get("blockers", []) or [])
    gate = _read_json(repo_root, CONTEXTHUB_GATE)
    if str(gate.get("decision") or gate.get("status") or "") != "APPROVED":
        blockers.append("contexthub_split_pregate_not_approved")
    for path, blocker in (
        ("nexus/core/context_hub.py", "contexthub_facade_missing"),
        ("tests/core/test_context_hub_strict_deps.py", "strict_deps_test_missing"),
        ("tests/core/test_belief_engine.py", "belief_engine_test_missing"),
    ):
        if not _exists(repo_root, path):
            blockers.append(blocker)
    if not evidence_gate:
        blockers.extend(["caller_map_missing", "leaf_extraction_candidate_missing", "deletion_test_missing"])
    return _gate(
        item_id="deep_contexthub_physical_split",
        current_status="PARTIAL_GATE_REPORTED",
        decision=_decision_from_blockers(blockers),
        blockers=blockers,
        required_evidence=[
            "caller/import map for ContextHub construction",
            "one leaf extraction candidate",
            "deletion test proving duplicated logic removal",
        ],
        allowed_files=[
            "docs/reports/NEXUS_CONTEXTHUB_SPLIT_PREGATE_2026-05-22.json",
            "nexus/core/context_hub.py",
            "tests/core/*",
        ],
        validation=["uv run pytest tests/core/test_context_hub_strict_deps.py tests/core/test_belief_engine.py -q"],
        stop_conditions=[
            "constructor semantics need broad changes",
            "strict dependency compatibility cannot be preserved",
        ],
    )


def _recursive_dispatch_gate(repo_root: Path) -> dict[str, Any]:
    blockers: list[str] = []
    evidence_gate = _runtime_evidence_gate(repo_root, "rlm_recursive_dispatch_prerequisite")
    if evidence_gate:
        blockers.extend(str(item) for item in evidence_gate.get("blockers", []) or [])
    if _rlm_gate_decision(repo_root) != "APPROVED":
        blockers.append("rlm_recursive_dispatch_gate_not_approved")
    if not evidence_gate:
        blockers.extend(["runtime_authorization_missing", "negative_control_missing", "recursion_limits_missing"])
    return _gate(
        item_id="routing_v2_full_recursive_dispatch",
        current_status="DEFERRED_GATE_REPORTED",
        decision=_decision_from_blockers(blockers),
        blockers=blockers,
        required_evidence=[
            "APPROVED recursive dispatch gate report",
            "max recursion depth, max handoff count, budget ceiling, and stop reasons",
            "negative-control test proving recursion stops safely",
            "separate runtime authorization if runtime defaults change",
        ],
        allowed_files=[
            "docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_GATE_2026-05-22.json",
            "tests/contracts/test_routing_spec_v2_backlog.py",
            "tests/engine/test_rlm_outcome_integration.py",
        ],
        validation=[
            "uv run pytest tests/contracts/test_routing_spec_v2_backlog.py tests/engine/test_rlm_outcome_integration.py -q"
        ],
        stop_conditions=[
            "gate is not APPROVED",
            "recursion limits are missing",
            "implementation requires public benchmark or Zero Trust V2 gate edits",
        ],
    )


def build_antigravity_remaining_prerequisite_gates(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    gates = [
        _signal_collector_gate(repo_root),
        _orchestrator_gate(repo_root),
        _pipeline_repair_gate(repo_root),
        _capability_planner_gate(repo_root),
        _contexthub_gate(repo_root),
        _recursive_dispatch_gate(repo_root),
    ]
    approved = [gate for gate in gates if gate["decision"] == "APPROVED"]
    return {
        "schema": "nexus.antigravity_remaining_prerequisite_gates.v1",
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
            "This report evaluates prerequisites only.",
            "DEFERRED gates are successful fail-closed outcomes, not implementation approval.",
            "No runtime defaults, Zero Trust V2 reports, public benchmark gates, or forbidden paths are modified.",
        ],
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Antigravity remaining prerequisite gate report.")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    report = build_antigravity_remaining_prerequisite_gates(repo_root=args.repo_root)
    _write_json(args.output, report)
    print(json.dumps({"output": args.output.as_posix(), **report["summary"], "status": report["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
