"""Host git in directories a worker has written runs through the hardened runner (#3291).

Three sites: the nightshift commit/reset in the leased work path, the candidate diff in the
repair attempt worktree, and the patch application after the Ollama worker. Each test lets a
"worker" change the repository's own metadata and checks that nothing it placed runs and that
the site still reads and writes the real repository.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from nexus.app.nightshift_runner_service import AutoResearchNightShift
from nexus.core.hardened_git import linked_worktree_git_dir
from nexus.core.state_contracts import NexusState
from nexus.engine.repair_attempt_service import RepairAttemptService
from nexus.executors.cli_worker import CliWorkerResult, CliWorkerStatus
from nexus.executors.worker_contract import WorkerOutcome
from nexus.executors.worker_registry import OllamaPatchWorkerAdapter


@pytest.fixture(autouse=True)
def _isolated_git_env(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for key in list(os.environ):
        if key.startswith("GIT_") and key != "GIT_CONFIG_NOSYSTEM":
            monkeypatch.delenv(key, raising=False)


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


def _repo(path: Path, content: str = "old\n") -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.name", "Test")
    _git(path, "config", "user.email", "test@example.invalid")
    (path / "f.txt").write_text(content)
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "base")
    return path


def _program(path: Path, marker: Path) -> Path:
    path.write_text(f"#!/bin/sh\necho ran >> '{marker}'\nexit 0\n")
    path.chmod(0o755)
    return path


def _evil_gitdir(path: Path, marker: Path) -> Path:
    """A git dir of the worker's own making: its config points hooks at a pre-commit."""
    hooks = path.parent / "evil-hooks"
    hooks.mkdir()
    _program(hooks / "pre-commit", marker)
    _git(path.parent, "init", "-q", "--bare", str(path))
    _git(path, "config", "core.hooksPath", str(hooks))
    return path


# ---------------------------------------------------------------------------
# nightshift: add / commit / reset in the leased work path
# ---------------------------------------------------------------------------


def _leased_runner(tmp_path: Path):
    root = _repo(tmp_path / "root")
    runner = AutoResearchNightShift(project_root=root, task="t3291")
    runner.worktree_mgr.workspace_base = tmp_path / "leases"
    runner.worktree_mgr.workspace_base.mkdir()
    _, _, workpath = runner.worktree_mgr.lease("t3291", "nightshift-3291")
    workpath = Path(workpath)
    runner._workpath_git_dir = linked_worktree_git_dir(workpath, root)
    assert runner._workpath_git_dir is not None
    return runner, root, workpath


@pytest.mark.parametrize("variant", ["config_hooks", "git_pointer"])
def test_nightshift_commit_runs_no_worker_placed_program(tmp_path, variant):
    runner, root, workpath = _leased_runner(tmp_path)
    marker = tmp_path / "marker"
    admin = Path(runner._workpath_git_dir)
    if variant == "config_hooks":
        hooks = tmp_path / "hooks"
        hooks.mkdir()
        _program(hooks / "pre-commit", marker)
        _git(root, "config", "core.hooksPath", str(hooks))
    else:
        evil = _evil_gitdir(tmp_path / "evil.git", marker)
        (workpath / ".git").write_text(f"gitdir: {evil}\n")
    (workpath / "f.txt").write_text("new\n")
    base_before = _git(root, "rev-parse", "HEAD").stdout.strip()

    committed = runner._commit_improvement(workpath, 1.0)

    assert not marker.exists()
    if variant == "config_hooks":
        assert committed is True
        head = _git(root, "--git-dir", str(admin), "rev-parse", "HEAD").stdout.strip()
        assert runner.base_commit == head != base_before
        message = _git(root, "--git-dir", str(admin), "log", "-1", "--format=%s").stdout
        assert message.startswith("opt(nightshift): optimize t3291 (score: 1.00)")
    else:
        # A rewritten .git pointer is refused: nothing is committed or promoted.
        assert committed is False
        assert _git(root, "rev-parse", "HEAD").stdout.strip() == base_before


def test_nightshift_reset_is_hardened_and_keeps_semantics(tmp_path):
    runner, root, workpath = _leased_runner(tmp_path)
    marker = tmp_path / "marker"
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    _program(hooks / "post-checkout", marker)
    _git(root, "config", "core.hooksPath", str(hooks))
    (workpath / "f.txt").write_text("scratch\n")

    result = runner._workpath_git(workpath, "reset", "--hard", "HEAD")

    assert result is not None and result.returncode == 0
    assert (workpath / "f.txt").read_text() == "old\n"
    assert not marker.exists()


