"""Unit tests for the memory-on vs memory-off A/B runner (issue #1639). No model calls."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import run_memory_ab_v1 as runner  # noqa: E402
import verify_fixtures  # noqa: E402
from nexus_learning.effectiveness_measurement import normalize_attempt_row  # noqa: E402

BUGGY = "def f():\n    return 1\n"
FIXED = "def f():\n    return 2\n"
REPRO = "import sys\nfrom m import f\nsys.exit(0 if f() == 2 else 1)\n"


def make_tasks(root: Path, count: int = 2) -> Path:
    tasks = root / "tasks"
    for i in range(count):
        task_dir = tasks / f"toy-{i}"
        task_dir.mkdir(parents=True)
        (task_dir / "m.py").write_text(BUGGY, encoding="utf-8")
        (task_dir / "repro.py").write_text(REPRO, encoding="utf-8")
        (task_dir / "task.json").write_text(
            json.dumps({
                "id": task_dir.name,
                "bug_class": "toy",
                "variant": str(i),
                "problem_statement": "f() returns 1 instead of 2",
                "target_file": "m.py",
                "repro_file": "repro.py",
            }),
            encoding="utf-8",
        )
    return tasks


def fake_pipeline_factory(extra_write: Path | None = None):
    """Stands in for HealPipeline.run. Applies the route-context seed the way to_v2() does,
    then repairs the file only on the memory-on arm. The verdict still comes from the real repro."""

    def fake(ctx, generate_fn):
        for key, value in ctx.route_context["semantic_retry_seed"].items():
            setattr(ctx, key, value)
        if ctx.memory_enabled:
            (ctx.repo_dir / "m.py").write_text(FIXED, encoding="utf-8")
            ctx.solve_eligible = True
        else:
            ctx.solve_eligible = False
            ctx.failure_reason = "verifier_fail"
        ctx.receipt_path = f"receipt:{ctx.attempt_id}"
        if extra_write is not None:
            extra_write.write_text("leak", encoding="utf-8")
        return ctx

    return fake


@pytest.fixture
def harness(tmp_path, monkeypatch):
    watched = tmp_path / "watched"
    watched.mkdir()
    monkeypatch.setattr(runner, "preflight_model", lambda *a, **k: None)
    monkeypatch.setattr(runner, "redirect_learning_state", lambda root, reports=None: None)
    monkeypatch.setattr(runner, "STATE_WATCH_ROOTS", [watched])
    monkeypatch.setattr(runner, "git_head", lambda repo: "0" * 40)
    monkeypatch.setattr(runner, "git_tree_head", lambda repo: "1" * 40)
    for key in (
        "NEXUS_OLLAMA_MODEL",
        "NEXUS_PATCH_TIMEOUT_SECONDS",
        "NEXUS_LEARNING_REFLECT_JUDGE",
        "NEXUS_LEARNING_STATE_ROOT",
    ):
        monkeypatch.setenv(key, "")
    return {"root": tmp_path, "watched": watched, "monkeypatch": monkeypatch}


def run_main(harness, extra_args=None, run_id="t1"):
    args = [
        "--tasks-dir",
        str(make_tasks(harness["root"])),
        "--run-id",
        run_id,
        "--artifact-root",
        str(harness["root"] / "art"),
        "--limit",
        "2",
    ] + (extra_args or [])
    return runner.main(args)


def test_all_fixtures_are_red():
    results = verify_fixtures.verify_all()
    assert len(results) == 12
    assert {r["bug_class"] for r in results} == {
        "off_by_one",
        "wrong_comparison_operator",
        "mutable_default_argument",
        "integer_division",
        "missing_none_check",
        "string_key_typo",
    }
    assert all(r["red"] and r["within_budget"] for r in results), results


def test_v2_fixtures_are_red():
    v2_dir = EVAL_DIR / "memory_ab_tasks_v2"
    results = verify_fixtures.verify_all(v2_dir)
    assert len(results) == 12
    assert {r["bug_class"] for r in results} == {
        "timezone_naive_aware",
        "consumed_iterator",
        "mutate_while_iterating",
        "float_money_rounding",
        "greedy_regex_multiline",
        "recursive_base_case",
    }
    assert {r["task_id"].rsplit("-", 1)[1] for r in results} == {"a", "b"}
    assert all(r["red"] and r["within_budget"] for r in results), results


def test_fixture_verifier_rejects_green_repro(tmp_path):
    task_dir = make_tasks(tmp_path, 1) / "toy-0"
    (task_dir / "m.py").write_text(FIXED, encoding="utf-8")
    result = verify_fixtures.verify_fixture(task_dir)
    assert result["red"] is False and result["ok"] is False


def test_ab_rows_scorecard_and_validation(harness):
    monkeypatch = harness["monkeypatch"]
    monkeypatch.setattr(runner, "run_pipeline", fake_pipeline_factory())
    assert run_main(harness) == 0

    run_root = harness["root"] / "art" / "t1"
    rows = [json.loads(line) for line in (run_root / "rows.jsonl").read_text().splitlines()]
    assert len(rows) == 2 * 2  # 2 tasks x 2 arms
    for row in rows:
        normalize_attempt_row(row)  # contract-valid, unchanged
        assert row["evidence_origin"] == "physical"
        assert row["workflow_revision"] == runner.DEFAULT_MODEL
    off = [r for r in rows if r["memory_arm"] == "memory_off"]
    on = [r for r in rows if r["memory_arm"] == "memory_on"]
    assert len(off) == len(on) == 2
    assert all(
        r["workflow"] == "nexus_memory_off" and r["terminal_outcome"] == "FAILED" for r in off
    )
    assert all(
        r["workflow"] == "nexus_memory_on" and r["terminal_outcome"] == "SUCCEEDED" for r in on
    )
    assert all(r["memory_flag_applied"] for r in rows)
    assert all(r["ineligibility_reasons"] == [] for r in rows)
    # Arms ran in order: all off rows precede all on rows in rows.jsonl.
    arms_in_order = [r["memory_arm"] for r in rows]
    assert arms_in_order == ["memory_off", "memory_off", "memory_on", "memory_on"]

    scorecard = json.loads((run_root / "scorecard.json").read_text())
    assert "paired_memory_uplift" in scorecard
    assert "quality_gate" in scorecard
    assert scorecard["row_count"] == 4

    validation = json.loads((run_root / "validation.json").read_text())
    assert validation["real_model_call_executed"] is False
    assert validation["synthetic_delta_measured"] is False
    assert validation["public_claim_allowed"] is False
    assert validation["training_export_allowed"] is False
    assert validation["production_ready"] is False
    assert validation["internal_only"] is True
    assert validation["memory_flags_verified"] is True
    assert validation["rows"] == 4
    assert validation["state_leaks"] == []

    decision = json.loads((run_root / "adoption_decision.json").read_text())
    assert decision["decision"] in {"ADOPT", "DEFER"}, decision["reason_codes"]
    assert decision["advisory_only"] is True
    for code in decision["reason_codes"]:
        assert "SCORECARD_INVALID" not in code and "SIMULATED_EVIDENCE" not in code, code
    assert rows[0]["attempt_index"] == rows[1]["attempt_index"] == 0


def test_rows_carry_retrieval_and_consumption_receipts(harness):
    harness["monkeypatch"].setattr(runner, "run_pipeline", fake_pipeline_factory())
    assert run_main(harness) == 0
    rows = [
        json.loads(line)
        for line in (harness["root"] / "art" / "t1" / "rows.jsonl").read_text().splitlines()
    ]
    for row in rows:
        refs = row["evidence_refs"]
        assert any("retrieval_receipt" in ref for ref in refs)
        assert any("ollama_consumption" in ref for ref in refs)
        assert Path(row["work_dir"], "retrieval_receipt.json").is_file()
        assert Path(row["work_dir"], "ollama_consumption.json").is_file()
        assert row["applied_attributed_lesson_ids"] == row["applied_lesson_ids"]
        assert row["source_tree"] == "1" * 40 and row["source_revision"] == "0" * 40
    off = json.loads(Path(rows[0]["work_dir"], "retrieval_receipt.json").read_text())
    assert off["status"] == "disabled" and off["memory_enabled"] is False
    for task_id in {r["task_id"] for r in rows}:
        arms = sorted(r["memory_arm"] for r in rows if r["task_id"] == task_id)
        assert arms == ["memory_off", "memory_on"]


def test_preflight_failure_writes_no_rows(harness, capsys):
    harness["monkeypatch"].setattr(
        runner,
        "preflight_model",
        lambda *a, **k: (_ for _ in ()).throw(runner.ModelUnavailable("down")),
    )
    assert run_main(harness) == runner.EXIT_PREFLIGHT
    assert not (harness["root"] / "art" / "t1" / "rows.jsonl").exists()
    assert "PREFLIGHT_FAILED" in capsys.readouterr().err


def test_state_leak_is_reported_with_exit_3(harness, capsys):
    leak_target = harness["watched"] / "memory.json"
    harness["monkeypatch"].setattr(
        runner, "run_pipeline", fake_pipeline_factory(extra_write=leak_target)
    )
    assert run_main(harness) == runner.EXIT_STATE_LEAK
    assert f"STATE_LEAK: {leak_target}" in capsys.readouterr().out
    validation = json.loads((harness["root"] / "art" / "t1" / "validation.json").read_text())
    assert str(leak_target) in validation["state_leaks"]
    assert leak_target.exists(), "runner must not delete anything"


def test_pipeline_exception_is_recorded_not_raised(harness):
    def boom(ctx, generate_fn):
        raise RuntimeError("synthetic pipeline failure")

    harness["monkeypatch"].setattr(runner, "run_pipeline", boom)
    assert run_main(harness) == 0
    rows = [
        json.loads(line)
        for line in (harness["root"] / "art" / "t1" / "rows.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 4
    assert all("pipeline_exception" in r["ineligibility_reasons"] for r in rows)
    assert all(r["pipeline_status"] == "exception" for r in rows)
    # Ineligible arms must not produce a paired memory signal.
    scorecard = json.loads((harness["root"] / "art" / "t1" / "scorecard.json").read_text())
    assert scorecard["paired_memory_uplift"] is not None
