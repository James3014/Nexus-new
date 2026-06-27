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
    env: Mapping[str, str],
    executor_controls: Mapping[str, Any],
) -> LocalHealRuntimePolicy:
    enable_pipeline = env.get("NEXUS_LOCAL_HEAL_CAPABILITY_ADAPTER_ENABLE_PIPELINE") == "1"
    
    return LocalHealRuntimePolicy(
        enable_pipeline=enable_pipeline,
        mutation_allowed=False,
        public_claim_allowed=False,
        production_ready=False,
        model_call_allowed=False,
        provider_call_allowed=False,
        network_allowed=False,
        dry_run=True,
    )
