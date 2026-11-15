"""Regression cases for withdrawn review verdict shapes in #3453."""

from scripts.ops import review_record_check as rrc

HEAD = "8d70e3ff83eb16c7b1f4af93ae9d87e01d5fe129"
DOCS = [{"filename": "docs/a.md", "status": "modified"}]


def _comment(body):
    return {"body": body, "user": {"login": "reviewer"}, "created_at": "2026-11-15T00:00:00Z"}


def _status_after_withdrawal(body):
    comments = [
        _comment(f"Claude review: ACCEPT@{HEAD}"),
        _comment(body),
    ]
    return rrc.evaluate(HEAD, DOCS, comments, [])["status"]


def test_bullet_withdrawal_retracts_prior_accept():
    assert (
        _status_after_withdrawal(f"- Withdrawn: Claude Verdict: ACCEPT@{HEAD}") == "MISSING_RECORD"
    )


def test_full_width_colon_withdrawal_retracts_prior_accept():
    assert (
        _status_after_withdrawal(f"Withdrawn： Claude Verdict: ACCEPT@{HEAD}") == "MISSING_RECORD"
    )


def test_withdrawal_tag_after_reviewer_label_retracts_prior_accept():
    assert (
        _status_after_withdrawal(f"Claude review: Withdrawn: Verdict: ACCEPT@{HEAD}")
        == "MISSING_RECORD"
    )


def test_accept_pending_ci_retracts_prior_accept():
    assert _status_after_withdrawal(f"Claude review: ACCEPT@{HEAD} pending CI") == "MISSING_RECORD"


def test_accept_pending_ci_followed_by_passed_does_not_retract_prior_accept():
    assert _status_after_withdrawal(
        f"Claude review: ACCEPT@{HEAD} pending CI passed afterwards"
    ) == "OK"


def test_stale_finding_prose_before_verdict_does_not_retract_accept():
    assert (
        _status_after_withdrawal(
            f"The stale: finding was resolved; Claude Verdict: ACCEPT@{HEAD}"
        )
        == "OK"
    )


def test_withdrawal_tag_only_applies_until_next_verdict_or_reviewer():
    reads = rrc._verdict_reads(
        f"Claude: Withdrawn: ACCEPT@{HEAD}; Gemini Verdict: ACCEPT@{HEAD}"
    )
    assert [withdrawn for _clause, withdrawn in reads] == [True, False]


def test_withdrawal_labels_are_case_insensitive():
    for label in ("WITHDRAWN", "withdrawn"):
        assert (
            _status_after_withdrawal(f"Claude review: {label}: Verdict: ACCEPT@{HEAD}")
            == "MISSING_RECORD"
        )


def test_normal_bold_accept_at_sha_still_passes():
    comments = [_comment(f"Claude review: **ACCEPT** at {HEAD}")]
    assert rrc.evaluate(HEAD, DOCS, comments, [])["status"] == "OK"
