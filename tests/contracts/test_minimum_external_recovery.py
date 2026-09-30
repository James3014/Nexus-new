from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from nexus.contracts.minimum_external_recovery import (
    GovernanceIntegrationPhysicalEvidence,
    GovernanceIntegrationSubject,
    IndependentRecoveryEvidence,
    MinimumExternalRecoveryGrant,
    PriorEffectState,
    RecoveryContractError,
    RecoveryDisposition,
    RecoveryObservation,
    evaluate_governance_integration_recovery,
    evaluate_minimum_external_recovery,
)

NOW = datetime(2026, 9, 30, 13, 45, tzinfo=timezone.utc)
REPOSITORY = "James3014/Nexus-new"
IDENTITY = "a" * 64


@pytest.fixture
def exact_grant() -> MinimumExternalRecoveryGrant:
    return MinimumExternalRecoveryGrant(
        schema="nexus.minimum_external_recovery_grant.v1",
        grant_id="1218-g0-01",
        owner_login="James3014",
        repository=REPOSITORY,
        subject_kind="issue",
        subject_id="1218",
        effect_kind="SOURCE_HARDENING",
        effect_id="minimum-external-recovery-g0",
        effect_identity_sha256=IDENTITY,
        issued_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(minutes=30),
    )


@pytest.fixture
def independent_evidence() -> IndependentRecoveryEvidence:
    return IndependentRecoveryEvidence(
        schema="nexus.minimum_external_recovery_evidence.v1",
        repository=REPOSITORY,
        subject_kind="issue",
        subject_id="1218",
        effect_kind="SOURCE_HARDENING",
        effect_id="minimum-external-recovery-g0",
        effect_identity_sha256=IDENTITY,
        normal_governance_available=False,
        independent=True,
        evidence_sha256="b" * 64,
    )


@pytest.fixture
def observation() -> RecoveryObservation:
    return RecoveryObservation(
        repository=REPOSITORY,
        subject_kind="issue",
        subject_id="1218",
        effect_kind="SOURCE_HARDENING",
        effect_id="minimum-external-recovery-g0",
        effect_identity_sha256=IDENTITY,
        prior_effect_state=PriorEffectState.NONE,
    )


def test_negative_control_fails_closed_without_exact_usable_grant(
    exact_grant: MinimumExternalRecoveryGrant,
    independent_evidence: IndependentRecoveryEvidence,
    observation: RecoveryObservation,
) -> None:
    cases = [
        (None, observation, RecoveryDisposition.DENY, "FRESH_EXTERNAL_OWNER_GRANT_REQUIRED"),
        (
            replace(exact_grant, repository="James3014/devspace"),
            observation,
            RecoveryDisposition.DENY,
            "RECOVERY_SUBJECT_MISMATCH",
        ),
        (
            replace(exact_grant, expires_at=NOW),
            observation,
            RecoveryDisposition.DENY,
            "GRANT_EXPIRED",
        ),
        (
            exact_grant,
            replace(observation, prior_effect_state=PriorEffectState.CONSUMED),
            RecoveryDisposition.DENY,
            "RECOVERY_REPLAY_DENIED",
        ),
        (
            exact_grant,
            replace(observation, prior_effect_state=PriorEffectState.OUTCOME_UNKNOWN),
            RecoveryDisposition.RECONCILE_ONLY,
            "AMBIGUOUS_PRIOR_EFFECT",
        ),
    ]
    for grant, observed, disposition, reason in cases:
        decision = evaluate_minimum_external_recovery(
            grant=grant,
            evidence=independent_evidence,
            observation=observed,
            now=NOW,
        )
        assert decision.disposition is disposition
        assert decision.reason == reason


def test_positive_controlled_recovery_fixture_permits_only_one_exact_bounded_effect(
    exact_grant: MinimumExternalRecoveryGrant,
    independent_evidence: IndependentRecoveryEvidence,
    observation: RecoveryObservation,
) -> None:
    decision = evaluate_minimum_external_recovery(
        grant=exact_grant,
        evidence=independent_evidence,
        observation=observation,
        now=NOW,
    )
    assert decision.disposition is RecoveryDisposition.ALLOW_ONE_BOUNDED_EFFECT
    assert decision.reason == "EXACT_EXTERNAL_RECOVERY_CONTRACT_SATISFIED"

    replay = evaluate_minimum_external_recovery(
        grant=exact_grant,
        evidence=independent_evidence,
        observation=replace(observation, prior_effect_state=PriorEffectState.CONSUMED),
        now=NOW,
    )
    assert replay.disposition is RecoveryDisposition.DENY
    assert replay.reason == "RECOVERY_REPLAY_DENIED"


