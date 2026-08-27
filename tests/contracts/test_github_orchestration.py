from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from nexus.contracts.github_orchestration import (
    CandidateBlobEquivalenceEntry,
    CandidateLineage,
    CheckResult,
    GitHubOrchestrationEvidence,
    ImpactResult,
    IntegrationBinding,
    MainMovementEvidence,
    MergeIntent,
    ReviewResult,
    canonical_hash,
    compute_blob_equivalence_hash,
    compute_candidate_acceptance_binding_hash,
    compute_source_candidate_binding_hash,
)

NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


def evidence(**overrides):
    checks = (CheckResult(name="ci", status="completed", conclusion="success"),)
    reviews = (ReviewResult(reviewer="reviewer", state="APPROVED"),)
    impact = ImpactResult(classification="NO_CHANGE", known=True, regression_free=True)
    diff_hash_val = overrides.get("diff_hash", "e" * 64)
    base_candidate = CandidateLineage(
        task_id="task-8",
        attempt_id="attempt-1",
        contract_hash="2" * 64,
        card_hash="7" * 64,
        candidate_commit_sha="b" * 40,
        candidate_tree_sha="c" * 40,
        candidate_state_hash="3" * 64,
        candidate_diff_hash=overrides.get("candidate_diff_hash", diff_hash_val),
        verified_receipt_hash="4" * 64,
        independent_acceptance_hash="5" * 64,
        reviewer="reviewer",
        implementer="implementer",
    )
    if "integration" in overrides and overrides["integration"] is not None and "candidate" not in overrides:
        candidate = CandidateLineage(
            task_id=base_candidate.task_id,
            attempt_id=base_candidate.attempt_id,
            contract_hash=base_candidate.contract_hash,
            card_hash=base_candidate.card_hash,
            candidate_commit_sha=base_candidate.candidate_commit_sha,
            candidate_tree_sha=base_candidate.candidate_tree_sha,
            candidate_state_hash=base_candidate.candidate_state_hash,
            candidate_diff_hash=base_candidate.candidate_diff_hash,
            verified_receipt_hash=base_candidate.verified_receipt_hash,
            independent_acceptance_hash=compute_candidate_acceptance_binding_hash(base_candidate),
            reviewer=base_candidate.reviewer,
            implementer=base_candidate.implementer,
        )
    else:
        candidate = overrides.get("candidate", base_candidate)

    if "integration" in overrides and overrides["integration"] is not None and "required_checks" not in overrides:
        ib = overrides["integration"]
        checks = (
            CheckResult(
                name="ci",
                status="completed",
                conclusion="success",
                subject_kind=ib.check_subject_kind,
                subject_sha=ib.integration_head_sha,
                generation=ib.generation,
            ),
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
        independent_acceptance_hash=overrides.get("independent_acceptance_hash", candidate.independent_acceptance_hash),
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


def integration_binding(candidate=None, changed_paths=("nexus/a.py",), **overrides):
    if candidate is None:
        base_c = CandidateLineage(
            task_id="task-8",
            attempt_id="attempt-1",
            contract_hash="2" * 64,
            card_hash="7" * 64,
            candidate_commit_sha="b" * 40,
            candidate_tree_sha="c" * 40,
            candidate_state_hash="3" * 64,
            candidate_diff_hash="e" * 64,
            verified_receipt_hash="4" * 64,
            independent_acceptance_hash="0" * 64,
            reviewer="reviewer",
            implementer="implementer",
        )
        candidate = CandidateLineage(
            task_id=base_c.task_id,
            attempt_id=base_c.attempt_id,
            contract_hash=base_c.contract_hash,
            card_hash=base_c.card_hash,
            candidate_commit_sha=base_c.candidate_commit_sha,
            candidate_tree_sha=base_c.candidate_tree_sha,
            candidate_state_hash=base_c.candidate_state_hash,
            candidate_diff_hash=base_c.candidate_diff_hash,
            verified_receipt_hash=base_c.verified_receipt_hash,
            independent_acceptance_hash=compute_candidate_acceptance_binding_hash(base_c),
            reviewer=base_c.reviewer,
            implementer=base_c.implementer,
        )
    proof = overrides.get(
        "blob_proof",
        tuple(
            CandidateBlobEquivalenceEntry(
                path=p,
                source_blob_sha="7" * 40,
                integration_blob_sha="7" * 40,
            )
            for p in sorted(set(changed_paths))
        ) if changed_paths else (),
    )
    blob_hash = overrides.get(
        "blob_equivalence_hash",
        compute_blob_equivalence_hash(proof) if proof else "0" * 64,
    )
    source_commit = overrides.get("source_candidate_commit_sha", candidate.candidate_commit_sha)
    source_tree = overrides.get("source_candidate_tree_sha", candidate.candidate_tree_sha)
    source_diff = overrides.get("source_candidate_diff_hash", candidate.candidate_diff_hash or ("e" * 64))
    binding_hash = overrides.get("source_candidate_binding_hash", compute_source_candidate_binding_hash(candidate))

    value = dict(
        base_sha="d" * 40,
        integration_head_sha="1" * 40,
        integration_tree_sha="2" * 40,
        source_candidate_commit_sha=source_commit,
        source_candidate_tree_sha=source_tree,
        source_candidate_diff_hash=source_diff,
        source_candidate_binding_hash=binding_hash,
        generation=1,
        check_subject_generation=1,
        requalification_hash="9" * 64,
        check_subject_kind="INTEGRATION_HEAD",
        check_subject_sha="1" * 40,
        candidate_blobs_equivalent=True,
        blob_proof=proof,
        blob_equivalence_hash=blob_hash,
        acceptance_reused=True,
    )
    value.update(overrides)
    return IntegrationBinding.model_validate(value)


def test_a1_source_candidate_and_distinct_integration_head_coexist():
    ib = integration_binding()
    ev = evidence(
        head_sha="1" * 40,
        tree_sha="2" * 40,
        integration=ib,
    )
    assert ev.candidate.candidate_commit_sha == "b" * 40
    assert ev.candidate.candidate_tree_sha == "c" * 40
    assert ev.head_sha == "1" * 40
    assert ev.tree_sha == "2" * 40
    assert ev.integration is not None
    assert ev.integration.integration_head_sha == "1" * 40
    assert ev.integration.integration_tree_sha == "2" * 40
    assert ev.integration.source_candidate_commit_sha == "b" * 40
    assert ev.integration.source_candidate_tree_sha == "c" * 40
    assert ev.integration.base_sha == "d" * 40
    assert ev.independent_acceptance_hash == ev.candidate.independent_acceptance_hash
    assert ev.candidate.independent_acceptance_hash == compute_candidate_acceptance_binding_hash(ev.candidate)


def test_a2_substituting_integration_head_or_altering_source_candidate_fails_closed():
    cand_substituted_i = CandidateLineage(
        task_id="task-8",
        attempt_id="attempt-1",
        contract_hash="2" * 64,
        card_hash="7" * 64,
        candidate_commit_sha="1" * 40,
        candidate_tree_sha="c" * 40,
        candidate_state_hash="3" * 64,
        candidate_diff_hash="e" * 64,
        verified_receipt_hash="4" * 64,
        independent_acceptance_hash="5" * 64,
        reviewer="reviewer",
        implementer="implementer",
    )
    with pytest.raises(ValidationError, match="SOURCE_CANDIDATE_COMMIT_SHA_MISMATCH|INTEGRATION_CANNOT_REPLACE_SOURCE_CANDIDATE"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            candidate=cand_substituted_i,
            integration=integration_binding(),
        )

    cand_substituted_c_prime = CandidateLineage(
        task_id="task-8",
        attempt_id="attempt-1",
        contract_hash="2" * 64,
        card_hash="7" * 64,
        candidate_commit_sha="a" * 40,
        candidate_tree_sha="9" * 40,
        candidate_state_hash="3" * 64,
        candidate_diff_hash="e" * 64,
        verified_receipt_hash="4" * 64,
        independent_acceptance_hash="5" * 64,
        reviewer="reviewer",
        implementer="implementer",
    )
    with pytest.raises(ValidationError, match="SOURCE_CANDIDATE_COMMIT_SHA_MISMATCH"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            candidate=cand_substituted_c_prime,
            integration=integration_binding(source_candidate_commit_sha="b" * 40, source_candidate_tree_sha="c" * 40),
        )

    with pytest.raises(ValidationError, match="INTEGRATION_CHECK_SUBJECT_KIND_INVALID"):
        integration_binding(check_subject_kind="ARBITRARY_NON_CANDIDATE_KIND")
    with pytest.raises(ValidationError, match="INTEGRATION_CHECK_SUBJECT_KIND_INVALID"):
        integration_binding(check_subject_kind="SOURCE_CANDIDATE")
    with pytest.raises(ValidationError, match="INTEGRATION_CHECK_SUBJECT_KIND_INVALID"):
        integration_binding(check_subject_kind="CANDIDATE")

    with pytest.raises(ValidationError, match="CANDIDATE_LINEAGE_MISMATCH"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
        )


def test_a3_wrong_source_candidate_tree_diff_acceptance_binding_fails_closed():
    with pytest.raises(ValidationError, match="ACCEPTANCE_HASH_LINEAGE_MISMATCH"):
        evidence(independent_acceptance_hash="6" * 64)

    with pytest.raises(ValidationError, match="TASK_ATTEMPT_LINEAGE_MISMATCH"):
        evidence(task_attempt_contract_hash="6" * 64)

    with pytest.raises(ValidationError, match="CANDIDATE_HASH_LINEAGE_MISMATCH"):
        evidence(candidate_hash="6" * 64)

    with pytest.raises(ValidationError, match="VERIFIER_HASH_LINEAGE_MISMATCH"):
        evidence(verifier_hash="6" * 64)

    with pytest.raises(ValidationError, match="CANDIDATE_LINEAGE_MISMATCH"):
        evidence(tree_sha="9" * 40)

    cand_with_diff = CandidateLineage(
        task_id="task-8",
        attempt_id="attempt-1",
        contract_hash="2" * 64,
        card_hash="7" * 64,
        candidate_commit_sha="b" * 40,
        candidate_tree_sha="c" * 40,
        candidate_state_hash="3" * 64,
        candidate_diff_hash="f" * 64,
        verified_receipt_hash="4" * 64,
        independent_acceptance_hash="5" * 64,
        reviewer="reviewer",
        implementer="implementer",
    )
    with pytest.raises(ValidationError, match="CANDIDATE_DIFF_HASH_MISMATCH"):
        evidence(candidate=cand_with_diff, diff_hash="e" * 64)


def test_a4_wrong_integration_base_head_tree_generation_check_subject_binding_fails_closed():
    with pytest.raises(ValidationError, match="INTEGRATION_BASE_SHA_MISMATCH"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            integration=integration_binding(base_sha="f" * 40),
        )

    with pytest.raises(ValidationError, match="INTEGRATION_HEAD_SHA_MISMATCH"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            integration=integration_binding(
                integration_head_sha="3" * 40,
                check_subject_sha="3" * 40,
            ),
        )

    with pytest.raises(ValidationError, match="INTEGRATION_TREE_SHA_MISMATCH"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            integration=integration_binding(integration_tree_sha="3" * 40),
        )

    with pytest.raises(ValidationError, match="INTEGRATION_CHECK_SUBJECT_SHA_MISMATCH"):
        integration_binding(
            integration_head_sha="1" * 40,
            check_subject_sha="3" * 40,
        )

    with pytest.raises(ValidationError):
        integration_binding(generation=0)
    with pytest.raises(ValidationError):
        integration_binding(generation=-1)

    base_dict = integration_binding().model_dump(mode="json")
    del base_dict["check_subject_generation"]
    with pytest.raises(ValidationError):
        IntegrationBinding.model_validate(base_dict)

    with pytest.raises(ValidationError, match="INTEGRATION_CHECK_SUBJECT_KIND_INVALID"):
        integration_binding(check_subject_kind="   ")


def test_a5_stale_or_mismatched_integration_generation_cannot_consume_checks():
    with pytest.raises(ValidationError, match="INTEGRATION_CHECK_GENERATION_MISMATCH"):
        integration_binding(generation=2, check_subject_generation=1)

    with pytest.raises(ValidationError, match="INTEGRATION_CHECK_GENERATION_MISMATCH"):
        integration_binding(generation=1, check_subject_generation=2)

    checks_gen1 = (
        CheckResult(
            name="ci",
            status="completed",
            conclusion="success",
            subject_kind="INTEGRATION_HEAD",
            subject_sha="1" * 40,
            generation=1,
        ),
    )
    with pytest.raises(ValidationError, match="CHECK_GENERATION_MISMATCH"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            required_checks=checks_gen1,
            checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in checks_gen1]}),
            integration=integration_binding(generation=2, check_subject_generation=2),
        )

    checks_bad_sha = (
        CheckResult(
            name="ci",
            status="completed",
            conclusion="success",
            subject_kind="INTEGRATION_HEAD",
            subject_sha="9" * 40,
            generation=1,
        ),
    )
    with pytest.raises(ValidationError, match="CHECK_SUBJECT_SHA_MISMATCH"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            required_checks=checks_bad_sha,
            checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in checks_bad_sha]}),
            integration=integration_binding(generation=1, check_subject_generation=1),
        )

    checks_gen2 = (
        CheckResult(
            name="ci",
            status="completed",
            conclusion="success",
            subject_kind="INTEGRATION_HEAD",
            subject_sha="1" * 40,
            generation=2,
        ),
    )
    ev = evidence(
        head_sha="1" * 40,
        tree_sha="2" * 40,
        required_checks=checks_gen2,
        checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in checks_gen2]}),
        integration=integration_binding(generation=2, check_subject_generation=2),
    )
    assert ev.integration.generation == 2


