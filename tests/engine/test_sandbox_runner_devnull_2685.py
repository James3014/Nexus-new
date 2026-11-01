"""#2685: `nexus sandbox run` (SandboxRunner) must be able to run pytest.

Its sandbox-exec profile did not allow writing /dev/null, so every pytest run stopped with
INTERNALERROR (exit 3) on macOS.  The profile-text tests run on every platform; the run
test executes everywhere and, on macOS with sandbox-exec, exercises the real OS barrier.
"""

from __future__ import annotations

import sys
from pathlib import Path

import nexus.engine.sandbox_runner as sandbox_runner
from nexus.engine.sandbox_runner import SandboxRunner

DEVICE_RULE = (
    '(allow file-write* (literal "/dev/null") (literal "/dev/tty") (literal "/dev/dtracehelper"))'
)

PYTEST = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]


def _project(tmp_path: Path, assertion: str) -> Path:
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    (root / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (root / "tests/test_ok.py").write_text(
        f"from calc import add\n\ndef test_add():\n    assert {assertion}\n"
    )
    (root / "pytest.ini").write_text("[pytest]\npythonpath = .\n")
    return root


def test_elastic_profile_allows_dev_null_writes(tmp_path):
    profile = SandboxRunner(tmp_path).build_elastic_profile(
        read_literals=["/usr"], write_literals=["/tmp"]
    )
    assert '(literal "/dev/null")' in profile
    assert DEVICE_RULE in profile.splitlines()
    # Still deny-by-default with no network.
    assert "(deny default)" in profile and "(deny network-outbound)" in profile


def test_device_write_rule_matches_sandboxed_lane():
    source = (Path(__file__).resolve().parents[2] / "nexus/engine/sandboxed_lane.py").read_text()
    assert '(literal "/dev/null") (literal "/dev/tty") (literal "/dev/dtracehelper")' in source
    assert getattr(sandbox_runner, "SANDBOX_DEVICE_WRITE_RULE", None) == DEVICE_RULE


def test_default_profile_uses_resolved_workspace_path(tmp_path, monkeypatch):
    # A symlinked project root (/var -> /private/var on macOS) must appear resolved in the
    # profile, or sandbox-exec never matches the workspace subpath.
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    (real / "a.txt").write_text("x")
    runner = SandboxRunner(link)
    captured: dict = {}

    def fake_build(read_literals=None, write_literals=None):
        captured["read"] = list(read_literals or [])
        captured["write"] = list(write_literals or [])
        return "(version 1)"

    monkeypatch.setattr(runner, "has_sandbox_exec", True)
    monkeypatch.setattr(runner, "build_elastic_profile", fake_build)

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr("nexus.engine.sandbox_runner.subprocess.run", lambda *a, **k: _Proc())
    # The task command runs through the process-group reaping runner (#3052).
    monkeypatch.setattr(
        "nexus.engine.sandbox_runner.run_reaping_process_group", lambda *a, **k: _Proc()
    )
    result = runner.run_task("profile", command=["true"], timeout_sec=5)
    workspace = Path(result["workspace_path"])
    assert str(workspace.resolve()) in captured["write"]
    assert str(workspace.resolve()) in captured["read"]
    # The working copy lives in a system temp dir outside the project since #2698.
    assert not str(workspace.resolve()).startswith(str(real.resolve()))


def test_sandbox_run_pytest_pass_exits_0_and_fail_exits_1(tmp_path):
    passing = SandboxRunner(_project(tmp_path / "pass", "add(1, 2) == 3")).run_task(
        "pytest pass", command=PYTEST, timeout_sec=120
    )
    assert passing["exit_code"] == 0, (passing["stdout"][-400:], passing["stderr"][-400:])
    assert passing["success"] is True
    failing = SandboxRunner(_project(tmp_path / "fail", "add(1, 2) == 4")).run_task(
        "pytest fail", command=PYTEST, timeout_sec=120
    )
    assert failing["exit_code"] == 1, (failing["stdout"][-400:], failing["stderr"][-400:])
    assert failing["success"] is False
    if sys.platform == "darwin" and SandboxRunner(tmp_path).has_sandbox_exec:
        # On macOS the run must really have gone through the sandbox-exec profile.
        assert passing["network_barrier"]["mode"] == "os_level_sandbox_exec"
