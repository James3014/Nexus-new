from __future__ import annotations

from nexus.services.local_heal.capability_runtime_policy import build_local_heal_runtime_policy


def test_build_runtime_policy_disabled_by_default() -> None:
    policy = build_local_heal_runtime_policy(route_context={}, executor_controls={})
    assert policy.enable_pipeline is False
    assert policy.mutation_allowed is False
    assert policy.public_claim_allowed is False
    assert policy.production_ready is False
    assert policy.model_call_allowed is False
    assert policy.provider_call_allowed is False
    assert policy.network_allowed is False
    assert policy.dry_run is True


def test_build_runtime_policy_enabled_by_env() -> None:
    route_context = {
        "signal_snapshot": {
            "enable_pipeline": True,
            "mutation_allowed": True,
        }
    }
    policy = build_local_heal_runtime_policy(route_context=route_context, executor_controls={})
    assert policy.enable_pipeline is True
    assert policy.mutation_allowed is True
    assert policy.public_claim_allowed is False
