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


def test_caller_elastic_profile_still_denies_network(tmp_path, monkeypatch):
    root = _project(tmp_path)
    fake_exec = tmp_path / "sandbox-exec"
    fake_exec.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_exec.chmod(0o755)
    monkeypatch.setattr(sandbox_runner_mod, "SANDBOX_EXEC", str(fake_exec))
    monkeypatch.setattr(sandbox_runner_mod.sys, "platform", "darwin")
    seen: list[list[str]] = []

    def _capture(argv, *_args, **_kwargs):
        seen.append(list(argv))
        return _run_success()

    monkeypatch.setattr(sandbox_runner_mod, "run_reaping_process_group", _capture)
    permissive = "(version 1)\n(allow default)"
    result = SandboxRunner(root).run_task(
        "probe", command=[sys.executable, "probe.py"], elastic_profile=permissive
    )
    profiles = [argv[2] for argv in seen if len(argv) > 2 and argv[1] == "-p"]
    assert profiles, seen
    # SBPL: the last matching rule wins, so the denial must come after the caller's rules.
    assert profiles[0].index("(deny network*)") > profiles[0].index("(allow default)")
    assert result["network_allowed"] is False


def test_isolation_requiring_callers_pass_require_os_sandbox(tmp_path):
    from scripts.engine.commands.sandbox_actions import run_sandbox_task

    calls: list[dict] = []

    class _Runner:
        def run_task(self, task, **kwargs):
            calls.append(kwargs)
            return {"success": True}

    run_sandbox_task(tmp_path, "t", command="echo hi", runner_factory=lambda _root: _Runner())
    assert calls and calls[0].get("require_os_sandbox") is True

    source = Path("nexus/core/capability_executor_registry.py").read_text(encoding="utf-8")
    start = source.index("result = inst.run_task(")
    assert "require_os_sandbox=True" in source[start : start + 400]
