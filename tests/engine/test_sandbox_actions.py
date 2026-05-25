from __future__ import annotations

import hashlib
import sys
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
        self.calls: list[dict[str, object]] = []

    def run_task(self, task: str, **kwargs: object) -> dict[str, object]:
        self.calls.append({"task": task, **kwargs})
        return self.result


def test_run_sandbox_task_returns_success_view(tmp_path: Path):
    runner = FakeSandboxRunner({"success": True, "workspace": "sandbox-a"})

    result = run_sandbox_task(
        tmp_path,
        "verify isolated command",
        command=["/bin/echo", "ok"],
        runner_factory=lambda root: runner,
    )

    assert runner.calls == [
        {
            "task": "verify isolated command",
            "command": ["/bin/echo", "ok"],
            "cwd": ".",
            "timeout_sec": 60,
            "output_file": None,
            "cleanup": True,
        }
    ]
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
            command=["/bin/echo", "ok"],
            runner_factory=lambda root: RunnerWithoutTask(),
        )


def test_default_sandbox_runner_requires_explicit_command(tmp_path: Path):
    with pytest.raises(NexusCliActionError, match="requires an explicit command"):
        run_sandbox_task(tmp_path, "verify isolated command")


def test_default_sandbox_runner_executes_local_command_and_collects_output(tmp_path: Path):
    script = (
        "from pathlib import Path; "
        "Path('out').mkdir(); "
        "Path('out/result.txt').write_text('sandbox-ok', encoding='utf-8'); "
        "print('stdout-ok')"
    )

    result = run_sandbox_task(
        tmp_path,
        "verify isolated command",
        command=[sys.executable, "-c", script],
        output_file="out/result.txt",
        timeout_sec=5,
    )

    artifact_path = Path(str(result.raw_result["output_artifact_path"]))
    workspace_path = Path(str(result.raw_result["workspace_path"]))
    assert result.success is True
    assert result.raw_result["exit_code"] == 0
    assert result.raw_result["stdout"].strip() == "stdout-ok"
    assert artifact_path.read_text(encoding="utf-8") == "sandbox-ok"
    assert result.raw_result["output_artifact"] == {
        "sandbox_relative_path": "out/result.txt",
        "artifact_path": str(artifact_path),
        "sha256": hashlib.sha256(b"sandbox-ok").hexdigest(),
        "size_bytes": len("sandbox-ok"),
    }
    assert result.raw_result["workspace_source"] == "local_project_copy"
    assert result.raw_result["cleanup"] is True
    assert not workspace_path.exists()


def test_default_sandbox_runner_blocks_cwd_escape_before_command_execution(tmp_path: Path):
    marker = tmp_path / "escaped.txt"

    result = run_sandbox_task(
        tmp_path,
        "blocked escape",
        command=[sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')"],
        cwd="../outside",
        timeout_sec=5,
    )

    assert result.success is False
    assert result.raw_result["exit_code"] == 126
    assert result.raw_result["error"] == "cwd_outside_sandbox_workspace"
    assert not marker.exists()


def test_default_sandbox_runner_does_not_follow_source_symlinks(tmp_path: Path):
    outside_file = tmp_path.parent / f"{tmp_path.name}-outside-secret.txt"
    outside_file.write_text("secret", encoding="utf-8")
    try:
        (tmp_path / "linked_secret.txt").symlink_to(outside_file)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")

    result = run_sandbox_task(
        tmp_path,
        "do not copy symlink target",
        command=[
            sys.executable,
            "-c",
            "from pathlib import Path; print(Path('linked_secret.txt').exists())",
        ],
        timeout_sec=5,
    )

    assert result.success is True
    assert result.raw_result["stdout"].strip() == "False"


def test_default_sandbox_runner_does_not_copy_source_git_hooks(tmp_path: Path):
    hooks_dir = tmp_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "pre-commit").write_text("echo should-not-copy", encoding="utf-8")

    result = run_sandbox_task(
        tmp_path,
        "do not copy hooks",
        command=[
            sys.executable,
            "-c",
            "from pathlib import Path; print(Path('.git/hooks/pre-commit').exists())",
        ],
        timeout_sec=5,
    )

    assert result.success is True
    assert result.raw_result["stdout"].strip() == "False"
    assert result.raw_result["hook_policy"] == {
        "source_git_metadata_copied": False,
        "git_hooks_copied": False,
        "git_hooks_allowed": False,
    }


