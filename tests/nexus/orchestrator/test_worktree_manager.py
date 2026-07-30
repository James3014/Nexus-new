import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from nexus.orchestrator.task_contract import (
    ApprovalStatus,
    MutationMode,
    SelfHostedTaskContract,
)
from nexus.orchestrator.worktree_manager import WorktreeManager


@pytest.fixture
def temp_git_repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "Initial commit"], cwd=repo_dir, check=True)
    return repo_dir

def test_worktree_create_and_cleanup(temp_git_repo):
    worktree_root = temp_git_repo / ".nexus" / "worktrees"
    manager = WorktreeManager(root_dir=str(worktree_root))
    # We need to change cwd to the repo for git commands to work
    original_cwd = os.getcwd()
    os.chdir(temp_git_repo)
    
    try:
        task_id = "TASK-001"
        path = manager.create(task_id)
        
        assert Path(path).exists()
        assert (Path(path) / ".git").exists()
        
        # Check if branch exists
        branch_name = manager.get_branch_name(task_id)
        result = subprocess.run(["git", "branch"], capture_output=True, text=True)
        assert branch_name in result.stdout
        
        # Cleanup
        manager.cleanup(task_id, force=True)
        assert not Path(path).exists()
        
    finally:
        os.chdir(original_cwd)

def test_worktree_idempotent(temp_git_repo):
    worktree_root = temp_git_repo / ".nexus" / "worktrees"
    manager = WorktreeManager(root_dir=str(worktree_root))
    original_cwd = os.getcwd()
    os.chdir(temp_git_repo)
    
    try:
        task_id = "TASK-002"
        path1 = manager.create(task_id)
        path2 = manager.create(task_id)
        
        assert path1 == path2
        assert Path(path1).exists()
        
    finally:
        os.chdir(original_cwd)


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.fixture
def sh2_repo(tmp_path):
    controller = tmp_path / "controller"
    target_root = tmp_path / "targets"
    controller.mkdir()
    target_root.mkdir()
    _git(controller, "init")
    _git(controller, "config", "user.email", "sh2@example.test")
    _git(controller, "config", "user.name", "SH2 Test")
    (controller / "src").mkdir()
    (controller / "src" / "allowed.txt").write_text("base\n", encoding="utf-8")
    (controller / "outside.txt").write_text("outside\n", encoding="utf-8")
    _git(controller, "add", "src/allowed.txt", "outside.txt")
    _git(controller, "commit", "-m", "target base")
    target_base_revision = _git(controller, "rev-parse", "HEAD")
    (controller / "controller.txt").write_text("controller\n", encoding="utf-8")
    _git(controller, "add", "controller.txt")
    _git(controller, "commit", "-m", "controller revision")
    controller_revision = _git(controller, "rev-parse", "HEAD")
    return {
        "controller": controller,
        "target_root": target_root,
        "controller_revision": controller_revision,
        "target_base_revision": target_base_revision,
    }


def _contract(
    sh2_repo,
    *,
    task_id: str = "sh2-task",
    allowed_files=None,
    forbidden_files=None,
    target_repo_root: Path | None = None,
) -> SelfHostedTaskContract:
    target_root = sh2_repo["target_root"]
    return SelfHostedTaskContract(
        task_id=task_id,
        objective="Capture a bounded candidate",
        controller_revision=sh2_repo["controller_revision"],
        target_base_revision=sh2_repo["target_base_revision"],
        controller_repo_root=str(sh2_repo["controller"]),
        target_repo_root=str(target_repo_root or (target_root / task_id)),
        target_worktree_root=str(target_root),
        allowed_files=allowed_files or ["src/"],
        forbidden_files=forbidden_files or [],
        verifier_commands=[],
        protected_contracts=[],
        preferred_provider=None,
        fallback_provider=None,
        maximum_provider_calls=0,
        maximum_replans=0,
        mutation_mode=MutationMode.WORKING_TREE_ONLY,
        human_approval_required=True,
    )


