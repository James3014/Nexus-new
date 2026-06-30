from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class LocalHealRuntimePolicy:
    enable_pipeline: bool = False
    mutation_allowed: bool = False
    public_claim_allowed: bool = False
    production_ready: bool = False
    model_call_allowed: bool = False
    provider_call_allowed: bool = False
    network_allowed: bool = False
    dry_run: bool = True


def build_local_heal_runtime_policy(
    route_context: Mapping[str, Any],
    executor_controls: Mapping[str, Any],
) -> LocalHealRuntimePolicy:
    signal_snapshot = route_context.get("signal_snapshot", {}) if isinstance(route_context, dict) else {}
    
    if not isinstance(signal_snapshot, dict) or not signal_snapshot:
        return LocalHealRuntimePolicy(
            enable_pipeline=False,
            mutation_allowed=False,
            public_claim_allowed=False,
            production_ready=False,
            model_call_allowed=False,
            provider_call_allowed=False,
            network_allowed=False,
            dry_run=True,
        )
        
    enable_pipeline = bool(signal_snapshot.get("enable_pipeline", False))
    mutation_allowed = bool(signal_snapshot.get("mutation_allowed", False))
    public_claim_allowed = bool(signal_snapshot.get("public_claim_allowed", False))
    production_ready = bool(signal_snapshot.get("production_ready", False))
    model_call_allowed = bool(signal_snapshot.get("model_call_allowed", False))
    provider_call_allowed = bool(signal_snapshot.get("provider_call_allowed", False))
    network_allowed = bool(signal_snapshot.get("network_allowed", False))
    dry_run = bool(signal_snapshot.get("dry_run", True))
    
    return LocalHealRuntimePolicy(
        enable_pipeline=enable_pipeline,
        mutation_allowed=mutation_allowed,
        public_claim_allowed=public_claim_allowed,
        production_ready=production_ready,
        model_call_allowed=model_call_allowed,
        provider_call_allowed=provider_call_allowed,
        network_allowed=network_allowed,
        dry_run=dry_run,
    )
