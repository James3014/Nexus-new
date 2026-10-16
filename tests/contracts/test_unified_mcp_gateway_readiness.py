"""Characterization tests for the gateway's in-process readiness observation helpers.

Pins the current behaviour of ``_in_process_readiness_plane_observations``,
``_completion_authority_observation_from_environment`` and their constants before
they move out of ``unified_mcp_gateway.py`` (big-file split G2, Issue #2439).  Every
name is read through the gateway facade, so the tests hold before and after the move.
"""

from __future__ import annotations

import pytest

from nexus.contracts.execution_readiness import (
    COMPLETION_AUTHORITY_KIND,
    HOST_GATEWAY_SERVICE_LABEL,
    ExecutionReadinessBlockerCode,
    ExecutionReadinessPlane,
    ExecutionReadinessRequest,
    ExecutionReadinessStatus,
    RequiredCompletionContract,
)
from nexus.orchestrator import unified_mcp_gateway as gateway_module
from nexus.orchestrator.execution_readiness import (
    _COMPLETION_REQUIRED_CAPABILITIES,
    COMPLETION_INTERFACE_REVISION,
    COMPLETION_REPOSITORY,
    CompletionAuthorityObservation,
    GatewayReadinessObservation,
    evaluate_completion_contract,
)

Plane = ExecutionReadinessPlane
Status = ExecutionReadinessStatus
Blocker = ExecutionReadinessBlockerCode

STATUS_VARS = {
    Plane.GOVERNANCE: "NEXUS_READINESS_GOVERNANCE_STATUS",
    Plane.AUTHORITY: "NEXUS_READINESS_AUTHORITY_STATUS",
    Plane.REPLAY_FENCE: "NEXUS_READINESS_REPLAY_FENCE_STATUS",
    Plane.WORKFORCE: "NEXUS_READINESS_WORKFORCE_STATUS",
}
COMPLETION_VARS = (
    "NEXUS_READINESS_COMPLETION_ARTIFACT_IDENTITY",
    "NEXUS_READINESS_COMPLETION_AUTHORITY_KIND",
    "NEXUS_READINESS_COMPLETION_REPOSITORY",
    "NEXUS_READINESS_COMPLETION_INTERFACE_REVISION",
    "NEXUS_READINESS_COMPLETION_CAPABILITIES",
)
SURFACE_EVIDENCE = (
    "action_surface:manifest=manifest-rev",
    "action_surface:schema=schema-hash",
    "action_surface:permission=permission-hash",
)
BINDING = {"planner_output": {"k": "v"}}


@pytest.fixture(autouse=True)
def _clean_readiness_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (*STATUS_VARS.values(), *COMPLETION_VARS):
        monkeypatch.delenv(name, raising=False)


def _observation(*, reload_required: bool = False) -> GatewayReadinessObservation:
    return GatewayReadinessObservation(
        gateway_instance_id="instance-1",
        observed_repo_head="c" * 40,
        observed_repo_tree="d" * 40,
        observed_runtime_sha256="runtime-sha",
        runtime_sha256_at_start="runtime-start-sha",
        tool_manifest_revision="manifest-rev",
        full_tool_schema_hash="schema-hash",
        permission_policy_hash="permission-hash",
        reload_required=reload_required,
    )


def _request(*, binding: dict | None = None) -> ExecutionReadinessRequest:
    # ``model_construct`` skips the material-binding validator: the helper only
    # reads ``workforce_dispatch_binding`` and passes it through unchanged.
    return ExecutionReadinessRequest.model_construct(
        repository_owner="James3014",
        repository_name="Nexus-new",
        intended_source_commit="a" * 40,
        intended_source_tree="b" * 40,
        execution_realm="in_process_preflight",
        required_action_family="MUTATE_BOUNDED",
        execution_contract_kind="BOUNDED_DIRECT_CHANGE",
        workforce_dispatch_binding=binding,
    )


def _contract() -> RequiredCompletionContract:
    return RequiredCompletionContract(
        authority_kind=COMPLETION_AUTHORITY_KIND,
        repository=COMPLETION_REPOSITORY,
        artifact_or_source_identity="artifact-1",
        interface_revision=COMPLETION_INTERFACE_REVISION,
        required_capabilities=("COMPLETION_VERDICT",),
    )


def _observe(**kwargs):
    observation = kwargs.pop("observation", None) or _observation()
    request = kwargs.pop("request", None) or _request()
    return gateway_module._in_process_readiness_plane_observations(
        observation, request=request, **kwargs
    )


def _single(observations, plane):
    assert len(observations[plane]) == 1
    return observations[plane][0]


