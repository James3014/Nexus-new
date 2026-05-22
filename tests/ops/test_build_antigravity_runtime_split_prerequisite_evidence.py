from __future__ import annotations

import json

from scripts.ops.build_antigravity_runtime_split_prerequisite_evidence import (
    build_antigravity_runtime_split_prerequisite_evidence,
    main,
)


def _write(path, text="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _minimal_repo(tmp_path):
    repo = tmp_path / "repo"
    _write(
        repo / "nexus/engine/rlm_controller.py",
        "RLM_RUNTIME_DECISION_RECEIPT_SCHEMA = 'x'\n"
        "def build_bounded_rlm_orchestration_receipt():\n    pass\n",
    )
    _write(
        repo / "tests/engine/test_rlm_outcome_integration.py",
        "def test_bounded_rlm_orchestration_receipt_emits_x_r_and_handoff_without_runtime_unlock(): pass\n"
        "def test_bounded_rlm_orchestration_stops_cleanly_on_gate_passed_high_belief(): pass\n",
    )
    _write(
        repo / "tests/contracts/test_routing_spec_v2_backlog.py",
        "full_recursive_dispatch_requires_separate_runtime_authorization = True\n",
    )
    _write(
        repo / "tests/engine/test_recursive_repair_loop.py",
        "def test_recursive_repair_budget_exhaustion_fails_closed(): pass\n"
        "def test_recursive_repair_default_off_preserves_existing_loop(): pass\n",
    )
    _write(
        repo / "nexus/engine/pipeline_repair.py",
        "from nexus.engine.recursive_repair_loop import RecursiveRepairLoop\nclass PipelineRepairMixin: pass\n",
    )
    _write(repo / "nexus/engine/repair/audit_evaluator.py")
    _write(repo / "nexus/engine/repair/escalation_manager.py")
    _write(repo / "tests/engine/test_pipeline_repair.py")
    _write(
        repo / "nexus/engine/capability_planner.py",
        "from nexus.engine.planner.ab_evaluator import build_decision_trace\n"
        "from nexus.engine.planner.policy_applier import apply_learning_policy\n"
        "class CapabilityPlanner: pass\n",
    )
    _write(repo / "nexus/engine/planner/ab_evaluator.py")
    _write(repo / "nexus/engine/planner/policy_applier.py")
    _write(repo / "nexus/engine/learning_policy_store.py")
    _write(repo / "tests/engine/test_capability_planner.py")
    _write(repo / "tests/engine/test_route_contracts.py")
    _write(
        repo / "nexus/core/context_hub.py",
        "class StateView: pass\nclass ContextDependencies: pass\nclass ContextHub:\n    strict_deps = True\n",
    )
    _write(repo / "nexus/engine/bootstrap.py", "ContextHub(strict_deps=True)\n")
    _write(repo / "nexus/engine/autonomic_routing_service.py", "context_hub.make_pre_routing_decision()\n")
    _write(repo / "tests/core/test_context_hub_strict_deps.py", "ContextHub(strict_deps=True)\n")
    _write(repo / "tests/core/test_belief_engine.py", "hub.make_pre_routing_decision()\n")
    _write(
        repo / "docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_GATE_2026-05-22.json",
        json.dumps({"decision": "DEFERRED", "runtime_update_allowed": False, "max_recursion_depth": 0}),
    )
    _write(
        repo / "docs/reports/NEXUS_CONTEXTHUB_SPLIT_PREGATE_2026-05-22.json",
        json.dumps({"decision": "DEFERRED"}),
    )
    return repo


def test_runtime_split_prerequisite_evidence_is_fail_closed_with_maps(tmp_path):
    report = build_antigravity_runtime_split_prerequisite_evidence(repo_root=_minimal_repo(tmp_path))

    assert report["status"] == "PASS"
    assert report["runtime_update_allowed"] is False
    assert report["public_benchmark_allowed"] is False
    assert report["zero_trust_v2_modification_allowed"] is False
    assert report["summary"] == {
        "gate_count": 4,
        "approved_count": 0,
        "deferred_count": 4,
        "implementation_allowed_count": 0,
    }
    by_id = {gate["item_id"]: gate for gate in report["gates"]}
    assert "rlm_recursive_dispatch_gate_not_approved" in by_id["rlm_recursive_dispatch_prerequisite"]["blockers"]
    assert by_id["rlm_recursive_dispatch_prerequisite"]["evidence"]["checks"]["negative_control_test_present"] is True
    assert "failing_rlm_repair_acceptance_evidence_missing" in by_id["pipeline_repair_split_prerequisite"]["blockers"]
    assert "failing_policy_order_or_injection_test_missing" in by_id["capability_planner_split_prerequisite"]["blockers"]
    context = by_id["contexthub_physical_split_prerequisite"]
    assert context["evidence"]["checks"]["caller_map_present"] is True
    assert "deletion_test_missing" in context["blockers"]
    assert "StateView" in context["evidence"]["leaf_extraction_candidates"]


def test_main_writes_runtime_split_prerequisite_evidence(tmp_path, capsys):
    output = tmp_path / "report.json"

    assert main(["--repo-root", str(_minimal_repo(tmp_path)), "--output", str(output)]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "nexus.antigravity_runtime_split_prerequisite_evidence.v1"
    assert payload["summary"]["gate_count"] == 4
    assert '"deferred_count": 4' in capsys.readouterr().out
