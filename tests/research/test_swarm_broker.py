from pathlib import Path
import os
import subprocess

import pytest

from nexus.research.swarm_broker import SwarmBroker


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_repo(repo: Path) -> str:
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "nexus@example.test")
    _git(repo, "config", "user.name", "Nexus Test")
    _git(repo, "config", "core.hooksPath", "/dev/null")
    (repo / "tracked.txt").write_text("controller\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "branch", "-M", "main")
    return _git(repo, "rev-parse", "HEAD")


def test_sync_scope_normalizes_absolute_paths(tmp_path: Path):
    source = tmp_path / ".nexus" / "bench_cases" / "hard-001" / "target.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('x')\n", encoding="utf-8")
    swarm = tmp_path / ".nexus-swarm-001"
    swarm.mkdir()

    broker = SwarmBroker(tmp_path)
    broker.sync_scope(swarm, [str(source)], required_configs=[])

    copied = swarm / ".nexus" / "bench_cases" / "hard-001" / "target.py"
    assert copied.read_text(encoding="utf-8") == "print('x')\n"
    assert copied.resolve() != source.resolve()


def test_release_unlinks_shared_cache_symlinks(tmp_path: Path):
    cache = tmp_path / ".ruff_cache"
    cache.mkdir()
    swarm = tmp_path / ".nexus-swarm-001"
    swarm.mkdir()
    (swarm / ".swarm_lock").write_text("", encoding="utf-8")

    broker = SwarmBroker(tmp_path)
    broker._mount_shared_cache(swarm)
    assert (swarm / ".ruff_cache").is_symlink()

    broker.release(swarm)

    assert not (swarm / ".ruff_cache").exists()
    assert not (swarm / ".swarm_lock").exists()


def test_acquire_rejects_placeholder_child_resolving_to_controller(tmp_path: Path):
    controller = tmp_path / "controller"
    _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    swarm.mkdir()

    broker = SwarmBroker(controller)

    assert broker.acquire(timeout_sec=0.05) is None
    assert not (swarm / ".swarm_lock").exists()


def test_release_rejects_placeholder_without_cleaning_contents(tmp_path: Path):
    controller = tmp_path / "controller"
    _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    swarm.mkdir()
    (swarm / ".swarm_lock").write_text("", encoding="utf-8")
    payload = swarm / "candidate.txt"
    payload.write_text("must not be deleted\n", encoding="utf-8")

    broker = SwarmBroker(controller)
    broker.release(swarm)

    assert payload.read_text(encoding="utf-8") == "must not be deleted\n"
    assert not (swarm / ".swarm_lock").exists()


def test_acquire_accepts_independent_registered_worktree(tmp_path: Path):
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)

    broker = SwarmBroker(controller)

    assert broker.acquire(timeout_sec=0.05).resolve() == swarm.resolve()
    assert _git(swarm, "rev-parse", "--show-toplevel") == str(swarm.resolve())
    assert (swarm / ".swarm_lock").exists()


def _sentinel_cwd(tmp_path: Path, monkeypatch) -> Path:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "SENTINEL").write_text("keep", encoding="utf-8")
    monkeypatch.chdir(sandbox)
    # git must not discover any repository above tmp_path.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    return sandbox


def _add_foreign_worktree(controller: Path, path: Path, base: str) -> None:
    _git(controller, "worktree", "add", "--detach", str(path), base)
    (path / "tracked.txt").write_text("uncommitted edit\n", encoding="utf-8")
    (path / "wip.txt").write_text("untracked work\n", encoding="utf-8")


