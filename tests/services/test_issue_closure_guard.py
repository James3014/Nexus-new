"""Acceptance tests for Issue #1199: PR issue closure intent guard."""

from __future__ import annotations

import pytest

from nexus.services.issue_closure_guard import (
    CLAIM_CEILING,
    INTENT_SCHEMA,
    MERGE_INTENT_BINDING_SCHEMA,
    IssueClosureIntentError,
    validate_final_merge_intent_binding,
    validate_issue_closure_intent,
    verify_post_merge_state,
)

FIXTURE_1191_ACCIDENTAL_CLOSE = """\
Implement the read-only operator-doctor slice of #1188.

What this adds:
- canonical `nexus.workflow_doctor.v1` projection

This does not close #1188; the umbrella remains open for its standalone-owner child contracts and later full cross-session acceptance.

<!-- NEXUS_ISSUE_INTENT_V1
{
  "issue": 1188,
  "on_merge": "KEEP_OPEN"
}
NEXUS_ISSUE_INTENT_V1 -->
"""

FIXTURE_1188_NEUTRAL_PROSE_PASS = """\
Implement the read-only operator-doctor slice of #1188.

What this adds:
- canonical `nexus.workflow_doctor.v1` projection

#1188 remains open for its standalone-owner child contracts and later full cross-session acceptance.

<!-- NEXUS_ISSUE_INTENT_V1
{
  "issue": 1188,
  "on_merge": "KEEP_OPEN"
}
NEXUS_ISSUE_INTENT_V1 -->
"""

FIXTURE_EXPLICIT_CLOSE_PASS = """\
Implement and close the issue.

Closes #1188

<!-- NEXUS_ISSUE_INTENT_V1
{
  "issue": 1188,
  "on_merge": "CLOSE"
}
NEXUS_ISSUE_INTENT_V1 -->
"""

FIXTURE_UNINTENDED_CLOSING_KEYWORD = """\
Fix some minor typos.

Also fixes #1192 in passing.

<!-- NEXUS_ISSUE_INTENT_V1
{
  "issue": 1188,
  "on_merge": "KEEP_OPEN"
}
NEXUS_ISSUE_INTENT_V1 -->
"""


def test_fixture_1191_negated_close_fails_before_merge():
    """Criterion 1: Fixture reproduces #1191 text 'This does not close #1188' and the guard fails."""
    with pytest.raises(IssueClosureIntentError, match="REJECTED_CLOSING_KEYWORD_FOR_KEEP_OPEN"):
        validate_issue_closure_intent(FIXTURE_1191_ACCIDENTAL_CLOSE)


def test_neutral_prose_with_keep_open_passes():
    """Criterion 2: '#1188 remains open' with KEEP_OPEN passes."""
    result = validate_issue_closure_intent(FIXTURE_1188_NEUTRAL_PROSE_PASS)
    assert result["schema"] == INTENT_SCHEMA
    assert result["status"] == "PASS"
    assert result["claim_ceiling"] == CLAIM_CEILING
    assert result["intents"] == [{"issue_number": 1188, "on_merge": "KEEP_OPEN"}]
    assert result["detected_closing_references"] == []


def test_explicit_close_passes():
    """Criterion 3: explicit CLOSE with one intended closing declaration passes."""
    result = validate_issue_closure_intent(FIXTURE_EXPLICIT_CLOSE_PASS)
    assert result["status"] == "PASS"
    assert result["intents"] == [{"issue_number": 1188, "on_merge": "CLOSE"}]
    assert result["detected_closing_references"] == [{"issue_number": 1188, "keyword": "closes"}]


def test_explicit_close_missing_declaration_fails():
    """Criterion 3 (cont): CLOSE declared in intent without closing keyword in prose fails."""
    body = """\
Some work done.

<!-- NEXUS_ISSUE_INTENT_V1
{
  "issue": 1188,
  "on_merge": "CLOSE"
}
NEXUS_ISSUE_INTENT_V1 -->
"""
    with pytest.raises(IssueClosureIntentError, match="MISSING_EXPLICIT_CLOSING_DECLARATION"):
        validate_issue_closure_intent(body)


def test_unintended_closing_keyword_for_different_issue_surfaced():
    """Criterion 4: accidental close keyword targeting a different/unrelated Issue is surfaced."""
    with pytest.raises(
        IssueClosureIntentError, match="UNINTENDED_CLOSING_KEYWORD_FOR_UNTRACKED_ISSUE"
    ):
        validate_issue_closure_intent(FIXTURE_UNINTENDED_CLOSING_KEYWORD)


