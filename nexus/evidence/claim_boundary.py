"""
Claim Boundary: fields and rules for claim eligibility.

All new report / receipt summary must support these fields.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ClaimBoundary:
    """Claim boundary fields for receipts and reports."""
    simulated: bool = False
    claim_eligible: bool = True
    receipt_present: bool = True
    model_calls: int = 0
    visible_tests_passed: int = 0
    hidden_tests_passed: int = 0
    public_claim_allowed: bool = True
    claim_block_reason: str = ""

    def evaluate(self) -> None:
        """Apply claim boundary rules. Modifies public_claim_allowed and claim_block_reason."""
        reasons = []

        if self.simulated:
            reasons.append("simulated=true")

        if not self.receipt_present:
            reasons.append("receipt_present=false")

        if not self.claim_eligible:
            reasons.append("claim_eligible=false")

        if self.model_calls == 0:
            reasons.append("model_calls=0")

        if reasons:
            self.public_claim_allowed = False
            self.claim_block_reason = "; ".join(reasons)
        else:
            self.public_claim_allowed = True
            self.claim_block_reason = ""

    def to_dict(self) -> dict:
        return {
            "simulated": self.simulated,
            "claim_eligible": self.claim_eligible,
            "receipt_present": self.receipt_present,
            "model_calls": self.model_calls,
            "visible_tests_passed": self.visible_tests_passed,
            "hidden_tests_passed": self.hidden_tests_passed,
            "public_claim_allowed": self.public_claim_allowed,
            "claim_block_reason": self.claim_block_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClaimBoundary":
        return cls(
            simulated=data.get("simulated", False),
            claim_eligible=data.get("claim_eligible", True),
            receipt_present=data.get("receipt_present", True),
            model_calls=data.get("model_calls", 0),
            visible_tests_passed=data.get("visible_tests_passed", 0),
            hidden_tests_passed=data.get("hidden_tests_passed", 0),
            public_claim_allowed=data.get("public_claim_allowed", True),
            claim_block_reason=data.get("claim_block_reason", ""),
        )


def evaluate_claim_boundary(
    *,
    simulated: bool,
    claim_eligible: bool,
    receipt_present: bool,
    model_calls: int,
    visible_tests_passed: int = 0,
    hidden_tests_passed: int = 0,
) -> ClaimBoundary:
    """Convenience function to build and evaluate a claim boundary."""
    boundary = ClaimBoundary(
        simulated=simulated,
        claim_eligible=claim_eligible,
        receipt_present=receipt_present,
        model_calls=model_calls,
        visible_tests_passed=visible_tests_passed,
        hidden_tests_passed=hidden_tests_passed,
    )
    boundary.evaluate()
    return boundary


CLAIM_RULES = [
    "simulated=true -> public_claim_allowed=false",
    "receipt_present=false -> public_claim_allowed=false",
    "claim_eligible=false -> public_claim_allowed=false",
    "model_calls=0 -> public_claim_allowed=false (cannot be model capability claim)",
    "workspace_provisioning_failure -> not counted as patcher failure",
]
