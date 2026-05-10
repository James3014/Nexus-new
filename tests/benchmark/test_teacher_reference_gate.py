from pathlib import Path

from scripts.bench.teacher_reference_gate import build_teacher_reference_gate


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(__import__("json").dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_teacher_reference_gate_accepts_student_near_teacher(tmp_path: Path) -> None:
    teacher = tmp_path / "teacher"
    student = tmp_path / "student"
    teacher.mkdir()
    student.mkdir()
    _write_jsonl(
        teacher / "without_nexus_1.jsonl",
        [
            {"task_id": "a", "semantic_status": "VERIFIED"},
            {"task_id": "b", "semantic_status": "VERIFIED"},
            {"task_id": "c", "semantic_status": "UNVERIFIED"},
            {"task_id": "d", "semantic_status": "VERIFIED"},
        ],
    )
    _write_jsonl(
        student / "with_nexus_1.jsonl",
        [
            {"task_id": "a", "semantic_status": "VERIFIED"},
            {"task_id": "b", "semantic_status": "VERIFIED"},
            {"task_id": "c", "semantic_status": "VERIFIED"},
            {"task_id": "d", "semantic_status": "VERIFIED"},
        ],
    )
    (student / "evidence_bundle.json").write_text(
        """
{
  "public_claim_gate": {
    "verdict": "PASS",
    "checks": {
      "with_semantic_verified_rate": 1.0,
      "without_semantic_verified_rate": 0.25,
      "trust_mismatch_free": true,
      "wall_cost_ratio_with_over_without": 1.4,
      "token_cost_ratio_with_over_without": 1.2
    }
  }
}
""".strip(),
        encoding="utf-8",
    )

    out = build_teacher_reference_gate(teacher_run=teacher, student_runs={"flash": student})

    assert out["passed"] is True
    assert out["teacher_verified_rate"] == 0.75
    assert out["students"][0]["student_verified_rate"] == 1.0


def test_teacher_reference_gate_blocks_student_below_teacher_threshold(tmp_path: Path) -> None:
    teacher = tmp_path / "teacher"
    student = tmp_path / "student"
    teacher.mkdir()
    student.mkdir()
    _write_jsonl(
        teacher / "without_nexus_1.jsonl",
        [
            {"task_id": "a", "semantic_status": "VERIFIED"},
            {"task_id": "b", "semantic_status": "VERIFIED"},
            {"task_id": "c", "semantic_status": "VERIFIED"},
            {"task_id": "d", "semantic_status": "VERIFIED"},
        ],
    )
    _write_jsonl(
        student / "with_nexus_1.jsonl",
        [
            {"task_id": "a", "semantic_status": "VERIFIED"},
            {"task_id": "b", "semantic_status": "UNVERIFIED"},
            {"task_id": "c", "semantic_status": "UNVERIFIED"},
            {"task_id": "d", "semantic_status": "UNVERIFIED"},
        ],
    )
    (student / "evidence_bundle.json").write_text(
        '{"public_claim_gate": {"verdict": "PASS", "checks": {"trust_mismatch_free": true}}}',
        encoding="utf-8",
    )

    out = build_teacher_reference_gate(teacher_run=teacher, student_runs={"flash": student})

    assert out["passed"] is False
    assert any(item["reason"] == "student_quality_below_teacher_threshold" for item in out["failures"])