# ---------------------------------------------------------------------------
# repair attempt: git diff --binary in the candidate worktree
# ---------------------------------------------------------------------------


def _candidate_diff(tmp_path: Path, plant) -> str:
    root = _repo(tmp_path / "root")
    wt = tmp_path / "wt_conservative"
    _git(root, "worktree", "add", "-q", "-b", "cand", str(wt))
    seen: dict = {}

    def pregate(*, project_root, commands):
        plant(root, wt)
        (wt / "f.txt").write_text("new\n")
        return True, []

    def trigger_battle(*, task_id, desc, context, execute_fn):
        seen.update(execute_fn({"name": "conservative", "params": {}}, str(wt), task_id, desc, {}))
        return {"status": "all_failed", "winner": None, "all_results": []}

    svc = RepairAttemptService(
        project_root=root, run_cli_pregate_fn=pregate, subprocess_run=MagicMock()
    )
    swarm = MagicMock()
    swarm.default_workers = 1
    swarm.trigger_battle.side_effect = trigger_battle
    try:
        svc.execute_attempt(
            task_id="t3291",
            task_desc="fix",
            state=NexusState(task_id="t3291"),
            attempt=2,
            verify_cmds=["true"],
            run_dir=tmp_path,
            skip_pregate_for_isolated_workspace=False,
            battle_swarm=swarm,
        )
    except Exception:  # noqa: BLE001 - only the worker result is under test
        if not seen:
            raise
    return seen["candidate_payload"]


def test_repair_candidate_diff_reads_real_objects_and_runs_no_worker_program(tmp_path):
    marker = tmp_path / "marker"
    program = _program(tmp_path / "driver.sh", marker)

    def plant(root: Path, wt: Path):
        # An external diff driver and a text conversion, named for every file.
        _git(root, "config", "diff.external", str(program))
        _git(root, "config", "diff.t.textconv", str(program))
        (wt / ".gitattributes").write_text("*.txt diff=t\n")

    payload = _candidate_diff(tmp_path, plant)

    assert not marker.exists()
    assert payload == ""  # config naming a program: the diff is not taken at all


def test_repair_candidate_diff_ignores_replaced_base_object(tmp_path):
    def plant(root: Path, wt: Path):
        old = _git(root, "rev-parse", "HEAD:f.txt").stdout.strip()
        forged = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=root,
            input="forged\n",
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        _git(root, "replace", old, forged)

    payload = _candidate_diff(tmp_path, plant)

    assert "-old" in payload and "+new" in payload
    assert "forged" not in payload


def test_repair_candidate_diff_ignores_rewritten_git_pointer(tmp_path):
    def plant(root: Path, wt: Path):
        decoy = _repo(tmp_path / "decoy", "forged\n")
        (wt / ".git").write_text(f"gitdir: {decoy / '.git'}\n")

    payload = _candidate_diff(tmp_path, plant)

    assert "forged" not in payload  # refused or read from the real git dir, never the decoy


# ---------------------------------------------------------------------------
# worker registry: git apply after the Ollama worker
# ---------------------------------------------------------------------------

_PATCH = (
    b"diff --git a/f.txt b/f.txt\nindex 8f3f5f0..9b5f0b1 100644\n--- a/f.txt\n+++ b/f.txt\n"
    b"@@ -1 +1 @@\n-old\n+after\n"
)


def _run_ollama(tmp_path, monkeypatch, plant):
    target = _repo(tmp_path / "target")

    monkeypatch.setenv("NEXUS_LOCAL_MODEL_CALL_ALLOWED", "1")
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/ollama")

    def fake_worker(request, on_process_group=None):
        plant(target)
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=_PATCH,
            stderr=b"",
            wall_time_ms=1,
            process_group_id=None,
        )

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = OllamaPatchWorkerAdapter(executable="ollama").invoke(
        SimpleNamespace(task_id="ollama-3291"),
        SimpleNamespace(target_worktree=str(target)),
        prompt="change file",
    )
    return target, receipt


