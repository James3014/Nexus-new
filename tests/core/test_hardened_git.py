"""Restore and rollback paths run git only through nexus.core.hardened_git.

Each site runs git in a directory whose repository a candidate may have written: the
candidate restore, the action-protocol rollback, the transaction rollback and the heal
workspace reset. Every repo here is a fresh ``git init`` under ``tmp_path``; each test first
moves the cwd to a sentinel directory, and every hook or filter script only touches a marker
file under ``tmp_path``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, cast
from unittest.mock import MagicMock

import pytest

from nexus.core import hardened_git
from nexus.core.engine.nexus_transaction import TransactionManager
from nexus.services.local_heal.action_protocol import ActionProtocol
from nexus.services.local_heal.candidate_search import CandidatePatchSearcher
from nexus.services.local_heal.orchestrator import HealOrchestrator

DIRTY_EDIT = "x = 2  # uncommitted edit\n"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _repo_with_local_work(root: Path) -> Path:
    """A git repo with one uncommitted edit (notes.py)."""
    root.mkdir(parents=True)
    (root / "notes.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "base")
    (root / "notes.py").write_text(DIRTY_EDIT, encoding="utf-8")
    return root


def _restore_candidate_files(repo: Path) -> Any:
    searcher = CandidatePatchSearcher(parser=MagicMock(), patch_applier=MagicMock())
    return searcher._restore_files(repo, [cast(Any, SimpleNamespace(file_path="notes.py"))])


def _roll_back_action_protocol(repo: Path) -> Any:
    protocol = ActionProtocol(
        protocol_id="p",
        protocol_type="MULTI_STEP_LOCAL_EDIT",
        task_id="t",
        files_involved=["notes.py"],
    )
    return protocol.rollback(repo)


def _roll_back_transaction(repo: Path) -> Any:
    return TransactionManager(str(repo)).audit_rollback("t")


def _reset_heal_workspace(repo: Path) -> Any:
    ctx = SimpleNamespace(op=SimpleNamespace(repo_dir=repo))
    return HealOrchestrator._reset_workspace(cast(Any, SimpleNamespace()), cast(Any, ctx))


SITES: dict[str, Callable[[Path], Any]] = {
    "candidate_restore": _restore_candidate_files,
    "action_protocol_rollback": _roll_back_action_protocol,
    "transaction_rollback": _roll_back_transaction,
}
# What each site returns when it restored nothing (the transaction reports failure).
REFUSED = {
    "candidate_restore": None,
    "action_protocol_rollback": None,
    "transaction_rollback": False,
    "heal_workspace_reset": None,
}
RESTORED = {
    "candidate_restore": None,
    "action_protocol_rollback": None,
    "transaction_rollback": True,
}


@pytest.fixture
def env(tmp_path, monkeypatch):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / "SENTINEL").write_text("cwd\n", encoding="utf-8")
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.delenv("NEXUS_ROOT", raising=False)
    yield tmp_path
    assert (cwd / "SENTINEL").read_text(encoding="utf-8") == "cwd\n"


def _marker_script(tmp_path: Path, name: str, marker: Path, *, passthrough: bool = False) -> Path:
    tools = tmp_path / "tools"
    tools.mkdir(exist_ok=True)
    script = tools / name
    script.write_text(f'#!/bin/sh\ntouch "{marker}"\n' + ("cat\n" if passthrough else ""))
    script.chmod(0o755)
    return script


@pytest.mark.parametrize("site", sorted(SITES))
def test_restore_and_rollback_do_not_run_a_post_checkout_hook_the_candidate_created(env, site):
    repo = _repo_with_local_work(env / "repo")
    marker = env / "hook-ran"
    # post-checkout fires on a path checkout; reset --hard fires the other two instead.
    for hook in ("post-checkout", "reference-transaction", "post-index-change"):
        path = repo / ".git" / "hooks" / hook
        path.write_text(f'#!/bin/sh\ntouch "{marker}"\n', encoding="utf-8")
        path.chmod(0o755)

    assert SITES[site](repo) == RESTORED[site]

    assert not marker.exists()
    assert (repo / "notes.py").read_text(encoding="utf-8") == "x = 1\n"


@pytest.mark.parametrize("site", sorted(SITES))
def test_restore_and_rollback_refuse_a_repository_with_a_candidate_configured_filter(env, site):
    repo = _repo_with_local_work(env / "repo")
    (repo / ".gitattributes").write_text("*.py filter=mark\n", encoding="utf-8")
    _git(repo, "add", ".gitattributes")
    _git(repo, "commit", "-qm", "attributes", "--", ".gitattributes")
    marker = env / "filter-ran"
    script = _marker_script(env, "filter.sh", marker, passthrough=True)
    with open(repo / ".git" / "config", "a", encoding="utf-8") as config:
        config.write(f'[filter "mark"]\n\tsmudge = {script}\n\tclean = {script}\n')

    assert SITES[site](repo) == REFUSED[site]

    assert not marker.exists()
    assert (repo / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT


@pytest.mark.parametrize("site", sorted(SITES))
def test_restore_and_rollback_still_restore_the_candidate_edit(env, site):
    repo = _repo_with_local_work(env / "repo")
    (repo / "untracked.py").write_text("y\n", encoding="utf-8")

    assert SITES[site](repo) == RESTORED[site]

    assert (repo / "notes.py").read_text(encoding="utf-8") == "x = 1\n"
    # Only the transaction rollback cleans untracked files.
    assert (repo / "untracked.py").exists() == (site != "transaction_rollback")


@pytest.mark.parametrize("site", sorted(SITES))
def test_restore_and_rollback_leave_a_work_tree_named_elsewhere_untouched(env, site):
    repo = _repo_with_local_work(env / "repo")
    other = env / "other"
    other.mkdir()
    (other / "notes.py").write_text("other work\n", encoding="utf-8")
    (other / "keep.txt").write_text("keep\n", encoding="utf-8")
    _git(repo, "config", "core.worktree", str(other))

    assert SITES[site](repo) == REFUSED[site]

    assert (other / "notes.py").read_text(encoding="utf-8") == "other work\n"
    assert (other / "keep.txt").exists()
    assert (repo / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT


@pytest.mark.parametrize("site", sorted(REFUSED))
def test_every_restore_site_asks_the_shared_hardened_git_config_check(env, site, monkeypatch):
    repo = _repo_with_local_work(env / "repo")
    seen: list[list[str]] = []

    def refuse(names: list[str]) -> bool:
        seen.append(list(names))
        return True

    monkeypatch.setattr(hardened_git, "config_names_a_repository_program", refuse)
    run = {**SITES, "heal_workspace_reset": _reset_heal_workspace}[site]

    assert run(repo) == REFUSED[site]

    assert len(seen) == 1 and "core.bare" in seen[0]
    assert (repo / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT


ALL_SITES = {**SITES, "heal_workspace_reset": _reset_heal_workspace}


@pytest.mark.parametrize("site", sorted(ALL_SITES))
def test_restore_and_rollback_refuse_a_repository_with_a_config_defined_hook(env, site):
    repo = _repo_with_local_work(env / "repo")
    marker = env / "config-hook-ran"
    # core.hooksPath does not cover hooks named in config (hook.<name>.command).
    _git(repo, "config", "hook.mark.command", f'touch "{marker}"')
    for event in ("post-checkout", "reference-transaction", "post-index-change"):
        _git(repo, "config", "--add", "hook.mark.event", event)

    assert ALL_SITES[site](repo) == REFUSED[site]

    assert not marker.exists()
    assert (repo / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT


@pytest.mark.parametrize("site", sorted(SITES))
def test_restore_and_rollback_leave_a_git_dir_kept_elsewhere_untouched(env, site):
    repo = _repo_with_local_work(env / "repo")
    outside = env / "outside.git"
    (repo / ".git").rename(outside)
    (repo / ".git").write_text(f"gitdir: {outside}\n", encoding="utf-8")
    index = (outside / "index").read_bytes()

    assert SITES[site](repo) == REFUSED[site]

    assert (outside / "index").read_bytes() == index
    assert not (outside / "ORIG_HEAD").exists()
    assert (repo / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT


@pytest.mark.parametrize("site", sorted(SITES))
def test_restore_and_rollback_act_on_their_repo_under_a_foreign_git_environment(
    env, site, monkeypatch
):
    repo = _repo_with_local_work(env / "repo")
    elsewhere = _repo_with_local_work(env / "elsewhere")
    (elsewhere / "untracked.py").write_text("keep\n", encoding="utf-8")
    monkeypatch.setenv("GIT_DIR", str(elsewhere / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(elsewhere))

    assert SITES[site](repo) == RESTORED[site]

    assert (repo / "notes.py").read_text(encoding="utf-8") == "x = 1\n"
    assert (elsewhere / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT
    assert (elsewhere / "untracked.py").exists()


@pytest.mark.parametrize("outcome", ["error", "timeout"])
def test_an_unreadable_repository_config_counts_as_naming_a_program(env, monkeypatch, outcome):
    def failing_git(repo_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(["git", *args], hardened_git.GIT_TIMEOUT_S)
        return subprocess.CompletedProcess(["git", *args], 1, "", "error")

    monkeypatch.setattr(hardened_git, "run_hardened_git", failing_git)

    assert hardened_git.repository_config_can_start_a_program(env) is True


def test_reset_clears_a_stale_index_lock_a_timed_out_step_left_and_the_next_reset_restores(
    env, monkeypatch, caplog
):
    from nexus.services.local_heal import orchestrator

    repo = _repo_with_local_work(env / "repo")
    lock = repo / ".git" / "index.lock"
    real_git = orchestrator.run_hardened_git

    def checkout_times_out(repo_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
        if args[:1] == ("checkout",):
            lock.write_text("", encoding="utf-8")  # what a killed checkout leaves behind
            raise subprocess.TimeoutExpired(["git", *args], hardened_git.GIT_TIMEOUT_S)
        return real_git(repo_dir, *args)

    monkeypatch.setattr(orchestrator, "run_hardened_git", checkout_times_out)
    with caplog.at_level("WARNING", logger="nexus.services.local_heal.orchestrator"):
        _reset_heal_workspace(repo)

    assert not lock.exists()
    assert "removed a stale index.lock" in caplog.text
    assert (repo / "notes.py").read_text(encoding="utf-8") == DIRTY_EDIT

    monkeypatch.setattr(orchestrator, "run_hardened_git", real_git)
    _reset_heal_workspace(repo)

    assert (repo / "notes.py").read_text(encoding="utf-8") == "x = 1\n"


def test_a_timed_out_git_call_no_longer_counts_as_running(env, monkeypatch):
    repo = _repo_with_local_work(env / "repo")
    (repo / ".git" / "index.lock").write_text("", encoding="utf-8")

    def timed_out(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert repo.resolve() in hardened_git._RUNNING
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(hardened_git.subprocess, "run", timed_out)
    with pytest.raises(subprocess.TimeoutExpired):
        hardened_git.run_hardened_git(repo, "checkout", "--", ".")

    assert repo.resolve() not in hardened_git._RUNNING
    assert hardened_git.clear_stale_index_lock(repo, repo / ".git") is True
    assert not (repo / ".git" / "index.lock").exists()


def test_an_index_lock_is_kept_while_a_git_call_still_runs_in_the_repo(env, monkeypatch):
    repo = _repo_with_local_work(env / "repo")
    lock = repo / ".git" / "index.lock"
    lock.write_text("", encoding="utf-8")
    monkeypatch.setitem(hardened_git._RUNNING, repo.resolve(), 1)

    assert hardened_git.clear_stale_index_lock(repo, repo / ".git") is False
    assert lock.exists()


def test_an_index_lock_in_a_git_dir_outside_the_repo_is_kept(env):
    repo = _repo_with_local_work(env / "repo")
    outside = env / "outside.git"
    outside.mkdir()
    lock = outside / "index.lock"
    lock.write_text("", encoding="utf-8")

    assert hardened_git.clear_stale_index_lock(repo, outside) is False
    assert lock.exists()
