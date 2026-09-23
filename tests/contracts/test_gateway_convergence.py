from __future__ import annotations

import pytest
from pydantic import ValidationError

from nexus.contracts.gateway_convergence import (
    DesiredDeploymentMode,
    DesiredDeploymentPolicy,
    GatewayConvergenceObservation,
    RecoveryEffectObservation,
    RecoveryEffectState,
    EvidenceState,
    UpstreamFreshness,
)


def test_policy_generation_is_explicit_and_stable():
    policy = DesiredDeploymentPolicy(
        mode=DesiredDeploymentMode.TRACK_ACCEPTED_MAIN,
        desired_commit="a" * 40,
        desired_tree="b" * 40,
    )
    same = DesiredDeploymentPolicy(
        desired_tree="b" * 40,
        desired_commit="a" * 40,
        mode="TRACK_ACCEPTED_MAIN",
    )
    assert policy.generation_id == same.generation_id
    assert len(policy.generation_id) == 64


def test_policy_rejects_malformed_desired_identity():
    with pytest.raises(ValidationError, match="DESIRED_COMMIT_MALFORMED"):
        DesiredDeploymentPolicy(
            mode="PINNED",
            desired_commit="not-a-sha",
            desired_tree="b" * 40,
        )


def test_known_upstream_freshness_requires_observed_head():
    with pytest.raises(
        ValidationError,
        match="KNOWN_UPSTREAM_FRESHNESS_REQUIRES_OBSERVED_HEAD",
    ):
        GatewayConvergenceObservation(
            loaded_commit="a" * 40,
            loaded_tree="b" * 40,
            upstream_freshness=UpstreamFreshness.STALE,
            readiness_state=EvidenceState.SAFE,
            quiescence_state=EvidenceState.SAFE,
        )


def test_terminal_success_requires_exact_verified_postflight():
    with pytest.raises(
        ValidationError,
        match="TERMINAL_SUCCESS_REQUIRES_VERIFIED_POSTFLIGHT",
    ):
        RecoveryEffectObservation(
            state=RecoveryEffectState.TERMINAL_SUCCESS,
            operation_id="op-1",
            request_id="request-1",
            idempotency_fence="fence-1",
            target_commit="a" * 40,
            target_tree="b" * 40,
        )

    with pytest.raises(
        ValidationError,
        match="TERMINAL_SUCCESS_POSTFLIGHT_TARGET_MISMATCH",
    ):
        RecoveryEffectObservation(
            state=RecoveryEffectState.TERMINAL_SUCCESS,
            operation_id="op-1",
            request_id="request-1",
            idempotency_fence="fence-1",
            target_commit="a" * 40,
            target_tree="b" * 40,
            postflight_verified=True,
            postflight_loaded_commit="c" * 40,
            postflight_loaded_tree="b" * 40,
            postflight_receipt_hash="d" * 64,
        )
