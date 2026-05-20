from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.build_heep_flash_nexus_compare_matrix import build_heep_flash_nexus_compare_artifacts, main


def _queue() -> dict:
    return {
        "schema": "nexus.heep_flash_nexus_live_compare_queue.v1",
        "status": "PASS",
        "rows": [
            {
                "capability": "codeintel",
                "status": "READY",
                "selected_mode": "Mode C (Swarm)",
                "baseline_arm": {
                    "arm_id": "mode_a_current_primary",
                    "mode": "Mode A (Solo)",
                    "skill_ids": ["sf2-codeintel-route-fit-spec"],
                },
                "challenger_arm": {
                    "arm_id": "heep_multi_skill",
                    "mode": "Mode C (Swarm)",
                    "skill_ids": [
                        "github6-agent-context-codeintel",
                        "sf-systematic-codeintel-first-principles-thinking-f95019ea",
                        "github9-complexity-optimizer-codeintel",
                    ],
                },
                "mat_b_gate": {
                    "schema": "nexus.heep_mat_b_gate.v1",
                    "required_kpis": [
                        "success_rate",
                        "pollution_pct",
                        "evidence_seal_count",
                        "token_delta",
                        "wall_delta",
                        "reopen_rate",
                    ],
                    "status": "PENDING_LIVE_COMPARE",
                },
            },
            {
                "capability": "hyper_sprint",
                "status": "HOLD",
                "baseline_arm": {"skill_ids": ["sf2-hyper_sprint-route-fit-spec"]},
                "challenger_arm": {"skill_ids": ["github7-fstack-implement-plan-direct-master-loop"]},
            },
        ],
    }


def test_build_heep_flash_nexus_compare_artifacts_emit_two_arms_per_ready_candidate(tmp_path: Path) -> None:
    artifacts = build_heep_flash_nexus_compare_artifacts(
        queue=_queue(),
        tasks_output=tmp_path / "tasks.json",
        status_output=tmp_path / "status.json",
        matrix_output=tmp_path / "matrix.json",
    )

    matrix = artifacts["matrix"]
    assert matrix["status"] == "PASS"
    assert matrix["summary"]["candidate_count"] == 1
    assert matrix["summary"]["row_count"] == 2
    assert [row["arm_id"] for row in matrix["rows"]] == ["mode_a_current_primary", "heep_multi_skill"]
    assert all(row["arm_type"] == "skill_ablation" for row in matrix["rows"])
    assert all(row["runner_env"]["NEXUS_HEEP_MAT_B_COMPARE"] == "1" for row in matrix["rows"])
    assert json.loads(matrix["rows"][0]["runner_env"]["NEXUS_BENCH_SKILL_MOUNT_REQUESTS"]) == [
        "sf2-codeintel-route-fit-spec"
    ]
    assert json.loads(matrix["rows"][1]["runner_env"]["NEXUS_BENCH_SKILL_MOUNT_REQUESTS"]) == [
        "github6-agent-context-codeintel",
        "sf-systematic-codeintel-first-principles-thinking-f95019ea",
        "github9-complexity-optimizer-codeintel",
    ]
    assert matrix["rows"][1]["heep_mat_b_gate"]["status"] == "PENDING_LIVE_COMPARE"
    assert matrix["summary"]["runtime_update_allowed"] is False
    assert matrix["summary"]["public_benchmark_allowed"] is False
    assert artifacts["tasks"]["tasks"][0]["success_criteria"] == "all_target_tests_pass"

    status = artifacts["status"]
    assert status["summary"]["skill_count"] == 4
    assert {row["skill_status"] for row in status["skills"]} == {"external_reference_candidate"}


def test_heep_flash_nexus_compare_cli_writes_artifacts(tmp_path: Path, capsys) -> None:
    queue = tmp_path / "queue.json"
    tasks = tmp_path / "tasks.json"
    status = tmp_path / "status.json"
    matrix = tmp_path / "matrix.json"
    queue.write_text(json.dumps(_queue()), encoding="utf-8")

    rc = main(
        [
            "--queue",
            str(queue),
            "--tasks-output",
            str(tasks),
            "--skill-status-output",
            str(status),
            "--matrix-output",
            str(matrix),
        ]
    )
    captured = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert captured["status"] == "PASS"
    assert captured["row_count"] == 2
    assert tasks.exists()
    assert status.exists()
    assert matrix.exists()


def test_heep_flash_nexus_compare_normalizes_sf_only_capability_names(tmp_path: Path) -> None:
    queue = _queue()
    queue["rows"] = [
        {
            "capability": "governance_and_trust",
            "status": "READY",
            "selected_mode": "Mode B (Dual Guard)",
            "baseline_arm": {"arm_id": "mode_a_current_primary", "mode": "Mode A (Solo)", "skill_ids": ["gov-a"]},
            "challenger_arm": {
                "arm_id": "heep_multi_skill",
                "mode": "Mode B (Dual Guard)",
                "skill_ids": ["gov-a", "gov-b"],
            },
            "mat_b_gate": {"status": "PENDING_LIVE_COMPARE"},
        }
    ]

    artifacts = build_heep_flash_nexus_compare_artifacts(
        queue=queue,
        tasks_output=tmp_path / "tasks.json",
        status_output=tmp_path / "status.json",
        matrix_output=tmp_path / "matrix.json",
    )

    task = artifacts["tasks"]["tasks"][0]
    assert task["expected_capabilities"] == ["mempalace_gate"]
    assert artifacts["matrix"]["rows"][0]["runner_capability_id"] == "mempalace_gate"


def test_heep_flash_nexus_compare_enables_swarm_executor_for_receipt_capabilities(tmp_path: Path) -> None:
    queue = _queue()
    queue["rows"] = [
        {
            "capability": "drone",
            "status": "READY",
            "baseline_arm": {
                "arm_id": "mode_a_current_primary",
                "mode": "Mode A (Solo)",
                "skill_ids": ["sf-systematic-drone-python-background-jobs-18326a62"],
            },
            "challenger_arm": {
                "arm_id": "heep_multi_skill",
                "mode": "Mode C (Swarm)",
                "skill_ids": [
                    "sf-systematic-codeintel-first-principles-thinking-f95019ea",
                    "sf-systematic-drone-python-background-jobs-18326a62",
                    "sf-systematic-artifact_gate-differential-review-461fbd0c",
                ],
            },
            "mat_b_gate": {"status": "PENDING_LIVE_COMPARE"},
        }
    ]

    artifacts = build_heep_flash_nexus_compare_artifacts(
        queue=queue,
        tasks_output=tmp_path / "tasks.json",
        status_output=tmp_path / "status.json",
        matrix_output=tmp_path / "matrix.json",
    )

    assert artifacts["tasks"]["tasks"][0]["expected_capabilities"] == ["drone"]
    assert all(row["runner_env"]["NEXUS_ENABLE_SWARM_BENCH_EXECUTOR"] == "1" for row in artifacts["matrix"]["rows"])
