from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nexus.research.flow.evidence_packer import (
    AUTO_NIGHTSHIFT_BUDGET_MIN_ENV,
    AUTO_NIGHTSHIFT_ENV,
    AUTO_NIGHTSHIFT_MAX_ROUNDS_ENV,
    apply_nightshift_auto_run,
    maybe_run_nightshift_after_hyper_failure,
)

HYPER_FAILED = {"flow": "hyper_sprint", "status": "FAILED", "error": "stage1_no_passing_candidate"}


class FakeRunner:
    calls: list[dict[str, Any]] = []
    terminal_state = "SUCCESS"
    raises: Exception | None = None

    def __init__(self, **kwargs: Any) -> None:
        type(self).calls.append(kwargs)
        self.task = kwargs["task"]
        self.project_root = Path(kwargs["project_root"])

    def run(self) -> dict[str, Any]:
        error = type(self).raises
        if error is not None:
            raise error
        report = self.project_root / ".nexus" / "reports" / f"nightshift_{self.task}.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps({"terminal_state": type(self).terminal_state, "best_score": 1.0}),
            encoding="utf-8",
        )
        return {"status": "COMPLETED"}


@pytest.fixture(autouse=True)
def _reset_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeRunner.calls = []
    FakeRunner.terminal_state = "SUCCESS"
    FakeRunner.raises = None
    for name in (
        AUTO_NIGHTSHIFT_ENV,
        AUTO_NIGHTSHIFT_BUDGET_MIN_ENV,
        AUTO_NIGHTSHIFT_MAX_ROUNDS_ENV,
    ):
        monkeypatch.delenv(name, raising=False)


def _run(tmp_path: Path, **overrides: Any) -> dict[str, Any] | None:
    kwargs: dict[str, Any] = {
        "repo_root": tmp_path,
        "result": HYPER_FAILED,
        "nightshift_recommended": True,
        "task_desc": "fix-bug",
        "target_file": "a.py",
        "test_file": "tests",
        "runner_factory": FakeRunner,
    }
    kwargs.update(overrides)
    return maybe_run_nightshift_after_hyper_failure(**kwargs)


def test_flag_off_runner_not_called(tmp_path: Path) -> None:
    assert _run(tmp_path) is None
    assert FakeRunner.calls == []


def test_flag_on_but_not_applicable_runner_not_called(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(AUTO_NIGHTSHIFT_ENV, "1")
    assert _run(tmp_path, nightshift_recommended=False) is None
    assert _run(tmp_path, result={"flow": "hyper_sprint", "status": "SUCCESS"}) is None
    assert _run(tmp_path, result={"flow": "baseline", "status": "FAILED"}) is None
    assert FakeRunner.calls == []


def test_flag_on_hyper_failure_calls_runner_with_budget_and_records_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(AUTO_NIGHTSHIFT_ENV, "1")
    monkeypatch.setenv(AUTO_NIGHTSHIFT_BUDGET_MIN_ENV, "3")
    receipt = _run(tmp_path)
    assert receipt is not None
    assert len(FakeRunner.calls) == 1
    call = FakeRunner.calls[0]
    assert call["budget_min"] == 3 and call["max_rounds"] == 2 and call["convergence_patience"] == 1
    assert receipt["budget"] == {"budget_min": 3, "max_rounds": 2, "convergence_patience": 1}
    assert receipt["invoked"] is True and receipt["recovered"] is True
    assert receipt["runner_report"]["terminal_state"] == "SUCCESS"
    assert receipt["report_path"].endswith("nightshift_fix-bug.json")

    evidence = apply_nightshift_auto_run({"nightshift_recommended": True}, receipt)
    assert evidence["nightshift_invoked"] is True and evidence["nightshift_recovered"] is True
    assert evidence["nightshift_report"]["budget"]["budget_min"] == 3
    assert evidence["nightshift_report"]["runner_report"]["best_score"] == 1.0


def test_runner_report_not_success_is_not_recovered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(AUTO_NIGHTSHIFT_ENV, "true")
    FakeRunner.terminal_state = "NO_IMPROVEMENT"
    receipt = _run(tmp_path)
    assert receipt is not None
    assert receipt["invoked"] is True and receipt["recovered"] is False
    assert receipt["failure_reason"] == "nightshift_not_recovered:NO_IMPROVEMENT"


def test_runner_without_report_is_not_invoked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(AUTO_NIGHTSHIFT_ENV, "1")

    class NoReport(FakeRunner):
        def run(self) -> dict[str, Any]:
            return {"status": "FAILED", "reason": "policy_blocked"}

    receipt = _run(tmp_path, runner_factory=NoReport)
    assert receipt is not None
    assert receipt["invoked"] is False and receipt["recovered"] is False
    assert receipt["failure_reason"] == "nightshift_no_report:policy_blocked"


def test_runner_exception_sets_failure_reason_and_never_recovered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(AUTO_NIGHTSHIFT_ENV, "1")
    FakeRunner.raises = RuntimeError("boom")
    receipt = _run(tmp_path)
    assert receipt is not None
    assert receipt["recovered"] is False and receipt["invoked"] is False
    assert receipt["failure_reason"].startswith("nightshift_runner_exception:RuntimeError:boom")
    evidence = apply_nightshift_auto_run({}, receipt)
    assert evidence["nightshift_recovered"] is False
    assert evidence["nightshift_failure_reason"] == receipt["failure_reason"]


def test_apply_is_noop_without_auto_run() -> None:
    evidence = {"nightshift_recommended": True, "nightshift_invoked": False}
    assert apply_nightshift_auto_run(evidence, None) is evidence
