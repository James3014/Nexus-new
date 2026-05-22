from __future__ import annotations

from scripts.bench.route_execution_policy import apply_model_participation_rescue_policy


def test_model_participation_blocks_pre_model_rescue_without_cost_profile() -> None:
    result = apply_model_participation_rescue_policy(
        {"allow_pre_model_deterministic_rescue": True},
        {},
        llm_enabled=True,
        require_model_participation_env=True,
        disable_deterministic_rescue_env=False,
        allow_cost_efficiency_pre_model_rescue_env=False,
    )

    assert result.require_model_participation_for_run is True
    assert result.allow_cost_efficiency_pre_model_rescue is False
    assert result.route_cost_controls["allow_pre_model_deterministic_rescue"] is False
    assert result.route_cost_controls["require_model_participation"] is True
    assert result.route_cost_policy_overrides["allow_pre_model_deterministic_rescue"] is True


def test_cost_efficiency_profile_preserves_pre_model_rescue_under_required_participation() -> None:
    result = apply_model_participation_rescue_policy(
        {"allow_pre_model_deterministic_rescue": True},
        {},
        llm_enabled=True,
        require_model_participation_env=True,
        disable_deterministic_rescue_env=False,
        allow_cost_efficiency_pre_model_rescue_env=True,
    )

    assert result.route_cost_controls["allow_pre_model_deterministic_rescue"] is True
    assert result.route_cost_controls["cost_efficiency_pre_model_rescue_profile"] is True
    assert result.route_cost_controls["require_model_participation"] is True


def test_benchmark_disable_deterministic_rescue_wins_before_required_participation() -> None:
    result = apply_model_participation_rescue_policy(
        {"allow_pre_model_deterministic_rescue": True},
        {},
        llm_enabled=True,
        require_model_participation_env=True,
        disable_deterministic_rescue_env=True,
        allow_cost_efficiency_pre_model_rescue_env=True,
    )

    assert result.route_cost_controls["disable_deterministic_rescue"] is True
    assert result.route_cost_policy_overrides["disable_deterministic_rescue"] is True
    assert result.route_cost_controls["allow_pre_model_deterministic_rescue"] is False
    assert result.route_cost_controls["cost_efficiency_pre_model_rescue_profile"] is True


def test_model_participation_env_is_ignored_when_llm_disabled() -> None:
    result = apply_model_participation_rescue_policy(
        {"allow_pre_model_deterministic_rescue": True},
        {},
        llm_enabled=False,
        require_model_participation_env=True,
        disable_deterministic_rescue_env=True,
        allow_cost_efficiency_pre_model_rescue_env=True,
    )

    assert result.require_model_participation_for_run is False
    assert result.route_cost_controls == {"allow_pre_model_deterministic_rescue": True}
    assert result.route_cost_policy_overrides == {}
