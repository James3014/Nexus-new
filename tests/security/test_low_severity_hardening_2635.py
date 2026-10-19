"""Witnesses for the #2635 low-severity hardening (SEC-006, SEC-007, SEC-011).

SEC-008/009/010 are covered next to their modules' existing tests:
tests/nexus/orchestrator/test_self_hosted_mcp_http.py,
tests/nexus/orchestrator/test_unified_mcp_gateway_http.py and
tests/nexus/orchestrator/test_unified_mcp_gateway.py.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.core.argv_command import (
    UNSUPPORTED_SYNTAX_EXIT,
    UnsupportedShellSyntax,
    run_command_string,
    split_command_chain,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

SEC_007_FILES = (
    "nexus/health/executor.py",
    "nexus/delivery/gate.py",
    "nexus/core/drone_engine.py",
    "scripts/ops/__init__.py",
    "scripts/ops/task_runner.py",
    "scripts/ops/task_scheduler.py",
    "scripts/core/guard_executor.py",
    "nexus/core/notifier.py",
)

# A command string that, under a shell, would create the marker file.
INJECTION = "echo hi; touch {marker}"


# ---------------------------------------------------------------- helper


def test_split_command_chain_supports_and_chains_and_quoting():
    assert split_command_chain("python -c \"import sys; sys.exit(2)\" && echo 'a|b'") == [
        ["python", "-c", "import sys; sys.exit(2)"],
        ["echo", "a|b"],
    ]


@pytest.mark.parametrize(
    "command",
    [
        "a; b",
        "a;b",
        "a | b",
        "a || b",
        "a > f",
        "a < f",
        "a &",
        "echo $(id)",
        "(a)",
        "a &&",
        "'unbalanced",
    ],
)
def test_split_command_chain_refuses_other_shell_syntax(command):
    with pytest.raises(UnsupportedShellSyntax):
        split_command_chain(command)


def test_run_command_string_refuses_injection_and_runs_nothing(tmp_path):
    marker = tmp_path / "pwned"
    result = run_command_string(INJECTION.format(marker=marker), cwd=tmp_path)
    assert result.returncode == UNSUPPORTED_SYNTAX_EXIT
    assert "refused" in result.stderr
    assert not marker.exists()


def test_run_command_string_chain_env_and_no_expansion(tmp_path):
    ok = run_command_string(
        f"FOO=bar {sys.executable} -c \"import os; print(os.environ['FOO'])\" && echo $HOME",
        cwd=tmp_path,
    )
    assert ok.returncode == 0
    assert ok.stdout.splitlines() == ["bar", "$HOME"]  # no variable expansion
    stopped = run_command_string("false && touch never", cwd=tmp_path)
    assert stopped.returncode != 0
    assert not (tmp_path / "never").exists()
    missing = run_command_string("definitely-not-a-command-2635", cwd=tmp_path)
    assert missing.returncode == 127


@pytest.mark.parametrize("command", ["true\nfalse", "true\rfalse", "true\x00false"])
def test_newline_cr_nul_are_refused_not_run(command, tmp_path):
    """Gemini r1 #1: a shell ran ``true\\nfalse`` as two commands (exit 1)."""
    marker = tmp_path / "pwned"
    result = run_command_string(command.replace("false", f"touch {marker}"), cwd=tmp_path)
    assert result.returncode == UNSUPPORTED_SYNTAX_EXIT
    assert not marker.exists()
    with pytest.raises(UnsupportedShellSyntax):
        split_command_chain(command)


@pytest.mark.parametrize("command", ["false # comment", "#false", "echo ok && false #x"])
def test_unquoted_comment_is_refused_not_truncated(command, tmp_path):
    """Gemini r1 #2: an unquoted ``#`` must not silently drop the rest."""
    result = run_command_string(command, cwd=tmp_path)
    assert result.returncode == UNSUPPORTED_SYNTAX_EXIT
    assert result.stdout == ""


def test_quoted_or_embedded_hash_stays_literal():
    assert split_command_chain("echo a#b '#x' \"#y\" \\#z") == [["echo", "a#b", "#x", "#y", "#z"]]


