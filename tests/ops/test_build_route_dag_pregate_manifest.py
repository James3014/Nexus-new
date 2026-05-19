from __future__ import annotations

from scripts.ops.build_route_dag_pregate_manifest import build_route_dag_pregate_manifest


def test_build_route_dag_pregate_manifest_is_read_only_and_exposes_retry_policy() -> None:
    manifest = build_route_dag_pregate_manifest(
        task_desc="Fix cross-module websocket bug with code impact and research citations",
        task_type="bug",
        route={
            "should_research": True,
            "route_features": {
                "candidate_count": 3,
                "has_hard_signal": True,
                "is_cross_module_task": True,
                "risk_score": 80,
            },
        },
        codeintel={"impact_report_present": True},
    )

    assert manifest["status"] == "PASS"
    assert manifest["source"] == "capability_planner_dry_run"
    assert manifest["runtime_dispatch_changed"] is False
    assert "artifact_gate" in manifest["fallback_policy_by_capability"]
    assert manifest["retry_policy_by_capability"]["artifact_gate"] == "no_retry_fail_closed"
    assert any(edge["to"] == "codeintel" for edge in manifest["dependency_edges"])
    assert any(edge == {"a": "codeintel", "b": "research"} for edge in manifest["parallelizable_edges"])