def test_a6_candidate_owned_blob_changed_rejects_acceptance_reuse():
    with pytest.raises(ValidationError, match="CANDIDATE_BLOBS_CHANGED_ACCEPTANCE_REUSE_REJECTED"):
        CandidateBlobEquivalenceEntry(
            path="nexus/a.py",
            source_blob_sha="7" * 40,
            integration_blob_sha="8" * 40,
        )

    with pytest.raises(ValidationError, match="BLOB_PROOF_EMPTY_FOR_ACCEPTANCE_REUSE"):
        integration_binding(blob_proof=(), acceptance_reused=True)

    with pytest.raises(ValidationError, match="CANDIDATE_BLOBS_CHANGED_ACCEPTANCE_REUSE_REJECTED"):
        integration_binding(candidate_blobs_equivalent=False, acceptance_reused=True)


def test_a7_candidate_owned_blobs_preserved_allows_reuse_without_bypassing_ci_freshness():
    proof = (
        CandidateBlobEquivalenceEntry(
            path="nexus/a.py",
            source_blob_sha="7" * 40,
            integration_blob_sha="7" * 40,
        ),
    )
    ib = integration_binding(
        candidate_blobs_equivalent=True,
        blob_proof=proof,
        blob_equivalence_hash=compute_blob_equivalence_hash(proof),
    )
    ev = evidence(
        head_sha="1" * 40,
        tree_sha="2" * 40,
        integration=ib,
    )
    assert ev.independent_acceptance is True

    with pytest.raises(ValidationError, match="CHECKS_FAILED_OR_MISSING"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            integration=ib,
            checks_passed=False,
        )

    with pytest.raises(ValidationError, match="FRESHNESS_INVALID"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            integration=ib,
            fresh_until=NOW,
        )


