"""#2945: micro_verifier and the reproduction run execute model-written code only inside the OS
sandbox, and the env-recipe pip install never takes a package name from model output.

Where an OS barrier exists (macOS sandbox-exec) the tests prove writes outside the repo, network
and the host environment are out of reach while a legitimate run still works; where none exists
(Linux CI, NEXUS_DISABLE_OS_SANDBOX=1) they prove nothing runs. No test skips.
"""

from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nexus.engine.model_output_sandbox import SandboxError, run_model_argv
from nexus.engine.sandboxed_lane import os_sandbox_available
from nexus.services.local_heal.interface import ReproductionInput
from nexus.services.local_heal.micro_verifier import MicroVerifier
from nexus.services.local_heal.phases import reproduction as reproduction_phase
from nexus.services.local_heal.phases.reproduction import ReproductionPhase
from nexus.services.local_heal.reproduction import ReproductionRunner

_META = {"interpreter": sys.executable}


@pytest.fixture
def no_barrier(monkeypatch):
    monkeypatch.setenv("NEXUS_DISABLE_OS_SANDBOX", "1")


@pytest.fixture
def listener():
    # A loopback port the host itself can reach, so a failed connect proves the sandbox denied it.
    server = socket.create_server(("127.0.0.1", 0))
    port = server.getsockname()[1]
    socket.create_connection(("127.0.0.1", port), 3).close()
    yield port
    server.close()


def _verify(repo: Path, patched: list[str]):
    return MicroVerifier.verify(
        patch_content="", repo_dir=repo, patched_files=patched, verifier_env_metadata=_META
    )


def test_micro_verifier_import_runs_nothing_without_barrier(tmp_path, no_barrier):
    marker = tmp_path / "ran.txt"
    (tmp_path / "patched.py").write_text(f"open({str(marker)!r}, 'w').write('x')\n")
    res = _verify(tmp_path, ["patched.py"])
    assert res.passed is False and res.import_ok is False
    assert "verifier_unavailable" in res.classifications
    assert "no_os_barrier" in res.details
    assert not marker.exists()


def test_micro_verifier_tests_run_nothing_without_barrier(tmp_path, no_barrier):
    marker = tmp_path / "ran.txt"
    (tmp_path / "test_patched.py").write_text(
        f"open({str(marker)!r}, 'w').write('x')\n\ndef test_ok():\n    pass\n"
    )
    res = _verify(tmp_path, ["test_patched.py"])
    assert res.passed is False and res.test_ok is False
    assert "verifier_unavailable" in res.classifications
    assert "no_os_barrier" in res.details
    assert not marker.exists()


def test_micro_verifier_import_is_confined(tmp_path, listener):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.txt"
    (repo / "good.py").write_text("VALUE = 1\n")
    (repo / "writes.py").write_text(f"open({str(outside)!r}, 'w').write('x')\n")
    (repo / "dials.py").write_text(
        f"import socket\nsocket.create_connection(('127.0.0.1', {listener}), 3)\n"
    )
    good, writes, dials = (_verify(repo, [name]) for name in ("good.py", "writes.py", "dials.py"))
    assert not outside.exists()
    if not os_sandbox_available():
        assert all("verifier_unavailable" in r.classifications for r in (good, writes, dials))
        return
    assert good.import_ok is True  # the sandbox still lets a legitimate patch import
    assert writes.import_ok is False
    assert dials.import_ok is False


def test_reproduction_runs_nothing_without_barrier(tmp_path, no_barrier):
    marker = tmp_path / "ran.txt"
    runner = ReproductionRunner(tmp_path, python_executable=sys.executable)
    ok, out = runner.run_repro(f"open({str(marker)!r}, 'w').write('x')\nassert False")
    assert ok is False
    assert runner.last_reason_code == "sandbox_unavailable"
    assert "no_os_barrier" in out
    assert not marker.exists()