def test_readiness_constants_are_pinned() -> None:
    assert gateway_module.EXECUTION_READINESS_TOOL_NAME == "nexus_execution_readiness"
    assert gateway_module._READINESS_ENV_STATUS_VARS == STATUS_VARS
    assert gateway_module._READINESS_DEFAULTED_PASSED_PLANES == {
        Plane.GOVERNANCE: "governance_plane:default_no_open_recovery",
        Plane.AUTHORITY: "authority_plane:in_process_caller_context",
        Plane.REPLAY_FENCE: "replay_fence_plane:in_process_first_observation",
    }
    names = [spec["name"] for spec in gateway_module.UnifiedMCPGateway.tool_specs()]
    assert gateway_module.EXECUTION_READINESS_TOOL_NAME in names


def test_unset_env_observes_every_plane_with_default_evidence() -> None:
    observations = _observe()
    assert set(observations) == set(Plane)
    assert _single(observations, Plane.SOURCE).plane is Plane.SOURCE
    for plane, identity in gateway_module._READINESS_DEFAULTED_PASSED_PLANES.items():
        result = _single(observations, plane)
        assert (result.status, result.blocker_code, result.evidence_identities) == (
            Status.PASSED,
            None,
            (identity,),
        )
    workforce = _single(observations, Plane.WORKFORCE)
    assert workforce.status is Status.PASSED
    assert workforce.evidence_identities == ("workforce_plane:canonical_evaluator_pending",)
    assert workforce.workforce_dispatch_binding is None
    host = _single(observations, Plane.HOST_BINDING)
    assert host.status is Status.PASSED
    assert host.evidence_identities == (f"host_binding:{HOST_GATEWAY_SERVICE_LABEL}:in_process",)


def test_gateway_plane_passes_with_instance_evidence_when_no_reload_required() -> None:
    gateway = _single(_observe(), Plane.GATEWAY)
    assert gateway.status is Status.PASSED
    assert gateway.blocker_code is None
    assert gateway.evidence_identities == (
        "gateway_instance=instance-1",
        "gateway_reload_required=false",
        "gateway_runtime_sha256=runtime-sha",
    )


def test_gateway_plane_blocks_with_observation_payload_when_reload_required() -> None:
    observation = _observation(reload_required=True)
    gateway = _single(_observe(observation=observation), Plane.GATEWAY)
    assert gateway.status is Status.BLOCKED
    assert gateway.blocker_code is Blocker.GATEWAY_REBIND_REQUIRED
    assert gateway.evidence_identities == observation.to_observation_payload()


def test_action_surface_passes_with_surface_evidence_without_completion_contract() -> None:
    surface = _single(_observe(), Plane.ACTION_SURFACE)
    assert (surface.status, surface.blocker_code) == (Status.PASSED, None)
    assert surface.evidence_identities == SURFACE_EVIDENCE


def test_action_surface_blocks_when_required_completion_observation_is_missing() -> None:
    contract = _contract()
    surface = _single(_observe(required_completion_contract=contract), Plane.ACTION_SURFACE)
    _, code, evidence = evaluate_completion_contract(contract, None)
    assert surface.status is Status.BLOCKED
    assert surface.blocker_code is code is Blocker.COMPLETION_CONTRACT_BINDING_REQUIRED
    assert surface.evidence_identities == SURFACE_EVIDENCE + tuple(evidence)


def test_action_surface_passes_when_completion_observation_matches_contract() -> None:
    contract = _contract()
    completion = CompletionAuthorityObservation(
        observed_authority_kind=COMPLETION_AUTHORITY_KIND,
        observed_repository=COMPLETION_REPOSITORY,
        observed_artifact_identity="artifact-1",
        observed_interface_revision=COMPLETION_INTERFACE_REVISION,
        observed_capabilities=("COMPLETION_VERDICT", "EVIDENCE_VERIFY"),
    )
    surface = _single(
        _observe(required_completion_contract=contract, completion_observation=completion),
        Plane.ACTION_SURFACE,
    )
    ok, _, evidence = evaluate_completion_contract(contract, completion)
    assert ok is True
    assert (surface.status, surface.blocker_code) == (Status.PASSED, None)
    assert surface.evidence_identities == SURFACE_EVIDENCE + tuple(evidence)


def test_supplied_workforce_binding_passes_without_env_status() -> None:
    workforce = _single(_observe(request=_request(binding=BINDING)), Plane.WORKFORCE)
    assert workforce.status is Status.PASSED
    assert workforce.evidence_identities == ("workforce_plane:canonical_binding_supplied",)
    assert workforce.workforce_dispatch_binding == BINDING


