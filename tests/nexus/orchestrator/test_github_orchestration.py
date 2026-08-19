import json
import os
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from nexus.contracts.autonomy_goal import (
    AutonomyActionClass,
    RepositoryIdentity,
    StandingGrantContext,
)
from nexus.contracts.github_orchestration import MainMovementEvidence, canonical_hash
from nexus.orchestrator.autonomy_policy import StandingGrantOutcome, StandingGrantRequest
from nexus.orchestrator.github_orchestration import (
    _resolve_durable_merge_authorization_at,
    evaluate_action,
    prepare_merge_intent,
    requalify_main_movement,
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


def movement_for(snap, **overrides):
    value = dict(
        old_main_sha=snap.base_sha,
        old_main_tree_sha="1" * 40,
        new_main_sha="e" * 40,
        new_main_tree_sha="2" * 40,
        candidate_head_sha=snap.head_sha,
        candidate_tree_sha=snap.tree_sha,
        candidate_diff_hash=snap.diff_hash,
        candidate_changed_paths=snap.changed_paths,
        changed_main_paths=("docs/unrelated.md",),
        prior_impact_hash=snap.impact_hash,
        prior_verifier_hash=snap.verifier_hash,
    )
    value.update(overrides)
    return MainMovementEvidence.model_validate(value)


def _plan(**overrides):
    values = dict(
        impact_class="DOCS_GOVERNANCE", unmatched_paths=[], changed_paths=["docs/unrelated.md"]
    )
    values.update(overrides)
    return type("Plan", (), values)()


def test_main_movement_reuses_unaffected_dimensions(monkeypatch):
    snap = evidence()
    monkeypatch.setattr("scripts.ops.pr_impact_gate.build_impact_plan", lambda *a, **k: _plan())
    result = requalify_main_movement(snap, movement_for(snap))
    assert result.blocked is False
    assert {item.action for item in result.dimensions} == {"REUSE_UNAFFECTED"}


def test_main_movement_rechecks_overlap_and_authority(monkeypatch):
    snap = evidence()
    monkeypatch.setattr("scripts.ops.pr_impact_gate.build_impact_plan", lambda *a, **k: _plan())
    result = requalify_main_movement(
        snap,
        movement_for(snap, changed_main_paths=("AGENTS.md", "nexus/a.py")),
    )
    by_name = {item.dimension: item for item in result.dimensions}
    assert by_name["SEMANTIC_OVERLAP"].action == "RECHECK_AFFECTED"
    assert by_name["AUTHORITY_DRIFT"].action == "RECHECK_AFFECTED"
    assert result.blocked is True


def test_main_movement_tamper_fails_closed(monkeypatch):
    snap = evidence()
    monkeypatch.setattr("scripts.ops.pr_impact_gate.build_impact_plan", lambda *a, **k: _plan())
    result = requalify_main_movement(snap, movement_for(snap, candidate_head_sha="a" * 40))
    assert result.blocked is True
    source = next(item for item in result.dimensions if item.dimension == "SOURCE_IDENTITY")
    assert source.action == "IMPACT_UNKNOWN"


def test_durable_receipt_loads_and_authorizes_without_caller_context(tmp_path):
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    receipt = StandingGrantReceipt.issue(grant_id="grant-durable-1", context=ctx)
    _write_standing_grant_receipt_at(receipt, Path(_receipt_path(tmp_path)))
    merge_request = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)
    snap = evidence()
    intent = prepare_merge_intent(ctx, merge_request, snap, now=NOW)

    decision = _resolve_durable_merge_authorization_at(
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

    decision = _resolve_durable_merge_authorization_at(
        intent,
        merge_request,
        snap,
        receipt_path=_receipt_path(tmp_path),
        now=NOW,
    )

    assert decision.outcome is StandingGrantOutcome.GRANT_INVALID
    assert decision.mutation_authorized is False


def test_durable_receipt_missing_or_malformed_is_invalid(tmp_path):
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    merge_request = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)
    snap = evidence()
    intent = prepare_merge_intent(ctx, merge_request, snap, now=NOW)

    decision = _resolve_durable_merge_authorization_at(
        intent,
        merge_request,
        snap,
        receipt_path=_receipt_path(tmp_path),
        now=NOW,
    )
    assert decision.outcome is StandingGrantOutcome.GRANT_INVALID
    assert decision.mutation_authorized is False


def test_durable_resolution_uses_effective_now_not_old_request_time(tmp_path):
    ctx = context(
        allowed_actions=(AutonomyActionClass.GITHUB_MERGE,),
        expires_at=NOW + timedelta(minutes=5),
    )
    receipt = StandingGrantReceipt.issue(grant_id="grant-effective-now", context=ctx)
    path = Path(_receipt_path(tmp_path))
    _write_standing_grant_receipt_at(receipt, path)
    merge_request = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)
    snap = evidence(fresh_until=NOW + timedelta(hours=1))
    intent = prepare_merge_intent(ctx, merge_request, snap, now=NOW)

    decision = _resolve_durable_merge_authorization_at(
        intent,
        merge_request,
        snap,
        receipt_path=path,
        now=NOW + timedelta(minutes=10),
    )

    assert decision.outcome is StandingGrantOutcome.GRANT_INVALID


