from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "scripts" / "ops" / "nexus-dsh-workflow"


def test_git_host_timeout_kills_process_group(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    pid_file = tmp_path / "descendant.pid"
    fake_git = fake_bin / "git"
    fake_git.write_text(
        '#!/bin/sh\nsleep 30 &\necho $! > "$FAKE_DESCENDANT_PID"\nwait\n',
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    worker = (
        "import importlib.machinery, json, pathlib; "
        f"m=importlib.machinery.SourceFileLoader('workflow_timeout_test', {str(WORKFLOW)!r}).load_module(); "
        "m.HOST_SUBPROCESS_TIMEOUT_SECONDS=0.5; "
        f"p=m._git(pathlib.Path({str(tmp_path)!r}), 'status'); "
        "print(json.dumps({'returncode':p.returncode,'stderr':p.stderr.decode(errors='replace')}))"
    )
    env = dict(os.environ)
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
    env["FAKE_DESCENDANT_PID"] = str(pid_file)
    started = time.monotonic()
    proc = subprocess.Popen(
        [sys.executable, "-c", worker],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise AssertionError("host Git call did not return by its configured timeout")

    assert time.monotonic() - started < 2
    assert proc.returncode == 0, stderr
    assert json.loads(stdout)["returncode"] == 124
    descendant_pid = int(pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        try:
            os.kill(descendant_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        raise AssertionError("Git descendant survived host timeout")


def _load_workflow():
    import importlib.machinery

    return importlib.machinery.SourceFileLoader(
        "workflow_timeout_regression", str(WORKFLOW)
    ).load_module()


def test_host_timeout_preserves_sigterm_output_and_skips_sigkill(
    tmp_path: Path, monkeypatch
) -> None:
    import signal as signal_module

    workflow = _load_workflow()
    monkeypatch.setattr(workflow, "HOST_SUBPROCESS_TIMEOUT_SECONDS", 0.01)
    calls = []

    def record_killpg(pid, sig):
        calls.append(sig)

    monkeypatch.setattr(workflow.os, "killpg", record_killpg)

    class FakeProcess:
        pid = 123
        stdout = stderr = None

        def __init__(self, *_args, **_kwargs):
            self.communicates = 0

        def communicate(self, timeout=None):
            self.communicates += 1
            if self.communicates == 1:
                raise subprocess.TimeoutExpired("fake", timeout)
            if self.communicates == 2:
                return b"term-out", b"term-err"
            return None, None

        def wait(self):
            return 0

    monkeypatch.setattr(workflow.subprocess, "Popen", FakeProcess)
    result = workflow._host_run(
        [sys.executable, "-c", "pass"],
        capture_output=True,
    )
    assert result.returncode == 124
    assert result.stdout == b"term-out"
    assert result.stderr == b"term-err"
    assert signal_module.SIGKILL not in calls


def test_host_run_rejects_check_true() -> None:
    workflow = _load_workflow()
    try:
        workflow._host_run([sys.executable, "-c", "pass"], check=True)
    except ValueError:
        pass
    else:
        raise AssertionError("check=True must not be silently ignored")


def test_classifier_scratch_fails_on_git_timeout(monkeypatch, tmp_path: Path) -> None:
    workflow = _load_workflow()

    def make_scratch(**_):
        path = tmp_path / "scratch"
        path.mkdir()
        return str(path)

    monkeypatch.setattr(workflow.tempfile, "mkdtemp", make_scratch)

    def fail_git(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 124, b"", b"timeout")

    monkeypatch.setattr(workflow, "_host_run", fail_git)
    try:
        workflow._classifier_scratch()
    except workflow.DshWorkflowError as exc:
        assert exc.code == "CLASSIFIER_SCRATCH_GIT_FAILED"
    else:
        raise AssertionError("classifier scratch must fail closed on timed out git")


def test_materialize_base_tree_fails_on_git_show_timeout(monkeypatch, tmp_path: Path) -> None:
    workflow = _load_workflow()
    monkeypatch.setattr(
        workflow,
        "_host_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 124, b"", b"timeout"),
    )
    try:
        workflow._materialize_base_tree(tmp_path, "base", ["file.py"], tmp_path / "out")
    except workflow.DshWorkflowError as exc:
        assert exc.code == "BASE_TREE_READ_FAILED"
    else:
        raise AssertionError("git show timeout must not mean file absence")


def test_standalone_clone_git_operations_use_long_timeout_and_name_it(
    monkeypatch, tmp_path: Path
) -> None:
    workflow = _load_workflow()
    calls = []
    source = Path.cwd()
    base = "a" * 40

    def record_git(cwd, *args, timeout=None):
        calls.append((args, timeout))
        if args[0] == "clone":
            return subprocess.CompletedProcess(args, 124, "", "timed out")
        if args[:1] == ("rev-parse",):
            return subprocess.CompletedProcess(args, 0, f"{source}\n{source / '.git'}\n", "")
        if args[:2] == ("remote", "get-url"):
            return subprocess.CompletedProcess(
                args, 0, "https://github.com/James3014/Nexus-new\n", ""
            )
        if args[:1] == ("worktree",):
            return subprocess.CompletedProcess(args, 0, f"worktree {source}\n", "")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(workflow, "_identity_git", record_git)
    monkeypatch.setattr(workflow, "_under_temp_grant", lambda _path: None)
    try:
        workflow.prepare_standalone_clone(
            repository="James3014/Nexus-new",
            source_repo_root=source,
            base_revision=base,
            target=tmp_path / "clone",
        )
    except workflow.DshWorkflowError as exc:
        assert exc.code == "STANDALONE_CLONE_FAILED"
        assert "timeout 300s" in str(exc)
    else:
        raise AssertionError("timed out clone must fail")

    clone_call = next((args, timeout) for args, timeout in calls if args[0] == "clone")
    assert clone_call[1] == 300

    calls.clear()
    target = tmp_path / "clone-success"

    def complete_git(cwd, *args, timeout=None):
        calls.append((args, timeout))
        if args[:1] == ("rev-parse",):
            return subprocess.CompletedProcess(args, 0, f"{source}\n{source / '.git'}\n", "")
        if args[:2] == ("remote", "get-url"):
            return subprocess.CompletedProcess(
                args, 0, "https://github.com/James3014/Nexus-new\n", ""
            )
        if args[:1] == ("worktree",):
            return subprocess.CompletedProcess(args, 0, f"worktree {source}\n", "")
        if args[:1] == ("cat-file",) and cwd == target:
            return subprocess.CompletedProcess(args, 1, "", "missing")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(workflow, "_identity_git", complete_git)
    monkeypatch.setattr(workflow, "_validate_standalone_target", lambda *_args, **_kwargs: {})
    workflow.prepare_standalone_clone(
        repository="James3014/Nexus-new",
        source_repo_root=source,
        base_revision=base,
        target=target,
    )
    operations = {args[0] for args, _ in calls if args[0] in {"clone", "fetch", "-c"}}
    assert operations == {"clone", "fetch", "-c"}
    assert all(timeout == 300 for args, timeout in calls if args[0] in operations)


def test_host_run_returns_124_when_setsid_grandchild_holds_pipes(tmp_path: Path) -> None:
    workflow = _load_workflow()
    pidfile = tmp_path / "grandchild.pid"
    code = (
        "import os, subprocess, sys\n"
        "p = subprocess.Popen([sys.executable, '-c', 'import os, time; os.setsid(); time.sleep(4)'])\n"
        f"open({str(pidfile)!r}, 'w').write(str(p.pid))\n"
        "import time; time.sleep(60)\n"
    )
    started = time.monotonic()
    try:
        result = workflow._host_run([sys.executable, "-c", code], capture_output=True, timeout=0.3)
        assert result.returncode == 124
        assert time.monotonic() - started < 3.5
    finally:
        if pidfile.exists():
            try:
                os.kill(int(pidfile.read_text()), signal.SIGKILL)
            except (ProcessLookupError, ValueError, PermissionError):
                pass


def test_host_run_returns_124_when_killpg_permission_denied(monkeypatch) -> None:
    workflow = _load_workflow()

    def deny(_pid, _sig):
        raise PermissionError

    monkeypatch.setattr(workflow.os, "killpg", deny)
    procs = []
    real_popen = subprocess.Popen

    def popen(*a, **k):
        proc = real_popen(*a, **k)
        procs.append(proc)
        return proc

    monkeypatch.setattr(workflow.subprocess, "Popen", popen)
    try:
        result = workflow._host_run(
            [sys.executable, "-c", "import time; time.sleep(30)"], capture_output=True, timeout=0.2
        )
        assert result.returncode == 124
    finally:
        for proc in procs:
            proc.kill()
            proc.wait()
