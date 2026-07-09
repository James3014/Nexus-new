from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexus.services.local_heal.p3_provider_contract import (
    P3ProviderRequest,
    P3ProviderResponse,
    build_p3_provider_request,
    process_p3_provider_request,
    p3_provider_request_to_dict,
    p3_provider_response_to_dict,
)
from nexus.services.local_heal.p3_runtime_guard import (
    P3RuntimeGuard,
    compute_p3_runtime_guard,
    p3_runtime_guard_to_dict,
)


@dataclass(frozen=True)
class P3RouteProviderAdapterResult:
    """P3-K4: Route-to-provider adapter stub.

    Pure adapter: maps P3 shadow route/diagnosis metadata into provider dry-run request.
    Does not call provider. Does not invoke network.
    """
    adapter_version: str
    adapter_authority: str
    request_built: bool
    provider_request: P3ProviderRequest | None
    provider_response: P3ProviderResponse | None
    intended_topology: str
    task_difficulty: str
    env_guard_present: bool
    dry_run: bool
    provider_invoked: bool
    network_invoked: bool
    runtime_behavior_changed: bool
    full_verifier_required: bool
    claim_gate_required: bool
    public_claim_allowed: bool
    blocked_reasons: list[str]


def compute_route_provider_adapter(
    route_metadata: dict[str, Any],
    diagnosis_metadata: dict[str, Any] | None = None,
    guard_state: str = "shadow_only",
    env_guard_override: bool | None = None,
) -> P3RouteProviderAdapterResult:
    """Compute route-to-provider adapter result.

    Pure adapter: no provider call, no network, no runtime mutation.
    """
    topology = str(route_metadata.get("p3_intended_topology", "") or "")
    difficulty = str(route_metadata.get("p3_task_difficulty", "") or "")
    compact_prompt_hash = str(diagnosis_metadata.get("p3_diagnosis_compact_prompt_hash", "") or "") if diagnosis_metadata else ""

    guard = compute_p3_runtime_guard(requested_state=guard_state, env_guard_override=env_guard_override)
    env_guard_present = guard.env_guard_present

    blocked_reasons = []

    if topology == "local_only" or not topology:
        blocked_reasons.append("topology_local_only_no_provider_needed")
        return P3RouteProviderAdapterResult(
            adapter_version="1.0",
            adapter_authority="stub_only",
            request_built=False,
            provider_request=None,
            provider_response=None,
            intended_topology=topology,
            task_difficulty=difficulty,
            env_guard_present=env_guard_present,
            dry_run=True,
            provider_invoked=False,
            network_invoked=False,
            runtime_behavior_changed=False,
            full_verifier_required=True,
            claim_gate_required=True,
            public_claim_allowed=False,
            blocked_reasons=blocked_reasons,
        )

    if not env_guard_present:
        blocked_reasons.append("env_guard_missing")

    if not compact_prompt_hash:
        blocked_reasons.append("compact_prompt_hash_missing")

    request = build_p3_provider_request(
        compact_prompt_hash=compact_prompt_hash,
        task_difficulty=difficulty,
        intended_topology=topology,
        env_guard_present=env_guard_present,
        dry_run=True,
    )

    response = process_p3_provider_request(request)

    if response.blocked_reason:
        blocked_reasons.append(response.blocked_reason)

    return P3RouteProviderAdapterResult(
        adapter_version="1.0",
        adapter_authority="stub_only",
        request_built=True,
        provider_request=request,
        provider_response=response,
        intended_topology=topology,
        task_difficulty=difficulty,
        env_guard_present=env_guard_present,
        dry_run=True,
        provider_invoked=False,
        network_invoked=False,
        runtime_behavior_changed=False,
        full_verifier_required=True,
        claim_gate_required=True,
        public_claim_allowed=False,
        blocked_reasons=blocked_reasons,
    )


def p3_adapter_to_dict(result: P3RouteProviderAdapterResult) -> dict[str, Any]:
    """Convert P3RouteProviderAdapterResult to JSON-serializable dict."""
    d = {
        "p3_adapter_version": result.adapter_version,
        "p3_adapter_authority": result.adapter_authority,
        "p3_adapter_request_built": result.request_built,
        "p3_adapter_intended_topology": result.intended_topology,
        "p3_adapter_task_difficulty": result.task_difficulty,
        "p3_adapter_env_guard_present": result.env_guard_present,
        "p3_adapter_dry_run": result.dry_run,
        "p3_adapter_provider_invoked": result.provider_invoked,
        "p3_adapter_network_invoked": result.network_invoked,
        "p3_adapter_runtime_behavior_changed": result.runtime_behavior_changed,
        "p3_adapter_full_verifier_required": result.full_verifier_required,
        "p3_adapter_claim_gate_required": result.claim_gate_required,
        "p3_adapter_public_claim_allowed": result.public_claim_allowed,
        "p3_adapter_blocked_reasons": result.blocked_reasons,
    }
    if result.provider_request:
        d["p3_adapter_provider_request"] = p3_provider_request_to_dict(result.provider_request)
    if result.provider_response:
        d["p3_adapter_provider_response"] = p3_provider_response_to_dict(result.provider_response)
    return d