def test_recovery_path_is_denied_when_normal_governance_is_available(
    exact_grant: MinimumExternalRecoveryGrant,
    independent_evidence: IndependentRecoveryEvidence,
    observation: RecoveryObservation,
) -> None:
    decision = evaluate_minimum_external_recovery(
        grant=exact_grant,
        evidence=replace(independent_evidence, normal_governance_available=True),
        observation=observation,
        now=NOW,
    )
    assert decision.disposition is RecoveryDisposition.DENY
    assert decision.reason == "NORMAL_GOVERNANCE_AVAILABLE_USE_NORMAL_PATH"


A4_NOW = datetime(2026, 9, 30, 14, 35, tzinfo=timezone.utc)
A4_BASE = "651c780ecdaee9c25f77f6c82287e6c5c9f3d791"
A4_HEAD = "ada6dab5f71acf096be919cdf70531008d83b9ce"
A4_TREE = "e34fd98ca7f56a42a43dee24e91d4f0aa4e1bcdd"
A4_DIFF = "e43c3880db6922b9dc660452f7a1478d6b1c83c2f94bd6e9b7a5acab3878c5e7"
A4_ACCEPTANCE = "1d020f02a2eb105a6a0134f2f304144557ca4b1952758a5f644e1807083d29f6"
A4_FAILURE = "7791b4dfba904d74ffa0696a8c8a004f856c8dd6349e1e610480a0958ff9d685"
A4_PHYSICAL = "e7044738ef79f44f0903c1bd6af3ee55aa16fa9653daf5fae60e98a949f62271"
A4_CHECKS = (
    "Exact-base impact gate",
    "Trusted verifier (default branch)",
    "Full published Git history secret audit",
)
A4_PATHS = (
    "nexus/orchestrator/unified_mcp_gateway.py",
    "nexus/orchestrator/standing_grant_store.py",
)


@pytest.fixture
def a4_subject() -> GovernanceIntegrationSubject:
    return GovernanceIntegrationSubject(
        repository=REPOSITORY,
        issue_number=1237,
        pull_request_number=1236,
        expected_base_sha=A4_BASE,
        accepted_head_sha=A4_HEAD,
        accepted_tree_sha=A4_TREE,
        accepted_diff_sha256=A4_DIFF,
        independent_acceptance_sha256=A4_ACCEPTANCE,
        required_check_names=A4_CHECKS,
        repaired_authority_paths=A4_PATHS,
        failed_action="nexus_owner_standing_grant_issue",
        failure_code="EXPIRED",
        failure_evidence_sha256=A4_FAILURE,
    )


@pytest.fixture
def a4_physical() -> GovernanceIntegrationPhysicalEvidence:
    return GovernanceIntegrationPhysicalEvidence(
        schema="nexus.governance_integration_physical_evidence.v1",
        repository=REPOSITORY,
        pull_request_number=1236,
        base_sha=A4_BASE,
        head_sha=A4_HEAD,
        tree_sha=A4_TREE,
        independent_acceptance_sha256=A4_ACCEPTANCE,
        successful_required_checks=A4_CHECKS,
        repaired_authority_paths=A4_PATHS,
        failed_action="nexus_owner_standing_grant_issue",
        failure_code="EXPIRED",
        failure_evidence_sha256=A4_FAILURE,
        evidence_sha256=A4_PHYSICAL,
        independent=True,
    )


def _a4_observation(
    subject: GovernanceIntegrationSubject, state: PriorEffectState = PriorEffectState.NONE
):
    return RecoveryObservation(
        repository=REPOSITORY,
        subject_kind="pull_request",
        subject_id="1236",
        effect_kind="GOVERNANCE_INTEGRATION_MERGE",
        effect_id="pr-1236-merge",
        effect_identity_sha256=subject.effect_identity_sha256,
        prior_effect_state=state,
    )


