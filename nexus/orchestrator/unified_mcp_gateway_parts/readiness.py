"""In-process readiness observation helpers of the unified MCP gateway (G2 split, Issue #2439).

Moved from ``nexus/orchestrator/unified_mcp_gateway.py`` with AST-identical bodies, except
that ``GatewayInputError`` (defined in the gateway) is resolved at call time through
``_gateway()``; the gateway re-exports every name, so ``unified_mcp_gateway.X`` keeps
resolving.
"""

from __future__ import annotations

import importlib
import os

from nexus.contracts.execution_readiness import (
    COMPLETION_AUTHORITY_KIND,
    HOST_GATEWAY_SERVICE_LABEL,
    ExecutionReadinessBlockerCode,
    ExecutionReadinessPlane,
    ExecutionReadinessRequest,
    ExecutionReadinessStatus,
)
from nexus.orchestrator.execution_readiness import (
    _COMPLETION_REQUIRED_CAPABILITIES,
    COMPLETION_INTERFACE_REVISION,
    COMPLETION_REPOSITORY,
    CompletionAuthorityObservation,
    GatewayReadinessObservation,
    PlaneObservation,
    evaluate_completion_contract,
    evaluate_source_binding,
)


def _gateway():
    # Late binding: the gateway imports this module at its top level, so its own
    # names are only resolvable once a helper is called.
    return importlib.import_module("nexus.orchestrator.unified_mcp_gateway")


EXECUTION_READINESS_TOOL_NAME = "nexus_execution_readiness"
# In-process preflight realm only: each status variable accepts exactly
# "PASSED" or "BLOCKED"; anything else fails closed.
_READINESS_ENV_STATUS_VARS: dict[ExecutionReadinessPlane, str] = {
    ExecutionReadinessPlane.GOVERNANCE: "NEXUS_READINESS_GOVERNANCE_STATUS",
    ExecutionReadinessPlane.AUTHORITY: "NEXUS_READINESS_AUTHORITY_STATUS",
    ExecutionReadinessPlane.REPLAY_FENCE: "NEXUS_READINESS_REPLAY_FENCE_STATUS",
    ExecutionReadinessPlane.WORKFORCE: "NEXUS_READINESS_WORKFORCE_STATUS",
}
# Planes that default to PASSED in the in-process preflight realm, each with an
# explicit evidence identity.  Source is never defaulted: it is derived from
# the exact requested commit/tree versus the canonical checkout.  Gateway,
# host-binding, and action-surface planes carry derived evidence separately.
_READINESS_DEFAULTED_PASSED_PLANES = {
    ExecutionReadinessPlane.GOVERNANCE: "governance_plane:default_no_open_recovery",
    ExecutionReadinessPlane.AUTHORITY: "authority_plane:in_process_caller_context",
    ExecutionReadinessPlane.REPLAY_FENCE: "replay_fence_plane:in_process_first_observation",
}


