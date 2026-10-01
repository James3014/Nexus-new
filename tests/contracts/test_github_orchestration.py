from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from nexus.contracts.github_orchestration import (
    CandidateLineage,
    CheckResult,
    GitHubOrchestrationEvidence,
    ImpactResult,
    IntegrationBinding,
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
            implementer="i",
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


# ==============================================================================
# Hostile Matrix & Integration Subject Identity Separations (Issue #599 Gate A)
# ==============================================================================


def _valid_integration(**overrides):
    source_commit = overrides.get("source_candidate_commit_sha", "b" * 40)
    source_tree = overrides.get("source_candidate_tree_sha", "c" * 40)
    source_diff = overrides.get("source_candidate_diff_hash", "e" * 64)
    int_base = overrides.get("integration_base_sha", "e" * 40)
    int_head = overrides.get("integration_head_sha", "f" * 40)
    int_tree = overrides.get("integration_tree_sha", "9" * 40)
    gen = overrides.get("generation", 1)

    from nexus.contracts.github_orchestration import (
        CandidateBlobEquivalence,
        compute_candidate_equivalence_proof_hash,
    )

    blob_eqs = overrides.get(
        "blob_equivalences",
        (
            CandidateBlobEquivalence(
                path="nexus/a.py",
                source_blob_sha="1" * 40,
                integration_blob_sha="1" * 40,
            ),
        ),
    )

    proof_hash = compute_candidate_equivalence_proof_hash(
        source_candidate_commit_sha=source_commit,
        source_candidate_tree_sha=source_tree,
        source_candidate_diff_hash=source_diff,
        integration_base_sha=int_base,
        integration_head_sha=int_head,
        integration_tree_sha=int_tree,
        generation=gen,
        blob_equivalences=blob_eqs,
    )

    data = dict(
        source_candidate_commit_sha=source_commit,
        source_candidate_tree_sha=source_tree,
        source_contract_hash="2" * 64,
        source_candidate_state_hash="3" * 64,
        source_verified_receipt_hash="4" * 64,
        source_independent_acceptance_hash="5" * 64,
        source_candidate_diff_hash=source_diff,
        integration_base_sha=int_base,
        integration_head_sha=int_head,
        integration_tree_sha=int_tree,
        generation=gen,
        requalification_hash="8" * 64,
        check_subject_kind="INTEGRATION_HEAD",
        check_subject_sha=int_head,
        check_subject_tree_sha=int_tree,
        blob_equivalences=blob_eqs,
        candidate_equivalence_proof_hash=proof_hash,
    )
    data.update(overrides)
    return IntegrationBinding.model_validate(data)


def test_candidate_c_and_distinct_integration_head_i_coexist_validly():
    # Source Candidate C is commit 'b'*40, tree 'c'*40 (base 'd'*40)
    # Drifted integration head I is commit 'f'*40, tree '9'*40 (base 'e'*40)
    integration = _valid_integration(
        integration_base_sha="e" * 40,
        integration_head_sha="f" * 40,
        integration_tree_sha="9" * 40,
        generation=1,
        check_subject_sha="f" * 40,
        check_subject_tree_sha="9" * 40,
    )
    checks = (
        CheckResult(
            name="ci",
            status="completed",
            conclusion="success",
            head_sha="f" * 40,
            generation=1,
        ),
    )
    ev = evidence(
        base_sha="e" * 40,
        head_sha="f" * 40,
        tree_sha="9" * 40,
        current_main_sha="e" * 40,
        integration=integration,
        required_checks=checks,
        checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in checks]}),
    )
    assert ev.candidate.candidate_commit_sha == "b" * 40
    assert ev.candidate.candidate_tree_sha == "c" * 40
    assert ev.head_sha == "f" * 40
    assert ev.tree_sha == "9" * 40
    assert ev.base_sha == "e" * 40
    assert ev.integration.generation == 1
    assert ev.integration.check_subject_sha == "f" * 40
    assert ev.integration.check_subject_kind == "INTEGRATION_HEAD"