def test_a8_malformed_tampered_sha_hash_equivalence_proof_fails_closed():
    with pytest.raises(ValidationError, match="BASE_SHA_INVALID"):
        integration_binding(base_sha="Z" * 40)
    with pytest.raises(ValidationError, match="BASE_SHA_INVALID"):
        integration_binding(base_sha="d" * 39)

    with pytest.raises(ValidationError, match="INTEGRATION_HEAD_SHA_INVALID"):
        integration_binding(integration_head_sha="not-a-sha")

    with pytest.raises(ValidationError, match="INTEGRATION_TREE_SHA_INVALID"):
        integration_binding(integration_tree_sha="1" * 41)

    with pytest.raises(ValidationError, match="REQUALIFICATION_HASH_INVALID"):
        integration_binding(requalification_hash="9" * 63)

    with pytest.raises(ValidationError, match="BLOB_EQUIVALENCE_HASH_MISMATCH"):
        integration_binding(blob_equivalence_hash="0" * 64)

    unsorted_proof = (
        CandidateBlobEquivalenceEntry(path="z.py", source_blob_sha="1" * 40, integration_blob_sha="1" * 40),
        CandidateBlobEquivalenceEntry(path="a.py", source_blob_sha="2" * 40, integration_blob_sha="2" * 40),
    )
    with pytest.raises(ValidationError, match="BLOB_PROOF_PATHS_NOT_SORTED_UNIQUE"):
        integration_binding(
            blob_proof=unsorted_proof,
            blob_equivalence_hash=compute_blob_equivalence_hash(unsorted_proof),
        )

    with pytest.raises(ValidationError, match="PATH_INVALID"):
        CandidateBlobEquivalenceEntry(path="../secret.py", source_blob_sha="1" * 40, integration_blob_sha="1" * 40)
    with pytest.raises(ValidationError, match="PATH_INVALID"):
        CandidateBlobEquivalenceEntry(path="/etc/passwd", source_blob_sha="1" * 40, integration_blob_sha="1" * 40)


