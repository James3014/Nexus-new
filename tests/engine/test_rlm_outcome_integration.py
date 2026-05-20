from __future__ import annotations

import json

from nexus.engine.capability_planner import CapabilityPlanner
from nexus.engine.learning_policy_loader import merge_runtime_learning_policy
from nexus.engine.rlm_controller import (
    RLM_BOUNDED_ORCHESTRATION_RECEIPT_SCHEMA,
    RlmBudget,
    RlmController,
    build_bounded_rlm_orchestration_receipt,
    build_nightshift_handoff_receipt,
    build_rlm_decision_receipt,
)
from nexus.learning.outcome_memory import EpisodeOutcomeRecord, OutcomeMemoryManager


def test_rlm_controller_token_meltdown() -> None:
    budget = RlmBudget(max_r_iterations=4, max_tokens=1000, current_tokens=1200)
    rlm = RlmController(budget)

    assert rlm.should_continue_r(gate_passed=False, belief_confidence=0.1) is False
    assert rlm.terminal_reason(gate_passed=False, belief_confidence=0.1) == "token_budget_exhausted"


def test_rlm_controller_stops_x_loop_on_iteration_budget() -> None:
    budget = RlmBudget(max_x_iterations=2, current_x_count=2, max_tokens=1000, current_tokens=10)
    rlm = RlmController(budget)

    assert rlm.should_continue_x(belief_confidence=0.1) is False
    assert rlm.terminal_reason(gate_passed=False, belief_confidence=0.1) == "x_iteration_budget_exhausted"


def test_rlm_budget_exhaustion_builds_nightshift_handoff_receipt() -> None:
    decision = build_rlm_decision_receipt(
        loop_phase="R",
        gate_passed=False,
        belief_confidence=0.2,
        current_tokens=1000,
        max_tokens=1000,
    )

    handoff = build_nightshift_handoff_receipt(
        decision_receipt=decision,
        artifact_gate_passed=False,
    )

    assert decision["terminal_reason"] == "token_budget_exhausted"
    assert handoff["status"] == "PASS"
    assert handoff["recommended"] is True
    assert handoff["runtime_update_allowed"] is False
    assert handoff["public_benchmark_allowed"] is False


def test_rlm_no_handoff_when_artifact_gate_passed() -> None:
    decision = build_rlm_decision_receipt(
        loop_phase="R",
        gate_passed=True,
        belief_confidence=0.9,
    )

    handoff = build_nightshift_handoff_receipt(
        decision_receipt=decision,
        artifact_gate_passed=True,
    )

    assert handoff["status"] == "NOT_APPLICABLE"
    assert handoff["recommended"] is False
    assert "artifact_gate_passed_no_handoff" in handoff["blockers"]


def test_bounded_rlm_orchestration_receipt_emits_x_r_and_handoff_without_runtime_unlock() -> None:
    receipt = build_bounded_rlm_orchestration_receipt(
        gate_passed=False,
        belief_confidence=0.2,
        current_tokens=1000,
        x_observations=2,
        r_observations=4,
        max_tokens=10_000,
        max_x_iterations=3,
        max_r_iterations=4,
    )

    assert receipt["schema_version"] == RLM_BOUNDED_ORCHESTRATION_RECEIPT_SCHEMA
    assert receipt["status"] == "PASS"
    assert receipt["orchestration_mode"] == "bounded_adapter_not_dispatch"
    assert receipt["x_loop_decision_receipt"]["loop_phase"] == "X"
    assert receipt["r_loop_decision_receipt"]["loop_phase"] == "R"
    assert receipt["final_decision_receipt"]["terminal_reason"] == "r_iteration_budget_exhausted"
    assert receipt["nightshift_handoff_receipt"]["recommended"] is True
    assert receipt["runtime_update_allowed"] is False
    assert receipt["public_benchmark_allowed"] is False


def test_bounded_rlm_orchestration_stops_cleanly_on_gate_passed_high_belief() -> None:
    receipt = build_bounded_rlm_orchestration_receipt(
        gate_passed=True,
        belief_confidence=0.91,
        current_tokens=120,
        x_observations=1,
        r_observations=1,
    )

    assert receipt["final_decision_receipt"]["continue_allowed"] is False
    assert receipt["final_decision_receipt"]["terminal_reason"] == "gate_passed_high_belief"
    assert receipt["nightshift_handoff_receipt"]["status"] == "NOT_APPLICABLE"


