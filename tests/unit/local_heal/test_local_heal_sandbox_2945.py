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

from nexus.engine.model_output_sandbox import (
    SandboxError,
    interpreter_readable_roots,
    run_model_argv,
)
from nexus.engine.sandboxed_lane import os_sandbox_available
from nexus.services.local_heal.env_denoiser import EnvDenoiser
from nexus.services.local_heal.interface import ReproductionInput
from nexus.services.local_heal.micro_verifier import MicroVerifier
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

    monkeypatch.setattr(subprocess, "run", fake_run)
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
    # The script's own output names the package; it must not reach pip, in any recipe. Since
    # #2961 not even the recipe's fixed package is installed: the recipe is chosen from that
    # output, and uv would start the venv interpreter, which imports from the repo.
    evidence = "ModuleNotFoundError: No module named 'evilpkg'\nSymPy now depends on mpmath"
    assert _recipe_installs(tmp_path, monkeypatch, evidence, with_venv=True) == []


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
        # APFS is case-insensitive: other spellings name the same entries.
        "attempt(lambda: plant('.VENV/bin/python3'))\n"
        "attempt(lambda: plant('.Git/hooks/pre-commit'))\n"
        "attempt(lambda: open('.GIT/config', 'a').write('[core]\\n\\thooksPath = ../hooks\\n'))\n"
    )


def test_model_command_cannot_change_what_the_host_runs_in_the_repo(tmp_path):
    repo = tmp_path / "repo"
    marker = tmp_path / "escaped.txt"
    venv_python = _git_repo_with_venv(repo)
    config = (repo / ".git" / "config").read_text()
    script = _plant_host_run_code(marker) + "open('legit.txt', 'w').write('x')\n"
    try:
        result = run_model_argv(
            [sys.executable, "-c", script],
            work_dir=repo,
            timeout=60,
            readable=interpreter_readable_roots(sys.executable),
        )
    except SandboxError as exc:
        assert not os_sandbox_available() and str(exc) == "no_os_barrier"
        assert not (repo / "fsmonitor.sh").exists()
        return
    assert result.returncode == 0, result.stderr
    assert (repo / "legit.txt").exists()  # the work dir itself stays writable
    assert venv_python.read_text() == _HOST_RUN_STUB
    assert (repo / ".git" / "config").read_text() == config
    assert not (repo / ".git" / "hooks" / "post-checkout").exists()
    assert not (repo / ".git" / "hooks" / "pre-commit").exists()
    assert not (repo / "config_link").exists()
    assert not marker.exists()


def test_model_command_cannot_create_git_or_venv_in_any_spelling(tmp_path):
    # A repo without .git (or .venv): creating one, as a dir or as a gitfile pointing at a
    # writable dir, in any case spelling, would hand the host's next git call to the model.
    repo = tmp_path / "repo"
    repo.mkdir()
    script = (
        "import os\n"
        "for name in ('.git', '.GIT', '.Git', '.venv', '.Venv'):\n"
        "    for make in (lambda: os.makedirs(name + '/hooks'),\n"
        "                 lambda: open(name, 'w').write('gitdir: ./planted\\n')):\n"
        "        try:\n"
        "            make()\n"
        "        except OSError:\n"
        "            pass\n"
        "os.makedirs('planted', exist_ok=True)\n"
    )
    try:
        result = run_model_argv(
            [sys.executable, "-c", script],
            work_dir=repo,
            timeout=60,
            readable=interpreter_readable_roots(sys.executable),
        )
    except SandboxError as exc:
        assert not os_sandbox_available() and str(exc) == "no_os_barrier"
        assert sorted(p.name for p in repo.iterdir()) == []
        return
    assert result.returncode == 0, result.stderr
    assert sorted(p.name for p in repo.iterdir()) == ["planted"]


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


# --- #2961: the recipe's host install is refused and recorded apart from env_denoise ---------

_MPMATH_EVIDENCE = "ModuleNotFoundError: No module named 'evilpkg'\nSymPy now depends on mpmath"


def _make_venv_python(repo: Path) -> Path:
    venv_python = repo / ".venv" / "bin" / "python3"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("")
    return venv_python


def _no_subprocess(monkeypatch) -> list[list[str]]:
    # Popen underlies run / check_output / call, so any host command the phase starts lands
    # here (and fails the run), whichever helper it uses.
    calls: list[list[str]] = []

    def fake_popen(argv, *args, **kwargs):
        calls.append(list(argv) if not isinstance(argv, str) else [argv])
        raise AssertionError(f"host subprocess started: {argv!r}")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    return calls


def _mpmath_runner(outcomes=None) -> MagicMock:
    runner = MagicMock()
    if outcomes is None:
        runner.run_repro.return_value = (False, _MPMATH_EVIDENCE)
    else:
        runner.run_repro.side_effect = outcomes
    runner.last_exit_status = 1
    runner.last_reason_code = "unclassified_nonzero_exit"
    runner.last_command = (sys.executable, "reproduce_bug.py")
    runner.last_script_sha256 = "a" * 64
    runner.workspace_identity.return_value = (f"HEAD={'b' * 40};WORKSPACE_SHA256={'d' * 64}", True)
    return runner