def _prepare_candidate(sh2_repo, **contract_kwargs):
    contract = _contract(sh2_repo, **contract_kwargs)
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]))
    lease = manager.create_lease(contract)
    return contract, manager, lease, Path(lease.target_worktree)


def test_create_lease_uses_exact_target_revision(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo)

    assert lease.initial_head == contract.target_base_revision
    assert _git(target, "rev-parse", "HEAD") == contract.target_base_revision
    assert lease.created_from_exact_revision is True


def test_create_lease_creates_model_neutral_branch(sh2_repo):
    _, _, lease, target = _prepare_candidate(sh2_repo)

    assert lease.target_branch == "nexus/task/sh2-task"
    assert _git(target, "branch", "--show-current") == "nexus/task/sh2-task"


def test_create_lease_separates_controller_and_target(sh2_repo):
    contract, _, lease, _ = _prepare_candidate(sh2_repo)

    assert Path(lease.target_worktree).resolve() != Path(contract.controller_repo_root).resolve()
    assert Path(contract.controller_repo_root).resolve() not in Path(lease.target_worktree).resolve().parents


def test_create_lease_rejects_dirty_controller(sh2_repo):
    (sh2_repo["controller"] / "controller.txt").write_text("dirty\n", encoding="utf-8")
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]))

    with pytest.raises(RuntimeError, match="Controller.*clean"):
        manager.create_lease(_contract(sh2_repo))


def test_create_lease_rejects_existing_non_worktree_without_deleting_it(sh2_repo):
    target = sh2_repo["target_root"] / "sh2-task"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("do not delete\n", encoding="utf-8")
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]))

    with pytest.raises(RuntimeError, match="existing.*not.*worktree"):
        manager.create_lease(_contract(sh2_repo))

    assert sentinel.read_text(encoding="utf-8") == "do not delete\n"


def test_create_lease_rejects_wrong_existing_worktree_identity(sh2_repo):
    target = sh2_repo["target_root"] / "occupied"
    _git(
        sh2_repo["controller"],
        "worktree",
        "add",
        "-b",
        "nexus/task/wrong-identity",
        str(target),
        sh2_repo["target_base_revision"],
    )
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]))
    contract = _contract(sh2_repo, target_repo_root=target)

    with pytest.raises(RuntimeError, match="identity"):
        manager.create_lease(contract)

    assert target.exists()
    assert _git(target, "branch", "--show-current") == "nexus/task/wrong-identity"


def test_create_lease_does_not_commit_or_merge(sh2_repo):
    controller_head = _git(sh2_repo["controller"], "rev-parse", "HEAD")
    contract, _, lease, target = _prepare_candidate(sh2_repo)

    assert _git(sh2_repo["controller"], "rev-parse", "HEAD") == controller_head
    assert _git(target, "rev-parse", "HEAD") == contract.target_base_revision
    assert lease.commit_created is False
    assert lease.merge_performed is False


def test_candidate_receipt_captures_allowed_tracked_edit(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo)
    (target / "src" / "allowed.txt").write_text("changed\n", encoding="utf-8")

    receipt = manager.capture_candidate(contract, lease)

    assert receipt.changed_files == ["src/allowed.txt"]
    assert receipt.allowed_scope_passed is True
    assert receipt.out_of_scope_paths == []


def test_candidate_receipt_captures_untracked_file(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo)
    content = b"new candidate\n"
    (target / "src" / "new.txt").write_bytes(content)

    receipt = manager.capture_candidate(contract, lease)

    assert receipt.untracked_files == ["src/new.txt"]
    assert receipt.untracked_content_hashes == {
        "src/new.txt": hashlib.sha256(content).hexdigest()
    }


def test_candidate_receipt_captures_deletion(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo)
    (target / "src" / "allowed.txt").unlink()

    receipt = manager.capture_candidate(contract, lease)

    assert receipt.deleted_files == ["src/allowed.txt"]


