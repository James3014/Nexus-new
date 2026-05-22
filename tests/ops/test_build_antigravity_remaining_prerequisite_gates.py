from __future__ import annotations

import json

from scripts.ops.build_antigravity_remaining_prerequisite_gates import (
    build_antigravity_remaining_prerequisite_gates,
    main,
)


def _write(path, text="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _minimal_repo(tmp_path):
    repo = tmp_path / "repo"
    _write(repo / "nexus/research/flow/route_decider.py", "def collect_route_signals():\n    pass\n")
    _write(repo / "nexus/app/research_flow_service.py", "collect_route_signals()\n")
    _write(repo / "nexus/research/flow/orchestrator.py")
    _write(repo / "nexus/engine/pipeline_repair.py")
    _write(repo / "nexus/engine/repair/audit_evaluator.py")
    _write(repo / "nexus/engine/repair/escalation_manager.py")
    _write(repo / "nexus/engine/planner/ab_evaluator.py")
    _write(repo / "nexus/engine/planner/policy_applier.py")
    _write(repo / "nexus/engine/learning_policy_store.py")
    _write(repo / "nexus/core/context_hub.py", "class ContextHub: pass\n")
    _write(repo / "tests/core/test_context_hub_strict_deps.py")
    _write(repo / "tests/core/test_belief_engine.py")
    _write(
        repo / "docs/reports/NEXUS_RLM_RECURSIVE_DISPATCH_GATE_2026-05-22.json",
        json.dumps({"decision": "DEFERRED"}),
    )
    _write(
        repo / "docs/reports/NEXUS_CONTEXTHUB_SPLIT_PREGATE_2026-05-22.json",
        json.dumps({"decision": "DEFERRED"}),
    )
    return repo


def test_remaining_prerequisite_gates_fail_closed_by_default(tmp_path):
    report = build_antigravity_remaining_prerequisite_gates(repo_root=_minimal_repo(tmp_path))

    assert report["status"] == "PASS"
    assert report["runtime_update_allowed"] is False
    assert report["public_benchmark_allowed"] is False
    assert report["zero_trust_v2_modification_allowed"] is False
    assert report["summary"] == {
        "gate_count": 6,
        "approved_count": 0,
        "deferred_count": 6,
        "implementation_allowed_count": 0,
    }
    by_id = {gate["item_id"]: gate for gate in report["gates"]}
    assert "deletion_test_missing" in by_id["clean_code_signal_collector_module"]["blockers"]
    assert "rlm_recursive_dispatch_gate_not_approved" in by_id["clean_code_orchestrator_module"]["blockers"]
    assert "runtime_authorization_missing" in by_id["routing_v2_full_recursive_dispatch"]["blockers"]


def test_main_writes_remaining_prerequisite_report(tmp_path, capsys):
    output = tmp_path / "report.json"

    assert main(["--repo-root", str(_minimal_repo(tmp_path)), "--output", str(output)]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "nexus.antigravity_remaining_prerequisite_gates.v1"
    assert payload["summary"]["gate_count"] == 6
    assert '"deferred_count": 6' in capsys.readouterr().out
