from __future__ import annotations

from dataclasses import dataclass

from nexus.contracts.s2t_policy import S2TCandidate, S2TSelector, S2TStrictGate


@dataclass(frozen=True)
class S2TStrictDecision:
    passed: bool
    selected_candidate_id: str
    failure_reason: str = ""
    reason_codes: tuple[str, ...] = ()


class S2TStrictRuntimeGate:
    """Fail-closed S2T gate for claim and delivery-sensitive nodes."""

    def __init__(self, *, selector: S2TSelector | None = None, gate: S2TStrictGate | None = None) -> None:
        self.selector = selector or S2TSelector()
        self.gate = gate or S2TStrictGate()

    def evaluate(
        self,
        *,
        risk_tier: str,
        candidates: list[S2TCandidate],
        verifier_result: str,
        verifier_evidence_ref: str = "",
    ) -> S2TStrictDecision:
        selection = self.selector.select(candidates)
        gate_result = self.gate.evaluate(
            risk_tier=risk_tier,
            decision=selection,
            verifier_result=verifier_result,
            verifier_evidence_ref=verifier_evidence_ref,
        )
        return S2TStrictDecision(
            passed=gate_result.gate_passed,
            selected_candidate_id=selection.selected_candidate_id,
            failure_reason=gate_result.failure_reason,
            reason_codes=tuple(selection.reason_codes),
        )
