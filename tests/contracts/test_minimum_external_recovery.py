from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from nexus.contracts.minimum_external_recovery import (
    IndependentRecoveryEvidence,
    MinimumExternalRecoveryGrant,
    PriorEffectState,
    RecoveryDisposition,
    RecoveryObservation,
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