def test_candidate_receipt_rejects_out_of_scope_edit(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo)
    (target / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")

    receipt = manager.capture_candidate(contract, lease)

    assert receipt.allowed_scope_passed is False
    assert receipt.out_of_scope_paths == ["unexpected.txt"]
    assert (target / "unexpected.txt").exists()


def test_candidate_receipt_forbidden_path_overrides_allowed(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(
        sh2_repo,
        forbidden_files=["src/secret.txt"],
    )
    (target / "src" / "secret.txt").write_text("secret\n", encoding="utf-8")

    receipt = manager.capture_candidate(contract, lease)

    assert receipt.allowed_scope_passed is False
    assert receipt.forbidden_path_violations == ["src/secret.txt"]
    assert receipt.out_of_scope_paths == ["src/secret.txt"]


def test_candidate_receipt_hash_is_deterministic(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo)
    (target / "src" / "allowed.txt").write_text("stable\n", encoding="utf-8")

    first = manager.capture_candidate(contract, lease)
    second = manager.capture_candidate(contract, lease)

    assert first.candidate_state_hash == second.candidate_state_hash


def test_candidate_receipt_changes_when_file_content_changes(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo)
    candidate = target / "src" / "allowed.txt"
    candidate.write_text("first\n", encoding="utf-8")
    first = manager.capture_candidate(contract, lease)
    candidate.write_text("second\n", encoding="utf-8")
    second = manager.capture_candidate(contract, lease)

    assert first.candidate_state_hash != second.candidate_state_hash


def test_candidate_receipt_keeps_controller_unchanged(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo)
    (target / "src" / "allowed.txt").write_text("candidate\n", encoding="utf-8")

    receipt = manager.capture_candidate(contract, lease)

    assert receipt.controller_unchanged is True
    assert receipt.controller_status_before_sha256 == receipt.controller_status_after_sha256
    assert _git(sh2_repo["controller"], "status", "--porcelain") == ""


def test_candidate_receipt_keeps_approval_pending(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo)
    (target / "src" / "allowed.txt").write_text("candidate\n", encoding="utf-8")

    receipt = manager.capture_candidate(contract, lease)

    assert receipt.approval_status == ApprovalStatus.PENDING
    assert receipt.human_approval_required is True
    assert receipt.public_claim_allowed is False
    assert receipt.production_ready is False


def test_candidate_receipt_does_not_stage_files(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo)
    (target / "src" / "allowed.txt").write_text("candidate\n", encoding="utf-8")
    (target / "src" / "new.txt").write_text("untracked\n", encoding="utf-8")

    manager.capture_candidate(contract, lease)

    assert _git(target, "diff", "--cached", "--name-only") == ""


def test_candidate_receipt_does_not_create_commit(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo)
    initial_head = _git(target, "rev-parse", "HEAD")
    (target / "src" / "allowed.txt").write_text("candidate\n", encoding="utf-8")

    receipt = manager.capture_candidate(contract, lease)

    assert _git(target, "rev-parse", "HEAD") == initial_head
    assert receipt.commit_created is False
    assert receipt.merge_performed is False


def test_serial_target_budget_rejects_second_active_target(sh2_repo):
    first = _contract(sh2_repo, task_id="first")
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]))
    manager.create_lease(first)

    with pytest.raises(RuntimeError, match="serial Target budget"):
        manager.create_lease(_contract(sh2_repo, task_id="second"))


def test_candidate_cleanup_requires_durable_ref_and_is_idempotent(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo)
    (target / "src" / "allowed.txt").write_text("candidate\n", encoding="utf-8")
    _git(target, "add", "src/allowed.txt")
    _git(target, "commit", "-m", "candidate")
    candidate = _git(target, "rev-parse", "HEAD")

    blocked = manager.cleanup_terminal_target(contract, lease, candidate_commit=candidate)
    assert blocked.decision == "BLOCKED_BY_MISSING_REF"
    assert target.exists()

    candidate_ref = f"refs/nexus-candidates/{contract.task_id}"
    _git(sh2_repo["controller"], "update-ref", candidate_ref, candidate)
    removed = manager.cleanup_terminal_target(
        contract, lease, candidate_commit=candidate, candidate_ref=candidate_ref
    )
    assert removed.decision == "REMOVED"
    assert not target.exists()
    assert manager.cleanup_terminal_target(
        contract, lease, candidate_commit=candidate, candidate_ref=candidate_ref
    ).decision == "ALREADY_REMOVED"

    retried = manager.create_lease(contract)
    assert retried.initial_head == contract.target_base_revision
    assert retried.target_detached is True
    assert _git(sh2_repo["controller"], "rev-parse", f"refs/heads/{retried.target_branch}") == candidate


