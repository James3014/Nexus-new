"""P4-I2: Committee Activation / Suppression Gate Tests."""
from __future__ import annotations

import os
import pytest
from nexus.services.local_heal.committee_activation_gate import (
    CommitteeActivationInput,
    evaluate_committee_activation,
)
from nexus.services.local_heal.committee_routed_tool import (
    CommitteeRoutedToolRequest,
    CommitteeRoutedToolResult,
    evaluate_and_execute,
)
from nexus.services.local_heal.receipt import build_repair_receipt


@pytest.fixture(autouse=True)
def setup_env():
    """Set up env vars for P4 tests."""
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
    yield
    os.environ.pop("NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL", None)


def _valid_input(**overrides):
    defaults = {
        "execution_topology": "cloud_with_local_assist",
        "p3_route_status": "shadow_stage5_escalation_recommended",
        "hard_case_escalation_recommended": True,
        "difficulty": "hard",
        "stage4_local_retry_success": False,
        "local_committee_enabled": True,
        "proposer_specs": [{"model": "a", "role": "primary"}, {"model": "b", "role": "secondary"}],
        "judge_model": "judge",
    }
    defaults.update(overrides)
    return CommitteeActivationInput(**defaults)


def test_hard_case_flag_on_specs_valid_allowed():
    """P4-I2: Hard case with valid specs → invocation allowed."""
    inputs = _valid_input()
    gate = evaluate_committee_activation(inputs)
    assert gate["gate_evaluated"] is True
    assert gate["invocation_allowed"] is True
    assert gate["blocked_reason"] == ""


def test_hard_case_flag_off_blocked():
    """P4-I2: Hard case escalation not recommended → blocked."""
    inputs = _valid_input(hard_case_escalation_recommended=False)
    gate = evaluate_committee_activation(inputs)
    assert gate["invocation_allowed"] is False
    assert "hard_case_escalation_recommended" in gate["blocked_reason"]


def test_medium_task_blocked():
    """P4-I2: Medium difficulty → blocked."""
    inputs = _valid_input(difficulty="medium")
    gate = evaluate_committee_activation(inputs)
    assert gate["invocation_allowed"] is False
    assert "difficulty" in gate["blocked_reason"]


def test_local_only_blocked():
    """P4-I2: local_only topology → blocked."""
    inputs = _valid_input(execution_topology="local_only")
    gate = evaluate_committee_activation(inputs)
    assert gate["invocation_allowed"] is False


def test_already_solved_blocked():
    """P4-I2: Claim gate already passed → blocked."""
    inputs = _valid_input(claim_gate_already_passed=True)
    gate = evaluate_committee_activation(inputs)
    assert gate["invocation_allowed"] is False
    assert gate["blocked_reason"] != ""


def test_missing_judge_model_blocked():
    """P4-I2: Missing judge model → blocked."""
    inputs = _valid_input(judge_model="")
    gate = evaluate_committee_activation(inputs)
    assert gate["invocation_allowed"] is False
    assert "judge_model" in gate["blocked_reason"]


def test_only_one_proposer_blocked():
    """P4-I2: Only 1 proposer spec → blocked."""
    inputs = _valid_input(proposer_specs=[{"model": "a", "role": "primary"}])
    gate = evaluate_committee_activation(inputs)
    assert gate["invocation_allowed"] is False
    assert "proposer_specs" in gate["blocked_reason"]


def test_enable_condition_tracking_in_receipt():
    """P4-I2: Enable conditions tracked in activation_inputs."""
    inputs = _valid_input()
    gate = evaluate_committee_activation(inputs)
    ai = gate["activation_inputs"]
    assert ai["enable_results"]["execution_topology == cloud_with_local_assist"] is True
    assert ai["enable_results"]["difficulty == hard"] is True
    assert ai["enable_results"]["local_retry_failed"] is True


def test_disable_condition_tracking_in_receipt():
    """P4-I2: Disable conditions tracked in activation_inputs."""
    inputs = _valid_input(difficulty="medium")
    gate = evaluate_committee_activation(inputs)
    ai = gate["activation_inputs"]
    assert ai["disable_results"]["difficulty easy/medium"] is True


def test_gate_not_evaluated_when_not_cloud_topology():
    """P4-I2: Gate blocks when not cloud topology."""
    inputs = _valid_input(execution_topology="single_local_model")
    gate = evaluate_committee_activation(inputs)
    assert gate["invocation_allowed"] is False


def test_evaluate_and_execute_blocks_invalid():
    """P4-I2: evaluate_and_execute blocks invalid requests."""
    req = CommitteeRoutedToolRequest(
        task_id="t1",
        repo_root="/tmp",
        target_file="foo.py",
        difficulty="medium",
        proposer_specs=[{"model": "a", "role": "primary"}, {"model": "b", "role": "secondary"}],
        judge_model="judge",
    )
    result = evaluate_and_execute(req)
    assert result.invoked is False
    assert result.invocation_allowed is False
    assert result.blocked_reason != ""


def test_evaluate_and_execute_allows_valid():
    """P4-I2: evaluate_and_execute allows valid requests."""
    req = CommitteeRoutedToolRequest(
        task_id="t1",
        repo_root="/tmp",
        target_file="foo.py",
        difficulty="hard",
        execution_topology="cloud_with_local_assist",
        p3_route_status="shadow_stage5_escalation_recommended",
        hard_case_escalation_reason="retry_failed",
        proposer_specs=[{"model": "a", "role": "primary"}, {"model": "b", "role": "secondary"}],
        judge_model="judge",
    )
    result = evaluate_and_execute(req)
    assert result.invoked is True
    assert result.invocation_allowed is True
