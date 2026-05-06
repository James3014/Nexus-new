from __future__ import annotations

from nexus.contracts.s2t_policy import S2TCandidate, S2TSelector


def _candidate(candidate_id: str, *, score: float, verifier_result: str = "pass") -> S2TCandidate:
    return S2TCandidate(
        candidate_id=candidate_id,
        source="repair_pass",
        content_ref=f".nexus/reports/s2t/{candidate_id}.json",
        static_score=0.5,
        selector_score=score,
        verifier_result=verifier_result,
        evidence_refs=["tests/test_target.py"] if verifier_result == "pass" else [],
    )


def test_s2t_selector_exposes_score_components_for_selected_candidate() -> None:
    decision = S2TSelector().select([_candidate("A", score=0.80), _candidate("B", score=0.70)])

    assert decision.selected_candidate_id == "A"
    assert decision.score_components["selector_score"] == 0.8
    assert decision.score_components["empirical_evidence_present"] == 1.0
    assert decision.second_pass_required is False


def test_s2t_selector_marks_close_scores_for_second_pass_verifier() -> None:
    decision = S2TSelector(tie_threshold=0.05).select([_candidate("A", score=0.80), _candidate("B", score=0.77)])

    assert decision.selected_candidate_id == "A"
    assert decision.second_pass_required is True
    assert "second_pass_required" in decision.reason_codes


def test_s2t_selector_never_selects_verifier_failed_candidate() -> None:
    decision = S2TSelector().select([_candidate("A", score=0.95, verifier_result="fail"), _candidate("B", score=0.70)])

    assert decision.selected_candidate_id == "B"
    assert "verifier_failed_candidate_excluded" in decision.reason_codes
