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
    _git(swarm, "update-ref", "refs/worktree/nexus-swarm-base", "HEAD")
    (swarm / "candidate.txt").write_text("candidate scratch\n", encoding="utf-8")
    victim = _victim_repo(tmp_path)
    moved = tmp_path / "moved-swarm"
    real_run = subprocess.run

    def run_then_swap(cmd, *args, **kwargs):
        result = real_run(cmd, *args, **kwargs)
        if cmd[0] == "git" and "checkout" in cmd and not swarm.is_symlink():
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


def test_sync_scope_replaces_hard_linked_swarm_files_without_touching_the_shared_file(
    tmp_path: Path, monkeypatch
):
    sandbox, workspace, swarm = _scope_layout(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    shared_file = outside / "shared-file.txt"
    shared_deep = outside / "shared-deep.txt"
    shared_file.write_text("OUTSIDE FILE\n", encoding="utf-8")
    shared_deep.write_text("OUTSIDE DEEP\n", encoding="utf-8")
    (swarm / "pkg" / "sub").mkdir(parents=True)
    os.link(shared_file, swarm / "pkg" / "mod.py")
    os.link(shared_deep, swarm / "pkg" / "sub" / "deep.py")
    broker = SwarmBroker(workspace)

    broker.sync_scope(swarm, ["pkg/mod.py"], required_configs=[])
    broker.sync_scope(swarm, ["pkg"], required_configs=[])

    assert shared_file.read_text(encoding="utf-8") == "OUTSIDE FILE\n"
    assert shared_deep.read_text(encoding="utf-8") == "OUTSIDE DEEP\n"
    assert (swarm / "pkg" / "mod.py").read_text(encoding="utf-8") == "workspace mod\n"
    assert (swarm / "pkg" / "sub" / "deep.py").read_text(encoding="utf-8") == "workspace deep\n"
    assert sorted(p.name for p in (swarm / "pkg").iterdir()) == ["mod.py", "sub"]
    assert (sandbox / "SENTINEL").exists()


# --- release: git through the hardened runner, pinned to the swarm's own registration -------


def _registered_swarm(tmp_path: Path) -> tuple[Path, Path]:
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    # A leased swarm has its base recorded by `acquire`; release now fails closed without it.
    _git(swarm, "update-ref", "refs/worktree/nexus-swarm-base", "HEAD")
    (swarm / ".swarm_lock").write_text("", encoding="utf-8")
    (swarm / "candidate.txt").write_text("candidate scratch\n", encoding="utf-8")
    return controller, swarm


def _rewrite_gitfile_after_check(broker: SwarmBroker, monkeypatch, swarm: Path, text: str) -> None:
    real_check = broker.is_independently_registered_worktree

    def check_then_rewrite(path):
        result = real_check(path)
        (swarm / ".git").write_text(text, encoding="utf-8")
        return result

    monkeypatch.setattr(broker, "is_independently_registered_worktree", check_then_rewrite)


def test_release_keeps_repo_named_by_gitfile_rewritten_after_check(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    victim = _victim_repo(tmp_path)
    planted = swarm / "planted"
    _git(swarm, "init", "-q", str(planted))
    _git(planted, "config", "core.worktree", str(victim))
    broker = SwarmBroker(controller)
    _rewrite_gitfile_after_check(broker, monkeypatch, swarm, f"gitdir: {planted / '.git'}\n")

    broker.release(swarm)

    assert _victim_repo_intact(victim)
    assert (swarm / ".swarm_lock").exists()
    assert (sandbox / "SENTINEL").exists()


def test_release_keeps_swarm_locked_when_gitfile_names_another_repos_registration(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    other = tmp_path / "other"
    other_base = _init_repo(other)
    other_wt = tmp_path / "other-wt"
    _git(other, "worktree", "add", "--detach", str(other_wt), other_base)
    other_admin = Path(_git(other_wt, "rev-parse", "--absolute-git-dir"))
    (other_admin / "gitdir").write_text(f"{swarm.resolve() / '.git'}\n", encoding="utf-8")
    broker = SwarmBroker(controller)
    _rewrite_gitfile_after_check(broker, monkeypatch, swarm, f"gitdir: {other_admin}\n")

    broker.release(swarm)

    assert (swarm / ".swarm_lock").exists()
    assert (swarm / "candidate.txt").exists()
    assert (sandbox / "SENTINEL").exists()


def test_release_keeps_swarm_locked_when_repository_config_names_a_filter(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    marker = tmp_path / "filter-ran"
    _git(controller, "config", "filter.mark.smudge", f"touch '{marker}'; cat")
    (swarm / ".gitattributes").write_text("tracked.txt filter=mark\n", encoding="utf-8")
    (swarm / "tracked.txt").write_text("candidate edit\n", encoding="utf-8")

    SwarmBroker(controller).release(swarm)

    assert not marker.exists()
    assert (swarm / ".swarm_lock").exists()
    assert (sandbox / "SENTINEL").exists()


def test_release_keeps_swarm_locked_when_git_reset_fails(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    real_run = subprocess.run

    def failing_checkout(cmd, *args, **kwargs):
        if cmd[0] == "git" and "checkout" in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", "error: checkout refused\n")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", failing_checkout)
    SwarmBroker(controller).release(swarm)
    monkeypatch.setattr(subprocess, "run", real_run)

    assert (swarm / ".swarm_lock").exists()
    assert (swarm / "candidate.txt").exists()
    assert (sandbox / "SENTINEL").exists()


@pytest.mark.parametrize("after", ["config", "checkout"])
def test_release_leaves_replacement_with_copied_gitfile_untouched(
    tmp_path: Path, monkeypatch, after
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    moved = tmp_path / "moved-swarm"
    real_run = subprocess.run
    swapped: list[bool] = []

    def run_then_replace(cmd, *args, **kwargs):
        result = real_run(cmd, *args, **kwargs)
        if cmd[0] == "git" and after in cmd and not swapped:
            gitfile = (swarm / ".git").read_text(encoding="utf-8")
            swarm.rename(moved)
            swarm.mkdir()
            (swarm / ".git").write_text(gitfile, encoding="utf-8")
            (swarm / "replacement_wip.txt").write_text("not validated\n", encoding="utf-8")
            (swarm / ".swarm_lock").write_text("", encoding="utf-8")
            swapped.append(True)
        return result

    monkeypatch.setattr(subprocess, "run", run_then_replace)
    SwarmBroker(controller).release(swarm)
    monkeypatch.setattr(subprocess, "run", real_run)

    assert swapped
    assert (swarm / "replacement_wip.txt").exists()
    assert (swarm / ".swarm_lock").exists()
    assert (moved / ".swarm_lock").exists()
    assert (sandbox / "SENTINEL").exists()


def test_release_keeps_lock_when_swarm_is_swapped_after_clean(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    victim = _victim_repo(tmp_path)
    moved = tmp_path / "moved-swarm"
    real_run = subprocess.run

    def run_then_swap(cmd, *args, **kwargs):
        result = real_run(cmd, *args, **kwargs)
        if cmd[0] == "git" and "clean" in cmd and not swarm.is_symlink():
            _swap_for_link(swarm, victim, moved)
        return result

    monkeypatch.setattr(subprocess, "run", run_then_swap)
    SwarmBroker(controller).release(swarm)
    monkeypatch.setattr(subprocess, "run", real_run)

    assert swarm.is_symlink()
    assert _victim_repo_intact(victim)
    assert (moved / ".swarm_lock").exists()
    assert (sandbox / "SENTINEL").exists()


@pytest.mark.parametrize("entry", [".venv", ".swarm_lock"])
def test_release_removes_links_and_lock_only_in_the_opened_swarm(
    tmp_path: Path, monkeypatch, entry
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    (controller / ".venv").mkdir()
    SwarmBroker(controller)._mount_shared_cache(swarm)
    assert (swarm / ".venv").is_symlink()
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / ".venv").symlink_to(controller / ".venv", target_is_directory=True)
    (victim / ".swarm_lock").write_text("", encoding="utf-8")
    moved = tmp_path / "moved-swarm"
    real_unlink = os.unlink

    def swap_then_unlink(path, *args, **kwargs):
        if os.path.basename(os.fspath(path)) == entry and not swarm.is_symlink():
            _swap_for_link(swarm, victim, moved)
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", swap_then_unlink)
    SwarmBroker(controller).release(swarm)
    monkeypatch.setattr(os, "unlink", real_unlink)

    assert swarm.is_symlink()
    assert (victim / ".venv").is_symlink()
    assert (victim / ".swarm_lock").exists()
    assert (sandbox / "SENTINEL").exists()


# --- acquire: lock and cache links only in the directory that was validated -----------------


def _two_registered_swarms(tmp_path: Path) -> tuple[Path, Path, Path]:
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    first = controller / ".nexus-swarm-001"
    second = controller / ".nexus-swarm-002"
    _git(controller, "worktree", "add", "--detach", str(first), base)
    _git(controller, "worktree", "add", "--detach", str(second), base)
    return controller, first, second


def _replace_with_plain_dir(swarm: Path, moved: Path) -> None:
    swarm.rename(moved)
    swarm.mkdir()
    (swarm / "replacement_wip.txt").write_text("not validated\n", encoding="utf-8")


def test_acquire_skips_swarm_replaced_while_being_validated(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, first, _second = _two_registered_swarms(tmp_path)
    (tmp_path / "keep").mkdir()
    broker = SwarmBroker(controller)
    broker.swarm_dirs = [first]
    real_check = broker.is_independently_registered_worktree

    def check_then_replace(path):
        result = real_check(path)
        _replace_with_plain_dir(first, tmp_path / "moved-first")
        return result

    monkeypatch.setattr(broker, "is_independently_registered_worktree", check_then_replace)

    assert broker.acquire(timeout_sec=0.05) is None
    assert not (first / ".swarm_lock").exists()
    assert (sandbox / "SENTINEL").exists()


def test_acquire_skips_swarm_replaced_after_validation(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, first, second = _two_registered_swarms(tmp_path)
    broker = SwarmBroker(controller)
    real_check = broker.is_independently_registered_worktree

    def check_second_then_replace_first(path):
        result = real_check(path)
        if Path(path).name == second.name and not (tmp_path / "moved-first").exists():
            _replace_with_plain_dir(first, tmp_path / "moved-first")
        return result

    monkeypatch.setattr(
        broker, "is_independently_registered_worktree", check_second_then_replace_first
    )

    acquired = broker.acquire(timeout_sec=0.05)

    assert acquired is not None and acquired.name == second.name
    assert not (first / ".swarm_lock").exists()
    assert (second / ".swarm_lock").exists()
    assert (sandbox / "SENTINEL").exists()


@pytest.mark.parametrize("call", ["open", "symlink"])
def test_acquire_writes_lock_and_cache_links_only_in_the_validated_swarm(
    tmp_path: Path, monkeypatch, call
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, first, _second = _two_registered_swarms(tmp_path)
    (controller / ".venv").mkdir()
    victim = tmp_path / "victim"
    victim.mkdir()
    moved = tmp_path / "moved-first"
    broker = SwarmBroker(controller)
    broker.swarm_dirs = [first]
    real_call = getattr(os, call)

    def swap_then_call(*args, **kwargs):
        name = os.path.basename(os.fspath(args[1] if call == "symlink" else args[0]))
        if name in (".swarm_lock", ".venv") and not first.is_symlink():
            _swap_for_link(first, victim, moved)
        return real_call(*args, **kwargs)

    monkeypatch.setattr(os, call, swap_then_call)
    acquired = broker.acquire(timeout_sec=0.05)
    monkeypatch.setattr(os, call, real_call)

    assert first.is_symlink()
    assert acquired is None
    assert list(victim.iterdir()) == []
    assert (moved / ".swarm_lock").exists()
    assert (sandbox / "SENTINEL").exists()


# --- sync_scope: only into a swarm directory of this workspace, bound to the opened dirs ------


@pytest.mark.parametrize("where", ["outside", "plain_child", "nested_swarm_name"])
def test_sync_scope_writes_only_into_swarm_children_of_the_workspace(
    tmp_path: Path, monkeypatch, where
):
    sandbox, workspace, _swarm = _scope_layout(tmp_path, monkeypatch)
    target = {
        "outside": tmp_path / "elsewhere",
        "plain_child": workspace / "plain",
        "nested_swarm_name": workspace / "pkg" / ".nexus-swarm-009",
    }[where]
    target.mkdir()

    SwarmBroker(workspace).sync_scope(target, ["pkg/mod.py"], required_configs=[])

    assert list(target.iterdir()) == []
    assert (sandbox / "SENTINEL").exists()


def test_sync_scope_does_not_follow_swarm_swapped_for_link_after_check(tmp_path: Path, monkeypatch):
    sandbox, workspace, swarm = _scope_layout(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    broker = SwarmBroker(workspace)
    real_check = broker._is_swarm_child_dir
    swapped: list[bool] = []

    def check_then_swap(path):
        result = real_check(path)
        _swap_for_link(swarm, outside, tmp_path / "moved-swarm")
        swapped.append(True)
        return result

    monkeypatch.setattr(broker, "_is_swarm_child_dir", check_then_swap)
    broker.sync_scope(swarm, ["pkg/mod.py"], required_configs=[])

    assert swapped
    assert list(outside.iterdir()) == []
    assert (sandbox / "SENTINEL").exists()


def test_sync_scope_refuses_the_workspace_root_as_scope(tmp_path: Path, monkeypatch):
    sandbox, workspace, swarm = _scope_layout(tmp_path, monkeypatch)

    SwarmBroker(workspace).sync_scope(swarm, ["."], required_configs=[])

    assert list(swarm.iterdir()) == []
    assert (sandbox / "SENTINEL").exists()


@pytest.mark.parametrize("scope", ["pkg/mod.py", "pkg"])
def test_sync_scope_renames_into_the_opened_parent_when_it_is_swapped(
    tmp_path: Path, monkeypatch, scope
):
    sandbox, workspace, swarm = _scope_layout(tmp_path, monkeypatch)
    (swarm / "pkg").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    moved = tmp_path / "moved-pkg"
    real_replace = os.replace

    def swap_parent_then_replace(src, dst, *args, **kwargs):
        if not (swarm / "pkg").is_symlink():
            _swap_for_link(swarm / "pkg", outside, moved)
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", swap_parent_then_replace)
    SwarmBroker(workspace).sync_scope(swarm, [scope], required_configs=[])
    monkeypatch.setattr(os, "replace", real_replace)

    assert (swarm / "pkg").is_symlink()
    assert list(outside.iterdir()) == []
    assert (moved / "mod.py").read_text(encoding="utf-8") == "workspace mod\n"
    assert (sandbox / "SENTINEL").exists()


def test_sync_scope_skips_links_inside_copied_source_dirs(tmp_path: Path, monkeypatch):
    sandbox, workspace, swarm = _scope_layout(tmp_path, monkeypatch)
    secret_dir = tmp_path / "secret-dir"
    secret_dir.mkdir()
    (secret_dir / "key.txt").write_text("SECRET\n", encoding="utf-8")
    (workspace / "pkg" / "file_link.txt").symlink_to(secret_dir / "key.txt")
    (workspace / "pkg" / "dir_link").symlink_to(secret_dir, target_is_directory=True)
    (workspace / "pkg" / "inside_link.py").symlink_to(workspace / "pkg" / "mod.py")

    SwarmBroker(workspace).sync_scope(swarm, ["pkg"], required_configs=[])

    assert sorted(p.name for p in (swarm / "pkg").iterdir()) == ["mod.py", "sub"]
    assert (swarm / "pkg" / "sub" / "deep.py").read_text(encoding="utf-8") == "workspace deep\n"
    assert (sandbox / "SENTINEL").exists()


@pytest.mark.parametrize("scope", ["pkg/mod.py", "pkg"])
def test_sync_scope_removes_temporary_file_when_copy_fails(tmp_path: Path, monkeypatch, scope):
    sandbox, workspace, swarm = _scope_layout(tmp_path, monkeypatch)

    def failing_replace(*_args, **_kwargs):
        raise OSError("injected rename failure")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(OSError, match="injected rename failure"):
        SwarmBroker(workspace).sync_scope(swarm, [scope], required_configs=[])
    monkeypatch.undo()

    leftovers = [p for p in swarm.rglob("*") if p.is_file()]
    assert leftovers == []
    assert (sandbox / "SENTINEL").exists()


def _sync_in_thread(broker: SwarmBroker, swarm: Path, scope: list[str], fifo: Path, real_open):
    import threading

    errors: list[BaseException] = []

    def run():
        try:
            broker.sync_scope(swarm, scope, required_configs=[])
        except BaseException as exc:  # reported to the test thread
            errors.append(exc)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout=5)
    finished = not worker.is_alive()
    if not finished:
        # Release the reader blocked on the FIFO so the thread ends.
        os.close(real_open(fifo, os.O_WRONLY))
        worker.join(timeout=5)
    return finished, errors


def test_sync_scope_refuses_a_fifo_named_in_the_scope(tmp_path: Path, monkeypatch):
    sandbox, workspace, swarm = _scope_layout(tmp_path, monkeypatch)
    fifo = workspace / "pkg" / "pipe"
    os.mkfifo(fifo)

    finished, errors = _sync_in_thread(
        SwarmBroker(workspace), swarm, ["pkg/pipe", "pkg/mod.py"], fifo, os.open
    )

    assert finished
    assert errors == []
    assert not (swarm / "pkg" / "pipe").exists()
    assert (swarm / "pkg" / "mod.py").read_text(encoding="utf-8") == "workspace mod\n"
    assert (sandbox / "SENTINEL").exists()


def test_sync_scope_refuses_a_file_swapped_for_a_fifo_after_the_scan(tmp_path: Path, monkeypatch):
    sandbox, workspace, swarm = _scope_layout(tmp_path, monkeypatch)
    source = workspace / "pkg" / "mod.py"
    real_open = os.open
    swapped: list[bool] = []

    def swap_then_open(path, *args, **kwargs):
        if Path(os.fspath(path)) == source and not swapped:
            source.unlink()
            os.mkfifo(source)
            swapped.append(True)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap_then_open)
    finished, errors = _sync_in_thread(SwarmBroker(workspace), swarm, ["pkg"], source, real_open)
    monkeypatch.setattr(os, "open", real_open)

    assert swapped
    assert finished
    assert errors == []
    assert not (swarm / "pkg" / "mod.py").exists()
    assert (swarm / "pkg" / "sub" / "deep.py").read_text(encoding="utf-8") == "workspace deep\n"
    assert (sandbox / "SENTINEL").exists()


# --- #3153: double acquire, recovery after a failed release, fallback cleanup, special files --


def _locked_registered_swarm(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A registered swarm left locked by a failed release: a fresh `index.lock` in its own
    registration makes the checkout fail, so the lock is marked and the candidate's file kept."""
    controller, swarm = _registered_swarm(tmp_path)
    index_lock = Path(_git(swarm, "rev-parse", "--absolute-git-dir")) / "index.lock"
    index_lock.write_text("", encoding="utf-8")
    broker = SwarmBroker(controller)
    broker.release(swarm)
    assert (swarm / ".swarm_lock").exists()
    assert (swarm / "candidate.txt").exists()
    assert broker.locked_swarms() == [(swarm, "release_failed")]
    return controller, swarm, index_lock


def _age(path: Path, seconds: float = 3600) -> None:
    import time

    old = time.time() - seconds
    os.utime(path, (old, old))


def test_acquire_does_not_take_a_swarm_whose_lock_already_exists(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)

    first = SwarmBroker(controller).acquire(timeout_sec=0.05)
    second = SwarmBroker(controller).acquire(timeout_sec=0.05)

    assert first is not None and first.resolve() == swarm.resolve()
    assert second is None
    assert (swarm / ".swarm_lock").exists()
    assert (sandbox / "SENTINEL").exists()


def test_recovery_resets_then_unlocks_a_swarm_left_locked_by_a_failed_release(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm, index_lock = _locked_registered_swarm(tmp_path)
    _age(index_lock)
    broker = SwarmBroker(controller)

    assert broker.recover_failed_releases() == [swarm]

    assert not index_lock.exists()
    assert not (swarm / "candidate.txt").exists()
    assert not (swarm / ".swarm_lock").exists()
    assert broker.locked_swarms() == []
    assert (sandbox / "SENTINEL").exists()


def test_recovery_keeps_swarm_locked_while_its_registration_lock_is_recent(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm, index_lock = _locked_registered_swarm(tmp_path)
    broker = SwarmBroker(controller)

    assert broker.recover_failed_releases() == []

    assert index_lock.exists()
    assert (swarm / "candidate.txt").exists()
    assert broker.locked_swarms() == [(swarm, "release_failed")]
    assert (sandbox / "SENTINEL").exists()


def test_recovery_keeps_swarm_locked_when_its_reset_still_fails(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm, index_lock = _locked_registered_swarm(tmp_path)
    _age(index_lock)
    real_run = subprocess.run

    def failing_clean(cmd, *args, **kwargs):
        if cmd[0] == "git" and "clean" in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", "error: clean refused\n")
        return real_run(cmd, *args, **kwargs)

    broker = SwarmBroker(controller)
    monkeypatch.setattr(subprocess, "run", failing_clean)
    recovered = broker.recover_failed_releases()
    monkeypatch.setattr(subprocess, "run", real_run)

    assert recovered == []
    assert (swarm / "candidate.txt").exists()
    assert broker.locked_swarms() == [(swarm, "release_failed")]
    assert (sandbox / "SENTINEL").exists()


def test_recovery_never_touches_a_swarm_that_is_still_held(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)  # locked by a holder, no failed release
    index_lock = Path(_git(swarm, "rev-parse", "--absolute-git-dir")) / "index.lock"
    index_lock.write_text("", encoding="utf-8")
    _age(index_lock)
    broker = SwarmBroker(controller)

    assert broker.recover_failed_releases() == []

    assert index_lock.exists()
    assert (swarm / "candidate.txt").exists()
    assert broker.locked_swarms() == [(swarm, "held")]
    assert (sandbox / "SENTINEL").exists()


def test_recovery_skips_a_swarm_whose_release_is_running(tmp_path: Path, monkeypatch):
    import fcntl

    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm, index_lock = _locked_registered_swarm(tmp_path)
    _age(index_lock)
    broker = SwarmBroker(controller)
    other = os.open(swarm / ".swarm_lock", os.O_RDWR)
    try:
        fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)  # another release holds it
        recovered = broker.recover_failed_releases()
    finally:
        os.close(other)

    assert recovered == []
    assert index_lock.exists()
    assert (swarm / "candidate.txt").exists()
    assert broker.locked_swarms() == [(swarm, "release_failed")]
    assert (sandbox / "SENTINEL").exists()


def test_acquire_takes_back_a_swarm_once_its_failed_release_is_recovered(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm, index_lock = _locked_registered_swarm(tmp_path)
    _age(index_lock)

    acquired = SwarmBroker(controller).acquire(timeout_sec=0.05)

    assert acquired is not None and acquired.resolve() == swarm.resolve()
    assert not (swarm / "candidate.txt").exists()
    assert SwarmBroker(controller).locked_swarms() == [(swarm, "held")]
    assert (sandbox / "SENTINEL").exists()


def test_release_fallback_removes_entries_only_in_the_opened_swarm(tmp_path: Path, monkeypatch):
    import nexus.research.swarm_broker as swarm_broker

    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    (swarm / "a.txt").write_text("swarm\n", encoding="utf-8")
    (swarm / ".swarm_lock").write_text("", encoding="utf-8")
    victim = tmp_path / "victim"
    victim.mkdir()
    for name in ("tracked.txt", "a.txt"):  # the same names as the swarm's entries
        (victim / name).write_text("victim\n", encoding="utf-8")
    moved = tmp_path / "moved-swarm"
    broker = SwarmBroker(controller)
    real_check = broker.is_independently_registered_worktree
    real_names_dir = swarm_broker._names_dir

    def check_then_drop_gitfile(path):
        result = real_check(path)
        (swarm / ".git").unlink()  # forces the non-git fallback cleanup
        return result

    def check_then_swap(path, fd):
        result = real_names_dir(path, fd)
        if not swarm.is_symlink():
            _swap_for_link(swarm, victim, moved)
        return result

    monkeypatch.setattr(broker, "is_independently_registered_worktree", check_then_drop_gitfile)
    monkeypatch.setattr(swarm_broker, "_names_dir", check_then_swap)
    broker.release(swarm)
    monkeypatch.setattr(swarm_broker, "_names_dir", real_names_dir)

    assert all(
        (victim / name).read_text(encoding="utf-8") == "victim\n"
        for name in ("tracked.txt", "a.txt")
    )
    assert len([p for p in moved.iterdir() if p.name != ".swarm_lock"]) == 1  # one removed there
    assert (moved / ".swarm_lock").exists()
    assert (sandbox / "SENTINEL").exists()


def test_sync_scope_skips_a_file_swapped_for_a_directory_after_the_scan(
    tmp_path: Path, monkeypatch
):
    sandbox, workspace, swarm = _scope_layout(tmp_path, monkeypatch)
    source = workspace / "pkg" / "mod.py"
    real_open = os.open
    opened: list[int] = []

    def swap_then_open(path, *args, **kwargs):
        if Path(os.fspath(path)) == source and not opened:
            source.unlink()
            source.mkdir()
            opened.append(real_open(path, *args, **kwargs))
            return opened[-1]
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap_then_open)
    try:
        SwarmBroker(workspace).sync_scope(swarm, ["pkg"], required_configs=[])
    finally:
        monkeypatch.setattr(os, "open", real_open)

    assert opened
    try:
        still_open = os.fstat(opened[0])
    except OSError:
        still_open = None
    source_dir = os.stat(source)
    assert still_open is None or (still_open.st_dev, still_open.st_ino) != (
        source_dir.st_dev,
        source_dir.st_ino,
    )
    assert not (swarm / "pkg" / "mod.py").exists()
    assert (swarm / "pkg" / "sub" / "deep.py").read_text(encoding="utf-8") == "workspace deep\n"
    assert (sandbox / "SENTINEL").exists()


def test_sync_scope_skips_a_socket_named_in_the_scope(tmp_path: Path, monkeypatch):
    import socket

    sandbox, workspace, swarm = _scope_layout(tmp_path, monkeypatch)
    # Bound by a relative name: tmp_path can be longer than a socket path may be.
    monkeypatch.chdir(workspace / "pkg")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind("sock")
        monkeypatch.chdir(sandbox)
        SwarmBroker(workspace).sync_scope(swarm, ["pkg/sock", "pkg/mod.py"], required_configs=[])
    finally:
        server.close()

    assert not (swarm / "pkg" / "sock").exists()
    assert (swarm / "pkg" / "mod.py").read_text(encoding="utf-8") == "workspace mod\n"
    assert (sandbox / "SENTINEL").exists()


def test_sync_scope_refuses_special_files_without_opening_them(tmp_path: Path, monkeypatch):
    sandbox, workspace, swarm = _scope_layout(tmp_path, monkeypatch)
    fifo = workspace / "pkg" / "pipe"
    os.mkfifo(fifo)
    real_open = os.open
    opened: list[Path] = []

    def recording_open(path, *args, **kwargs):
        opened.append(Path(os.fspath(path)))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", recording_open)
    finished, errors = _sync_in_thread(
        SwarmBroker(workspace), swarm, ["pkg/pipe", "pkg/mod.py"], fifo, real_open
    )
    monkeypatch.setattr(os, "open", real_open)

    assert finished
    assert errors == []
    assert fifo not in opened
    assert (swarm / "pkg" / "mod.py").read_text(encoding="utf-8") == "workspace mod\n"
    assert (sandbox / "SENTINEL").exists()


def test_sync_scope_removes_the_earlier_copy_of_a_refused_source(tmp_path: Path, monkeypatch):
    sandbox, workspace, swarm = _scope_layout(tmp_path, monkeypatch)
    source = workspace / "pkg" / "mod.py"
    broker = SwarmBroker(workspace)
    broker.sync_scope(swarm, ["pkg/mod.py"], required_configs=[])
    assert (swarm / "pkg" / "mod.py").exists()
    source.unlink()
    os.mkfifo(source)

    finished, errors = _sync_in_thread(broker, swarm, ["pkg/mod.py"], source, os.open)

    assert finished
    assert errors == []
    assert not (swarm / "pkg" / "mod.py").exists()
    assert (sandbox / "SENTINEL").exists()


def test_sync_scope_skips_a_file_swapped_for_a_socket_after_the_scan(tmp_path: Path, monkeypatch):
    import socket

    sandbox, workspace, swarm = _scope_layout(tmp_path, monkeypatch)
    source = workspace / "pkg" / "mod.py"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    real_open = os.open
    swapped: list[bool] = []

    def swap_then_open(path, *args, **kwargs):
        if Path(os.fspath(path)) == source and not swapped:
            source.unlink()
            os.chdir(source.parent)  # bound by a relative name: tmp_path can be too long
            try:
                server.bind(source.name)
            finally:
                os.chdir(sandbox)
            swapped.append(True)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap_then_open)
    try:
        SwarmBroker(workspace).sync_scope(swarm, ["pkg"], required_configs=[])
    finally:
        monkeypatch.setattr(os, "open", real_open)
        server.close()

    assert swapped
    assert not (swarm / "pkg" / "mod.py").exists()
    assert (swarm / "pkg" / "sub" / "deep.py").read_text(encoding="utf-8") == "workspace deep\n"
    assert (sandbox / "SENTINEL").exists()


def test_recovery_leaves_a_lock_taken_by_a_new_holder_alone(tmp_path: Path, monkeypatch):
    import nexus.research.swarm_broker as swarm_broker

    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm, index_lock = _locked_registered_swarm(tmp_path)
    _age(index_lock)
    real_flock = swarm_broker.fcntl.flock
    taken: list[bool] = []

    def new_holder_then_flock(fd, operation):
        if not taken:
            # Between recovery opening the marked lock and locking it, the marked lock goes
            # and a new holder takes the swarm with a fresh exclusive-create lock.
            (swarm / ".swarm_lock").unlink()
            os.close(os.open(swarm / ".swarm_lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644))
            (swarm / "holder.txt").write_text("new holder\n", encoding="utf-8")
            taken.append(True)
        return real_flock(fd, operation)

    monkeypatch.setattr(swarm_broker.fcntl, "flock", new_holder_then_flock)
    recovered = SwarmBroker(controller).recover_failed_releases()
    monkeypatch.setattr(swarm_broker.fcntl, "flock", real_flock)

    assert taken
    assert recovered == []
    assert (swarm / ".swarm_lock").read_text(encoding="utf-8") == ""
    assert (swarm / "holder.txt").read_text(encoding="utf-8") == "new holder\n"
    assert (swarm / "candidate.txt").exists()
    assert index_lock.exists()
    assert SwarmBroker(controller).locked_swarms() == [(swarm, "held")]
    assert (sandbox / "SENTINEL").exists()


def test_release_does_not_mark_a_swarm_whose_path_was_swapped(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    victim = _victim_repo(tmp_path)
    moved = tmp_path / "moved-swarm"
    real_run = subprocess.run

    def run_then_swap(cmd, *args, **kwargs):
        result = real_run(cmd, *args, **kwargs)
        if cmd[0] == "git" and "clean" in cmd and not swarm.is_symlink():
            _swap_for_link(swarm, victim, moved)
        return result

    monkeypatch.setattr(subprocess, "run", run_then_swap)
    SwarmBroker(controller).release(swarm)
    monkeypatch.setattr(subprocess, "run", real_run)

    assert _victim_repo_intact(victim)
    assert (moved / ".swarm_lock").read_text(encoding="utf-8") == ""  # left for a person
    assert (sandbox / "SENTINEL").exists()


def test_release_waits_for_a_recovery_holding_the_lock(tmp_path: Path, monkeypatch):
    import fcntl
    import threading

    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    broker = SwarmBroker(controller)
    other = os.open(swarm / ".swarm_lock", os.O_RDWR)
    worker = threading.Thread(target=broker.release, args=(swarm,), daemon=True)
    try:
        fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        worker.start()
        worker.join(timeout=0.5)
        waited = worker.is_alive()
    finally:
        os.close(other)  # lets the release go on
    worker.join(timeout=5)

    assert waited
    assert not worker.is_alive()
    assert not (swarm / ".swarm_lock").exists()
    assert not (swarm / "candidate.txt").exists()
    assert (sandbox / "SENTINEL").exists()


def test_release_stays_quiet_and_locked_when_the_mark_cannot_be_written(
    tmp_path: Path, monkeypatch
):
    import errno

    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    real_run = subprocess.run

    def failing_checkout(cmd, *args, **kwargs):
        if cmd[0] == "git" and "checkout" in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", "error: checkout refused\n")
        return real_run(cmd, *args, **kwargs)

    def failing_pwrite(*_args, **_kwargs):
        raise OSError(errno.ENOSPC, "no space left")

    real_pwrite = os.pwrite
    monkeypatch.setattr(subprocess, "run", failing_checkout)
    monkeypatch.setattr(os, "pwrite", failing_pwrite)
    SwarmBroker(controller).release(swarm)
    monkeypatch.setattr(os, "pwrite", real_pwrite)
    monkeypatch.setattr(subprocess, "run", real_run)

    assert (swarm / ".swarm_lock").exists()
    assert (swarm / "candidate.txt").exists()
    assert (sandbox / "SENTINEL").exists()


def test_sync_scope_keeps_a_directory_where_a_refused_source_was_copied(
    tmp_path: Path, monkeypatch
):
    sandbox, workspace, swarm = _scope_layout(tmp_path, monkeypatch)
    fifo = workspace / "pkg" / "pipe"
    os.mkfifo(fifo)
    (swarm / "pkg" / "pipe").mkdir(parents=True)
    (swarm / "pkg" / "pipe" / "kept.txt").write_text("swarm\n", encoding="utf-8")

    finished, errors = _sync_in_thread(
        SwarmBroker(workspace), swarm, ["pkg/pipe", "pkg/mod.py"], fifo, os.open
    )

    assert finished
    assert errors == []
    assert (swarm / "pkg" / "pipe" / "kept.txt").read_text(encoding="utf-8") == "swarm\n"
    assert (swarm / "pkg" / "mod.py").read_text(encoding="utf-8") == "workspace mod\n"
    assert (sandbox / "SENTINEL").exists()


def test_sync_scope_removes_the_earlier_copy_of_a_source_that_became_a_link(
    tmp_path: Path, monkeypatch
):
    sandbox, workspace, swarm = _scope_layout(tmp_path, monkeypatch)
    source = workspace / "pkg" / "mod.py"
    broker = SwarmBroker(workspace)
    broker.sync_scope(swarm, ["pkg"], required_configs=[])
    assert (swarm / "pkg" / "mod.py").exists()
    source.unlink()
    source.symlink_to(workspace / "pkg" / "sub" / "deep.py")

    broker.sync_scope(swarm, ["pkg"], required_configs=[])

    assert not (swarm / "pkg" / "mod.py").exists()
    assert (swarm / "pkg" / "sub" / "deep.py").read_text(encoding="utf-8") == "workspace deep\n"
    assert (sandbox / "SENTINEL").exists()


# --- release puts the swarm back at its lease base; acquire checks the swarm again once locked ---


def _leased_swarm(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    """A registered swarm (with `*.log` ignored) leased by `acquire`; also returns the base."""
    controller = tmp_path / "controller"
    _init_repo(controller)
    (controller / ".gitignore").write_text("*.log\n", encoding="utf-8")
    _git(controller, "add", ".gitignore")
    _git(controller, "commit", "-m", "ignore logs")
    base = _git(controller, "rev-parse", "HEAD")
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    acquired = SwarmBroker(controller).acquire(timeout_sec=0.05)
    assert acquired is not None and acquired.resolve() == swarm.resolve()
    return controller, swarm, acquired, base


def _next_lease_sees_a_clean_tree_at(controller: Path, swarm: Path, base: str) -> None:
    acquired = SwarmBroker(controller).acquire(timeout_sec=0.05)
    assert acquired is not None and acquired.resolve() == swarm.resolve()
    assert _git(swarm, "rev-parse", "HEAD") == base
    status = _git(swarm, "status", "--porcelain", "--ignored", "--untracked-files=all")
    assert status.splitlines() == ["?? .swarm_lock"]


def test_release_drops_changes_the_lease_staged(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm, acquired, base = _leased_swarm(tmp_path)
    (swarm / "tracked.txt").write_text("staged edit\n", encoding="utf-8")
    (swarm / "tests").mkdir()
    (swarm / "tests" / "conftest.py").write_text("# staged\n", encoding="utf-8")
    _git(swarm, "add", "tracked.txt", "tests/conftest.py")

    SwarmBroker(controller).release(acquired)

    assert not (swarm / ".swarm_lock").exists()
    assert not (swarm / "tests").exists()
    assert (swarm / "tracked.txt").read_text(encoding="utf-8") == "controller\n"
    _next_lease_sees_a_clean_tree_at(controller, swarm, base)
    assert (sandbox / "SENTINEL").exists()


def test_release_returns_to_the_lease_base_after_a_commit_without_moving_the_branch(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm, acquired, base = _leased_swarm(tmp_path)
    _git(swarm, "checkout", "-q", "-b", "lease-work")
    (swarm / "committed.py").write_text("C = 1\n", encoding="utf-8")
    _git(swarm, "add", "committed.py")
    _git(swarm, "commit", "-q", "-m", "lease commit")
    lease_commit = _git(swarm, "rev-parse", "HEAD")

    SwarmBroker(controller).release(acquired)

    assert not (swarm / ".swarm_lock").exists()
    assert not (swarm / "committed.py").exists()
    assert _git(controller, "rev-parse", "lease-work") == lease_commit
    _next_lease_sees_a_clean_tree_at(controller, swarm, base)
    assert (sandbox / "SENTINEL").exists()


def test_release_removes_ignored_files_the_lease_wrote(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm, acquired, base = _leased_swarm(tmp_path)
    (swarm / "run.log").write_text("ignored output\n", encoding="utf-8")
    (swarm / "logs").mkdir()
    (swarm / "logs" / "deep.log").write_text("ignored output\n", encoding="utf-8")

    SwarmBroker(controller).release(acquired)

    assert not (swarm / ".swarm_lock").exists()
    assert not (swarm / "run.log").exists()
    assert not (swarm / "logs").exists()
    _next_lease_sees_a_clean_tree_at(controller, swarm, base)
    assert (sandbox / "SENTINEL").exists()


def test_waiting_acquire_leaves_locked_a_swarm_released_without_its_registration(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    holder = SwarmBroker(controller)
    held = holder.acquire(timeout_sec=0.05)
    assert held is not None
    waiter = SwarmBroker(controller)
    real_try = waiter._try_lock
    left = []

    def try_then_holder_leaves(swarm_dir, identity):
        outcome = real_try(swarm_dir, identity)
        if outcome is False and not left:
            # The waiter has validated the swarm; its holder now turns it into a repository of
            # its own and releases, which unlocks without resetting.
            (swarm / ".git").unlink()
            _git(swarm, "init", "-q")
            _git(swarm, "config", "user.email", "nexus@example.test")
            _git(swarm, "config", "user.name", "Nexus Test")
            (swarm / "planted.txt").write_text("left behind\n", encoding="utf-8")
            _git(swarm, "add", "planted.txt")
            _git(swarm, "commit", "-q", "-m", "planted")
            holder.release(held)
            left.append(True)
        return outcome

    monkeypatch.setattr(waiter, "_try_lock", try_then_holder_leaves)

    assert waiter.acquire(timeout_sec=5) is None
    assert left
    assert (swarm / ".swarm_lock").read_bytes() == b"release_failed\n"
    assert (sandbox / "SENTINEL").exists()


def test_acquire_leaves_locked_a_swarm_replaced_while_it_is_checked_again(
    tmp_path: Path, monkeypatch
):
    import nexus.research.swarm_broker as swarm_broker

    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    moved = tmp_path / "moved"
    real_lookup = swarm_broker.linked_worktree_git_dir
    calls = []

    def lookup_then_replace(path, *args, **kwargs):
        result = real_lookup(path, *args, **kwargs)
        calls.append(path)
        if len(calls) == 1:
            # Another directory carrying a copy of the swarm's .git file takes its path.
            swarm.rename(moved)
            swarm.mkdir()
            (swarm / ".git").write_bytes((moved / ".git").read_bytes())
            (swarm / ".swarm_lock").write_text("", encoding="utf-8")
        return result

    monkeypatch.setattr(swarm_broker, "linked_worktree_git_dir", lookup_then_replace)

    assert SwarmBroker(controller).acquire(timeout_sec=0.05) is None
    assert calls
    assert (moved / ".swarm_lock").exists()
    assert (swarm / ".swarm_lock").read_bytes() == b""
    assert (sandbox / "SENTINEL").exists()


def test_acquire_leaves_swarm_locked_when_its_lease_base_cannot_be_recorded(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    real_run = subprocess.run

    def failing_update_ref(cmd, *args, **kwargs):
        if cmd[0] == "git" and "update-ref" in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", "error: update-ref refused\n")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", failing_update_ref)
    acquired = SwarmBroker(controller).acquire(timeout_sec=0.05)
    monkeypatch.setattr(subprocess, "run", real_run)

    assert acquired is None
    assert SwarmBroker(controller).locked_swarms() == [(swarm, "release_failed")]
    assert (sandbox / "SENTINEL").exists()


def test_acquire_never_runs_a_hook_named_in_repository_config(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    marker = tmp_path / "hook-ran"
    _git(controller, "config", "hook.probe.command", f"touch '{marker}'")
    _git(controller, "config", "hook.probe.event", "reference-transaction")

    assert SwarmBroker(controller).acquire(timeout_sec=0.05) is None

    assert not marker.exists()
    assert SwarmBroker(controller).locked_swarms() == [(swarm, "release_failed")]
    assert (sandbox / "SENTINEL").exists()


# --- recovery backs off from a swarm whose recovery keeps failing --------------------------------


def _git_calls_during(monkeypatch, action) -> tuple[object, list[list[str]]]:
    calls: list[list[str]] = []
    real_run = subprocess.run

    def recording_run(cmd, *args, **kwargs):
        if cmd[0] == "git":
            calls.append(list(cmd))
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording_run)
    try:
        result = action()
    finally:
        monkeypatch.setattr(subprocess, "run", real_run)
    return result, calls


def test_recovery_is_not_retried_soon_after_it_failed(tmp_path: Path, monkeypatch):
    import nexus.research.swarm_broker as swarm_broker

    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm, index_lock = _locked_registered_swarm(tmp_path)
    monkeypatch.setattr(swarm_broker, "_RECOVERY_BACKOFF_SEC", 3600, raising=False)
    assert SwarmBroker(controller).recover_failed_releases() == []  # index.lock still recent
    _age(index_lock)

    recovered, calls = _git_calls_during(
        monkeypatch, lambda: SwarmBroker(controller).recover_failed_releases()
    )

    assert recovered == []
    assert not [cmd for cmd in calls if "checkout" in cmd or "clean" in cmd]
    assert index_lock.exists()
    assert (swarm / "candidate.txt").exists()
    assert SwarmBroker(controller).locked_swarms() == [(swarm, "release_failed")]
    monkeypatch.setattr(swarm_broker, "_RECOVERY_BACKOFF_SEC", 0, raising=False)
    assert SwarmBroker(controller).recover_failed_releases() == [swarm]
    assert not (swarm / "candidate.txt").exists()
    assert (sandbox / "SENTINEL").exists()


def test_recovery_backoff_ends_once_a_recovery_succeeds(tmp_path: Path, monkeypatch):
    import nexus.research.swarm_broker as swarm_broker

    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm, index_lock = _locked_registered_swarm(tmp_path)
    monkeypatch.setattr(swarm_broker, "_RECOVERY_BACKOFF_SEC", 3600, raising=False)
    assert SwarmBroker(controller).recover_failed_releases() == []
    _age(index_lock)
    monkeypatch.setattr(swarm_broker, "_RECOVERY_BACKOFF_SEC", 0, raising=False)
    assert SwarmBroker(controller).recover_failed_releases() == [swarm]
    monkeypatch.setattr(swarm_broker, "_RECOVERY_BACKOFF_SEC", 3600, raising=False)
    # A later lease's release fails the same way; its first recovery runs right away.
    acquired = SwarmBroker(controller).acquire(timeout_sec=0.05)
    assert acquired is not None
    (swarm / "candidate.txt").write_text("second lease\n", encoding="utf-8")
    index_lock.write_text("", encoding="utf-8")
    SwarmBroker(controller).release(acquired)
    assert SwarmBroker(controller).locked_swarms() == [(swarm, "release_failed")]
    _age(index_lock)

    assert SwarmBroker(controller).recover_failed_releases() == [swarm]

    assert not (swarm / "candidate.txt").exists()
    assert (sandbox / "SENTINEL").exists()


def test_mark_stale_lease_only_marks_swarm_directories(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    _init_repo(controller)
    other = controller / "not-a-swarm"
    other.mkdir()
    (other / ".swarm_lock").write_text("", encoding="utf-8")
    _age(other / ".swarm_lock")

    assert SwarmBroker(controller).mark_stale_lease(other, 60) is False

    assert (other / ".swarm_lock").read_text(encoding="utf-8") == ""
    assert (sandbox / "SENTINEL").exists()


# #3230: a release whose registration check cannot be made keeps the lock, and recovery clears
# every registration lock file the reset can trip on, not only index.lock.


def test_release_keeps_the_lock_when_the_registration_check_cannot_be_made(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    broker = SwarmBroker(controller)
    real_output = SwarmBroker._git_output

    def worktree_list_fails(self, args, cwd):
        if args[:2] == ["worktree", "list"]:
            return None  # a transient git failure during the release's check
        return real_output(self, args, cwd)

    monkeypatch.setattr(SwarmBroker, "_git_output", worktree_list_fails)
    broker.release(swarm)
    assert (swarm / ".swarm_lock").exists()
    assert (swarm / "candidate.txt").exists()
    assert broker.locked_swarms() == [(swarm, "release_failed")]
    assert SwarmBroker(controller).acquire(timeout_sec=0.05) is None

    monkeypatch.setattr(SwarmBroker, "_git_output", real_output)
    from nexus.research import swarm_broker as swarm_broker_module

    swarm_broker_module._RECOVERY_FAILED_AT.clear()  # the failed attempt above set a backoff
    assert broker.recover_failed_releases() == [swarm]
    assert not (swarm / "candidate.txt").exists()
    assert broker.locked_swarms() == []
    assert (sandbox / "SENTINEL").exists()


def test_release_still_unlocks_a_placeholder_without_git_metadata(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    _init_repo(controller)
    placeholder = controller / ".nexus-swarm-001"
    placeholder.mkdir()
    (placeholder / ".swarm_lock").write_text("", encoding="utf-8")
    (placeholder / "leftover.txt").write_text("kept", encoding="utf-8")
    broker = SwarmBroker(controller)
    broker.release(placeholder)
    assert not (placeholder / ".swarm_lock").exists()
    assert (placeholder / "leftover.txt").exists()
    assert (sandbox / "SENTINEL").exists()


def test_recovery_clears_a_stale_head_lock_left_by_a_killed_reset(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    head_lock = Path(_git(swarm, "rev-parse", "--absolute-git-dir")) / "HEAD.lock"
    head_lock.write_text("", encoding="utf-8")
    broker = SwarmBroker(controller)
    broker.release(swarm)
    assert broker.locked_swarms() == [(swarm, "release_failed")]
    assert (swarm / "candidate.txt").exists()
    _age(head_lock)

    assert broker.recover_failed_releases() == [swarm]

    assert not head_lock.exists()
    assert not (swarm / "candidate.txt").exists()
    assert broker.locked_swarms() == []
    assert (sandbox / "SENTINEL").exists()


def test_recovery_clears_the_lease_base_and_reflog_locks_so_the_next_lease_can_start(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm, index_lock = _locked_registered_swarm(tmp_path)
    git_dir = Path(_git(swarm, "rev-parse", "--absolute-git-dir"))
    extra = [
        git_dir / "refs" / "worktree" / "nexus-swarm-base.lock",
        git_dir / "logs" / "HEAD.lock",
    ]
    for lock in (index_lock, *extra):
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("", encoding="utf-8")
        _age(lock)

    acquired = SwarmBroker(controller).acquire(timeout_sec=0.05)

    assert acquired is not None and acquired.resolve() == swarm.resolve()
    assert not any(lock.exists() for lock in (index_lock, *extra))
    assert not (swarm / "candidate.txt").exists()
    assert (sandbox / "SENTINEL").exists()


def test_recovery_leaves_a_young_or_linked_registration_lock_alone(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm, index_lock = _locked_registered_swarm(tmp_path)
    git_dir = index_lock.parent
    outside = tmp_path / "outside.lock"
    outside.write_text("", encoding="utf-8")
    _age(outside)
    (git_dir / "HEAD.lock").symlink_to(outside)
    # The link itself is old too: only the regular-file check leaves it alone.
    os.utime(git_dir / "HEAD.lock", (1, 1), follow_symlinks=False)
    _age(index_lock)
    broker = SwarmBroker(controller)

    recovered = broker.recover_failed_releases()

    assert recovered == []  # the linked HEAD.lock still blocks the reset
    assert outside.exists() and (git_dir / "HEAD.lock").is_symlink()
    assert not index_lock.exists()
    assert (sandbox / "SENTINEL").exists()


# #3231: the reset covers a tracked file hidden by an index flag, and a nested repository.


@pytest.mark.parametrize("flag", ["--skip-worktree", "--assume-unchanged"])
def test_release_resets_a_tracked_file_hidden_by_an_index_flag(tmp_path: Path, monkeypatch, flag):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    _git(swarm, "update-index", flag, "tracked.txt")
    (swarm / "tracked.txt").write_text("lease edit\n", encoding="utf-8")
    broker = SwarmBroker(controller)

    broker.release(swarm)

    assert not (swarm / ".swarm_lock").exists()
    assert (swarm / "tracked.txt").read_text(encoding="utf-8") == "controller\n"
    assert _git(swarm, "ls-files", "-v", "tracked.txt").startswith("H ")
    assert _git(swarm, "status", "--porcelain") == ""
    assert (sandbox / "SENTINEL").exists()


def test_release_removes_a_nested_repository_left_by_the_lease(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    nest = swarm / "nest"
    nest.mkdir()
    _git(nest, "init", "-q")
    (nest / "payload.txt").write_text("carried over\n", encoding="utf-8")
    broker = SwarmBroker(controller)

    broker.release(swarm)

    assert not (swarm / ".swarm_lock").exists()
    assert not nest.exists()
    assert not (swarm / "candidate.txt").exists()
    assert (sandbox / "SENTINEL").exists()


def test_release_resets_a_tracked_file_carrying_both_index_flags(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    _git(swarm, "update-index", "--skip-worktree", "tracked.txt")
    _git(swarm, "update-index", "--assume-unchanged", "tracked.txt")
    assert _git(swarm, "ls-files", "-v", "tracked.txt").startswith("s ")
    (swarm / "tracked.txt").write_text("lease edit\n", encoding="utf-8")

    SwarmBroker(controller).release(swarm)

    assert not (swarm / ".swarm_lock").exists()
    assert (swarm / "tracked.txt").read_text(encoding="utf-8") == "controller\n"
    assert _git(swarm, "ls-files", "-v", "tracked.txt").startswith("H ")
    assert (sandbox / "SENTINEL").exists()


EMPTY_BLOB = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


def _index_add(swarm: Path, paths: list[bytes], flag: str) -> None:
    """Put `paths` (any bytes) in the index as empty blobs and set `flag` on them."""
    info = b"".join(b"100644 " + EMPTY_BLOB.encode() + b" 0\t" + p + b"\0" for p in paths)
    subprocess.run(["git", "update-index", "-z", "--index-info"], cwd=swarm, input=info, check=True)
    subprocess.run(
        ["git", "update-index", flag, "-z", "--stdin"],
        cwd=swarm,
        input=b"".join(p + b"\0" for p in paths),
        check=True,
    )


def test_release_clears_a_flag_on_a_path_that_is_not_utf8(tmp_path: Path, monkeypatch):
    """A lease can put any bytes in the index; decoding them must not leave the swarm locked."""
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    odd = b"odd-\xff\xfe.txt"
    _index_add(swarm, [odd], "--skip-worktree")
    listed = subprocess.run(
        ["git", "ls-files", "-v", "-z"], cwd=swarm, capture_output=True, check=True
    ).stdout
    assert b"S " + odd in listed

    SwarmBroker(controller).release(swarm)

    assert not (swarm / ".swarm_lock").exists()
    listed = subprocess.run(
        ["git", "ls-files", "-v", "-z"], cwd=swarm, capture_output=True, check=True
    ).stdout
    assert b"S " not in listed and b"s " not in listed
    assert (sandbox / "SENTINEL").exists()


def test_release_clears_flags_on_an_index_longer_than_one_argument_list(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    many = [f"deep/{i:05d}/".encode() + b"x" * 180 + b".txt" for i in range(1500)]
    assert sum(len(p) + 1 for p in many) > 2 * 64 * 1024  # several batches
    _index_add(swarm, many, "--assume-unchanged")

    SwarmBroker(controller).release(swarm)

    assert not (swarm / ".swarm_lock").exists()
    listed = subprocess.run(
        ["git", "ls-files", "-v", "-z"], cwd=swarm, capture_output=True, check=True
    ).stdout
    assert not [e for e in listed.split(b"\0") if e[:1].islower()]
    assert (sandbox / "SENTINEL").exists()


def test_argv_batches_stay_under_the_budget_and_keep_order():
    from nexus.research.swarm_broker import _argv_batches

    paths = [f"p{i}" for i in range(10)]
    assert _argv_batches(paths, budget=10) == [
        ["p0", "p1", "p2"],
        ["p3", "p4", "p5"],
        ["p6", "p7", "p8"],
        ["p9"],
    ]
    assert _argv_batches([], budget=10) == []
    assert _argv_batches(["x" * 50], budget=10) == [["x" * 50]]  # one oversized path still goes


# #3232: the lock names its holder, and an aged lock is not marked stale while that holder
# still runs.


def _acquired_lease(tmp_path: Path) -> tuple[Path, Path, SwarmBroker]:
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    broker = SwarmBroker(controller)
    acquired = broker.acquire(timeout_sec=0.05)
    assert acquired is not None
    (swarm / "work_in_progress.txt").write_text("live holder output\n", encoding="utf-8")
    return controller, swarm, broker


def test_acquire_records_the_holder_in_the_lock(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    _controller, swarm, broker = _acquired_lease(tmp_path)
    text = (swarm / ".swarm_lock").read_text(encoding="utf-8")
    assert text.startswith(f"held pid={os.getpid()}")
    # The second identity: the process start time, read back the same way later.
    from nexus.research.swarm_broker import _process_start_identity

    assert text == f"held pid={os.getpid()} id={_process_start_identity(os.getpid())}\n"
    assert broker.locked_swarms() == [(swarm, "held")]
    assert (sandbox / "SENTINEL").exists()


def test_an_aged_lock_is_not_marked_stale_while_its_holder_runs(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    _controller, swarm, broker = _acquired_lease(tmp_path)
    _age(swarm / ".swarm_lock", 3 * 3600)
    probed: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: probed.append((pid, sig)))

    assert broker.mark_stale_lease(swarm, 2 * 3600) is False

    assert probed == [(os.getpid(), 0)]
    assert broker.locked_swarms() == [(swarm, "held")]
    assert broker.recover_failed_releases() == []
    assert (swarm / "work_in_progress.txt").exists()
    assert (sandbox / "SENTINEL").exists()


def test_an_aged_lock_of_a_gone_holder_is_marked_and_recovered(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    _controller, swarm, broker = _acquired_lease(tmp_path)
    _age(swarm / ".swarm_lock", 3 * 3600)

    def gone(pid, sig):
        raise ProcessLookupError(pid)

    monkeypatch.setattr(os, "kill", gone)

    assert broker.mark_stale_lease(swarm, 2 * 3600) is True

    assert broker.locked_swarms() == [(swarm, "release_failed")]
    assert broker.recover_failed_releases() == [swarm]
    assert not (swarm / "work_in_progress.txt").exists()
    assert broker.locked_swarms() == []
    assert (sandbox / "SENTINEL").exists()


def test_a_lock_without_a_holder_is_still_marked_by_age_alone(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)  # an older, empty lock
    _age(swarm / ".swarm_lock", 3 * 3600)
    monkeypatch.setattr(os, "kill", lambda pid, sig: pytest.fail("no holder to probe"))

    assert SwarmBroker(controller).mark_stale_lease(swarm, 2 * 3600) is True
    assert (sandbox / "SENTINEL").exists()


@pytest.mark.parametrize(
    "mark",
    [
        b"held pid=99999999999999999999\n",
        b"held pid=0\n",
        b"held pid=1\n",
        b"held pid=-7\n",
        b"held pid=12abc\n",
    ],
    ids=["overlong", "zero", "one", "negative", "mixed"],
)
def test_mark_stale_lease_treats_a_lock_value_that_is_not_a_pid_as_no_holder(
    tmp_path: Path, monkeypatch, mark: bytes
):
    """The lock sits where the lease's commands run; a value that is not a pid this host
    could hand out must not raise out of the cleanup nor count as a live holder."""
    _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    (swarm / ".swarm_lock").write_bytes(mark)
    _age(swarm / ".swarm_lock")

    assert SwarmBroker(controller).mark_stale_lease(swarm, 60) is True


def test_mark_stale_lease_sweep_continues_past_a_lock_with_a_bad_holder_value(
    tmp_path: Path, monkeypatch
):
    _sentinel_cwd(tmp_path, monkeypatch)
    controller, first = _registered_swarm(tmp_path)
    second = first.parent / ".nexus-swarm-002"
    _git(controller, "worktree", "add", "-q", str(second), "HEAD")
    (first / ".swarm_lock").write_bytes(b"held pid=99999999999999999999\n")
    (second / ".swarm_lock").write_bytes(b"held pid=4194303\n")  # a pid nothing runs under
    _age(first / ".swarm_lock")
    _age(second / ".swarm_lock")
    broker = SwarmBroker(controller)

    marked = [broker.mark_stale_lease(path, 60) for path in (first, second)]

    assert marked == [True, True]


def test_process_exists_is_false_for_a_pid_the_os_cannot_take():
    from nexus.research.swarm_broker import _process_exists

    assert _process_exists(2**40) is False
    assert _process_exists(os.getpid()) is True


def test_start_identity_of_this_process_is_stable_and_a_missing_pid_has_none():
    from nexus.research.swarm_broker import _process_start_identity

    identity = _process_start_identity(os.getpid())
    assert identity and identity == _process_start_identity(os.getpid())
    assert _process_start_identity(2**22 + 12345) is None


def test_an_aged_lock_naming_a_live_pid_with_another_start_time_is_marked(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    _controller, swarm, broker = _acquired_lease(tmp_path)
    lock = swarm / ".swarm_lock"
    text = lock.read_text(encoding="utf-8")
    pid_part, _, _ = text.partition(" id=")
    from nexus.research.swarm_broker import _process_start_identity

    same_kind_other = (
        "ps:other"
        if (_process_start_identity(os.getpid()) or "").startswith("ps:")
        else "other-boot:1"
    )
    lock.write_text(f"{pid_part} id={same_kind_other}\n", encoding="utf-8")
    _age(lock, 3 * 3600)

    assert broker.mark_stale_lease(swarm, 2 * 3600) is True

    assert broker.locked_swarms() == [(swarm, "release_failed")]
    assert (sandbox / "SENTINEL").exists()


def test_an_aged_lock_recording_the_other_identity_kind_for_a_live_pid_is_kept(
    tmp_path: Path, monkeypatch
):
    # /proc (boot:ticks) and ps (ps:...) strings never compare; a differing kind is unknown (#3284).
    from nexus.research.swarm_broker import _process_start_identity

    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    _controller, swarm, broker = _acquired_lease(tmp_path)
    lock = swarm / ".swarm_lock"
    pid_part, _, _ = lock.read_text(encoding="utf-8").partition(" id=")
    now_is_ps = (_process_start_identity(os.getpid()) or "").startswith("ps:")
    other_kind = "boot-x:12345" if now_is_ps else "ps:Tue_Nov_3_06:37:00_2026"
    lock.write_text(f"{pid_part} id={other_kind}\n", encoding="utf-8")
    _age(lock, 3 * 3600)

    assert broker.mark_stale_lease(swarm, 2 * 3600) is False
    assert (sandbox / "SENTINEL").exists()


def test_an_aged_pid_only_lock_whose_holder_runs_is_kept(tmp_path: Path, monkeypatch):
    # A lock written before #3259 (or without a readable start time) names only a pid; while
    # that pid runs the lease is left alone, as before (#3277 review).
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    (swarm / ".swarm_lock").write_bytes(f"held pid={os.getpid()}\n".encode())
    _age(swarm / ".swarm_lock", 3 * 3600)

    assert SwarmBroker(controller).mark_stale_lease(swarm, 2 * 3600) is False
    assert (swarm / ".swarm_lock").read_bytes() == f"held pid={os.getpid()}\n".encode()
    assert (sandbox / "SENTINEL").exists()


def test_an_aged_lock_is_kept_when_the_start_time_cannot_be_read_now(tmp_path: Path, monkeypatch):
    # Not being able to read the start time now says nothing about the holder: keep the lock.
    _sentinel_cwd(tmp_path, monkeypatch)
    _controller, swarm, broker = _acquired_lease(tmp_path)
    _age(swarm / ".swarm_lock", 3 * 3600)
    monkeypatch.setattr("nexus.research.swarm_broker._process_start_identity", lambda pid: None)

    assert broker.mark_stale_lease(swarm, 2 * 3600) is False


def test_the_ps_start_time_is_read_in_utc(monkeypatch):
    # The ps fallback must not depend on the host's time zone (#3277 review).
    import nexus.research.swarm_broker as broker_module

    def no_proc(*_a, **_k):
        raise OSError("no /proc")

    seen = {}

    def fake_run(argv, **kwargs):
        seen.update(kwargs.get("env") or {})
        return subprocess.CompletedProcess(argv, 0, stdout="Tue Nov  3 06:37:00 2026\n")

    monkeypatch.setattr(broker_module, "open", no_proc, raising=False)
    monkeypatch.setattr(broker_module.subprocess, "run", fake_run)

    assert broker_module._process_start_identity(os.getpid()) == "ps:Tue_Nov_3_06:37:00_2026"
    assert seen.get("TZ") == "UTC"


def _commit_submodule(controller: Path, tmp_path: Path) -> str:
    sub = tmp_path / "subrepo"
    _init_repo(sub)
    _git(
        controller,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(sub),
        "vendor",
    )
    _git(controller, "commit", "-q", "-m", "add submodule")
    return _git(controller, "rev-parse", "HEAD")


def _swarm_with_submodule(tmp_path: Path) -> tuple[Path, Path]:
    controller = tmp_path / "controller"
    _init_repo(controller)
    base = _commit_submodule(controller, tmp_path)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    _git(swarm, "update-ref", "refs/worktree/nexus-swarm-base", "HEAD")
    (swarm / ".swarm_lock").write_text("", encoding="utf-8")
    return controller, swarm


def test_release_stays_locked_while_a_submodule_is_initialised(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _swarm_with_submodule(tmp_path)
    _git(swarm, "-c", "protocol.file.allow=always", "submodule", "update", "--init", "-q")
    (swarm / "vendor" / "lease_note.txt").write_text("lease output\n", encoding="utf-8")
    broker = SwarmBroker(controller)

    broker.release(swarm)

    # #3279: the submodule working tree is removed instead of leaving the swarm locked.
    assert not (swarm / ".swarm_lock").exists()
    assert (swarm / "vendor").is_dir() and not any((swarm / "vendor").iterdir())
    assert (sandbox / "SENTINEL").exists()


def test_release_stays_locked_when_files_were_written_in_an_uninitialised_submodule_path(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _swarm_with_submodule(tmp_path)
    (swarm / "vendor" / "lease_note.txt").write_text("lease output\n", encoding="utf-8")
    broker = SwarmBroker(controller)

    broker.release(swarm)

    # #3279: the submodule working tree is removed instead of leaving the swarm locked.
    assert not (swarm / ".swarm_lock").exists()
    assert (swarm / "vendor").is_dir() and not any((swarm / "vendor").iterdir())
    assert (sandbox / "SENTINEL").exists()


def test_release_unlocks_when_the_submodule_path_is_untouched(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _swarm_with_submodule(tmp_path)
    (swarm / "candidate.txt").write_text("scratch\n", encoding="utf-8")

    SwarmBroker(controller).release(swarm)

    assert not (swarm / ".swarm_lock").exists()
    assert not (swarm / "candidate.txt").exists()
    assert (sandbox / "SENTINEL").exists()


def test_release_restores_the_full_tree_after_a_lease_enabled_sparse_checkout(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _registered_swarm(tmp_path)
    _git(swarm, "sparse-checkout", "set", "--no-cone", "/nothing-here")
    assert not (swarm / "tracked.txt").exists()
    broker = SwarmBroker(controller)

    broker.release(swarm)

    assert not (swarm / ".swarm_lock").exists()
    assert (swarm / "tracked.txt").read_text(encoding="utf-8") == "controller\n"
    assert _git(swarm, "config", "--bool", "--get-all", "core.sparseCheckout") != "true"
    assert _git(swarm, "status", "--porcelain") == ""
    assert (sandbox / "SENTINEL").exists()


def test_release_leaves_nothing_of_a_lease_in_the_swarm_git_dir_modules(
    tmp_path: Path, monkeypatch
):
    # Candidate from #3284: deinit empties the submodule path but the swarm git dir's modules/
    # keeps the submodule repository, which the next lease's `submodule update --init` reuses.
    _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _swarm_with_submodule(tmp_path)
    _git(swarm, "-c", "protocol.file.allow=always", "submodule", "update", "--init", "-q")
    git_dir = Path(_git(swarm, "rev-parse", "--absolute-git-dir"))
    marker = git_dir / "modules" / "vendor" / "lease_marker"
    marker.write_text("lease output\n", encoding="utf-8")
    _git(swarm, "submodule", "deinit", "-f", "--all")
    broker = SwarmBroker(controller)

    broker.release(swarm)

    assert not (swarm / ".swarm_lock").exists()  # the release itself succeeded
    assert not marker.exists()


def test_release_does_not_remove_modules_of_a_git_dir_the_lease_pointed_the_swarm_at(
    tmp_path: Path, monkeypatch
):
    # The lease rewrites the swarm's `.git` file to another registration; release must refuse
    # and leave the swarm locked instead of deleting `modules/` there (#3284).
    _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    sibling = controller / ".nexus-swarm-002"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    _git(controller, "worktree", "add", "--detach", str(sibling), base)
    (swarm / ".swarm_lock").write_text("", encoding="utf-8")
    broker = SwarmBroker(controller)
    victim = Path(_git(sibling, "rev-parse", "--absolute-git-dir")) / "modules" / "keep"
    victim.parent.mkdir()
    victim.write_text("not the lease's\n", encoding="utf-8")
    (swarm / ".git").write_text(f"gitdir: {victim.parent.parent}\n", encoding="utf-8")

    broker.release(swarm)

    assert victim.exists()
    assert (swarm / ".swarm_lock").exists()


def test_release_recovers_an_initialised_submodule_and_the_swarm_can_be_leased_again(
    tmp_path: Path, monkeypatch
):
    _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _swarm_with_submodule(tmp_path)
    _git(swarm, "-c", "protocol.file.allow=always", "submodule", "update", "--init", "-q")
    git_dir = Path(_git(swarm, "rev-parse", "--absolute-git-dir"))
    assert (git_dir / "modules" / "vendor").exists()
    (swarm / "vendor" / "lease_note.txt").write_text("lease output\n", encoding="utf-8")
    broker = SwarmBroker(controller)

    broker.release(swarm)

    assert not (swarm / ".swarm_lock").exists()
    assert broker.locked_swarms() == []
    assert (swarm / "vendor").is_dir() and not any((swarm / "vendor").iterdir())
    assert not (git_dir / "modules" / "vendor").exists()
    assert _git(swarm, "status", "--porcelain") == ""


def test_release_does_not_follow_a_link_inside_the_submodule_working_tree(
    tmp_path: Path, monkeypatch
):
    _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _swarm_with_submodule(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep\n", encoding="utf-8")
    (swarm / "vendor" / "escape").symlink_to(outside)

    SwarmBroker(controller).release(swarm)

    assert not (swarm / ".swarm_lock").exists()
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "keep\n"
    assert not os.path.lexists(swarm / "vendor" / "escape")


def test_release_stays_locked_when_the_submodule_working_tree_cannot_be_removed(
    tmp_path: Path, monkeypatch
):
    import nexus.research.swarm_broker as broker_module

    _sentinel_cwd(tmp_path, monkeypatch)
    controller, swarm = _swarm_with_submodule(tmp_path)
    (swarm / "vendor" / "lease_note.txt").write_text("lease output\n", encoding="utf-8")

    def refuse(_path):
        raise broker_module.UntrustedTreeNotRemoved("tree_not_removed:vendor")

    monkeypatch.setattr(broker_module, "remove_untrusted_tree", refuse)
    broker = SwarmBroker(controller)

    broker.release(swarm)

    assert (swarm / ".swarm_lock").exists()
    assert broker.locked_swarms() == [(swarm, "release_failed")]


# --- fail-closed release base, hardened git, and lease-start failures (#3169) ---------------------


def _swarm_with_lease_base(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    acquired = SwarmBroker(controller).acquire(timeout_sec=0.05)
    assert acquired is not None
    return sandbox, controller, swarm, acquired


def test_release_keeps_swarm_locked_when_the_lease_base_is_missing(tmp_path: Path, monkeypatch):
    sandbox, controller, swarm, acquired = _swarm_with_lease_base(tmp_path, monkeypatch)
    (swarm / "lease_work.txt").write_text("work\n", encoding="utf-8")
    _git(swarm, "update-ref", "-d", "refs/worktree/nexus-swarm-base")

    SwarmBroker(controller).release(acquired)

    assert (swarm / ".swarm_lock").exists()
    assert (swarm / "lease_work.txt").exists()
    assert (sandbox / "SENTINEL").exists()


def test_release_keeps_swarm_locked_when_the_lease_base_is_not_a_full_commit_id(
    tmp_path: Path, monkeypatch
):
    import nexus.research.swarm_broker as swarm_broker

    sandbox, controller, swarm, acquired = _swarm_with_lease_base(tmp_path, monkeypatch)
    (swarm / "lease_work.txt").write_text("work\n", encoding="utf-8")
    real_run = swarm_broker.run_hardened_git
    checkouts = []

    def odd_base(repo_dir, *args, **kwargs):
        if "--verify" in args:
            return subprocess.CompletedProcess(args, 0, "--detach\n", "")
        if args and args[0] == "checkout":
            checkouts.append(args)
        return real_run(repo_dir, *args, **kwargs)

    monkeypatch.setattr(swarm_broker, "run_hardened_git", odd_base)

    SwarmBroker(controller).release(acquired)

    assert not checkouts
    assert (swarm / ".swarm_lock").exists()
    assert (swarm / "lease_work.txt").exists()


def test_acquire_marks_swarm_when_recording_the_lease_base_raises_oserror(
    tmp_path: Path, monkeypatch
):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    real_run = subprocess.run

    def raising_update_ref(cmd, *args, **kwargs):
        if cmd[0] == "git" and "update-ref" in cmd:
            raise OSError("git vanished")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", raising_update_ref)
    acquired = SwarmBroker(controller).acquire(timeout_sec=0.05)
    monkeypatch.setattr(subprocess, "run", real_run)

    assert acquired is None
    assert SwarmBroker(controller).locked_swarms() == [(swarm, "release_failed")]
    assert (sandbox / "SENTINEL").exists()


def test_unstarted_lease_mark_is_not_written_into_a_replaced_lock_file(tmp_path: Path, monkeypatch):
    sandbox = _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    broker = SwarmBroker(controller)

    def fail_after_lock_swap(swarm_dir, identity):
        # Another party swaps the lock for its own file after this acquire took it.
        (swarm / ".swarm_lock.other").write_bytes(b"other holder\n")
        os.replace(swarm / ".swarm_lock.other", swarm / ".swarm_lock")
        return False

    monkeypatch.setattr(broker, "_start_lease", fail_after_lock_swap)

    assert broker.acquire(timeout_sec=0.05) is None
    assert (swarm / ".swarm_lock").read_bytes() == b"other holder\n"
    assert (sandbox / "SENTINEL").exists()


def _first_start_fails_then_recovers(tmp_path: Path, monkeypatch, drop_unstarted_mark: bool):
    _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    real_run = subprocess.run

    def failing_update_ref(cmd, *args, **kwargs):
        if cmd[0] == "git" and "update-ref" in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", "error: update-ref refused\n")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", failing_update_ref)
    assert SwarmBroker(controller).acquire(timeout_sec=0.05) is None
    monkeypatch.setattr(subprocess, "run", real_run)
    if drop_unstarted_mark:
        # A lock marked like any other failed release, as by `mark_stale_lease`.
        (swarm / ".swarm_lock").write_bytes(b"release_failed\n")
    return controller, swarm


def test_first_lease_start_failure_is_recovered_without_a_lease_base(tmp_path: Path, monkeypatch):
    controller, swarm = _first_start_fails_then_recovers(tmp_path, monkeypatch, False)

    broker = SwarmBroker(controller)
    assert broker.recover_failed_releases() == [swarm]
    assert broker.acquire(timeout_sec=0.05) == swarm


def test_handed_out_lease_without_a_base_stays_locked_after_recovery(tmp_path: Path, monkeypatch):
    controller, swarm = _first_start_fails_then_recovers(tmp_path, monkeypatch, True)

    broker = SwarmBroker(controller)
    assert broker.recover_failed_releases() == []
    assert broker.locked_swarms() == [(swarm, "release_failed")]


def test_unstarted_swarm_stays_recoverable_after_a_failed_recovery(tmp_path: Path, monkeypatch):
    import nexus.research.swarm_broker as swarm_broker

    controller, swarm = _first_start_fails_then_recovers(tmp_path, monkeypatch, False)
    index_lock = Path(_git(swarm, "rev-parse", "--absolute-git-dir")) / "index.lock"
    index_lock.write_text("", encoding="utf-8")  # fresh: not cleared, so the reset fails
    broker = SwarmBroker(controller)

    assert broker.recover_failed_releases() == []
    assert broker.locked_swarms() == [(swarm, "release_failed")]
    assert (swarm / ".swarm_lock").read_bytes() == b"release_failed\nunstarted\n"

    index_lock.unlink()
    swarm_broker._RECOVERY_FAILED_AT.clear()  # the retry backoff of the failed attempt
    assert broker.recover_failed_releases() == [swarm]
    assert broker.acquire(timeout_sec=0.05) == swarm


def test_git_output_does_not_run_a_program_named_by_the_repository(tmp_path: Path):
    repo = tmp_path / "controller"
    _init_repo(repo)
    marker = tmp_path / "fsmonitor-ran"
    hook = tmp_path / "fsmonitor.sh"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\nexit 0\n", encoding="utf-8")
    hook.chmod(0o755)
    _git(repo, "config", "core.fsmonitor", str(hook))
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")

    SwarmBroker(tmp_path)._git_output(["status", "--porcelain"], repo)

    assert not marker.exists()


def test_git_output_returns_none_when_git_hangs(tmp_path: Path, monkeypatch):
    repo = tmp_path / "controller"
    _init_repo(repo)
    seen = {}

    def hung_run(cmd, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        if kwargs.get("timeout") is None:
            raise AssertionError("git ran without a timeout")
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr("nexus.core.hardened_git.subprocess.run", hung_run)

    assert SwarmBroker(tmp_path)._git_output(["rev-parse", "--show-toplevel"], repo) is None
    assert seen["timeout"] is not None and seen["timeout"] > 0


def test_git_output_returns_none_when_git_fails_with_stdout(tmp_path: Path, monkeypatch):
    def failing_git(cwd, *args, **kwargs):
        return subprocess.CompletedProcess(["git", *args], 1, stdout="x", stderr="")

    monkeypatch.setattr("nexus.research.swarm_broker.run_hardened_git", failing_git)

    assert SwarmBroker(tmp_path)._git_output(["rev-parse", "--show-toplevel"], tmp_path) is None


def test_git_output_returns_none_when_output_cannot_be_decoded(tmp_path: Path, monkeypatch):
    def undecodable_git(cwd, *args, **kwargs):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr("nexus.research.swarm_broker.run_hardened_git", undecodable_git)

    assert SwarmBroker(tmp_path)._git_output(["rev-parse", "--show-toplevel"], tmp_path) is None


def _swarm_with_admin(tmp_path: Path, monkeypatch):
    _sentinel_cwd(tmp_path, monkeypatch)
    controller = tmp_path / "controller"
    base = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), base)
    admin = Path(_git(swarm, "rev-parse", "--absolute-git-dir"))
    return controller, swarm, admin


def _returns_within(seconds: float, call):
    import threading

    box: list = []
    thread = threading.Thread(target=lambda: box.append(call()), daemon=True)
    thread.start()
    thread.join(seconds)
    assert not thread.is_alive(), "back-pointer read blocked on a non-regular file"
    return box[0]


def test_swarm_back_pointer_that_is_a_named_pipe_is_refused_promptly(tmp_path: Path, monkeypatch):
    controller, swarm, admin = _swarm_with_admin(tmp_path, monkeypatch)
    text = (admin / "gitdir").read_bytes()
    (admin / "gitdir").unlink()
    os.mkfifo(admin / "gitdir")
    fd = os.open(admin / "gitdir", os.O_RDWR)
    os.write(fd, text)
    try:
        broker = SwarmBroker(controller)
        assert _returns_within(5, lambda: broker._git_metadata_points_to_own_admin_entry(swarm)) is False
    finally:
        os.close(fd)


def test_swarm_back_pointer_over_the_size_limit_is_refused(tmp_path: Path, monkeypatch):
    controller, swarm, admin = _swarm_with_admin(tmp_path, monkeypatch)
    pointer = admin / "gitdir"
    pointer.write_text(pointer.read_text(encoding="utf-8").strip() + " " * 5000, encoding="utf-8")
    assert SwarmBroker(controller)._git_metadata_points_to_own_admin_entry(swarm) is False