def _refusing_denoiser(repo: Path, seen: list) -> EnvDenoiser:
    # compat_python_executable given: no ``uv python find`` probe, so the recorded
    # subprocess calls are every one the phase starts.
    denoiser = EnvDenoiser(
        repo, run_command=lambda cmd, cwd, timeout: (0, "ok"), compat_python_executable="python3"
    )
    real_prepare = denoiser.prepare_from_evidence

    def prepare(evidence, **kwargs):
        seen.append(kwargs)
        return real_prepare(evidence, **kwargs)

    setattr(denoiser, "prepare_from_evidence", prepare)  # noqa: B010 - records the call
    return denoiser


def _run_phase(repo: Path, denoiser, runner, *, auto_heal: bool):
    return ReproductionPhase(runner, denoiser).run(
        ReproductionInput("test", repo, "bug", "import evilpkg", sys.executable),
        auto_heal_enabled=auto_heal,
    )


def _refused(venv_python: Path) -> dict:
    return {
        "argv": ["uv", "pip", "install", "mpmath", "--python", str(venv_python)],
        "attempted": False,
        "skipped": "HOST_INSTALL_REFUSED_MODEL_OUTPUT",
    }


def test_recipe_install_is_refused_recorded_and_env_denoise_is_unchanged(tmp_path, monkeypatch):
    from nexus.services.local_heal.env_taxonomy import classify_env_failure

    repo = tmp_path / "repo"
    venv_python = _make_venv_python(repo)
    calls = _no_subprocess(monkeypatch)
    seen: list = []
    runner = _mpmath_runner()
    out = _run_phase(repo, _refusing_denoiser(repo, seen), runner, auto_heal=True)
    assert calls == []
    assert out.env_recipe["recipe_id"]
    assert out.env_recipe["host_install_actions"] == [_refused(venv_python)]
    # The legacy denoiser still saw model output and refused; no rerun after its refusal.
    assert seen == [{"model_output": True}]
    assert runner.run_repro.call_count == 2
    alone = _refusing_denoiser(repo, []).prepare_from_evidence(_MPMATH_EVIDENCE, model_output=True)
    assert out.env_denoise == dict(alone.to_receipt())
    assert "host_install" not in str(out.env_denoise)
    reason = out.error_reason
    assert classify_env_failure(reason, {}, out.env_denoise) == classify_env_failure(
        reason, {}, dict(alone.to_receipt())
    )


def test_recipe_only_keeps_the_env_denoise_shape(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    venv_python = _make_venv_python(repo)
    assert _no_subprocess(monkeypatch) == []
    out = _run_phase(repo, MagicMock(), _mpmath_runner(), auto_heal=False)
    assert set(out.env_denoise) == {
        "recipe_id",
        "recipe_actions",
        "recipe_succeeded",
        "recipe_attempt",
    }
    assert out.env_recipe == {**out.env_denoise, "host_install_actions": [_refused(venv_python)]}


def test_recipe_without_a_task_venv_records_no_install(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _no_subprocess(monkeypatch)
    out = _run_phase(repo, MagicMock(), _mpmath_runner(), auto_heal=False)
    assert out.env_recipe["host_install_actions"] == []


@pytest.mark.parametrize("recipe_retry_reproduces", [False, True])
def test_recipe_record_reaches_the_repair_receipt(tmp_path, monkeypatch, recipe_retry_reproduces):
    from nexus.services.local_heal.pipeline import HealContext as LegacyHealContext
    from nexus.services.local_heal.receipt import build_repair_receipt

    repo = tmp_path / "repo"
    venv_python = _make_venv_python(repo)
    calls = _no_subprocess(monkeypatch)
    retry = (True, "AssertionError: bug present " * 3) if recipe_retry_reproduces else None
    runner = _mpmath_runner([(False, _MPMATH_EVIDENCE), retry or (False, _MPMATH_EVIDENCE)])
    seen: list = []
    legacy = LegacyHealContext(
        instance_id="t-2961", repo_dir=repo, problem_statement="bug", auto_heal_enabled=True
    )
    legacy.repro_script = "import evilpkg"
    v2 = legacy.to_v2()
    ReproductionPhase(runner, _refusing_denoiser(repo, seen)).execute(v2)
    legacy.sync_from_v2(v2)
    receipt = build_repair_receipt(legacy)
    assert calls == []
    recipe = receipt["telemetries"]["env_recipe"]
    assert recipe["host_install_actions"] == [_refused(venv_python)]
    assert recipe["recipe_succeeded"] is recipe_retry_reproduces
    if recipe_retry_reproduces:
        # The denoiser is not reached; env_denoise is the recipe receipt, as before #2961.
        assert seen == []
        assert receipt["telemetries"]["env_denoise"] == {
            k: v for k, v in recipe.items() if k != "host_install_actions"
        }
    else:
        assert seen == [{"model_output": True}]
        denoise = receipt["telemetries"]["env_denoise"]
        assert denoise["reason"] == "HOST_INSTALL_REFUSED_MODEL_OUTPUT"
        assert "host_install" not in str(denoise)


def test_legacy_context_hands_env_recipe_to_v2_and_back(tmp_path):
    from nexus.services.local_heal.pipeline import HealContext as LegacyHealContext

    legacy = LegacyHealContext(instance_id="t", repo_dir=tmp_path, problem_statement="bug")
    legacy.env_recipe = {"recipe_id": "r", "host_install_actions": []}
    v2 = legacy.to_v2()
    assert v2.op.env_recipe == legacy.env_recipe
    back = LegacyHealContext(instance_id="t", repo_dir=tmp_path, problem_statement="bug")
    back.sync_from_v2(v2)
    assert back.env_recipe == legacy.env_recipe