def test_post_merge_state_mismatch_detected_and_persisted():
    """Criterion 5: post-merge state mismatch is detected and persisted."""
    intents = [{"issue_number": 1188, "on_merge": "KEEP_OPEN"}]
    # GitHub erroneously closed #1188
    actual_states = {1188: "closed"}
    merged_pr = {"pr_number": 1191, "head_sha": "a" * 40}

    record = verify_post_merge_state(
        intents=intents,
        actual_issue_states=actual_states,
        merged_pr=merged_pr,
    )
    assert record["status"] == "STATE_MISMATCH_DETECTED"
    assert len(record["mismatches"]) == 1
    assert "STATE_MISMATCH" in record["mismatches"][0]
    assert record["checks"][0]["matched"] is False

    # When states match properly
    actual_states_ok = {1188: "open"}
    record_ok = verify_post_merge_state(
        intents=intents,
        actual_issue_states=actual_states_ok,
        merged_pr=merged_pr,
    )
    assert record_ok["status"] == "PASS"
    assert record_ok["mismatches"] == []
    assert record_ok["checks"][0]["matched"] is True


def test_case_insensitive_keyword_coverage():
    """Verify keyword families case-insensitively: close, fix, resolve."""
    for kw in (
        "CLOSE",
        "closes",
        "Closed",
        "fix",
        "FIXES",
        "fixed",
        "resolve",
        "Resolves",
        "RESOLVED",
    ):
        body = f"""\
Note on #{1188}: does not {kw} #1188.

<!-- NEXUS_ISSUE_INTENT_V1
{{
  "issue": 1188,
  "on_merge": "KEEP_OPEN"
}}
NEXUS_ISSUE_INTENT_V1 -->
"""
        with pytest.raises(IssueClosureIntentError, match="REJECTED_CLOSING_KEYWORD_FOR_KEEP_OPEN"):
            validate_issue_closure_intent(body)


def test_validate_final_merge_intent_binding_keep_open_success():
    """KEEP_OPEN with neutral final merge message is allowed and passes."""
    body = FIXTURE_1188_NEUTRAL_PROSE_PASS
    result = validate_final_merge_intent_binding(
        pr_body=body,
        pr_number=1191,
        head_sha="a" * 40,
        base_sha="b" * 40,
        expected_pr_number=1191,
        expected_head_sha="a" * 40,
        expected_base_sha="b" * 40,
        merge_method="squash",
        commit_title="fix(#1188): operator doctor slice",
        commit_message="Implement operator doctor slice.\n\n#1188 remains open.",
    )
    assert result["schema"] == MERGE_INTENT_BINDING_SCHEMA
    assert result["status"] == "PASS"
    assert result["merge_method"] == "squash"
    assert result["intents"] == [{"issue_number": 1188, "on_merge": "KEEP_OPEN"}]


def test_validate_final_merge_intent_binding_historical_1236_fixture_fails():
    """The #1236/#1232 historical regression fixture: PR declared KEEP_OPEN for #1232,

    but final squash commit message contained 'Closes #1232'.
    Must be rejected at the final merge effect boundary before merge.
    """
    pr_body_1236 = """\
## Summary
Separate expired predecessor structural read from live authority seam.

#1232 remains open for complete acceptance.

<!-- NEXUS_ISSUE_INTENT_V1
{
  "issue": 1232,
  "on_merge": "KEEP_OPEN"
}
NEXUS_ISSUE_INTENT_V1 -->
"""
    final_commit_title = (
        "fix(#1232): separate expired predecessor structural read from live authority seam"
    )
    final_commit_message = "Closes #1232\n\n## Requalification on current main..."

    with pytest.raises(
        IssueClosureIntentError,
        match="REJECTED_CLOSING_KEYWORD_FOR_KEEP_OPEN_IN_FINAL_MERGE_FIELDS",
    ):
        validate_final_merge_intent_binding(
            pr_body=pr_body_1236,
            pr_number=1236,
            head_sha="c" * 40,
            base_sha="d" * 40,
            expected_pr_number=1236,
            expected_head_sha="c" * 40,
            expected_base_sha="d" * 40,
            merge_method="squash",
            commit_title=final_commit_title,
            commit_message=final_commit_message,
        )


