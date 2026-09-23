from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nexus.contracts.gateway_convergence import (
    ConvergenceAction,
    ConvergenceReason,
    DesiredDeploymentPolicy,
    EvidenceState,
    GatewayConvergenceObservation,
    GatewayConvergenceRequest,
    RecoveryEffectObservation,
    RecoveryEffectState,
    UpstreamFreshness,
)
from nexus.orchestrator.gateway_convergence import evaluate_gateway_convergence


NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


def _policy(
    *,
    mode: str = "TRACK_ACCEPTED_MAIN",
    commit: str = "c" * 40,
    tree: str = "d" * 40,
) -> DesiredDeploymentPolicy:
    return DesiredDeploymentPolicy(
        mode=mode,
        desired_commit=commit,
        desired_tree=tree,
    )


def _observation(
    *,
    loaded_commit: str = "a" * 40,
    loaded_tree: str = "b" * 40,
    upstream: str = "c" * 40,
    freshness: str = "STALE",
    readiness: str = "SAFE",
    quiescence: str = "SAFE",
) -> GatewayConvergenceObservation:
    return GatewayConvergenceObservation(
        loaded_commit=loaded_commit,
        loaded_tree=loaded_tree,
        upstream_freshness=UpstreamFreshness(freshness),
        observed_upstream_main_head=None if freshness == "UNKNOWN" else upstream,
        readiness_state=EvidenceState(readiness),
        quiescence_state=EvidenceState(quiescence),
        server_instance_id="server-1",
    )


def _effect(
    state: str,
    *,
    target_commit: str = "c" * 40,
    target_tree: str = "d" * 40,
) -> RecoveryEffectObservation:
    values = {
        "state": RecoveryEffectState(state),
        "operation_id": "op-1",
        "request_id": "request-1",
        "idempotency_fence": "fence-1",
        "target_commit": target_commit,
        "target_tree": target_tree,
    }
    if state == "TERMINAL_SUCCESS":
        values.update({
            "postflight_verified": True,
            "postflight_loaded_commit": target_commit,
            "postflight_loaded_tree": target_tree,
            "postflight_receipt_hash": "e" * 64,
        })
    return RecoveryEffectObservation(**values)


def test_stale_pinned_older_deployment_is_intentional_noop():
    request = GatewayConvergenceRequest(
        policy=_policy(mode="PINNED", commit="a" * 40, tree="b" * 40),
        observation=_observation(),
    )
    result = evaluate_gateway_convergence(request, now=NOW)
    assert result.action is ConvergenceAction.NOOP
    assert result.reason is ConvergenceReason.PINNED_ALREADY_LOADED
    assert result.effect_authorized is False


def test_follow_current_policy_requests_one_existing_recovery_path():
    request = GatewayConvergenceRequest(
        policy=_policy(),
        observation=_observation(),
    )
    result = evaluate_gateway_convergence(request, now=NOW)
    assert result.action is ConvergenceAction.REQUEST_RECOVERY
    assert result.reason is ConvergenceReason.EXPLICIT_POLICY_REQUIRES_RECOVERY
    assert result.effect_owner == "ISSUE_526_GATEWAY_RECOVERY"
    assert result.effect_authorized is False
    assert result.retry_authorized is False


def test_unknown_upstream_fails_closed_without_effect():
    request = GatewayConvergenceRequest(
        policy=_policy(),
        observation=_observation(freshness="UNKNOWN"),
    )
    result = evaluate_gateway_convergence(request, now=NOW)
    assert result.action is ConvergenceAction.BLOCKED
    assert result.reason is ConvergenceReason.UPSTREAM_UNKNOWN
    assert result.effect_authorized is False


def test_pre_effect_target_is_coalesced_to_latest_generation():
    request = GatewayConvergenceRequest(
        policy=_policy(commit="c" * 40, tree="d" * 40),
        observation=_observation(),
        active_effect=_effect(
            "PRE_EFFECT_READY",
            target_commit="1" * 40,
            target_tree="2" * 40,
        ),
    )
    result = evaluate_gateway_convergence(request, now=NOW)
    assert result.action is ConvergenceAction.COALESCE_PRE_EFFECT_TARGET
    assert result.reason is ConvergenceReason.PRE_EFFECT_TARGET_SUPERSEDED
    assert result.superseded_target_commit == "1" * 40
    assert result.operation_id == "op-1"