def test_default_sandbox_runner_blocks_python_external_socket(tmp_path: Path):
    result = run_sandbox_task(
        tmp_path,
        "block external python socket",
        command=[
            sys.executable,
            "-c",
            "import socket; socket.create_connection(('example.com', 80), timeout=1)",
        ],
        timeout_sec=5,
    )

    assert result.success is False
    expected_mode = "os_level_sandbox_exec" if sys.platform == "darwin" else "python_sitecustomize"
    assert result.raw_result["network_barrier"]["mode"] == expected_mode
    assert "Nexus sandbox blocked external network host: example.com:80" in result.raw_result["stderr"]


def test_sandbox_run_cli_uses_action_result(monkeypatch, tmp_path: Path):
    calls = []

    def fake_run_sandbox_task(root: Path, task: str, **kwargs: object):
        calls.append((root, task, kwargs))
        return SandboxRunResult(task=task, success=True, raw_result={"success": True})

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "run_sandbox_task", fake_run_sandbox_task)

    result = CliRunner().invoke(
        cli_mod.nexus,
        [
            "nexus",
            "sandbox",
            "run",
            "--task",
            "verify isolated command",
            "--command",
            "/bin/echo ok",
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        (
            tmp_path,
            "verify isolated command",
            {
                "command": ["/bin/echo", "ok"],
                "cwd": ".",
                "timeout_sec": 60,
                "output_file": None,
                "cleanup": True,
            },
        )
    ]
    assert "🏗️ [Sandbox] Execution finished. Success: True" in result.output


def test_sandbox_run_cli_passes_physical_contract_options(monkeypatch, tmp_path: Path):
    calls = []

    def fake_run_sandbox_task(root: Path, task: str, **kwargs: object):
        calls.append((root, task, kwargs))
        return SandboxRunResult(task=task, success=True, raw_result={"success": True})

    monkeypatch.setattr(cli_mod, "repo_root", tmp_path)
    monkeypatch.setattr(cli_mod, "run_sandbox_task", fake_run_sandbox_task)

    result = CliRunner().invoke(
        cli_mod.nexus,
        [
            "nexus",
            "sandbox",
            "run",
            "--task",
            "verify isolated command",
            "--command",
            f"{sys.executable} -c 'print(42)'",
            "--cwd",
            "demo",
            "--timeout-sec",
            "7",
            "--output-file",
            "out/result.txt",
            "--keep-workspace",
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        (
            tmp_path,
            "verify isolated command",
            {
                "command": [sys.executable, "-c", "print(42)"],
                "cwd": "demo",
                "timeout_sec": 7,
                "output_file": "out/result.txt",
                "cleanup": False,
            },
        )
    ]


def test_default_sandbox_runner_os_level_network_barrier_blocks_non_python_commands(tmp_path: Path):
    # 此測試僅在支援 sandbox-exec 的 macOS 上執行實體網路阻斷驗證，其它系統跳過
    if sys.platform != "darwin":
        pytest.skip("OS-level network barrier utilizing sandbox-exec is only supported on macOS (darwin).")

    # 執行一個試圖存取外部主機的非 Python shell 命令
    result = run_sandbox_task(
        tmp_path,
        "block external shell curl",
        command=["curl", "-I", "https://www.google.com"],
        timeout_sec=5,
    )

    # 斷言其執行失敗
    assert result.success is False
    assert result.raw_result["network_allowed"] is False
    assert result.raw_result["network_barrier"]["mode"] == "os_level_sandbox_exec"
    assert result.raw_result["network_barrier"]["loopback_allowed"] is False
    assert result.raw_result["network_barrier"]["external_allowed"] is False
    # 退出碼應不為 0（在 sandbox-exec 封鎖下通常 curl 回傳 6 或 Operation not permitted 造成的失敗）
    assert result.raw_result["exit_code"] != 0