def test_create_lease_accepts_verified_salvage_parent_on_revision_refresh(sh2_repo):
    original = _contract(sh2_repo)
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]))
    lease = manager.create_lease(original)
    target = Path(lease.target_worktree)
    (target / "src" / "allowed.txt").write_text("salvaged\n", encoding="utf-8")
    _git(target, "add", "src/allowed.txt")
    _git(target, "commit", "-m", "salvage snapshot")
    salvage = _git(target, "rev-parse", "HEAD")
    _git(sh2_repo["controller"], "update-ref", f"refs/nexus-salvage/worktree/{original.task_id}-attempt-1", salvage)
    assert manager.cleanup_terminal_target(
        original,
        lease,
        candidate_commit=salvage,
        candidate_ref=f"refs/nexus-salvage/worktree/{original.task_id}-attempt-1",
    ).decision == "REMOVED"
    _git(
        sh2_repo["controller"],
        "update-ref",
        f"refs/heads/nexus/task/{original.task_id}",
        original.target_base_revision,
    )

    (sh2_repo["controller"] / "controller.txt").write_text("refreshed\n", encoding="utf-8")
    _git(sh2_repo["controller"], "add", "controller.txt")
    _git(sh2_repo["controller"], "commit", "-m", "refreshed integration base")
    refreshed_sha = _git(sh2_repo["controller"], "rev-parse", "HEAD")
    refreshed = _contract(sh2_repo)
    refreshed = refreshed.model_copy(
        update={
            "controller_revision": refreshed_sha,
            "target_base_revision": refreshed_sha,
        }
    )

    retried = manager.create_lease(refreshed)

    assert retried.target_detached is True
    assert retried.initial_head == refreshed_sha
    assert _git(sh2_repo["controller"], "rev-parse", f"refs/heads/{retried.target_branch}") == original.target_base_revision


def test_dirty_unique_target_is_retained_for_review(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo)
    (target / "src" / "allowed.txt").write_text("unique\n", encoding="utf-8")

    receipt = manager.cleanup_terminal_target(contract, lease)

    assert receipt.decision == "BLOCKED_BY_UNSAVED_CHANGES"
    assert receipt.blocker == "dirty target has no durable snapshot"
    assert target.exists()


def test_empty_unregistered_target_is_removed(sh2_repo):
    contract = _contract(sh2_repo, task_id="empty-unregistered")
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]))
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    _git(sh2_repo["controller"], "worktree", "remove", "--force", str(target))
    target.mkdir()

    receipt = manager.cleanup_terminal_target(contract, lease)

    assert receipt.decision == "REMOVED"
    assert receipt.performed is True
    assert not target.exists()


def test_nonempty_unregistered_target_remains_blocked(sh2_repo):
    contract = _contract(sh2_repo, task_id="nonempty-unregistered")
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]))
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    _git(sh2_repo["controller"], "worktree", "remove", "--force", str(target))
    target.mkdir()
    (target / "retained.txt").write_text("must remain\n", encoding="utf-8")

    receipt = manager.cleanup_terminal_target(contract, lease)

    assert receipt.decision == "BLOCKED_BY_UNSAVED_CHANGES"
    assert receipt.blocker == "unregistered Target is not an empty directory"
    assert target.exists()
    assert (target / "retained.txt").exists()


