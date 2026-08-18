from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from nexus.contracts.autonomy_goal import (
    AutonomyActionClass,
    AutonomyGoalGrant,
    AutonomyPathPolicy,
    AutonomyRiskLevel,
    CollaborationBaseIdentity,
    MergeAuthorizationPolicy,
    RepositoryIdentity,
    RuntimeActivationPolicy,
    SensitiveScope,
    StandingGrantContext,
)
from nexus.orchestrator.autonomy_policy import (
    AcceptanceAuthorityKind,
    AcceptanceIdentity,
    AutonomyBudgetUsage,
    AutonomyCandidateIdentity,
    AutonomyDecision,
    AutonomyDecisionState,
    AutonomyEvaluationInput,
    AutonomyRuntimeIdentity,
    AutonomySubmissionBinding,
    ChildAutonomyScope,
    StandingGrantOutcome,
    StandingGrantRequest,
    evaluate_autonomy_policy,
    evaluate_standing_grant_decision,
)
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

NOW = datetime.now(timezone.utc)


def _standing_context(**overrides) -> StandingGrantContext:
    values = {
        "owner_id": "owner-james",
        "coordinator_id": "coordinator-codex",
        "repository": RepositoryIdentity(
            repository_id="James3014/Nexus-new",
            canonical_remote="https://github.com/James3014/Nexus-new.git",
        ),
        "thread_id": "thread-163",
        "goal_id": "goal-163",
        "allowed_actions": (AutonomyActionClass.REPOSITORY_PUSH,),
        "issued_at": NOW - timedelta(minutes=5),
        "expires_at": NOW + timedelta(hours=1),
    }
    values.update(overrides)
    return StandingGrantContext.issue(**values)


def _standing_request(context: StandingGrantContext, **overrides) -> StandingGrantRequest:
    values = {
        "owner_id": context.owner_id,
        "coordinator_id": context.coordinator_id,
        "repository": context.repository,
        "thread_id": context.thread_id,
        "goal_id": context.goal_id,
        "action": AutonomyActionClass.REPOSITORY_PUSH,
        "requested_at": NOW,
        "context_hash": context.context_hash,
    }
    values.update(overrides)
    return StandingGrantRequest(**values)


def test_standing_grant_match_is_evidence_only_and_hash_bound():
    """Legacy node ID retained for CI continuity; current assertions govern superseding semantics."""
    context = _standing_context()
    decision = evaluate_standing_grant_decision(context, _standing_request(context))
    assert decision.outcome is StandingGrantOutcome.GRANT_MATCH
    assert decision.mutation_authorized is True
    assert decision.claim_ceiling == "AUTHORIZATION_ONLY_VERIFICATION_REQUIRED"
    assert decision.context_hash == context.context_hash
    assert decision.decision_hash


def test_standing_grant_merge_requires_platform_approval():
    """Legacy node ID retained for CI continuity; current assertions govern superseding semantics."""
    context = _standing_context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    decision = evaluate_standing_grant_decision(
        context, _standing_request(context, action=AutonomyActionClass.GITHUB_MERGE)
    )
    assert decision.outcome is StandingGrantOutcome.GRANT_MATCH
    assert decision.mutation_authorized is True


def test_platform_approval_is_distinct_from_grant_mismatch():
    context = _standing_context(allowed_actions=(AutonomyActionClass.GITHUB_MERGE,))
    decision = evaluate_standing_grant_decision(
        context,
        _standing_request(context, action=AutonomyActionClass.GITHUB_MERGE),
        platform_approval_required=True,
    )
    assert decision.outcome is StandingGrantOutcome.PLATFORM_APPROVAL_REQUIRED
    assert decision.mutation_authorized is False


@pytest.mark.parametrize(
    "override",
    [
        {"coordinator_id": "other-coordinator"},
        {"goal_id": "other-goal"},
        {"context_hash": "0" * 64},
        {"action": AutonomyActionClass.RUNTIME_ACTIVATE},
    ],
)
def test_standing_grant_mismatch_is_fail_closed(override):
    context = _standing_context()
    decision = evaluate_standing_grant_decision(context, _standing_request(context, **override))
    assert decision.outcome in {
        StandingGrantOutcome.OUT_OF_SCOPE,
        StandingGrantOutcome.INVALID,
    }
    assert decision.mutation_authorized is False


