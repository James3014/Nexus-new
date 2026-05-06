from __future__ import annotations

from nexus.contracts.s2t_policy import S2TCandidate
from nexus.services.s2t_strict import S2TStrictRuntimeGate


def _candidate(candidate_id: str = "A", *, verifier_result: str = "pass") -> S2TCandidate:
    return S2TCandidate(
        candidate_id=candidate_id,
        source="repair_pass",
        content_ref=f".nexus/reports/s2t/{candidate_id}.json",
        selector_score=0.8,
        verifier_result=verifier_result,
        evidence_refs=[".nexus/reports/claim_gate.json"] if verifier_result == "pass" else [],
    )


def test_s2t_claim_gate_blocks_public_claim_without_gate_evidence() -> None:
    decision = S2TStrictRuntimeGate().evaluate(
        risk_tier="public_claim",
        candidates=[_candidate()],
        verifier_result="pass",
        verifier_evidence_ref="",
    )

    assert decision.passed is False
    assert decision.failure_reason == "public_claim_requires_gate_evidence"


def test_s2t_claim_gate_passes_verified_public_claim_with_evidence() -> None:
    decision = S2TStrictRuntimeGate().evaluate(
        risk_tier="public_claim",
        candidates=[_candidate()],
        verifier_result="pass",
        verifier_evidence_ref=".nexus/reports/claim_gate.json",
    )

    assert decision.passed is True
    assert decision.selected_candidate_id == "A"