def test_reproduction_phase_reports_sandbox_unavailable(tmp_path, no_barrier):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "source.py").write_text("value = 1\n")
    subprocess.run(["git", "add", "source.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=tmp_path, check=True)
    runner = ReproductionRunner(tmp_path, python_executable=sys.executable)
    output = ReproductionPhase(runner, MagicMock()).run(
        ReproductionInput("test", tmp_path, "bug", "assert False", sys.executable)
    )
    assert output.success is False
    assert output.provenance.physical is False
    assert output.provenance.reason_code == "sandbox_unavailable"


def test_reproduction_script_is_confined_but_still_reproduces(tmp_path, monkeypatch, listener):
    monkeypatch.setenv("NEXUS_TEST_SECRET_2945", "s3cret")
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.txt"
    script = (
        "import os, socket\n"
        "print('SECRET=' + os.environ.get('NEXUS_TEST_SECRET_2945', '<none>'))\n"
        "try:\n"
        f"    open({str(outside)!r}, 'w').write('x')\n"
        "    print('WROTE')\n"
        "except OSError:\n"
        "    print('WRITE_DENIED')\n"
        "try:\n"
        f"    socket.create_connection(('127.0.0.1', {listener}), 3)\n"
        "    print('CONNECTED')\n"
        "except OSError:\n"
        "    print('NET_DENIED')\n"
        "assert False, 'bug present'\n"
    )
    runner = ReproductionRunner(repo, python_executable=sys.executable)
    ok, out = runner.run_repro(script)
    assert not outside.exists()
    if not os_sandbox_available():
        assert ok is False and runner.last_reason_code == "sandbox_unavailable"
        return
    # The failure record still reaches the runner, so a real reproduction is recognised.
    assert ok is True and runner.last_reason_code == "physical_fail"
    assert "SECRET=<none>" in out and "s3cret" not in out
    assert "WRITE_DENIED" in out and "WROTE" not in out
    assert "NET_DENIED" in out and "CONNECTED" not in out


def _recipe_installs(tmp_path, monkeypatch, evidence: str, *, with_venv: bool) -> list[list[str]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    if with_venv:
        venv_python = repo / ".venv" / "bin" / "python3"
        venv_python.parent.mkdir(parents=True)
        venv_python.write_text("")
    calls: list[list[str]] = []

    def fake_run(argv, *args, **kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(reproduction_phase.subprocess, "run", fake_run)
    runner = MagicMock()
    runner.run_repro.return_value = (False, evidence)
    runner.last_exit_status = 1
    runner.last_reason_code = "unclassified_nonzero_exit"
    runner.last_command = (sys.executable, "reproduce_bug.py")
    runner.last_script_sha256 = "a" * 64
    runner.workspace_identity.return_value = (f"HEAD={'b' * 40};WORKSPACE_SHA256={'d' * 64}", True)
    ReproductionPhase(runner, MagicMock()).run(
        ReproductionInput("test", repo, "bug", "import evilpkg", sys.executable)
    )
    return [argv for argv in calls if argv[:3] == ["uv", "pip", "install"]]


def test_recipe_never_installs_a_package_named_by_model_output(tmp_path, monkeypatch):
    # The script's own output names the package; it must not reach pip, in any recipe.
    evidence = "ModuleNotFoundError: No module named 'evilpkg'\nSymPy now depends on mpmath"
    installs = _recipe_installs(tmp_path, monkeypatch, evidence, with_venv=True)
    venv_python = str(tmp_path / "repo" / ".venv" / "bin" / "python3")
    assert installs == [["uv", "pip", "install", "mpmath", "--python", venv_python]]


def test_recipe_never_installs_into_the_host_python(tmp_path, monkeypatch):
    evidence = "ModuleNotFoundError: No module named 'mpmath'\nSymPy now depends on mpmath"
    assert _recipe_installs(tmp_path, monkeypatch, evidence, with_venv=False) == []


_HOST_RUN_STUB = "#!/bin/sh\nexit 1\n"


def _git_repo_with_venv(repo: Path) -> Path:
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "source.py").write_text("value = 1\n")
    subprocess.run(["git", "add", "source.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=repo, check=True)
    venv_python = repo / ".venv" / "bin" / "python3"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text(_HOST_RUN_STUB)
    venv_python.chmod(0o755)
    return venv_python


def _plant_host_run_code(marker: Path) -> str:
    # What the host runs in the repo after the model's command: git (hooks, core.fsmonitor)
    # and the task venv's interpreter (the recipe install). The payload leaves ``marker``.
    payload = f"#!/bin/sh\ntouch {str(marker)!r}\n"
    return (
        "import os\n"
        "def attempt(f):\n"
        "    try:\n"
        "        f()\n"
        "    except OSError:\n"
        "        pass\n"
        f"PAYLOAD = {payload!r}\n"
        "def plant(path):\n"
        "    os.makedirs(os.path.dirname(path), exist_ok=True)\n"
        "    with open(path, 'w') as f:\n"
        "        f.write(PAYLOAD)\n"
        "    os.chmod(path, 0o755)\n"
        "attempt(lambda: plant('.venv/bin/python3'))\n"
        "attempt(lambda: plant('.git/hooks/post-checkout'))\n"
        "attempt(lambda: plant('fsmonitor.sh'))\n"
        "attempt(lambda: open('.git/config', 'a').write('[core]\\n\\tfsmonitor = ./fsmonitor.sh\\n'))\n"
        "attempt(lambda: os.link('.git/config', 'config_link'))\n"
        "attempt(lambda: os.rename('.venv', 'venv_moved'))\n"
    )


def test_model_command_cannot_change_what_the_host_runs_in_the_repo(tmp_path):
    repo = tmp_path / "repo"
    marker = tmp_path / "escaped.txt"
    venv_python = _git_repo_with_venv(repo)
    config = (repo / ".git" / "config").read_text()
    script = _plant_host_run_code(marker) + "open('legit.txt', 'w').write('x')\n"
    try:
        result = run_model_argv([sys.executable, "-c", script], work_dir=repo, timeout=60)
    except SandboxError as exc:
        assert not os_sandbox_available() and str(exc) == "no_os_barrier"
        assert not (repo / "fsmonitor.sh").exists()
        return
    assert result.returncode == 0, result.stderr
    assert (repo / "legit.txt").exists()  # the work dir itself stays writable
    assert venv_python.read_text() == _HOST_RUN_STUB
    assert (repo / ".git" / "config").read_text() == config
    assert not (repo / ".git" / "hooks" / "post-checkout").exists()
    assert not (repo / "config_link").exists()
    assert not marker.exists()


def test_reproduction_phase_runs_no_interpreter_or_git_hook_the_script_planted(tmp_path):
    repo = tmp_path / "repo"
    marker = tmp_path / "escaped.txt"
    venv_python = _git_repo_with_venv(repo)
    # Fails without the reproduction contract and names the mpmath recipe, so the phase goes on
    # to the recipe install (``uv pip install mpmath --python .venv/bin/python3``) on the host.
    script = (
        _plant_host_run_code(marker) + "print('SymPy now depends on mpmath')\nraise SystemExit(1)\n"
    )
    runner = ReproductionRunner(repo, python_executable=sys.executable)
    ReproductionPhase(runner, MagicMock()).run(
        ReproductionInput("test", repo, "bug", script, sys.executable)
    )
    runner.workspace_identity()
    subprocess.run(["git", "status"], cwd=repo, capture_output=True, check=False)
    assert venv_python.read_text() == _HOST_RUN_STUB
    assert not marker.exists()


@pytest.mark.timeout(120)
def test_a_fifo_failure_record_does_not_hang_the_host(tmp_path):
    runner = ReproductionRunner(tmp_path, python_executable=sys.executable)
    script = "import os, __main__\nos.mkfifo(__main__._nexus_record_path)\nos._exit(1)\n"
    ok, _ = runner.run_repro(script)
    assert ok is False
