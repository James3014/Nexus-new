from __future__ import annotations

import pytest

from nexus.services.local_heal.local_model_capability_executor_registry import (
    LocalModelCapabilityExecutorRegistry,
    NoOpFailClosedExecutor,
)
from nexus.services.local_heal.local_model_capability_context import (
    LocalModelCapabilityContext,
    CapabilityExecutionResult,
)


class FakeExecutor:
    name = "ddtree"
    phase = "D"

    def execute(self, ctx):
        return CapabilityExecutionResult(
            name="ddtree", selected=True, invoked=True, gate_passed=True,
            outcome_contributed=True, evidence_present=True,
            telemetries={"saved_steps": 3},
        )


def _make_ctx(selected=("ddtree",)):
    return LocalModelCapabilityContext(
        task_id="t1", source_root="/ws", problem_statement="p",
        target_file="a.py", target_symbol="f", selected_capabilities=selected,
        execution_topology="local_committee_only", evidence_refs=("ref1",),
    )


def test_registry_execute_selected_with_executor():
    reg = LocalModelCapabilityExecutorRegistry()
    reg.register(FakeExecutor())
    result = reg.execute_selected(_make_ctx(("ddtree",)))
    assert "ddtree" in result["executed_capabilities"]
    assert "ddtree" not in result["unsupported_capabilities"]
    assert len(result["capability_execution_results"]) == 1
    assert result["capability_execution_results"][0]["invoked"] is True


def test_registry_unknown_capability_unsupported():
    reg = LocalModelCapabilityExecutorRegistry()
    result = reg.execute_selected(_make_ctx(("totally_fake",)))
    assert "totally_fake" in result["unsupported_capabilities"]
    assert result["capability_execution_results"][0]["invoked"] is False
    assert "unknown_capability" in result["capability_execution_results"][0]["failure_reason"]


def test_registry_external_only_unsupported():
    reg = LocalModelCapabilityExecutorRegistry()
    result = reg.execute_selected(_make_ctx(("swarm_multi_agent",)))
    assert "swarm_multi_agent" in result["unsupported_capabilities"]
    assert result["capability_execution_results"][0]["invoked"] is False


def test_registry_mixed_capabilities():
    reg = LocalModelCapabilityExecutorRegistry()
    reg.register(FakeExecutor())
    result = reg.execute_selected(_make_ctx(("ddtree", "swarm_multi_agent", "totally_fake")))
    assert "ddtree" in result["executed_capabilities"]
    assert "swarm_multi_agent" in result["unsupported_capabilities"]
    assert "totally_fake" in result["unsupported_capabilities"]
    assert len(result["capability_execution_results"]) == 3


def test_noop_executor():
    noop = NoOpFailClosedExecutor()
    ctx = _make_ctx()
    result = noop.execute(ctx)
    assert result.invoked is False
    assert result.gate_passed is False
    assert "unsupported" in result.failure_reason


def test_registry_result_deterministic_order():
    reg = LocalModelCapabilityExecutorRegistry()
    reg.register(FakeExecutor())
    result = reg.execute_selected(_make_ctx(("ddtree",)))
    assert result["capability_execution_results"][0]["name"] == "ddtree"
    assert result["capability_execution_results"][0]["selected"] is True
