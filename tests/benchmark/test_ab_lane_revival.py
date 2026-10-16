"""Coverage for the revived same-model A/B lane (issue #1820).

Covers the no-LLM dry mode of ``capability_ab_runner`` and the real semantics of
``--strict-llm-baseline``: a success with ``model_calls == 0`` is a
``deterministic_rescue`` and is not counted as a solve.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from nexus.engine.sandboxed_lane import os_sandbox_available
from scripts.bench.capability_ab_runner import _summarize_with_strict_baseline
from scripts.bench.strict_llm_baseline import apply_strict_llm_baseline_classification

REPO_ROOT = Path(__file__).resolve().parents[2]
VALUE_FIXTURE = REPO_ROOT / "scripts" / "bench" / "public_benchmark_nexus_value_v1.json"


def _row(mode: str, status: str, model_calls: int | None) -> dict:
    row = {"mode": mode, "status": status, "run_eligible": True}
    if model_calls is not None:
        row["model_calls"] = model_calls
    return row


def test_strict_baseline_classifies_zero_model_call_success_as_deterministic_rescue():
    rows = [
        _row("with_nexus", "SUCCESS", 0),
        _row("with_nexus", "SUCCESS", 2),
        _row("with_nexus", "FAILED", 1),
        _row("without_nexus", "SUCCESS", 1),
        _row("without_nexus", "SUCCESS", 0),
        _row("without_nexus", "SUCCESS", None),
    ]
    summary = _summarize_with_strict_baseline(rows, strict=True)

    assert [r["solve_classification"] for r in rows] == [
        "deterministic_rescue",
        "model_solve",
        "not_solved",
        "model_solve",
        "deterministic_rescue",
        "deterministic_rescue",
    ]
    assert summary["with_nexus"]["solved_n"] == 1
    assert summary["with_nexus"]["deterministic_rescue_n"] == 1
    assert summary["with_nexus"]["solve_rate"] == round(1 / 3, 4)
    assert summary["without_nexus"]["solved_n"] == 1
    assert summary["without_nexus"]["deterministic_rescue_n"] == 2
    assert summary["without_nexus"]["strict_llm_baseline_applied"] is True


def test_classifier_alone_marks_rows_and_never_flips_status():
    rows = [_row("with_nexus", "SUCCESS", 0)]
    apply_strict_llm_baseline_classification(rows)
    assert rows[0]["status"] == "SUCCESS"
    assert rows[0]["deterministic_rescue"] is True


def test_without_strict_baseline_zero_model_call_success_still_counts():
    rows = [_row("with_nexus", "SUCCESS", 0), _row("with_nexus", "SUCCESS", 1)]
    summary = _summarize_with_strict_baseline(rows, strict=False)
    assert summary["with_nexus"]["solve_rate"] == 1.0
    assert "deterministic_rescue_n" not in summary["with_nexus"]
    assert "solve_classification" not in rows[0]


def _run_lane(tmp_path: Path, *extra: str) -> dict:
    env = {
        **os.environ,
        "NEXUS_BENCH_SUBPROCESS_PYTHON": sys.executable,
        "PYTHONPATH": str(REPO_ROOT),
    }
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "bench" / "capability_ab_runner.py"),
            "--tasks-file",
            str(VALUE_FIXTURE),
            "--output-dir",
            str(tmp_path),
            "--repeat-trials",
            "1",
            "--strict-llm-baseline",
            *extra,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_dry_mode_smoke_only_runs_on_the_12_task_fixture(tmp_path: Path):
    result = _run_lane(tmp_path, "--max-tasks", "12", "--parallel-arms", "smoke-only")
    assert result["status"] == "SMOKE_ONLY"
    assert result["tasks_requested"] == 12
    assert Path(result["evidence_bundle_file"]).exists()


def test_dry_mode_without_llm_reports_deterministic_rescue_not_solves(tmp_path: Path):
    result = _run_lane(
        tmp_path,
        "--max-tasks",
        "1",
        "--nexus-only",
        "--with-llm-mode",
        "off",
        "--with-nexus-runner",
        "subprocess",
        "--difficulty",
        "all",
        "--repo-kind-filter",
        "all",
        "--materialize-missing",
        "--isolation-mode",
        "preserve_target",
        "--neutralize-history",
        "--disable-learning-loop",
        "--evidence-bundle",
        # The default 30s leg timeout made the row ineligible (avg_model_calls None)
        # when the shared CI runner took 31s (nightly 38429695994); the dry lane
        # takes ~11-13s on an idle host. Budget for runner load, not for the logic.
        "--timeout-sec",
        "240",
    )
    with_summary = result["benchmark_summary"]["with_nexus"]
    assert with_summary["total_n"] == 1
    if not os_sandbox_available():
        # The strict lane confines the visible test (#2211); with no OS barrier (Seatbelt is
        # macOS-only, so Linux CI) the task is excluded for both arms, never scored (fail closed).
        assert with_summary["eligible_n"] == 0
        assert with_summary["solved_n"] == 0
        row = json.loads(Path(result["with_nexus_file"]).read_text().splitlines()[0])
        assert row["status"] == "NOT_RUN"
        assert row["not_run_reason"] == "confinement_parity_failed"
        assert row["confinement_parity_detail"] == "visible:confinement_unavailable"
        return
    assert with_summary["avg_model_calls"] == 0.0
    assert with_summary["solved_n"] == 0
    # #2339 follow-up: the deterministic local rescue (answer table) is deleted; without a model
    # nothing is rescued either.
    assert with_summary["deterministic_rescue_n"] == 0
    assert with_summary["strict_llm_baseline_applied"] is True