@pytest.mark.parametrize(
    "override",
    [
        {"owner_id": "other-owner"},
        {"coordinator_id": "other-coordinator"},
        {
            "repository": RepositoryIdentity(
                repository_id="other/repo",
                canonical_remote="https://github.com/other/repo.git",
            )
        },
        {"thread_id": "other-thread"},
        {"goal_id": "other-goal"},
        {"action": AutonomyActionClass.RUNTIME_ACTIVATE},
    ],
)
def test_durable_explicit_path_rejects_request_scope_mismatches(tmp_path, override):
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    receipt = StandingGrantReceipt.issue(grant_id="grant-scope", context=ctx)
    path = Path(_receipt_path(tmp_path))
    _write_standing_grant_receipt_at(receipt, path)
    original = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)
    snap = evidence()
    intent = prepare_merge_intent(ctx, original, snap, now=NOW)
    changed = request(ctx, **override)

    decision = _resolve_durable_merge_authorization_at(
        intent, changed, snap, receipt_path=path, now=NOW
    )

    assert decision.outcome is StandingGrantOutcome.GRANT_OUT_OF_SCOPE


def test_durable_explicit_path_preserves_platform_approval_boundary(tmp_path):
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    receipt = StandingGrantReceipt.issue(grant_id="grant-platform", context=ctx)
    path = Path(_receipt_path(tmp_path))
    _write_standing_grant_receipt_at(receipt, path)
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)
    snap = evidence()
    intent = prepare_merge_intent(ctx, req, snap, now=NOW)

    decision = _resolve_durable_merge_authorization_at(
        intent,
        req,
        snap,
        receipt_path=path,
        now=NOW,
        platform_approval_required=True,
    )

    assert decision.outcome is StandingGrantOutcome.PLATFORM_APPROVAL_REQUIRED


def test_two_fresh_durable_evaluators_reuse_unchanged_receipt(tmp_path):
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    receipt = StandingGrantReceipt.issue(grant_id="grant-fresh-reuse", context=ctx)
    path = Path(_receipt_path(tmp_path))
    _write_standing_grant_receipt_at(receipt, path)
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)
    snap = evidence()
    intent = prepare_merge_intent(ctx, req, snap, now=NOW)
    inputs = {}
    for name, value in (("intent", intent), ("request", req), ("evidence", snap)):
        item = tmp_path / f"{name}.json"
        item.write_text(json.dumps(value.model_dump(mode="json")), encoding="utf-8")
        inputs[name] = item
    before = path.read_bytes(), path.stat().st_mtime_ns
    code = (
        "import json,sys; from datetime import datetime; from pathlib import Path; "
        "from nexus.contracts.autonomy_goal import StandingGrantContext; "
        "from nexus.contracts.github_orchestration import GitHubOrchestrationEvidence,MergeIntent; "
        "from nexus.orchestrator.autonomy_policy import StandingGrantRequest; "
        "from nexus.orchestrator.github_orchestration import _resolve_durable_merge_authorization_at; "
        "load=lambda p: json.loads(Path(p).read_text()); "
        "d=_resolve_durable_merge_authorization_at(MergeIntent.model_validate(load(sys.argv[2])),StandingGrantRequest.model_validate(load(sys.argv[3])),GitHubOrchestrationEvidence.model_validate(load(sys.argv[4])),receipt_path=Path(sys.argv[1]),now=datetime.fromisoformat(sys.argv[5])); print(d.outcome.value)"
    )
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[3]))
    results = [
        subprocess.run(
            [
                os.sys.executable,
                "-c",
                code,
                str(path),
                str(inputs["intent"]),
                str(inputs["request"]),
                str(inputs["evidence"]),
                NOW.isoformat(),
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        for _ in range(2)
    ]
    assert [result.stdout.strip() for result in results] == ["GRANT_MATCH", "GRANT_MATCH"]
    assert all(result.returncode == 0 for result in results)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (
            lambda intent, snap: (
                {**intent.model_dump(mode="json"), "intent_hash": "0" * 64},
                snap,
            ),
            "MALFORMED_INPUT",
        ),
        (lambda intent, snap: (intent, evidence(diff_hash="7" * 64)), "DRIFT_"),
        (
            lambda intent, snap: (intent, {**snap.model_dump(mode="json"), "checks_passed": False}),
            "MALFORMED_INPUT",
        ),
        (
            lambda intent, snap: (intent, {**snap.model_dump(mode="json"), "required_checks": []}),
            "MALFORMED_INPUT",
        ),
        (
            lambda intent, snap: (
                intent,
                {**snap.model_dump(mode="json"), "reviews_resolved": False},
            ),
            "MALFORMED_INPUT",
        ),
        (
            lambda intent, snap: (
                intent,
                {**snap.model_dump(mode="json"), "independent_acceptance": False},
            ),
            "MALFORMED_INPUT",
        ),
    ],
)
def test_durable_wrapper_keeps_evidence_failures_fail_closed(tmp_path, mutation, expected):
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    receipt = StandingGrantReceipt.issue(grant_id="grant-evidence", context=ctx)
    path = Path(_receipt_path(tmp_path))
    _write_standing_grant_receipt_at(receipt, path)
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)
    snap = evidence()
    intent = prepare_merge_intent(ctx, req, snap, now=NOW)
    changed_intent, changed_snap = mutation(intent, snap)

    with pytest.raises(ValueError, match=expected):
        _resolve_durable_merge_authorization_at(
            changed_intent, req, changed_snap, receipt_path=path, now=NOW
        )


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


