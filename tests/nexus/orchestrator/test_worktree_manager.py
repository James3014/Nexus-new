import pytest
import subprocess
import shutil
import os
import hashlib
from pathlib import Path
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
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
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
# integrity-seal: 1776512137
