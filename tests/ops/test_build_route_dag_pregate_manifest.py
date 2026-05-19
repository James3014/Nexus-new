from __future__ import annotations

import json

from scripts.ops.build_route_dag_pregate_manifest import build_route_dag_pregate_manifest, main


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


def test_route_dag_pregate_cli_can_write_to_output_dir(tmp_path, capsys) -> None:
    output_dir = tmp_path / "reports"

    rc = main(
        [
            "--task-desc",
            "Fix a small bug with code impact",
            "--task-type",
            "bug",
            "--codeintel-json",
            '{"impact_report_present": true}',
            "--output-dir",
            str(output_dir),
        ]
    )
    captured = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert captured["output"].startswith(str(output_dir))
    assert (output_dir / "NEXUS_OPT_ROUTE_DAG_PREGATE_2026-05-20.json").exists()