def test_active_process_blocks_terminal_cleanup(sh2_repo):
    contract = _contract(sh2_repo)
    manager = WorktreeManager(
        root_dir=str(sh2_repo["target_root"]),
        process_checker=lambda path: True,
    )
    lease = manager.create_lease(contract)

    receipt = manager.cleanup_terminal_target(contract, lease)

    assert receipt.decision == "BLOCKED_BY_PROCESS"
    assert Path(lease.target_worktree).exists()


def test_clean_terminal_target_is_removed_and_branch_can_be_reused(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo)

    preview = manager.cleanup_terminal_target(contract, lease, dry_run=True)
    assert preview.decision == "REMOVED"
    assert preview.performed is False
    assert target.exists()

    applied = manager.cleanup_terminal_target(contract, lease)
    assert applied.decision == "REMOVED"
    assert applied.performed is True
    assert not target.exists()

    retried = manager.create_lease(contract)
    assert Path(retried.target_worktree).exists()
    assert retried.initial_head == contract.target_base_revision


def test_candidate_ref_is_immutable_per_candidate_commit(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo)
    (target / "src" / "allowed.txt").write_text("candidate\n", encoding="utf-8")
    _git(target, "add", "src/allowed.txt")
    _git(target, "commit", "-m", "candidate")
    candidate = _git(target, "rev-parse", "HEAD")

    candidate_ref = manager.protect_candidate(contract, lease, candidate)

    assert candidate_ref.endswith(candidate)
    assert _git(sh2_repo["controller"], "rev-parse", candidate_ref) == candidate


def test_candidate_ref_uses_immutable_fallback_when_legacy_parent_exists(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo)
    _git(
        sh2_repo["controller"], "update-ref",
        f"refs/nexus-candidates/{contract.task_id}", contract.target_base_revision,
    )
    (target / "src" / "allowed.txt").write_text("candidate\n", encoding="utf-8")
    _git(target, "add", "src/allowed.txt")
    _git(target, "commit", "-m", "candidate")
    candidate = _git(target, "rev-parse", "HEAD")

    candidate_ref = manager.protect_candidate(contract, lease, candidate)

    assert candidate_ref == f"refs/nexus-candidate-commits/{contract.task_id}/{candidate}"
    assert _git(sh2_repo["controller"], "rev-parse", candidate_ref) == candidate


def test_five_clean_attempts_do_not_grow_worktrees(sh2_repo):
    contract = _contract(sh2_repo, task_id="stable-five")
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]))
    baseline = len(manager._registered_worktrees(sh2_repo["controller"]))

    for _ in range(5):
        lease = manager.create_lease(contract)
        assert manager.cleanup_terminal_target(contract, lease).decision == "REMOVED"

    assert len(manager._registered_worktrees(sh2_repo["controller"])) == baseline


def test_run_git_passes_custom_env_to_subprocess(temp_git_repo):
    worktree_root = temp_git_repo / ".nexus" / "worktrees"
    manager = WorktreeManager(root_dir=str(worktree_root))
    hooks_dir = temp_git_repo / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    post_commit = hooks_dir / "post-commit"
    post_commit.write_text(
        "#!/bin/sh\necho \"HOOK_ENV=$CUSTOM_WORKTREE_ENV\" > hook_out.txt\n",
        encoding="utf-8",
    )
    post_commit.chmod(0o755)
    _git(temp_git_repo, "config", "core.hooksPath", str(hooks_dir))

    manager._run_git(
        ["commit", "--allow-empty", "-m", "env test"],
        cwd=temp_git_repo,
        env={**os.environ, "CUSTOM_WORKTREE_ENV": "isolated_value"},
    )

    assert (temp_git_repo / "hook_out.txt").read_text(encoding="utf-8").strip() == "HOOK_ENV=isolated_value"


def test_run_git_without_env_uses_default_process_environment(temp_git_repo):
    worktree_root = temp_git_repo / ".nexus" / "worktrees"
    manager = WorktreeManager(root_dir=str(worktree_root))
    output = manager._run_git(["rev-parse", "HEAD"], cwd=temp_git_repo)
    assert len(output) == 40
# integrity-seal: 1776512137