def test_non_git_workspace_keeps_real_swarm_dir_contents(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    workspace = tmp_path / "workspace"
    swarm = workspace / ".nexus-swarm-001"
    (swarm / "data").mkdir(parents=True)
    (swarm / "data" / "kept.txt").write_text("x", encoding="utf-8")

    broker = SwarmBroker(workspace)

    assert broker.is_independently_registered_worktree(swarm) is False
    assert broker.acquire(timeout_sec=0.05) is None
    broker.release(swarm)
    assert (swarm / "data" / "kept.txt").exists()
    assert (sandbox / "SENTINEL").exists()


def test_non_git_workspace_ignores_symlinked_swarm_entry(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = tmp_path / "target"
    (target / "data").mkdir(parents=True)
    (target / "data" / "kept.txt").write_text("x", encoding="utf-8")
    (target / "notes.txt").write_text("y", encoding="utf-8")
    (workspace / ".nexus-swarm-001").symlink_to(target)

    broker = SwarmBroker(workspace)
    assert broker.swarm_dirs == []
    swarm_dir = broker.acquire(timeout_sec=0.05)
    if swarm_dir is not None:
        broker.release(swarm_dir)
    broker.release(workspace / ".nexus-swarm-001")

    assert (sandbox / "SENTINEL").exists()
    assert (target / "notes.txt").exists()
    assert (target / "data" / "kept.txt").exists()


def test_git_workspace_ignores_symlink_to_registered_worktree(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    other = tmp_path / "other-wt"
    _add_foreign_worktree(controller, other, base)
    (other / ".swarm_lock").write_text("", encoding="utf-8")
    link = controller / ".nexus-swarm-001"
    link.symlink_to(other)

    broker = SwarmBroker(controller)
    assert broker.swarm_dirs == []
    assert broker.is_independently_registered_worktree(link) is False
    swarm_dir = broker.acquire(timeout_sec=0.05)
    if swarm_dir is not None:
        broker.release(swarm_dir)
    broker.release(link)

    assert (sandbox / "SENTINEL").exists()
    assert (other / "wip.txt").exists()
    assert (other / "tracked.txt").read_text(encoding="utf-8") == "uncommitted edit\n"
    assert (other / ".swarm_lock").exists()


def test_release_leaves_registered_worktree_outside_workspace_untouched(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    other = tmp_path / ".nexus-swarm-001"
    _add_foreign_worktree(controller, other, base)

    SwarmBroker(controller).release(other)

    assert (sandbox / "SENTINEL").exists()
    assert (other / "wip.txt").exists()
    assert (other / "tracked.txt").read_text(encoding="utf-8") == "uncommitted edit\n"


def test_release_resets_registered_child_worktree(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)

    broker = SwarmBroker(controller)
    acquired = broker.acquire(timeout_sec=0.05)
    assert acquired is not None
    (swarm / "tracked.txt").write_text("candidate edit\n", encoding="utf-8")
    (swarm / "scratch.txt").write_text("candidate scratch\n", encoding="utf-8")
    broker.release(acquired)

    assert (sandbox / "SENTINEL").exists()
    assert (swarm / "tracked.txt").read_text(encoding="utf-8") == "controller\n"
    assert not (swarm / "scratch.txt").exists()
    assert not (swarm / ".swarm_lock").exists()


def test_release_leaves_worktree_reached_through_parent_of_link_untouched(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    _git(controller, "worktree", "add", "--detach", str(controller / ".nexus-swarm-001"), base)
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "sub").mkdir(parents=True)
    other = elsewhere / ".nexus-swarm-001"
    _add_foreign_worktree(controller, other, base)
    (controller / "link").symlink_to(elsewhere / "sub", target_is_directory=True)

    SwarmBroker(controller).release(controller / "link" / ".." / ".nexus-swarm-001")

    assert (sandbox / "SENTINEL").exists()
    assert (other / "wip.txt").exists()
    assert (other / "tracked.txt").read_text(encoding="utf-8") == "uncommitted edit\n"


def _controller_head(controller: Path) -> tuple[str, str]:
    return (
        _git(controller, "rev-parse", "HEAD"),
        _git(controller, "symbolic-ref", "-q", "--short", "HEAD"),
    )


def test_swarm_gitfile_pointing_at_controller_gitdir_is_refused_and_head_kept(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    (swarm / ".git").write_text(f"gitdir: {controller / '.git'}\n", encoding="utf-8")
    before = _controller_head(controller)
    monkeypatch.setenv("NEXUS_WORKSPACE_BASE", str(tmp_path / "wsbase"))
    monkeypatch.setenv("NEXUS_WORKSPACE_LOCK", str(tmp_path / "merge.lock"))
    monkeypatch.setenv("NEXUS_ALLOW_LEGACY_SWARM_REUSE", "1")
    from nexus.services.workspace import WorkspaceManager

    WorkspaceManager(controller).lease("t-swarm", "isolated/t-swarm")

    assert _controller_head(controller) == before
    assert SwarmBroker(controller).is_independently_registered_worktree(swarm) is False
    assert (sandbox / "SENTINEL").exists()


def test_swarm_admin_entry_with_mismatched_back_pointer_is_refused(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    sibling = controller / ".nexus-swarm-002"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    _git(controller, "worktree", "add", "--detach", str(sibling), base)
    (sibling / "tracked.txt").write_text("sibling edit\n", encoding="utf-8")
    sibling_admin = _git(sibling, "rev-parse", "--absolute-git-dir")
    (swarm / ".git").write_text(f"gitdir: {sibling_admin}\n", encoding="utf-8")

    broker = SwarmBroker(controller)
    assert broker.is_independently_registered_worktree(swarm) is False
    broker.release(swarm)

    assert (sibling / "tracked.txt").read_text(encoding="utf-8") == "sibling edit\n"
    assert (sandbox / "SENTINEL").exists()


def test_swarm_created_by_git_worktree_add_is_accepted_and_reset(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    before = _controller_head(controller)

    broker = SwarmBroker(controller)
    assert broker.is_independently_registered_worktree(swarm) is True
    assert broker.acquire(timeout_sec=0.05) == swarm.resolve()
    (swarm / "tracked.txt").write_text("candidate edit\n", encoding="utf-8")
    broker.release(swarm)

    assert (swarm / "tracked.txt").read_text(encoding="utf-8") == "controller\n"
    assert not (swarm / ".swarm_lock").exists()
    assert _controller_head(controller) == before
    assert (sandbox / "SENTINEL").exists()


def test_swarm_gitfile_naming_another_repos_worktree_entry_is_refused(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    other = tmp_path / "other"
    other_base = _init_repo(other)
    other_wt = tmp_path / "other-wt"
    _git(other, "worktree", "add", "--detach", str(other_wt), other_base)
    other_admin = Path(_git(other_wt, "rev-parse", "--absolute-git-dir"))
    (other_admin / "gitdir").write_text(f"{swarm / '.git'}\n", encoding="utf-8")
    (swarm / ".git").write_text(f"gitdir: {other_admin}\n", encoding="utf-8")

    assert SwarmBroker(controller).is_independently_registered_worktree(swarm) is False
    assert (sandbox / "SENTINEL").exists()


def test_swarm_gitfile_symlinked_to_sibling_gitfile_is_refused(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    sibling = controller / ".nexus-swarm-002"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    _git(controller, "worktree", "add", "--detach", str(sibling), base)
    (swarm / ".git").unlink()
    (swarm / ".git").symlink_to(sibling / ".git")

    assert SwarmBroker(controller).is_independently_registered_worktree(swarm) is False
    assert SwarmBroker(controller).is_independently_registered_worktree(sibling) is True
    assert (sandbox / "SENTINEL").exists()


@pytest.mark.parametrize("back_pointer", [None, ""], ids=["missing", "empty"])
def test_swarm_admin_entry_without_back_pointer_is_refused(
    tmp_path: Path, monkeypatch, back_pointer
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    sibling = controller / ".nexus-swarm-002"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    _git(controller, "worktree", "add", "--detach", str(sibling), base)
    sibling_admin = Path(_git(sibling, "rev-parse", "--absolute-git-dir"))
    if back_pointer is None:
        (sibling_admin / "gitdir").unlink()
    else:
        (sibling_admin / "gitdir").write_text(back_pointer, encoding="utf-8")
    (swarm / ".git").write_text(f"gitdir: {sibling_admin}\n", encoding="utf-8")

    assert SwarmBroker(controller).is_independently_registered_worktree(swarm) is False
    assert (sandbox / "SENTINEL").exists()


def test_swarm_with_relative_back_pointer_is_accepted(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    admin = Path(_git(swarm, "rev-parse", "--absolute-git-dir"))
    relative = os.path.relpath(swarm.resolve() / ".git", admin)
    (admin / "gitdir").write_text(f"{relative}\n", encoding="utf-8")

    assert SwarmBroker(controller).is_independently_registered_worktree(swarm) is True
    assert (sandbox / "SENTINEL").exists()


@pytest.mark.parametrize("failing_arg", ["--git-common-dir", "--absolute-git-dir"])
def test_swarm_is_refused_when_git_dir_lookup_fails(tmp_path: Path, monkeypatch, failing_arg):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    broker = SwarmBroker(controller)
    real_git_output = broker._git_output

    def failing_git_output(args, cwd):
        if failing_arg in args:
            return None
        return real_git_output(args, cwd)

    monkeypatch.setattr(broker, "_git_output", failing_git_output)

    assert broker.is_independently_registered_worktree(swarm) is False
    assert (sandbox / "SENTINEL").exists()