def test_started_effect_is_reconciled_before_newer_generation():
    request = GatewayConvergenceRequest(
        policy=_policy(commit="c" * 40, tree="d" * 40),
        observation=_observation(),
        active_effect=_effect(
            "EFFECT_MAY_HAVE_STARTED",
            target_commit="1" * 40,
            target_tree="2" * 40,
        ),
    )
    result = evaluate_gateway_convergence(request, now=NOW)
    assert result.action is ConvergenceAction.RECONCILE_RECOVERY
    assert result.reason is ConvergenceReason.EFFECT_RECONCILIATION_REQUIRED
    assert result.operation_id == "op-1"
    assert result.request_id == "request-1"
    assert result.idempotency_fence == "fence-1"
    assert result.retry_authorized is False


def test_outcome_unknown_never_becomes_retry_permission():
    request = GatewayConvergenceRequest(
        policy=_policy(),
        observation=_observation(),
        active_effect=_effect("OUTCOME_UNKNOWN"),
    )
    result = evaluate_gateway_convergence(request, now=NOW)
    assert result.action is ConvergenceAction.RECONCILE_RECOVERY
    assert result.retry_authorized is False


def test_repeated_identical_generation_is_idempotent_noop():
    request = GatewayConvergenceRequest(
        policy=_policy(commit="c" * 40, tree="d" * 40),
        observation=_observation(
            loaded_commit="c" * 40,
            loaded_tree="d" * 40,
            freshness="CURRENT",
        ),
    )
    first = evaluate_gateway_convergence(request, now=NOW)
    second = evaluate_gateway_convergence(request, now=NOW)
    assert first == second
    assert first.action is ConvergenceAction.NOOP


def test_unsafe_quiescence_blocks_recovery():
    request = GatewayConvergenceRequest(
        policy=_policy(),
        observation=_observation(quiescence="BLOCKED"),
    )
    result = evaluate_gateway_convergence(request, now=NOW)
    assert result.action is ConvergenceAction.BLOCKED
    assert result.reason is ConvergenceReason.QUIESCENCE_BLOCKED


def test_backoff_prevents_restart_storm():
    request = GatewayConvergenceRequest(
        policy=_policy(),
        observation=_observation(),
        not_before=NOW + timedelta(minutes=5),
    )
    result = evaluate_gateway_convergence(request, now=NOW)
    assert result.action is ConvergenceAction.BLOCKED
    assert result.reason is ConvergenceReason.BACKOFF_ACTIVE


def test_terminal_success_re_reads_latest_generation_without_rewriting_history():
    request = GatewayConvergenceRequest(
        policy=_policy(commit="c" * 40, tree="d" * 40),
        observation=_observation(
            loaded_commit="1" * 40,
            loaded_tree="2" * 40,
            upstream="c" * 40,
        ),
        active_effect=_effect(
            "TERMINAL_SUCCESS",
            target_commit="1" * 40,
            target_tree="2" * 40,
        ),
    )
    result = evaluate_gateway_convergence(request, now=NOW)
    assert result.action is ConvergenceAction.REQUEST_RECOVERY
    assert result.next_generation_required is True
    assert result.effect_authorized is False


def test_track_accepted_main_requires_current_observed_identity():
    request = GatewayConvergenceRequest(
        policy=_policy(commit="c" * 40, tree="d" * 40),
        observation=_observation(upstream="9" * 40),
    )
    result = evaluate_gateway_convergence(request, now=NOW)
    assert result.action is ConvergenceAction.BLOCKED
    assert result.reason is ConvergenceReason.TRACKED_ACCEPTED_MAIN_MOVED
    assert result.next_generation_required is True


def test_prepared_matching_effect_can_start_only_after_safe_gates():
    request = GatewayConvergenceRequest(
        policy=_policy(),
        observation=_observation(),
        active_effect=_effect("PRE_EFFECT_READY"),
    )
    result = evaluate_gateway_convergence(request, now=NOW)
    assert result.action is ConvergenceAction.START_PREPARED_RECOVERY
    assert result.reason is ConvergenceReason.PREPARED_EFFECT_MATCHES_DESIRED
    assert result.effect_authorized is False
