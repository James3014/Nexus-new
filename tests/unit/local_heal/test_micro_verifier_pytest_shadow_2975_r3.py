"""#2975 R3: a repo-local ``pytest.py`` must not turn a failing test into a recorded pass.

The task interpreter had no pytest and the repo (model output) carried a ``pytest.py`` shim: the
probe (``find_spec`` with the cwd on ``sys.path``) found the shim and ``-m pytest`` ran it, so a
failing test was recorded as ``ran`` / ``test_ok``. A real pytest in the interpreter was shadowed
the same way (the cwd leads ``sys.path`` under ``-m``). Importing the patched module could also
plant the shim, and the verification phase then ran in the same directory. Now the probe and the
run take the cwd and repo_dir off ``sys.path`` until pytest is imported, and the MicroVerifier
runs on a disposable copy of the repo. Known limit, not covered here: ``os._exit(0)`` in the
module under test forges the exit code (follow-up issue).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.services.local_heal import micro_verifier as mv
from nexus.services.local_heal.evaluation_gate import EvaluationGate
from nexus.services.local_heal.micro_verifier import MicroVerifier
from tests.model_sandbox_passthrough import model_exec_without_barrier_runs_unconfined  # noqa: F401

pytestmark = pytest.mark.usefixtures("model_exec_without_barrier_runs_unconfined")

SHIM = (
    "import sys\ndef console_main():\n    return 0\nif __name__ == '__main__':\n    sys.exit(0)\n"
)
FAILING_TEST = "def add(a, b):\n    return a + b\n\ndef test_add():\n    assert add(2, 2) == 5\n"
PLANTING_TEST = (
    "import pathlib\n"
    "pathlib.Path(__file__).with_name('pytest.py').write_text("
    f"{SHIM!r})\n" + FAILING_TEST
)


@pytest.fixture(scope="module")
def _venv_python(tmp_path_factory) -> str:
    venv = tmp_path_factory.mktemp("nopytest_r3") / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True, timeout=120
    )
    return str(venv / "bin" / "python")


@pytest.fixture
def python_without_pytest(_venv_python, monkeypatch) -> str:
    for name in ("PYTHONPATH", "PYTHONHOME"):
        monkeypatch.delenv(name, raising=False)
    probe = subprocess.run(
        [_venv_python, "-c", "import pytest"], capture_output=True, text=True, timeout=60
    )
    assert probe.returncode != 0, "fixture venv unexpectedly has pytest"
    return _venv_python


@pytest.fixture
def real_pytest_python(monkeypatch) -> str:
    # The real pytest must come from the interpreter itself, not from a leaked PYTHONPATH entry.
    monkeypatch.delenv("PYTHONPATH", raising=False)
    return sys.executable


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for rel, text in files.items():
        (repo / rel).write_text(text)
    return repo


def _verify(repo: Path, patched: list[str], interpreter: str):
    return MicroVerifier.verify(
        patch_content="",
        repo_dir=repo,
        patched_files=patched,
        verifier_env_metadata={"interpreter": interpreter},
    )


def _assert_skipped_not_ran(res) -> None:
    assert res.test_step == "skipped" and res.test_skip_reason == "pytest_unavailable"
    assert res.test_ok is False
    assert "false_pass_risk" in res.classifications
    assert "verifier_command_check" not in res.classifications


# A: control, no shim and no pytest -> already a recorded skip.
def test_a_no_shim_no_pytest_is_a_skip(tmp_path, python_without_pytest):
    repo = _repo(tmp_path, {"oracle_test.py": FAILING_TEST})
    _assert_skipped_not_ran(_verify(repo, ["oracle_test.py"], python_without_pytest))


# B: a shim already in the repo, interpreter has no pytest -> still a skip, never "ran".
def test_b_preexisting_shim_without_pytest_is_a_skip(tmp_path, python_without_pytest):
    repo = _repo(tmp_path, {"oracle_test.py": FAILING_TEST, "pytest.py": SHIM})
    _assert_skipped_not_ran(_verify(repo, ["oracle_test.py"], python_without_pytest))


# C: the test file plants the shim while being imported -> still a skip.
def test_c_import_time_planted_shim_without_pytest_is_a_skip(tmp_path, python_without_pytest):
    repo = _repo(tmp_path, {"oracle_test.py": PLANTING_TEST})
    _assert_skipped_not_ran(_verify(repo, ["oracle_test.py"], python_without_pytest))


# D0: control, real pytest and no shim -> the failing test fails.
def test_d0_real_pytest_failing_test_fails(tmp_path, real_pytest_python):
    repo = _repo(tmp_path, {"oracle_test.py": FAILING_TEST})
    res = _verify(repo, ["oracle_test.py"], real_pytest_python)
    assert res.passed is False and res.test_step == "failed"


# D1: real pytest installed, shim in the repo must not shadow it.
def test_d1_preexisting_shim_does_not_shadow_real_pytest(tmp_path, real_pytest_python):
    repo = _repo(tmp_path, {"oracle_test.py": FAILING_TEST, "pytest.py": SHIM})
    res = _verify(repo, ["oracle_test.py"], real_pytest_python)
    assert res.passed is False and res.error_message == "TEST_FAILURE"
    assert res.test_step == "failed"


# D2: real pytest installed, the test file plants the shim at import.
def test_d2_import_time_planted_shim_does_not_shadow_real_pytest(tmp_path, real_pytest_python):
    repo = _repo(tmp_path, {"oracle_test.py": PLANTING_TEST})
    res = _verify(repo, ["oracle_test.py"], real_pytest_python)
    assert res.passed is False and res.error_message == "TEST_FAILURE"


def test_passing_test_still_passes_with_repo_modules_importable(tmp_path, real_pytest_python):
    """Taking the cwd off sys.path for the pytest import must not break top-level imports."""
    repo = _repo(
        tmp_path,
        {
            "calc.py": "def add(a, b):\n    return a + b\n",
            "calc_test.py": "from calc import add\n\ndef test_add():\n    assert add(2, 2) == 4\n",
        },
    )
    res = _verify(repo, ["calc.py", "calc_test.py"], real_pytest_python)
    assert res.passed is True and res.test_step == "ran" and res.test_ok is True
    assert "false_pass_risk" not in res.classifications


def test_probe_flags_a_pytest_resolved_from_inside_repo_dir(tmp_path, real_pytest_python):
    """The probe itself (run without the macOS env allowlist, so PYTHONPATH reaches it): a pytest
    that still resolves under repo_dir is reported as shadowed; the interpreter's own is not."""
    repo = _repo(tmp_path, {"oracle_test.py": FAILING_TEST})
    vendored = repo / "vendored"
    vendored.mkdir()
    (vendored / "pytest.py").write_text(SHIM)
    base_env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}

    def probe(env):
        return subprocess.run(
            [real_pytest_python, "-c", mv._PYTEST_PROBE, str(repo)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=repo,
            env=env,
        ).stdout

    assert mv._PYTEST_SHADOWED_MARKER in probe({**base_env, "PYTHONPATH": str(vendored)})
    assert mv._PYTEST_SHADOWED_MARKER not in probe(base_env)
    assert mv._PYTEST_ABSENT_MARKER not in probe(base_env)


def test_shadowed_probe_answer_fails_the_test_step_closed(
    tmp_path, real_pytest_python, monkeypatch
):
    repo = _repo(tmp_path, {"oracle_test.py": FAILING_TEST})
    real_run = mv.run_model_argv

    def fake(argv, **kw):
        if "-c" in argv and mv._PYTEST_PROBE in argv:
            return subprocess.CompletedProcess(argv, 0, mv._PYTEST_SHADOWED_MARKER + "\n", "")
        return real_run(argv, **kw)

    monkeypatch.setattr(mv, "run_model_argv", fake)
    res = _verify(repo, ["oracle_test.py"], real_pytest_python)
    assert res.passed is False and res.test_step != "ran"
    assert "pytest_shadowed" in res.details
    assert "verifier_unavailable" in res.classifications


# G: a patched non-test module plants the shim at import. The MicroVerifier used by the patch
# synthesis phase runs on a disposable copy, so the directory the verification phase uses stays
# clean and its failing test still fails.
def test_g_scratch_copy_keeps_planted_shim_out_of_the_real_repo(tmp_path, real_pytest_python):
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_calc.py").write_text(
        "from calc import sub\n\ndef test_sub():\n    assert sub(5, 3) == 2\n"
    )
    (repo / "calc.py").write_text(
        "import pathlib\n"
        "pathlib.Path(__file__).with_name('pytest.py').write_text("
        f"{SHIM!r})\n"
        "def sub(a, b):\n    return a + b  # wrong\n"
    )
    res = mv.micro_verify_in_scratch_copy(
        patch_content="",
        repo_dir=repo,
        patched_files=["calc.py"],
        verifier_env_metadata={"interpreter": real_pytest_python},
    )
    assert res.passed is True  # nothing to run for a non-test module; only syntax + import
    assert not (repo / "pytest.py").exists()
    gate = EvaluationGate(repo)
    cmd = [real_pytest_python, "-m", "pytest", "tests/test_calc.py", "-q"]
    assert gate.run_visible_tests([cmd])[0].passed is False


