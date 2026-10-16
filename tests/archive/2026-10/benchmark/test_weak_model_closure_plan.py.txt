from __future__ import annotations

import json
from pathlib import Path

from scripts.bench.weak_model_closure_plan import build_closure_plan, classify_gap_row, main, render_markdown


def test_classify_local_fast_path_as_cost_avoidance_not_uplift():
    row = classify_gap_row(
        {
            "task_id": "nexus-value-hidden-001",
            "student_verified": True,
            "teacher_verified": True,
            "student_success_source": "local_deterministic_success",
            "student_model_uplift_eligible": False,
        }
    )

    assert row.classification == "nexus_cost_avoidance_not_model_uplift"
    assert row.recommendation == "keep_separate_from_weak_model_claims"
    assert row.model_uplift_eligible is False


def test_build_closure_plan_blocks_phase9_until_12_tasks_and_model_uplift():
    payload = build_closure_plan(
        gap_payload={
            "student_model": "flash",
            "teacher_model": "gpt55",
            "rows": [
                {
                    "task_id": "local-1",
                    "student_verified": True,
                    "teacher_verified": True,
                    "student_success_source": "local_deterministic_success",
                    "student_model_uplift_eligible": False,
                }
            ],
        },
        min_task_count=12,
    )

    assert payload["closure_ready"] is False
    assert payload["model_uplift_eligible_task_count"] == 0
    assert payload["next_required_action"] == "expand_to_12_task_teacher_student_loop_before_claims"
    assert any(item["phase"] == "phase9_closure" and item["status"] == "not_ready" for item in payload["phase_status"])


def test_build_closure_plan_promotes_only_eligible_model_uplift_rows():
    rows = [
        {
            "task_id": f"task-{idx}",
            "student_verified": True,
            "teacher_verified": True,
            "student_success_source": "model_assisted_success",
            "student_model_uplift_eligible": True,
            "student_vs_teacher_wall_ratio": 1.2,
            "student_vs_teacher_token_ratio": 1.1,
        }
        for idx in range(12)
    ]
    payload = build_closure_plan(gap_payload={"rows": rows}, min_task_count=12)
    md = render_markdown(payload)

    assert payload["closure_ready"] is True
    assert payload["classification_counts"] == {"model_uplift_candidate": 12}
    assert payload["next_required_action"] == "run_same_model_ab_and_publish_only_if_public_gate_passes"
    assert "phase9_closure" in md


def test_main_writes_closure_plan(tmp_path: Path, monkeypatch):
    gap = tmp_path / "gap.json"
    output = tmp_path / "plan.md"
    output_json = tmp_path / "plan.json"
    gap.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "task_id": "gap-1",
                        "student_verified": False,
                        "teacher_verified": True,
                        "student_success_source": "failed",
                        "student_model_uplift_eligible": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "weak_model_closure_plan.py",
            "--gap-json",
            str(gap),
            "--min-task-count",
            "1",
            "--output",
            str(output),
            "--output-json",
            str(output_json),
        ],
    )

    assert main() == 0
    assert "Nexus Weak Model Closure Plan" in output.read_text(encoding="utf-8")
    assert json.loads(output_json.read_text(encoding="utf-8"))["rows"][0]["classification"] == "weak_model_capability_gap"
