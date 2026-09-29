"""Acceptance tests for Issue #1199: PR issue closure intent guard."""

from __future__ import annotations

import pytest

from nexus.services.issue_closure_guard import (
    CLAIM_CEILING,
    INTENT_SCHEMA,
    IssueClosureIntentError,
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
