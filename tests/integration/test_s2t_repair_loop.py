from __future__ import annotations

from nexus.contracts.s2t_policy import NO_VERIFIED_CANDIDATE, S2TCandidate
from nexus.services.s2t_repair import S2TRepairCandidateLoop


def _candidate(candidate_id: str, *, score: float, verifier_result: str = "not_run") -> S2TCandidate:
    return S2TCandidate(
        candidate_id=candidate_id,
        source="repair_pass",
        content_ref=f".nexus/reports/s2t/{candidate_id}.json",
        selector_score=score,
        static_score=score,
        verifier_result=verifier_result,
        evidence_refs=["tests/test_target.py"] if verifier_result == "pass" else [],
    )


def test_s2t_repair_loop_tries_next_candidate_when_top_candidate_fails_verifier() -> None:
    candidates = [
        _candidate("A", score=0.95, verifier_result="not_run"),
        _candidate("B", score=0.80, verifier_result="pass"),
    ]

    result = S2TRepairCandidateLoop(max_attempts=2).run(
        candidates,
        verify=lambda candidate: candidate.candidate_id == "B",
    )

    assert result.verified is True
    assert result.selected_candidate_id == "B"
    assert result.attempted_candidate_ids == ("A", "B")


def test_s2t_repair_loop_fails_closed_when_budget_is_exhausted() -> None:
    candidates = [
        _candidate("A", score=0.95, verifier_result="not_run"),
        _candidate("B", score=0.80, verifier_result="not_run"),
    ]

    result = S2TRepairCandidateLoop(max_attempts=1).run(candidates, verify=lambda _candidate: False)

    assert result.verified is False
    assert result.selected_candidate_id == NO_VERIFIED_CANDIDATE
    assert result.failure_reason == "budget_exhausted_or_no_verified_candidate"