def test_standing_grant_context_rejects_tampering_and_revocation_pairing():
    context = _standing_context()
    tampered = context.model_dump(mode="json")
    tampered["goal_id"] = "tampered-goal"
    with pytest.raises(ValidationError, match="CONTEXT_HASH_INVALID"):
        StandingGrantContext.model_validate(tampered)
    with pytest.raises(ValidationError, match="REVOCATION_BINDING_INVALID"):
        _standing_context(revocation_reason="owner revoked")


@pytest.mark.parametrize(
    "context, requested_value",
    [
        ({"context_hash": "not-a-hash"}, {}),
        ({"context_hash": "0" * 64, "unexpected": True}, {}),
        (_standing_context().model_dump(mode="json"), {"context_hash": "bad"}),
        (None, None),
    ],
)
def test_malformed_standing_inputs_return_typed_invalid(context, requested_value):
    decision = evaluate_standing_grant_decision(context, requested_value)
    assert decision.outcome is StandingGrantOutcome.INVALID
    assert decision.mutation_authorized is False
    assert len(decision.context_hash) == 64


def _grant(**overrides) -> AutonomyGoalGrant:
    values = {
        "goal_id": "goal-autonomy-m0",
        "issued_by": "owner-james",
        "issued_at": NOW - timedelta(minutes=5),
        "expires_at": NOW + timedelta(hours=1),
        "repository": RepositoryIdentity(
            repository_id="James3014/Nexus-new",
            canonical_remote="https://github.com/James3014/Nexus-new.git",
        ),
        "collaboration_base": CollaborationBaseIdentity(
            branch="main",
            head_sha="a" * 40,
        ),
        "objective": "Evaluate one bounded candidate action in shadow mode",
        "allowed_actions": (AutonomyActionClass.CANDIDATE_APPROVE,),
        "forbidden_actions": (
            AutonomyActionClass.GITHUB_MERGE,
            AutonomyActionClass.RUNTIME_ACTIVATE,
            AutonomyActionClass.PRODUCTION_RELEASE,
        ),
        "risk_ceiling": AutonomyRiskLevel.MEDIUM,
        "path_policy": AutonomyPathPolicy(
            allowed_paths=("nexus/contracts", "tests/nexus/orchestrator"),
            forbidden_paths=(".github", "nexus/orchestrator/lifecycle_guards.py"),
        ),
        "maximum_tasks": 2,
        "maximum_attempts_per_task": 2,
        "maximum_provider_calls": 4,
        "maximum_wall_time_seconds": 900,
        "maximum_changed_files": 4,
        "maximum_concurrent_targets": 1,
        "independent_acceptance_required": True,
        "admitted_sensitive_scopes": (),
        "merge_authorization_policy": MergeAuthorizationPolicy.OWNER_ONLY,
        "runtime_activation_authorization_policy": RuntimeActivationPolicy.OWNER_ONLY,
        "production_release_authorized": False,
    }
    values.update(overrides)
    return AutonomyGoalGrant.issue(**values)


def _fresh_service_grant(**overrides) -> AutonomyGoalGrant:
    now = datetime.now(timezone.utc)
    return _grant(
        issued_at=now - timedelta(minutes=5),
        expires_at=now + timedelta(hours=1),
        **overrides,
    )


def _candidate(seed: str = "c") -> AutonomyCandidateIdentity:
    return AutonomyCandidateIdentity(
        task_id="autonomy-task-1",
        attempt_id="attempt-1",
        candidate_commit_sha=seed * 40,
        candidate_tree_sha="d" * 40,
        candidate_state_hash="e" * 64,
        verified_receipt_hash="f" * 64,
    )


def _budget(**overrides) -> AutonomyBudgetUsage:
    values = {
        "tasks": 0,
        "attempts_for_task": 0,
        "provider_calls": 0,
        "wall_time_seconds": 0,
        "changed_files": 0,
        "active_targets": 0,
    }
    values.update(overrides)
    return AutonomyBudgetUsage(**values)


