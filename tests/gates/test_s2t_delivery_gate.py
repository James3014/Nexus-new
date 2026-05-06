from __future__ import annotations

from nexus.contracts.s2t_policy import S2TCandidate
from nexus.services.s2t_strict import S2TStrictRuntimeGate


def _candidate(candidate_id: str, *, verifier_result: str) -> S2TCandidate:
    return S2TCandidate(
        candidate_id=candidate_id,
        source="repair_pass",
        content_ref=f".nexus/reports/s2t/{candidate_id}.json",
        selector_score=0.9,
        verifier_result=verifier_result,
        evidence_refs=["tests/test_target.py"] if verifier_result == "pass" else [],
    )


def test_s2t_delivery_gate_blocks_when_no_verified_candidate_exists() -> None:
    decision = S2TStrictRuntimeGate().evaluate(
        risk_tier="high",
        candidates=[_candidate("A", verifier_result="fail")],
        verifier_result="fail",
    )

    assert decision.passed is False
    assert decision.failure_reason == "no_verified_candidate"


def test_s2t_delivery_gate_passes_verified_candidate() -> None:
    decision = S2TStrictRuntimeGate().evaluate(
        risk_tier="high",
        candidates=[_candidate("A", verifier_result="pass")],
        verifier_result="pass",
        verifier_evidence_ref="tests/test_target.py",
    )

    assert decision.passed is True
    assert decision.selected_candidate_id == "A"