def test_scratch_copy_is_discarded_and_does_not_touch_the_repo(tmp_path, real_pytest_python):
    repo = _repo(tmp_path, {"lib.py": "X = 1\n"})
    seen: list[Path] = []
    real_verify = MicroVerifier.verify

    def spy(patch_content, repo_dir, patched_files, *a, **kw):
        seen.append(Path(repo_dir))
        assert (Path(repo_dir) / "lib.py").read_text() == "X = 1\n"
        return real_verify(patch_content, repo_dir, patched_files, *a, **kw)

    MicroVerifier.verify = staticmethod(spy)  # type: ignore[method-assign]
    try:
        res = mv.micro_verify_in_scratch_copy(
            patch_content="",
            repo_dir=repo,
            patched_files=["lib.py"],
            verifier_env_metadata={"interpreter": real_pytest_python},
        )
    finally:
        MicroVerifier.verify = staticmethod(real_verify)  # type: ignore[method-assign]
    assert res.passed is True
    assert len(seen) == 1 and seen[0].resolve() != repo.resolve()
    assert not seen[0].exists()
    assert sorted(p.name for p in repo.iterdir()) == ["lib.py"]


def test_patch_synthesis_uses_the_scratch_copy_helper():
    src = (
        Path(__file__).parents[3] / "nexus/services/local_heal/phases/patch_synthesis.py"
    ).read_text()
    assert "micro_verify_in_scratch_copy(" in src
    assert "MicroVerifier.verify(" not in src