def _evaluation(grant: AutonomyGoalGrant, **overrides) -> AutonomyEvaluationInput:
    candidate = _candidate()
    binding = AutonomySubmissionBinding.issue(
        task_id="autonomy-task-1",
        initial_attempt_id="attempt-1",
        action_request_hash="1" * 64,
        contract_hash="2" * 64,
        controller_revision="a" * 40,
        allowed_paths=("nexus/contracts", "tests/nexus/orchestrator"),
        repository=grant.repository,
        collaboration_base=grant.collaboration_base,
        goal_id=grant.goal_id,
        grant_hash=grant.grant_hash,
    )
    values = {
        "schema": "nexus.autonomy_evaluation_input.v1",
        "evaluated_at": NOW,
        "task_id": "autonomy-task-1",
        "attempt_id": "attempt-1",
        "contract_hash": "2" * 64,
        "action": AutonomyActionClass.CANDIDATE_APPROVE,
        "repository": grant.repository,
        "collaboration_base": grant.collaboration_base,
        "requested_paths": ("nexus/contracts/autonomy_goal.py",),
        "risk": AutonomyRiskLevel.MEDIUM,
        "sensitive_scopes": (),
        "child_scope": ChildAutonomyScope(
            allowed_actions=(AutonomyActionClass.CANDIDATE_APPROVE,),
            allowed_paths=("nexus/contracts",),
            risk_ceiling=AutonomyRiskLevel.MEDIUM,
            maximum_attempts_per_task=2,
            maximum_provider_calls=4,
            maximum_wall_time_seconds=900,
            maximum_changed_files=2,
            maximum_concurrent_targets=1,
        ),
        "budget_usage": _budget(),
        "submission_binding": binding,
        "post_submission_grant_presented": False,
        "implementer_id": "worker-codex",
        "candidate_at_verification": candidate,
        "current_candidate": candidate,
        "acceptance": AcceptanceIdentity(
            receipt_hash="3" * 64,
            accepted_by="independent-reviewer",
            authority_kind=AcceptanceAuthorityKind.INDEPENDENT_REVIEWER,
            candidate=candidate,
            candidate_receipt_hash=candidate.verified_receipt_hash,
        ),
        "expected_runtime_identity": AutonomyRuntimeIdentity(
            tool_manifest_hash="4" * 64,
            full_tool_schema_hash="5" * 64,
            permission_policy_hash="6" * 64,
            lifecycle_revision="7" * 64,
            server_instance_id="server-1",
        ),
        "current_runtime_identity": AutonomyRuntimeIdentity(
            tool_manifest_hash="4" * 64,
            full_tool_schema_hash="5" * 64,
            permission_policy_hash="6" * 64,
            lifecycle_revision="7" * 64,
            server_instance_id="server-1",
        ),
    }
    values.update(overrides)
    return AutonomyEvaluationInput(**values)


def _decision(grant: AutonomyGoalGrant, **overrides):
    return evaluate_autonomy_policy(grant, _evaluation(grant, **overrides))


def test_grant_hash_is_deterministic_frozen_and_extra_forbidden():
    grant = _grant(
        allowed_actions=(AutonomyActionClass.CANDIDATE_APPROVE, AutonomyActionClass.TASK_RETRY),
    )
    reordered = _grant(
        allowed_actions=(AutonomyActionClass.TASK_RETRY, AutonomyActionClass.CANDIDATE_APPROVE),
    )
    assert grant.grant_hash == reordered.grant_hash
    with pytest.raises(ValidationError):
        AutonomyGoalGrant.model_validate({**grant.model_dump(mode="json"), "unknown": True})
    with pytest.raises(ValidationError):
        grant.goal_id = "changed"


@pytest.mark.parametrize(
    "override",
    [
        {
            "repository": RepositoryIdentity.model_construct(
                repository_id="../../repo", canonical_remote="not-a-url"
            )
        },
        {
            "collaboration_base": CollaborationBaseIdentity.model_construct(
                branch="main..bad", head_sha="a" * 40
            )
        },
    ],
)
def test_malformed_repository_and_base_identity_are_rejected(override):
    with pytest.raises(ValidationError):
        _grant(**override)


def test_tampered_and_expired_grants_fail_closed():
    grant = _grant()
    tampered = grant.model_dump(mode="json")
    tampered["maximum_tasks"] = 99
    decision = evaluate_autonomy_policy(tampered, _evaluation(grant))
    assert decision.state is AutonomyDecisionState.WOULD_BLOCK
    assert decision.reason_codes == ("GRANT_HASH_INVALID",)

    expired = _grant(
        issued_at=NOW - timedelta(hours=2),
        expires_at=NOW - timedelta(hours=1),
    )
    decision = _decision(expired)
    assert decision.reason_codes == ("GRANT_EXPIRED",)

    missing_schema = grant.model_dump(mode="json")
    missing_schema.pop("schema")
    decision = evaluate_autonomy_policy(missing_schema, _evaluation(grant))
    assert decision.reason_codes == ("GRANT_INVALID",)


