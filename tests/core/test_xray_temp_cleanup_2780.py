"""Completed xray reports remain readable, then expire without touching active runs."""

import os
import time
from pathlib import Path

from nexus.core import capability_executor_registry as registry
from nexus.core.belief_contracts import CapabilityExecutionPlan


def _plan(workspace: Path) -> CapabilityExecutionPlan:
    (workspace / "pkg").mkdir(parents=True, exist_ok=True)
    (workspace / "pkg" / "task.py").write_text("def task_symbol():\n    return 1\n")
    return CapabilityExecutionPlan(
        plan_id="xray-cleanup",
        task_id="xray-cleanup",
        constraints={"workspace_root": str(workspace), "xray_targets": ["pkg/task.py"]},
    )


def test_completed_xray_run_is_pruned_after_retention(tmp_path, monkeypatch) -> None:
    os_temp = tmp_path / "os-temp"
    os_temp.mkdir()
    monkeypatch.setattr(registry.tempfile, "gettempdir", lambda: str(os_temp))
    plan = _plan(tmp_path / "workspace")

    first = registry._exec_xray(plan, "scan")
    assert first.gate_passed
    old_report = Path(first.outcome["output_paths"][0])
    done = old_report.parent / "done"
    assert old_report.is_file() and done.is_file()
    old_time = time.time() - registry._XRAY_RETENTION_SECONDS - 60
    os.utime(done, (old_time, old_time))

    second = registry._exec_xray(plan, "scan again")
    assert second.gate_passed
    assert not old_report.parent.exists()
    assert Path(second.outcome["output_paths"][0]).is_file()


def test_recent_report_and_unmarked_active_run_survive_prune(tmp_path, monkeypatch) -> None:
    os_temp = tmp_path / "os-temp"
    os_temp.mkdir()
    monkeypatch.setattr(registry.tempfile, "gettempdir", lambda: str(os_temp))
    plan = _plan(tmp_path / "workspace")

    first = registry._exec_xray(plan, "scan")
    assert first.gate_passed
    report = Path(first.outcome["output_paths"][0])
    active = report.parent.parent / "run-active"
    active.mkdir(mode=0o700)
    (active / "xray_report_full.md").write_text("active")
    old_time = time.time() - registry._XRAY_RETENTION_SECONDS - 60
    os.utime(active, (old_time, old_time))

    second = registry._exec_xray(plan, "scan again")
    assert second.gate_passed
    assert "task_symbol" in report.read_text()
    assert (active / "xray_report_full.md").read_text() == "active"
    assert Path(second.outcome["output_paths"][0]).is_file()


def test_symlinked_private_parent_fails_without_touching_target(tmp_path, monkeypatch) -> None:
    os_temp = tmp_path / "os-temp"
    os_temp.mkdir()
    monkeypatch.setattr(registry.tempfile, "gettempdir", lambda: str(os_temp))
    target = tmp_path / "other"
    target.mkdir()
    sentinel = target / "keep"
    sentinel.write_text("unchanged")
    (os_temp / f"nexus-xray-runs-{os.getuid()}").symlink_to(target, target_is_directory=True)

    receipt = registry._exec_xray(_plan(tmp_path / "workspace"), "scan")

    assert receipt.gate_passed is False
    assert sentinel.read_text() == "unchanged"
    assert list(target.iterdir()) == [sentinel]