def test_ollama_patch_apply_is_pinned_to_the_real_repository(tmp_path, monkeypatch):
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    (decoy / "f.txt").write_text("old\n")

    def plant(target: Path):
        # The worker points the repository's work tree somewhere else.
        _git(target, "config", "core.worktree", str(decoy))

    target, receipt = _run_ollama(tmp_path, monkeypatch, plant)

    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert (target / "f.txt").read_text() == "after\n"
    assert (decoy / "f.txt").read_text() == "old\n"


def test_ollama_patch_apply_is_refused_when_git_pointer_is_rewritten(tmp_path, monkeypatch):
    marker = tmp_path / "marker"

    def plant(target: Path):
        evil = _evil_gitdir(tmp_path / "evil.git", marker)
        shutil.rmtree(target / ".git")
        (target / ".git").write_text(f"gitdir: {evil}\n")

    target, receipt = _run_ollama(tmp_path, monkeypatch, plant)

    assert not marker.exists()
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert (target / "f.txt").read_text() == "old\n"


# ---------------------------------------------------------------------------
# Review round 1 (#3291): each site's test goes red when that site runs plain git again
# ---------------------------------------------------------------------------


def _worker_clone(src: Path, dest: Path) -> Path:
    """A non-bare copy of ``src`` the worker made; its own config is the worker's to write."""
    _git(src.parent, "clone", "-q", str(src), str(dest))
    return dest


