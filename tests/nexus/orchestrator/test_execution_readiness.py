"""Execution Readiness evaluator tests (issue #807 G1): precedence, UNPROVEN,
canonical routing, completion binding, and the no-fake-certification fence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.contracts.autonomy_goal import (
    AutonomyActionClass,
    RepositoryIdentity,
    StandingGrantContext,
)
from nexus.contracts.execution_readiness import (
    CanonicalNextAction,
    ExecutionReadinessBlockerCode,
    ExecutionReadinessOutcome,
    ExecutionReadinessPlane,
    ExecutionReadinessRequest,
    ExecutionReadinessStatus,
    RequiredCompletionContract,
)
from nexus.orchestrator import standing_grant_store
from nexus.orchestrator.execution_readiness import (
    CompletionAuthorityObservation,
    GatewayReadinessObservation,
    PlaneObservation,
    _canonical_authority_observation,
    _canonical_provider_preflight_digest,
    _physical_repository_id,
    evaluate_execution_readiness,
    evaluate_source_binding,
)
from nexus.orchestrator.standing_grant_store import StandingGrantReceipt


def test_provider_preflight_digest_is_deterministic_and_tamper_sensitive() -> None:
    preflight = _valid_preflight("agy", "model-1")
    reordered = {key: preflight[key] for key in reversed(tuple(preflight))}
    assert _canonical_provider_preflight_digest(preflight) == _canonical_provider_preflight_digest(
        reordered
    )
    tampered = dict(preflight, probe_evidence_hash="e" * 64)
    assert _canonical_provider_preflight_digest(preflight) != _canonical_provider_preflight_digest(
        tampered
    )


def test_authenticated_preflight_summary_stays_within_evidence_budget(monkeypatch) -> None:
    import nexus.orchestrator.self_hosted_task_service as task_service

    monkeypatch.setattr(
        task_service,
        "validate_workforce_dispatch_binding",
        lambda *_a, **_k: {
            "worker_id": "worker-1",
            "provider": "agy",
            "model": "model-1",
            "policy_hash": "p" * 64,
            "binding_hash": "b" * 64,
            "aggregate_binding_hash": "a" * 64,
        },
    )
    preflight = _valid_preflight("agy", "model-1")
    preflight.update(
        authentication_required=True,
        authenticated=True,
        authentication_evidence="authenticated-exact-probe",
    )
    result = _evaluate(
        _request(worker_constraints=("provider=agy",)),
        {
            ExecutionReadinessPlane.WORKFORCE: (
                PlaneObservation(
                    plane=ExecutionReadinessPlane.WORKFORCE,
                    status=ExecutionReadinessStatus.PASSED,
                    workforce_dispatch_binding=_workforce_binding(),
                ),
            )
        },
        provider_preflight_observer=lambda _p, _m: preflight,
    )
    workforce = result.plane_results[-1]
    assert workforce.status is ExecutionReadinessStatus.PASSED
    assert len(workforce.evidence_identities) == 16
    assert (
        "provider_preflight_auth=required:true,authenticated:true,evidence:authenticated-exact-probe"
        in workforce.evidence_identities
    )


@pytest.mark.parametrize("observer_kind", ("missing", "raises", "malformed", "mismatch"))
def test_provider_authentication_requirement_observer_fails_closed(
    monkeypatch, observer_kind
) -> None:
    import nexus.orchestrator.self_hosted_task_service as task_service

    monkeypatch.setattr(
        task_service,
        "validate_workforce_dispatch_binding",
        lambda *_a, **_k: {
            "worker_id": "worker-1",
            "provider": "agy",
            "model": "model-1",
            "policy_hash": "p" * 64,
            "binding_hash": "b" * 64,
            "aggregate_binding_hash": "a" * 64,
        },
    )
    preflight = _valid_preflight("agy", "model-1")
    preflight.update(
        authentication_required=True,
        authenticated=True,
        authentication_evidence="authenticated-exact-probe",
    )
    if observer_kind == "missing":
        observer = None
    elif observer_kind == "raises":

        def observer(_provider):
            raise RuntimeError("observer unavailable")

    elif observer_kind == "malformed":

        def observer(_provider):
            return "true"

    else:

        def observer(_provider):
            return False

    result = (
        _evaluate(
            _request(worker_constraints=("provider=agy",)),
            {
                ExecutionReadinessPlane.WORKFORCE: (
                    PlaneObservation(
                        plane=ExecutionReadinessPlane.WORKFORCE,
                        status=ExecutionReadinessStatus.PASSED,
                        workforce_dispatch_binding=_workforce_binding(),
                    ),
                )
            },
            provider_preflight_observer=lambda _p, _m: preflight,
            provider_authentication_required_observer=observer,
        )
        if observer_kind != "missing"
        else evaluate_execution_readiness(
            _request(worker_constraints=("provider=agy",)),
            {
                **_all_pass(),
                ExecutionReadinessPlane.WORKFORCE: (
                    PlaneObservation(
                        plane=ExecutionReadinessPlane.WORKFORCE,
                        status=ExecutionReadinessStatus.PASSED,
                        workforce_dispatch_binding=_workforce_binding(),
                    ),
                ),
            },
            evaluated_at=datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc),
            provider_preflight_observer=lambda _p, _m: preflight,
        )
    )
    assert result.primary_blocker is not None
    assert result.primary_blocker.code is ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY


def test_non_json_preflight_evidence_fails_closed(monkeypatch) -> None:
    import nexus.orchestrator.self_hosted_task_service as task_service

    monkeypatch.setattr(
        task_service,
        "validate_workforce_dispatch_binding",
        lambda *_a, **_k: {
            "worker_id": "worker-1",
            "provider": "agy",
            "model": "model-1",
            "policy_hash": "p" * 64,
            "binding_hash": "b" * 64,
            "aggregate_binding_hash": "a" * 64,
        },
    )
    preflight = _valid_preflight("agy", "model-1")
    preflight["authentication_evidence"] = object()
    result = _evaluate(
        _request(worker_constraints=("provider=agy",)),
        {
            ExecutionReadinessPlane.WORKFORCE: (
                PlaneObservation(
                    plane=ExecutionReadinessPlane.WORKFORCE,
                    status=ExecutionReadinessStatus.PASSED,
                    workforce_dispatch_binding=_workforce_binding(),
                ),
            )
        },
        provider_preflight_observer=lambda _p, _m: preflight,
    )
    assert result.primary_blocker.code is ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY


def _request(**overrides: object) -> ExecutionReadinessRequest:
    base: dict[str, object] = {
        "repository_owner": "James3014",
        "repository_name": "Nexus-new",
        "intended_source_commit": "a" * 40,
        "intended_source_tree": "b" * 40,
        "execution_realm": "in_process_preflight",
        "required_action_family": "MUTATE_BOUNDED",
        "execution_contract_kind": "BOUNDED_DIRECT_CHANGE",
    }
    base.update(overrides)
    return ExecutionReadinessRequest(**base)  # type: ignore[arg-type]


def test_material_authority_selects_exact_repository_with_same_goal_and_scope(
    tmp_path: Path, monkeypatch
) -> None:
    """Physical keyed receipts are selected by the complete repository key."""
    receipt_root = tmp_path / "authority"
    monkeypatch.setattr(
        standing_grant_store, "DEFAULT_RECEIPT_PATH", receipt_root / "standing-grant.json"
    )
    common = dict(goal_id="goal-readiness-keyed", thread_id="scope-readiness-keyed")
    repo_a = RepositoryIdentity(
        repository_id="Owner/repo-a", canonical_remote="https://github.com/Owner/repo-a.git"
    )
    repo_b = RepositoryIdentity(
        repository_id="Owner/repo-b", canonical_remote="https://github.com/Owner/repo-b.git"
    )
    receipts = []
    for repo, grant_id in ((repo_a, "readiness-a"), (repo_b, "readiness-b")):
        context = StandingGrantContext.issue(
            owner_id="owner-james",
            coordinator_id="coordinator-codex",
            repository=repo,
            allowed_actions=(AutonomyActionClass.TASK_SUBMIT,),
            issued_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            **common,
        )
        receipt = StandingGrantReceipt.issue(grant_id=grant_id, context=context)
        standing_grant_store.write_keyed_standing_grant_receipt(receipt)
        receipts.append(receipt)

    def observe(repo: RepositoryIdentity) -> PlaneObservation:
        return _canonical_authority_observation(
            _request(
                repository_owner=repo.repository_id.split("/", 1)[0],
                repository_name=repo.repository_id.split("/", 1)[1],
                task_campaign_goal_identity=common["goal_id"],
                durable_coordination_scope_id=common["thread_id"],
                durable_repository_canonical_remote=repo.canonical_remote,
            ),
            datetime.now(timezone.utc),
        )

    for repo, receipt in zip((repo_a, repo_b), receipts):
        observation = observe(repo)
        assert observation.status is ExecutionReadinessStatus.PASSED
        assert f"authority_receipt_hash={receipt.receipt_hash}" in observation.evidence_identities
        assert f"authority_repository_id={repo.repository_id}" in observation.evidence_identities
        assert f"authority_goal_id={common['goal_id']}" in observation.evidence_identities
        assert "authority_action=TASK_SUBMIT" in observation.evidence_identities

    wrong = observe(
        RepositoryIdentity(
            repository_id="Owner/repo-c",
            canonical_remote="https://github.com/Owner/repo-c.git",
        )
    )
    assert wrong.status is ExecutionReadinessStatus.BLOCKED
    assert wrong.blocker_code is ExecutionReadinessBlockerCode.TASK_AUTHORITY_MISSING

    missing = _canonical_authority_observation(
        _request(
            task_campaign_goal_identity=common["goal_id"],
            durable_coordination_scope_id=None,
            durable_repository_canonical_remote=None,
        ),
        datetime.now(timezone.utc),
    )
    assert missing.status is ExecutionReadinessStatus.BLOCKED


def _pass(plane: ExecutionReadinessPlane, *evidence: str) -> PlaneObservation:
    return PlaneObservation(
        plane=plane,
        status=ExecutionReadinessStatus.PASSED,
        evidence_identities=evidence or (f"{plane.value}:ok",),
    )


def _block(
    plane: ExecutionReadinessPlane,
    code: ExecutionReadinessBlockerCode,
    *evidence: str,
) -> PlaneObservation:
    return PlaneObservation(
        plane=plane,
        status=ExecutionReadinessStatus.BLOCKED,
        blocker_code=code,
        evidence_identities=evidence or (f"{plane.value}:{code.value}",),
    )


def _all_pass() -> dict[ExecutionReadinessPlane, tuple[PlaneObservation, ...]]:
    return {plane: (_pass(plane),) for plane in ExecutionReadinessPlane}


def _evaluate(
    request: ExecutionReadinessRequest,
    overrides: dict[ExecutionReadinessPlane, tuple[PlaneObservation, ...]] | None = None,
    *,
    completion_observation: CompletionAuthorityObservation | None = None,
    provider_preflight_observer=None,
    provider_authentication_required_observer=None,
):
    observations = _all_pass()
    if overrides:
        observations.update(overrides)
    return evaluate_execution_readiness(
        request,
        observations,
        completion_observation=completion_observation,
        evaluated_at=datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc),
        provider_preflight_observer=provider_preflight_observer,
        provider_authentication_required_observer=(
            provider_authentication_required_observer
            or (lambda provider: str(provider).strip().lower() == "agy")
        ),
    )


def _workforce_binding() -> dict[str, object]:
    demands = {"schema": "nexus.workforce_demands.v1", "demands": [{"demand_id": "d1"}]}
    return {
        "planner_output": {"plan_payload": {"signal_snapshot": {"workforce_demands": demands}}},
        "workforce_demands": demands,
        "workforce_admission": {"overall_decision": "ALLOW"},
        "canonical_dispatch_envelope": {"schema": "nexus.canonical_dispatch.v1"},
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "task_card_path": "tasks/card.md",
        "task_card_hash": "c" * 64,
    }


def _valid_preflight(provider: str, model: str) -> dict[str, object]:
    authentication_required = provider == "agy"
    return {
        "schema": "nexus.provider_preflight.v1",
        "status": "VERSION_VERIFIED",
        "blocker": None,
        "provider": provider,
        "requested_model": model,
        "resolved_model": model,
        "execution_ready": True,
        "readiness_status": "MODEL_VERIFIED",
        "model_reachable": True,
        "requested_model_verified": True,
        "binary_found": True,
        "binary_path": "/bin/agy",
        "binary_sha256": "b" * 64,
        "cli_version_sha256": "c" * 64,
        "probe_evidence_hash": "d" * 64,
        "probe_expires_at": "2099-01-01T00:00:00Z",
        "authentication_required": authentication_required,
        "authenticated": authentication_required,
        "authentication_evidence": (
            "successful_exact_model_probe" if authentication_required else None
        ),
    }


@pytest.mark.parametrize(
    "mutation",
    (
        "wrong_task",
        "missing_attempt",
        "missing_action",
        "missing_request",
        "missing_action_map",
        "wrong_action_task",
        "malformed_request_hash",
        "nested_action_mismatch",
        "nested_request_mismatch",
        "nested_action_malformed",
        "nested_request_malformed",
        "not_found",
        "invalid_state",
    ),
)
def test_material_replay_identity_hostiles_block(monkeypatch, mutation):
    import nexus.orchestrator.self_hosted_task_service as task_service

    snapshot = {
        "task_id": "goal-test",
        "attempt_id": "attempt-1",
        "action_id": "action-1",
        "request_hash": "a" * 64,
        "status": "READY",
        "task_action": {
            "task_id": "goal-test",
            "action_id": "action-1",
            "request_hash": "a" * 64,
            "next_action": "none",
        },
        "found": True,
        "state_valid": True,
    }
    if mutation == "wrong_task":
        snapshot["task_id"] = "other"
    elif mutation == "missing_attempt":
        snapshot.pop("attempt_id")
    elif mutation == "missing_action":
        snapshot.pop("action_id")
    elif mutation == "missing_request":
        snapshot.pop("request_hash")
    elif mutation == "missing_action_map":
        snapshot.pop("task_action")
    elif mutation == "wrong_action_task":
        snapshot["task_action"]["task_id"] = "other"
    elif mutation == "malformed_request_hash":
        snapshot["request_hash"] = "R" * 64
    elif mutation == "nested_action_mismatch":
        snapshot["task_action"]["action_id"] = "action-other"
    elif mutation == "nested_request_mismatch":
        snapshot["task_action"]["request_hash"] = "e" * 64
    elif mutation == "nested_action_malformed":
        snapshot["task_action"]["action_id"] = 42
    elif mutation == "nested_request_malformed":
        snapshot["task_action"]["request_hash"] = "not-a-hash"
    elif mutation == "not_found":
        snapshot["found"] = False
    else:
        snapshot["state_valid"] = False
    monkeypatch.setattr(
        task_service,
        "SelfHostedTaskService",
        lambda: SimpleNamespace(get_task_snapshot=lambda *_a, **_k: snapshot),
    )
    from nexus.orchestrator.execution_readiness import _canonical_replay_observation

    observation = _canonical_replay_observation(
        _request(
            task_campaign_goal_identity="goal-test", execution_contract_kind="TRACKED_TASK_CARD"
        )
    )
    assert observation.blocker_code is ExecutionReadinessBlockerCode.SEMANTIC_REPLAY_FENCE


def test_material_replay_valid_identity_passes(monkeypatch):
    import nexus.orchestrator.self_hosted_task_service as task_service

    snapshot = {
        "task_id": "goal-test",
        "attempt_id": "attempt-1",
        "action_id": "action-1",
        "request_hash": "a" * 64,
        "status": "READY",
        "task_action": {
            "task_id": "goal-test",
            "action_id": "action-1",
            "request_hash": "a" * 64,
            "next_action": "none",
        },
        "found": True,
        "state_valid": True,
    }
    monkeypatch.setattr(
        task_service,
        "SelfHostedTaskService",
        lambda: SimpleNamespace(get_task_snapshot=lambda *_a, **_k: snapshot),
    )
    from nexus.orchestrator.execution_readiness import _canonical_replay_observation

    assert (
        _canonical_replay_observation(
            _request(
                task_campaign_goal_identity="goal-test", execution_contract_kind="TRACKED_TASK_CARD"
            )
        ).status
        is ExecutionReadinessStatus.PASSED
    )


def test_cline_requested_and_resolved_model_identities_pass(monkeypatch):
    import nexus.orchestrator.self_hosted_task_service as task_service

    monkeypatch.setattr(
        task_service,
        "validate_workforce_dispatch_binding",
        lambda *_a, **_k: {
            "worker_id": "worker-1",
            "provider": "cline",
            "model": "glm-5.2",
            "policy_hash": "p" * 64,
            "binding_hash": "b" * 64,
            "aggregate_binding_hash": "a" * 64,
        },
    )
    binding = _workforce_binding()
    result = _evaluate(
        _request(worker_constraints=("provider=cline",)),
        {
            ExecutionReadinessPlane.WORKFORCE: (
                PlaneObservation(
                    plane=ExecutionReadinessPlane.WORKFORCE,
                    status=ExecutionReadinessStatus.PASSED,
                    workforce_dispatch_binding=binding,
                ),
            )
        },
        provider_preflight_observer=lambda p, m: {
            **_valid_preflight(p, m),
            "requested_model": "glm-5.2",
            "resolved_model": "cline-pass/glm-5.2",
        },
    )
    assert result.plane_results[-1].status is ExecutionReadinessStatus.PASSED
    evidence = result.plane_results[-1].evidence_identities
    assert len(evidence) == 15
    assert "provider_preflight_requested_model=glm-5.2" in evidence
    assert "provider_preflight_resolved_model=cline-pass/glm-5.2" in evidence
    assert any(item.startswith("provider_preflight_digest=") for item in evidence)


@pytest.mark.parametrize(
    "override",
    [
        {"authentication_required": None},
        {"authentication_required": "false"},
        {"authenticated": "false"},
        {"resolved_model": {"model": "model-1"}},
        {"binary_path": {"path": "/bin/agy"}},
    ],
)
def test_material_workforce_preflight_identity_types_fail(monkeypatch, override):
    import nexus.orchestrator.self_hosted_task_service as task_service

    monkeypatch.setattr(
        task_service,
        "validate_workforce_dispatch_binding",
        lambda *_a, **_k: {
            "worker_id": "worker-1",
            "provider": "agy",
            "model": "model-1",
            "policy_hash": "p" * 64,
            "binding_hash": "b" * 64,
            "aggregate_binding_hash": "a" * 64,
        },
    )
    result = _evaluate(
        _request(worker_constraints=("provider=agy",)),
        {
            ExecutionReadinessPlane.WORKFORCE: (
                PlaneObservation(
                    plane=ExecutionReadinessPlane.WORKFORCE,
                    status=ExecutionReadinessStatus.PASSED,
                    workforce_dispatch_binding=_workforce_binding(),
                ),
            )
        },
        provider_preflight_observer=lambda p, m: {
            **_valid_preflight(p, m),
            **override,
        },
    )
    assert result.primary_blocker.code is ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY


def _completion_observation(**overrides: object) -> CompletionAuthorityObservation:
    base: dict[str, object] = {
        "observed_authority_kind": "NEXUS_CORE_COMPLETION",
        "observed_repository": "James3014/nexus-core",
        "observed_artifact_identity": "git:4e4c911eb83ed2eeda14caf276d3a1bd6709c6aa",
        "observed_interface_revision": "nexus-core.completion.iface.v2",
        "observed_capabilities": (
            "EVIDENCE_VERIFICATION",
            "COMPLETION_DECISION",
            "RECEIPT_BIND",
        ),
    }
    base.update(overrides)
    return CompletionAuthorityObservation(**base)  # type: ignore[arg-type]


def _required_contract(**overrides: object) -> RequiredCompletionContract:
    base: dict[str, object] = {
        "authority_kind": "NEXUS_CORE_COMPLETION",
        "repository": "James3014/nexus-core",
        "artifact_or_source_identity": "git:4e4c911eb83ed2eeda14caf276d3a1bd6709c6aa",
        "interface_revision": "nexus-core.completion.iface.v2",
        "required_capabilities": ("EVIDENCE_VERIFICATION", "COMPLETION_DECISION"),
    }
    base.update(overrides)
    return RequiredCompletionContract(**base)  # type: ignore[arg-type]


class TestReadyPath:
    def test_all_material_planes_compatible_is_ready(self) -> None:
        result = _evaluate(_request())
        assert result.outcome is ExecutionReadinessOutcome.READY_TO_EXECUTE
        assert result.primary_blocker is None
        assert result.ready_planes == tuple(ExecutionReadinessPlane)
        assert all(
            plane_result.status is ExecutionReadinessStatus.PASSED
            for plane_result in result.plane_results
        )
        assert result.request_satisfies_certification_fence()

    def test_ready_result_carries_no_certification_vocabulary(self) -> None:
        payload = _evaluate(_request()).model_dump(mode="json")
        blob = repr(payload)
        assert "VERIFIED" not in blob
        assert "CERTIFIED" not in blob
        for forbidden in ("VERIFIED", "CERTIFIED", "COMPLETE"):
            assert not any(
                identity.startswith(f"{forbidden}:")
                for plane_result in payload["plane_results"]
                for identity in plane_result["evidence_identities"]
            )

    def test_result_is_deterministic(self) -> None:
        first = _evaluate(_request())
        second = _evaluate(_request())
        assert first.result_hash() == second.result_hash()


class TestDeterministicPrecedence:
    def test_multiple_blockers_return_only_highest_precedence(self) -> None:
        overrides = {
            ExecutionReadinessPlane.GOVERNANCE: (
                _block(
                    ExecutionReadinessPlane.GOVERNANCE,
                    ExecutionReadinessBlockerCode.GOVERNANCE_PLANE_RECOVERY_REQUIRED,
                    "governance:open_recovery",
                ),
            ),
            ExecutionReadinessPlane.GATEWAY: (
                _block(
                    ExecutionReadinessPlane.GATEWAY,
                    ExecutionReadinessBlockerCode.GATEWAY_REBIND_REQUIRED,
                    "gateway:reload_required",
                ),
            ),
            ExecutionReadinessPlane.AUTHORITY: (
                _block(
                    ExecutionReadinessPlane.AUTHORITY,
                    ExecutionReadinessBlockerCode.TASK_AUTHORITY_MISSING,
                    "authority:missing",
                ),
            ),
            ExecutionReadinessPlane.WORKFORCE: (
                _block(
                    ExecutionReadinessPlane.WORKFORCE,
                    ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY,
                    "workforce:not_ready",
                ),
            ),
        }
        result = _evaluate(_request(), overrides)
        assert result.outcome is ExecutionReadinessOutcome.BLOCKED
        assert result.primary_blocker is not None
        assert (
            result.primary_blocker.code
            is ExecutionReadinessBlockerCode.GOVERNANCE_PLANE_RECOVERY_REQUIRED
        )
        assert result.primary_blocker.plane is ExecutionReadinessPlane.GOVERNANCE
        assert result.primary_blocker.next_action is (
            CanonicalNextAction.ROUTE_TO_ISSUE_806_BREAK_GLASS_RECOVERY
        )

    def test_lower_planes_stay_unproven_behind_a_higher_blocker(self) -> None:
        overrides = {
            ExecutionReadinessPlane.GOVERNANCE: (
                _block(
                    ExecutionReadinessPlane.GOVERNANCE,
                    ExecutionReadinessBlockerCode.GOVERNANCE_PLANE_RECOVERY_REQUIRED,
                ),
            ),
            ExecutionReadinessPlane.WORKFORCE: (
                _block(
                    ExecutionReadinessPlane.WORKFORCE,
                    ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY,
                ),
            ),
        }
        result = _evaluate(_request(), overrides)
        by_plane = {r.plane: r for r in result.plane_results}
        assert by_plane[ExecutionReadinessPlane.GOVERNANCE].status is (
            ExecutionReadinessStatus.BLOCKED
        )
        assert by_plane[ExecutionReadinessPlane.SOURCE].status is (
            ExecutionReadinessStatus.UNPROVEN
        )
        assert by_plane[ExecutionReadinessPlane.WORKFORCE].status is (
            ExecutionReadinessStatus.UNPROVEN
        )
        assert result.ready_planes == ()

    def test_ready_planes_recorded_above_the_primary_blocker_only(self) -> None:
        overrides = {
            ExecutionReadinessPlane.REPLAY_FENCE: (
                _block(
                    ExecutionReadinessPlane.REPLAY_FENCE,
                    ExecutionReadinessBlockerCode.SEMANTIC_REPLAY_FENCE,
                    "fence:open",
                ),
            ),
        }
        result = _evaluate(_request(), overrides)
        assert result.ready_planes == (
            ExecutionReadinessPlane.GOVERNANCE,
            ExecutionReadinessPlane.SOURCE,
            ExecutionReadinessPlane.GATEWAY,
            ExecutionReadinessPlane.HOST_BINDING,
            ExecutionReadinessPlane.ACTION_SURFACE,
            ExecutionReadinessPlane.AUTHORITY,
        )


class TestCanonicalRouting:
    def test_source_mismatch_routes_to_source_binding_action(self) -> None:
        overrides = {
            ExecutionReadinessPlane.SOURCE: (
                _block(
                    ExecutionReadinessPlane.SOURCE,
                    ExecutionReadinessBlockerCode.SOURCE_REALM_MISMATCH,
                    "source:desired_identity_unavailable",
                ),
            ),
        }
        result = _evaluate(_request(), overrides)
        assert result.primary_blocker is not None
        assert result.primary_blocker.code is ExecutionReadinessBlockerCode.SOURCE_REALM_MISMATCH
        assert result.primary_blocker.next_action is (
            CanonicalNextAction.BIND_EXACT_DESIRED_SOURCE_IDENTITY
        )

    def test_gateway_block_routes_to_526_rebind_reload(self) -> None:
        overrides = {
            ExecutionReadinessPlane.GATEWAY: (
                _block(
                    ExecutionReadinessPlane.GATEWAY,
                    ExecutionReadinessBlockerCode.GATEWAY_REBIND_REQUIRED,
                    "gateway_reload_required=true",
                ),
            ),
        }
        result = _evaluate(_request(), overrides)
        assert result.primary_blocker is not None
        assert result.primary_blocker.code is ExecutionReadinessBlockerCode.GATEWAY_REBIND_REQUIRED
        assert result.primary_blocker.next_action is (
            CanonicalNextAction.ROUTE_TO_ISSUE_526_GATEWAY_REBIND_RELOAD
        )
        assert "#526" in result.primary_blocker.message

    def test_governance_failure_routes_to_806_without_auto_break_glass(self) -> None:
        overrides = {
            ExecutionReadinessPlane.GOVERNANCE: (
                _block(
                    ExecutionReadinessPlane.GOVERNANCE,
                    ExecutionReadinessBlockerCode.GOVERNANCE_PLANE_RECOVERY_REQUIRED,
                    "governance:recovery_required",
                ),
            ),
        }
        result = _evaluate(_request(), overrides)
        assert result.primary_blocker is not None
        assert result.primary_blocker.next_action is (
            CanonicalNextAction.ROUTE_TO_ISSUE_806_BREAK_GLASS_RECOVERY
        )
        assert "#806" in result.primary_blocker.message
        assert "owner" in result.primary_blocker.message.lower()
        payload = result.model_dump(mode="json")
        blob = repr(payload)
        assert "break_glass_activate" not in blob
        assert "auto_recover" not in blob

    def test_authority_mismatch_is_not_gateway_repair(self) -> None:
        overrides = {
            ExecutionReadinessPlane.AUTHORITY: (
                _block(
                    ExecutionReadinessPlane.AUTHORITY,
                    ExecutionReadinessBlockerCode.AUTHORITY_OUT_OF_SCOPE,
                    "authority:out_of_scope",
                ),
            ),
        }
        result = _evaluate(_request(), overrides)
        assert result.primary_blocker is not None
        assert result.primary_blocker.code is ExecutionReadinessBlockerCode.AUTHORITY_OUT_OF_SCOPE
        assert (
            result.primary_blocker.next_action is CanonicalNextAction.OBTAIN_NORMAL_TASK_AUTHORITY
        )

    def test_replay_fence_requires_reconcile_not_retry(self) -> None:
        overrides = {
            ExecutionReadinessPlane.REPLAY_FENCE: (
                _block(
                    ExecutionReadinessPlane.REPLAY_FENCE,
                    ExecutionReadinessBlockerCode.SEMANTIC_REPLAY_FENCE,
                    "fence:request_seen_before",
                ),
            ),
        }
        result = _evaluate(_request(), overrides)
        assert result.primary_blocker is not None
        assert result.primary_blocker.code is ExecutionReadinessBlockerCode.SEMANTIC_REPLAY_FENCE
        assert result.primary_blocker.next_action is (
            CanonicalNextAction.RECONCILE_SAME_REQUEST_FENCE
        )
        assert "retry" in result.primary_blocker.message.lower()

    def test_workforce_evaluated_only_after_lower_planes_pass(self) -> None:
        overrides = {
            ExecutionReadinessPlane.GATEWAY: (
                _block(
                    ExecutionReadinessPlane.GATEWAY,
                    ExecutionReadinessBlockerCode.GATEWAY_REBIND_REQUIRED,
                ),
            ),
            ExecutionReadinessPlane.WORKFORCE: (
                _block(
                    ExecutionReadinessPlane.WORKFORCE,
                    ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY,
                ),
            ),
        }
        result = _evaluate(_request(), overrides)
        assert result.primary_blocker is not None
        assert result.primary_blocker.code is ExecutionReadinessBlockerCode.GATEWAY_REBIND_REQUIRED
        by_plane = {r.plane: r for r in result.plane_results}
        assert by_plane[ExecutionReadinessPlane.WORKFORCE].status is (
            ExecutionReadinessStatus.UNPROVEN
        )
        workforce_only = {
            ExecutionReadinessPlane.WORKFORCE: overrides[ExecutionReadinessPlane.WORKFORCE]
        }
        result2 = _evaluate(_request(), workforce_only)
        assert result2.primary_blocker is not None
        assert result2.primary_blocker.code is ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY


class TestCompletionOptionality:
    def test_ordinary_task_ready_without_nexus_core(self) -> None:
        request = _request()
        assert request.required_completion_contract is None
        result = _evaluate(request, completion_observation=None)
        assert result.outcome is ExecutionReadinessOutcome.READY_TO_EXECUTE

    def test_missing_observation_does_not_block_ordinary_task(self) -> None:
        result = _evaluate(_request())
        surface = next(
            r for r in result.plane_results if r.plane is ExecutionReadinessPlane.ACTION_SURFACE
        )
        assert surface.status is ExecutionReadinessStatus.PASSED
        assert surface.blocker_code is None


class TestCompletionBinding:
    def _formal_request(self) -> ExecutionReadinessRequest:
        return _request(
            execution_contract_kind="FORMAL_COMPLETION_CERTIFICATION",
            required_completion_contract=_required_contract(),
        )

    def test_exact_identity_compatible_is_plane_pass(self) -> None:
        result = _evaluate(
            self._formal_request(),
            completion_observation=_completion_observation(),
        )
        assert result.outcome is ExecutionReadinessOutcome.READY_TO_EXECUTE
        surface = next(
            r for r in result.plane_results if r.plane is ExecutionReadinessPlane.ACTION_SURFACE
        )
        assert surface.status is ExecutionReadinessStatus.PASSED

    def test_stale_artifact_identity_blocks(self) -> None:
        result = _evaluate(
            self._formal_request(),
            completion_observation=_completion_observation(
                observed_artifact_identity="git:stale000000000000000000000000000000000000000"
            ),
        )
        assert result.outcome is ExecutionReadinessOutcome.BLOCKED
        assert result.primary_blocker is not None
        assert result.primary_blocker.code is (
            ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED
        )
        assert result.primary_blocker.plane is ExecutionReadinessPlane.ACTION_SURFACE
        assert result.primary_blocker.next_action is (
            CanonicalNextAction.BIND_COMPLETION_CONTRACT_IDENTITY
        )
        assert any("stale" in identity for identity in result.primary_blocker.evidence_identities)

    def test_substituted_artifact_blocks(self) -> None:
        result = _evaluate(
            self._formal_request(),
            completion_observation=_completion_observation(
                observed_artifact_identity="substitute:abcdef0123456789"
            ),
        )
        assert result.primary_blocker is not None
        assert result.primary_blocker.code is (
            ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED
        )

    def test_incompatible_interface_blocks(self) -> None:
        result = _evaluate(
            self._formal_request(),
            completion_observation=_completion_observation(
                observed_interface_revision="nexus-core.completion.iface.v1"
            ),
        )
        assert result.primary_blocker is not None
        assert result.primary_blocker.code is (
            ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED
        )
        assert any(
            "interface" in identity for identity in result.primary_blocker.evidence_identities
        )

    def test_missing_observation_fails_closed(self) -> None:
        result = _evaluate(self._formal_request(), completion_observation=None)
        assert result.outcome is ExecutionReadinessOutcome.BLOCKED
        assert result.primary_blocker is not None
        assert result.primary_blocker.code is (
            ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED
        )
        assert any(
            "unavailable" in identity for identity in result.primary_blocker.evidence_identities
        )

    def test_missing_capability_blocks(self) -> None:
        result = _evaluate(
            self._formal_request(),
            completion_observation=_completion_observation(
                observed_capabilities=("EVIDENCE_VERIFICATION",)
            ),
        )
        assert result.primary_blocker is not None
        assert result.primary_blocker.code is (
            ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED
        )

    def test_repair_exact_binding_allows_ready(self) -> None:
        blocked = _evaluate(
            self._formal_request(),
            completion_observation=_completion_observation(
                observed_artifact_identity="git:stale000000000000000000000000000000000000000"
            ),
        )
        assert blocked.outcome is ExecutionReadinessOutcome.BLOCKED
        repaired = _evaluate(
            self._formal_request(),
            completion_observation=_completion_observation(),
        )
        assert repaired.outcome is ExecutionReadinessOutcome.READY_TO_EXECUTE
        assert repaired.primary_blocker is None

    def test_tamper_changes_completion_hash(self) -> None:
        canonical = _completion_observation().identity_digest()
        tampered = _completion_observation(
            observed_artifact_identity="git:evil0000000000000000000000000000000000000000"
        ).identity_digest()
        assert canonical != tampered


class TestAuthorityNonLeakage:
    """nexus-core identity can never exercise execution-side authorities."""

    def _formal_result(self):
        return _evaluate(
            _request(
                execution_contract_kind="FORMAL_COMPLETION_CERTIFICATION",
                required_completion_contract=_required_contract(),
            ),
            completion_observation=_completion_observation(),
        )

    def test_result_payload_never_carries_authority_abilities(self) -> None:
        payload = self._formal_result().model_dump(mode="json")
        blob = repr(payload).lower()
        for forbidden in (
            "select_route",
            "admit_worker",
            "grant_task_authority",
            "reload_gateway",
            "approve_candidate",
            "merge_pr",
            "release_",
        ):
            assert forbidden not in blob, forbidden

    def test_next_actions_never_include_execution_authorities(self) -> None:
        result = self._formal_result()
        for plane_result in result.plane_results:
            if plane_result.blocker_code is None:
                continue
        blocker = result.primary_blocker
        if blocker is not None:
            assert blocker.next_action is not None

        from nexus.contracts.execution_readiness import CanonicalNextAction as CNA

        forbidden_actions = set()
        for member in CNA:
            forbidden_actions.add(member)
        allowed = forbidden_actions  # all enum members are routing-only
        for member in allowed:
            assert "APPROVE" not in member.value
            assert "MERGE" not in member.value
            assert "RELEASE" not in member.value
            assert "GRANT" not in member.value
            assert "ADMIT" not in member.value
            # Routing-only literals may name the canonical owner they route to
            # (for example the #526 rebind/reload primitive) but must never be
            # an execution/selection verb performed by this gate.
            assert not member.value.startswith("DO_")
            assert "SELECT_ROUTE" not in member.value
            assert "TRIGGER_" not in member.value

    def test_completion_observation_has_no_authority_surface(self) -> None:
        observation = _completion_observation()
        payload = observation.to_observation_payload()
        assert set(payload) == {
            "completion_observed_authority_kind",
            "completion_observed_repository",
            "completion_observed_artifact_identity",
            "completion_observed_interface_revision",
            "completion_observed_capabilities",
        }
        assert not hasattr(observation, "approve")
        assert not hasattr(observation, "merge")
        assert not hasattr(observation, "reload")
        assert not hasattr(observation, "select_route")
        assert not hasattr(observation, "admit_worker")
        assert not hasattr(observation, "grant")

    def test_no_fake_certification_in_blocked_result(self) -> None:
        blocked = _evaluate(
            _request(
                execution_contract_kind="FORMAL_COMPLETION_CERTIFICATION",
                required_completion_contract=_required_contract(),
            ),
            completion_observation=None,
        )
        assert blocked.outcome is ExecutionReadinessOutcome.BLOCKED
        payload = blocked.model_dump(mode="json")
        assert blocked.request_satisfies_certification_fence()
        blob = repr(payload)
        assert '"VERIFIED"' not in blob
        assert '"CERTIFIED"' not in blob
        assert '"COMPLETE"' not in blob


class TestCorrectiveFalseGreenControls:
    """Post-merge #807 F1-F4 hostile controls."""

    @staticmethod
    def _install_valid_authority(monkeypatch) -> None:
        import nexus.orchestrator.standing_grant_store as grant_store

        snapshot = {
            "schema": "nexus.standing_grant_inspection.v1",
            "status": "VALID",
            "receipt_hash": "1" * 64,
            "owner_id": "owner-james",
            "coordinator_id": "coordinator-durable",
            "repository_id": "James3014/Nexus-new",
            "canonical_remote": "https://github.com/James3014/Nexus-new.git",
            "goal_id": "goal-test",
            "allowed_actions": ["TASK_SUBMIT"],
            "expires_at": "2099-01-01T00:00:00+00:00",
        }
        monkeypatch.setattr(
            grant_store,
            "inspect_standing_grant_receipt",
            lambda **_kwargs: dict(snapshot),
        )
        monkeypatch.setattr(
            grant_store,
            "evaluate_rehydrated_durable_standing_grant",
            lambda **_kwargs: SimpleNamespace(
                outcome=SimpleNamespace(value="GRANT_MATCH"),
                mutation_authorized=True,
                context_hash="2" * 64,
                decision_hash="3" * 64,
            ),
        )

    def test_governance_default_pass_cannot_hide_broken_canonical_observer(
        self, monkeypatch
    ) -> None:
        import nexus.orchestrator.standing_grant_store as grant_store

        def broken_observer(**_kwargs):
            raise RuntimeError("governance unavailable")

        monkeypatch.setattr(grant_store, "inspect_standing_grant_receipt", broken_observer)
        result = _evaluate(_request())
        assert result.outcome is ExecutionReadinessOutcome.BLOCKED
        assert result.primary_blocker is not None
        assert result.primary_blocker.code is (
            ExecutionReadinessBlockerCode.GOVERNANCE_PLANE_RECOVERY_REQUIRED
        )

    def test_material_authority_synthetic_pass_fails_closed(self, monkeypatch) -> None:
        import nexus.orchestrator.standing_grant_store as grant_store

        monkeypatch.setattr(
            grant_store,
            "inspect_standing_grant_receipt",
            lambda **_kwargs: {
                "schema": "nexus.standing_grant_inspection.v1",
                "status": "MISSING",
            },
        )
        result = _evaluate(
            _request(task_campaign_goal_identity="goal-test"),
            {
                ExecutionReadinessPlane.AUTHORITY: (
                    _pass(
                        ExecutionReadinessPlane.AUTHORITY,
                        "authority_plane:in_process_caller_context",
                    ),
                ),
            },
        )
        assert result.outcome is ExecutionReadinessOutcome.BLOCKED
        assert result.primary_blocker is not None
        assert result.primary_blocker.code is (ExecutionReadinessBlockerCode.TASK_AUTHORITY_MISSING)

    def test_material_replay_reconcile_state_overrides_synthetic_pass(self, monkeypatch) -> None:
        import nexus.orchestrator.self_hosted_task_service as task_service

        self._install_valid_authority(monkeypatch)
        monkeypatch.setattr(
            task_service.SelfHostedTaskService,
            "get_task_snapshot",
            lambda _self, task_id, include_details=False: {
                "task_id": task_id,
                "attempt_id": "attempt-1",
                "status": "UNKNOWN_REQUIRES_RECONCILE",
                "reconciliation_required": True,
                "task_action": {"next_action": "nexus_task_reconcile"},
            },
        )
        result = _evaluate(
            _request(
                task_campaign_goal_identity="goal-test",
                execution_contract_kind="TRACKED_TASK_CARD",
                durable_coordination_scope_id="scope-test",
                durable_repository_canonical_remote="https://github.com/James3014/Nexus-new.git",
            ),
            {
                ExecutionReadinessPlane.REPLAY_FENCE: (
                    _pass(
                        ExecutionReadinessPlane.REPLAY_FENCE,
                        "replay_fence_plane:in_process_first_observation",
                    ),
                ),
            },
        )
        assert result.outcome is ExecutionReadinessOutcome.BLOCKED
        assert result.primary_blocker is not None
        assert result.primary_blocker.code is (ExecutionReadinessBlockerCode.SEMANTIC_REPLAY_FENCE)

    def test_material_workforce_env_pass_is_not_canonical_evidence(self) -> None:
        result = _evaluate(
            _request(worker_constraints=("provider=agy",)),
            {
                ExecutionReadinessPlane.WORKFORCE: (
                    _pass(
                        ExecutionReadinessPlane.WORKFORCE,
                        "NEXUS_READINESS_WORKFORCE_STATUS=PASSED",
                    ),
                ),
            },
        )
        assert result.outcome is ExecutionReadinessOutcome.BLOCKED
        assert result.primary_blocker is not None
        assert result.primary_blocker.code is ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY

    def test_material_workforce_requires_semantic_canonical_binding(self, monkeypatch) -> None:
        import nexus.orchestrator.self_hosted_task_service as task_service

        demands = {"schema": "nexus.workforce_demands.v1", "demands": [{"demand_id": "d1"}]}
        binding = {
            "planner_output": {"plan_payload": {"signal_snapshot": {"workforce_demands": demands}}},
            "workforce_demands": demands,
            "workforce_admission": {"overall_decision": "ALLOW"},
            "canonical_dispatch_envelope": {"schema": "nexus.canonical_dispatch.v1"},
            "task_id": "task-1",
            "attempt_id": "attempt-1",
            "task_card_path": "tasks/card.md",
            "task_card_hash": "c" * 64,
        }
        monkeypatch.setattr(
            task_service,
            "validate_workforce_dispatch_binding",
            lambda request, require_binding=False: {
                "worker_id": "worker-1",
                "provider": "agy",
                "model": "model-1",
                "policy_hash": "p" * 64,
                "binding_hash": "b" * 64,
                "aggregate_binding_hash": "a" * 64,
            },
        )
        result = _evaluate(
            _request(worker_constraints=("provider=agy",)),
            {
                ExecutionReadinessPlane.WORKFORCE: (
                    _pass(
                        ExecutionReadinessPlane.WORKFORCE, "NEXUS_READINESS_WORKFORCE_STATUS=PASSED"
                    ),
                )
            },
        )
        # The evaluator-only API has no typed binding channel on the legacy
        # observation, so a status/hash witness remains blocked.
        assert result.primary_blocker.code is ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY

        result = _evaluate(
            _request(worker_constraints=("provider=agy",)),
            {
                ExecutionReadinessPlane.WORKFORCE: (
                    PlaneObservation(
                        plane=ExecutionReadinessPlane.WORKFORCE,
                        status=ExecutionReadinessStatus.PASSED,
                        evidence_identities=("NEXUS_READINESS_WORKFORCE_STATUS=PASSED",),
                        workforce_dispatch_binding=binding,
                    ),
                )
            },
            provider_preflight_observer=_valid_preflight,
        )
        assert result.plane_results[-1].status is ExecutionReadinessStatus.PASSED
        assert any(
            "workforce_policy_hash=" in item
            for item in result.plane_results[-1].evidence_identities
        )
        assert all(
            "NEXUS_READINESS_WORKFORCE_STATUS=PASSED" not in item
            for item in result.plane_results[-1].evidence_identities
        )

    def test_material_workforce_hashes_alone_fail(self) -> None:
        evidence = tuple(
            f"{name}={'a' * 64}"
            for name in (
                "planner_decision_hash",
                "workforce_admission_hash",
                "provider_preflight_hash",
            )
        )
        result = _evaluate(
            _request(worker_constraints=("provider=agy",)),
            {
                ExecutionReadinessPlane.WORKFORCE: (
                    _pass(ExecutionReadinessPlane.WORKFORCE, *evidence),
                )
            },
        )
        assert result.primary_blocker.code is ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY

    def test_binding_lineage_and_validator_rejection_fail_closed(self, monkeypatch) -> None:
        import nexus.orchestrator.self_hosted_task_service as task_service

        binding = _workforce_binding()
        binding.pop("canonical_dispatch_envelope")
        called = []
        monkeypatch.setattr(
            task_service,
            "validate_workforce_dispatch_binding",
            lambda *args, **kwargs: called.append(args) or {},
        )
        result = _evaluate(
            _request(worker_constraints=("worker_id=worker-1",)),
            {
                ExecutionReadinessPlane.WORKFORCE: (
                    PlaneObservation(
                        plane=ExecutionReadinessPlane.WORKFORCE,
                        status=ExecutionReadinessStatus.PASSED,
                        workforce_dispatch_binding=binding,
                    ),
                )
            },
        )
        assert result.primary_blocker.code is ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY
        assert not called

        binding = _workforce_binding()
        binding["workforce_demands"] = {"demands": [{"demand_id": "other"}]}
        result = _evaluate(
            _request(worker_constraints=("provider=agy",)),
            {
                ExecutionReadinessPlane.WORKFORCE: (
                    PlaneObservation(
                        plane=ExecutionReadinessPlane.WORKFORCE,
                        status=ExecutionReadinessStatus.PASSED,
                        workforce_dispatch_binding=binding,
                    ),
                )
            },
        )
        assert result.primary_blocker.code is ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY
        assert not called

        binding = _workforce_binding()
        monkeypatch.setattr(
            task_service,
            "validate_workforce_dispatch_binding",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("stale/tampered")),
        )
        result = _evaluate(
            _request(worker_constraints=("provider=agy",)),
            {
                ExecutionReadinessPlane.WORKFORCE: (
                    PlaneObservation(
                        plane=ExecutionReadinessPlane.WORKFORCE,
                        status=ExecutionReadinessStatus.PASSED,
                        workforce_dispatch_binding=binding,
                    ),
                )
            },
        )
        assert result.primary_blocker.code is ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY

    def test_worker_id_and_provider_constraints_are_bound(self, monkeypatch) -> None:
        import nexus.orchestrator.self_hosted_task_service as task_service

        captured = {}

        def validate(request, *, require_binding=False):
            captured.update(request)
            assert require_binding is True
            return {
                "worker_id": "worker-1",
                "provider": "agy",
                "model": "model-1",
                "policy_hash": "p" * 64,
                "binding_hash": "b" * 64,
                "aggregate_binding_hash": "a" * 64,
            }

        monkeypatch.setattr(task_service, "validate_workforce_dispatch_binding", validate)
        binding = _workforce_binding()
        for constraint in ("worker_id=worker-1", "provider=agy"):
            result = _evaluate(
                _request(worker_constraints=(constraint,)),
                {
                    ExecutionReadinessPlane.WORKFORCE: (
                        PlaneObservation(
                            plane=ExecutionReadinessPlane.WORKFORCE,
                            status=ExecutionReadinessStatus.PASSED,
                            workforce_dispatch_binding=binding,
                        ),
                    )
                },
                provider_preflight_observer=_valid_preflight,
            )
            assert result.plane_results[-1].status is ExecutionReadinessStatus.PASSED
        result = _evaluate(
            _request(worker_constraints=("worker_id=other",)),
            {
                ExecutionReadinessPlane.WORKFORCE: (
                    PlaneObservation(
                        plane=ExecutionReadinessPlane.WORKFORCE,
                        status=ExecutionReadinessStatus.PASSED,
                        workforce_dispatch_binding=binding,
                    ),
                )
            },
        )
        assert result.primary_blocker.code is ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY
        assert captured["canonical_dispatch_envelope"] == binding["canonical_dispatch_envelope"]
        assert captured["task_id"] == "task-1"

    def test_request_required_completion_capabilities_cannot_be_substituted(self) -> None:
        result = _evaluate(
            _request(
                execution_contract_kind="FORMAL_COMPLETION_CERTIFICATION",
                required_completion_contract=_required_contract(),
            ),
            completion_observation=_completion_observation(
                observed_capabilities=(
                    "COMPLETION_VERDICT",
                    "EVIDENCE_VERIFY",
                    "RECEIPT_BIND",
                )
            ),
        )
        assert result.outcome is ExecutionReadinessOutcome.BLOCKED
        assert result.primary_blocker is not None
        assert result.primary_blocker.code is (
            ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED
        )

    def test_repository_owner_name_must_match_physical_repository(self, monkeypatch) -> None:
        import nexus.orchestrator.execution_readiness as readiness_module

        monkeypatch.setattr(
            readiness_module,
            "_physical_repository_id",
            lambda: "James3014/Nexus-new",
        )
        observation = GatewayReadinessObservation(
            gateway_instance_id="gateway-test",
            observed_repo_head="a" * 40,
            observed_repo_tree="b" * 40,
            observed_runtime_sha256="c" * 64,
            runtime_sha256_at_start="c" * 64,
            tool_manifest_revision="manifest-test",
            full_tool_schema_hash="d" * 64,
            permission_policy_hash="e" * 64,
            reload_required=False,
        )
        result = evaluate_source_binding(
            _request(repository_owner="ForeignOwner"),
            observation,
        )
        assert result.status is ExecutionReadinessStatus.BLOCKED
        assert result.blocker_code is ExecutionReadinessBlockerCode.SOURCE_REALM_MISMATCH

    @pytest.mark.parametrize(
        "remote, expected",
        [
            ("https://github.com/James3014/Nexus-new.git", "James3014/Nexus-new"),
            ("https://github.com/_owner/.repo", "_owner/.repo"),
            ("https://github.com/James3014/Nexus-new", "James3014/Nexus-new"),
            ("git@github.com:James3014/Nexus-new.git", "James3014/Nexus-new"),
            ("ssh://git@github.com/James3014/Nexus-new.git", "James3014/Nexus-new"),
            ("https://github.com/James3014/repo.git.git", "James3014/repo.git"),
        ],
    )
    def test_physical_repository_id_accepts_supported_github_remotes(
        self, monkeypatch, remote, expected
    ) -> None:
        import nexus.orchestrator.execution_readiness as readiness_module

        monkeypatch.setattr(
            readiness_module.subprocess,
            "run",
            lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=remote + "\n"),
        )

        assert _physical_repository_id() == expected

    @pytest.mark.parametrize(
        "remote",
        [
            "https://notgithub.com/James3014/Nexus-new.git",
            "https://example.invalid/github.com/James3014/Nexus-new.git",
            "https://evil.github.com/James3014/Nexus-new.git",
            "https://github.com.evil/James3014/Nexus-new.git",
            "https://github.com/James3014/Nexus-new.git/extra",
            "https://github.com/James3014/Nexus-new.git?ref=main",
            "https://github.com/James3014/Nexus-new.git#fragment",
            "https://user@github.com/James3014/Nexus-new.git",
            "git@github.com:James3014/Nexus-new.git/extra",
            "ssh://other@github.com/James3014/Nexus-new.git",
            "ssh://git@github.com/James3014/../Nexus-new.git",
            "https://github.com/../Nexus-new.git",
            "https://github.com/James3014/..",
            "https://github.com/James3014/..git",
            "https://github.com/James3014/...git",
            " git@github.com:James3014/Nexus-new.git",
            "",
        ],
    )
    def test_physical_repository_id_rejects_malformed_or_noncanonical_remotes(
        self, monkeypatch, remote
    ) -> None:
        import nexus.orchestrator.execution_readiness as readiness_module

        monkeypatch.setattr(
            readiness_module.subprocess,
            "run",
            lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=remote),
        )

        assert _physical_repository_id() == ""

    def test_malformed_physical_remote_blocks_source_binding(self, monkeypatch) -> None:
        import nexus.orchestrator.execution_readiness as readiness_module

        monkeypatch.setattr(
            readiness_module.subprocess,
            "run",
            lambda *_args, **_kwargs: SimpleNamespace(
                returncode=0,
                stdout="https://github.com.evil/James3014/Nexus-new.git\n",
            ),
        )
        observation = GatewayReadinessObservation(
            gateway_instance_id="gateway-test",
            observed_repo_head="a" * 40,
            observed_repo_tree="b" * 40,
            observed_runtime_sha256="c" * 64,
            runtime_sha256_at_start="c" * 64,
            tool_manifest_revision="manifest-test",
            full_tool_schema_hash="d" * 64,
            permission_policy_hash="e" * 64,
            reload_required=False,
        )

        result = evaluate_source_binding(
            _request(repository_owner="James3014"),
            observation,
        )

        assert result.status is ExecutionReadinessStatus.BLOCKED
        assert result.blocker_code is ExecutionReadinessBlockerCode.SOURCE_BINDING_REQUIRED

    def test_ready_result_replaces_legacy_default_evidence(self) -> None:
        result = _evaluate(_request())
        evidence = {
            identity for item in result.plane_results for identity in item.evidence_identities
        }
        assert "governance_plane:default_no_open_recovery" not in evidence
        assert "authority_plane:in_process_caller_context" not in evidence
        assert "replay_fence_plane:in_process_first_observation" not in evidence
        assert "NEXUS_READINESS_WORKFORCE_STATUS=PASSED" not in evidence
