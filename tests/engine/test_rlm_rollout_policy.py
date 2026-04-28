from __future__ import annotations

from nexus.engine.rlm_rollout_policy import RLMRolloutMode, decide_rlm_rollout


def test_rlm_rollout_stays_disabled_until_requested():
    decision = decide_rlm_rollout(task_type="bug", task_desc="repair evidence drift")

    assert decision.mode is RLMRolloutMode.DISABLED
    assert decision.reason == "not_requested"


def test_rlm_rollout_blocks_live_delivery_without_explicit_approval(monkeypatch):
    monkeypatch.setenv("NEXUS_RLM_REPAIR_LOOP", "1")

    decision = decide_rlm_rollout(
        task_type="bug",
        task_desc="repair production handoff",
        delivery_profile="live_api",
    )

    assert decision.mode is RLMRolloutMode.DISABLED
    assert decision.reason == "live_delivery_requires_explicit_approval"


def test_rlm_rollout_enables_repair_loop_for_eligible_repair_task(monkeypatch):
    monkeypatch.setenv("NEXUS_RLM_REPAIR_LOOP", "1")

    decision = decide_rlm_rollout(task_type="bug", task_desc="repair hidden verifier failure")

    assert decision.mode is RLMRolloutMode.REPAIR_LOOP
    assert decision.repair_loop_enabled is True
    assert "ac_gate_verified" in decision.required_gates


def test_rlm_rollout_uses_trace_only_for_low_risk_task(monkeypatch):
    monkeypatch.setenv("NEXUS_RLM_REPAIR_LOOP", "1")

    decision = decide_rlm_rollout(task_type="docs", task_desc="update wording")

    assert decision.mode is RLMRolloutMode.TRACE_ONLY
    assert decision.repair_loop_enabled is False
    assert decision.required_gates == ["rlm_trace_present"]


def test_rlm_rollout_marks_research_loop_candidate():
    decision = decide_rlm_rollout(
        task_type="research",
        task_desc="compare candidate evidence",
        metadata={"rlm_recursive_research_enabled": True},
    )

    assert decision.mode is RLMRolloutMode.RESEARCH_LOOP_CANDIDATE
    assert decision.repair_loop_enabled is True
    assert "x_loop_budget_observed" in decision.required_gates