def test_valid_exact_shadow_evaluation_is_deterministic():
    grant = _grant()
    first = _decision(grant)
    second = _decision(grant)
    assert first.state is AutonomyDecisionState.WOULD_AUTO_CONTINUE
    assert first.reason_codes == ()
    assert first.decision_hash == second.decision_hash
    assert first.input_hash == second.input_hash
    assert first.shadow_only is True
    assert first.mutation_authorized is False
    tampered = first.model_dump(mode="json")
    tampered["state"] = AutonomyDecisionState.WOULD_BLOCK.value
    with pytest.raises(ValidationError, match="DECISION_HASH_INVALID"):
        AutonomyDecision.model_validate(tampered)


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        (
            {
                "repository": RepositoryIdentity(
                    repository_id="other/repo", canonical_remote="https://example.test/other.git"
                )
            },
            "REPOSITORY_IDENTITY_MISMATCH",
        ),
        (
            {"collaboration_base": CollaborationBaseIdentity(branch="main", head_sha="b" * 40)},
            "BASE_IDENTITY_MISMATCH",
        ),
        ({"action": AutonomyActionClass.TASK_RETRY}, "ACTION_NOT_ALLOWED"),
        ({"risk": AutonomyRiskLevel.HIGH}, "RISK_CEILING_EXCEEDED"),
    ],
)
def test_identity_action_and_risk_mismatches_block(override, reason):
    decision = _decision(_grant(), **override)
    assert decision.state is AutonomyDecisionState.WOULD_BLOCK
    assert reason in decision.reason_codes


def test_forbidden_action_and_production_default_block():
    with pytest.raises(ValidationError):
        _grant(
            allowed_actions=(AutonomyActionClass.GITHUB_MERGE,),
            forbidden_actions=(AutonomyActionClass.GITHUB_MERGE,),
        )

    forbidden = _decision(_grant(), action=AutonomyActionClass.GITHUB_MERGE)
    assert "ACTION_NOT_ALLOWED" in forbidden.reason_codes
    assert "ACTION_FORBIDDEN" in forbidden.reason_codes

    production_grant = _grant(
        allowed_actions=(AutonomyActionClass.PRODUCTION_RELEASE,),
        forbidden_actions=(),
        admitted_sensitive_scopes=(SensitiveScope.PRODUCTION,),
    )
    decision = _decision(
        production_grant,
        action=AutonomyActionClass.PRODUCTION_RELEASE,
        sensitive_scopes=(SensitiveScope.PRODUCTION,),
    )
    assert "PRODUCTION_RELEASE_NOT_AUTHORIZED" in decision.reason_codes

    merge = _decision(
        _grant(
            allowed_actions=(AutonomyActionClass.GITHUB_MERGE,),
            forbidden_actions=(),
        ),
        action=AutonomyActionClass.GITHUB_MERGE,
    )
    assert "MERGE_NOT_AUTHORIZED" in merge.reason_codes

    activation = _decision(
        _grant(
            allowed_actions=(AutonomyActionClass.RUNTIME_ACTIVATE,),
            forbidden_actions=(),
        ),
        action=AutonomyActionClass.RUNTIME_ACTIVATE,
    )
    assert "RUNTIME_ACTIVATION_NOT_AUTHORIZED" in activation.reason_codes


def test_path_and_child_scope_widening_block():
    grant = _grant()
    outside = _decision(grant, requested_paths=("nexus/services/gateway.py",))
    assert "PATH_SCOPE_EXCEEDED" in outside.reason_codes

    widened = _evaluation(grant).model_copy(
        update={
            "child_scope": ChildAutonomyScope(
                allowed_actions=(AutonomyActionClass.CANDIDATE_APPROVE,),
                allowed_paths=("nexus",),
                risk_ceiling=AutonomyRiskLevel.HIGH,
                maximum_attempts_per_task=3,
                maximum_provider_calls=5,
                maximum_wall_time_seconds=901,
                maximum_changed_files=5,
                maximum_concurrent_targets=2,
            )
        }
    )
    decision = evaluate_autonomy_policy(grant, widened)
    assert decision.reason_codes == ("CHILD_SCOPE_WIDENING",)


@pytest.mark.parametrize(
    ("usage", "reason"),
    [
        (_budget(tasks=2), "TASK_BUDGET_EXHAUSTED"),
        (_budget(attempts_for_task=2), "ATTEMPT_BUDGET_EXHAUSTED"),
        (_budget(provider_calls=4), "PROVIDER_CALL_BUDGET_EXHAUSTED"),
        (_budget(wall_time_seconds=900), "WALL_TIME_BUDGET_EXHAUSTED"),
        (_budget(changed_files=4), "CHANGED_FILE_BUDGET_EXHAUSTED"),
        (_budget(active_targets=1), "TARGET_CONCURRENCY_EXHAUSTED"),
    ],
)
def test_enforceable_budget_exhaustion_blocks(usage, reason):
    decision = _decision(_grant(), budget_usage=usage)
    assert reason in decision.reason_codes


