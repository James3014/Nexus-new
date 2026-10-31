"""Host-side writes driven by model output stay inside the task's work dir.

- PatchApplier writes the file a model patch names (``FILE:``): an absolute path, ``..``, or a
  link left in repo_dir must not take the write outside repo_dir.
- The verification phase writes ``reproduce_bug.py`` into repo_dir: never through a link.
- No model run may get write access to the directory the host imports its own code from, and
  the research harness's local mode now runs on a scratch copy instead of the checkout.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

import nexus
from nexus.engine.model_output_sandbox import SandboxError, host_code_roots, model_sandbox
from nexus.services.local_heal.evaluation_gate import EvaluationGate
from nexus.services.local_heal.interface import LocalizedFile, VerificationInput
from nexus.services.local_heal.patch_applier import PatchApplier
from nexus.services.local_heal.patcher import Patcher
from nexus.services.local_heal.phases.verification import VerificationPhase
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol
from nexus.services.local_heal.reproduction import ReproductionRunner

WRONG = "def add(a, b):\n    return a - b\n"
RIGHT = "def add(a, b):\n    return a + b\n"


@pytest.fixture(autouse=True)
def _standard_protocol(monkeypatch):
    monkeypatch.setenv("NEXUS_PROTOCOL_MODE", "standard")


def _patch(file_path: str) -> str:
    return f"FILE: {file_path}\n<<<<<<< SEARCH\n{WRONG}=======\n{RIGHT}>>>>>>> REPLACE\n"


def _apply(repo: Path, file_path: str, localized: list[LocalizedFile] | None = None):
    parser = SolidSearchReplaceProtocol()
    intents = parser.parse(_patch(file_path))
    assert not isinstance(intents, Exception) and intents
    return PatchApplier(parser, Patcher()).apply_and_validate(
        intents=intents, repo_dir=repo, localized_files=localized or []
    )


@pytest.fixture
def dirs(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "calc.py").write_text(WRONG, encoding="utf-8")
    return repo, outside


def test_patch_inside_repo_still_applies(dirs):
    repo, _ = dirs
    (repo / "calc.py").write_text(WRONG, encoding="utf-8")
    result = _apply(repo, "calc.py")
    assert result.success is True
    assert (repo / "calc.py").read_text(encoding="utf-8") == RIGHT


def test_absolute_path_inside_repo_still_applies(dirs):
    repo, _ = dirs
    (repo / "calc.py").write_text(WRONG, encoding="utf-8")
    assert _apply(repo, str((repo / "calc.py").resolve())).success is True
    assert (repo / "calc.py").read_text(encoding="utf-8") == RIGHT


@pytest.mark.parametrize("kind", ["parent", "absolute"])
def test_patch_path_outside_repo_is_refused(dirs, kind):
    repo, outside = dirs
    file_path = "../outside/calc.py" if kind == "parent" else str(outside / "calc.py")
    result = _apply(repo, file_path)
    assert result.success is False
    assert result.error_reason.startswith("PATH_OUTSIDE_REPO:")
    assert (outside / "calc.py").read_text(encoding="utf-8") == WRONG


def test_patch_through_a_link_in_repo_is_refused(dirs):
    repo, outside = dirs
    (repo / "calc.py").symlink_to(outside / "calc.py")
    result = _apply(repo, "calc.py")
    assert result.success is False
    assert (outside / "calc.py").read_text(encoding="utf-8") == WRONG


def test_patch_through_a_linked_directory_is_refused(dirs):
    repo, outside = dirs
    (repo / "pkg").symlink_to(outside)
    result = _apply(repo, "pkg/calc.py")
    assert result.success is False
    assert (outside / "calc.py").read_text(encoding="utf-8") == WRONG


def test_link_swapped_in_after_preflight_is_not_followed(dirs, monkeypatch):
    repo, outside = dirs
    (repo / "calc.py").write_text(WRONG, encoding="utf-8")
    applier_module = sys.modules[PatchApplier.__module__]
    real_read = applier_module.read_text_in_root

    def read_then_swap(root, relative):
        text = real_read(root, relative)
        (repo / "calc.py").unlink()
        (repo / "calc.py").symlink_to(outside / "calc.py")
        return text

    monkeypatch.setattr(applier_module, "read_text_in_root", read_then_swap)
    result = _apply(repo, "calc.py")
    assert result.success is False
    assert result.error_reason.startswith("PATH_OUTSIDE_REPO:")
    assert (outside / "calc.py").read_text(encoding="utf-8") == WRONG


def test_preflight_reports_a_path_outside_repo(dirs):
    repo, outside = dirs
    parser = SolidSearchReplaceProtocol()
    intents = parser.parse(_patch(str(outside / "calc.py")))
    passed, reason, telemetry = PatchApplier(parser, Patcher()).preflight_check(intents, repo)
    assert passed is False
    assert reason.startswith("PATH_OUTSIDE_REPO:")
    assert telemetry["preflight_checks"][-1]["check"] == "path_in_repo"


def test_cross_file_fallback_does_not_read_a_hard_linked_file(dirs):
    repo, outside = dirs
    (repo / "calc.py").write_text("x = 1\n", encoding="utf-8")
    os.link(outside / "calc.py", repo / "other.py")
    result = _apply(repo, "calc.py", [LocalizedFile(path="other.py", content="")])
    assert result.success is False
    # The linked file never matched: the patch fails as a plain SEARCH mismatch.
    assert not result.error_reason.startswith("PATH_OUTSIDE_REPO:")
    assert (outside / "calc.py").read_text(encoding="utf-8") == WRONG


def test_cross_file_fallback_does_not_read_through_a_link(dirs):
    repo, outside = dirs
    (repo / "calc.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "other.py").symlink_to(outside / "calc.py")
    result = _apply(repo, "calc.py", [LocalizedFile(path="other.py", content="")])
    assert result.success is False
    assert (outside / "calc.py").read_text(encoding="utf-8") == WRONG


def _verify(repo: Path, script: str):
    return VerificationPhase(EvaluationGate(repo)).run(
        VerificationInput(
            instance_id="t",
            repo_dir=repo,
            problem_statement="p",
            final_patch="diff",
            repro_script=script,
            python_executable=sys.executable,
        )
    )


def test_verification_does_not_write_the_repro_script_through_a_link(dirs):
    repo, outside = dirs
    (repo / "reproduce_bug.py").symlink_to(outside / "planted.py")
    output = _verify(repo, "print('ok')\n")
    assert output.success is False
    assert output.error_reason == "REPRO_SCRIPT_PATH_REFUSED"
    assert not (outside / "planted.py").exists()


def test_repro_runner_does_not_write_its_script_through_a_link(dirs):
    repo, outside = dirs
    (repo / "reproduce_bug.py").symlink_to(outside / "planted.py")
    runner = ReproductionRunner(repo, python_executable=sys.executable)
    reproduced, _ = runner.run_repro("raise AssertionError('bug')")
    assert reproduced is False
    assert runner.last_exit_status is None
    assert not (outside / "planted.py").exists()


def test_model_sandbox_refuses_the_host_code_root():
    checkout = Path(nexus.__file__).resolve().parents[1]
    assert checkout in host_code_roots()
    with pytest.raises(SandboxError, match="work_dir_holds_host_code"):
        with model_sandbox(checkout):
            pass
    with pytest.raises(SandboxError, match="work_dir_holds_host_code"):
        with model_sandbox(checkout.parent):
            pass


def test_checkout_is_a_host_code_root_even_off_sys_path(monkeypatch):
    checkout = Path(nexus.__file__).resolve().parents[1]
    monkeypatch.setattr(sys, "path", [p for p in sys.path if Path(p or ".").resolve() != checkout])
    assert checkout in host_code_roots()


def test_model_sandbox_refuses_a_dir_holding_a_sys_path_entry(tmp_path, monkeypatch):
    (tmp_path / "lib").mkdir()
    monkeypatch.syspath_prepend(str(tmp_path / "lib"))
    with pytest.raises(SandboxError, match="work_dir_holds_host_code"):
        with model_sandbox(tmp_path):
            pass
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(SandboxError, match="work_dir_holds_host_code"):
        with model_sandbox(work, writable=(tmp_path,)):
            pass


def test_model_sandbox_allows_a_dir_below_a_sys_path_entry(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "ws").mkdir()
    try:
        with model_sandbox(tmp_path / "ws"):
            pass
    except SandboxError as exc:  # no OS barrier on this host is fine; the guard is not
        assert "work_dir_holds_host_code" not in str(exc)


def _harness():
    path = (
        Path(nexus.__file__).resolve().parents[1] / "benchmarking/swebench_lite/swe_local_heal.py"
    )
    spec = importlib.util.spec_from_file_location("swe_local_heal_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_local_mode_task_runs_on_a_scratch_copy_not_the_checkout(tmp_path):
    harness = _harness()
    source = tmp_path / "src"
    target = source / "scripts" / "benchmarks" / "race.py"
    target.parent.mkdir(parents=True)
    target.write_text("def test_challenge():\n    pass\n", encoding="utf-8")
    task = {"local_mode": True, "repo_dir": source, "local_path": target}

    staged = harness.stage_local_mode_workspace(task, tmp_path / "scratch")

    repo = Path(staged["repo_dir"])
    assert repo.parent == (tmp_path / "scratch").resolve()
    assert Path(staged["local_path"]) == repo / "scripts" / "benchmarks" / "race.py"
    assert Path(staged["local_path"]).read_text(encoding="utf-8") == target.read_text(
        encoding="utf-8"
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    )
    assert len(head.stdout.strip()) == 40
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True
    )
    assert status.stdout == ""
    assert harness.localized_files_for_task(staged)[0][0] == "scripts/benchmarks/race.py"


def test_prepared_local_task_is_staged(tmp_path):
    harness = _harness()
    source = tmp_path / "src"
    source.mkdir()
    (source / "race.py").write_text("x = 1\n", encoding="utf-8")
    task = {"local_mode": True, "repo_dir": source, "local_path": "race.py"}

    prepared = harness.prepare_task_workspace(task, tmp_path / "scratch")

    assert Path(prepared["repo_dir"]).parent == (tmp_path / "scratch").resolve()
    assert Path(prepared["local_path"]).read_text(encoding="utf-8") == "x = 1\n"
    assert sorted(p.name for p in source.iterdir()) == ["race.py"]


def test_non_local_task_is_left_alone(tmp_path):
    harness = _harness()
    task = {"local_mode": False, "repo_dir": tmp_path}
    assert harness.stage_local_mode_workspace(task, tmp_path / "scratch") is task
    assert not (tmp_path / "scratch").exists()