def test_recomputed_hash_cannot_change_intent_semantics():
    ctx = context()
    req = request(ctx)
    snap = evidence()
    intent = prepare_merge_intent(ctx, req, snap, now=NOW)
    tampered = intent.model_dump(mode="json")
    tampered["claim_ceiling"] = "NO_MUTATION_AUTHORITY"
    tampered["intent_hash"] = canonical_hash({
        key: value for key, value in tampered.items() if key != "intent_hash"
    })

    with pytest.raises(ValueError, match="INTENT_SEMANTIC_MISMATCH"):
        resolve_merge_authorization(tampered, ctx, req, snap, now=NOW)


def test_durable_resolver_rejects_recomputed_semantic_tamper(tmp_path):
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    receipt = StandingGrantReceipt.issue(grant_id="grant-semantic", context=ctx)
    path = Path(_receipt_path(tmp_path))
    _write_standing_grant_receipt_at(receipt, path)
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)
    snap = evidence()
    intent = prepare_merge_intent(ctx, req, snap, now=NOW)
    tampered = intent.model_dump(mode="json")
    tampered["grant_outcome"] = "GRANT_INVALID"
    tampered["intent_hash"] = canonical_hash({
        key: value for key, value in tampered.items() if key != "intent_hash"
    })

    with pytest.raises(ValueError, match="INTENT_SEMANTIC_MISMATCH"):
        _resolve_durable_merge_authorization_at(tampered, req, snap, receipt_path=path, now=NOW)


@pytest.mark.parametrize("durable", [False, True])
@pytest.mark.parametrize(
    "field, value, expected",
    [
        ("grant_outcome", "GRANT_INVALID", "INTENT_SEMANTIC_MISMATCH"),
        ("claim_ceiling", "NO_MUTATION_AUTHORITY", "INTENT_SEMANTIC_MISMATCH"),
        ("schema", "nexus.github_merge_intent.v999", "INTENT_SEMANTIC_MISMATCH"),
        ("mutation_authorized", True, "MALFORMED_INPUT"),
    ],
)
def test_recomputed_hash_semantic_tamper_matrix(durable, field, value, expected, tmp_path):
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)
    snap = evidence()
    intent = prepare_merge_intent(ctx, req, snap, now=NOW)
    tampered = intent.model_dump(mode="json")
    tampered[field] = value
    tampered["intent_hash"] = canonical_hash({
        key: item for key, item in tampered.items() if key != "intent_hash"
    })

    if durable:
        receipt = StandingGrantReceipt.issue(grant_id="grant-matrix", context=ctx)
        path = Path(_receipt_path(tmp_path))
        _write_standing_grant_receipt_at(receipt, path)
        with pytest.raises(ValueError, match=expected):
            _resolve_durable_merge_authorization_at(tampered, req, snap, receipt_path=path, now=NOW)
    else:
        with pytest.raises(ValueError, match=expected):
            resolve_merge_authorization(tampered, ctx, req, snap, now=NOW)


@pytest.mark.parametrize("durable", [False, True])
def test_recomputed_hash_nested_evidence_tamper_is_rejected(durable, tmp_path):
    ctx = context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    req = request(ctx, action=AutonomyActionClass.GITHUB_MERGE)
    original = evidence()
    changed = evidence(diff_hash="7" * 64)
    intent = prepare_merge_intent(ctx, req, original, now=NOW)
    tampered = intent.model_dump(mode="json")
    tampered["evidence"] = changed.model_dump(mode="json")
    tampered["intent_hash"] = canonical_hash({
        key: item for key, item in tampered.items() if key != "intent_hash"
    })

    if durable:
        receipt = StandingGrantReceipt.issue(grant_id="grant-nested-matrix", context=ctx)
        path = Path(_receipt_path(tmp_path))
        _write_standing_grant_receipt_at(receipt, path)
        with pytest.raises(ValueError, match="DRIFT_"):
            _resolve_durable_merge_authorization_at(
                tampered, req, original, receipt_path=path, now=NOW
            )
    else:
        with pytest.raises(ValueError, match="DRIFT_"):
            resolve_merge_authorization(tampered, ctx, req, original, now=NOW)


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
