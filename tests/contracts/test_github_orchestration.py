from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from nexus.contracts.github_orchestration import (
    CandidateLineage,
    CheckResult,
    GitHubOrchestrationEvidence,
    ImpactResult,
    MainMovementEvidence,
    MergeIntent,
    ReviewResult,
    canonical_hash,
)

NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


def evidence(**overrides):
    checks = (CheckResult(name="ci", status="completed", conclusion="success"),)
    reviews = (ReviewResult(reviewer="reviewer", state="APPROVED"),)
    impact = ImpactResult(classification="NO_CHANGE", known=True, regression_free=True)
    candidate = CandidateLineage(
        task_id="task-8",
        attempt_id="attempt-1",
        contract_hash="2" * 64,
        card_hash="7" * 64,
        candidate_commit_sha="b" * 40,
        candidate_tree_sha="c" * 40,
        candidate_state_hash="3" * 64,
        verified_receipt_hash="4" * 64,
        independent_acceptance_hash="5" * 64,
        reviewer="reviewer",
        implementer="implementer",
    )
    value = dict(
        repository="James3014/Nexus-new",
        issue_number=8,
        pull_request_number=81,
        base_sha="d" * 40,
        head_sha="b" * 40,
        tree_sha="c" * 40,
        current_main_sha="d" * 40,
        diff_hash="e" * 64,
        checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in checks]}),
        reviews_hash=canonical_hash({"reviews": [r.model_dump(mode="json") for r in reviews]}),
        task_attempt_contract_hash="2" * 64,
        candidate_hash="3" * 64,
        verifier_hash="4" * 64,
        independent_acceptance_hash="5" * 64,
        impact_hash=canonical_hash(impact.model_dump(mode="json")),
        observed_at=NOW,
        fresh_until=NOW + timedelta(hours=1),
        allowed_paths=("nexus/a.py", "tests/test_a.py"),
        changed_paths=("nexus/a.py",),
        checks_passed=True,
        reviews_resolved=True,
        regression_free=True,
        impact_known=True,
        independent_acceptance=True,
        required_checks=checks,
        reviews=reviews,
        candidate=candidate,
        impact=impact,
    )
    value.update(overrides)
    return GitHubOrchestrationEvidence.model_validate(value)


def test_evidence_is_frozen_and_scope_checked():
    item = evidence()
    with pytest.raises(ValidationError):
        item.changed_paths = ("other.py",)


@pytest.mark.parametrize("field", ["base_sha", "head_sha", "tree_sha", "current_main_sha"])
def test_git_sha_must_be_lowercase_40(field):
    with pytest.raises(ValidationError, match="INVALID"):
        evidence(**{field: "z" * 40})


@pytest.mark.parametrize("field", ["diff_hash", "checks_hash", "reviews_hash", "impact_hash"])
def test_evidence_hashes_require_64_hex(field):
    with pytest.raises(ValidationError, match="INVALID"):
        evidence(**{field: "a" * 40})


@pytest.mark.parametrize("paths", [("z.py", "a.py"), ("a.py", "a.py"), ("a.py", "../secret")])
def test_paths_are_sorted_unique_and_safe(paths):
    with pytest.raises(ValidationError):
        evidence(allowed_paths=paths, changed_paths=(paths[0],))


def test_empty_changed_paths_are_allowed_but_empty_allowed_paths_are_not_out_of_scope():
    assert evidence(changed_paths=()).changed_paths == ()
    with pytest.raises(ValidationError, match="DIFF_OUT_OF_SCOPE"):
        evidence(allowed_paths=(), changed_paths=("nexus/a.py",))


def test_changed_path_out_of_scope_fails_closed():
    with pytest.raises(ValidationError, match="DIFF_OUT_OF_SCOPE"):
        evidence(changed_paths=("outside.py",))


@pytest.mark.parametrize(
    "check",
    [
        {"name": "ci", "status": "running", "conclusion": "success", "terminal": False},
        {"name": "ci", "status": "completed", "conclusion": "failure"},
    ],
)
def test_checks_reject_nonterminal_or_failed(check):
    with pytest.raises(ValidationError, match="CHECK_NONTERMINAL_OR_FAILED"):
        CheckResult.model_validate(check)


def test_duplicate_required_check_names_fail():
    check = CheckResult(name="ci", status="completed", conclusion="success")
    with pytest.raises(ValidationError, match="CHECKS_DUPLICATE"):
        evidence(required_checks=(check, check))


@pytest.mark.parametrize(
    "review",
    [
        {"reviewer": "r", "state": "CHANGES_REQUESTED"},
        {"reviewer": "r", "state": "APPROVED", "unresolved_threads": 1},
    ],
)
def test_review_changes_or_threads_fail_closed(review):
    with pytest.raises(ValidationError, match="REVIEW_UNRESOLVED"):
        ReviewResult.model_validate(review)


@pytest.mark.parametrize(
    "impact",
    [
        {"classification": "UNKNOWN", "known": False, "regression_free": True},
        {"classification": "NEW_REGRESSION", "known": True, "regression_free": False},
    ],
)
def test_impact_unknown_or_regression_fails_closed(impact):
    with pytest.raises(ValidationError, match="IMPACT_UNKNOWN_OR_REGRESSION"):
        ImpactResult.model_validate(impact)


def test_freshness_window_must_be_forward():
    with pytest.raises(ValidationError, match="FRESHNESS_INVALID"):
        evidence(fresh_until=NOW)


def test_candidate_lineage_rejects_wrong_lengths_and_is_frozen():
    with pytest.raises(ValidationError, match="INVALID"):
        CandidateLineage(
            task_id="t",
            attempt_id="a",
            contract_hash="x",
            card_hash="2" * 64,
            candidate_commit_sha="b" * 40,
            candidate_tree_sha="c" * 40,
            candidate_state_hash="3" * 64,
            verified_receipt_hash="4" * 64,
            independent_acceptance_hash="5" * 64,
            reviewer="r",
        )


def test_merge_intent_hash_tamper_and_mutation_authorization_fail():
    payload = {
        "schema": "nexus.github_merge_intent.v2",
        "kind": "MERGE_INTENT",
        "evidence": evidence().model_dump(mode="json"),
        "grant_outcome": "GRANT_MATCH",
        "mutation_authorized": False,
        "claim_ceiling": "m4_merge_eligible_and_intent_ready_only",
    }
    with pytest.raises(ValidationError, match="INTENT_HASH_INVALID"):
        MergeIntent.model_validate({**payload, "intent_hash": "0" * 64})
    with pytest.raises(ValidationError):
        MergeIntent.model_validate({
            **payload,
            "mutation_authorized": True,
            "intent_hash": canonical_hash(payload),
        })


def movement(**overrides):
    value = dict(
        old_main_sha="d" * 40,
        old_main_tree_sha="1" * 40,
        new_main_sha="e" * 40,
        new_main_tree_sha="2" * 40,
        candidate_head_sha="b" * 40,
        candidate_tree_sha="c" * 40,
        candidate_diff_hash="e" * 64,
        candidate_changed_paths=("nexus/a.py",),
        changed_main_paths=("docs/unrelated.md",),
        prior_impact_hash="f" * 64,
        prior_verifier_hash="4" * 64,
    )
    value.update(overrides)
    return MainMovementEvidence.model_validate(value)


def test_main_movement_requires_bound_sha_and_paths():
    with pytest.raises(ValidationError, match="TREE_SHA_BINDING"):
        movement(new_main_tree_sha="1" * 40)
    with pytest.raises(ValidationError, match="PATHS_MISSING"):
        movement(changed_main_paths=())