def test_a9_no_new_authority_field_becomes_authoritative():
    base_dict = integration_binding().model_dump(mode="json")
    for forbidden_field in [
        "mutation_authorized",
        "merge_authorized",
        "bypass_gate",
        "standing_grant_id",
        "route_override",
        "workforce_admitted",
    ]:
        with pytest.raises(ValidationError):
            IntegrationBinding.model_validate({**base_dict, forbidden_field: True})

    ev = evidence(head_sha="1" * 40, tree_sha="2" * 40, integration=integration_binding())
    payload = {
        "schema": "nexus.github_merge_intent.v2",
        "kind": "MERGE_INTENT",
        "evidence": ev.model_dump(mode="json"),
        "grant_outcome": "GRANT_MATCH",
        "mutation_authorized": False,
        "claim_ceiling": "m4_merge_eligible_and_intent_ready_only",
    }
    intent = MergeIntent.model_validate({**payload, "intent_hash": canonical_hash(payload)})
    assert intent.mutation_authorized is False
    assert intent.claim_ceiling == "m4_merge_eligible_and_intent_ready_only"

    with pytest.raises(ValidationError, match="INTENT_HASH_INVALID_OR_MUTATION_FORBIDDEN"):
        MergeIntent.model_validate({
            **payload,
            "mutation_authorized": True,
            "intent_hash": canonical_hash(payload),
        })


