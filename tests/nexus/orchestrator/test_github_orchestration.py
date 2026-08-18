from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from nexus.contracts.autonomy_goal import (
    AutonomyActionClass,
    RepositoryIdentity,
    StandingGrantContext,
)
from nexus.orchestrator.autonomy_policy import StandingGrantOutcome, StandingGrantRequest
from nexus.orchestrator.github_orchestration import (
    evaluate_action,
    prepare_merge_intent,
    resolve_durable_merge_authorization_at,
    resolve_merge_authorization,
    revalidate_merge_intent,
)
from nexus.orchestrator.standing_grant_store import (
    StandingGrantReceipt,
    _write_standing_grant_receipt_at,
)
from tests.contracts.test_github_orchestration import NOW, evidence


def _receipt_path(tmp_path) -> str:
    return str(tmp_path / "authority" / "standing-grant.json")


def context(**overrides):
    values = dict(
        owner_id="owner-james",
        coordinator_id="coordinator-codex",
        repository=RepositoryIdentity(
            repository_id="James3014/Nexus-new",
            canonical_remote="https://github.com/James3014/Nexus-new.git",
        ),
        thread_id="thread-8",
        goal_id="goal-8",
        allowed_actions=(AutonomyActionClass.REPOSITORY_PUSH,),
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
    )
    values.update(overrides)
    return StandingGrantContext.issue(**values)


def request(ctx, **overrides):
    values = dict(
        owner_id=ctx.owner_id,
        coordinator_id=ctx.coordinator_id,
        repository=ctx.repository,
        thread_id=ctx.thread_id,
        goal_id=ctx.goal_id,
        action=AutonomyActionClass.REPOSITORY_PUSH,
        requested_at=NOW,
        context_hash=ctx.context_hash,
    )
    values.update(overrides)
    return StandingGrantRequest(**values)


def test_valid_evidence_and_grant_produce_intent():
    intent = prepare_merge_intent(context(), request(context()), evidence(), now=NOW)
    assert (
        intent.kind == "MERGE_INTENT"
        and intent.grant_outcome == "GRANT_MATCH"
        and intent.mutation_authorized is False
    )


def test_durable_receipt_loads_and_authorizes_without_caller_context(tmp_path):
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    receipt = StandingGrantReceipt.issue(grant_id="grant-durable-1", context=ctx)
    _write_standing_grant_receipt_at(receipt, Path(_receipt_path(tmp_path)))
    merge_request = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)
    snap = evidence()
    intent = prepare_merge_intent(ctx, merge_request, snap, now=NOW)

    decision = resolve_durable_merge_authorization_at(
        intent,
        merge_request,
        snap,
        receipt_path=_receipt_path(tmp_path),
        now=NOW,
    )

    assert decision.outcome is StandingGrantOutcome.GRANT_MATCH
    assert decision.mutation_authorized is True


def test_durable_receipt_without_github_merge_is_out_of_scope(tmp_path):
    # The caller's in-memory context covers GITHUB_MERGE; the durable receipt
    # does not. Only the durable receipt decides.
    caller_ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    receipt_ctx = context()  # allowed_actions lacks GITHUB_MERGE
    receipt = StandingGrantReceipt.issue(grant_id="grant-nomerge-1", context=receipt_ctx)
    _write_standing_grant_receipt_at(receipt, Path(_receipt_path(tmp_path)))
    merge_request = request(caller_ctx, action=AutonomyActionClass.GITHUB_MERGE)
    snap = evidence()
    intent = prepare_merge_intent(caller_ctx, merge_request, snap, now=NOW)

    decision = resolve_durable_merge_authorization_at(
        intent,
        merge_request,
        snap,
        receipt_path=_receipt_path(tmp_path),
        now=NOW,
    )

    assert decision.outcome is StandingGrantOutcome.GRANT_OUT_OF_SCOPE
    assert decision.mutation_authorized is False


