from __future__ import annotations

from nexus.engine.capability_router import CapabilityRouter


def test_capability_router_stacks_hyper_autoreason_ddtree_and_ultra():
    decision = CapabilityRouter().route(
        task_desc="Fix cross-module websocket timeout race in orchestrator",
        task_type="bug",
        recommended_flow="hyper_sprint",
        route_features={
            "risk_score": 85,
            "adjusted_root_cause_confidence": 0.45,
            "findings_hits": 1,
            "memory_hits": 1,
            "candidate_count": 4,
            "is_cross_module_task": True,
            "has_hard_signal": True,
        },
        target_file="nexus/engine/pipeline.py",
    )

    payload = decision.to_dict()
    assert payload["selected_capabilities"] == ["hyper_sprint", "autoreason"]
    assert payload["acceleration_layers"] == ["ddtree"]
    assert payload["governance_layers"] == ["ultra_review"]
    assert payload["stop_policy"]["type"] == "a_streak"
    assert payload["explain_caps"][0]["capability"] == "hyper_sprint"
    assert any(item["capability"] == "autoreason" and item["enabled"] for item in payload["explain_caps"])
    assert any(item["capability"] == "ultra_review" and item["enabled"] for item in payload["explain_caps"])


def test_capability_router_keeps_simple_doc_fix_light():
    decision = CapabilityRouter().route(
        task_desc="Fix typo in README",
        task_type="bug",
        recommended_flow="baseline",
        route_features={
            "risk_score": 10,
            "adjusted_root_cause_confidence": 0.95,
            "findings_hits": 0,
            "memory_hits": 0,
            "candidate_count": 1,
            "is_doc_fix": True,
        },
        target_file="README.md",
    )

    payload = decision.to_dict()
    assert payload["selected_capabilities"] == ["baseline"]
    assert payload["acceleration_layers"] == []
    assert payload["governance_layers"] == []
    assert payload["stop_policy"]["type"] == "budget"


def test_capability_router_maps_governance_and_repair_semantics():
    governance = CapabilityRouter().route(
        task_desc="Refactor credential scrubber while preserving secret redaction.",
        task_type="public_refactor",
        recommended_flow="baseline",
        route_features={"risk_score": 10, "candidate_count": 1},
        target_file="target.py",
    ).to_dict()
    repair = CapabilityRouter().route(
        task_desc="Repair a flaky-looking timeout calculation without deleting assertions.",
        task_type="public_test_repair",
        recommended_flow="baseline",
        route_features={"risk_score": 10, "candidate_count": 1},
        target_file="target.py",
    ).to_dict()

    assert "autoreason" in governance["selected_capabilities"]
    assert governance["governance_layers"] == ["ultra_review"]
    assert repair["acceleration_layers"] == []
    assert "autoreason" not in repair["selected_capabilities"]
    assert repair["stop_policy"]["type"] == "budget"


def test_capability_router_uses_candidate_factory_readiness_for_ranking_layers():
    ready = CapabilityRouter().route(
        task_desc="Repair competing timeout candidates with enough A/B alternatives.",
        task_type="public_test_repair",
        recommended_flow="hyper_sprint",
        route_features={
            "risk_score": 40,
            "candidate_count": 3,
            "candidate_factory_readiness_estimate": {
                "ready": True,
                "status": "READY",
                "estimated_candidates": 3,
            },
        },
        target_file="target.py",
    ).to_dict()

    assert "autoreason" in ready["selected_capabilities"]
    assert ready["acceleration_layers"] == ["ddtree"]
    assert ready["stop_policy"]["type"] == "a_streak"
