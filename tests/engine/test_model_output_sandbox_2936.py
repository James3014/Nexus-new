"""#2936: local-model output (drone BASH, local_heal verifiers) runs only inside the OS sandbox.

Where an OS barrier exists (macOS sandbox-exec) the tests prove network and writes outside the
work dir are refused; where none exists (Linux CI, NEXUS_DISABLE_OS_SANDBOX=1) they prove that
nothing runs. No test skips.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from nexus.core.argv_command import run_command_string
from nexus.core.drone_engine import DroneToolBox
from nexus.engine import model_output_sandbox as mos
from nexus.engine.sandboxed_lane import os_sandbox_available
from nexus.services.local_heal.evaluation_gate import EvaluationGate
from nexus.services.local_heal.isolated_verifier import (
    IsolatedVerifierRequest,
    run_isolated_verifier,
)

_PY = [sys.executable, "-I", "-c"]


def _marker_cmd(marker: Path) -> str:
    return f'{sys.executable} -I -c \'open("{marker}", "w").write("ran")\''


@pytest.fixture
def no_barrier(monkeypatch):
    monkeypatch.setenv("NEXUS_DISABLE_OS_SANDBOX", "1")


def test_run_command_string_prefixes_every_segment(tmp_path):
    res = run_command_string(
        "first && second", cwd=tmp_path, argv_prefix=["/bin/echo", "PFX"], timeout=10
    )
    assert res.returncode == 0
    assert res.stdout.splitlines() == ["PFX first", "PFX second"]


def test_no_barrier_runs_nothing(tmp_path, no_barrier):
    marker = tmp_path / "ran.txt"
    with pytest.raises(mos.SandboxError, match="no_os_barrier"):
        mos.run_model_argv([*_PY, f"open({str(marker)!r}, 'w')"], work_dir=tmp_path, timeout=10)
    with pytest.raises(mos.SandboxError, match="no_os_barrier"):
        mos.run_model_command_string(_marker_cmd(marker), work_dir=tmp_path, timeout=10)
    assert not marker.exists()


def test_drone_bash_fails_closed_without_barrier(tmp_path, no_barrier):
    marker = tmp_path / "ran.txt"
    out = DroneToolBox(tmp_path).bash_exec(_marker_cmd(marker))
    assert out["exit_code"] == -1
    assert "no_os_barrier" in out["stderr"]
    assert not marker.exists()


def test_isolated_verifier_blocks_without_barrier(tmp_path, no_barrier):
    marker = tmp_path / "ran.txt"
    receipt = run_isolated_verifier(
        IsolatedVerifierRequest(
            task_id="t",
            workspace_path=str(tmp_path),
            verifier_command=(*_PY, f"open({str(marker)!r}, 'w')"),
            verifier_allowed=True,
        )
    )
    assert receipt.verifier_status == "blocked"
    assert receipt.verifier_error.startswith("verifier_sandbox_unavailable")
    assert not marker.exists()


@pytest.mark.parametrize("hidden", [False, True])
def test_evaluation_gate_fails_closed_without_barrier(tmp_path, no_barrier, hidden):
    marker = tmp_path / "ran.txt"
    gate = EvaluationGate(tmp_path)
    cmd = [*_PY, f"open({str(marker)!r}, 'w')"]
    results = gate.run_hidden_verifier([cmd]) if hidden else gate.run_visible_tests([cmd])
    assert [r.passed for r in results] == [False]
    assert "no_os_barrier" in results[0].output
    assert not marker.exists()


def test_interpreter_readable_roots_reads_the_venv_and_its_base(tmp_path):
    base = tmp_path / "base"
    (base / "bin").mkdir(parents=True)
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text(f"home = {base / 'bin'}\nversion = 3.13\n")
    python = venv / "bin" / "python"
    python.write_text("")
    roots = mos.interpreter_readable_roots(str(python))
    assert roots[:2] == [venv.resolve(), base.resolve()]
    assert mos.interpreter_readable_roots("no-such-tool-2936") == []
    assert mos.interpreter_readable_roots(str(tmp_path / "python")) == []
    # A model-chosen path never widens reads; only a bare name resolved on PATH may.
    assert mos.interpreter_readable_roots(str(python), allow_absolute=False) == []
    assert mos.interpreter_readable_roots("bin/python", allow_absolute=False) == []


def test_only_python_interpreters_widen_reads(tmp_path, monkeypatch):
    prefix = tmp_path / "prefix"
    (prefix / "bin").mkdir(parents=True)
    for name in ("python3.99", "uploader"):
        tool = prefix / "bin" / name
        tool.write_text("")
        tool.chmod(0o755)
    monkeypatch.setenv("PATH", str(prefix / "bin"))
    assert mos.interpreter_readable_roots("python3.99") == [prefix.resolve()]
    assert mos.interpreter_readable_roots("uploader") == []


# --- With a real barrier: what the model's command can no longer do. Without one: it never ran.

_NET = "import socket; socket.create_connection(('169.254.169.254', 80), 3); print('CONNECTED')"


def _expect_confined_or_refused(run):
    if not os_sandbox_available():
        with pytest.raises(mos.SandboxError, match="no_os_barrier"):
            run()
        return None
    return run()


def test_network_is_denied(tmp_path):
    res = _expect_confined_or_refused(
        lambda: mos.run_model_argv([*_PY, _NET], work_dir=tmp_path, timeout=20)
    )
    if res is not None:
        assert res.returncode != 0
        assert "CONNECTED" not in res.stdout


def test_write_outside_work_dir_is_denied(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    outside = tmp_path / "outside.txt"
    inside = work / "inside.txt"
    script = f"open({str(inside)!r}, 'w').write('x'); open({str(outside)!r}, 'w').write('x')"
    res = _expect_confined_or_refused(
        lambda: mos.run_model_argv([*_PY, script], work_dir=work, timeout=20)
    )
    if res is not None:
        assert inside.exists()
        assert res.returncode != 0
    assert not outside.exists()


def test_drone_bash_cannot_reach_the_network_or_leak_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_TEST_SECRET_2936", "s3cret")
    box = DroneToolBox(tmp_path)
    env_out = box.bash_exec("/usr/bin/env")
    net_out = box.bash_exec(f'{sys.executable} -I -c "{_NET}"')
    if not os_sandbox_available():
        assert env_out["exit_code"] == -1 and net_out["exit_code"] == -1
        return
    assert env_out["exit_code"] == 0
    assert "s3cret" not in env_out["stdout"]
    assert net_out["exit_code"] != 0
    assert "CONNECTED" not in net_out["stdout"]
