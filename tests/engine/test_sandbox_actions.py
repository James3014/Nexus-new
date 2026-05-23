from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

import scripts.engine.nexus_cli as cli_mod
from scripts.engine.commands.exception_translation import NexusCliActionError
from scripts.engine.commands.sandbox_actions import (
    SandboxRunResult,
    render_sandbox_run_result,
    run_sandbox_task,
)


class FakeSandboxRunner:
    def __init__(self, result: dict[str, object]):
        self.result = result
        self.calls: list[str] = []

    def run_task(self, task: str) -> dict[str, object]:
        self.calls.append(task)
        return self.result


def test_run_sandbox_task_returns_success_view(tmp_path: Path):
    runner = FakeSandboxRunner({"success": True, "workspace": "sandbox-a"})

    result = run_sandbox_task(
        tmp_path,
        "verify isolated command",
        runner_factory=lambda root: runner,
    )

    assert runner.calls == ["verify isolated command"]
    assert result == SandboxRunResult(
        task="verify isolated command",
        success=True,
        raw_result={"success": True, "workspace": "sandbox-a"},
    )
    assert render_sandbox_run_result(result) == [
        "🏗️ [Sandbox] Execution finished. Success: True"
    ]


def test_run_sandbox_task_fails_closed_without_runner_interface(tmp_path: Path):
    class RunnerWithoutTask:
        pass

    with pytest.raises(NexusCliActionError, match="does not expose run_task"):
        run_sandbox_task(
            tmp_path,
            "verify isolated command",
            runner_factory=lambda root: RunnerWithoutTask(),
        )


def test_sandbox_run_cli_uses_action_result(monkeypatch, tmp_path: Path):
    calls = []

    def fake_run_sandbox_task(root: Path, task: str):
        calls.append((root, task))
        return SandboxRunResult(task=task, success=True, raw_result={"success": True})

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "run_sandbox_task", fake_run_sandbox_task)

    result = CliRunner().invoke(
        cli_mod.nexus,
        ["nexus", "sandbox", "run", "--task", "verify isolated command"],
    )

    assert result.exit_code == 0
    assert calls == [(tmp_path, "verify isolated command")]
    assert "🏗️ [Sandbox] Execution finished. Success: True" in result.output