def test_quoted_and_and_is_a_literal_argument(tmp_path):
    """Gemini r1 #3: only an unquoted ``&&`` separates segments."""
    assert split_command_chain("echo '&&' \"a && b\" \\&\\& && echo x") == [
        ["echo", "&&", "a && b", "&&"],
        ["echo", "x"],
    ]
    result = run_command_string("echo '&&' false", cwd=tmp_path)
    assert (result.returncode, result.stdout) == (0, "&& false\n")


def test_only_unquoted_name_prefix_is_an_assignment(tmp_path):
    ok = run_command_string(
        f'FOO="a b" {sys.executable} -c "import os; print(os.environ[\'FOO\'])"', cwd=tmp_path
    )
    assert (ok.returncode, ok.stdout) == (0, "a b\n")
    quoted = run_command_string("'FOO=1' true", cwd=tmp_path)
    assert quoted.returncode == 127  # a shell runs 'FOO=1' as the command name


def test_sec007_files_no_longer_use_shell_true():
    for rel in SEC_007_FILES:
        tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "shell":
                        assert not (
                            isinstance(kw.value, ast.Constant) and kw.value.value is True
                        ), f"{rel}:{node.lineno} still passes shell=True"


# ---------------------------------------------------------------- SEC-007 call sites


def test_delivery_gate_verification_command_is_not_shell_interpreted(tmp_path):
    from nexus.delivery.gate import _run_verification_command

    marker = tmp_path / "pwned"
    record = _run_verification_command(INJECTION.format(marker=marker), tmp_path)
    assert record.passed is False
    assert not marker.exists()
    good = _run_verification_command(f"{sys.executable} -c \"print('ok')\"", tmp_path)
    assert good.passed is True and good.stdout.strip() == "ok"


def test_drone_bash_exec_is_not_shell_interpreted(tmp_path):
    from nexus.core.drone_engine import DroneToolBox

    marker = tmp_path / "pwned"
    box = DroneToolBox(tmp_path)
    refused = box.bash_exec(INJECTION.format(marker=marker))
    assert refused["exit_code"] == UNSUPPORTED_SYNTAX_EXIT
    assert not marker.exists()
    assert box.bash_exec("echo work") == {"exit_code": 0, "stdout": "work\n", "stderr": ""}


def test_health_executor_safe_action_is_not_shell_interpreted(tmp_path):
    from nexus.health.executor import RepairExecutor

    marker = tmp_path / "pwned"
    action = type("Action", (), {"id": "a1", "run": INJECTION.format(marker=marker)})()
    return_codes: dict[str, int] = {}
    executed, _notes, ok = RepairExecutor(tmp_path)._execute_safe_actions(
        [action], lambda: None, return_codes
    )
    assert executed == ["a1"]
    assert return_codes["a1"] == UNSUPPORTED_SYNTAX_EXIT
    assert ok is False
    assert not marker.exists()


def test_anti_drift_historical_test_is_not_shell_interpreted(tmp_path):
    from scripts.ops import _run_anti_drift_gate

    marker = tmp_path / "pwned"
    report = _run_anti_drift_gate(
        tmp_path,
        {"historical_tests": [{"name": "inj", "command": INJECTION.format(marker=marker)}]},
        tmp_path / "report.json",
    )
    assert report["gate_passed"] is False
    assert not marker.exists()


def test_task_runner_run_shell_is_not_shell_interpreted(tmp_path):
    from scripts.ops.task_runner import run_shell

    marker = tmp_path / "pwned"
    rc, _out, _err = run_shell(INJECTION.format(marker=marker), 10, cwd=tmp_path)
    assert rc == UNSUPPORTED_SYNTAX_EXIT
    assert not marker.exists()
    rc, out, _err = run_shell(
        f"{sys.executable} -c \"import os; print(os.environ['NEXUS_FORCE_RUN'])\"", 10, cwd=tmp_path
    )
    assert (rc, out.strip()) == (0, "1")


