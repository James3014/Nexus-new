import pytest
from dataclasses import asdict
from nexus.engine.pipeline_outcome import PipelineTerminalState, HumanReviewHandoff, PipelineOutcome
from nexus.core.outcome_schema import NexusOutcomeV2

def test_pipeline_terminal_state():
    assert PipelineTerminalState.SUCCESS == 0
    assert PipelineTerminalState.FAILED == 1
    assert PipelineTerminalState.ESCALATED == 2
    assert PipelineTerminalState.HUMAN_REVIEW == 3

def test_human_review_handoff():
    handoff = HumanReviewHandoff(
        escalation_count=3,
        last_root_cause="max_escalation:scope_drift",
        rejection_history=["rejected:lint_error"],
        sandbox_mode="test-ci",
        pregate_skip_reason="",
        task_id="abc-123",
        trace_id="trace-xyz",
        terminal_state="HUMAN_REVIEW"
    )
    
    data = asdict(handoff)
    assert data["escalation_count"] == 3
    assert data["last_root_cause"] == "max_escalation:scope_drift"
    assert data["terminal_state"] == "HUMAN_REVIEW"

def test_pipeline_outcome_serialization():
    handoff = HumanReviewHandoff(
        task_id="test",
        trace_id="trace",
        terminal_state="HUMAN_REVIEW"
    )
    
    outcome = PipelineOutcome(
        terminal_state=PipelineTerminalState.HUMAN_REVIEW,
        exit_code=PipelineTerminalState.HUMAN_REVIEW.value,
        task_id="test",
        trace_id="trace",
        handoff=handoff,
        cycle_root_cause="some_cause",
        verification_exit_codes=[0, 1],
        sandbox_mode="test",
        pregate_skip=True
    )
    
    data = asdict(outcome)
    assert data["terminal_state"] == PipelineTerminalState.HUMAN_REVIEW
    assert data["exit_code"] == 3
    assert data["handoff"]["task_id"] == "test"
    assert data["verification_exit_codes"] == [0, 1]
    assert data["pregate_skip"] is True

def test_nexus_outcome_v2_instantiation():
    outcome = NexusOutcomeV2(
        task_id="task-1",
        trace_id="trace-1",
        span_id="span-1",
        terminal_state="SUCCESS",
        exit_code=0,
        sandbox_mode="production",
        pregate_skip=False,
        pregate_skip_reason="",
        trust_level="production",
        escalation_count=0,
        verification_commands=["cargo test"],
        verification_exit_codes=[0],
        cycle_root_cause="",
        rejection_history=[],
        phantom_patterns=[],
        commit_sha="abcd",
        model_version="nexus-v17",
        timestamp="2026-03-30T00:00:00Z"
    )
    
    assert outcome.task_id == "task-1"
    assert outcome.exit_code == 0
    assert getattr(outcome, "timestamp", None) is not None
