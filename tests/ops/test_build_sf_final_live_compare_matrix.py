from pathlib import Path

from scripts.ops.build_sf_final_live_compare_matrix import build_sf_final_live_compare_artifacts


def test_build_sf_final_live_compare_artifacts_writes_current_candidate_pairs(tmp_path: Path):
    local_compare = {
        "compare_rows": [
            {
                "capability": "repair_loop",
                "current_primary_skill_id": "current-repair",
                "current_primary_path": "/Users/jameschen/Workspace/nexus/.agents/skills/current-repair/SKILL.md",
                "candidate_skill_id": "candidate-repair",
                "candidate_path": "/Users/jameschen/Workspace/hermes-agent/skills/candidate-repair/SKILL.md",
                "decision": "REPLACE_PRIMARY_LOCAL_CANDIDATE",
            },
            {
                "capability": "codeintel",
                "current_primary_skill_id": "current-codeintel",
                "current_primary_path": "/Users/jameschen/Workspace/nexus/.agents/skills/current-codeintel/SKILL.md",
                "candidate_skill_id": "candidate-codeintel",
                "candidate_path": "/Users/jameschen/Workspace/hermes-agent/skills/candidate-codeintel/SKILL.md",
                "decision": "KEEP_CURRENT",
            },
        ]
    }

    matrix = build_sf_final_live_compare_artifacts(
        local_compare=local_compare,
        tasks_output=tmp_path / "tasks.json",
        status_output=tmp_path / "status.json",
        matrix_output=tmp_path / "matrix.json",
    )

    assert matrix["status"] == "PASS"
    assert matrix["summary"]["row_count"] == 2
    assert [row["arm_id"] for row in matrix["rows"]] == ["current_primary_skill", "candidate_skill"]
    assert matrix["rows"][0]["skill_mount_requests"] == ["current-repair"]
    assert matrix["rows"][1]["skill_mount_requests"] == ["candidate-repair"]
    assert matrix["rows"][1]["source_type"] == "external_reference_candidate"
    assert (tmp_path / "tasks.json").exists()
    assert (tmp_path / "status.json").exists()
    assert (tmp_path / "matrix.json").exists()
