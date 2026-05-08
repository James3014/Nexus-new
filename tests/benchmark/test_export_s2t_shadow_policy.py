from __future__ import annotations

import json
from pathlib import Path

from scripts.bench.export_s2t_shadow_policy import build_export, load_rows_from_evidence_bundle


def test_export_s2t_shadow_policy_rebuilds_rows_from_bundle_raw_files(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_path.write_text(
        json.dumps(
            {
                "task_id": "task-a",
                "mode": "with_nexus",
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "model_calls": 2,
                "total_tokens": 91000,
                "nexus_winner_source": "llm_self_heal",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    without_path.write_text(
        json.dumps(
            {
                "task_id": "task-a",
                "mode": "without_nexus",
                "status": "FAILED",
                "semantic_status": "UNVERIFIED",
                "model_calls": 1,
                "total_tokens": 30000,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    bundle = tmp_path / "evidence_bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "raw_files": {
                    "with_nexus": {"path": str(with_path)},
                    "without_nexus": {"path": str(without_path)},
                }
            }
        ),
        encoding="utf-8",
    )

    rows = load_rows_from_evidence_bundle(bundle)
    export = build_export(bundle)

    assert len(rows) == 2
    assert export["schema"] == "nexus_s2t_shadow_policy_export_v1"
    assert export["row_count"] == 2
    assert export["s2t_shadow_report"]["summary"]["self_heal_win_task_ids"] == ["task-a"]
    assert export["s2t_policy_draft"]["task_rules"]["task-a"]["recommended_action"] == "keep_strict_repair_selector"
    assert export["route_cost_policy_candidate"]["lite_route_tasks"] == []


def test_export_s2t_shadow_policy_marks_bare_verified_expensive_tasks_as_lite_candidates(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_path.write_text(
        json.dumps(
            {
                "task_id": "task-a",
                "mode": "with_nexus",
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "model_calls": 2,
                "total_tokens": 91000,
                "nexus_winner_source": "llm_self_heal",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    without_path.write_text(
        json.dumps(
            {
                "task_id": "task-a",
                "mode": "without_nexus",
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "model_calls": 1,
                "total_tokens": 30000,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    bundle = tmp_path / "evidence_bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "raw_files": {
                    "with_nexus": {"path": str(with_path)},
                    "without_nexus": {"path": str(without_path)},
                }
            }
        ),
        encoding="utf-8",
    )

    export = build_export(bundle)

    assert export["s2t_policy_draft"]["task_rules"]["task-a"]["recommended_action"] == "try_lite_with_defensive_gate"
    assert export["route_cost_policy_candidate"]["lite_route_tasks"] == []
    assert export["route_cost_policy_candidate"]["candidate_cap_overrides"] == {"task-a": 1}


def test_export_s2t_shadow_policy_keeps_lite_routes_empty_until_validated_twice(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_path.write_text(
        json.dumps(
            {
                "task_id": "task-a",
                "mode": "with_nexus",
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "model_calls": 1,
                "total_tokens": 30000,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    without_path.write_text(
        json.dumps(
            {
                "task_id": "task-a",
                "mode": "without_nexus",
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "model_calls": 1,
                "total_tokens": 30000,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    bundle = tmp_path / "evidence_bundle.json"
    bundle.write_text(
        json.dumps({"raw_files": {"with_nexus": {"path": str(with_path)}, "without_nexus": {"path": str(without_path)}}}),
        encoding="utf-8",
    )

    export = build_export(bundle)

    assert export["s2t_policy_draft"]["task_rules"]["task-a"]["recommended_action"] == "prefer_lite_or_standard"
    assert export["route_cost_policy_candidate"]["candidate_cap_overrides"] == {"task-a": 1}
    assert export["route_cost_policy_candidate"]["lite_route_tasks"] == []