def test_outcome_memory_writes_learning_policy(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(OutcomeMemoryManager, "STORAGE_PATH", tmp_path / "history.jsonl")
    monkeypatch.setattr(OutcomeMemoryManager, "POLICY_PATH", tmp_path / "policy.json")

    record = EpisodeOutcomeRecord.from_task(
        task_id="test-001",
        task_type="bug",
        task_desc="Fix deterministic bug",
        solved=True,
        wall_duration_sec=12.5,
        total_tokens_used=5000,
        trust_mismatch=False,
        receipts=[
            {
                "name": "hyper",
                "selected": True,
                "invoked": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "public_claim_safe": True,
            }
        ],
    )

    summary = OutcomeMemoryManager.save_episode_and_tune_sync(record)
    policy = json.loads((tmp_path / "policy.json").read_text(encoding="utf-8"))

    assert summary["status"] == "PASS"
    assert (tmp_path / "history.jsonl").exists()
    assert policy["promoted_capabilities"] == ["hyper"]
    assert policy["penalized_capabilities"] == []
    assert policy["aging_window"]["records_used"] == 1
    assert policy["capability_scores"]["hyper"] == 1.0


def test_outcome_memory_penalizes_selected_without_invocation(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(OutcomeMemoryManager, "STORAGE_PATH", tmp_path / "history.jsonl")
    monkeypatch.setattr(OutcomeMemoryManager, "POLICY_PATH", tmp_path / "policy.json")

    record = EpisodeOutcomeRecord.from_task(
        task_id="test-002",
        task_type="bug",
        task_desc="Selected only route",
        solved=False,
        wall_duration_sec=1.0,
        total_tokens_used=100,
        trust_mismatch=False,
        receipts=[{"name": "swarm", "selected": True, "invoked": False}],
    )

    OutcomeMemoryManager.save_episode_and_tune_sync(record)
    policy = json.loads((tmp_path / "policy.json").read_text(encoding="utf-8"))

    assert policy["promoted_capabilities"] == []
    assert policy["penalized_capabilities"] == ["swarm"]
    assert policy["capability_scores"]["swarm"] == -1.0


def test_outcome_memory_excludes_trust_mismatch_from_policy_scores(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(OutcomeMemoryManager, "STORAGE_PATH", tmp_path / "history.jsonl")
    monkeypatch.setattr(OutcomeMemoryManager, "POLICY_PATH", tmp_path / "policy.json")

    poisoned = EpisodeOutcomeRecord.from_task(
        task_id="trust-mismatch",
        task_type="bug",
        task_desc="Trust mismatch should not tune route policy",
        solved=True,
        wall_duration_sec=1.0,
        total_tokens_used=100,
        trust_mismatch=True,
        receipts=[
            {
                "name": "hyper",
                "selected": True,
                "invoked": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "public_claim_safe": True,
            }
        ],
    )

    OutcomeMemoryManager.save_episode_and_tune_sync(poisoned)
    policy = json.loads((tmp_path / "policy.json").read_text(encoding="utf-8"))

    assert policy["source_experiences_count"] == 1
    assert policy["eligible_experiences_count"] == 0
    assert policy["promoted_capabilities"] == []
    assert policy["excluded_experiences"] == [{"task_id": "trust-mismatch", "reason": "trust_mismatch"}]


def test_outcome_memory_recency_aging_resolves_newer_signal(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(OutcomeMemoryManager, "STORAGE_PATH", tmp_path / "history.jsonl")
    monkeypatch.setattr(OutcomeMemoryManager, "POLICY_PATH", tmp_path / "policy.json")

    older_penalty = EpisodeOutcomeRecord.from_task(
        task_id="test-003",
        task_type="bug",
        task_desc="Older selected only route",
        solved=False,
        wall_duration_sec=1.0,
        total_tokens_used=100,
        trust_mismatch=False,
        receipts=[{"name": "research", "selected": True, "invoked": False}],
    )
    newer_promotion = EpisodeOutcomeRecord.from_task(
        task_id="test-004",
        task_type="research",
        task_desc="Newer receipt backed route",
        solved=True,
        wall_duration_sec=2.0,
        total_tokens_used=200,
        trust_mismatch=False,
        receipts=[
            {
                "name": "research",
                "selected": True,
                "invoked": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "public_claim_safe": True,
            }
        ],
    )

    OutcomeMemoryManager.save_episode_and_tune_sync(older_penalty)
    OutcomeMemoryManager.save_episode_and_tune_sync(newer_promotion)
    policy = json.loads((tmp_path / "policy.json").read_text(encoding="utf-8"))

    assert policy["promoted_capabilities"] == ["research"]
    assert policy["penalized_capabilities"] == []
    assert policy["capability_scores"]["research"] > 0


def test_dynamic_outcome_policy_feeds_planner_without_runtime_default_pollution(tmp_path) -> None:
    policy_path = tmp_path / ".nexus" / "memory" / "dynamic_learning_policy.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps(
            {
                "schema_version": "nexus_dynamic_learning_policy.v1",
                "status": "PASS",
                "source_experiences": ["test-001"],
                "promoted_capabilities": ["autoreason"],
                "penalized_capabilities": ["swarm"],
                "enforce_penalties": False,
            }
        ),
        encoding="utf-8",
    )

    budget = merge_runtime_learning_policy(tmp_path)
    plan = CapabilityPlanner().plan(
        task_desc="Simple typo repair with no research need.",
        task_type="docs_fix",
        route={
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 5, "candidate_count": 1},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        budget=budget,
    ).to_dict()

    assert budget["learning_policy"]["source_schema"] == "nexus_dynamic_learning_policy.v1"
    assert "autoreason" in plan["selected_capabilities"]
    assert "runtime_update_allowed" not in budget["learning_policy"]
