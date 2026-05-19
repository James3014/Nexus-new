from __future__ import annotations

from nexus.core.gate_evaluator import AcceptancePolicy


def test_acceptance_policy_normalizes_percent_style_v_pass_rate() -> None:
    policy = AcceptancePolicy.from_dict({"gates": {"v_pass_rate_min": 80.0}, "health": {}})

    assert policy.v_pass_rate_min == 0.8


def test_acceptance_policy_keeps_fraction_style_v_pass_rate() -> None:
    policy = AcceptancePolicy.from_dict({"gates": {"v_pass_rate_min": 0.75}, "health": {}})

    assert policy.v_pass_rate_min == 0.75
