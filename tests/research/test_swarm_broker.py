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


# --- the admin entry's commondir must name the controller's common dir ---------------------


def test_swarm_admin_entry_with_foreign_commondir_is_refused_and_foreign_refs_kept(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    foreign = tmp_path / "foreign"
    _git(tmp_path, "clone", "-q", str(controller), str(foreign))
    _git(foreign, "config", "user.email", "nexus@example.test")
    _git(foreign, "config", "user.name", "Nexus Test")
    broker = SwarmBroker(controller)
    assert broker.is_independently_registered_worktree(swarm) is True  # positive control

    admin = Path(_git(swarm, "rev-parse", "--absolute-git-dir"))
    (admin / "commondir").write_text(f"{foreign / '.git'}\n", encoding="utf-8")
    assert (
        Path(_git(swarm, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        == (foreign / ".git").resolve()
    )
    assert broker.is_independently_registered_worktree(swarm) is False

    monkeypatch.setenv("NEXUS_WORKSPACE_BASE", str(tmp_path / "wsbase"))
    monkeypatch.setenv("NEXUS_WORKSPACE_LOCK", str(tmp_path / "merge.lock"))
    monkeypatch.setenv("NEXUS_ALLOW_LEGACY_SWARM_REUSE", "1")
    from nexus.services.workspace import WorkspaceManager

    WorkspaceManager(controller).lease("t-commondir", "isolated/t-commondir")

    assert _git(foreign, "branch", "--list", "isolated/t-commondir") == ""
    assert (sandbox / "SENTINEL").exists()


def test_swarm_with_default_relative_commondir_is_accepted(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    admin = Path(_git(swarm, "rev-parse", "--absolute-git-dir"))
    assert not Path((admin / "commondir").read_text(encoding="utf-8").strip()).is_absolute()

    assert SwarmBroker(controller).is_independently_registered_worktree(swarm) is True
    (admin / "commondir").write_text(f"{(controller / '.git').resolve()}\n", encoding="utf-8")
    assert SwarmBroker(controller).is_independently_registered_worktree(swarm) is True
    assert (sandbox / "SENTINEL").exists()


# --- release acts only on the directory it validated ----------------------------------------


def _victim_repo(tmp_path: Path) -> Path:
    victim = tmp_path / "victim"
    _init_repo(victim)
    (victim / "tracked.txt").write_text("victim uncommitted edit\n", encoding="utf-8")
    (victim / "victim_wip.txt").write_text("victim untracked work\n", encoding="utf-8")
    (victim / ".swarm_lock").write_text("", encoding="utf-8")
    return victim


def _victim_repo_intact(victim: Path) -> bool:
    tracked = (victim / "tracked.txt").read_text(encoding="utf-8")
    kept = all((victim / name).exists() for name in ("victim_wip.txt", ".swarm_lock"))
    return tracked == "victim uncommitted edit\n" and kept


def _swap_for_link(swarm: Path, target: Path, moved: Path) -> None:
    swarm.rename(moved)
    swarm.symlink_to(target, target_is_directory=True)


def test_release_leaves_link_swapped_in_after_registration_check_untouched(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    victim = _victim_repo(tmp_path)
    broker = SwarmBroker(controller)
    real_check = broker.is_independently_registered_worktree

    def check_then_swap(path):
        result = real_check(path)
        _swap_for_link(swarm, victim, tmp_path / "moved-swarm")
        return result

    monkeypatch.setattr(broker, "is_independently_registered_worktree", check_then_swap)
    broker.release(swarm)

    assert _victim_repo_intact(victim)
    assert (sandbox / "SENTINEL").exists()


def test_release_leaves_other_real_dir_swapped_in_after_registration_check_untouched(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    broker = SwarmBroker(controller)
    real_check = broker.is_independently_registered_worktree

    def check_then_replace(path):
        result = real_check(path)
        swarm.rename(tmp_path / "moved-swarm")
        swarm.mkdir()
        (swarm / "replacement_wip.txt").write_text("not validated\n", encoding="utf-8")
        (swarm / ".swarm_lock").write_text("", encoding="utf-8")
        return result

    monkeypatch.setattr(broker, "is_independently_registered_worktree", check_then_replace)
    broker.release(swarm)

    assert (swarm / "replacement_wip.txt").exists()
    assert (swarm / ".swarm_lock").exists()
    assert (sandbox / "SENTINEL").exists()


def test_release_skips_clean_when_swarm_is_swapped_after_checkout(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    (swarm / "candidate.txt").write_text("candidate scratch\n", encoding="utf-8")
    victim = _victim_repo(tmp_path)
    moved = tmp_path / "moved-swarm"
    real_run = subprocess.run

    def run_then_swap(cmd, *args, **kwargs):
        result = real_run(cmd, *args, **kwargs)
        if list(cmd[:2]) == ["git", "checkout"] and not swarm.is_symlink():
            _swap_for_link(swarm, victim, moved)
        return result

    monkeypatch.setattr(subprocess, "run", run_then_swap)
    SwarmBroker(controller).release(swarm)
    monkeypatch.setattr(subprocess, "run", real_run)

    assert swarm.is_symlink()  # the swap happened after the checkout
    assert (victim / "victim_wip.txt").exists()
    assert (moved / "candidate.txt").exists()  # clean did not run anywhere
    assert (sandbox / "SENTINEL").exists()


def test_release_fallback_cleanup_stops_when_swarm_is_swapped(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    victim = tmp_path / "victim"
    for name in ("a", "b"):
        (swarm / name).mkdir()
        (swarm / name / "f.txt").write_text("swarm\n", encoding="utf-8")
        (victim / name).mkdir(parents=True)
        (victim / name / "f.txt").write_text("victim\n", encoding="utf-8")
    (victim / "tracked.txt").write_text("victim\n", encoding="utf-8")  # same names as the swarm
    broker = SwarmBroker(controller)
    real_check = broker.is_independently_registered_worktree

    def check_then_drop_gitfile(path):
        result = real_check(path)
        (swarm / ".git").unlink()  # forces the non-git fallback cleanup
        return result

    import shutil

    real_rmtree = shutil.rmtree
    removed: list[str] = []

    def rmtree_then_swap(path, *args, **kwargs):
        real_rmtree(path, *args, **kwargs)
        removed.append(Path(path).name)
        if not swarm.is_symlink():
            _swap_for_link(swarm, victim, tmp_path / "moved-swarm")

    monkeypatch.setattr(broker, "is_independently_registered_worktree", check_then_drop_gitfile)
    monkeypatch.setattr(shutil, "rmtree", rmtree_then_swap)
    broker.release(swarm)
    monkeypatch.setattr(shutil, "rmtree", real_rmtree)

    assert len(removed) == 1
    assert all((victim / name / "f.txt").exists() for name in ("a", "b"))
    assert (victim / "tracked.txt").exists()
    assert (sandbox / "SENTINEL").exists()


# --- sync_scope writes only inside the swarm -------------------------------------------------


def _scope_layout(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    workspace = tmp_path / "parent" / "workspace"
    (workspace / "pkg" / "sub").mkdir(parents=True)
    (workspace / "pkg" / "mod.py").write_text("workspace mod\n", encoding="utf-8")
    (workspace / "pkg" / "sub" / "deep.py").write_text("workspace deep\n", encoding="utf-8")
    swarm = workspace / ".nexus-swarm-001"
    swarm.mkdir()
    return sandbox, workspace, swarm


def test_sync_scope_refuses_parent_and_outside_absolute_paths(tmp_path: Path, monkeypatch):
    sandbox, workspace, swarm = _scope_layout(tmp_path, monkeypatch)
    (workspace.parent / "victim.txt").write_text("FROM-PARENT\n", encoding="utf-8")
    (workspace / "victim.txt").write_text("USER WORK\n", encoding="utf-8")
    outside = tmp_path / "outside" / "secret.txt"
    outside.parent.mkdir()
    outside.write_text("outside\n", encoding="utf-8")
    (workspace / "link").symlink_to(outside.parent, target_is_directory=True)

    SwarmBroker(workspace).sync_scope(
        swarm,
        ["../victim.txt", "pkg/../pkg/mod.py", str(outside), "link/secret.txt"],
        required_configs=[],
    )

    assert (workspace / "victim.txt").read_text(encoding="utf-8") == "USER WORK\n"
    assert list(swarm.iterdir()) == []
    assert (sandbox / "SENTINEL").exists()


def test_sync_scope_does_not_write_through_links_planted_in_swarm(tmp_path: Path, monkeypatch):
    sandbox, workspace, swarm = _scope_layout(tmp_path, monkeypatch)
    outside_file_dir = tmp_path / "outside-pkg"
    outside_file_dir.mkdir()
    outside_sub = tmp_path / "outside-sub"
    outside_sub.mkdir()
    broker = SwarmBroker(workspace)

    (swarm / "pkg").symlink_to(outside_file_dir, target_is_directory=True)
    broker.sync_scope(swarm, ["pkg/mod.py", "pkg"], required_configs=[])
    assert list(outside_file_dir.iterdir()) == []

    (swarm / "pkg").unlink()
    (swarm / "pkg").mkdir()
    (swarm / "pkg" / "sub").symlink_to(outside_sub, target_is_directory=True)
    broker.sync_scope(swarm, ["pkg"], required_configs=[])
    assert list(outside_sub.iterdir()) == []
    assert (swarm / "pkg" / "mod.py").read_text(encoding="utf-8") == "workspace mod\n"
    assert (sandbox / "SENTINEL").exists()


def test_sync_scope_copies_relative_files_and_dirs_into_swarm(tmp_path: Path, monkeypatch):
    sandbox, workspace, swarm = _scope_layout(tmp_path, monkeypatch)
    alias = tmp_path / "workspace-link"
    alias.symlink_to(workspace, target_is_directory=True)

    SwarmBroker(alias).sync_scope(
        alias / swarm.name,
        ["pkg/mod.py", "pkg", str(workspace / "pkg" / "mod.py")],
        required_configs=[],
    )

    assert (swarm / "pkg" / "mod.py").read_text(encoding="utf-8") == "workspace mod\n"
    assert (swarm / "pkg" / "sub" / "deep.py").read_text(encoding="utf-8") == "workspace deep\n"
    assert not (swarm / "mod.py").exists()
    assert (sandbox / "SENTINEL").exists()


def test_swarm_is_refused_when_its_own_common_dir_lookup_fails(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    broker = SwarmBroker(controller)
    assert broker.is_independently_registered_worktree(swarm) is True  # positive control
    real_git_output = broker._git_output

    def failing_in_swarm(args, cwd):
        if "--git-common-dir" in args and Path(cwd).resolve() == swarm.resolve():
            return None
        return real_git_output(args, cwd)

    monkeypatch.setattr(broker, "_git_output", failing_in_swarm)

    assert broker.is_independently_registered_worktree(swarm) is False
    assert (sandbox / "SENTINEL").exists()
