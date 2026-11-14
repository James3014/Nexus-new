"""#3438: SandboxRunner records whether its OS network barrier was enforced."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from nexus.engine import sandbox_runner as sandbox_runner_mod
from nexus.engine.sandbox_runner import SandboxRunner


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "probe.py").write_text("print('probe-ok')\n", encoding="utf-8")
    return root


def _run_success(*_args, **_kwargs):
    class _Proc:
        returncode = 0
        stdout = "probe-ok"
        stderr = ""

    return _Proc()


def test_missing_os_sandbox_is_not_recorded_as_network_isolated(tmp_path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.setattr(sandbox_runner_mod.sys, "platform", "linux")
    monkeypatch.setattr(sandbox_runner_mod, "run_reaping_process_group", _run_success)

    result = SandboxRunner(root).run_task("probe", command=[sys.executable, "probe.py"])
    record = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))

    assert result["success"] is True
    assert result["network_allowed"] is True
    assert result["network_barrier"]["external_allowed"] is True
    assert result["network_barrier"]["os_sandbox_enforced"] is False
    assert record["network_allowed"] is True
    assert record["network_barrier"]["external_allowed"] is True
    assert record["network_barrier"]["os_sandbox_enforced"] is False


def test_failed_os_sandbox_probe_is_not_recorded_as_network_isolated(tmp_path, monkeypatch):
    root = _project(tmp_path)
    trusted_binary = tmp_path / "sandbox-exec"
    trusted_binary.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    trusted_binary.chmod(0o755)
    monkeypatch.setattr(sandbox_runner_mod, "SANDBOX_EXEC", str(trusted_binary))
    monkeypatch.setattr(sandbox_runner_mod.sys, "platform", "darwin")

    class _FailedProbe:
        returncode = 1

    monkeypatch.setattr(
        sandbox_runner_mod.subprocess, "run", lambda *_args, **_kwargs: _FailedProbe()
    )
    monkeypatch.setattr(sandbox_runner_mod, "run_reaping_process_group", _run_success)

    result = SandboxRunner(root).run_task("probe", command=[sys.executable, "probe.py"])

    assert result["network_allowed"] is True
    assert result["network_barrier"]["external_allowed"] is True
    assert result["network_barrier"]["os_sandbox_enforced"] is False


def test_require_os_sandbox_refuses_when_unavailable(tmp_path, monkeypatch):
    root = _project(tmp_path)
    runner = SandboxRunner(root)
    monkeypatch.setattr(runner, "has_sandbox_exec", False)
    monkeypatch.setattr(
        sandbox_runner_mod,
        "run_reaping_process_group",
        lambda *_args, **_kwargs: pytest.fail("command must not execute"),
    )

    result = runner.run_task("probe", command=[sys.executable, "probe.py"], require_os_sandbox=True)

    assert result["success"] is False
    assert result["error"] == "os_sandbox_unavailable"
    assert result["network_barrier"]["os_sandbox_enforced"] is False
    assert json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))["error"] == (
        "os_sandbox_unavailable"
    )


def test_os_sandbox_records_network_isolation_when_enforced(tmp_path, monkeypatch):
    root = _project(tmp_path)
    runner = SandboxRunner(root)
    monkeypatch.setattr(runner, "has_sandbox_exec", True)
    monkeypatch.setattr(runner, "sandbox_exec_path", "/usr/bin/sandbox-exec")
    monkeypatch.setattr(sandbox_runner_mod, "run_reaping_process_group", _run_success)

    result = runner.run_task("probe", command=[sys.executable, "probe.py"])

    assert result["network_allowed"] is False
    assert result["network_barrier"]["mode"] == "os_level_sandbox_exec"
    assert result["network_barrier"]["external_allowed"] is False
    assert result["network_barrier"]["os_sandbox_enforced"] is True
