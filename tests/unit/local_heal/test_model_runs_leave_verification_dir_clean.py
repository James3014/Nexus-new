"""Model code run by the reproduction step or a verifier run must not leave files behind for a
later verification in the same directory.

The repro script and the visible/hidden verifier commands both run with write access to their
work dir. When that work dir was the task's repo_dir, a file written there (an oracle rewritten,
a pytest plugin planted) stayed for the next verification: a later, failing candidate was then
judged as passing. Each such run now happens on a disposable copy of repo_dir.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.services.local_heal import evaluation_gate as eg
from nexus.services.local_heal import scratch_copy
from nexus.services.local_heal.evaluation_gate import EvaluationGate
from nexus.services.local_heal.reproduction import ReproductionRunner
from nexus.services.local_heal.scratch_copy import disposable_repo_copy
from tests.model_sandbox_passthrough import model_exec_without_barrier_runs_unconfined  # noqa: F401

pytestmark = pytest.mark.usefixtures("model_exec_without_barrier_runs_unconfined")

ORACLE = "import calc\nassert calc.add(1, 2) == 3, 'wrong sum'\n"
WRONG = "def add(a, b):\n    return a - b\n"
# Rewrites the oracle in its cwd as a side effect of being imported.
WRONG_AND_REWRITES_ORACLE = (
    "import pathlib\npathlib.Path('oracle.py').write_text('pass\\n')\n" + WRONG
)
FAILING_TEST = "import calc\n\ndef test_add():\n    assert calc.add(1, 2) == 3\n"
# A pytest plugin that reports every test as passed, written next to the tests.
PASS_ALL_PLUGIN = (
    "import pytest\n\n"
    "@pytest.hookimpl(hookwrapper=True)\n"
    "def pytest_runtest_makereport(item, call):\n"
    "    outcome = yield\n"
    "    outcome.get_result().outcome = 'passed'\n"
)
WRONG_AND_PLANTS_PLUGIN = (
    f"import pathlib\npathlib.Path('conftest.py').write_text({PASS_ALL_PLUGIN!r})\n" + WRONG
)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "oracle.py").write_text(ORACLE, encoding="utf-8")
    (repo / "test_calc.py").write_text(FAILING_TEST, encoding="utf-8")
    return repo


def _oracle(repo: Path) -> list[str]:
    return [sys.executable, "oracle.py"]


def _pytest(repo: Path) -> list[str]:
    return [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_calc.py"]


def test_control_failing_candidate_fails_the_oracle(tmp_path):
    repo = _repo(tmp_path)
    (repo / "calc.py").write_text(WRONG, encoding="utf-8")
    result = EvaluationGate(repo).run_visible_tests([_oracle(repo)])
    assert result[0].passed is False
    assert "wrong sum" in result[0].output


def test_control_correct_candidate_passes_oracle_and_pytest(tmp_path):
    repo = _repo(tmp_path)
    (repo / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    gate = EvaluationGate(repo)
    assert gate.run_visible_tests([_oracle(repo)])[0].passed is True
    assert gate.run_visible_tests([_pytest(repo)])[0].passed is True


def test_verifier_run_cannot_rewrite_the_oracle_for_the_next_candidate(tmp_path):
    repo = _repo(tmp_path)
    gate = EvaluationGate(repo)
    (repo / "calc.py").write_text(WRONG_AND_REWRITES_ORACLE, encoding="utf-8")
    assert gate.run_visible_tests([_oracle(repo)])[0].passed is False

    (repo / "calc.py").write_text(WRONG, encoding="utf-8")
    second = gate.run_visible_tests([_oracle(repo)])

    assert second[0].passed is False
    assert (repo / "oracle.py").read_text(encoding="utf-8") == ORACLE


def test_verifier_run_cannot_plant_a_pytest_plugin_for_the_next_candidate(tmp_path):
    repo = _repo(tmp_path)
    gate = EvaluationGate(repo)
    (repo / "calc.py").write_text(WRONG_AND_PLANTS_PLUGIN, encoding="utf-8")
    gate.run_visible_tests([_pytest(repo)])

    (repo / "calc.py").write_text(WRONG, encoding="utf-8")
    second = gate.run_hidden_verifier([_pytest(repo)])

    assert second[0].passed is False
    assert not (repo / "conftest.py").exists()


def test_repro_script_cannot_rewrite_the_oracle_used_by_verification(tmp_path):
    repo = _repo(tmp_path)
    (repo / "calc.py").write_text(WRONG, encoding="utf-8")
    runner = ReproductionRunner(repo, python_executable=sys.executable)

    reproduced, evidence = runner.run_repro(
        "import pathlib\npathlib.Path('oracle.py').write_text('pass\\n')\n"
        "raise AssertionError('bug present')"
    )

    assert reproduced is True, evidence
    assert (repo / "oracle.py").read_text(encoding="utf-8") == ORACLE
    assert EvaluationGate(repo).run_visible_tests([_oracle(repo)])[0].passed is False


def test_repro_script_cannot_plant_a_pytest_plugin_for_verification(tmp_path):
    repo = _repo(tmp_path)
    (repo / "calc.py").write_text(WRONG, encoding="utf-8")
    runner = ReproductionRunner(repo, python_executable=sys.executable)

    reproduced, _ = runner.run_repro(
        f"import pathlib\npathlib.Path('conftest.py').write_text({PASS_ALL_PLUGIN!r})\n"
        "raise AssertionError('bug present')"
    )

    assert reproduced is True
    assert not (repo / "conftest.py").exists()
    assert EvaluationGate(repo).run_visible_tests([_pytest(repo)])[0].passed is False


def test_repro_script_still_imports_repo_modules_and_its_file_stays_bound(tmp_path):
    repo = _repo(tmp_path)
    (repo / "calc.py").write_text(WRONG, encoding="utf-8")
    runner = ReproductionRunner(repo, python_executable=sys.executable)

    reproduced, evidence = runner.run_repro("import calc\nassert calc.add(1, 2) == 3, 'repro'")

    assert reproduced is True, evidence
    assert "repro" in evidence
    script = (repo / "reproduce_bug.py").read_bytes()
    assert runner.last_script_sha256 == hashlib.sha256(script).hexdigest()
    # The script left in repo_dir is what verification runs later; it must not name the copy.
    assert b"repro-run-" not in script and b"eval-gate-" not in script
    # Nor any fixed directory: it imports from the directory it runs in.
    assert str(repo.resolve()).encode() not in script and str(repo).encode() not in script


def test_verifier_scratch_copy_is_discarded(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    (repo / "calc.py").write_text(WRONG, encoding="utf-8")
    seen: list[Path] = []
    real_run = eg.run_model_argv

    def spy(cmd, *, work_dir, **kwargs):
        seen.append(Path(work_dir))
        return real_run(cmd, work_dir=work_dir, **kwargs)

    monkeypatch.setattr(eg, "run_model_argv", spy)
    EvaluationGate(repo).run_visible_tests([_oracle(repo)])

    assert len(seen) == 1
    assert seen[0].resolve() != repo.resolve()
    assert not seen[0].exists()


def test_verifier_imports_from_its_own_copy_first(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    calls: list[tuple[Path, dict]] = []

    def record(cmd, *, work_dir, extra_env, **kwargs):
        calls.append((Path(work_dir), dict(extra_env)))
        return eg.subprocess.CompletedProcess(cmd, 1, "", "")

    monkeypatch.setattr(eg, "run_model_argv", record)
    EvaluationGate(repo).run_hidden_verifier([_oracle(repo)])

    work, env = calls[0]
    entries = env["PYTHONPATH"].split(":")
    assert entries[:2] == [str(work), str(work / "scripts/benchmarks")]
    assert str(repo) not in entries and str(repo.resolve()) not in entries


def test_copy_failure_is_a_failed_run_not_a_pass(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    (repo / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    def broken(*args, **kwargs):
        raise OSError("no space")

    monkeypatch.setattr(scratch_copy, "copy_repo_entries", broken)
    gate = EvaluationGate(repo)
    assert gate.run_visible_tests([_oracle(repo)])[0].passed is False
    assert gate.run_hidden_verifier([_oracle(repo)])[0].passed is False
    runner = ReproductionRunner(repo, python_executable=sys.executable)
    assert runner.run_repro("raise AssertionError('bug')")[0] is False
    assert runner.last_exit_status is None
    assert sorted(p.name for p in tmp_path.iterdir()) == ["repo"]


def test_disposable_copy_sits_next_to_repo_keeps_links_and_is_deleted(tmp_path):
    repo = _repo(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("host", encoding="utf-8")
    (repo / "link").symlink_to(outside)

    with disposable_repo_copy(repo, prefix="model-run-") as copy:
        assert copy.parent == repo.resolve().parent
        assert (copy / "link").is_symlink()
        assert (copy / "oracle.py").read_text(encoding="utf-8") == ORACLE
        (copy / "link").unlink()
        (copy / "oracle.py").write_text("pass\n", encoding="utf-8")
    assert not copy.exists()
    assert outside.read_text(encoding="utf-8") == "host"
    assert (repo / "oracle.py").read_text(encoding="utf-8") == ORACLE


def test_copy_entries_skips_an_entry_holding_the_scratch_dir(tmp_path):
    repo = _repo(tmp_path)
    scratch = repo / "holder" / "scratch"
    scratch.mkdir(parents=True)

    scratch_copy.copy_repo_entries(repo, scratch)

    assert (scratch / "oracle.py").is_file()
    assert not (scratch / "holder").exists()


def test_verifier_command_naming_repo_dir_by_absolute_path_still_runs(tmp_path):
    repo = _repo(tmp_path)
    (repo / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    command = [sys.executable, str((repo / "oracle.py").resolve())]
    assert EvaluationGate(repo).run_visible_tests([command])[0].passed is True


def test_copy_without_clone_keeps_nested_links_as_links(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("host", encoding="utf-8")
    (repo / "pkg").mkdir()
    (repo / "pkg" / "link").symlink_to(outside)
    monkeypatch.setattr(scratch_copy, "sys", SimpleNamespace(platform="linux"))

    with disposable_repo_copy(repo, prefix="model-run-") as copy:
        assert (copy / "pkg" / "link").is_symlink()
        assert (copy / "oracle.py").read_text(encoding="utf-8") == ORACLE