def test_substituting_i_for_immutable_source_candidate_c_fails_closed():
    # Attempting to relabel CandidateLineage with integration head I while integration pins C
    integration = _valid_integration(
        source_candidate_commit_sha="b" * 40,
        source_candidate_tree_sha="c" * 40,
        integration_base_sha="e" * 40,
        integration_head_sha="f" * 40,
        integration_tree_sha="9" * 40,
    )
    cand_substituted = CandidateLineage(
        task_id="task-8",
        attempt_id="attempt-1",
        contract_hash="2" * 64,
        card_hash="7" * 64,
        candidate_commit_sha="f" * 40,  # substituted I for C
        candidate_tree_sha="c" * 40,
        candidate_state_hash="3" * 64,
        verified_receipt_hash="4" * 64,
        independent_acceptance_hash="5" * 64,
        reviewer="reviewer",
        implementer="implementer",
    )
    checks = (
        CheckResult(
            name="ci",
            status="completed",
            conclusion="success",
            head_sha="f" * 40,
            generation=1,
        ),
    )
    with pytest.raises(ValidationError, match="SOURCE_CANDIDATE_COMMIT_SHA_MISMATCH"):
        evidence(
            candidate=cand_substituted,
            integration=integration,
            base_sha="e" * 40,
            head_sha="f" * 40,
            tree_sha="9" * 40,
            current_main_sha="e" * 40,
            required_checks=checks,
            checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in checks]}),
        )


def test_source_candidate_lineage_and_diff_mismatches_fail_closed():
    integration = _valid_integration()
    checks = (
        CheckResult(
            name="ci",
            status="completed",
            conclusion="success",
            head_sha=integration.integration_head_sha,
            generation=integration.generation,
        ),
    )
    base_kwargs = dict(
        integration=integration,
        base_sha=integration.integration_base_sha,
        head_sha=integration.integration_head_sha,
        tree_sha=integration.integration_tree_sha,
        current_main_sha=integration.integration_base_sha,
        required_checks=checks,
        checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in checks]}),
    )

    # Source tree mismatch
    cand_wrong_tree = CandidateLineage(
        task_id="task-8",
        attempt_id="attempt-1",
        contract_hash="2" * 64,
        card_hash="7" * 64,
        candidate_commit_sha="b" * 40,
        candidate_tree_sha="1" * 40,  # wrong tree
        candidate_state_hash="3" * 64,
        verified_receipt_hash="4" * 64,
        independent_acceptance_hash="5" * 64,
        reviewer="reviewer",
        implementer="implementer",
    )
    with pytest.raises(ValidationError, match="SOURCE_CANDIDATE_TREE_SHA_MISMATCH"):
        evidence(**{**base_kwargs, "candidate": cand_wrong_tree})

    # Source diff hash mismatch
    with pytest.raises(ValidationError, match="SOURCE_CANDIDATE_DIFF_HASH_MISMATCH"):
        evidence(**{**base_kwargs, "diff_hash": "9" * 64})

    # Source contract hash mismatch
    cand_wrong_contract = CandidateLineage(
        task_id="task-8",
        attempt_id="attempt-1",
        contract_hash="0" * 64,
        card_hash="7" * 64,
        candidate_commit_sha="b" * 40,
        candidate_tree_sha="c" * 40,
        candidate_state_hash="3" * 64,
        verified_receipt_hash="4" * 64,
        independent_acceptance_hash="5" * 64,
        reviewer="reviewer",
        implementer="implementer",
    )
    with pytest.raises(ValidationError, match="SOURCE_CONTRACT_HASH_MISMATCH"):
        evidence(**{
            **base_kwargs,
            "candidate": cand_wrong_contract,
            "task_attempt_contract_hash": "0" * 64,
        })


def test_blob_equivalence_changed_blob_fails_closed():
    from nexus.contracts.github_orchestration import CandidateBlobEquivalence

    # Mismatched blob SHA between source candidate and integration
    with pytest.raises(ValidationError, match="CANDIDATE_BLOB_SHA_MISMATCH"):
        CandidateBlobEquivalence(
            path="nexus/a.py",
            source_blob_sha="1" * 40,
            integration_blob_sha="2" * 40,
        )


