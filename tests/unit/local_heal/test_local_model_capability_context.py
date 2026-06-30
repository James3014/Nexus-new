from __future__ import annotations

import pytest

from nexus.services.local_heal.local_model_capability_context import (
    LocalModelCapabilityContext,
    CapabilityExecutionResult,
    build_capability_context_from_request,
)
from nexus.services.local_heal.local_model_executor import LocalModelExecutorRequest


def test_context_builds_from_request():
    req = LocalModelExecutorRequest(
        task_id="t1", problem_statement="fix bug", repo_root="/ws",
        target_file="a.py", selected_capabilities=("ddtree", "autoreason"),
        evidence_refs=("ref1",),
    )
    raw_meta = {"target_symbol": "func", "execution_topology": "local_committee_only",
                "source_anchor_present": True, "source_anchor_source": "locked_search",
                "source_anchor_hash": "abc", "failure_feedback_present": False}
    ctx = build_capability_context_from_request(req, raw_meta)
    assert ctx.task_id == "t1"
    assert ctx.selected_capabilities == ("ddtree", "autoreason")
    assert ctx.execution_topology == "local_committee_only"
    assert ctx.source_anchor["present"] is True


def test_context_no_env_needed():
    ctx = LocalModelCapabilityContext(
        task_id="t2", source_root="/ws", problem_statement="p",
        target_file="a.py", target_symbol="f", selected_capabilities=(),
        execution_topology="single_local_model", evidence_refs=(),
    )
    assert ctx.task_id == "t2"


def test_context_missing_target_file_no_crash():
    ctx = LocalModelCapabilityContext(
        task_id="t3", source_root="/ws", problem_statement="p",
        target_file="", target_symbol="", selected_capabilities=(),
        execution_topology="single_local_model", evidence_refs=(),
    )
    assert ctx.target_file == ""
    assert ctx.target_symbol == ""


def test_result_to_receipt_dict():
    r = CapabilityExecutionResult(
        name="ddtree", selected=True, invoked=True, gate_passed=True,
        outcome_contributed=True, evidence_present=True, evidence_refs=("ref1",),
        failure_reason="", telemetries={"saved_steps": 2},
    )
    d = r.to_receipt_dict()
    assert d["name"] == "ddtree"
    assert d["invoked"] is True
    assert d["gate_passed"] is True
    assert d["telemetries"]["saved_steps"] == 2


def test_result_invoked_false_needs_failure_reason():
    r = CapabilityExecutionResult(
        name="autoreason", selected=True, invoked=False, gate_passed=False,
        outcome_contributed=False, evidence_present=False, failure_reason="unsupported",
    )
    d = r.to_receipt_dict()
    assert d["invoked"] is False
    assert d["failure_reason"] == "unsupported"


def test_selected_capabilities_keep_tuple_order():
    req = LocalModelExecutorRequest(
        task_id="t4", problem_statement="p", repo_root="/ws",
        target_file="a.py", selected_capabilities=("z_cap", "a_cap", "m_cap"),
        evidence_refs=(),
    )
    ctx = build_capability_context_from_request(req, {})
    assert ctx.selected_capabilities == ("z_cap", "a_cap", "m_cap")
