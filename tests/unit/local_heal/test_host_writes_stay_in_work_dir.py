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
from nexus.core.contained_write import PathContainmentError
from nexus.engine.model_output_sandbox import (
    SandboxError,
    holds_host_code,
    host_code_roots,
    model_sandbox,
)
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


def test_patch_applies_with_a_relative_repo_dir(dirs, monkeypatch):
    repo, _ = dirs
    (repo / "calc.py").write_text(WRONG, encoding="utf-8")
    nested = repo / "repo"
    nested.mkdir()
    (nested / "calc.py").write_text(WRONG, encoding="utf-8")
    monkeypatch.chdir(repo.parent)
    result = _apply(Path("repo"), "calc.py")
    assert result.success is True, result.error_reason
    assert (repo / "calc.py").read_text(encoding="utf-8") == RIGHT
    assert (nested / "calc.py").read_text(encoding="utf-8") == WRONG


def test_preflight_reads_the_file_with_a_relative_repo_dir(dirs, monkeypatch):
    # An indented REPLACE does not parse alone, so preflight parses the whole patched file.
    repo, _ = dirs
    wrong = "class C:\n    def add(self, a, b):\n        return a - b\n"
    (repo / "calc.py").write_text(wrong, encoding="utf-8")
    monkeypatch.chdir(repo.parent)
    parser = SolidSearchReplaceProtocol()
    intents = parser.parse(
        "FILE: calc.py\n<<<<<<< SEARCH\n        return a - b\n=======\n"
        "        if a:\n            return a + b\n        return b\n>>>>>>> REPLACE\n"
    )
    assert not isinstance(intents, Exception) and intents
    passed, reason, _ = PatchApplier(parser, Patcher()).preflight_check(intents, Path("repo"))
    assert passed is True, reason


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
    # Only through a name no import can reach (local_heal keeps work dirs under .nexus/).
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in (".nexus/workspaces/armor-apply-x1", "ws-1", "pkg/.hidden/deep"):
        (tmp_path / name).mkdir(parents=True)
        assert holds_host_code(tmp_path / name) is False, name


def test_importable_dir_below_host_code_is_host_code(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("pkg", "pkg/sub", "pkg/__pycache__"):
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
        assert holds_host_code(tmp_path / name) is True, name
    assert holds_host_code(tmp_path) is True
    assert holds_host_code(tmp_path.parent) is True


def test_empty_sys_path_entry_is_the_current_directory(tmp_path, monkeypatch):
    (tmp_path / "pkg").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", ["", *sys.path])
    assert tmp_path.resolve() in host_code_roots()
    with pytest.raises(SandboxError, match="work_dir_holds_host_code"):
        with model_sandbox(tmp_path / "pkg"):
            pass


def test_model_sandbox_refuses_a_host_package_subdirectory(tmp_path):
    package_dir = Path(nexus.__file__).resolve().parent / "core"
    assert package_dir.is_dir()
    with pytest.raises(SandboxError, match="work_dir_holds_host_code"):
        with model_sandbox(package_dir):
            pass
    work = tmp_path / "work-1"
    work.mkdir()
    with pytest.raises(SandboxError, match="work_dir_holds_host_code"):
        with model_sandbox(work, writable=(package_dir,)):
            pass


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


# base_commit set: the SymPy step runs after the (stubbed) checkout to that commit.
_SYMPY_TASK = {"local_mode": True, "instance_id": "x", "base_commit": "0" * 40}


def _sympy_repo(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    repo = tmp_path / "sympy_ws"
    (repo / ".git").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / ".nexus_patched_310").symlink_to(outside / "planted")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0))
    return repo, outside


def test_sympy_patch_marker_is_not_created_through_a_dangling_link(tmp_path, monkeypatch):
    harness = _harness()
    repo, outside = _sympy_repo(tmp_path, monkeypatch)
    harness.ensure_workspace_state(_SYMPY_TASK | {"repo_dir": repo})
    assert not os.path.lexists(outside / "planted")


def test_sympy_patch_marker_write_refuses_a_link_swapped_in(tmp_path, monkeypatch):
    harness = _harness()
    repo, outside = _sympy_repo(tmp_path, monkeypatch)
    real_lexists = os.path.lexists
    monkeypatch.setattr(
        os.path,
        "lexists",
        lambda path: False if Path(path).name == ".nexus_patched_310" else real_lexists(path),
    )
    with pytest.raises(PathContainmentError):
        harness.ensure_workspace_state(_SYMPY_TASK | {"repo_dir": repo})
    assert not real_lexists(outside / "planted")