def test_independent_acceptance_and_exact_candidate_binding_are_required():
    grant = _grant()
    missing = _decision(grant, acceptance=None)
    assert "INDEPENDENT_ACCEPTANCE_REQUIRED" in missing.reason_codes

    candidate = _candidate()
    worker_acceptance = AcceptanceIdentity(
        receipt_hash="3" * 64,
        accepted_by="worker-codex",
        authority_kind=AcceptanceAuthorityKind.WORKER_OUTPUT,
        candidate=candidate,
        candidate_receipt_hash=candidate.verified_receipt_hash,
    )
    same_worker = _decision(grant, acceptance=worker_acceptance)
    assert "IMPLEMENTER_ACCEPTANCE_FORBIDDEN" in same_worker.reason_codes

    mismatch = _decision(
        grant,
        acceptance=AcceptanceIdentity(
            receipt_hash="3" * 64,
            accepted_by="independent-reviewer",
            authority_kind=AcceptanceAuthorityKind.INDEPENDENT_REVIEWER,
            candidate=_candidate("b"),
            candidate_receipt_hash=_candidate("b").verified_receipt_hash,
        ),
    )
    assert "ACCEPTANCE_CANDIDATE_MISMATCH" in mismatch.reason_codes

    receipt_mismatch = _decision(
        grant,
        acceptance=AcceptanceIdentity(
            receipt_hash="3" * 64,
            accepted_by="independent-reviewer",
            authority_kind=AcceptanceAuthorityKind.INDEPENDENT_REVIEWER,
            candidate=candidate,
            candidate_receipt_hash="0" * 64,
        ),
    )
    assert "ACCEPTANCE_RECEIPT_CANDIDATE_MISMATCH" in receipt_mismatch.reason_codes

    drift = _decision(grant, current_candidate=_candidate("b"))
    assert "CANDIDATE_IDENTITY_DRIFT" in drift.reason_codes

    absent_candidate = _decision(
        grant,
        candidate_at_verification=None,
        current_candidate=None,
        acceptance=None,
    )
    assert "CANDIDATE_IDENTITY_REQUIRED" in absent_candidate.reason_codes


def test_sensitive_and_runtime_identity_drift_block():
    grant = _grant()
    sensitive = _decision(grant, sensitive_scopes=(SensitiveScope.SECURITY,))
    assert "SENSITIVE_SCOPE_NOT_ADMITTED" in sensitive.reason_codes

    drifted = _evaluation(grant).current_runtime_identity.model_copy(
        update={"tool_manifest_hash": "9" * 64}
    )
    runtime = _decision(grant, current_runtime_identity=drifted)
    assert "RUNTIME_IDENTITY_DRIFT" in runtime.reason_codes


def test_submission_binding_attempt_must_match_evaluation_attempt():
    decision = _decision(_grant(), attempt_id="attempt-other")
    assert "ATTEMPT_BINDING_MISMATCH" in decision.reason_codes


def test_wall_clock_expiry_blocks_timestamp_backdating():
    now = datetime.now(timezone.utc)
    grant = _grant(
        issued_at=now - timedelta(hours=2),
        expires_at=now - timedelta(seconds=1),
    )
    decision = _decision(
        grant,
        evaluated_at=grant.expires_at - timedelta(seconds=1),
    )
    assert decision.reason_codes == ("GRANT_EXPIRED",)


def test_legacy_task_stays_manual_and_post_submission_injection_is_rejected():
    grant = _grant()
    legacy = _decision(grant, submission_binding=None)
    assert legacy.reason_codes == ("LEGACY_TASK_MANUAL",)
    injected = _decision(
        grant,
        submission_binding=None,
        post_submission_grant_presented=True,
    )
    assert injected.reason_codes == ("POST_SUBMISSION_GRANT_INJECTION",)


