"""Pure level-triggered Gateway convergence evaluator for issue #1064."""

from __future__ import annotations

from datetime import datetime, timezone

from nexus.contracts.gateway_convergence import (
    ConvergenceAction,
    ConvergenceReason,
    DesiredDeploymentMode,
    EvidenceState,
    GatewayConvergenceRequest,
    GatewayConvergenceResult,
    RecoveryEffectState,
    UpstreamFreshness,
)


def _result(
    request: GatewayConvergenceRequest,
    *,
    action: ConvergenceAction,
    reason: ConvergenceReason,
    operation_id: str | None = None,
    request_id: str | None = None,
    idempotency_fence: str | None = None,
    superseded_target_commit: str | None = None,
    superseded_target_tree: str | None = None,
    next_generation_required: bool = False,
) -> GatewayConvergenceResult:
    observation = request.observation
    return GatewayConvergenceResult(
        action=action,
        reason=reason,
        generation_id=request.policy.generation_id,
        policy_mode=request.policy.mode,
        desired_commit=request.policy.desired_commit,
        desired_tree=request.policy.desired_tree,
        observed_loaded_commit=observation.loaded_commit,
        observed_loaded_tree=observation.loaded_tree,
        operation_id=operation_id,
        request_id=request_id,
        idempotency_fence=idempotency_fence,
        superseded_target_commit=superseded_target_commit,
        superseded_target_tree=superseded_target_tree,
        next_generation_required=next_generation_required,
    )


def evaluate_gateway_convergence(
    request: GatewayConvergenceRequest,
    *,
    now: datetime | None = None,
) -> GatewayConvergenceResult:
    """Classify one desired-vs-observed generation without performing effects.

    The returned action is level-triggered.  It never grants recovery
    authority: every Gateway replacement remains owned by issue #526 and an
    ambiguous/started effect always reconciles the exact existing operation.
    """

    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("NOW_MUST_BE_TIMEZONE_AWARE")

    policy = request.policy
    observed = request.observation
    effect = request.active_effect

    if effect is not None and effect.state in {
        RecoveryEffectState.EFFECT_MAY_HAVE_STARTED,
        RecoveryEffectState.OUTCOME_UNKNOWN,
    }:
        return _result(
            request,
            action=ConvergenceAction.RECONCILE_RECOVERY,
            reason=ConvergenceReason.EFFECT_RECONCILIATION_REQUIRED,
            operation_id=effect.operation_id,
            request_id=effect.request_id,
            idempotency_fence=effect.idempotency_fence,
        )

    if effect is not None and effect.state is RecoveryEffectState.PRE_EFFECT_READY:
        if (effect.target_commit, effect.target_tree) != (
            policy.desired_commit,
            policy.desired_tree,
        ):
            return _result(
                request,
                action=ConvergenceAction.COALESCE_PRE_EFFECT_TARGET,
                reason=ConvergenceReason.PRE_EFFECT_TARGET_SUPERSEDED,
                operation_id=effect.operation_id,
                request_id=effect.request_id,
                idempotency_fence=effect.idempotency_fence,
                superseded_target_commit=effect.target_commit,
                superseded_target_tree=effect.target_tree,
            )

    if effect is not None and effect.state is RecoveryEffectState.TERMINAL_FAILURE:
        return _result(
            request,
            action=ConvergenceAction.BLOCKED,
            reason=ConvergenceReason.EFFECT_TERMINAL_FAILURE,
            operation_id=effect.operation_id,
            request_id=effect.request_id,
            idempotency_fence=effect.idempotency_fence,
        )

    next_generation = False
    if effect is not None and effect.state is RecoveryEffectState.TERMINAL_SUCCESS:
        if (
            observed.loaded_commit != effect.postflight_loaded_commit
            or observed.loaded_tree != effect.postflight_loaded_tree
        ):
            return _result(
                request,
                action=ConvergenceAction.BLOCKED,
                reason=ConvergenceReason.POSTFLIGHT_OBSERVATION_DRIFT,
                operation_id=effect.operation_id,
                request_id=effect.request_id,
                idempotency_fence=effect.idempotency_fence,
            )
        next_generation = (
            effect.target_commit != policy.desired_commit
            or effect.target_tree != policy.desired_tree
        )

    if (
        policy.mode is DesiredDeploymentMode.TRACK_ACCEPTED_MAIN
        and observed.upstream_freshness is UpstreamFreshness.UNKNOWN
    ):
        return _result(
            request,
            action=ConvergenceAction.BLOCKED,
            reason=ConvergenceReason.UPSTREAM_UNKNOWN,
            next_generation_required=next_generation,
        )

    if (
        policy.mode is DesiredDeploymentMode.TRACK_ACCEPTED_MAIN
        and observed.observed_upstream_main_head != policy.desired_commit
    ):
        return _result(
            request,
            action=ConvergenceAction.BLOCKED,
            reason=ConvergenceReason.TRACKED_ACCEPTED_MAIN_MOVED,
            next_generation_required=True,
        )

    if (observed.loaded_commit, observed.loaded_tree) == (
        policy.desired_commit,
        policy.desired_tree,
    ):
        return _result(
            request,
            action=ConvergenceAction.NOOP,
            reason=(
                ConvergenceReason.PINNED_ALREADY_LOADED
                if policy.mode is DesiredDeploymentMode.PINNED
                else ConvergenceReason.ALREADY_CONVERGED
            ),
            next_generation_required=False,
        )

    if request.not_before is not None and moment < request.not_before:
        return _result(
            request,
            action=ConvergenceAction.BLOCKED,
            reason=ConvergenceReason.BACKOFF_ACTIVE,
            next_generation_required=next_generation,
        )

    if observed.readiness_state is not EvidenceState.SAFE:
        return _result(
            request,
            action=ConvergenceAction.BLOCKED,
            reason=(
                ConvergenceReason.READINESS_BLOCKED
                if observed.readiness_state is EvidenceState.BLOCKED
                else ConvergenceReason.READINESS_UNKNOWN
            ),
            next_generation_required=next_generation,
        )

    if observed.quiescence_state is not EvidenceState.SAFE:
        return _result(
            request,
            action=ConvergenceAction.BLOCKED,
            reason=(
                ConvergenceReason.QUIESCENCE_BLOCKED
                if observed.quiescence_state is EvidenceState.BLOCKED
                else ConvergenceReason.QUIESCENCE_UNKNOWN
            ),
            next_generation_required=next_generation,
        )

    if effect is not None and effect.state is RecoveryEffectState.PRE_EFFECT_READY:
        return _result(
            request,
            action=ConvergenceAction.START_PREPARED_RECOVERY,
            reason=ConvergenceReason.PREPARED_EFFECT_MATCHES_DESIRED,
            operation_id=effect.operation_id,
            request_id=effect.request_id,
            idempotency_fence=effect.idempotency_fence,
            next_generation_required=next_generation,
        )

    return _result(
        request,
        action=ConvergenceAction.REQUEST_RECOVERY,
        reason=ConvergenceReason.EXPLICIT_POLICY_REQUIRES_RECOVERY,
        next_generation_required=next_generation,
    )