def test_a10_existing_m4_and_441_regressions_remain_green():
    base_ev = evidence()
    assert base_ev.integration is None
    assert base_ev.head_sha == base_ev.candidate.candidate_commit_sha
    assert base_ev.tree_sha == base_ev.candidate.candidate_tree_sha

    mm = movement()
    assert mm.old_main_sha == "d" * 40
    assert mm.candidate_head_sha == "b" * 40


def test_w13_1_unbound_or_missing_required_check_fields_fail_closed():
    check_none_kind = (
        CheckResult(
            name="ci",
            status="completed",
            conclusion="success",
            subject_kind=None,
            subject_sha="1" * 40,
            generation=1,
        ),
    )
    with pytest.raises(ValidationError, match="CHECK_SUBJECT_KIND_MISMATCH"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            required_checks=check_none_kind,
            checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in check_none_kind]}),
            integration=integration_binding(),
        )

    check_none_sha = (
        CheckResult(
            name="ci",
            status="completed",
            conclusion="success",
            subject_kind="INTEGRATION_HEAD",
            subject_sha=None,
            generation=1,
        ),
    )
    with pytest.raises(ValidationError, match="CHECK_SUBJECT_SHA_MISMATCH"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            required_checks=check_none_sha,
            checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in check_none_sha]}),
            integration=integration_binding(),
        )

    check_none_gen = (
        CheckResult(
            name="ci",
            status="completed",
            conclusion="success",
            subject_kind="INTEGRATION_HEAD",
            subject_sha="1" * 40,
            generation=None,
        ),
    )
    with pytest.raises(ValidationError, match="CHECK_GENERATION_MISMATCH"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            required_checks=check_none_gen,
            checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in check_none_gen]}),
            integration=integration_binding(),
        )

    check_valid = (
        CheckResult(
            name="ci",
            status="completed",
            conclusion="success",
            subject_kind="INTEGRATION_HEAD",
            subject_sha="1" * 40,
            generation=1,
        ),
    )
    ev = evidence(
        head_sha="1" * 40,
        tree_sha="2" * 40,
        required_checks=check_valid,
        checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in check_valid]}),
        integration=integration_binding(),
    )
    assert ev.checks_passed is True

    legacy_check = (CheckResult(name="ci", status="completed", conclusion="success"),)
    ev_legacy = evidence(
        required_checks=legacy_check,
        checks_hash=canonical_hash({"checks": [c.model_dump(mode="json") for c in legacy_check]}),
    )
    assert ev_legacy.checks_passed is True


