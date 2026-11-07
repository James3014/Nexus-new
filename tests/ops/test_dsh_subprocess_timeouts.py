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
