from pathlib import Path
import subprocess
import pytest
import os
from unittest.mock import MagicMock, patch
from nexus.services.workspace import WorkspaceManager


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


@pytest.fixture
def workspace_mgr(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    return WorkspaceManager(project_root)

def test_workspace_lease_success(workspace_mgr):
    """驗證 Workspace 租借流程（Mock Git）。"""
    with (
        patch.object(
            WorkspaceManager, "_hardened_git_dir", return_value=workspace_mgr.project_root
        ),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        
        task_id, branch, path = workspace_mgr.lease(task_id="T123")
        
        assert task_id == "T123"
        assert "isolated/task-T123" in branch
        assert path.name == "T123"
        assert mock_run.called
        # 檢查 git worktree add 是否被呼叫
        args = mock_run.call_args_list[0][0][0]
        assert "worktree" in args
        assert "add" in args

def test_workspace_cleanup(workspace_mgr, tmp_path):
    """驗證 Workspace 清理流程。"""
    task_id = "T123"
    branch = "isolated/task-T123"
    work_path = workspace_mgr.workspace_base / task_id
    work_path.mkdir(parents=True, exist_ok=True)
    
    with (
        patch.object(
            WorkspaceManager, "_hardened_git_dir", return_value=workspace_mgr.project_root
        ),
        patch("subprocess.run") as mock_run,
    ):
        workspace_mgr.cleanup(task_id, branch)
        
        # physical cleanup is allowed, but branch deletion is explicit-only.
        assert mock_run.call_count == 1
        args1 = mock_run.call_args_list[0][0][0]
        assert "remove" in args1


def test_workspace_harvest_fails_closed_without_explicit_legacy_mutation(workspace_mgr):
    with pytest.raises(Exception, match="legacy harvest is disabled"):
        workspace_mgr.harvest("isolated/task-T123", workspace_mgr.workspace_base / "T123")

def test_sync_staged_to_sandbox(workspace_mgr, tmp_path):
    """驗證暫存區同步至沙盒的邏輯。"""
    sandbox_path = tmp_path / "sandbox"
    sandbox_path.mkdir()
    
    # The sandbox side now resolves its git dir and probes its config first (#3339).
    with patch("subprocess.run") as mock_run, \
         patch("pathlib.Path.stat") as mock_stat, \
         patch("nexus.core.hardened_git.repository_git_dir", return_value=sandbox_path / ".git"), \
         patch("nexus.core.hardened_git.repository_config_can_start_a_program", return_value=False):
        
        mock_run.return_value = MagicMock(returncode=0)
        # st_mode: the pinned git dir is checked as a directory (0o040755 = S_IFDIR | 0o755).
        mock_stat.return_value = MagicMock(st_size=100, st_mode=0o040755) # 模擬 patch 大小 > 0
        
        success = workspace_mgr.sync_staged_to_sandbox(sandbox_path)
        assert success is True
        # 應包含 git diff --staged, git apply, git add .
        assert mock_run.call_count >= 3


def test_lease_rejects_placeholder_swarm_and_preserves_controller(tmp_path, monkeypatch):
    controller = tmp_path / "controller"
    head_before = _init_repo(controller)
    placeholder = controller / ".nexus-swarm-001"
    placeholder.mkdir()
    (placeholder / "marker.txt").write_text("ordinary child\n", encoding="utf-8")
    status_before = _git(controller, "status", "--porcelain=v1", "-z")
    branch_before = _git(controller, "branch", "--show-current")
    workspace_base = tmp_path / "workspaces"
    monkeypatch.setenv("NEXUS_WORKSPACE_BASE", str(workspace_base))
    monkeypatch.setattr(WorkspaceManager, "_sync_brain_to_path", lambda self, path: None)

    manager = WorkspaceManager(controller)
    task_id, branch, path = manager.lease(task_id="T123")

    assert task_id == "T123"
    assert branch == "isolated/task-T123"
    assert path.resolve() != placeholder.resolve()
    assert path.resolve() == (workspace_base / "T123").resolve()
    assert _git(path, "rev-parse", "--show-toplevel") == str(path.resolve())
    assert str(path.resolve()) in _git(controller, "worktree", "list", "--porcelain")
    assert _git(controller, "rev-parse", "HEAD") == head_before
    assert _git(controller, "branch", "--show-current") == branch_before
    assert _git(controller, "status", "--porcelain=v1", "-z") == status_before


def test_lease_accepts_registered_swarm_worktree_and_preserves_controller(tmp_path, monkeypatch):
    controller = tmp_path / "controller"
    head_before = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), head_before)
    status_before = _git(controller, "status", "--porcelain=v1", "-z")
    branch_before = _git(controller, "branch", "--show-current")
    monkeypatch.setenv("NEXUS_WORKSPACE_BASE", str(tmp_path / "workspaces"))
    monkeypatch.setenv("NEXUS_ALLOW_LEGACY_SWARM_REUSE", "1")
    monkeypatch.setattr(WorkspaceManager, "_sync_brain_to_path", lambda self, path: None)

    manager = WorkspaceManager(controller)
    task_id, branch, path = manager.lease(task_id="T456")

    assert task_id == "T456"
    assert branch == "isolated/task-T456"
    assert path.resolve() == swarm.resolve()
    assert _git(path, "rev-parse", "--show-toplevel") == str(swarm.resolve())
    assert _git(path, "branch", "--show-current") == "isolated/task-T456"
    assert (swarm / ".swarm_lease").read_text(encoding="utf-8") == "isolated/task-T456"
    assert _git(controller, "rev-parse", "HEAD") == head_before
    assert _git(controller, "branch", "--show-current") == branch_before
    assert _git(controller, "status", "--porcelain=v1", "-z") == status_before