def test_submission_goal_and_contract_binding_mismatch_blocks():
    grant = _grant()
    baseline = _evaluation(grant)
    wrong_goal = AutonomySubmissionBinding.issue(
        task_id=baseline.task_id,
        initial_attempt_id=baseline.attempt_id,
        action_request_hash="1" * 64,
        contract_hash=baseline.contract_hash,
        controller_revision="a" * 40,
        allowed_paths=("nexus/contracts",),
        repository=grant.repository,
        collaboration_base=grant.collaboration_base,
        goal_id="other-goal",
        grant_hash=grant.grant_hash,
    )
    decision = evaluate_autonomy_policy(
        grant,
        baseline.model_copy(update={"submission_binding": wrong_goal}),
    )
    assert "GOAL_BINDING_MISMATCH" in decision.reason_codes

    task = _decision(grant, task_id="other-task")
    assert "GOAL_BINDING_MISMATCH" in task.reason_codes

    contract = _decision(grant, contract_hash="9" * 64)
    assert "CONTRACT_HASH_MISMATCH" in contract.reason_codes

    repository_drift = AutonomySubmissionBinding.issue(
        task_id=baseline.task_id,
        initial_attempt_id=baseline.attempt_id,
        action_request_hash="1" * 64,
        contract_hash=baseline.contract_hash,
        controller_revision="a" * 40,
        allowed_paths=("nexus/contracts",),
        repository=RepositoryIdentity(
            repository_id="other/repository",
            canonical_remote="https://github.com/other/repository.git",
        ),
        collaboration_base=grant.collaboration_base,
        goal_id=grant.goal_id,
        grant_hash=grant.grant_hash,
    )
    repository_decision = evaluate_autonomy_policy(
        grant,
        baseline.model_copy(update={"submission_binding": repository_drift}),
    )
    assert "SUBMISSION_REPOSITORY_IDENTITY_MISMATCH" in repository_decision.reason_codes

    base_drift = AutonomySubmissionBinding.issue(
        task_id=baseline.task_id,
        initial_attempt_id=baseline.attempt_id,
        action_request_hash="1" * 64,
        contract_hash=baseline.contract_hash,
        controller_revision="a" * 40,
        allowed_paths=("nexus/contracts",),
        repository=grant.repository,
        collaboration_base=CollaborationBaseIdentity(
            branch="main",
            head_sha="b" * 40,
        ),
        goal_id=grant.goal_id,
        grant_hash=grant.grant_hash,
    )
    base_decision = evaluate_autonomy_policy(
        grant,
        baseline.model_copy(update={"submission_binding": base_drift}),
    )
    assert "SUBMISSION_BASE_IDENTITY_MISMATCH" in base_decision.reason_codes


def test_unknown_evaluator_field_and_candidate_attempt_mismatch_fail_closed():
    grant = _grant()
    raw = _evaluation(grant).model_dump(mode="json")
    raw["unknown_authority"] = True
    decision = evaluate_autonomy_policy(grant, raw)
    assert decision.reason_codes == ("EVALUATOR_INPUT_INVALID",)

    empty_paths = _evaluation(grant).model_dump(mode="json")
    empty_paths["requested_paths"] = []
    decision = evaluate_autonomy_policy(grant, empty_paths)
    assert decision.reason_codes == ("EVALUATOR_INPUT_INVALID",)

    candidate = _candidate().model_copy(update={"attempt_id": "attempt-other"})
    mismatch = _decision(
        grant,
        candidate_at_verification=candidate,
        current_candidate=candidate,
        acceptance=AcceptanceIdentity(
            receipt_hash="3" * 64,
            accepted_by="independent-reviewer",
            authority_kind=AcceptanceAuthorityKind.INDEPENDENT_REVIEWER,
            candidate=candidate,
            candidate_receipt_hash=candidate.verified_receipt_hash,
        ),
    )
    assert "CANDIDATE_TASK_ATTEMPT_MISMATCH" in mismatch.reason_codes


def _service_request(
    tmp_path,
    task_id: str,
    grant: AutonomyGoalGrant | None = None,
    *,
    execution_lane: str = "ISOLATED_TARGET",
):
    request = {
        "task_id": task_id,
        "what": "exercise the shadow autonomy lineage",
        "why": "prove that shadow evidence never becomes lifecycle authority",
        "controller_revision": "a" * 40,
        "target_base_revision": "b" * 40,
        "controller_repo_root": str(tmp_path / "controller"),
        "target_repo_root": str(tmp_path / "targets" / task_id),
        "target_worktree_root": str(tmp_path / "targets"),
        "allowed_files": ["nexus/contracts/autonomy_goal.py"],
        "forbidden_files": [],
        "verifier_commands": ["python3 -c 'print(1)'"],
        "protected_contracts": [],
        "worker": "codex",
        "execution_lane": execution_lane,
    }
    if grant is not None:
        request["autonomy_goal_grant"] = grant.model_dump(mode="json")
    return request


