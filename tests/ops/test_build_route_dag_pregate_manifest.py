from __future__ import annotations

import json

from nexus.contracts.route_runtime_plan import build_route_runtime_plan_from_pregate
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
    assert manifest["evidence_seal_status"] == "PASS"
    assert manifest["evidence_hash_status"] == "PASS"
    assert manifest["partial_telemetry_detected"] is False
    assert manifest["evidence_refs"][0].startswith("route_dag_pregate:content_hash:")
    assert manifest["runtime_plan"]["schema"] == "nexus.route_runtime_plan.v1"
    assert manifest["runtime_plan"]["status"] == "PASS"
    assert manifest["runtime_plan"]["dispatch_mode"] == "read_only_plan"
    assert manifest["runtime_plan"]["runtime_dispatch_changed"] is False
    assert manifest["runtime_plan"]["claim_verdict"] == "NOT_EVALUATED"
    assert manifest["runtime_plan"]["public_benchmark_allowed"] is False
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


def test_route_dag_pregate_manifest_can_include_skeleton_lookup(tmp_path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "core.py").write_text("def target(value):\n    return value\n", encoding="utf-8")

    manifest = build_route_dag_pregate_manifest(
        task_desc="Fix target with skeleton-first context",
        task_type="bug",
        project_root=tmp_path,
        symbols=["target"],
        symbol_roots=["pkg/core.py"],
    )

    assert manifest["runtime_dispatch_changed"] is False
    assert len(manifest["code_skeleton_lookup"]) == 1
    assert manifest["code_skeleton_lookup"][0]["found"] is True
    assert manifest["code_skeleton_lookup"][0]["matches"][0]["file_path"] == "pkg/core.py"


def test_route_runtime_plan_returns_when_pregate_attempts_dispatch_or_claim() -> None:
    runtime_plan = build_route_runtime_plan_from_pregate(
        {
            "schema": "nexus.route_dag_pregate.v1",
            "status": "PASS",
            "runtime_dispatch_changed": True,
            "claim_verdict": "PASS",
            "public_benchmark_allowed": True,
            "nodes": [
                {
                    "capability": "swarm",
                    "state": "required",
                    "execution_slot": "serial_forced_swarm",
                    "required_receipts": ["swarm_receipt"],
                }
            ],
        }
    )

    assert runtime_plan["status"] == "RETURN"
    assert runtime_plan["runtime_dispatch_changed"] is False
    assert runtime_plan["claim_verdict"] == "NOT_EVALUATED"
    assert runtime_plan["public_benchmark_allowed"] is False
    assert runtime_plan["isolated_serial_capabilities"] == ["swarm"]
    assert "runtime_dispatch_changed" in runtime_plan["blockers"]
    assert "claim_verdict_evaluated_in_pregate" in runtime_plan["blockers"]
    assert "public_benchmark_allowed_in_pregate" in runtime_plan["blockers"]
