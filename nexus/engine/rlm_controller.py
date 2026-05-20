from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RLM_RUNTIME_DECISION_RECEIPT_SCHEMA = "nexus_rlm_runtime_decision_receipt.v1"
RLM_NIGHTSHIFT_HANDOFF_RECEIPT_SCHEMA = "nexus_rlm_nightshift_handoff_receipt.v1"
RLM_BOUNDED_ORCHESTRATION_RECEIPT_SCHEMA = "nexus_rlm_bounded_orchestration_receipt.v1"


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


def build_nightshift_handoff_receipt(
    *,
    decision_receipt: dict[str, Any],
    artifact_gate_passed: bool,
    source: str = "research_flow_service",
) -> dict[str, Any]:
    budget = dict(decision_receipt.get("budget") or {})
    terminal_reason = str(decision_receipt.get("terminal_reason") or "")
    budget_exhausted = terminal_reason in {
        "token_budget_exhausted",
        "x_iteration_budget_exhausted",
        "r_iteration_budget_exhausted",
    }
    should_handoff = bool(not artifact_gate_passed and budget_exhausted)
    blockers: list[str] = []
    if artifact_gate_passed:
        blockers.append("artifact_gate_passed_no_handoff")
    if not budget_exhausted:
        blockers.append("rlm_budget_not_exhausted")
    return {
        "schema_version": RLM_NIGHTSHIFT_HANDOFF_RECEIPT_SCHEMA,
        "status": "PASS" if should_handoff else "NOT_APPLICABLE",
        "source": source,
        "recommended": should_handoff,
        "artifact_gate_passed": bool(artifact_gate_passed),
        "terminal_reason": terminal_reason or "unknown",
        "budget": budget,
        "blockers": blockers,
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "claim_boundary": "handoff_receipt_only_not_runtime_or_public_claim",
    }


def build_bounded_rlm_orchestration_receipt(
    *,
    gate_passed: bool,
    belief_confidence: float,
    current_tokens: int = 0,
    x_observations: int = 0,
    r_observations: int = 0,
    max_tokens: int = 150_000,
    max_x_iterations: int = 3,
    max_r_iterations: int = 4,
    source: str = "research_flow_service",
) -> dict[str, Any]:
    """Build a bounded X/R-loop orchestration receipt without dispatching loops.

    This adapter closes the routing-spec-v2 RLM seam by making the X/R budget
    decision explicit while keeping the existing ResearchFlowService flow intact.
    It does not execute recursive work, update runtime policy, or unlock public
    benchmark claims.
    """

    x_count = max(0, int(x_observations or 0))
    r_count = max(0, int(r_observations or 0))
    x_receipt = build_rlm_decision_receipt(
        loop_phase="X",
        gate_passed=False,
        belief_confidence=belief_confidence,
        current_tokens=current_tokens,
        current_x_count=x_count,
        current_r_count=r_count,
        max_tokens=max_tokens,
        max_x_iterations=max_x_iterations,
        max_r_iterations=max_r_iterations,
        source=source,
    )
    r_receipt = build_rlm_decision_receipt(
        loop_phase="R",
        gate_passed=gate_passed,
        belief_confidence=belief_confidence,
        current_tokens=current_tokens,
        current_x_count=x_count,
        current_r_count=r_count,
        max_tokens=max_tokens,
        max_x_iterations=max_x_iterations,
        max_r_iterations=max_r_iterations,
        source=source,
    )
    final_receipt = r_receipt if r_count > 0 or gate_passed else x_receipt
    handoff = build_nightshift_handoff_receipt(
        decision_receipt=final_receipt,
        artifact_gate_passed=gate_passed,
        source=source,
    )
    return {
        "schema_version": RLM_BOUNDED_ORCHESTRATION_RECEIPT_SCHEMA,
        "status": "PASS",
        "source": source,
        "orchestration_mode": "bounded_adapter_not_dispatch",
        "x_loop_decision_receipt": x_receipt,
        "r_loop_decision_receipt": r_receipt,
        "final_decision_receipt": final_receipt,
        "nightshift_handoff_receipt": handoff,
        "budget": dict(final_receipt.get("budget") or {}),
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "claim_boundary": "bounded_orchestration_receipt_only_not_runtime_or_public_claim",
    }