def test_blob_equivalence_paths_must_match_changed_paths_exactly():
    from nexus.contracts.github_orchestration import CandidateBlobEquivalence

    # Missing changed_path witness
    int_missing_path = _valid_integration(blob_equivalences=())
    checks = (
        CheckResult(
            name="ci",
            status="completed",
            conclusion="success",
            head_sha="f" * 40,
            generation=1,
        ),
    )
    with pytest.raises(ValidationError, match="BLOB_EQUIVALENCE_PATHS_MISMATCH_CHANGED_PATHS"):
        evidence(
            integration=int_missing_path,
            base_sha="e" * 40,
            head_sha="f" * 40,
            tree_sha="9" * 40,
            current_main_sha="e" * 40,
            required_checks=checks,
            checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in checks]}),
        )

    # Extra non-candidate path witness
    int_extra_path = _valid_integration(
        blob_equivalences=(
            CandidateBlobEquivalence(
                path="nexus/a.py",
                source_blob_sha="1" * 40,
                integration_blob_sha="1" * 40,
            ),
            CandidateBlobEquivalence(
                path="nexus/b.py",
                source_blob_sha="2" * 40,
                integration_blob_sha="2" * 40,
            ),
        )
    )
    with pytest.raises(ValidationError, match="BLOB_EQUIVALENCE_PATHS_MISMATCH_CHANGED_PATHS"):
        evidence(
            integration=int_extra_path,
            base_sha="e" * 40,
            head_sha="f" * 40,
            tree_sha="9" * 40,
            current_main_sha="e" * 40,
            required_checks=checks,
            checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in checks]}),
        )


def test_blob_equivalence_path_safety_and_duplicate_rejection():
    from nexus.contracts.github_orchestration import CandidateBlobEquivalence

    # Traversal or invalid paths fail
    with pytest.raises(ValidationError, match="PATH_INVALID"):
        CandidateBlobEquivalence(
            path="../secret.py",
            source_blob_sha="1" * 40,
            integration_blob_sha="1" * 40,
        )
    with pytest.raises(ValidationError, match="PATH_INVALID"):
        CandidateBlobEquivalence(
            path="/absolute.py",
            source_blob_sha="1" * 40,
            integration_blob_sha="1" * 40,
        )

    # Duplicate or unsorted blob equivalences in IntegrationBinding fail
    b1 = CandidateBlobEquivalence(
        path="nexus/a.py",
        source_blob_sha="1" * 40,
        integration_blob_sha="1" * 40,
    )
    with pytest.raises(ValidationError, match="BLOB_EQUIVALENCES_NOT_SORTED_OR_DUPLICATE"):
        _valid_integration(blob_equivalences=(b1, b1))


def test_check_subject_kind_invalid_fails_closed():
    with pytest.raises(ValidationError, match="CHECK_SUBJECT_KIND_INVALID"):
        _valid_integration(check_subject_kind="OTHER_SUBJECT")  # type: ignore[arg-type]


def test_wrong_integration_binding_mismatches_fail_closed():
    integration = _valid_integration(
        integration_base_sha="e" * 40,
        integration_head_sha="f" * 40,
        integration_tree_sha="9" * 40,
    )
    checks = (
        CheckResult(
            name="ci",
            status="completed",
            conclusion="success",
            head_sha="f" * 40,
            generation=1,
        ),
    )
    # Mismatched head_sha vs integration_head_sha
    with pytest.raises(ValidationError, match="INTEGRATION_HEAD_SHA_MISMATCH"):
        evidence(
            integration=integration,
            base_sha="e" * 40,
            head_sha="1" * 40,
            tree_sha="9" * 40,
            current_main_sha="e" * 40,
            required_checks=checks,
            checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in checks]}),
        )
    # Mismatched tree_sha vs integration_tree_sha
    with pytest.raises(ValidationError, match="INTEGRATION_TREE_SHA_MISMATCH"):
        evidence(
            integration=integration,
            base_sha="e" * 40,
            head_sha="f" * 40,
            tree_sha="1" * 40,
            current_main_sha="e" * 40,
            required_checks=checks,
            checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in checks]}),
        )
    # Mismatched base_sha vs integration_base_sha
    with pytest.raises(ValidationError, match="INTEGRATION_BASE_SHA_MISMATCH"):
        evidence(
            integration=integration,
            base_sha="d" * 40,
            head_sha="f" * 40,
            tree_sha="9" * 40,
            current_main_sha="d" * 40,
            required_checks=checks,
            checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in checks]}),
        )


def test_integration_binding_check_subject_mismatch_fails_closed():
    with pytest.raises(ValidationError, match="CHECK_SUBJECT_HEAD_SHA_MISMATCH"):
        _valid_integration(
            integration_head_sha="f" * 40,
            check_subject_sha="1" * 40,
        )
    with pytest.raises(ValidationError, match="CHECK_SUBJECT_TREE_SHA_MISMATCH"):
        _valid_integration(
            integration_tree_sha="9" * 40,
            check_subject_tree_sha="1" * 40,
        )


