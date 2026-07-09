from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P3ProviderReadiness:
    """P3-M4: Provider readiness non-execution contract.

    Determines whether a future real provider could be configured,
    without invoking or importing that provider.
    """
    readiness_version: str
    provider_kind: str
    model_name: str
    provider_config_present: bool
    api_key_present: bool
    network_allowed: bool
    sdk_import_allowed: bool
    provider_invocation_allowed: bool
    dry_run_only: bool
    human_approval_required: bool
    env_guard_required: bool
    env_guard_present: bool
    full_verifier_required: bool
    claim_gate_required: bool
    public_claim_allowed: bool
    production_ready: bool
    ready_for_real_invocation: bool
    blocked_reasons: list[str] = field(default_factory=list)
    reason: str = ""


ENV_GUARD_FLAG = "NEXUS_P3_CLOUD_WITH_LOCAL_ASSIST"


def _is_env_guard_present() -> bool:
    """Check if P3 env guard flag is set."""
    return bool(os.environ.get(ENV_GUARD_FLAG, ""))


def compute_p3_provider_readiness(
    *,
    provider_kind: str = "none",
    model_name: str = "none",
    provider_config_present: bool = False,
    api_key_env_var: str = "",
    env_guard_override: bool | None = None,
) -> P3ProviderReadiness:
    """Compute provider readiness without invoking provider.

    Pure contract: no SDK import, no network, no API key read.
    """
    env_guard_present = env_guard_override if env_guard_override is not None else _is_env_guard_present()

    api_key_present = bool(api_key_env_var and os.environ.get(api_key_env_var, ""))

    blocked_reasons = []

    if not provider_config_present:
        blocked_reasons.append("provider_config_missing")

    if not env_guard_present:
        blocked_reasons.append("env_guard_missing")

    blocked_reasons.append("human_approval_required")
    blocked_reasons.append("dry_run_only")

    reason = ";".join(blocked_reasons)

    return P3ProviderReadiness(
        readiness_version="1.0",
        provider_kind=provider_kind,
        model_name=model_name,
        provider_config_present=provider_config_present,
        api_key_present=api_key_present,
        network_allowed=False,
        sdk_import_allowed=False,
        provider_invocation_allowed=False,
        dry_run_only=True,
        human_approval_required=True,
        env_guard_required=True,
        env_guard_present=env_guard_present,
        full_verifier_required=True,
        claim_gate_required=True,
        public_claim_allowed=False,
        production_ready=False,
        ready_for_real_invocation=False,
        blocked_reasons=blocked_reasons,
        reason=reason,
    )


def p3_provider_readiness_to_dict(readiness: P3ProviderReadiness) -> dict[str, Any]:
    """Convert P3ProviderReadiness to JSON-serializable dict."""
    return {
        "p3_readiness_version": readiness.readiness_version,
        "p3_readiness_provider_kind": readiness.provider_kind,
        "p3_readiness_model_name": readiness.model_name,
        "p3_readiness_provider_config_present": readiness.provider_config_present,
        "p3_readiness_api_key_present": readiness.api_key_present,
        "p3_readiness_network_allowed": readiness.network_allowed,
        "p3_readiness_sdk_import_allowed": readiness.sdk_import_allowed,
        "p3_readiness_provider_invocation_allowed": readiness.provider_invocation_allowed,
        "p3_readiness_dry_run_only": readiness.dry_run_only,
        "p3_readiness_human_approval_required": readiness.human_approval_required,
        "p3_readiness_env_guard_required": readiness.env_guard_required,
        "p3_readiness_env_guard_present": readiness.env_guard_present,
        "p3_readiness_full_verifier_required": readiness.full_verifier_required,
        "p3_readiness_claim_gate_required": readiness.claim_gate_required,
        "p3_readiness_public_claim_allowed": readiness.public_claim_allowed,
        "p3_readiness_production_ready": readiness.production_ready,
        "p3_readiness_ready_for_real_invocation": readiness.ready_for_real_invocation,
        "p3_readiness_blocked_reasons": readiness.blocked_reasons,
        "p3_readiness_reason": readiness.reason,
    }
