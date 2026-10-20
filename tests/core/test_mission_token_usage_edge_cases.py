"""Edge cases of the #2768 token budget found in review (#2822): a report that exists but
cannot be read or parsed fails closed, and only this run's unified receipt counts."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from nexus.core.mission_contracts import NexusMission


def _mission() -> NexusMission:
    return NexusMission(mission_id="M", objective="o", budget={"max_tokens": 500.0})


@pytest.mark.parametrize(
    "content",
    [b"\xff\xfe not utf-8", b"[" * 100_000 + b"]" * 100_000, b"{not json"],
    ids=["non_utf8", "deeply_nested", "invalid_json"],
)
def test_unparsable_report_fails_closed(tmp_path: Path, content: bytes) -> None:
    report = tmp_path / "run_report.json"
    report.write_bytes(content)
    m = _mission()
    assert m.add_tokens_from_receipt_file(report) == 0.0
    assert m.check_telemetry_budget() is False


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
def test_unreadable_report_fails_closed(tmp_path: Path) -> None:
    report = tmp_path / "run_report.json"
    report.write_text(json.dumps({"usage": {"total_tokens": 10}}), encoding="utf-8")
    report.chmod(0)
    try:
        m = _mission()
        m.add_tokens_from_receipt_file(report)
        assert m.check_telemetry_budget() is False
    finally:
        report.chmod(0o600)


def test_missing_report_leaves_budget_unchanged(tmp_path: Path) -> None:
    m = _mission()
    assert m.add_tokens_from_receipt_file(tmp_path / "absent.json") == 0.0
    assert m.check_telemetry_budget() is True


def _receipt(path: Path, task_id: str, tokens: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"task_id": task_id, "usage": {"total_tokens": tokens}}), encoding="utf-8"
    )
    return path


def test_receipt_of_another_run_is_not_counted(tmp_path: Path) -> None:
    stale = _receipt(tmp_path / "runtime" / "old.json", "old-task", 1)
    report = tmp_path / "reports" / "run_report.json"
    report.parent.mkdir()
    report.write_text(
        json.dumps({
            "unified_runtime_receipt_path": str(stale),
            "unified_runtime_task_id": "new-task",
        }),
        encoding="utf-8",
    )
    m = _mission()
    assert m.add_tokens_from_receipt_file(report) == 0.0
    assert m.check_telemetry_budget() is False


def test_relative_pointer_resolves_against_the_report_directory_only(
    tmp_path: Path, monkeypatch
) -> None:
    reports = tmp_path / "reports"
    _receipt(reports / "runtime.json", "t", 40)
    _receipt(tmp_path / "elsewhere" / "runtime.json", "t", 9000)
    report = reports / "run_report.json"
    report.write_text(
        json.dumps({"unified_runtime_receipt_path": "runtime.json"}), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path / "elsewhere")
    m = _mission()
    assert m.add_tokens_from_receipt_file(report) == 40.0
    assert m.check_telemetry_budget() is True


def test_symlinked_receipt_is_not_followed(tmp_path: Path) -> None:
    target = _receipt(tmp_path / "outside.json", "t", 40)
    link = tmp_path / "reports" / "runtime.json"
    link.parent.mkdir()
    link.symlink_to(target)
    report = tmp_path / "reports" / "run_report.json"
    report.write_text(json.dumps({"unified_runtime_receipt_path": str(link)}), encoding="utf-8")
    m = _mission()
    assert m.add_tokens_from_receipt_file(report) == 0.0
    assert m.check_telemetry_budget() is False


def test_dangling_report_symlink_fails_closed(tmp_path: Path) -> None:
    report = tmp_path / "run_report.json"
    report.symlink_to(tmp_path / "gone.json")
    m = _mission()
    assert m.add_tokens_from_receipt_file(report) == 0.0
    assert m.check_telemetry_budget() is False


def test_pointer_with_nul_fails_closed(tmp_path: Path) -> None:
    report = tmp_path / "run_report.json"
    report.write_text(
        json.dumps({"unified_runtime_receipt_path": "a\u0000b.json"}), encoding="utf-8"
    )
    m = _mission()
    assert m.add_tokens_from_receipt_file(report) == 0.0
    assert m.check_telemetry_budget() is False