def _in_process_readiness_plane_observations(
    gateway_observation: GatewayReadinessObservation,
    *,
    request: ExecutionReadinessRequest,
    completion_observation: CompletionAuthorityObservation | None = None,
    required_completion_contract: object | None = None,
) -> dict[ExecutionReadinessPlane, tuple[PlaneObservation, ...]]:
    """Gather in-process plane observations for the local preflight realm.

    The gateway plane reuses the exact freshness primitives that
    ``nexus_gateway_status`` uses (same digest, same ``reload_required``
    semantics), so the readiness gate can never disagree with the running
    instance's own status payload.  Remaining env-declared planes accept
    exactly ``PASSED`` or ``BLOCKED``; anything else fails closed.
    """

    observations: dict[ExecutionReadinessPlane, tuple[PlaneObservation, ...]] = {
        ExecutionReadinessPlane.SOURCE: (evaluate_source_binding(request, gateway_observation),)
    }

    if gateway_observation.reload_required:
        observations[ExecutionReadinessPlane.GATEWAY] = (
            PlaneObservation(
                plane=ExecutionReadinessPlane.GATEWAY,
                status=ExecutionReadinessStatus.BLOCKED,
                blocker_code=ExecutionReadinessBlockerCode.GATEWAY_REBIND_REQUIRED,
                evidence_identities=gateway_observation.to_observation_payload(),  # pyright: ignore[reportArgumentType]
            ),
        )
    else:
        observations[ExecutionReadinessPlane.GATEWAY] = (
            PlaneObservation(
                plane=ExecutionReadinessPlane.GATEWAY,
                status=ExecutionReadinessStatus.PASSED,
                evidence_identities=(
                    f"gateway_instance={gateway_observation.gateway_instance_id}",
                    "gateway_reload_required=false",
                    f"gateway_runtime_sha256={gateway_observation.observed_runtime_sha256}",
                ),
            ),
        )

    observations[ExecutionReadinessPlane.HOST_BINDING] = (
        PlaneObservation(
            plane=ExecutionReadinessPlane.HOST_BINDING,
            status=ExecutionReadinessStatus.PASSED,
            evidence_identities=(f"host_binding:{HOST_GATEWAY_SERVICE_LABEL}:in_process",),
        ),
    )
    if required_completion_contract is not None:
        completion_ok, completion_code, completion_evidence = evaluate_completion_contract(
            required_completion_contract, completion_observation
        )
        surface_evidence = (
            f"action_surface:manifest={gateway_observation.tool_manifest_revision}",
            f"action_surface:schema={gateway_observation.full_tool_schema_hash}",
            f"action_surface:permission={gateway_observation.permission_policy_hash}",
        )
        if completion_ok:
            observations[ExecutionReadinessPlane.ACTION_SURFACE] = (
                PlaneObservation(
                    plane=ExecutionReadinessPlane.ACTION_SURFACE,
                    status=ExecutionReadinessStatus.PASSED,
                    evidence_identities=surface_evidence + tuple(completion_evidence),
                ),
            )
        else:
            observations[ExecutionReadinessPlane.ACTION_SURFACE] = (
                PlaneObservation(
                    plane=ExecutionReadinessPlane.ACTION_SURFACE,
                    status=ExecutionReadinessStatus.BLOCKED,
                    blocker_code=(
                        completion_code
                        or ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED
                    ),
                    evidence_identities=surface_evidence + tuple(completion_evidence),
                ),
            )
    else:
        observations[ExecutionReadinessPlane.ACTION_SURFACE] = (
            PlaneObservation(
                plane=ExecutionReadinessPlane.ACTION_SURFACE,
                status=ExecutionReadinessStatus.PASSED,
                evidence_identities=(
                    f"action_surface:manifest={gateway_observation.tool_manifest_revision}",
                    f"action_surface:schema={gateway_observation.full_tool_schema_hash}",
                    f"action_surface:permission={gateway_observation.permission_policy_hash}",
                ),
            ),
        )

    _env_declared_blockers = {
        ExecutionReadinessPlane.GOVERNANCE: (
            ExecutionReadinessBlockerCode.GOVERNANCE_PLANE_RECOVERY_REQUIRED
        ),
        ExecutionReadinessPlane.AUTHORITY: ExecutionReadinessBlockerCode.TASK_AUTHORITY_MISSING,
        ExecutionReadinessPlane.REPLAY_FENCE: ExecutionReadinessBlockerCode.SEMANTIC_REPLAY_FENCE,
        ExecutionReadinessPlane.WORKFORCE: ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY,
    }
    # Banded env statuses are processed in G0 precedence order.  An unset
    # status for a plane that has no default (workforce) is UNPROVEN whenever
    # any higher-precedence plane already observed a BLOCK, and fails closed
    # otherwise (a READY verdict can never be fabricated from missing evidence).
    for plane in tuple(_READINESS_ENV_STATUS_VARS):
        env_var = _READINESS_ENV_STATUS_VARS[plane]
        raw = os.environ.get(env_var)
        if raw is None:
            if plane is ExecutionReadinessPlane.WORKFORCE and request.workforce_dispatch_binding:
                observations[plane] = (
                    PlaneObservation(
                        plane=plane,
                        status=ExecutionReadinessStatus.PASSED,
                        evidence_identities=("workforce_plane:canonical_binding_supplied",),
                        workforce_dispatch_binding=request.workforce_dispatch_binding,
                    ),
                )
                continue
            # Workforce evidence is completed by the canonical evaluator.  A
            # missing env status must not prevent the evaluator from proving
            # the non-material case or returning WORKFORCE_NOT_READY for
            # material constraints without a typed binding.
            if plane is ExecutionReadinessPlane.WORKFORCE:
                observations[plane] = (
                    PlaneObservation(
                        plane=plane,
                        status=ExecutionReadinessStatus.PASSED,
                        evidence_identities=("workforce_plane:canonical_evaluator_pending",),
                    ),
                )
                continue
            default_identity = _READINESS_DEFAULTED_PASSED_PLANES.get(plane)
            if default_identity is not None:
                observations[plane] = (
                    PlaneObservation(
                        plane=plane,
                        status=ExecutionReadinessStatus.PASSED,
                        evidence_identities=(default_identity,),
                    ),
                )
                continue
            higher_unproven = any(
                observation.status is ExecutionReadinessStatus.BLOCKED
                for higher_plane, higher_observations in observations.items()
                for observation in higher_observations
                if higher_plane.precedence < plane.precedence
            )
            if higher_unproven:
                observations[plane] = (
                    PlaneObservation(
                        plane=plane,
                        status=ExecutionReadinessStatus.UNPROVEN,
                        evidence_identities=(),
                    ),
                )
                continue
            raise _gateway().GatewayInputError(f"{env_var} is required for in-process preflight")
        normalized = raw.strip().upper()
        if normalized == "PASSED":
            observations[plane] = (
                PlaneObservation(
                    plane=plane,
                    status=ExecutionReadinessStatus.PASSED,
                    evidence_identities=(f"{env_var}=PASSED",),
                    workforce_dispatch_binding=(
                        request.workforce_dispatch_binding
                        if plane is ExecutionReadinessPlane.WORKFORCE
                        else None
                    ),
                ),
            )
            continue
        if normalized != "BLOCKED":
            raise _gateway().GatewayInputError(f"{env_var} must be PASSED or BLOCKED")
        blocker = _env_declared_blockers.get(plane)
        if blocker is None:
            raise _gateway().GatewayInputError(f"{env_var}=BLOCKED is not evaluable in-process")
        observations[plane] = (
            PlaneObservation(
                plane=plane,
                status=ExecutionReadinessStatus.BLOCKED,
                blocker_code=blocker,
                evidence_identities=(f"{env_var}=BLOCKED",),
            ),
        )
    return observations


