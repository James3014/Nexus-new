"""The operation journal and the bounded swarm run git only through nexus.core.hardened_git.

The journal reads the identity and status of the directory a delegated agent ran and wrote
in; the swarm forks worktrees from its workspace root and commits a model's candidate in
each. Neither may start a program the repository names. Every repo here is a fresh
``git init`` under ``tmp_path``; each test moves the cwd to a sentinel directory first, and
every hook or config program only touches a marker file under ``tmp_path``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from nexus.engine.battle_swarm import BattleSwarm
from nexus.engine.swarm_run import _git as swarm_git
from nexus.engine.swarm_run import run_bounded_swarm
from nexus.services import direct_operation_journal as journal

HOOKS = (
    "pre-commit",
    "commit-msg",
    "post-commit",
    "post-checkout",
    "post-index-change",
    "reference-transaction",
)


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    sentinel = tmp_path / "sentinel"
    sentinel.mkdir()
    monkeypatch.chdir(sentinel)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    return tmp_path


def _repo(env: Path) -> Path:
    repo = env / "repo"
    (repo / "pkg").mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "user.email", "t@example.invalid")
    (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (repo / "pkg" / "mod.py").write_text("X = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    return repo


def _plant_hooks_and_fsmonitor(repo: Path, markers: Path) -> None:
    markers.mkdir(exist_ok=True)
    for hook in HOOKS:
        script = repo / ".git" / "hooks" / hook
        script.write_text(f"#!/bin/sh\ntouch '{markers}/hook.{hook}'\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)
    _git(repo, "config", "core.fsmonitor", f"touch '{markers}/fsmonitor'; true")


def _plant_config_hook(repo: Path, markers: Path, event: str) -> None:
    markers.mkdir(exist_ok=True)
    _git(repo, "config", "hook.mark.command", f"touch '{markers}/hook.config'")
    _git(repo, "config", "hook.mark.event", event)


def _fired(markers: Path) -> list[str]:
    return sorted(p.name for p in markers.iterdir()) if markers.exists() else []


# --- operation journal ----------------------------------------------------------------


def test_journal_baseline_reads_status_without_running_a_hook_or_fsmonitor(env):
    repo = _repo(env)
    markers = env / "markers"
    _plant_hooks_and_fsmonitor(repo, markers)
    (repo / "calc.py").write_text("changed\n", encoding="utf-8")
    (repo / "pkg" / "new.py").write_text("Y = 2\n", encoding="utf-8")

    baseline = journal.capture_source_baseline(str(repo))

    assert _fired(markers) == []
    assert baseline is not None
    assert {path: entry["status"] for path, entry in baseline["entries"].items()} == {
        "calc.py": " M",
        "pkg/new.py": "??",
    }


def test_journal_identity_from_a_subdirectory_is_the_repository_root_and_head(env):
    repo = _repo(env)

    root, head = journal._git_identity(str(repo / "pkg"))

    assert Path(str(root)).resolve() == repo.resolve()
    assert head == _git(repo, "rev-parse", "HEAD")
    assert journal._status_entries(str(repo / "pkg")) == {}


@pytest.mark.parametrize("event", ["post-index-change", "pre-commit"])
def test_journal_treats_a_repository_with_a_config_defined_hook_as_unattributable(env, event):
    repo = _repo(env)
    markers = env / "markers"
    _plant_config_hook(repo, markers, event)
    (repo / "calc.py").write_text("changed\n", encoding="utf-8")

    assert journal._git_identity(str(repo)) == (None, None)
    assert journal.capture_source_baseline(str(repo)) is None
    assert _fired(markers) == []


def test_journal_finds_no_repository_above_a_ceiling_or_in_a_missing_directory(env):
    repo = _repo(env)
    assert journal._git_identity(str(repo / "missing")) == (None, None)
    assert journal._git_identity(str(env / "sentinel")) == (None, None)


def test_journal_does_not_search_into_a_ceiling_directory(env, monkeypatch):
    repo = _repo(env)
    deeper = repo / "pkg" / "deeper"
    deeper.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(repo))

    assert journal._git_identity(str(deeper)) == (None, None)


# --- bounded swarm --------------------------------------------------------------------


def test_swarm_worktree_and_candidate_commit_run_no_hook_or_fsmonitor(env):
    root = _repo(env)
    markers = env / "markers"
    _plant_hooks_and_fsmonitor(root, markers)
    swarm = BattleSwarm(project_root=str(root), default_workers=1, run_dir=str(env / "runs"))
    swarm.run_dir.mkdir(parents=True)

    worktree = swarm._create_worktree("conservative", "battle_t_conservative_0")
    assert worktree is not None
    (worktree / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    swarm_git(["add", "calc.py"], worktree)
    commit = swarm_git(
        ["-c", "user.name=n", "-c", "user.email=n@n", "commit", "-q", "--no-verify", "-m", "c"],
        worktree,
    )
    swarm._cleanup_worktrees([worktree], ["battle_t_conservative_0"])

    assert commit.returncode == 0, commit.stderr
    assert _fired(markers) == []
    assert not worktree.exists()
    assert _git(root, "branch", "--list", "battle_t_conservative_0") == ""


def test_swarm_creates_no_worktree_in_a_repository_whose_config_names_a_program(env):
    root = _repo(env)
    markers = env / "markers"
    _plant_config_hook(root, markers, "post-checkout")
    swarm = BattleSwarm(project_root=str(root), default_workers=1, run_dir=str(env / "runs"))
    swarm.run_dir.mkdir(parents=True)

    assert swarm._create_worktree("conservative", "battle_t_conservative_0") is None
    assert _fired(markers) == []
    assert _git(root, "branch", "--list", "battle_t_conservative_0") == ""


def test_bounded_swarm_blocks_a_workspace_whose_config_names_a_program(env):
    root = _repo(env)
    (root / "repro.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    markers = env / "markers"
    _plant_config_hook(root, markers, "post-checkout")

    report = run_bounded_swarm(
        workspace_root=root,
        task_id="t1",
        task="fix",
        target_file="calc.py",
        verify_script="repro.py",
    )

    assert (report["status"], report["reason"]) == (
        "BLOCKED",
        "WORKSPACE_GIT_CONFIG_NAMES_A_PROGRAM",
    )
    assert _fired(markers) == []
    assert not (root / ".nexus").exists()
