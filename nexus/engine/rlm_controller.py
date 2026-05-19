from __future__ import annotations

from dataclasses import dataclass


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