def test_env_passed_status_is_case_and_space_insensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env_var in STATUS_VARS.values():
        monkeypatch.setenv(env_var, "  passed ")
    observations = _observe(request=_request(binding=BINDING))
    for plane, env_var in STATUS_VARS.items():
        result = _single(observations, plane)
        assert result.status is Status.PASSED
        assert result.evidence_identities == (f"{env_var}=PASSED",)
        expected_binding = BINDING if plane is Plane.WORKFORCE else None
        assert result.workforce_dispatch_binding == expected_binding


@pytest.mark.parametrize(
    ("plane", "blocker"),
    [
        (Plane.GOVERNANCE, Blocker.GOVERNANCE_PLANE_RECOVERY_REQUIRED),
        (Plane.AUTHORITY, Blocker.TASK_AUTHORITY_MISSING),
        (Plane.REPLAY_FENCE, Blocker.SEMANTIC_REPLAY_FENCE),
        (Plane.WORKFORCE, Blocker.WORKFORCE_NOT_READY),
    ],
)
def test_env_blocked_status_maps_to_the_plane_blocker(
    monkeypatch: pytest.MonkeyPatch, plane: ExecutionReadinessPlane, blocker: Blocker
) -> None:
    env_var = STATUS_VARS[plane]
    monkeypatch.setenv(env_var, "blocked")
    result = _single(_observe(), plane)
    assert (result.status, result.blocker_code) == (Status.BLOCKED, blocker)
    assert result.evidence_identities == (f"{env_var}=BLOCKED",)


def test_env_status_other_than_passed_or_blocked_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEXUS_READINESS_AUTHORITY_STATUS", "READY")
    with pytest.raises(
        gateway_module.GatewayInputError,
        match="^NEXUS_READINESS_AUTHORITY_STATUS must be PASSED or BLOCKED$",
    ):
        _observe()


def test_undefaulted_plane_without_higher_block_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(gateway_module._READINESS_DEFAULTED_PASSED_PLANES, Plane.GOVERNANCE)
    with pytest.raises(
        gateway_module.GatewayInputError,
        match="^NEXUS_READINESS_GOVERNANCE_STATUS is required for in-process preflight$",
    ):
        _observe()


def test_undefaulted_plane_below_a_blocked_plane_is_unproven(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(gateway_module._READINESS_DEFAULTED_PASSED_PLANES, Plane.AUTHORITY)
    observations = _observe(observation=_observation(reload_required=True))
    authority = _single(observations, Plane.AUTHORITY)
    assert (authority.status, authority.blocker_code, authority.evidence_identities) == (
        Status.UNPROVEN,
        None,
        (),
    )


def test_completion_observation_is_none_without_artifact_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert gateway_module._completion_authority_observation_from_environment() is None
    monkeypatch.setenv("NEXUS_READINESS_COMPLETION_ARTIFACT_IDENTITY", "")
    assert gateway_module._completion_authority_observation_from_environment() is None


def test_completion_observation_defaults_to_the_canonical_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEXUS_READINESS_COMPLETION_ARTIFACT_IDENTITY", "  artifact-1 ")
    observed = gateway_module._completion_authority_observation_from_environment()
    assert observed == CompletionAuthorityObservation(
        observed_authority_kind=COMPLETION_AUTHORITY_KIND,
        observed_repository=COMPLETION_REPOSITORY,
        observed_artifact_identity="artifact-1",
        observed_interface_revision=COMPLETION_INTERFACE_REVISION,
        observed_capabilities=tuple(_COMPLETION_REQUIRED_CAPABILITIES),
    )


def test_completion_observation_reads_every_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_READINESS_COMPLETION_ARTIFACT_IDENTITY", "artifact-2")
    monkeypatch.setenv("NEXUS_READINESS_COMPLETION_AUTHORITY_KIND", "OTHER_KIND")
    monkeypatch.setenv("NEXUS_READINESS_COMPLETION_REPOSITORY", "owner/repo")
    monkeypatch.setenv("NEXUS_READINESS_COMPLETION_INTERFACE_REVISION", "iface.v9")
    monkeypatch.setenv("NEXUS_READINESS_COMPLETION_CAPABILITIES", " A, B,, ,C ")
    observed = gateway_module._completion_authority_observation_from_environment()
    assert observed == CompletionAuthorityObservation(
        observed_authority_kind="OTHER_KIND",
        observed_repository="owner/repo",
        observed_artifact_identity="artifact-2",
        observed_interface_revision="iface.v9",
        observed_capabilities=("A", "B", "C"),
    )
