from typing import List, Optional
from nexus.core.gate_evaluator import AbstractGateRule, GateRuleResult


class CostRatioRule(AbstractGateRule):
    """🛡️ Checks if token cost ratio is within safe limits."""

    def __init__(self, max_ratio: float = 1.2):
        self.max_ratio = max_ratio

    def evaluate(self, context: dict) -> GateRuleResult:
        ratio = context.get("token_cost_ratio")
        if ratio is not None and float(ratio) > self.max_ratio:
            return GateRuleResult(
                passed=False,
                reason_code="COST_RATIO_EXCEEDED",
                reason=f"Token cost ratio {ratio:.2f} exceeds threshold {self.max_ratio:.2f}",
                evidence_refs=[f"ratio:{ratio}"]
            )
        return GateRuleResult(
            passed=True,
            reason_code="COST_RATIO_OK",
            reason="Token cost ratio is within safe limits",
            evidence_refs=[]
        )


class DenominatorRule(AbstractGateRule):
    """🛡️ Checks if chunks count meets baseline requirements."""

    def __init__(self, min_chunks: int = 100):
        self.min_chunks = min_chunks

    def evaluate(self, context: dict) -> GateRuleResult:
        chunks = context.get("chunks_count") or context.get("denominator")
        if chunks is not None and int(chunks) < self.min_chunks:
            return GateRuleResult(
                passed=False,
                reason_code="DENOMINATOR_CONSERVATION_VIOLATION",
                reason=f"Chunks count {chunks} is below threshold {self.min_chunks}",
                evidence_refs=[f"chunks:{chunks}"]
            )
        return GateRuleResult(
            passed=True,
            reason_code="DENOMINATOR_OK",
            reason="Chunks count meets baseline requirements",
            evidence_refs=[]
        )


class BlockerCleanRule(AbstractGateRule):
    """🛡️ Checks if there are any active policy blockers in context."""

    def evaluate(self, context: dict) -> GateRuleResult:
        blockers = context.get("blockers") or []
        # If there are active blockers, fail validation
        if blockers:
            return GateRuleResult(
                passed=False,
                reason_code="ACTIVE_BLOCKERS_PRESENT",
                reason=f"Active policy blockers detected: {', '.join(blockers)}",
                evidence_refs=[f"blockers:{blockers}"]
            )
        return GateRuleResult(
            passed=True,
            reason_code="BLOCKERS_CLEAN",
            reason="No active policy blockers found",
            evidence_refs=[]
        )