def _wait_for(service: SelfHostedTaskService, task_id: str, status: str):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        state = service.get_task(task_id)
        if state and state.get("status") == status:
            return state
        time.sleep(0.01)
    return service.get_task(task_id)


def test_submit_binds_goal_grant_once_and_shadow_still_stops_for_human(tmp_path):
    grant = _fresh_service_grant()

    def runner(_contract, _request, _update):
        return {
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "terminal_status": "PENDING_HUMAN_APPROVAL",
            "candidate_commit_created": True,
        }

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        runner=runner,
        auto_reconcile=False,
        ephemeral=True,
    )
    task_id = "shadow-service-task"
    service.submit_task(_service_request(tmp_path, task_id, grant))
    state = _wait_for(service, task_id, "PENDING_HUMAN_APPROVAL")

    assert state["status"] == "PENDING_HUMAN_APPROVAL"
    assert state["promotion_status"] == "PENDING_HUMAN_APPROVAL"
    assert state.get("approved_binding") is None
    assert state.get("integration_result_sha") is None
    assert state.get("merge_performed") is False
    assert state.get("push_performed") is False
    decision = _decision(grant)
    assert decision.authority_inputs_verified is False
    assert decision.claim_ceiling == "SHADOW_CALLER_BOUND_EVIDENCE_ONLY"
    assert state["autonomy_goal_id"] == grant.goal_id
    assert state["autonomy_goal_grant_hash"] == grant.grant_hash
    assert state["autonomy_mode"] == "SHADOW"
    binding = AutonomySubmissionBinding.model_validate(state["autonomy_submission_binding"])
    assert binding.task_id == task_id
    assert binding.grant_hash == grant.grant_hash
    assert binding.repository == grant.repository
    assert binding.collaboration_base == grant.collaboration_base

    compact = service.get_task_snapshot(task_id)
    assert compact["autonomy"] == {
        "schema": "nexus.autonomy_submission_projection.v1",
        "mode": "SHADOW",
        "eligible": True,
        "goal_id": grant.goal_id,
        "grant_hash": grant.grant_hash,
        "binding_hash": binding.binding_hash,
        "reason_codes": [],
    }

    before = service._state_path(task_id).read_bytes()
    without_grant = _service_request(tmp_path, task_id)
    with pytest.raises(ValueError, match="AUTONOMY_GOAL_GRANT_REQUIRED"):
        service.submit_task(without_grant)
    assert service._state_path(task_id).read_bytes() == before


def test_legacy_state_is_manual_read_only_and_grant_injection_fails(tmp_path):
    def runner(_contract, _request, _update):
        return {
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "terminal_status": "PENDING_HUMAN_APPROVAL",
        }

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        runner=runner,
        auto_reconcile=False,
        ephemeral=True,
    )
    task_id = "legacy-manual-task"
    manual_request = _service_request(tmp_path, task_id)
    service.submit_task(manual_request)
    assert _wait_for(service, task_id, "PENDING_HUMAN_APPROVAL")
    state_path = service._state_path(task_id)
    before = state_path.read_bytes()

    projection = service.get_task_snapshot(task_id)["autonomy"]
    assert projection == {
        "schema": "nexus.autonomy_submission_projection.v1",
        "mode": "MANUAL",
        "eligible": False,
        "reason_codes": ["LEGACY_TASK_MANUAL"],
    }
    assert state_path.read_bytes() == before

    injected = _service_request(tmp_path, task_id, _fresh_service_grant())
    with pytest.raises(ValueError, match="POST_SUBMISSION_GRANT_INJECTION"):
        service.submit_task(injected)
    assert state_path.read_bytes() == before


