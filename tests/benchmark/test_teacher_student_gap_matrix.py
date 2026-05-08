from __future__ import annotations

import json
from pathlib import Path

from scripts.bench.teacher_student_gap_matrix import build_gap_matrix, render_markdown


def _write_row(root: Path, arm: str, task_id: str, **overrides) -> None:
    evidence = root / "evidence_1"
    evidence.mkdir(parents=True, exist_ok=True)
    row = {
        "task_id": task_id,
        "task_type": "public_test_repair" if "repair" in task_id else "public_bugfix",
        "category": "test_repair" if "repair" in task_id else "bugfix",
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "report_trust_mismatch": False,
        "wall_duration_sec": 10.0,
        "total_tokens": 1000,
        "model_calls": 1,
        "run_eligible": True,
        "infra_invalid_reason": None,
        "model_uses_nexus": True,
        "gemini_uses_nexus": True,
        "nexus_wearing_valid": True,
        "nexus_winner_source": "llm",
        "baseline_source_policy": "model_first",
        "rescue_cost_status": "model_assisted",
        "token_capture_status": "captured",
        "route_decision_selected_count": 4,
        "strategy_path": "baseline_only",
        "route_profile_high_cost_selected": [],
    }
    row.update(overrides)
    (evidence / f"{arm}__{task_id}__trial_1.row.json").write_text(json.dumps(row), encoding="utf-8")


def test_teacher_student_gap_matrix_recommends_teacher_runtime_profile(tmp_path: Path):
    student = tmp_path / "student"
    teacher = tmp_path / "teacher"
    _write_row(student, "with_nexus", "nexus-value-repair-002", wall_duration_sec=60.0, total_tokens=50000, strategy_path="hyper_direct_hard_skip_probe")
    _write_row(student, "without_nexus", "nexus-value-repair-002", status="FAILED", semantic_status="UNVERIFIED", wall_duration_sec=30.0)
    _write_row(teacher, "with_nexus", "nexus-value-repair-002", wall_duration_sec=20.0, total_tokens=20000, strategy_path="codex_wearing_nexus_context")
    _write_row(teacher, "without_nexus", "nexus-value-repair-002", status="FAILED", semantic_status="UNVERIFIED", wall_duration_sec=12.0)

    payload = build_gap_matrix(student_run=student, teacher_run=teacher, student_name="flash_nexus", teacher_name="gpt55_nexus")

    assert payload["schema_version"] == "nexus_teacher_student_gap_matrix_v1"
    assert payload["rows"][0]["bucket"] == "repair"
    assert payload["rows"][0]["student_vs_teacher_wall_ratio"] == 3.0
    assert payload["rows"][0]["recommendation"] == "keep_nexus_value_but_copy_teacher_runtime_profile"


def test_render_markdown_includes_gap_ratios(tmp_path: Path):
    student = tmp_path / "student"
    teacher = tmp_path / "teacher"
    _write_row(student, "with_nexus", "nexus-value-hidden-001", wall_duration_sec=40.0, total_tokens=4000)
    _write_row(student, "without_nexus", "nexus-value-hidden-001", wall_duration_sec=10.0, total_tokens=3000)
    _write_row(teacher, "with_nexus", "nexus-value-hidden-001", wall_duration_sec=20.0, total_tokens=2000)
    _write_row(teacher, "without_nexus", "nexus-value-hidden-001", wall_duration_sec=12.0, total_tokens=1800)

    out = render_markdown(build_gap_matrix(student_run=student, teacher_run=teacher, student_name="flash_nexus", teacher_name="gpt55_nexus"))

    assert "Nexus Teacher Student Gap Matrix" in out
    assert "2.00x" in out
    assert "slim_student_runtime_path" in out


def test_local_deterministic_success_is_not_model_uplift(tmp_path: Path):
    student = tmp_path / "student"
    teacher = tmp_path / "teacher"
    _write_row(
        student,
        "with_nexus",
        "nexus-value-hidden-001",
        wall_duration_sec=14.6789,
        total_tokens=0,
        model_calls=0,
        run_eligible=False,
        infra_invalid_reason="nexus_delivery_invalid",
        model_uses_nexus=False,
        gemini_uses_nexus=False,
        nexus_wearing_valid=False,
        nexus_winner_source="local_hidden_contract_fast_path",
        baseline_source_policy="hidden_contract_local_first_before_llm",
        rescue_cost_status="local_only",
        token_capture_status="not_applicable_local_only",
    )
    _write_row(
        teacher,
        "with_nexus",
        "nexus-value-hidden-001",
        wall_duration_sec=27.74,
        total_tokens=21278,
        model_calls=1,
        nexus_winner_source="llm",
    )

    payload = build_gap_matrix(student_run=student, teacher_run=teacher, student_name="flash_lite_route_local_first", teacher_name="gpt55_nexus")
    row = payload["rows"][0]
    out = render_markdown(payload)

    assert row["student_verified"] is True
    assert row["student_success_source"] == "local_deterministic_success"
    assert row["student_model_uplift_eligible"] is False
    assert row["student_run_eligible"] is False
    assert row["student_infra_invalid_reason"] == "nexus_delivery_invalid"
    assert row["recommendation"] == "keep_as_nexus_cost_avoidance_not_model_uplift"
    assert "local_deterministic_success -> model_assisted_success" in out
    assert "False -> True" in out


def test_gap_matrix_can_use_gpt55_direct_teacher_arm(tmp_path: Path):
    student = tmp_path / "student"
    teacher = tmp_path / "teacher"
    _write_row(student, "with_nexus", "nexus-value-hidden-001", wall_duration_sec=45.0, total_tokens=9000)
    _write_row(teacher, "with_nexus", "nexus-value-hidden-001", wall_duration_sec=30.0, total_tokens=6000, strategy_path="codex_wearing_nexus_context")
    _write_row(
        teacher,
        "without_nexus",
        "nexus-value-hidden-001",
        wall_duration_sec=15.0,
        total_tokens=3000,
        model_uses_nexus=False,
        gemini_uses_nexus=False,
        nexus_wearing_valid=False,
        strategy_path="gpt55_direct",
    )

    payload = build_gap_matrix(
        student_run=student,
        teacher_run=teacher,
        student_name="flash_nexus",
        teacher_name="gpt55_direct",
        teacher_arm="without_nexus",
    )
    row = payload["rows"][0]
    out = render_markdown(payload)

    assert payload["teacher_arm"] == "without_nexus"
    assert row["teacher_wall_sec"] == 15.0
    assert row["student_vs_teacher_wall_ratio"] == 3.0
    assert row["teacher_strategy_path"] == "gpt55_direct"
    assert "teacher_arm: `without_nexus`" in out