def _run_shift(tmp_path: Path, monkeypatch, worker_round):
    from nexus.app.nightshift_runner_service import RoundOutcome  # noqa: F401

    monkeypatch.setenv("NIGHTSHIFT_BYPASS_LEARN_SLO", "1")
    root = _repo(tmp_path / "root")
    (root / "target.py").write_text("value = 1\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "target")
    shift = AutoResearchNightShift(
        "target.py", project_root=root, max_rounds=1, convergence_patience=1
    )
    shift.keep_worktree = True
    shift.tracelog_path = tmp_path / "tracelog.jsonl"
    shift.lesson_writeback_path = tmp_path / "lesson.json"
    shift.pending_manifest_path = root / ".nexus/nightshift/pending.json"
    shift.worktree_mgr.workspace_base = tmp_path / "leases"
    shift.worktree_mgr.workspace_base.mkdir()
    shift.resolved_target_file = "target.py"
    shift._resolve_target_file = lambda: "target.py"
    shift._run_round = lambda round_id, workpath: worker_round(root, Path(workpath))
    shift._run_tier2_validation = lambda _workpath: (True, "tier2_pass")
    records: list = []
    shift._log_trace = lambda *args, **kwargs: records.append(args[1])
    queued: list = []
    shift._append_to_pending_manifest = lambda *a, **k: queued.append(a)
    shift.run()
    return shift, records, queued


def test_nightshift_run_reset_runs_no_file_monitor_program(tmp_path, monkeypatch):
    from nexus.app.nightshift_runner_service import RoundOutcome

    marker = tmp_path / "marker"
    monitor = _program(tmp_path / "monitor.sh", marker)

    def worker_round(root: Path, workpath: Path):
        _git(root, "config", "core.fsmonitor", str(monitor))
        (workpath / "target.py").write_text("scratch\n")
        return RoundOutcome(0.0, "", "NO_CHANGE", "same file")

    _, records, _ = _run_shift(tmp_path, monkeypatch, worker_round)

    assert "NO_CHANGE" in records
    assert not marker.exists()


def test_nightshift_commit_ignores_git_pointer_to_worker_clone_with_hooks(tmp_path):
    runner, root, workpath = _leased_runner(tmp_path)
    marker = tmp_path / "marker"
    clone = _worker_clone(root, tmp_path / "clone")
    hooks = tmp_path / "clone-hooks"
    hooks.mkdir()
    _program(hooks / "pre-commit", marker)
    _git(clone, "config", "core.hooksPath", str(hooks))
    (workpath / ".git").write_text(f"gitdir: {clone / '.git'}\n")
    (workpath / "f.txt").write_text("new\n")
    base_before = runner.base_commit

    committed = runner._commit_improvement(workpath, 1.0)

    assert not marker.exists()
    assert committed is False
    assert runner.base_commit == base_before


def test_nightshift_revision_ignores_git_pointer_to_decoy(tmp_path):
    runner, root, workpath = _leased_runner(tmp_path)
    real = _git(root, "rev-parse", "HEAD").stdout.strip()
    assert runner._workspace_revision(workpath) == real
    decoy = _repo(tmp_path / "decoy", "forged\n")
    decoy_head = _git(decoy, "rev-parse", "HEAD").stdout.strip()
    (workpath / ".git").write_text(f"gitdir: {decoy / '.git'}\n")

    assert runner._workspace_revision(workpath) != decoy_head


def test_nightshift_run_does_not_promote_when_git_pointer_rewritten_mid_round(
    tmp_path, monkeypatch
):
    from nexus.app.nightshift_runner_service import RoundOutcome

    decoy = _repo(tmp_path / "decoy", "forged\n")

    def worker_round(root: Path, workpath: Path):
        (workpath / ".git").write_text(f"gitdir: {decoy / '.git'}\n")
        return RoundOutcome(9.0, "value = 2\n", "SCORED", "improved")

    shift, records, queued = _run_shift(tmp_path, monkeypatch, worker_round)

    assert "GIT_UNTRUSTED" in records
    assert "IMPROVED" not in records
    assert queued == []
    assert not shift.pending_manifest_path.exists()


def test_repair_candidate_diff_ignores_git_pointer_to_worker_clone_with_diff_program(tmp_path):
    marker = tmp_path / "marker"
    program = _program(tmp_path / "driver.sh", marker)

    def plant(root: Path, wt: Path):
        clone = _worker_clone(root, tmp_path / "clone")
        _git(clone, "config", "diff.external", str(program))
        (wt / ".git").write_text(f"gitdir: {clone / '.git'}\n")

    payload = _candidate_diff(tmp_path, plant)

    assert not marker.exists()
    assert payload == ""


def test_repair_candidate_diff_ignores_git_pointer_to_worker_clone_with_replaced_object(tmp_path):
    def plant(root: Path, wt: Path):
        clone = _worker_clone(root, tmp_path / "clone")
        old = _git(clone, "rev-parse", "HEAD:f.txt").stdout.strip()
        forged = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=clone,
            input="forged\n",
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        _git(clone, "replace", old, forged)
        (wt / ".git").write_text(f"gitdir: {clone / '.git'}\n")

    payload = _candidate_diff(tmp_path, plant)

    assert "forged" not in payload
    assert payload == ""


def _filter_plant(tmp_path: Path, marker: Path):
    program = _program(tmp_path / "filter.sh", marker)

    def plant(target: Path):
        _git(target, "config", "filter.x.clean", str(program))
        _git(target, "config", "filter.x.smudge", str(program))
        (target / ".gitattributes").write_text("*.txt filter=x\n")

    return plant


def test_ollama_patch_apply_refuses_when_target_config_names_a_program(tmp_path, monkeypatch):
    marker = tmp_path / "marker"

    target, receipt = _run_ollama(tmp_path, monkeypatch, _filter_plant(tmp_path, marker))

    assert not marker.exists()
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert (target / "f.txt").read_text() == "old\n"


def test_nightshift_commit_that_does_not_land_is_not_promoted(tmp_path):
    runner, root, workpath = _leased_runner(tmp_path)
    (workpath / "f.txt").write_text("new\n")
    base_before = runner.base_commit
    real = runner._workpath_git

    def commit_fails(path, *args):
        if "commit" in args:
            return subprocess.CompletedProcess(args, 1, "", "commit failed")
        return real(path, *args)

    runner._workpath_git = commit_fails

    assert runner._commit_improvement(workpath, 1.0) is False
    assert runner.base_commit == base_before


def test_nightshift_stage_failure_is_not_promoted(tmp_path):
    runner, root, workpath = _leased_runner(tmp_path)
    (workpath / "f.txt").write_text("new\n")
    base_before = runner.base_commit
    real = runner._workpath_git

    def add_fails(path, *args):
        if "add" in args:
            return subprocess.CompletedProcess(args, 128, "", "permission denied")
        return real(path, *args)

    runner._workpath_git = add_fails

    assert runner._commit_improvement(workpath, 1.0) is False
    assert runner.base_commit == base_before


def test_repair_candidate_diff_refuses_an_option_shaped_source_revision_3361(tmp_path, monkeypatch):
    written = tmp_path / "written-by-git"
    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if list(cmd) == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=f"--output={written}\n", stderr="")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)

    payload = _candidate_diff(tmp_path, lambda root, wt: None)

    assert not written.exists()
    assert payload == ""