def test_legacy_reuse_releases_the_swarm_when_its_checkout_fails(tmp_path, monkeypatch):
    import nexus.core.hardened_git as hardened_git

    controller = tmp_path / "controller"
    head = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), head)
    monkeypatch.setenv("NEXUS_WORKSPACE_BASE", str(tmp_path / "workspaces"))
    monkeypatch.setenv("NEXUS_ALLOW_LEGACY_SWARM_REUSE", "1")
    monkeypatch.setattr(WorkspaceManager, "_sync_brain_to_path", lambda self, path: None)
    real_run = hardened_git.run_hardened_git
    seen = []

    def failing_branch_checkout(repo_dir, *args, **kwargs):
        if args[:2] == ("checkout", "-b"):
            seen.append(args)
            return subprocess.CompletedProcess(args, 1, "", "fatal: refused\n")
        return real_run(repo_dir, *args, **kwargs)

    monkeypatch.setattr(hardened_git, "run_hardened_git", failing_branch_checkout)

    WorkspaceManager(controller).lease(task_id="T789")

    assert seen
    assert not (swarm / ".swarm_lock").exists()


def test_legacy_reuse_error_names_the_swarm_path_when_it_is_not_registered(
    tmp_path, monkeypatch, caplog
):
    from nexus.research.swarm_broker import SwarmBroker

    controller = tmp_path / "controller"
    head = _init_repo(controller)
    swarm = controller / ".nexus-swarm-001"
    _git(controller, "worktree", "add", "--detach", str(swarm), head)
    monkeypatch.setenv("NEXUS_WORKSPACE_BASE", str(tmp_path / "workspaces"))
    monkeypatch.setenv("NEXUS_ALLOW_LEGACY_SWARM_REUSE", "1")
    monkeypatch.setattr(WorkspaceManager, "_sync_brain_to_path", lambda self, path: None)
    real_check = SwarmBroker.is_independently_registered_worktree
    calls = []

    def registered_only_for_acquire(self, path):
        # `acquire` checks first; the manager's own check afterwards sees it unregistered.
        calls.append(path)
        return real_check(self, path) if len(calls) == 1 else False

    monkeypatch.setattr(
        SwarmBroker, "is_independently_registered_worktree", registered_only_for_acquire
    )

    with caplog.at_level("WARNING"):
        WorkspaceManager(controller).lease(task_id="T790")

    assert f"not an independently registered worktree: {swarm}" in caplog.text


