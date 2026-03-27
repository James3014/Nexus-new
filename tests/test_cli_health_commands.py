from unittest.mock import MagicMock

from scripts.nexus_cli import NexusCLI


def test_cli_check_dispatches_to_service(tmp_path):
    cli = NexusCLI(project_root=tmp_path, output_dir=tmp_path / "runs")
    mock_service = MagicMock()
    mock_service.execute_self_check.return_value = type(
        "Result",
        (),
        {
            "level": "high",
            "ok": True,
            "snapshot_score": 93.33,
            "snapshot_status": "HEALTHY",
            "benchmark_avg_health": 93.33,
            "benchmark_tasks": 1,
            "notes": [],
        },
    )()
    cli._service = mock_service

    cli.run_check("high")

    mock_service.execute_self_check.assert_called_once_with(level="high")


def test_cli_self_heal_dispatches_to_service(tmp_path):
    cli = NexusCLI(project_root=tmp_path, output_dir=tmp_path / "runs")
    mock_service = MagicMock()
    mock_service.execute_self_heal.return_value = type(
        "HealResult",
        (),
        {
            "mode": "strict",
            "ok": True,
            "cycle_status": "repaired",
            "before_score": 41.0,
            "after_score": 94.0,
            "diagnosis_kind": "audit_failure",
            "after_diagnosis_kind": "healthy",
            "planned_actions": ["auto.repair.phase.r"],
            "notes": ["health_recovered"],
        },
    )()
    cli._service = mock_service

    cli.run_self_heal("strict")

    mock_service.execute_self_heal.assert_called_once_with(mode="strict")


def test_cli_health_explain_dispatches_to_service(tmp_path):
    cli = NexusCLI(project_root=tmp_path, output_dir=tmp_path / "runs")
    mock_service = MagicMock()
    mock_service.execute_health_explain.return_value = type(
        "ExplainResult",
        (),
        {
            "snapshot_score": 92.0,
            "snapshot_status": "HEALTHY",
            "pipeline_health": 90.0,
            "phase_health": {"R": 88.0},
            "anti_hallucination": {
                "last_review_status": "APPROVED",
                "patch_generated": True,
                "patch_apply_success": True,
                "proof_type": "git_diff_checksum",
                "proof_present": True,
                "phantom_success_reason": "",
            },
            "learning": {
                "frozen": False,
                "freeze_reasons": [],
                "ingest_status": "ingested",
                "curiosity_score": 35.0,
                "pattern_reuse_rate": 80.0,
                "lesson_quality": 85.0,
                "next_run_hit_rate": 82.0,
            },
            "self_healing": {
                "cycle_status": "repaired",
                "diagnosis_kind": "audit_failure",
                "after_diagnosis_kind": "healthy",
                "phase_route": ["R", "A"],
                "route_before": ["R", "A"],
                "route_after": ["A", "R"],
                "route_weights": {"R": 10.0},
                "policy_sync": "ok",
            },
            "notes": [],
        },
    )()
    cli._service = mock_service

    cli.run_health_explain("json")

    mock_service.execute_health_explain.assert_called_once_with()
