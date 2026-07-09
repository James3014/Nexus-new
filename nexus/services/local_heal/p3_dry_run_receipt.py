from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexus.services.local_heal.p3_runtime_guard import (
    P3RuntimeGuard,
    compute_p3_runtime_guard,
)
from nexus.services.local_heal.p3_route_provider_adapter import (
    P3RouteProviderAdapterResult,
    compute_route_provider_adapter,
    p3_adapter_to_dict,
)


@dataclass(frozen=True)
class P3DryRunReceipt:
    """P3-L2: Pure dry-run receipt block builder.

    Combines K2 runtime guard + K4 adapter result into one safe receipt block.
    No provider invocation, no network, no runtime mutation.
    """
    p3_l_receipt_version: str
    p3_l_enabled: bool
    p3_l_authority: str
    p3_l_runtime_state: str
    p3_l_env_guard_present: bool
    p3_l_dry_run_only: bool
    p3_l_intended_topology: str
    p3_l_task_difficulty: str
    p3_l_provider_request_built: bool
    p3_l_provider_invoked: bool
    p3_l_network_invoked: bool
    p3_l_api_key_used: bool
    p3_l_local_model_invoked: bool
    p3_l_patch_apply_invoked: bool
    p3_l_runtime_behavior_changed: bool
    p3_l_full_verifier_required: bool
    p3_l_claim_gate_required: bool
    p3_l_claim_eligible: bool
    p3_l_public_claim_allowed: bool
    p3_l_production_ready: bool
    p3_l_blocked_reasons: list[str] = field(default_factory=list)
    p3_l_receipt_complete: bool = False


def compute_p3_dry_run_receipt(
    route_metadata: dict[str, Any],
    diagnosis_metadata: dict[str, Any] | None = None,
    guard_state: str = "shadow_only",
    env_guard_override: bool | None = None,
) -> P3DryRunReceipt:
    """Compute P3 dry-run receipt block.

    Pure builder: no provider call, no network, no runtime mutation.
    """
    guard = compute_p3_runtime_guard(requested_state=guard_state, env_guard_override=env_guard_override)

    topology = str(route_metadata.get("p3_intended_topology", "") or "")
    difficulty = str(route_metadata.get("p3_task_difficulty", "") or "")

    adapter = compute_route_provider_adapter(
        route_metadata=route_metadata,
        diagnosis_metadata=diagnosis_metadata,
        guard_state=guard.runtime_state,
        env_guard_override=env_guard_override,
    )

    blocked_reasons = list(adapter.blocked_reasons)
    if guard.runtime_state in ("blocked", "rollback_required"):
        blocked_reasons.append(f"guard_state:{guard.runtime_state}")

    enabled = guard.runtime_state not in ("disabled", "blocked", "rollback_required") and guard.env_guard_present
    authority = "env_guarded_dry_run" if guard.runtime_state == "env_guarded_dry_run" and guard.env_guard_present else "shadow_only"

    local_only_or_no_topology = topology == "local_only" or not topology
    has_unsafe_blocked = any(r for r in blocked_reasons if r not in ("topology_local_only_no_provider_needed",))
    receipt_complete = (
        adapter.request_built
        or local_only_or_no_topology
    ) and not has_unsafe_blocked

    return P3DryRunReceipt(
        p3_l_receipt_version="1.0",
        p3_l_enabled=enabled,
        p3_l_authority=authority,
        p3_l_runtime_state=guard.runtime_state,
        p3_l_env_guard_present=guard.env_guard_present,
        p3_l_dry_run_only=True,
        p3_l_intended_topology=topology,
        p3_l_task_difficulty=difficulty,
        p3_l_provider_request_built=adapter.request_built,
        p3_l_provider_invoked=False,
        p3_l_network_invoked=False,
        p3_l_api_key_used=False,
        p3_l_local_model_invoked=False,
        p3_l_patch_apply_invoked=False,
        p3_l_runtime_behavior_changed=False,
        p3_l_full_verifier_required=True,
        p3_l_claim_gate_required=True,
        p3_l_claim_eligible=False,
        p3_l_public_claim_allowed=False,
        p3_l_production_ready=False,
        p3_l_blocked_reasons=blocked_reasons,
        p3_l_receipt_complete=receipt_complete,
    )


def p3_dry_run_receipt_to_dict(receipt: P3DryRunReceipt) -> dict[str, Any]:
    """Convert P3DryRunReceipt to JSON-serializable dict."""
    return {
        "p3_l_receipt_version": receipt.p3_l_receipt_version,
        "p3_l_enabled": receipt.p3_l_enabled,
        "p3_l_authority": receipt.p3_l_authority,
        "p3_l_runtime_state": receipt.p3_l_runtime_state,
        "p3_l_env_guard_present": receipt.p3_l_env_guard_present,
        "p3_l_dry_run_only": receipt.p3_l_dry_run_only,
        "p3_l_intended_topology": receipt.p3_l_intended_topology,
        "p3_l_task_difficulty": receipt.p3_l_task_difficulty,
        "p3_l_provider_request_built": receipt.p3_l_provider_request_built,
        "p3_l_provider_invoked": receipt.p3_l_provider_invoked,
        "p3_l_network_invoked": receipt.p3_l_network_invoked,
        "p3_l_api_key_used": receipt.p3_l_api_key_used,
        "p3_l_local_model_invoked": receipt.p3_l_local_model_invoked,
        "p3_l_patch_apply_invoked": receipt.p3_l_patch_apply_invoked,
        "p3_l_runtime_behavior_changed": receipt.p3_l_runtime_behavior_changed,
        "p3_l_full_verifier_required": receipt.p3_l_full_verifier_required,
        "p3_l_claim_gate_required": receipt.p3_l_claim_gate_required,
        "p3_l_claim_eligible": receipt.p3_l_claim_eligible,
        "p3_l_public_claim_allowed": receipt.p3_l_public_claim_allowed,
        "p3_l_production_ready": receipt.p3_l_production_ready,
        "p3_l_blocked_reasons": receipt.p3_l_blocked_reasons,
        "p3_l_receipt_complete": receipt.p3_l_receipt_complete,
    }
