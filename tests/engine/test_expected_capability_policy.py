from __future__ import annotations

from nexus.engine.expected_capability_policy import (
    expected_capability_executor_flags,
    normalize_expected_capabilities,
    protect_expected_capability_controls,
)


def test_expected_capability_executor_flags_normalizes_common_spellings():
    assert expected_capability_executor_flags("AutoReason,ddtree ultra-review") == {
        "enable_autoreason_executor": True,
        "enable_ddtree_executor": True,
        "enable_ultra_review_dry_gate": True,
    }
    assert normalize_expected_capabilities(["claim-gate", "delivery gate"]) == {"claim_gate", "delivery_gate"}


def test_protect_expected_capability_controls_allows_gate_only_receipt_lite():
    controls, overrides = protect_expected_capability_controls(
        {
            "context_mode": "compact",
            "disable_research": True,
            "max_rounds": 1,
            "route_lane": "governance_hardened",
            "skip_llm_baseline": True,
        },
        ("claim_gate", "delivery_gate"),
    )

    assert overrides == {}
    assert controls["gate_only_receipt_lite"] is True
    assert controls["supervised_bare_first"] is True
    assert controls["allow_pre_model_deterministic_rescue"] is True
    assert "expected_capability_protection" not in controls


def test_protect_expected_capability_controls_preserves_route_oracle_receipt_lite():
    controls, overrides = protect_expected_capability_controls(
        {
            "context_mode": "compact",
            "disable_research": True,
            "max_rounds": 1,
            "route_lane": "governance_hardened_capped",
            "supervised_bare_first": True,
        },
        ("semantic_failure_sensor",),
    )

    assert overrides == {}
    assert controls["route_oracle_receipt_lite"] is True
    assert controls["allow_pre_model_deterministic_rescue"] is True
    assert "expected_capability_protection" not in controls


def test_protect_expected_capability_controls_lifts_candidate_factory_caps():
    controls, overrides = protect_expected_capability_controls(
        {
            "candidate_cap": 1,
            "context_mode": "compact",
            "disable_research": True,
            "lite_route": True,
            "supervised_bare_first": True,
        },
        ("ddtree", "ultra_review"),
    )

    assert controls["candidate_cap"] == 3
    assert controls["lite_route"] is False
    assert controls["supervised_bare_first"] is False
    assert controls["ddtree_mixed_candidate_pool"] is True
    assert controls["expected_capability_protection"] == ["ddtree", "ultra_review"]
    assert overrides["candidate_cap"] == 1
    assert overrides["lite_route"] is True
    assert overrides["supervised_bare_first"] is True


def test_protect_expected_capability_controls_requires_baseline_for_unknown_capability():
    controls, overrides = protect_expected_capability_controls(
        {
            "context_mode": "compact",
            "disable_research": True,
            "max_rounds": 1,
            "route_lane": "feature_reflex",
            "skip_llm_baseline": True,
        },
        ("judge-panel",),
    )

    assert controls["require_llm_baseline"] is True
    assert "skip_llm_baseline" not in controls
    assert controls["expected_capability_protection"] == ["judge_panel"]
    assert overrides["skip_llm_baseline"] is True
