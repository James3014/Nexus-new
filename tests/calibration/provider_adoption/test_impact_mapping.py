from pathlib import Path

from scripts.ops.select_tests import load_impact_rules, select_target_details


def test_provider_adoption_calibration_maps_exact_oracles_without_fallback():
    details = select_target_details(
        [
            "nexus/calibration/provider_adoption/orchestrator.py",
            "nexus/calibration/provider_adoption/cohort.py",
        ],
        load_impact_rules(),
        index_path=Path("/tmp/missing-provider-adoption-impact-index.json"),
        history_path=Path("/tmp/missing-provider-adoption-history.jsonl"),
    )

    assert details.targets == [
        "tests/calibration/provider_adoption",
        "tests/bench/test_model_calibration_plan.py",
        "tests/services/test_policy_gate.py",
    ]
    assert details.unmatched_paths == []
    assert details.fallback_used is False
    assert details.risk == "high"
    assert details.high_risk_escalated is True
    assert details.risk_reasons == ["provider_adoption_calibration_evidence_contract"]
