"""Mission token budget must count real usage or fail closed (Issue #2768).

`nexus run --report-file` writes a completion report that carries no ``usage``
block itself; it points at the unified runtime receipt
(``unified_runtime_receipt_path``), which is where stage usage is recorded.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod
from nexus.core.mission_contracts import MissionStatus, NexusMission


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _run_report(tmp_path: Path, runtime_receipt: Path | None) -> Path:
    """Shape of a real `nexus run` report: status fields, no usage of its own."""
    payload = {
        "status": "SUCCESS",
        "task_pipeline_success": True,
        "online_provider": "",
        "local_assist_mode": "disabled",
    }
    if runtime_receipt is not None:
        payload["unified_runtime_receipt_path"] = str(runtime_receipt)
    return _write(tmp_path / "reports" / "run_report.json", payload)


def _no_usage_report(tmp_path: Path, variant: str) -> Path:
    if variant == "no_pointer":
        return _run_report(tmp_path, None)
    if variant == "pointer_missing_file":
        return _run_report(tmp_path, tmp_path / "unified_runtime" / "absent.json")
    if variant == "pointer_without_usage":
        receipt = _write(
            tmp_path / "unified_runtime" / "task.json",
            {"task_id": "t", "online": {"gate_passed": True, "response": {"provider": "x"}}},
        )
        return _run_report(tmp_path, receipt)
    raise AssertionError(variant)


NO_USAGE_VARIANTS = ["no_pointer", "pointer_missing_file", "pointer_without_usage"]


@pytest.mark.parametrize("variant", NO_USAGE_VARIANTS)
def test_token_budget_fails_closed_when_run_has_no_usage(tmp_path: Path, variant: str) -> None:
    report = _no_usage_report(tmp_path, variant)
    m = NexusMission(mission_id="M", objective="o", budget={"max_tokens": 500.0})
    assert m.check_telemetry_budget() is True  # nothing run yet

    m.add_tokens_from_receipt_file(report)

    assert m.check_telemetry_budget() is False, (
        "max_tokens is set but the run reported no usage: budget is unknown and must not pass"
    )
    # The unknown-budget state survives persistence (a later `mission start` reloads from disk).
    m.persist(tmp_path)
    reloaded = NexusMission.load(tmp_path)
    assert reloaded is not None
    assert reloaded.check_telemetry_budget() is False


@pytest.mark.parametrize("variant", NO_USAGE_VARIANTS)
def test_missions_without_token_limit_unaffected(tmp_path: Path, variant: str) -> None:
    report = _no_usage_report(tmp_path, variant)
    for budget in ({"max_retries": 10.0}, {"max_tokens": 0.0, "max_retries": 10.0}):
        m = NexusMission(mission_id="M", objective="o", budget=dict(budget))
        m.add_tokens_from_receipt_file(report)
        assert m.check_telemetry_budget() is True


def test_usage_recorded_in_unified_runtime_receipt_is_counted(tmp_path: Path) -> None:
    receipt = _write(
        tmp_path / "unified_runtime" / "task.json",
        {
            "task_id": "t",
            "online": {
                "gate_passed": True,
                "response": {"provider": "x", "usage": {"total_tokens": 120}},
            },
        },
    )
    report = _run_report(tmp_path, receipt)
    m = NexusMission(mission_id="M", objective="o", budget={"max_tokens": 500.0})

    m.add_tokens_from_receipt_file(report)

    assert m.accumulated_usage["tokens"] == 120
    assert m.check_telemetry_budget() is True  # real usage, under budget

    receipt2 = _write(
        tmp_path / "unified_runtime" / "task2.json",
        {"local": {"response": {"usage": {"input_tokens": 300, "output_tokens": 100}}}},
    )
    report2 = _write(
        tmp_path / "reports" / "run_report2.json",
        {"status": "SUCCESS", "unified_runtime_receipt_path": str(receipt2)},
    )
    m.add_tokens_from_receipt_file(report2)

    assert m.accumulated_usage["tokens"] == 520
    assert m.check_telemetry_budget() is False


def test_mission_start_does_not_keep_passing_without_usage(tmp_path: Path) -> None:
    NexusMission(mission_id="M", objective="o", budget={"max_tokens": 500.0}).persist(tmp_path)
    launches = []

    def fake_run(cmd, *a, **k):
        launches.append(cmd)
        report = Path(cmd[cmd.index("--report-file") + 1])
        _write(report, {"status": "SUCCESS", "task_pipeline_success": True})
        return MagicMock(returncode=0)

    def start():
        with (
            patch.object(cli_mod, "repo_root", tmp_path),
            patch.object(cli_mod.subprocess, "run", fake_run),
            patch.object(NexusMission, "run_fingerprint_preflight", return_value=True),
        ):
            return CliRunner().invoke(cli_mod.nexus, ["nexus", "mission", "start"])

    first = start()
    assert first.exit_code != 0, first.output
    loaded = NexusMission.load(tmp_path)
    assert loaded.status not in (
        MissionStatus.ACTIVE,
        MissionStatus.VERIFYING,
        MissionStatus.COMPLETED,
    )

    second = start()
    assert second.exit_code != 0, second.output
    assert len(launches) == 1, "a mission whose token budget is unknown must not launch another run"
