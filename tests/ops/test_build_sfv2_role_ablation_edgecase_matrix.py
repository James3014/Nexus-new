from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.build_sfv2_role_ablation_edgecase_matrix import build_sfv2_role_ablation_edgecase_matrix, main


def _probe() -> dict:
    return {
        "rows": [
            {
                "capability": "codeintel",
                "arms": [
                    {"arm_id": "full_assembly", "skill_ids": ["scout", "logic", "audit"]},
                    {"arm_id": "minus_scout", "dropped_role": "Scout", "skill_ids": ["logic", "audit"]},
                    {"arm_id": "minus_logic", "dropped_role": "Logic", "skill_ids": ["scout", "audit"]},
                ],
            },
            {
                "capability": "xray",
                "arms": [
                    {"arm_id": "full_assembly", "skill_ids": ["xray-primary"]},
                    {"arm_id": "minus_primary", "dropped_role": "primary", "skill_ids": []},
                ],
            },
        ]
    }


def _rollup() -> dict:
    return {
        "capabilities": [
            {
                "capability": "codeintel",
                "interpretation": "RECEIPT_CLEAN_ROLE_REQUIREDNESS_NOT_PROVEN",
            },
            {
                "capability": "xray",
                "interpretation": "KEEP_SINGLE_PRIMARY",
            },
        ]
    }


def test_edgecase_matrix_emits_full_and_matching_minus_pairs(tmp_path: Path) -> None:
    artifacts = build_sfv2_role_ablation_edgecase_matrix(
        probe=_probe(),
        rollup=_rollup(),
        tasks_output=tmp_path / "tasks.json",
        status_output=tmp_path / "status.json",
        matrix_output=tmp_path / "matrix.json",
    )

    matrix = artifacts["matrix"]
    assert matrix["status"] == "PASS"
    assert matrix["summary"]["capability_count"] == 1
    assert matrix["summary"]["role_focus_count"] == 2
    assert matrix["summary"]["row_count"] == 4
    assert matrix["summary"]["runtime_update_allowed"] is False
    assert matrix["summary"]["public_benchmark_allowed"] is False
    assert [row["role_focus"] for row in matrix["rows"]] == ["Scout", "Scout", "Logic", "Logic"]
    assert [row["arm_id"] for row in matrix["rows"]] == [
        "full_assembly",
        "minus_scout",
        "full_assembly",
        "minus_logic",
    ]
    assert matrix["rows"][1]["runner_env"]["NEXUS_SFV2_ROLE_EDGECASE"] == "1"
    assert matrix["rows"][1]["runner_env"]["NEXUS_SFV2_ROLE_FOCUS"] == "Scout"
    assert json.loads(matrix["rows"][0]["runner_env"]["NEXUS_BENCH_SKILL_MOUNT_REQUESTS"]) == [
        "scout",
        "logic",
        "audit",
    ]


def test_edgecase_task_manifest_keeps_runner_top_fields(tmp_path: Path) -> None:
    artifacts = build_sfv2_role_ablation_edgecase_matrix(
        probe=_probe(),
        rollup=_rollup(),
        tasks_output=tmp_path / "tasks.json",
        status_output=tmp_path / "status.json",
        matrix_output=tmp_path / "matrix.json",
    )

    tasks = artifacts["tasks"]
    assert tasks["benchmark_id"] == "nexus-sfv2-role-ablation-edgecase-v1"
    assert tasks["frozen"] is True
    assert "Scout role" in tasks["tasks"][0]["task_desc"]
    assert "role_focus" not in tasks["tasks"][0]


def test_edgecase_matrix_cli_writes_all_outputs(tmp_path: Path, capsys) -> None:
    probe = tmp_path / "probe.json"
    rollup = tmp_path / "rollup.json"
    tasks = tmp_path / "tasks.json"
    status = tmp_path / "status.json"
    matrix = tmp_path / "matrix.json"
    probe.write_text(json.dumps(_probe()), encoding="utf-8")
    rollup.write_text(json.dumps(_rollup()), encoding="utf-8")

    rc = main(
        [
            "--probe",
            str(probe),
            "--rollup",
            str(rollup),
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
    assert captured["row_count"] == 4
    assert tasks.exists()
    assert status.exists()
    assert matrix.exists()
