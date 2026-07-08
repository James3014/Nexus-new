from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MemoryDecision:
    """Decision output for memory eligibility."""
    allowed: bool
    decision_mode: str  # "decision_eligible" | "audit_only" | "blocked_by_policy" | "blocked_by_mem_palace" | "blocked_by_low_copyability" | "blocked_by_unverified_outcome"
    reason: str
    policy_ref: str
    mem_palace_ref: str


def evaluate_memory_decision(
    *,
    copyability_score: float,
    decision_eligibility: str,
    memory_confidence_signal: float = 0.0,
    task_difficulty: str = "",
    phase: str = "",
) -> MemoryDecision:
    """Evaluate memory decision eligibility through MemPalace + policy_gate governance.

    Prevents unverified/policy-blocked memory from influencing P5/P6 decisions.
    """
    # Check 1: Low copyability → blocked
    if copyability_score < 0.50:
        return MemoryDecision(
            allowed=False,
            decision_mode="blocked_by_low_copyability",
            reason=f"copyability_score={copyability_score:.2f} < 0.50",
            policy_ref="",
            mem_palace_ref="",
        )

    # Check 2: Unverified outcome → blocked
    if decision_eligibility != "decision_eligible":
        return MemoryDecision(
            allowed=False,
            decision_mode="blocked_by_unverified_outcome",
            reason=f"decision_eligibility={decision_eligibility}",
            policy_ref="",
            mem_palace_ref="",
        )

    # Check 3: Policy gate (stub — always allows for now)
    # In production, this would call policy_gate.evaluate()
    policy_ref = "policy_gate_stub"
    policy_allowed = True  # stub: always allows

    if not policy_allowed:
        return MemoryDecision(
            allowed=False,
            decision_mode="blocked_by_policy",
            reason="policy_gate_blocked",
            policy_ref=policy_ref,
            mem_palace_ref="",
        )

    # Check 4: MemPalace gate (stub — always allows for now)
    # In production, this would call MemPalace.evaluate()
    mem_palace_ref = "mem_palace_stub"
    mem_palace_allowed = True  # stub: always allows

    if not mem_palace_allowed:
        return MemoryDecision(
            allowed=False,
            decision_mode="blocked_by_mem_palace",
            reason="mem_palace_blocked",
            policy_ref=policy_ref,
            mem_palace_ref=mem_palace_ref,
        )

    # All checks passed → allowed
    return MemoryDecision(
        allowed=True,
        decision_mode="decision_eligible",
        reason="all_checks_passed",
        policy_ref=policy_ref,
        mem_palace_ref=mem_palace_ref,
    )