def test_w13_2_consistent_source_substitution_with_old_acceptance_fails_closed():
    cand_c_prime = CandidateLineage(
        task_id="task-8",
        attempt_id="attempt-1",
        contract_hash="2" * 64,
        card_hash="7" * 64,
        candidate_commit_sha="a" * 40,
        candidate_tree_sha="9" * 40,
        candidate_state_hash="3" * 64,
        candidate_diff_hash="e" * 64,
        verified_receipt_hash="4" * 64,
        independent_acceptance_hash="5" * 64,
        reviewer="reviewer",
        implementer="implementer",
    )
    original_c = CandidateLineage(
        task_id="task-8",
        attempt_id="attempt-1",
        contract_hash="2" * 64,
        card_hash="7" * 64,
        candidate_commit_sha="b" * 40,
        candidate_tree_sha="c" * 40,
        candidate_state_hash="3" * 64,
        candidate_diff_hash="e" * 64,
        verified_receipt_hash="4" * 64,
        independent_acceptance_hash="5" * 64,
        reviewer="reviewer",
        implementer="implementer",
    )
    old_binding_hash = compute_source_candidate_binding_hash(original_c)

    ib_tampered = integration_binding(
        source_candidate_commit_sha="a" * 40,
        source_candidate_tree_sha="9" * 40,
        source_candidate_diff_hash="e" * 64,
        source_candidate_binding_hash=old_binding_hash,
    )
    with pytest.raises(ValidationError, match="SOURCE_CANDIDATE_BINDING_HASH_MISMATCH|SOURCE_CANDIDATE_ACCEPTANCE_HASH_MISMATCH"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            candidate=cand_c_prime,
            integration=ib_tampered,
        )


