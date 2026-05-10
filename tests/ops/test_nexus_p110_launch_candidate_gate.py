from pathlib import Path

from scripts.ops.nexus_p110_launch_candidate_gate import build_p110_launch_candidate_gate, main


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(__import__("json").dumps(row) for row in rows) + "\n", encoding="utf-8")


def _write_bundle(path: Path, *, wall: float = 1.4, median_wall: float = 1.1, token: float = 1.2) -> None:
    path.write_text(
        __import__("json").dumps(
            {
                "public_claim_gate": {
                    "verdict": "PASS",
                    "checks": {
                        "with_semantic_verified_rate": 1.0,
                        "without_semantic_verified_rate": 0.5,
                        "trust_mismatch_free": True,
                        "wall_cost_ratio_with_over_without": wall,
                        "median_paired_wall_cost_ratio_with_over_without": median_wall,
                        "token_cost_ratio_with_over_without": token,
                    },
                }
            }
        ),
        encoding="utf-8",
    )


def test_p110_gate_distinguishes_quality_ready_from_launch_ready(tmp_path: Path) -> None:
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
            {"task_id": "d", "semantic_status": "UNVERIFIED"},
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
    _write_bundle(student / "evidence_bundle.json")

    payload = build_p110_launch_candidate_gate(
        repo_root=Path(".").resolve(),
        teacher_run=teacher,
        student_runs={"flash": student},
        run_pre_flash=False,
        target_teacher_tasks=8,
    )

    assert payload["quality_ready"] is True
    assert payload["launch_ready"] is False
    assert payload["readiness_blockers"][0]["reason"] == "teacher_reference_suite_below_launch_target"


def test_p110_cli_exits_nonzero_when_launch_is_blocked(tmp_path: Path) -> None:
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
            {"task_id": "d", "semantic_status": "UNVERIFIED"},
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
    _write_bundle(student / "evidence_bundle.json")

    assert (
        main(
            [
                "--repo-root",
                ".",
                "--teacher-run",
                str(teacher),
                "--student",
                f"flash={student}",
                "--output",
                str(tmp_path / "gate.json"),
                "--target-teacher-tasks",
                "8",
            ]
        )
        == 1
    )


def test_p110_gate_blocks_hard_cost_failure(tmp_path: Path) -> None:
    teacher = tmp_path / "teacher"
    student = tmp_path / "student"
    teacher.mkdir()
    student.mkdir()
    rows = [{"task_id": item, "semantic_status": "VERIFIED"} for item in ("a", "b", "c", "d")]
    _write_jsonl(teacher / "without_nexus_1.jsonl", rows)
    _write_jsonl(student / "with_nexus_1.jsonl", rows)
    _write_bundle(student / "evidence_bundle.json", wall=2.1, median_wall=1.8, token=1.5)

    payload = build_p110_launch_candidate_gate(
        repo_root=Path(".").resolve(),
        teacher_run=teacher,
        student_runs={"pro": student},
        run_pre_flash=False,
        target_teacher_tasks=4,
    )

    assert payload["quality_ready"] is False
    assert payload["launch_ready"] is False
    assert payload["cost_gate"]["hard_failures"]