def test_task_scheduler_run_command_uses_argv_runner():
    # Importing task_scheduler configures file logging under the repo, so pin the source.
    source = (REPO_ROOT / "scripts/ops/task_scheduler.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    run_command = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_command"
    )
    calls = {ast.unparse(n.func) for n in ast.walk(run_command) if isinstance(n, ast.Call)}
    assert "run_command_string" in calls
    assert "subprocess.run" not in calls


def _guard_executor():
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from core import guard_executor

    return guard_executor


def test_guard_executor_rm_preview_is_argv_only():
    guard = _guard_executor()
    assert guard.preview_argv_for_rm(["rm", "-rf", "x; touch pwned", "--", "-odd"]) == [
        "ls",
        "-ld",
        "--",
        "x; touch pwned",
        "-odd",
    ]
    assert guard.preview_argv_for_rm(["rm", "-f", "a"]) == ["ls", "-l", "--", "a"]
    assert guard.preview_argv_for_rm(["git", "rm", "-r", "a"]) is None


def test_guard_executor_runs_non_rm_command_without_shell(tmp_path):
    marker = tmp_path / "pwned"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/core/guard_executor.py"),
            "echo",
            f"hi; touch {marker}",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert not marker.exists(), proc.stdout + proc.stderr
    assert f"hi; touch {marker}" in proc.stdout


# ---------------------------------------------------------------- SEC-006


def test_notifier_passes_title_and_message_as_argv(monkeypatch):
    from nexus.core import notifier

    hostile = 'x" & (do shell script "touch /tmp/pwned-2635") & "'
    argv = notifier.build_notification_argv(hostile, hostile)
    assert argv[:2] == ["osascript", "-e"]
    assert "on run argv" in argv[2]
    assert hostile not in argv[2]
    assert argv[3:] == [f"🛡️ Nexus {hostile}", hostile]

    captured = []
    monkeypatch.setattr(notifier, "_side_effects_suppressed", lambda: False)
    monkeypatch.setattr(notifier.subprocess, "run", lambda cmd, **kw: captured.append((cmd, kw)))
    monkeypatch.setattr(notifier.subprocess, "Popen", lambda cmd, **kw: captured.append((cmd, kw)))
    notifier.NexusNotifier._system_ui_notify("T", hostile)
    notifier.NexusNotifier._voice_alert(hostile)
    assert captured[0][0] == notifier.build_notification_argv("T", hostile)
    assert captured[1][0] == ["say", hostile]
    assert all(not kw.get("shell") for _cmd, kw in captured)


# ---------------------------------------------------------------- SEC-011


def test_secure_sync_serve_defaults_to_loopback():
    from nexus.security.secure_sync import SecureRegistrySync

    assert inspect.signature(SecureRegistrySync.serve).parameters["host"].default == "127.0.0.1"


def test_legacy_guard_executor_runs_non_rm_command_without_shell(tmp_path):
    # Second sweep (#2635): scripts/guard_executor.py is the older copy of the core guard.
    marker = tmp_path / "pwned"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/guard_executor.py"),
            "echo",
            f"hi; touch {marker}",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert not marker.exists(), proc.stdout + proc.stderr
    assert f"hi; touch {marker}" in proc.stdout


def test_legacy_guard_executor_rm_preview_is_argv_only(tmp_path):
    marker = tmp_path / "pwned"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/guard_executor.py"),
            "rm",
            "-rf",
            f"x; touch {marker}",
        ],
        cwd=tmp_path,
        input="0\n",  # wrong challenge: the rm itself never runs
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 1
    assert not marker.exists(), proc.stdout + proc.stderr


def test_morning_report_voice_notify_has_no_shell():
    tree = ast.parse((REPO_ROOT / "scripts/core/morning_report.py").read_text(encoding="utf-8"))
    notify = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_voice_notify"
    )
    for node in ast.walk(notify):
        if isinstance(node, ast.Call):
            assert not any(kw.arg == "shell" for kw in node.keywords), ast.unparse(node)