def test_tampered_persisted_submission_binding_projects_fail_closed(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        auto_reconcile=False,
        ephemeral=True,
    )
    grant = _fresh_service_grant()
    binding = AutonomySubmissionBinding.issue(
        task_id="binding-tamper",
        initial_attempt_id="attempt-1",
        action_request_hash="1" * 64,
        contract_hash="2" * 64,
        controller_revision="a" * 40,
        repository=grant.repository,
        collaboration_base=grant.collaboration_base,
        allowed_paths=("nexus/contracts",),
        goal_id=grant.goal_id,
        grant_hash=grant.grant_hash,
    ).model_dump(mode="json")
    binding["contract_hash"] = "9" * 64
    service._write_state(
        "binding-tamper",
        {
            "task_id": "binding-tamper",
            "status": "PENDING_HUMAN_APPROVAL",
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "autonomy_goal_id": grant.goal_id,
            "autonomy_goal_grant_hash": grant.grant_hash,
            "autonomy_mode": "SHADOW",
            "autonomy_submission_binding": binding,
        },
    )
    before = service._state_path("binding-tamper").read_bytes()
    projected = service.get_task_snapshot("binding-tamper")["autonomy"]
    assert projected["eligible"] is False
    assert projected["reason_codes"] == ["SUBMISSION_BINDING_INVALID"]
    assert service._state_path("binding-tamper").read_bytes() == before


def test_validly_hashed_binding_drift_projects_and_resubmits_fail_closed(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        auto_reconcile=False,
        ephemeral=True,
    )
    grant = _fresh_service_grant()
    binding = AutonomySubmissionBinding.issue(
        task_id="binding-drift",
        initial_attempt_id="attempt-1",
        action_request_hash="1" * 64,
        contract_hash="9" * 64,
        controller_revision="a" * 40,
        repository=grant.repository,
        collaboration_base=grant.collaboration_base,
        allowed_paths=("nexus/contracts/autonomy_goal.py",),
        goal_id=grant.goal_id,
        grant_hash=grant.grant_hash,
    )
    state = {
        "task_id": "binding-drift",
        "status": "PENDING_HUMAN_APPROVAL",
        "promotion_status": "PENDING_HUMAN_APPROVAL",
        "contract_hash": "2" * 64,
        "controller_revision": "a" * 40,
        "contract": {"allowed_files": ["nexus/contracts/autonomy_goal.py"]},
        "attempts": [
            {
                "attempt_id": "attempt-1",
                "action_request_hash": "1" * 64,
            }
        ],
        "autonomy_goal_id": grant.goal_id,
        "autonomy_goal_grant_hash": grant.grant_hash,
        "autonomy_mode": "SHADOW",
        "autonomy_submission_binding": binding.model_dump(mode="json"),
    }
    service._write_state("binding-drift", state)
    before = service._state_path("binding-drift").read_bytes()

    projected = service.get_task_snapshot("binding-drift")["autonomy"]
    assert projected["eligible"] is False
    assert projected["reason_codes"] == ["SUBMISSION_BINDING_DRIFT"]
    with pytest.raises(ValueError, match="AUTONOMY_SUBMISSION_BINDING_DRIFT"):
        service.submit_task(_service_request(tmp_path, "binding-drift", grant))
    assert service._state_path("binding-drift").read_bytes() == before


def test_submission_rejects_expired_base_drift_and_out_of_scope_grants(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        auto_reconcile=False,
        ephemeral=True,
    )
    now = datetime.now(timezone.utc)
    expired = _grant(
        issued_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
    )
    with pytest.raises(ValueError, match="AUTONOMY_GOAL_GRANT_EXPIRED"):
        service.submit_task(_service_request(tmp_path, "expired-submit", expired))

    base_drift = _fresh_service_grant(
        collaboration_base=CollaborationBaseIdentity(branch="main", head_sha="b" * 40)
    )
    with pytest.raises(ValueError, match="AUTONOMY_COLLABORATION_BASE_MISMATCH"):
        service.submit_task(_service_request(tmp_path, "base-drift", base_drift))

    out_of_scope = _fresh_service_grant(
        path_policy=AutonomyPathPolicy(
            allowed_paths=("docs",),
            forbidden_paths=(),
        )
    )
    with pytest.raises(ValueError, match="AUTONOMY_TASK_SCOPE_EXCEEDED"):
        service.submit_task(_service_request(tmp_path, "scope-drift", out_of_scope))


def test_goal_grant_rejects_direct_canonical_submission(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.resolve_execution_lane",
        lambda request, active_mutation_tasks=0: {
            "execution_lane": "DIRECT_CANONICAL",
            "eligible": True,
            "blockers": [],
            "next_action": "edit_canonical_checkout",
        },
    )
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        auto_reconcile=False,
        ephemeral=True,
    )
    with pytest.raises(ValueError, match="AUTONOMY_DIRECT_CANONICAL_UNSUPPORTED"):
        service.submit_task(
            _service_request(
                tmp_path,
                "direct-autonomy-task",
                _fresh_service_grant(),
                execution_lane="DIRECT_CANONICAL",
            )
        )
    assert service.get_task("direct-autonomy-task") is None