def test_w13_3_source_diff_substitution_or_omission_fails_closed():
    cand_no_diff = CandidateLineage(
        task_id="task-8",
        attempt_id="attempt-1",
        contract_hash="2" * 64,
        card_hash="7" * 64,
        candidate_commit_sha="b" * 40,
        candidate_tree_sha="c" * 40,
        candidate_state_hash="3" * 64,
        candidate_diff_hash=None,
        verified_receipt_hash="4" * 64,
        independent_acceptance_hash="5" * 64,
        reviewer="reviewer",
        implementer="implementer",
    )
    with pytest.raises(ValidationError, match="SOURCE_CANDIDATE_DIFF_HASH_MISMATCH|SOURCE_CANDIDATE_BINDING_HASH_MISMATCH"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            candidate=cand_no_diff,
            integration=integration_binding(),
        )

    ib_diff_mismatch = integration_binding(
        source_candidate_diff_hash="9" * 64,
    )
    with pytest.raises(ValidationError, match="SOURCE_CANDIDATE_DIFF_HASH_MISMATCH"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            integration=ib_diff_mismatch,
        )


def test_w13_4_partial_or_mismatched_blob_proof_fails_closed():
    changed_2_paths = ("nexus/a.py", "nexus/b.py")
    proof_1_path = (
        CandidateBlobEquivalenceEntry(
            path="nexus/a.py",
            source_blob_sha="7" * 40,
            integration_blob_sha="7" * 40,
        ),
    )
    ib_partial = integration_binding(
        blob_proof=proof_1_path,
        blob_equivalence_hash=compute_blob_equivalence_hash(proof_1_path),
    )
    with pytest.raises(ValidationError, match="BLOB_PROOF_PATHS_MISMATCH_CHANGED_PATHS"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            allowed_paths=("nexus/a.py", "nexus/b.py"),
            changed_paths=changed_2_paths,
            integration=ib_partial,
        )

    proof_2_paths = (
        CandidateBlobEquivalenceEntry(path="nexus/a.py", source_blob_sha="7" * 40, integration_blob_sha="7" * 40),
        CandidateBlobEquivalenceEntry(path="nexus/b.py", source_blob_sha="8" * 40, integration_blob_sha="8" * 40),
    )
    ib_extra = integration_binding(
        blob_proof=proof_2_paths,
        blob_equivalence_hash=compute_blob_equivalence_hash(proof_2_paths),
    )
    with pytest.raises(ValidationError, match="BLOB_PROOF_PATHS_MISMATCH_CHANGED_PATHS"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            allowed_paths=("nexus/a.py", "nexus/b.py"),
            changed_paths=("nexus/a.py",),
            integration=ib_extra,
        )

    proof_mismatch = (
        CandidateBlobEquivalenceEntry(path="nexus/other.py", source_blob_sha="7" * 40, integration_blob_sha="7" * 40),
    )
    ib_mismatched = integration_binding(
        blob_proof=proof_mismatch,
        blob_equivalence_hash=compute_blob_equivalence_hash(proof_mismatch),
    )
    with pytest.raises(ValidationError, match="BLOB_PROOF_PATHS_MISMATCH_CHANGED_PATHS"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            allowed_paths=("nexus/a.py", "nexus/other.py"),
            changed_paths=("nexus/a.py",),
            integration=ib_mismatched,
        )

    ib_exact = integration_binding(
        changed_paths=changed_2_paths,
    )
    ev_exact = evidence(
        head_sha="1" * 40,
        tree_sha="2" * 40,
        allowed_paths=("nexus/a.py", "nexus/b.py"),
        changed_paths=changed_2_paths,
        integration=ib_exact,
    )
    assert ev_exact.changed_paths == changed_2_paths