def _sync_manager(project_root: Path, tmp_path: Path) -> WorkspaceManager:
    return WorkspaceManager(project_root)


def test_sync_staged_to_sandbox_runs_git_hardened(tmp_path, monkeypatch):
    main = tmp_path / "main"
    _init_repo(main)
    sandbox = tmp_path / "sandbox"
    _init_repo(sandbox)
    marker = tmp_path / "fsmonitor-ran"
    hook = tmp_path / "fsmon.sh"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    hook.chmod(0o755)
    _git(main, "config", "core.fsmonitor", str(hook))
    (main / "tracked.txt").write_text("controller\nstaged change\n", encoding="utf-8")
    _git(main, "add", "tracked.txt")
    monkeypatch.setenv("NEXUS_SYNC_PATCH", str(tmp_path / "sync.patch"))
    marker.unlink(missing_ok=True)  # the plain git calls above already ran the hook

    assert _sync_manager(main, tmp_path).sync_staged_to_sandbox(sandbox) is True

    assert not marker.exists()
    assert "staged change" in (sandbox / "tracked.txt").read_text(encoding="utf-8")


def test_sync_staged_to_sandbox_fails_closed_when_git_hangs(tmp_path, monkeypatch):
    import nexus.core.hardened_git as hardened_git

    def hang(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=1)

    monkeypatch.setattr(hardened_git, "run_hardened_git", hang)
    monkeypatch.setenv("NEXUS_SYNC_PATCH", str(tmp_path / "sync.patch"))
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    assert _sync_manager(tmp_path, tmp_path).sync_staged_to_sandbox(sandbox) is False


def test_sync_staged_to_sandbox_relative_patch_path_is_applied(tmp_path, monkeypatch):
    main = tmp_path / "main"
    _init_repo(main)
    sandbox = tmp_path / "sandbox"
    _init_repo(sandbox)
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    (cwd / "rel.patch").write_text("", encoding="utf-8")  # same name, empty, in Python cwd
    (main / "tracked.txt").write_text("controller\nstaged change\n", encoding="utf-8")
    _git(main, "add", "tracked.txt")
    monkeypatch.setenv("NEXUS_SYNC_PATCH", "rel.patch")
    monkeypatch.chdir(cwd)

    result = _sync_manager(main, tmp_path).sync_staged_to_sandbox(sandbox)

    assert result is True
    assert "staged change" in (sandbox / "tracked.txt").read_text(encoding="utf-8")


def test_sync_staged_to_sandbox_refuses_sandbox_config_naming_a_program(tmp_path, monkeypatch):
    main = tmp_path / "main"
    _init_repo(main)
    sandbox = tmp_path / "sandbox"
    _init_repo(sandbox)
    marker = tmp_path / "filter-ran"
    script = tmp_path / "filter.sh"
    script.write_text(f"#!/bin/sh\ntouch {marker}\ncat\n", encoding="utf-8")
    script.chmod(0o755)
    _git(sandbox, "config", "filter.x.clean", str(script))
    _git(sandbox, "config", "filter.x.smudge", str(script))
    (sandbox / ".git" / "info").mkdir(exist_ok=True)
    (sandbox / ".git" / "info" / "attributes").write_text("* filter=x\n", encoding="utf-8")
    (main / "tracked.txt").write_text("controller\nstaged change\n", encoding="utf-8")
    _git(main, "add", "tracked.txt")
    monkeypatch.setenv("NEXUS_SYNC_PATCH", str(tmp_path / "sync.patch"))
    marker.unlink(missing_ok=True)

    assert _sync_manager(main, tmp_path).sync_staged_to_sandbox(sandbox) is False

    assert not marker.exists()
    assert "staged change" not in (sandbox / "tracked.txt").read_text(encoding="utf-8")