def test_validate_final_merge_intent_binding_untracked_issue_in_final_fields():
    """Untracked issue closing keyword in final fields fails closed."""
    body = FIXTURE_1188_NEUTRAL_PROSE_PASS
    with pytest.raises(
        IssueClosureIntentError,
        match="UNINTENDED_CLOSING_KEYWORD_FOR_UNTRACKED_ISSUE",
    ):
        validate_final_merge_intent_binding(
            pr_body=body,
            pr_number=1191,
            head_sha="a" * 40,
            base_sha="b" * 40,
            expected_pr_number=1191,
            expected_head_sha="a" * 40,
            expected_base_sha="b" * 40,
            merge_method="merge",
            commit_title="fix(#1188): work",
            commit_message="Also fixes #9999 in passing",
        )


def test_validate_final_merge_intent_binding_identity_mismatches():
    """PR number, head SHA, base SHA, or merge method mismatches fail closed."""
    body = FIXTURE_1188_NEUTRAL_PROSE_PASS
    # PR number mismatch
    with pytest.raises(IssueClosureIntentError, match="PR_NUMBER_MISMATCH"):
        validate_final_merge_intent_binding(
            pr_body=body,
            pr_number=1192,
            head_sha="a" * 40,
            base_sha="b" * 40,
            expected_pr_number=1191,
            expected_head_sha="a" * 40,
            expected_base_sha="b" * 40,
            merge_method="squash",
        )

    # Head SHA mismatch
    with pytest.raises(IssueClosureIntentError, match="HEAD_SHA_MISMATCH"):
        validate_final_merge_intent_binding(
            pr_body=body,
            pr_number=1191,
            head_sha="e" * 40,
            base_sha="b" * 40,
            expected_pr_number=1191,
            expected_head_sha="a" * 40,
            expected_base_sha="b" * 40,
            merge_method="squash",
        )

    # Base SHA mismatch
    with pytest.raises(IssueClosureIntentError, match="BASE_SHA_MISMATCH"):
        validate_final_merge_intent_binding(
            pr_body=body,
            pr_number=1191,
            head_sha="a" * 40,
            base_sha="f" * 40,
            expected_pr_number=1191,
            expected_head_sha="a" * 40,
            expected_base_sha="b" * 40,
            merge_method="squash",
        )

    # Unsupported merge method
    with pytest.raises(IssueClosureIntentError, match="UNSUPPORTED_MERGE_METHOD"):
        validate_final_merge_intent_binding(
            pr_body=body,
            pr_number=1191,
            head_sha="a" * 40,
            base_sha="b" * 40,
            expected_pr_number=1191,
            expected_head_sha="a" * 40,
            expected_base_sha="b" * 40,
            merge_method="cherry-pick",
        )


def test_validate_final_merge_intent_binding_explicit_close_allowed():
    """Explicit authorized CLOSE with matching final fields succeeds."""
    body = FIXTURE_EXPLICIT_CLOSE_PASS
    result = validate_final_merge_intent_binding(
        pr_body=body,
        pr_number=1191,
        head_sha="a" * 40,
        base_sha="b" * 40,
        expected_pr_number=1191,
        expected_head_sha="a" * 40,
        expected_base_sha="b" * 40,
        merge_method="squash",
        commit_title="fix(#1188): close issue",
        commit_message="Closes #1188",
    )
    assert result["status"] == "PASS"
    assert result["intents"] == [{"issue_number": 1188, "on_merge": "CLOSE"}]


def test_verify_post_merge_state_reconciliation_contract():
    """Post-merge state verification enforces bounded reconciliation and prohibits second merge."""
    intents = [{"issue_number": 1232, "on_merge": "KEEP_OPEN"}]
    # Erroneously closed
    actual_states = {1232: "closed"}
    merged_pr = {
        "pr_number": 1236,
        "head_sha": "a" * 40,
        "base_sha": "b" * 40,
        "merge_commit_sha": "c" * 40,
    }

    record = verify_post_merge_state(
        intents=intents,
        actual_issue_states=actual_states,
        merged_pr=merged_pr,
    )
    assert record["status"] == "STATE_MISMATCH_DETECTED"
    assert record["disposition"] == "RECONCILIATION_REQUIRED"
    assert record["allow_second_merge"] is False
    assert record["merged_pr"]["merge_commit_sha"] == "c" * 40


def test_validate_final_merge_intent_binding_pr_body_required():
    """PR body is strictly required for final merge intent binding validation."""
    for invalid_body in (None, "", "   ", "\n\t"):
        with pytest.raises(IssueClosureIntentError, match="PR_BODY_REQUIRED"):
            validate_final_merge_intent_binding(
                pr_body=invalid_body,
                pr_number=1191,
                head_sha="a" * 40,
                base_sha="b" * 40,
                expected_pr_number=1191,
                expected_head_sha="a" * 40,
                expected_base_sha="b" * 40,
                merge_method="squash",
            )