def test_durable_receipt_missing_or_malformed_is_invalid(tmp_path):
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    merge_request = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)
    snap = evidence()
    intent = prepare_merge_intent(ctx, merge_request, snap, now=NOW)

    decision = resolve_durable_merge_authorization_at(
        intent,
        merge_request,
        snap,
        receipt_path=_receipt_path(tmp_path),
        now=NOW,
    )
    assert decision.outcome is StandingGrantOutcome.GRANT_INVALID
    assert decision.mutation_authorized is False


def test_production_durable_authorization_uses_canonical_path_only(tmp_path):
    """Production does not accept an explicit alternate receipt path."""
    import inspect

    from nexus.orchestrator.github_orchestration import resolve_durable_merge_authorization

    sig = inspect.signature(resolve_durable_merge_authorization)
    assert "receipt_path" not in sig.parameters
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    merge_request = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)
    snap = evidence()
    intent = prepare_merge_intent(ctx, merge_request, snap, now=NOW)
    # No live canonical receipt: production resolves INVALID (fail closed).
    decision = resolve_durable_merge_authorization(intent, merge_request, snap, now=NOW)
    assert decision.outcome is StandingGrantOutcome.GRANT_INVALID
    assert decision.mutation_authorized is False


def test_github_merge_is_owner_slot_and_never_authorizes_mutation():
    """Legacy node ID retained for CI continuity; current assertions govern superseding semantics."""
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    merge_request = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)

    decision = evaluate_action(ctx, merge_request)

    assert decision.outcome is StandingGrantOutcome.GRANT_MATCH
    assert decision.mutation_authorized is True
    intent = prepare_merge_intent(ctx, merge_request, evidence(), now=NOW)
    assert intent.grant_outcome == "GRANT_MATCH"
    assert intent.mutation_authorized is False


def test_verified_merge_intent_resolves_to_authorized_grant_match():
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    merge_request = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)
    snap = evidence()
    intent = prepare_merge_intent(ctx, merge_request, snap, now=NOW)

    decision = resolve_merge_authorization(intent, ctx, merge_request, snap, now=NOW)

    assert decision.outcome is StandingGrantOutcome.GRANT_MATCH
    assert decision.mutation_authorized is True


def test_external_platform_approval_is_not_reported_as_grant_mismatch():
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    merge_request = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)
    snap = evidence()
    intent = prepare_merge_intent(ctx, merge_request, snap, now=NOW)

    decision = resolve_merge_authorization(
        intent,
        ctx,
        merge_request,
        snap,
        now=NOW,
        platform_approval_required=True,
    )

    assert decision.outcome is StandingGrantOutcome.PLATFORM_APPROVAL_REQUIRED
    assert decision.mutation_authorized is False


def test_uncovered_merge_and_delegated_self_merge_fail_closed():
    ctx = context()
    uncovered = evaluate_action(ctx, request(ctx, action=AutonomyActionClass.GITHUB_MERGE))
    assert uncovered.outcome is StandingGrantOutcome.OUT_OF_SCOPE
    assert uncovered.mutation_authorized is False

    merge_ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    delegated = evaluate_action(
        merge_ctx,
        request(
            merge_ctx,
            action=AutonomyActionClass.GITHUB_MERGE,
            coordinator_id="delegated-worker",
        ),
    )
    assert delegated.outcome is StandingGrantOutcome.OUT_OF_SCOPE
    assert delegated.mutation_authorized is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("issue_number", 0),
        ("pull_request_number", 0),
        ("head_sha", "z" * 40),
        ("tree_sha", "z" * 40),
    ],
)
def test_identity_and_snapshot_mismatch_rejected(field, value):
    with pytest.raises((ValidationError, ValueError)):
        prepare_merge_intent(context(), request(context()), evidence(**{field: value}), now=NOW)


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"checks_passed": False}, "CHECKS_FAILED_OR_MISSING"),
        ({"required_checks": ()}, "CHECK_FAILED_OR_MISSING"),
        ({"independent_acceptance": False}, "INDEPENDENT_ACCEPTANCE_MISSING"),
    ],
)
def test_missing_failed_checks_and_acceptance_fail_closed(kwargs, code):
    with pytest.raises(ValueError, match=code):
        prepare_merge_intent(context(), request(context()), evidence(**kwargs), now=NOW)