def test_sync_staged_to_sandbox_refuses_a_patch_path_that_is_a_link(tmp_path, monkeypatch):
    """A configured patch path that is a link is refused; the link target is not written."""
    controller = tmp_path / "controller"
    _init_repo(controller)
    (controller / "tracked.txt").write_text("changed\n", encoding="utf-8")
    _git(controller, "add", "tracked.txt")
    target = tmp_path / "victim.txt"
    target.write_text("keep me\n", encoding="utf-8")
    link = tmp_path / "sync.patch"
    link.symlink_to(target)
    monkeypatch.setenv("NEXUS_SYNC_PATCH", str(link))
    monkeypatch.setenv("NEXUS_WORKSPACE_BASE", str(tmp_path / "workspaces"))
    mgr = WorkspaceManager(controller)

    assert mgr.sync_staged_to_sandbox(tmp_path / "sandbox") is False
    assert target.read_text(encoding="utf-8") == "keep me\n"



# --- #3343: the remaining git calls run through the hardened runner ---


def _hostile_repo(tmp_path):
    """A repo whose config names a smudge filter (applied to every file) that writes a marker."""
    repo = tmp_path / "project"
    _init_repo(repo)
    marker = tmp_path / "filter-ran"
    script = tmp_path / "smudge.sh"
    script.write_text(f"#!/bin/sh\ntouch {marker}\ncat\n", encoding="utf-8")
    script.chmod(0o755)
    (repo / ".gitattributes").write_text("* filter=evil\n", encoding="utf-8")
    _git(repo, "add", ".gitattributes")
    _git(repo, "commit", "-m", "attrs")
    _git(repo, "config", "filter.evil.smudge", str(script))
    marker.unlink(missing_ok=True)
    return repo, marker


def _manager(repo, tmp_path):
    mgr = WorkspaceManager(repo)
    mgr.workspace_base = tmp_path / "ws"
    mgr.workspace_base.mkdir(exist_ok=True)
    return mgr


def _hang_on(monkeypatch, subcommand):
    """run_hardened_git raises TimeoutExpired for ``subcommand``; the probes run for real."""
    import nexus.core.hardened_git as hardened_git

    real = hardened_git.run_hardened_git

    def run(repo_dir, *args, **kwargs):
        if args and args[0] == subcommand:
            raise subprocess.TimeoutExpired(cmd="git", timeout=1)
        return real(repo_dir, *args, **kwargs)

    monkeypatch.setattr(hardened_git, "run_hardened_git", run)


def test_lease_refuses_a_repository_config_naming_a_program(tmp_path):
    repo, marker = _hostile_repo(tmp_path)
    mgr = _manager(repo, tmp_path)
    assert mgr.lease(task_id="T1") == (None, None, None)
    assert not marker.exists()
    assert not (mgr.workspace_base / "T1").exists()


def test_lease_fails_closed_when_worktree_add_hangs(tmp_path, monkeypatch):
    repo = tmp_path / "project"
    _init_repo(repo)
    mgr = _manager(repo, tmp_path)
    _hang_on(monkeypatch, "worktree")
    assert mgr.lease(task_id="T1") == (None, None, None)


def test_lease_runs_through_the_hardened_runner_on_a_clean_repo(tmp_path):
    repo = tmp_path / "project"
    _init_repo(repo)
    mgr = _manager(repo, tmp_path)
    task_id, branch, path = mgr.lease(task_id="T1")
    assert path == mgr.workspace_base / "T1"
    assert (path / "tracked.txt").exists()


def test_cleanup_refuses_a_repository_config_naming_a_program(tmp_path):
    repo, marker = _hostile_repo(tmp_path)
    mgr = _manager(repo, tmp_path)
    work = mgr.workspace_base / "T1"
    _git(repo, "worktree", "add", "-b", "isolated/task-T1", str(work), "HEAD")
    marker.unlink(missing_ok=True)  # the plain add above ran the filter
    mgr.cleanup("T1", "isolated/task-T1")
    assert not marker.exists()
    assert work.exists()  # git was not run, so the registered worktree was not removed


def test_cleanup_branch_delete_refuses_a_config_naming_a_program(tmp_path, monkeypatch):
    repo, marker = _hostile_repo(tmp_path)
    _git(repo, "branch", "isolated/task-T1")
    mgr = _manager(repo, tmp_path)
    (mgr.workspace_base / "T1").mkdir()
    monkeypatch.setenv(WorkspaceManager.LEGACY_MUTATION_ENV, "1")
    mgr.cleanup("T1", "isolated/task-T1")
    assert not marker.exists()
    assert "isolated/task-T1" in _git(repo, "branch", "--list", "isolated/task-T1")