def _a4_grant(subject: GovernanceIntegrationSubject) -> MinimumExternalRecoveryGrant:
    return MinimumExternalRecoveryGrant(
        schema="nexus.minimum_external_recovery_grant.v1",
        grant_id="issue1237-a4-merge",
        owner_login="James3014",
        repository=REPOSITORY,
        subject_kind="pull_request",
        subject_id="1236",
        effect_kind="GOVERNANCE_INTEGRATION_MERGE",
        effect_id="pr-1236-merge",
        effect_identity_sha256=subject.effect_identity_sha256,
        issued_at=A4_NOW - timedelta(minutes=5),
        expires_at=A4_NOW + timedelta(minutes=30),
    )


def test_issue1237_a4_physical_reproduction_allows_one_exact_integration(
    a4_subject: GovernanceIntegrationSubject,
    a4_physical: GovernanceIntegrationPhysicalEvidence,
) -> None:
    decision = evaluate_governance_integration_recovery(
        subject=a4_subject,
        grant=_a4_grant(a4_subject),
        physical_evidence=a4_physical,
        observation=_a4_observation(a4_subject),
        now=A4_NOW,
    )
    assert decision.disposition is RecoveryDisposition.ALLOW_ONE_BOUNDED_EFFECT
    assert decision.reason == "EXACT_EXTERNAL_RECOVERY_CONTRACT_SATISFIED"


def test_issue1237_recovery_rejects_unrelated_failure_and_wrong_merge_method(
    a4_subject: GovernanceIntegrationSubject,
) -> None:
    with pytest.raises(RecoveryContractError, match="FAILED_ACTION_NOT_STANDING_GRANT_ISSUER"):
        replace(a4_subject, failed_action="provider_timeout").validate()
    with pytest.raises(RecoveryContractError, match="RECOVERY_MERGE_METHOD_INVALID"):
        replace(a4_subject, merge_method="squash").validate()


def test_issue1237_recovery_rejects_missing_checks_or_wrong_repair_seam(
    a4_subject: GovernanceIntegrationSubject,
) -> None:
    with pytest.raises(RecoveryContractError, match="GOVERNANCE_REQUIRED_CHECKS_MISSING"):
        replace(a4_subject, required_check_names=("Exact-base impact gate",)).validate()
    with pytest.raises(RecoveryContractError, match="REPAIR_DOES_NOT_TOUCH_FAILED_AUTHORITY_SEAM"):
        replace(a4_subject, repaired_authority_paths=("docs/readme.md",)).validate()


def test_issue1237_physical_evidence_rejects_head_substitution_or_failed_check(
    a4_subject: GovernanceIntegrationSubject,
    a4_physical: GovernanceIntegrationPhysicalEvidence,
) -> None:
    with pytest.raises(RecoveryContractError, match="GOVERNANCE_PHYSICAL_SUBJECT_MISMATCH"):
        replace(a4_physical, head_sha="0" * 40).assert_subject(a4_subject)
    with pytest.raises(RecoveryContractError, match="GOVERNANCE_REQUIRED_CHECKS_NOT_SUCCESSFUL"):
        replace(a4_physical, successful_required_checks=A4_CHECKS[:-1]).assert_subject(a4_subject)


def test_issue1237_current_main_or_effect_identity_drift_fails_closed(
    a4_subject: GovernanceIntegrationSubject,
    a4_physical: GovernanceIntegrationPhysicalEvidence,
) -> None:
    drifted = replace(a4_subject, expected_base_sha="1" * 40)
    decision = evaluate_governance_integration_recovery(
        subject=a4_subject,
        grant=_a4_grant(a4_subject),
        physical_evidence=a4_physical,
        observation=_a4_observation(drifted),
        now=A4_NOW,
    )
    assert decision.disposition is RecoveryDisposition.DENY
    assert decision.reason == "RECOVERY_SUBJECT_MISMATCH"


def test_issue1237_post_consume_replay_is_denied(
    a4_subject: GovernanceIntegrationSubject,
    a4_physical: GovernanceIntegrationPhysicalEvidence,
) -> None:
    decision = evaluate_governance_integration_recovery(
        subject=a4_subject,
        grant=_a4_grant(a4_subject),
        physical_evidence=a4_physical,
        observation=_a4_observation(a4_subject, PriorEffectState.CONSUMED),
        now=A4_NOW,
    )
    assert decision.disposition is RecoveryDisposition.DENY
    assert decision.reason == "RECOVERY_REPLAY_DENIED"