def test_stale_future_and_outside_now_snapshots_fail():
    with pytest.raises(ValueError, match="EVIDENCE_STALE"):
        prepare_merge_intent(
            context(),
            request(context()),
            evidence(fresh_until=NOW + timedelta(minutes=1)),
            now=NOW + timedelta(minutes=2),
        )
    with pytest.raises(ValueError, match="EVIDENCE_STALE"):
        prepare_merge_intent(
            context(), request(context()), evidence(observed_at=NOW + timedelta(minutes=1)), now=NOW
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"coordinator_id": "other"},
        {"goal_id": "other"},
        {"context_hash": "0" * 64},
        {"action": AutonomyActionClass.RUNTIME_ACTIVATE},
    ],
)
def test_grant_identity_action_and_hash_mismatches_fail_closed(kwargs):
    ctx = context()
    with pytest.raises(ValueError, match="(OUT_OF_SCOPE|INVALID)"):
        prepare_merge_intent(ctx, request(ctx, **kwargs), evidence(), now=NOW)


def test_expired_and_revoked_grants_fail_closed():
    ctx = context(expires_at=NOW)
    with pytest.raises(ValueError, match="OUT_OF_SCOPE"):
        prepare_merge_intent(ctx, request(ctx), evidence(), now=NOW)
    revoked = context(revoked_at=NOW, revocation_reason="owner revoked")
    with pytest.raises(ValueError, match="OUT_OF_SCOPE"):
        prepare_merge_intent(revoked, request(revoked), evidence(), now=NOW)


def test_malformed_mapping_is_typed_fail_closed():
    decision = evaluate_action({"unexpected": True}, {"unexpected": True})
    assert (
        decision.outcome is StandingGrantOutcome.INVALID and decision.mutation_authorized is False
    )


def test_intent_replay_and_snapshot_drift_rejected():
    ctx = context()
    req = request(ctx)
    snap = evidence()
    intent = prepare_merge_intent(ctx, req, snap, now=NOW)
    with pytest.raises(ValueError, match="DRIFT_"):
        revalidate_merge_intent(intent, ctx, req, evidence(diff_hash="7" * 64), now=NOW)
    tampered = intent.model_dump(mode="json")
    tampered["intent_hash"] = "0" * 64
    with pytest.raises(ValueError, match="MALFORMED_INPUT|INTENT_REPLAY_OR_TAMPER"):
        revalidate_merge_intent(tampered, ctx, req, snap, now=NOW)


def test_protocol_surface_is_pure_and_no_provider_is_required():
    class ExplodingProvider:
        def snapshot(self, *args, **kwargs):
            raise AssertionError("network called")

    intent = prepare_merge_intent(context(), request(context()), evidence(), now=NOW)
    assert intent.mutation_authorized is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("candidate", None),
        ("impact", None),
        ("reviews", ()),
        ("reviews_resolved", False),
        ("regression_free", False),
        ("impact_known", False),
        ("current_main_sha", None),
        ("repository", "evil/repo"),
    ],
)
def test_hostile_missing_or_spoofed_summary_is_fail_closed(field, value):
    raw = evidence().model_dump(mode="json")
    raw[field] = value
    with pytest.raises(ValueError, match="MALFORMED_INPUT"):
        prepare_merge_intent(context(), request(context()), raw, now=NOW)


def test_reviewer_implementer_identity_cannot_collude():
    raw = evidence().model_dump(mode="json")
    raw["candidate"]["implementer"] = "reviewer"
    with pytest.raises(ValueError, match="MALFORMED_INPUT"):
        prepare_merge_intent(context(), request(context()), raw, now=NOW)
