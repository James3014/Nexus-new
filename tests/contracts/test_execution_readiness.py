"""Typed Execution Readiness contract tests (issue #807 G1)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from nexus.contracts.execution_readiness import (
    COMPLETION_CONTRACT_BLOCKER,
    EXECUTION_READINESS_BLOCKER_SCHEMA,
    EXECUTION_READINESS_PLANE_RESULTS_SCHEMA,
    EXECUTION_READINESS_SCHEMA,
    READY_ONLY_VOCABULARY,
    CanonicalNextAction,
    ExecutionReadinessBlocker,
    ExecutionReadinessBlockerCode,
    ExecutionReadinessOutcome,
    ExecutionReadinessPlane,
    ExecutionReadinessRequest,
    ExecutionReadinessResult,
    ExecutionReadinessStatus,
    RequiredCompletionContract,
    blocker_plane,
    blocker_precedence,
    canonical_hash,
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


def _completion_contract(**overrides: object) -> RequiredCompletionContract:
    base: dict[str, object] = {
        "authority_kind": "NEXUS_CORE_COMPLETION",
        "repository": "James3014/nexus-core",
        "artifact_or_source_identity": "git:4e4c911eb83ed2eeda14caf276d3a1bd6709c6aa",
        "interface_revision": "nexus-core.completion.iface.v2",
        "required_capabilities": ("EVIDENCE_VERIFICATION", "COMPLETION_DECISION"),
    }
    base.update(overrides)
    return RequiredCompletionContract(**base)  # type: ignore[arg-type]


class TestFrozenPrecedence:
    def test_plane_precedence_matches_g0_freeze(self) -> None:
        expected = [
            (ExecutionReadinessPlane.GOVERNANCE, 1),
            (ExecutionReadinessPlane.SOURCE, 2),
            (ExecutionReadinessPlane.GATEWAY, 3),
            (ExecutionReadinessPlane.HOST_BINDING, 4),
            (ExecutionReadinessPlane.ACTION_SURFACE, 5),
            (ExecutionReadinessPlane.AUTHORITY, 6),
            (ExecutionReadinessPlane.REPLAY_FENCE, 7),
            (ExecutionReadinessPlane.WORKFORCE, 8),
        ]
        for plane, rank in expected:
            assert plane.precedence == rank

    def test_every_blocker_code_maps_to_exactly_one_plane(self) -> None:
        for code in ExecutionReadinessBlockerCode:
            plane = blocker_plane(code)
            assert isinstance(plane, ExecutionReadinessPlane)
            assert 1 <= blocker_precedence(code) <= 8

    def test_plane5_blockers_share_plane(self) -> None:
        assert (
            blocker_plane(ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED)
            is ExecutionReadinessPlane.ACTION_SURFACE
        )
        assert (
            blocker_plane(ExecutionReadinessBlockerCode.PERMISSION_SURFACE_STALE)
            is ExecutionReadinessPlane.ACTION_SURFACE
        )


class TestRequestContract:
    def test_minimal_request_without_completion_contract(self) -> None:
        request = _request()
        assert request.required_completion_contract is None
        assert request.worker_constraints == ()
        assert len(request.request_hash()) == 64

    def test_commit_and_tree_shape_fail_closed(self) -> None:
        with pytest.raises(ValidationError):
            _request(intended_source_commit="short")
        assert _request(intended_source_tree="a" * 40).intended_source_tree == "a" * 40
        with pytest.raises(ValidationError):
            _request(intended_source_tree="a" * 64)

    def test_worker_constraints_bounded(self) -> None:
        with pytest.raises(ValidationError):
            _request(worker_constraints=("x",) * 9)
        with pytest.raises(ValidationError):
            _request(worker_constraints=("y" * 257,))

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            _request(sneaky_field="no")

    def test_completion_contract_requires_formal_execution_contract(self) -> None:
        with pytest.raises(ValidationError):
            _request(required_completion_contract=_completion_contract())
        request = _request(
            execution_contract_kind="FORMAL_COMPLETION_CERTIFICATION",
            required_completion_contract=_completion_contract(),
        )
        assert request.required_completion_contract is not None

    def test_completion_contract_authority_kind_pinned(self) -> None:
        with pytest.raises(ValidationError):
            _request(
                execution_contract_kind="FORMAL_COMPLETION_CERTIFICATION",
                required_completion_contract=_completion_contract(authority_kind="OTHER"),
            )

    def test_completion_contract_rejects_github_main_as_artifact(self) -> None:
        with pytest.raises(ValidationError):
            _request(
                execution_contract_kind="FORMAL_COMPLETION_CERTIFICATION",
                required_completion_contract=_completion_contract(
                    artifact_or_source_identity="github:main"
                ),
            )

    def test_optional_identity_fields_reject_empty(self) -> None:
        with pytest.raises(ValidationError):
            _request(task_campaign_goal_identity="   ")
        with pytest.raises(ValidationError):
            _request(desired_deployment_identity="")


class TestResultContract:
    def _blocker(self) -> ExecutionReadinessBlocker:
        return ExecutionReadinessBlocker(
            code=ExecutionReadinessBlockerCode.GATEWAY_REBIND_REQUIRED,
            plane=ExecutionReadinessPlane.GATEWAY,
            message="gateway reload required",
            evidence_identities=("gateway_reload_required=true",),
            next_action=CanonicalNextAction.ROUTE_TO_ISSUE_526_GATEWAY_REBIND_RELOAD,
        )

    def test_blocker_requires_consistent_plane(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionReadinessBlocker(
                code=ExecutionReadinessBlockerCode.GATEWAY_REBIND_REQUIRED,
                plane=ExecutionReadinessPlane.WORKFORCE,
                message="mismatched plane must be rejected",
                evidence_identities=("evidence",),
                next_action=CanonicalNextAction.ROUTE_TO_ISSUE_526_GATEWAY_REBIND_RELOAD,
            )

    def test_blocked_result_needs_exactly_one_blocker(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionReadinessResult(
                outcome=ExecutionReadinessOutcome.BLOCKED,
                request_hash="a" * 64,
                evaluated_at=datetime.now(timezone.utc),
                ready_planes=(),
                plane_results=(),
            )

    def test_no_fake_certification_vocabulary(self) -> None:
        assert set(READY_ONLY_VOCABULARY) == {"READY_TO_EXECUTE"}
        assert not {"VERIFIED", "CERTIFIED", "COMPLETE"} & set(READY_ONLY_VOCABULARY)

    def test_schema_constants_stable(self) -> None:
        assert EXECUTION_READINESS_SCHEMA == "nexus.execution_readiness.v1"
        assert EXECUTION_READINESS_PLANE_RESULTS_SCHEMA == (
            "nexus.execution_readiness_plane_results.v1"
        )
        assert EXECUTION_READINESS_BLOCKER_SCHEMA == "nexus.execution_readiness_blocker.v1"
        assert COMPLETION_CONTRACT_BLOCKER == "COMPLETION_CONTRACT_BINDING_REQUIRED"
        assert ExecutionReadinessStatus.UNPROVEN.value == "UNPROVEN"


class TestCanonicalHash:
    def test_hash_is_key_order_independent(self) -> None:
        assert canonical_hash({"b": 1, "a": 2}) == canonical_hash({"a": 2, "b": 1})

    def test_tamper_changes_hash(self) -> None:
        original = {"artifact": "git:4e4c", "interface": "v2"}
        assert canonical_hash(original) != canonical_hash({**original, "interface": "v3"})

    def test_non_serializable_fail_closed(self) -> None:
        with pytest.raises(ValueError):
            canonical_hash({"bad": object()})