def test_integration_required_checks_missing_or_stale_fail_closed():
    # Integration is generation 2 on head 'f'*40
    integration = _valid_integration(
        integration_base_sha="e" * 40,
        integration_head_sha="f" * 40,
        integration_tree_sha="9" * 40,
        generation=2,
    )
    base_kwargs = dict(
        integration=integration,
        base_sha="e" * 40,
        head_sha="f" * 40,
        tree_sha="9" * 40,
        current_main_sha="e" * 40,
    )

    # Missing head_sha on check
    check_no_head = CheckResult(
        name="ci",
        status="completed",
        conclusion="success",
        head_sha=None,
        generation=2,
    )
    with pytest.raises(ValidationError, match="CHECK_HEAD_SHA_MISMATCH"):
        evidence(
            **base_kwargs,
            required_checks=(check_no_head,),
            checks_hash=canonical_hash({"checks": [check_no_head.model_dump(mode="json")]}),
        )

    # Missing generation on check
    check_no_gen = CheckResult(
        name="ci",
        status="completed",
        conclusion="success",
        head_sha="f" * 40,
        generation=None,
    )
    with pytest.raises(ValidationError, match="CHECK_GENERATION_MISMATCH"):
        evidence(
            **base_kwargs,
            required_checks=(check_no_gen,),
            checks_hash=canonical_hash({"checks": [check_no_gen.model_dump(mode="json")]}),
        )

    # Stale generation 1 check when integration is generation 2
    stale_gen_check = CheckResult(
        name="ci",
        status="completed",
        conclusion="success",
        head_sha="f" * 40,
        generation=1,
    )
    with pytest.raises(ValidationError, match="CHECK_GENERATION_MISMATCH"):
        evidence(
            **base_kwargs,
            required_checks=(stale_gen_check,),
            checks_hash=canonical_hash({"checks": [stale_gen_check.model_dump(mode="json")]}),
        )

    # Stale head_sha check (e.g. from I1 head '1'*40)
    stale_head_check = CheckResult(
        name="ci",
        status="completed",
        conclusion="success",
        head_sha="1" * 40,
        generation=2,
    )
    with pytest.raises(ValidationError, match="CHECK_HEAD_SHA_MISMATCH"):
        evidence(
            **base_kwargs,
            required_checks=(stale_head_check,),
            checks_hash=canonical_hash({"checks": [stale_head_check.model_dump(mode="json")]}),
        )


def test_equivalence_proof_hash_tamper_fails_closed():
    with pytest.raises(ValidationError, match="CANDIDATE_EQUIVALENCE_PROOF_HASH_MISMATCH"):
        _valid_integration(candidate_equivalence_proof_hash="0" * 64)


def test_malformed_integration_shas_and_hashes_fail_closed():
    with pytest.raises(ValidationError, match="INVALID"):
        _valid_integration(integration_head_sha="short")
    with pytest.raises(ValidationError, match="INVALID"):
        _valid_integration(requalification_hash="short")
    with pytest.raises(ValidationError):
        _valid_integration(generation=0)


def test_no_authority_escalation_in_merge_intent_with_integration():
    integration = _valid_integration(
        integration_base_sha="e" * 40,
        integration_head_sha="f" * 40,
        integration_tree_sha="9" * 40,
    )
    checks = (
        CheckResult(
            name="ci",
            status="completed",
            conclusion="success",
            head_sha="f" * 40,
            generation=1,
        ),
    )
    ev = evidence(
        base_sha="e" * 40,
        head_sha="f" * 40,
        tree_sha="9" * 40,
        current_main_sha="e" * 40,
        integration=integration,
        required_checks=checks,
        checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in checks]}),
    )
    payload = {
        "schema": "nexus.github_merge_intent.v2",
        "kind": "MERGE_INTENT",
        "evidence": ev.model_dump(mode="json"),
        "grant_outcome": "GRANT_MATCH",
        "mutation_authorized": False,
        "claim_ceiling": "m4_merge_eligible_and_intent_ready_only",
    }
    # Valid intent with integration evidence
    intent = MergeIntent.model_validate({
        **payload,
        "intent_hash": canonical_hash(payload),
    })
    assert intent.mutation_authorized is False

    # Attempting mutation_authorized=True must fail
    with pytest.raises(ValidationError):
        MergeIntent.model_validate({
            **payload,
            "mutation_authorized": True,
            "intent_hash": canonical_hash(payload),
        })
