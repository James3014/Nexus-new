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

