from pathlib import Path

from nexus.learning.skill_fit_closure import read_json
from scripts.ops.build_sf_final_live_compare_matrix import build_sf_final_live_compare_artifacts


def test_build_sf_final_live_compare_artifacts_dedupes_baseline_and_keeps_all_candidates(tmp_path: Path):
    compare_report = {
        "compare_rows": [
            {
                "capability": "repair_loop",
                "baseline_arm": {"skill_ids": ["current-repair"]},
                "challenger_arm": {"skill_ids": ["current-repair", "candidate-a"]},
                "candidate_skill_id": "candidate-a",
                "candidate_role": "Logic",
                "static_fit_score": 40,
                "fit_reason": "term_hits:1",
                "canonical_source_path": "/Users/jameschen/Workspace/hermes-agent/skills/candidate-a/SKILL.md",
                "decision": "READY_FOR_LIVE_COMPARE",
            },
            {
                "capability": "repair_loop",
                "baseline_arm": {"skill_ids": ["current-repair"]},
                "challenger_arm": {"skill_ids": ["current-repair", "candidate-b"]},
                "candidate_skill_id": "candidate-b",
                "candidate_role": "Audit",
                "static_fit_score": 50,
                "fit_reason": "term_hits:2",
                "canonical_source_path": "/Users/jameschen/Workspace/nexus/.agents/skills/candidate-b/SKILL.md",
                "decision": "READY_FOR_LIVE_COMPARE",
            },
        ]
    }

    matrix = build_sf_final_live_compare_artifacts(
        compare_report=compare_report,
        tasks_output=tmp_path / "tasks.json",
        status_output=tmp_path / "status.json",
        matrix_output=tmp_path / "matrix.json",
        classification_output=tmp_path / "classification.json",
    )

    assert matrix["status"] == "PASS"
    assert matrix["summary"]["baseline_arm_count"] == 1
    assert matrix["summary"]["candidate_arm_count"] == 2
    assert matrix["summary"]["live_eligible_candidate_count"] == 2
    assert matrix["summary"]["row_count"] == 3
    assert [row["arm_id"] for row in matrix["rows"]] == ["current_primary_skill", "candidate_skill", "candidate_skill"]
    assert matrix["rows"][1]["skill_mount_requests"] == ["current-repair", "candidate-a"]
    assert matrix["rows"][2]["source_type"] == "nexus_curated_candidate"
    assert (tmp_path / "tasks.json").exists()
    assert (tmp_path / "status.json").exists()
    assert (tmp_path / "matrix.json").exists()
    classification = read_json(tmp_path / "classification.json")
    assert classification["summary"]["ready_candidate_count"] == 2
    assert {row["classification"] for row in classification["candidates"]} == {
        "LIVE_ELIGIBLE_PRIMARY_ROLE",
        "LIVE_ELIGIBLE_SUPPORT_ROLE",
    }


def test_build_sf_final_live_compare_artifacts_filters_coarse_and_mismatched_candidates(tmp_path: Path):
    compare_report = {
        "compare_rows": [
            {
                "capability": "codeintel",
                "baseline_arm": {"skill_ids": ["current-codeintel"]},
                "challenger_arm": {"skill_ids": ["current-codeintel", "candidate-a"]},
                "candidate_skill_id": "candidate-a",
                "candidate_role": "Scout",
                "static_fit_score": 40,
                "fit_reason": "coarse:research_and_source_discipline",
                "canonical_source_path": "/Users/jameschen/.agents/skills/candidate-a/SKILL.md",
                "decision": "READY_FOR_LIVE_COMPARE",
            },
            {
                "capability": "codeintel",
                "baseline_arm": {"skill_ids": ["current-codeintel"]},
                "challenger_arm": {"skill_ids": ["current-codeintel", "candidate-b"]},
                "candidate_skill_id": "candidate-b",
                "candidate_role": "Audit",
                "static_fit_score": 40,
                "fit_reason": "term_hits:1",
                "canonical_source_path": "/Users/jameschen/.agents/skills/candidate-b/SKILL.md",
                "decision": "READY_FOR_LIVE_COMPARE",
            },
        ]
    }

    matrix = build_sf_final_live_compare_artifacts(
        compare_report=compare_report,
        tasks_output=tmp_path / "tasks.json",
        status_output=tmp_path / "status.json",
        matrix_output=tmp_path / "matrix.json",
        classification_output=tmp_path / "classification.json",
    )

    assert matrix["status"] == "BLOCKED"
    assert matrix["summary"]["live_eligible_candidate_count"] == 0
    classification = read_json(tmp_path / "classification.json")
    assert [row["classification"] for row in classification["candidates"]] == [
        "FILTERED_COARSE_FIT_ONLY",
        "FILTERED_SUPPORT_ROLE_LOW_STATIC_FIT",
    ]
