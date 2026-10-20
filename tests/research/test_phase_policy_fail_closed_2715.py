"""#2715: phase_policy.phase_slo_pass_rate and the learn_phase_slo audit fixture fail closed.

After #2702 the phase SLO report fails closed, but ``phase_slo_pass_rate`` still scored a phase
with no required write-back rows as passing (its ``required_done_ratio`` defaults to 1.0) and
ignored ``phase_slo_pass``, so a ledger of only not-required rows still gave ``allow_research``.
The wiring audit's ``learn_phase_slo`` scenario used a failing ledger as its positive fixture.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nexus.research.learn.phase_policy import derive_phase_actions, phase_slo_pass_rate
from nexus.research.learn_mode import LearnModeService
from scripts.ops import capability_wiring_audit as audit


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


def _summary(root: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    path = root / ".nexus" / "reports" / "learn" / "phase_writeback.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return LearnModeService(project_root=root, run_root=root).build_phase_slo_report(window=300)


def test_only_not_required_rows_do_not_allow_research(tmp_path: Path) -> None:
    summary = _summary(tmp_path, [_row("R", required=False, done=True)] * 3)
    assert summary["status"] == "SUCCESS"
    assert summary["phases"]["R"]["required_done_ratio"] == 1.0  # the default that proved nothing
    assert phase_slo_pass_rate(summary) == 0.0
    actions = derive_phase_actions(summary, "bug", "standard")
    assert actions.allow_research is False
    assert actions.force_baseline is True
    assert "PassRate=0.0%" in actions.reasoning


def test_phase_without_required_rows_is_not_counted_as_passing(tmp_path: Path) -> None:
    # X has rows but none required: it is judged on success_ratio only (its required_done_ratio
    # default proves nothing), and a ledger whose only phases are not-required is 0.0.
    summary = {
        "status": "SUCCESS",
        "phase_slo_pass": True,
        "phases": {
            "R": {
                "total": 2,
                "writeback_required": 2,
                "required_done_ratio": 1.0,
                "success_ratio": 1.0,
            },
            "X": {
                "total": 5,
                "writeback_required": 0,
                "required_done_ratio": 1.0,
                "success_ratio": 1.0,
            },
        },
    }
    assert phase_slo_pass_rate(summary) == 1.0
    only_unrequired = {
        "status": "SUCCESS",
        "phase_slo_pass": True,
        "phases": {"X": summary["phases"]["X"]},
    }
    assert phase_slo_pass_rate(only_unrequired) == 0.0
    failing_unrequired = {**summary["phases"]["X"], "success_ratio": 0.0}
    mixed = {**summary, "phases": {"R": summary["phases"]["R"], "X": failing_unrequired}}
    assert phase_slo_pass_rate(mixed) == 0.5


def test_failing_phase_slo_pass_overrides_row_ratios_and_overall_rate() -> None:
    ok = {"total": 4, "writeback_required": 4, "required_done_ratio": 1.0, "success_ratio": 1.0}
    assert (
        phase_slo_pass_rate({"status": "SUCCESS", "phase_slo_pass": False, "phases": {"R": ok}})
        == 0.0
    )
    assert phase_slo_pass_rate({"phase_slo_pass": False, "overall_pass_rate": 0.9}) == 0.0
    # A real-schema summary that does not say phase_slo_pass is not evidence of a pass.
    assert phase_slo_pass_rate({"status": "SUCCESS", "phases": {"R": ok}}) == 0.0
    assert (
        derive_phase_actions(
            {"status": "SUCCESS", "phase_slo_pass": False, "phases": {"R": ok}},
            "feature",
            "standard",
        ).allow_research
        is False
    )


def test_healthy_ledger_still_allows_research(tmp_path: Path) -> None:
    summary = _summary(
        tmp_path,
        [
            _row("R", required=True, done=True),
            _row("X", required=True, done=True),
            _row("X", required=False, done=False),
        ],
    )
    assert summary["phase_slo_pass"] is True
    assert phase_slo_pass_rate(summary) == 1.0
    assert derive_phase_actions(summary, "bug", "standard").allow_research is True


def test_failing_ledger_summary_scores_zero(tmp_path: Path) -> None:
    summary = _summary(
        tmp_path,
        [
            _row("R", required=True, done=True),
            _row("X", status="FAILED", required=True, done=False),
        ],
    )
    assert summary["phase_slo_pass"] is False
    assert phase_slo_pass_rate(summary) == 0.0


def test_wiring_audit_learn_phase_slo_positive_fixture_passes(tmp_path: Path) -> None:
    matrix = audit.run_audit(["learn_phase_slo"], tmp_path, allow_model=False, smoke_summary=None)
    row = {r["capability"]: r for r in matrix["rows"]}["learn_phase_slo"]
    assert row["verdict"] == audit.REAL, row.get("checks")
    checks = {c["name"]: c["passed"] for c in row["checks"]}
    assert checks["seeded_writebacks_counted"] is True
    assert checks["complete_writebacks_pass_slo"] is True
    assert row["negative_control"]["passed"] is True
    assert row["negative_control"]["name"] == "negative_control:failing_ledger_fails_slo"
    assert row["negative_control"]["negative_block_reason"] == "phase_slo_failed"
    probe = row["component_probe"]
    assert probe["project_root_phase_slo_pass"] is True
    assert probe["per_task_run_root_phase_slo_pass"] is False


def test_overall_pass_rate_needs_phase_slo_pass_and_success_status() -> None:
    assert phase_slo_pass_rate({"overall_pass_rate": 1.0}) == 0.0
    assert phase_slo_pass_rate({"overall_pass_rate": 1.0, "status": "FAILED"}) == 0.0
    assert (
        phase_slo_pass_rate({"overall_pass_rate": 1.0, "status": "FAILED", "phase_slo_pass": True})
        == 0.0
    )
    ok = {"phase_slo_pass": True, "status": "SUCCESS"}
    assert phase_slo_pass_rate({**ok, "overall_pass_rate": 0.85}) == 0.85
    assert phase_slo_pass_rate({**ok, "overall_pass_rate": 7.0}) == 1.0
    assert phase_slo_pass_rate({**ok, "overall_pass_rate": -3.0}) == 0.0
    assert phase_slo_pass_rate({**ok, "overall_pass_rate": "nan"}) == 0.0
    assert (
        derive_phase_actions({"overall_pass_rate": 1.0}, "bug", "standard").allow_research is False
    )


def test_failing_phase_cannot_hide_by_being_not_required() -> None:
    bad_unrequired = {
        "total": 3,
        "writeback_required": 0,
        "required_done_ratio": 1.0,
        "success_ratio": 0.0,
    }
    summary = {
        "status": "SUCCESS",
        "phase_slo_pass": True,
        "phases": {
            "R": {
                "total": 2,
                "writeback_required": 2,
                "required_done_ratio": 1.0,
                "success_ratio": 1.0,
            },
            "X": dict(bad_unrequired),
            "D": dict(bad_unrequired),
            "A": dict(bad_unrequired),
            "C": {
                "total": 0,
                "writeback_required": 0,
                "required_done_ratio": 1.0,
                "success_ratio": 1.0,
            },
        },
    }
    assert phase_slo_pass_rate(summary) == 0.25
    assert derive_phase_actions(summary, "bug", "standard").allow_research is False