def test_w13_r2_recomputed_binding_with_old_acceptance_fails_closed():
    # 1. Original C has deterministic acceptance hash A(C)
    base_c = CandidateLineage(
        task_id="task-8",
        attempt_id="attempt-1",
        contract_hash="2" * 64,
        card_hash="7" * 64,
        candidate_commit_sha="b" * 40,
        candidate_tree_sha="c" * 40,
        candidate_state_hash="3" * 64,
        candidate_diff_hash="e" * 64,
        verified_receipt_hash="4" * 64,
        independent_acceptance_hash="0" * 64,
        reviewer="reviewer",
        implementer="implementer",
    )
    old_acceptance_hash = compute_candidate_acceptance_binding_hash(base_c)
    original_c = CandidateLineage(
        task_id=base_c.task_id,
        attempt_id=base_c.attempt_id,
        contract_hash=base_c.contract_hash,
        card_hash=base_c.card_hash,
        candidate_commit_sha=base_c.candidate_commit_sha,
        candidate_tree_sha=base_c.candidate_tree_sha,
        candidate_state_hash=base_c.candidate_state_hash,
        candidate_diff_hash=base_c.candidate_diff_hash,
        verified_receipt_hash=base_c.verified_receipt_hash,
        independent_acceptance_hash=old_acceptance_hash,
        reviewer=base_c.reviewer,
        implementer=base_c.implementer,
    )

    # 2. Substitute C' with changed commit/tree
    cand_c_prime_with_old_acc = CandidateLineage(
        task_id="task-8",
        attempt_id="attempt-1",
        contract_hash="2" * 64,
        card_hash="7" * 64,
        candidate_commit_sha="a" * 40,
        candidate_tree_sha="9" * 40,
        candidate_state_hash="3" * 64,
        candidate_diff_hash="e" * 64,
        verified_receipt_hash="4" * 64,
        independent_acceptance_hash=old_acceptance_hash,  # RETAIN OLD A(C)
        reviewer="reviewer",
        implementer="implementer",
    )

    # 3. Caller recomputes source_candidate_binding_hash for C'
    recomputed_binding_hash = compute_source_candidate_binding_hash(cand_c_prime_with_old_acc)
    ib_tampered = integration_binding(
        candidate=cand_c_prime_with_old_acc,
        source_candidate_commit_sha="a" * 40,
        source_candidate_tree_sha="9" * 40,
        source_candidate_diff_hash="e" * 64,
        source_candidate_binding_hash=recomputed_binding_hash,
    )

    # 4. Evidence must fail closed with SOURCE_CANDIDATE_ACCEPTANCE_HASH_MISMATCH
    with pytest.raises(ValidationError, match="SOURCE_CANDIDATE_ACCEPTANCE_HASH_MISMATCH"):
        evidence(
            head_sha="1" * 40,
            tree_sha="2" * 40,
            candidate=cand_c_prime_with_old_acc,
            independent_acceptance_hash=old_acceptance_hash,
            integration=ib_tampered,
        )

    # Nearby control: C' with freshly recomputed A(C') is structurally valid as a NEW acceptance identity
    new_acceptance_hash = compute_candidate_acceptance_binding_hash(cand_c_prime_with_old_acc)
    cand_c_prime_valid = CandidateLineage(
        task_id="task-8",
        attempt_id="attempt-1",
        contract_hash="2" * 64,
        card_hash="7" * 64,
        candidate_commit_sha="a" * 40,
        candidate_tree_sha="9" * 40,
        candidate_state_hash="3" * 64,
        candidate_diff_hash="e" * 64,
        verified_receipt_hash="4" * 64,
        independent_acceptance_hash=new_acceptance_hash,
        reviewer="reviewer",
        implementer="implementer",
    )
    ib_new_valid = integration_binding(
        candidate=cand_c_prime_valid,
        source_candidate_commit_sha="a" * 40,
        source_candidate_tree_sha="9" * 40,
        source_candidate_diff_hash="e" * 64,
        source_candidate_binding_hash=compute_source_candidate_binding_hash(cand_c_prime_valid),
    )
    ev_new = evidence(
        head_sha="1" * 40,
        tree_sha="2" * 40,
        candidate=cand_c_prime_valid,
        independent_acceptance_hash=new_acceptance_hash,
        integration=ib_new_valid,
    )
    assert ev_new.candidate.candidate_commit_sha == "a" * 40
    assert ev_new.candidate.independent_acceptance_hash == new_acceptance_hash
    assert ev_new.independent_acceptance_hash == new_acceptance_hash
