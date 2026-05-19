from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RLM_RUNTIME_DECISION_RECEIPT_SCHEMA = "nexus_rlm_runtime_decision_receipt.v1"


@dataclass
class RlmBudget:
    max_x_iterations: int = 3
    max_r_iterations: int = 4
    max_tokens: int = 150_000
    current_tokens: int = 0
    current_x_count: int = 0
    current_r_count: int = 0

    def observe_tokens(self, tokens: int) -> None:
        self.current_tokens = max(0, self.current_tokens + max(0, int(tokens or 0)))

    def observe_x_iteration(self) -> None:
        self.current_x_count = max(0, self.current_x_count + 1)

    def observe_r_iteration(self) -> None:
        self.current_r_count = max(0, self.current_r_count + 1)


class RlmController:
    def __init__(self, budget: RlmBudget | None = None):
        self.budget = budget or RlmBudget()

    def should_continue_x(self, belief_confidence: float) -> bool:
        if self.budget.current_x_count >= self.budget.max_x_iterations:
            return False
        if self.budget.current_tokens >= self.budget.max_tokens:
            return False
        return float(belief_confidence or 0.0) < 0.6

    def should_continue_r(self, *, gate_passed: bool, belief_confidence: float) -> bool:
        if bool(gate_passed) and float(belief_confidence or 0.0) >= 0.8:
            return False
        if self.budget.current_r_count >= self.budget.max_r_iterations:
            return False
        if self.budget.current_tokens >= self.budget.max_tokens:
            return False
        return True

    def terminal_reason(self, *, gate_passed: bool, belief_confidence: float) -> str:
        if bool(gate_passed) and float(belief_confidence or 0.0) >= 0.8:
            return "gate_passed_high_belief"
        if self.budget.current_tokens >= self.budget.max_tokens:
            return "token_budget_exhausted"
        if self.budget.current_x_count >= self.budget.max_x_iterations:
            return "x_iteration_budget_exhausted"
        if self.budget.current_r_count >= self.budget.max_r_iterations:
            return "r_iteration_budget_exhausted"
        return "continue_allowed"


def build_rlm_decision_receipt(
    *,
    loop_phase: str,
    gate_passed: bool,
    belief_confidence: float,
    current_tokens: int = 0,
    current_x_count: int = 0,
    current_r_count: int = 0,
    max_tokens: int = 150_000,
    max_x_iterations: int = 3,
    max_r_iterations: int = 4,
    source: str = "research_flow_service",
) -> dict[str, Any]:
    phase = str(loop_phase or "R").upper()
    budget = RlmBudget(
        max_x_iterations=max(1, int(max_x_iterations or 1)),
        max_r_iterations=max(1, int(max_r_iterations or 1)),
        max_tokens=max(1, int(max_tokens or 1)),
        current_tokens=max(0, int(current_tokens or 0)),
        current_x_count=max(0, int(current_x_count or 0)),
        current_r_count=max(0, int(current_r_count or 0)),
    )
    controller = RlmController(budget)
    if phase == "X":
        continue_allowed = controller.should_continue_x(belief_confidence)
    else:
        continue_allowed = controller.should_continue_r(
            gate_passed=gate_passed,
            belief_confidence=belief_confidence,
        )
    return {
        "schema_version": RLM_RUNTIME_DECISION_RECEIPT_SCHEMA,
        "status": "PASS",
        "source": source,
        "loop_phase": phase,
        "gate_passed": bool(gate_passed),
        "belief_confidence": float(belief_confidence or 0.0),
        "continue_allowed": bool(continue_allowed),
        "terminal_reason": controller.terminal_reason(
            gate_passed=gate_passed,
            belief_confidence=belief_confidence,
        ),
        "budget": {
            "max_tokens": budget.max_tokens,
            "current_tokens": budget.current_tokens,
            "max_x_iterations": budget.max_x_iterations,
            "current_x_count": budget.current_x_count,
            "max_r_iterations": budget.max_r_iterations,
            "current_r_count": budget.current_r_count,
        },
        "runtime_update_allowed": False,
        "claim_boundary": "runtime_receipt_only_not_public_claim",
    }
