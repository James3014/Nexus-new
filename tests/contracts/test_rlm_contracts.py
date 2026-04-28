from __future__ import annotations

import json

import pytest

from nexus.contracts.rlm_budget import RLMBudget, RLMBudgetState
from nexus.contracts.rlm_trace import RLMTraceEvent, RLMTraceWriter
from nexus.contracts.rule_lifecycle import (
    RuleLifecycleEvidence,
    RuleLifecycleState,
    recommend_rule_state,
)


def test_rlm_trace_event_round_trips_with_policy_fields():
    event = RLMTraceEvent(
        task_id="task-1",
        phase="R",
        iteration_id="R-1",
        parent_iteration_id="R-0",
        action_type="tool_call",
        tool_call={"name": "pytest", "args": ["tests/test_target.py"]},
        observation="pytest failed on hidden edge case",
        delta_hypothesis="normalize empty input before merge",
        confidence=0.62,
        allowed_tools=["read_file", "pytest"],
        blocked_reason="",
        policy_reason="phase:R allows pytest verification",
        stop_reason="",
        artifact_refs=["target.py", "test_target.py"],
    )

    restored = RLMTraceEvent.from_dict(event.to_dict())

    assert restored == event
    assert restored.schema_version == "rlm-trace-v1"
    assert restored.confidence == 0.62


def test_rlm_trace_event_rejects_unknown_top_level_fields():
    payload = RLMTraceEvent(task_id="task-1", phase="R", iteration_id="R-1").to_dict()
    payload["unexpected"] = "schema swell"

    with pytest.raises(ValueError, match="unknown RLMTraceEvent fields"):
        RLMTraceEvent.from_dict(payload)


def test_rlm_trace_writer_appends_jsonl(tmp_path):
    path = tmp_path / "trace.jsonl"
    writer = RLMTraceWriter(path)
    writer.append(RLMTraceEvent(task_id="task-1", phase="R", iteration_id="R-1", stop_reason="submit"))
    writer.append(RLMTraceEvent(task_id="task-1", phase="A", iteration_id="A-1", stop_reason="verified"))

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert [row["iteration_id"] for row in rows] == ["R-1", "A-1"]
    assert rows[0]["stop_reason"] == "submit"


def test_rlm_budget_tracks_consumption_and_exhaustion():
    budget = RLMBudget(max_iterations=2, max_llm_calls=2, max_tool_calls=3, max_output_chars=100)
    state = RLMBudgetState.from_budget(budget)

    first = state.consume(iterations=1, llm_calls=1, tool_calls=2, output_chars=40)
    second = first.consume(iterations=1, llm_calls=1, tool_calls=1, output_chars=60)

    assert first.exhausted is False
    assert second.exhausted is True
    assert second.exhausted_reasons == [
        "max_iterations",
        "max_llm_calls",
        "max_tool_calls",
        "max_output_chars",
    ]
    assert second.remaining["max_iterations"] == 0
    assert second.remaining["max_tool_calls"] == 0


def test_rlm_budget_rejects_negative_limits():
    with pytest.raises(ValueError, match="must be >= 0"):
        RLMBudget(max_iterations=-1)


def test_rule_lifecycle_keeps_rule_active_until_sample_is_large_enough():
    evidence = RuleLifecycleEvidence(rule_id="mem-palace-live-gate", sample_size=2, verified_lift_pp=0)

    assert recommend_rule_state(evidence) == RuleLifecycleState.ACTIVE


def test_rule_lifecycle_can_recommend_light_or_removed_candidate():
    light = RuleLifecycleEvidence(rule_id="context-prefetch", sample_size=6, verified_lift_pp=2.0)
    removable = RuleLifecycleEvidence(
        rule_id="heavy-rerank",
        sample_size=6,
        verified_lift_pp=0.2,
        cost_delta_pct=18.0,
    )

    assert recommend_rule_state(light) == RuleLifecycleState.LIGHT
    assert recommend_rule_state(removable) == RuleLifecycleState.REMOVED_CANDIDATE


def test_rule_lifecycle_keeps_rule_active_when_trust_regresses():
    evidence = RuleLifecycleEvidence(
        rule_id="claim-gate",
        sample_size=8,
        verified_lift_pp=0.0,
        trust_mismatch_delta_pp=3.0,
        cost_delta_pct=20.0,
    )

    assert recommend_rule_state(evidence) == RuleLifecycleState.ACTIVE
