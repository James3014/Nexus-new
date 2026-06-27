from __future__ import annotations

from nexus.services.local_heal.capability_runtime_policy import build_local_heal_runtime_policy


def test_build_runtime_policy_disabled_by_default() -> None:
    policy = build_local_heal_runtime_policy(env={}, executor_controls={})
    assert policy.enable_pipeline is False
    assert policy.mutation_allowed is False
    assert policy.public_claim_allowed is False
    assert policy.production_ready is False
    assert policy.model_call_allowed is False
    assert policy.provider_call_allowed is False
    assert policy.network_allowed is False
    assert policy.dry_run is True


def test_build_runtime_policy_enabled_by_env() -> None:
    env = {"NEXUS_LOCAL_HEAL_CAPABILITY_ADAPTER_ENABLE_PIPELINE": "1"}
    policy = build_local_heal_runtime_policy(env=env, executor_controls={})
    assert policy.enable_pipeline is True
    assert policy.mutation_allowed is False
    assert policy.public_claim_allowed is False
