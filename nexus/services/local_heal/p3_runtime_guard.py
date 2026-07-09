from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


ALLOWED_RUNTIME_STATES = frozenset({
    "disabled",
    "shadow_only",
    "env_guarded_dry_run",
    "env_guarded_runtime_candidate",
    "blocked",
    "rollback_required",
})

ENV_GUARD_FLAG = "NEXUS_P3_CLOUD_WITH_LOCAL_ASSIST"


@dataclass(frozen=True)
class P3RuntimeGuard:
    """P3-K2: Runtime env guard contract.

    Pure contract: determines P3 runtime state without calling or mutating runtime.
    """
    guard_version: str
    runtime_state: str
    env_guard_required: bool
    env_guard_present: bool
    default_runtime_allowed: bool
    cloud_call_allowed: bool
    local_model_call_allowed: bool
    patch_apply_allowed: bool
    full_verifier_required: bool
    claim_gate_required: bool
    claim_eligible_allowed: bool
    public_claim_allowed: bool
    production_ready: bool
    runtime_behavior_change_allowed: bool
    reason: str


def _is_env_guard_present() -> bool:
    """Check if P3 env guard flag is set."""
    return bool(os.environ.get(ENV_GUARD_FLAG, ""))


def compute_p3_runtime_guard(
    *,
    requested_state: str = "shadow_only",
    env_guard_override: bool | None = None,
) -> P3RuntimeGuard:
    """Compute P3 runtime guard state.

    Pure contract: no runtime mutation, no cloud call, no local model call.
    """
    if requested_state not in ALLOWED_RUNTIME_STATES:
        return P3RuntimeGuard(
            guard_version="1.0",
            runtime_state="blocked",
            env_guard_required=False,
            env_guard_present=False,
            default_runtime_allowed=False,
            cloud_call_allowed=False,
            local_model_call_allowed=False,
            patch_apply_allowed=False,
            full_verifier_required=True,
            claim_gate_required=True,
            claim_eligible_allowed=False,
            public_claim_allowed=False,
            production_ready=False,
            runtime_behavior_change_allowed=False,
            reason=f"unknown_state:{requested_state}",
        )

    env_guard_present = env_guard_override if env_guard_override is not None else _is_env_guard_present()

    if requested_state == "disabled":
        return P3RuntimeGuard(
            guard_version="1.0",
            runtime_state="disabled",
            env_guard_required=False,
            env_guard_present=env_guard_present,
            default_runtime_allowed=False,
            cloud_call_allowed=False,
            local_model_call_allowed=False,
            patch_apply_allowed=False,
            full_verifier_required=True,
            claim_gate_required=True,
            claim_eligible_allowed=False,
            public_claim_allowed=False,
            production_ready=False,
            runtime_behavior_change_allowed=False,
            reason="p3_disabled",
        )

    if requested_state == "shadow_only":
        return P3RuntimeGuard(
            guard_version="1.0",
            runtime_state="shadow_only",
            env_guard_required=False,
            env_guard_present=env_guard_present,
            default_runtime_allowed=False,
            cloud_call_allowed=False,
            local_model_call_allowed=False,
            patch_apply_allowed=False,
            full_verifier_required=True,
            claim_gate_required=True,
            claim_eligible_allowed=False,
            public_claim_allowed=False,
            production_ready=False,
            runtime_behavior_change_allowed=False,
            reason="shadow_only_default",
        )

    if requested_state == "env_guarded_dry_run":
        if not env_guard_present:
            return P3RuntimeGuard(
                guard_version="1.0",
                runtime_state="shadow_only",
                env_guard_required=True,
                env_guard_present=False,
                default_runtime_allowed=False,
                cloud_call_allowed=False,
                local_model_call_allowed=False,
                patch_apply_allowed=False,
                full_verifier_required=True,
                claim_gate_required=True,
                claim_eligible_allowed=False,
                public_claim_allowed=False,
                production_ready=False,
                runtime_behavior_change_allowed=False,
                reason="env_guard_missing_downgraded_to_shadow_only",
            )
        return P3RuntimeGuard(
            guard_version="1.0",
            runtime_state="env_guarded_dry_run",
            env_guard_required=True,
            env_guard_present=True,
            default_runtime_allowed=False,
            cloud_call_allowed=False,
            local_model_call_allowed=False,
            patch_apply_allowed=False,
            full_verifier_required=True,
            claim_gate_required=True,
            claim_eligible_allowed=False,
            public_claim_allowed=False,
            production_ready=False,
            runtime_behavior_change_allowed=False,
            reason="env_guarded_dry_run_active",
        )

    if requested_state == "env_guarded_runtime_candidate":
        if not env_guard_present:
            return P3RuntimeGuard(
                guard_version="1.0",
                runtime_state="shadow_only",
                env_guard_required=True,
                env_guard_present=False,
                default_runtime_allowed=False,
                cloud_call_allowed=False,
                local_model_call_allowed=False,
                patch_apply_allowed=False,
                full_verifier_required=True,
                claim_gate_required=True,
                claim_eligible_allowed=False,
                public_claim_allowed=False,
                production_ready=False,
                runtime_behavior_change_allowed=False,
                reason="env_guard_missing_downgraded_to_shadow_only",
            )
        return P3RuntimeGuard(
            guard_version="1.0",
            runtime_state="env_guarded_runtime_candidate",
            env_guard_required=True,
            env_guard_present=True,
            default_runtime_allowed=False,
            cloud_call_allowed=False,
            local_model_call_allowed=False,
            patch_apply_allowed=False,
            full_verifier_required=True,
            claim_gate_required=True,
            claim_eligible_allowed=False,
            public_claim_allowed=False,
            production_ready=False,
            runtime_behavior_change_allowed=False,
            reason="env_guarded_runtime_candidate_active",
        )

    if requested_state in ("blocked", "rollback_required"):
        return P3RuntimeGuard(
            guard_version="1.0",
            runtime_state=requested_state,
            env_guard_required=False,
            env_guard_present=env_guard_present,
            default_runtime_allowed=False,
            cloud_call_allowed=False,
            local_model_call_allowed=False,
            patch_apply_allowed=False,
            full_verifier_required=True,
            claim_gate_required=True,
            claim_eligible_allowed=False,
            public_claim_allowed=False,
            production_ready=False,
            runtime_behavior_change_allowed=False,
            reason=f"{requested_state}_active",
        )

    return P3RuntimeGuard(
        guard_version="1.0",
        runtime_state="blocked",
        env_guard_required=False,
        env_guard_present=env_guard_present,
        default_runtime_allowed=False,
        cloud_call_allowed=False,
        local_model_call_allowed=False,
        patch_apply_allowed=False,
        full_verifier_required=True,
        claim_gate_required=True,
        claim_eligible_allowed=False,
        public_claim_allowed=False,
        production_ready=False,
        runtime_behavior_change_allowed=False,
        reason="fallthrough_blocked",
    )


def p3_runtime_guard_to_dict(guard: P3RuntimeGuard) -> dict[str, Any]:
    """Convert P3RuntimeGuard to JSON-serializable dict."""
    return {
        "p3_guard_version": guard.guard_version,
        "p3_runtime_state": guard.runtime_state,
        "p3_env_guard_required": guard.env_guard_required,
        "p3_env_guard_present": guard.env_guard_present,
        "p3_default_runtime_allowed": guard.default_runtime_allowed,
        "p3_cloud_call_allowed": guard.cloud_call_allowed,
        "p3_local_model_call_allowed": guard.local_model_call_allowed,
        "p3_patch_apply_allowed": guard.patch_apply_allowed,
        "p3_guard_full_verifier_required": guard.full_verifier_required,
        "p3_guard_claim_gate_required": guard.claim_gate_required,
        "p3_guard_claim_eligible_allowed": guard.claim_eligible_allowed,
        "p3_guard_public_claim_allowed": guard.public_claim_allowed,
        "p3_guard_production_ready": guard.production_ready,
        "p3_guard_runtime_behavior_change_allowed": guard.runtime_behavior_change_allowed,
        "p3_guard_reason": guard.reason,
    }