def test_cleanup_fails_closed_when_git_hangs(tmp_path, monkeypatch):
    repo = tmp_path / "project"
    _init_repo(repo)
    mgr = _manager(repo, tmp_path)
    (mgr.workspace_base / "T1").mkdir()
    _hang_on(monkeypatch, "worktree")
    mgr.cleanup("T1", "isolated/task-T1")  # returns instead of hanging; nothing raised


def test_auto_gc_refuses_a_repository_config_naming_a_program(tmp_path, monkeypatch):
    repo, marker = _hostile_repo(tmp_path)
    mgr = _manager(repo, tmp_path)
    stale = mgr.workspace_base / "old"
    _git(repo, "worktree", "add", "-b", "old", str(stale), "HEAD")
    marker.unlink(missing_ok=True)  # the plain add above ran the filter
    old = 1_000_000_000
    os.utime(stale, (old, old))
    monkeypatch.setattr(mgr, "_is_independently_registered_worktree", lambda path: True)
    mgr._auto_gc()
    assert not marker.exists()
    assert stale.exists()


def test_harvest_refuses_a_repository_config_naming_a_program(tmp_path, monkeypatch):
    repo, marker = _hostile_repo(tmp_path)
    _git(repo, "branch", "feature")
    head = _git(repo, "rev-parse", "HEAD")
    mgr = _manager(repo, tmp_path)
    monkeypatch.setenv(WorkspaceManager.LEGACY_MUTATION_ENV, "1")
    monkeypatch.setattr(mgr, "_trigger_flash_crystallization", lambda: None)
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    assert mgr.harvest("feature", sandbox) is False
    assert not marker.exists()
    assert _git(repo, "rev-parse", "HEAD") == head


def test_ensure_sandbox_committed_refuses_a_config_naming_a_program(tmp_path):
    sandbox, marker = _hostile_repo(tmp_path)
    (sandbox / "tracked.txt").write_text("changed\n", encoding="utf-8")
    _git(sandbox, "add", "tracked.txt")
    head = _git(sandbox, "rev-parse", "HEAD")
    _manager(sandbox, tmp_path)._ensure_sandbox_committed(sandbox)
    assert _git(sandbox, "rev-parse", "HEAD") == head


def test_merge_steps_fail_closed_when_git_hangs(tmp_path, monkeypatch):
    repo = tmp_path / "project"
    _init_repo(repo)
    _git(repo, "branch", "feature")
    mgr = _manager(repo, tmp_path)
    _hang_on(monkeypatch, "merge")
    assert mgr._execute_merge("feature") is False
    _hang_on(monkeypatch, "checkout")
    mgr._prepare_main_for_merge()  # bounded: returns instead of hanging


def test_run_git_stays_pinned_to_the_probed_git_dir_when_the_pointer_is_rewritten(
    tmp_path, monkeypatch
):
    """#3351: git runs on the git dir probed before the call, never on one a rewritten
    .git pointer names afterwards."""
    controller = tmp_path / "controller"
    _init_repo(controller)
    work = tmp_path / "work"
    _git(controller, "worktree", "add", "-q", "--detach", str(work))
    other = tmp_path / "other"
    other_head = _init_repo(other)
    monkeypatch.setenv("NEXUS_WORKSPACE_BASE", str(tmp_path / "workspaces"))
    mgr = WorkspaceManager(controller)
    probed = mgr._hardened_git_dir(work)
    assert probed is not None
    monkeypatch.setattr(WorkspaceManager, "_hardened_git_dir", staticmethod(lambda cwd: probed))
    (work / ".git").write_text(f"gitdir: {other / '.git'}\n", encoding="utf-8")

    mgr._run_git(work, "commit", "--allow-empty", "-q", "-m", "should not land in other")

    assert _git(other, "rev-parse", "HEAD") == other_head
