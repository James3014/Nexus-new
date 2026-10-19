"""#2702: learn_phase_slo fails closed.

Before, an empty phase ledger passed (every ratio defaulted to 1.0), a not-required row that
wrote back inflated the ``done`` ratio, and the ``learn_phase_slo`` receipt was SUCCEEDED for
empty, failing and healthy stores alike (``gate_passed = result is not None``).
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from nexus.core.capability_executor_registry import _exec_learn_phase_slo
from nexus.research.learn_mode import LearnModeService

_PLAN_CLS: Any = getattr(
    importlib.import_module("nexus.core.belief_contracts"), "CapabilityExecutionPlan"
)


@pytest.fixture(autouse=True)
def _plain_lane(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXUS_SYMMETRIC_PROMPT", raising=False)
    monkeypatch.delenv("NEXUS_STATE_ROOT", raising=False)


def _row(phase: str, *, status: str = "SUCCESS", required: bool, done: bool) -> dict[str, Any]:
    return {
        "phase": phase,
        "phase_status": status,
        "writeback_policy": {"required": required},
        "writeback_done": done,
    }


def _seed(root: Path, rows: list[dict[str, Any]]) -> None:
    path = root / ".nexus" / "reports" / "learn" / "phase_writeback.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _report(root: Path) -> dict[str, Any]:
    return LearnModeService(project_root=root, run_root=root).build_phase_slo_report(window=300)


def _plan(root: Path) -> Any:
    return _PLAN_CLS(
        plan_id="p", task_id="t2702", phases=["R"], constraints={"workspace_root": str(root)}
    )


def test_empty_store_is_no_data_not_pass(tmp_path: Path) -> None:
    report = _report(tmp_path)
    assert report["phase_slo_pass"] is False
    assert report["status"] == "NO_DATA"
    assert report["reason"] == "no_phase_rows"
    assert report["global"]["required_done_ratio"] == 0.0
    written = json.loads(
        (tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json").read_text()
    )
    assert written["phase_slo_pass"] is False and written["status"] == "NO_DATA"


def test_not_required_row_does_not_inflate_done_ratio(tmp_path: Path) -> None:
    # One required row that did not write back + one not-required row that did: 0/1, not 1/1.
    _seed(tmp_path, [_row("R", required=True, done=False), _row("R", required=False, done=True)])
    report = _report(tmp_path)
    assert report["phases"]["R"]["writeback_required"] == 1
    assert report["phases"]["R"]["writeback_done"] == 0
    assert report["phases"]["R"]["required_done_ratio"] == 0.0
    assert report["global"]["required_done_ratio"] == 0.0
    assert report["phase_slo_pass"] is False


def test_rows_without_any_required_writeback_do_not_pass(tmp_path: Path) -> None:
    _seed(tmp_path, [_row("R", required=False, done=True)])
    report = _report(tmp_path)
    assert report["phase_slo_pass"] is False
    assert report["reason"] == "no_required_writeback_rows"


def test_healthy_store_passes_judging_only_observed_phases(tmp_path: Path) -> None:
    # Only R has rows; the five empty phases are not judged (and do not make it pass alone).
    _seed(tmp_path, [_row("R", required=True, done=True), _row("R", required=False, done=False)])
    report = _report(tmp_path)
    assert report["phase_slo_pass"] is True
    assert report["status"] == "SUCCESS"
    assert report["global"]["required_done_ratio"] == 1.0


def test_failing_observed_phase_fails_even_if_another_passes(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        [_row("R", required=True, done=True), _row("X", status="FAILED", required=True, done=True)],
    )
    report = _report(tmp_path)
    assert report["phase_slo_pass"] is False
    assert report["reason"] == "phase_slo_below_threshold"


def test_executor_reflects_failing_slo(tmp_path: Path) -> None:
    _seed(tmp_path, [_row("R", required=True, done=False), _row("R", required=False, done=True)])
    receipt = _exec_learn_phase_slo(_plan(tmp_path), "task")
    outcome = dict(receipt.outcome)
    assert receipt.gate_passed is False
    assert outcome["semantic_status"] == "FAILED"
    assert outcome["error"] == "phase_slo_failed"
    assert outcome["result"]["phase_slo_pass"] is False


def test_executor_empty_store_is_not_succeeded(tmp_path: Path) -> None:
    receipt = _exec_learn_phase_slo(_plan(tmp_path), "task")
    outcome = dict(receipt.outcome)
    assert receipt.gate_passed is False
    assert outcome["semantic_status"] == "FAILED"
    assert outcome["error"] == "phase_slo_no_data"
    assert outcome["result"]["status"] == "NO_DATA"


def test_executor_healthy_store_succeeds(tmp_path: Path) -> None:
    _seed(tmp_path, [_row("R", required=True, done=True)])
    receipt = _exec_learn_phase_slo(_plan(tmp_path), "task")
    outcome = dict(receipt.outcome)
    assert receipt.gate_passed is True
    assert outcome["semantic_status"] == "SUCCEEDED"
    assert "error" not in outcome
    assert outcome["result"]["phase_slo_pass"] is True


def test_no_data_summary_keeps_downstream_guards_closed(tmp_path: Path) -> None:
    """The summary an empty store writes no longer unlocks the readers that gate on it."""
    from nexus.research.flow.runtime_state import read_phase_slo_summary_fast
    from nexus.research.learn.phase_policy import phase_slo_pass_rate

    _report(tmp_path)
    fast = read_phase_slo_summary_fast(tmp_path)
    assert fast["phase_slo_pass"] is False and fast["status"] == "NO_DATA"
    assert LearnModeService(tmp_path).read_phase_slo_summary()["phase_slo_pass"] is False
    assert phase_slo_pass_rate(fast) == 0.0