def _completion_authority_observation_from_environment() -> CompletionAuthorityObservation | None:
    """Read the observed completion authority identity from the environment.

    Returns ``None`` when no completion environment is configured, which is
    itself a fail-closed blocker whenever the request requires one.
    """

    artifact = os.environ.get("NEXUS_READINESS_COMPLETION_ARTIFACT_IDENTITY")
    if not artifact:
        return None
    return CompletionAuthorityObservation(
        observed_authority_kind=os.environ.get(
            "NEXUS_READINESS_COMPLETION_AUTHORITY_KIND",
            COMPLETION_AUTHORITY_KIND,
        ),
        observed_repository=os.environ.get(
            "NEXUS_READINESS_COMPLETION_REPOSITORY", COMPLETION_REPOSITORY
        ),
        observed_artifact_identity=artifact.strip(),
        observed_interface_revision=os.environ.get(
            "NEXUS_READINESS_COMPLETION_INTERFACE_REVISION",
            COMPLETION_INTERFACE_REVISION,
        ),
        observed_capabilities=tuple(
            item.strip()
            for item in os.environ.get(
                "NEXUS_READINESS_COMPLETION_CAPABILITIES",
                ",".join(_COMPLETION_REQUIRED_CAPABILITIES),
            ).split(",")
            if item.strip()
        ),
    )
