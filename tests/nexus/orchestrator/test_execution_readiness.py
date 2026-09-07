"""Execution Readiness evaluator tests (issue #807 G1): precedence, UNPROVEN,
canonical routing, completion binding, and the no-fake-certification fence."""

from __future__ import annotations

from datetime import datetime, timezone

from nexus.contracts.execution_readiness import (
    CanonicalNextAction,
    ExecutionReadinessBlockerCode,
    ExecutionReadinessOutcome,
    ExecutionReadinessPlane,
    ExecutionReadinessRequest,
    ExecutionReadinessStatus,
    RequiredCompletionContract,
)
from nexus.orchestrator.execution_readiness import (
    CompletionAuthorityObservation,
    PlaneObservation,
    evaluate_execution_readiness,
)


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
):
    observations = _all_pass()
    if overrides:
        observations.update(overrides)
    return evaluate_execution_readiness(
        request,
        observations,
        completion_observation=completion_observation,
        evaluated_at=datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc),
    )


def _completion_observation(**overrides: object) -> CompletionAuthorityObservation:
    base: dict[str, object] = {
        "observed_authority_kind": "NEXUS_CORE_COMPLETION",
        "observed_repository": "James3014/nexus-core",
        "observed_artifact_identity": "git:4e4c911eb83ed2eeda14caf276d3a1bd6709c6aa",
        "observed_interface_revision": "nexus-core.completion.iface.v2",
        "observed_capabilities": (
            "COMPLETION_VERDICT",
            "EVIDENCE_VERIFY",
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
        assert result.primary_blocker.next_action is CanonicalNextAction.OBTAIN_NORMAL_TASK_AUTHORITY

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
            r
            for r in result.plane_results
            if r.plane is ExecutionReadinessPlane.ACTION_SURFACE
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
        assert any(
            "stale" in identity
            for identity in result.primary_blocker.evidence_identities
        )

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
            "interface" in identity
            for identity in result.primary_blocker.evidence_identities
        )

    def test_missing_observation_fails_closed(self) -> None:
        result = _evaluate(self._formal_request(), completion_observation=None)
        assert result.outcome is ExecutionReadinessOutcome.BLOCKED
        assert result.primary_blocker is not None
        assert result.primary_blocker.code is (
            ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED
        )
        assert any(
            "unavailable" in identity
            for identity in result.primary_blocker.evidence_identities
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
