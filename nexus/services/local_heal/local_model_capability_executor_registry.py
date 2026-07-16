"""Local model capability executor registry (dispatch helper — not authority).

Authority for execution class / Local mode is PLANNER_EXECUTION_CONTRACTS in
``nexus.services.capability_registry``. This registry only dispatches local
helpers and must not invent independent wiring truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Any

from nexus.services.local_heal.local_model_capability_context import (
    LocalModelCapabilityContext,
    CapabilityExecutionResult,
)


class BaseLocalCapabilityExecutor(Protocol):
    """Protocol for capability executors in local model path."""
    name: str
    phase: str

    def execute(self, ctx: LocalModelCapabilityContext) -> CapabilityExecutionResult: ...


class NoOpFailClosedExecutor:
    """Fail-closed executor for unsupported capabilities."""
    name = "unsupported"
    phase = ""

    def execute(self, ctx: LocalModelCapabilityContext) -> CapabilityExecutionResult:
        return CapabilityExecutionResult(
            name="unsupported",
            selected=True,
            invoked=False,
            gate_passed=False,
            outcome_contributed=False,
            evidence_present=False,
            failure_reason="unsupported_local_model_capability",
        )


class LocalModelCapabilityExecutorRegistry:
    """Registry for capability executors in local model path."""

    def __init__(self):
        self._executors: dict[str, BaseLocalCapabilityExecutor] = {}
        self._noop = NoOpFailClosedExecutor()

    def register(self, executor: BaseLocalCapabilityExecutor) -> None:
        self._executors[executor.name] = executor

    def get(self, name: str) -> BaseLocalCapabilityExecutor:
        return self._executors.get(name, self._noop)

    def execute_selected(
        self, ctx: LocalModelCapabilityContext
    ) -> dict[str, Any]:
        """Execute all selected capabilities and return structured results."""
        executed: list[str] = []
        blocked: list[str] = []
        unsupported: list[str] = []
        results: list[CapabilityExecutionResult] = []

        from nexus.services.local_heal.local_model_capability_wiring import (
            build_local_model_capability_wiring,
            CapabilityWiringStatus,
        )
        wiring = build_local_model_capability_wiring()

        for cap_name in ctx.selected_capabilities:
            w = wiring.get(cap_name)
            if w is None:
                unsupported.append(cap_name)
                results.append(CapabilityExecutionResult(
                    name=cap_name, selected=True, invoked=False,
                    gate_passed=False, outcome_contributed=False,
                    evidence_present=False, failure_reason="unknown_capability",
                ))
                continue

            if w.status in (CapabilityWiringStatus.EXTERNAL_ONLY, CapabilityWiringStatus.UNSUPPORTED):
                unsupported.append(cap_name)
                results.append(CapabilityExecutionResult(
                    name=cap_name, selected=True, invoked=False,
                    gate_passed=False, outcome_contributed=False,
                    evidence_present=False, failure_reason=w.reason,
                ))
                continue

            executor = self.get(cap_name)
            try:
                result = executor.execute(ctx)
                results.append(result)
                if result.invoked:
                    executed.append(cap_name)
                else:
                    blocked.append(cap_name)
            except Exception as e:
                blocked.append(cap_name)
                results.append(CapabilityExecutionResult(
                    name=cap_name, selected=True, invoked=False,
                    gate_passed=False, outcome_contributed=False,
                    evidence_present=False, failure_reason=f"executor_error: {e}",
                ))

        return {
            "executed_capabilities": executed,
            "blocked_capabilities": blocked,
            "unsupported_capabilities": unsupported,
            "capability_execution_results": [r.to_receipt_dict() for r in results],
        }
