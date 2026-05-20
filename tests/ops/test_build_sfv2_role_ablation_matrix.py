from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.build_sfv2_role_ablation_matrix import build_sfv2_role_ablation_matrix, main


def _probe() -> dict:
    return {
        "schema": "nexus.sfv2_role_ablation_probe.v1",
        "status": "PASS",
        "rows": [
            {
                "capability": "codeintel",
                "role_contribution_state": "READY_FOR_LIVE_ROLE_ABLATION",
                "arms": [
                    {
                        "arm_id": "full_assembly",
                        "dropped_role": "",
                        "skill_ids": [
                            "github6-agent-context-codeintel",
                            "sf-systematic-codeintel-first-principles-thinking-f95019ea",
                            "github9-complexity-optimizer-codeintel",
                        ],
                    },
                    {
                        "arm_id": "minus_scout",
                        "dropped_role": "Scout",
                        "skill_ids": [
                            "sf-systematic-codeintel-first-principles-thinking-f95019ea",
                            "github9-complexity-optimizer-codeintel",
                        ],
                    },
                ],
            },
            {
                "capability": "xray",
                "role_contribution_state": "NOT_APPLICABLE",
                "arms": [{"arm_id": "full_assembly", "skill_ids": ["xray"]}],
            },
        ],
    }


def test_sfv2_role_ablation_matrix_builds_runner_artifacts(tmp_path: Path) -> None:
    artifacts = build_sfv2_role_ablation_matrix(
        probe=_probe(),
        tasks_output=tmp_path / "tasks.json",
        status_output=tmp_path / "status.json",
        matrix_output=tmp_path / "matrix.json",
    )

    matrix = artifacts["matrix"]
    assert matrix["status"] == "PASS"
    assert matrix["summary"]["capability_count"] == 1
    assert matrix["summary"]["row_count"] == 2
    assert matrix["summary"]["runtime_update_allowed"] is False
    assert matrix["summary"]["public_benchmark_allowed"] is False
    assert [row["arm_id"] for row in matrix["rows"]] == ["full_assembly", "minus_scout"]
    assert matrix["rows"][0]["arm_type"] == "role_ablation"
    assert matrix["rows"][1]["dropped_role"] == "Scout"
    assert matrix["rows"][1]["runner_env"]["NEXUS_SFV2_DROPPED_ROLE"] == "Scout"
    assert json.loads(matrix["rows"][0]["runner_env"]["NEXUS_BENCH_SKILL_MOUNT_REQUESTS"]) == [
        "github6-agent-context-codeintel",
        "sf-systematic-codeintel-first-principles-thinking-f95019ea",
        "github9-complexity-optimizer-codeintel",
    ]
    assert artifacts["tasks"]["tasks"][0]["expected_capabilities"] == ["codeintel"]
    assert artifacts["tasks"]["benchmark_id"] == "nexus-sfv2-role-ablation-v1"
    assert artifacts["tasks"]["frozen"] is True
    assert artifacts["status"]["summary"]["skill_count"] == 3


def test_sfv2_role_ablation_matrix_normalizes_runner_capability_alias(tmp_path: Path) -> None:
    probe = _probe()
    probe["rows"][0]["capability"] = "governance_and_trust"

    artifacts = build_sfv2_role_ablation_matrix(
        probe=probe,
        tasks_output=tmp_path / "tasks.json",
        status_output=tmp_path / "status.json",
        matrix_output=tmp_path / "matrix.json",
    )

    task = artifacts["tasks"]["tasks"][0]
    row = artifacts["matrix"]["rows"][0]
    assert task["expected_capabilities"] == ["mempalace_gate"]
    assert row["runner_capability_id"] == "mempalace_gate"
    assert artifacts["status"]["skills"][0]["capability_mount"] == "mempalace_gate"


def test_sfv2_role_ablation_matrix_cli_writes_all_outputs(tmp_path: Path, capsys) -> None:
    probe = tmp_path / "probe.json"
    tasks = tmp_path / "tasks.json"
    status = tmp_path / "status.json"
    matrix = tmp_path / "matrix.json"
    probe.write_text(json.dumps(_probe()), encoding="utf-8")

    rc = main(
        [
            "--probe",
            str(probe),
            "--tasks-output",
            str(tasks),
            "--status-output",
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
