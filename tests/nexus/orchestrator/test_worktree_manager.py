import hashlib
import json
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
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True, env=env)
    subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "commit", "--allow-empty", "-m", "Initial commit"],
        cwd=repo_dir, check=True, env=env,
    )
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
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
    git_args = list(args)
    if not any("core.hooksPath" in a for a in args):
        hooks_dir = cwd.parent / ".nexus_test_hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        git_args = ["-c", f"core.hooksPath={hooks_dir}", *args]
    result = subprocess.run(
        ["git", *git_args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=env,
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


def test_candidate_receipt_accepts_precommitted_target_changes(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo)
    (target / "src" / "allowed.txt").write_text("committed candidate\n", encoding="utf-8")
    _git(target, "add", "src/allowed.txt")
    _git(target, "commit", "-m", "worker candidate")

    receipt = manager.capture_candidate(contract, lease)

    assert receipt.target_head == _git(target, "rev-parse", "HEAD")
    assert receipt.changed_files == ["src/allowed.txt"]
    assert receipt.allowed_scope_passed is True
    assert _git(target, "status", "--porcelain") == ""


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


def test_serial_target_budget_ignores_retained_dirty_target(sh2_repo):
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]), process_checker=lambda _path: False)
    retained = _contract(sh2_repo, task_id="retained")
    retained_lease = manager.create_lease(retained)
    Path(retained_lease.target_worktree, "retained.txt").write_text("evidence\n", encoding="utf-8")

    second = _contract(sh2_repo, task_id="second")
    with pytest.raises(RuntimeError, match="serial Target budget"):
        manager.create_lease(
            second,
            task_states={"retained": {"status": "FINAL_BLOCK", "lease": retained_lease.__dict__}},
        )
    assert Path(retained_lease.target_worktree, "retained.txt").exists()


def test_serial_target_budget_fails_closed_when_process_evidence_unknown(sh2_repo):
    first = _contract(sh2_repo, task_id="unknown-process")
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]), process_checker=lambda _path: None)
    manager.create_lease(first)

    with pytest.raises(RuntimeError, match="serial Target budget"):
        manager.create_lease(_contract(sh2_repo, task_id="second"))


def test_serial_target_budget_ignores_detached_dirty_non_task_target(sh2_repo):
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]), process_checker=lambda _path: False)
    unmapped = sh2_repo["target_root"] / "unmapped-detached"
    _git(sh2_repo["controller"], "worktree", "add", "--detach", str(unmapped), sh2_repo["target_base_revision"])
    (unmapped / "forensic.txt").write_text("evidence\n", encoding="utf-8")

    manager.create_lease(_contract(sh2_repo, task_id="second"))
    assert (unmapped / "forensic.txt").exists()


def test_serial_target_budget_fails_closed_for_unmapped_managed_target(sh2_repo):
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]), process_checker=lambda _path: False)
    unmapped = sh2_repo["target_root"] / "unmapped-managed"
    _git(sh2_repo["controller"], "worktree", "add", "-b", "nexus/task/unmapped", str(unmapped), sh2_repo["target_base_revision"])

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


def test_ten_clean_attempts_do_not_grow_worktrees(sh2_repo):
    contract = _contract(sh2_repo, task_id="stable-ten")
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]))
    baseline = len(manager._registered_worktrees(sh2_repo["controller"]))

    for _ in range(10):
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
        ["-c", f"core.hooksPath={hooks_dir}", "commit", "--allow-empty", "-m", "env test"],
        cwd=temp_git_repo,
        env={**os.environ, "CUSTOM_WORKTREE_ENV": "isolated_value"},
    )

    assert (temp_git_repo / "hook_out.txt").read_text(encoding="utf-8").strip() == "HOOK_ENV=isolated_value"


def test_run_git_without_env_uses_default_process_environment(temp_git_repo):
    worktree_root = temp_git_repo / ".nexus" / "worktrees"
    manager = WorktreeManager(root_dir=str(worktree_root))
    output = manager._run_git(["rev-parse", "HEAD"], cwd=temp_git_repo)
    assert len(output) == 40


# ---------------------------------------------------------------------------
# LC1: restore_task_branch_for_retry — salvage → cleanup → branch restoration
# ---------------------------------------------------------------------------

def _setup_salvage_scenario(sh2_repo, *, task_id="salvage-lc1"):
    """Helper: create contract, lease, salvage commit + ref, cleanup target.

    Returns (contract, manager, lease, salvage_commit, salvage_ref, controller).
    """
    contract = _contract(
        sh2_repo,
        task_id=task_id,
        allowed_files=["src/"],
    )
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]))
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "src" / "allowed.txt").write_text("salvaged\n", encoding="utf-8")
    _git(target, "add", "src/allowed.txt")
    _git(target, "commit", "-m", f"salvage: {task_id}")
    salvage_commit = _git(target, "rev-parse", "HEAD")
    salvage_ref = f"refs/nexus-salvage/worktree/{task_id}-attempt-1"
    _git(sh2_repo["controller"], "update-ref", salvage_ref, salvage_commit)
    removed = manager.cleanup_terminal_target(
        contract, lease,
        salvage_commit=salvage_commit,
        salvage_ref=salvage_ref,
    )
    assert removed.decision == "REMOVED", f"cleanup failed: {removed}"
    return contract, manager, lease, salvage_commit, salvage_ref


def test_restore_task_branch_happy_path(sh2_repo):
    """Dirty Target → salvage commit + ref → cleanup → branch restored.

    Verifies tests 1-4 from LC1 spec.
    """
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)

    # 2: restore the task branch to initial_head
    restored = manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)
    assert restored["decision"] == "RESTORED"
    assert restored["restored_to"] == lease.initial_head

    # 2b: branch now points to initial_head
    branch_ref = f"refs/heads/nexus/task/{contract.task_id}"
    branch_head = _git(sh2_repo["controller"], "rev-parse", branch_ref)
    assert branch_head == contract.target_base_revision

    # 3: salvage ref still resolves to salvage commit
    assert _git(sh2_repo["controller"], "rev-parse", salvage_ref) == salvage_commit

    # 4: new integration revision → detached Target
    (sh2_repo["controller"] / "controller.txt").write_text("refreshed\n", encoding="utf-8")
    _git(sh2_repo["controller"], "add", "controller.txt")
    _git(sh2_repo["controller"], "commit", "-m", "refreshed integration base")
    refreshed_sha = _git(sh2_repo["controller"], "rev-parse", "HEAD")
    refreshed = contract.model_copy(update={
        "controller_revision": refreshed_sha,
        "target_base_revision": refreshed_sha,
    })
    retried = manager.create_lease(refreshed)
    assert retried.target_detached is True
    assert retried.initial_head == refreshed_sha
    # Branch still at original base (not the salvage commit)
    assert _git(sh2_repo["controller"], "rev-parse", branch_ref) == contract.target_base_revision


def test_restore_rejects_branch_not_at_salvage_or_initial_head(sh2_repo):
    """Safety check 2: branch differs from both salvage_commit AND initial_head → fail-closed."""
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)
    # Move branch to a third SHA (not salvage_commit, not initial_head)
    branch_ref = f"refs/heads/nexus/task/{contract.task_id}"
    unrelated = _git(sh2_repo["controller"], "rev-parse", "HEAD")
    _git(sh2_repo["controller"], "update-ref", branch_ref, unrelated)
    with pytest.raises(RuntimeError, match="Safety check 2 failed"):
        manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)


def test_restore_already_restored_when_branch_at_initial_head(sh2_repo):
    """After cleanup + prior restore, branch at initial_head → ALREADY_RESTORED."""
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)
    # Simulate branch already at initial_head (as restore_task_branch would leave it)
    branch_ref = f"refs/heads/nexus/task/{contract.task_id}"
    _git(sh2_repo["controller"], "update-ref", branch_ref, lease.initial_head)
    result = manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)
    assert result["decision"] == "ALREADY_RESTORED"
    assert result["restored_to"] == lease.initial_head


def test_restore_rejects_missing_salvage_ref(sh2_repo):
    """Safety check 3: salvage ref missing → fail-closed."""
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)
    # Delete salvage ref
    _git(sh2_repo["controller"], "update-ref", "-d", salvage_ref)
    with pytest.raises(RuntimeError, match="Safety check 3 failed"):
        manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)


def test_restore_rejects_wrong_salvage_ref(sh2_repo):
    """Safety check 3: salvage ref points to different commit → fail-closed."""
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)
    # Point salvage ref elsewhere
    _git(sh2_repo["controller"], "update-ref", salvage_ref, contract.target_base_revision)
    with pytest.raises(RuntimeError, match="Safety check 3 failed"):
        manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)


def test_restore_rejects_multi_parent_salvage(sh2_repo):
    """Safety check 4: merge commit as salvage → fail-closed."""
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)
    controller = sh2_repo["controller"]
    # Create a second parent by making another commit and merging
    _git(controller, "checkout", "-b", "side-branch", contract.target_base_revision)
    (controller / "side.txt").write_text("side\n", encoding="utf-8")
    _git(controller, "add", "side.txt")
    _git(controller, "commit", "-m", "side commit")
    side_sha = _git(controller, "rev-parse", "HEAD")
    # Create merge commit on the task branch
    branch_ref = f"refs/heads/nexus/task/{contract.task_id}"
    _git(controller, "checkout", branch_ref)
    _git(controller, "merge", side_sha, "--no-edit")
    merge_sha = _git(controller, "rev-parse", "HEAD")
    # Update salvage ref to point to merge commit
    _git(controller, "update-ref", salvage_ref, merge_sha)
    # Also update branch to point to the merge commit
    _git(controller, "update-ref", branch_ref, merge_sha)
    with pytest.raises(RuntimeError, match="Safety check 4 failed"):
        manager.restore_task_branch_for_retry(contract, lease, merge_sha, salvage_ref)


def test_restore_rejects_wrong_parent(sh2_repo):
    """Safety check 5: salvage parent ≠ initial_head → fail-closed."""
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)
    controller = sh2_repo["controller"]
    # Create a new commit on controller that is NOT the original base
    (controller / "new_base.txt").write_text("new\n", encoding="utf-8")
    _git(controller, "add", "new_base.txt")
    _git(controller, "commit", "-m", "new base")
    wrong_head = _git(controller, "rev-parse", "HEAD")
    # Create a salvage commit from the wrong parent
    branch_ref = f"refs/heads/nexus/task/{contract.task_id}"
    _git(controller, "checkout", branch_ref)
    _git(controller, "reset", "--soft", wrong_head)
    _git(controller, "commit", "-m", "salvage from wrong parent")
    wrong_salvage = _git(controller, "rev-parse", "HEAD")
    # Point branch to the new salvage commit
    _git(controller, "update-ref", branch_ref, wrong_salvage)
    _git(controller, "update-ref", salvage_ref, wrong_salvage)
    with pytest.raises(RuntimeError, match="Safety check 5 failed"):
        manager.restore_task_branch_for_retry(contract, lease, wrong_salvage, salvage_ref)


def test_restore_rejects_active_candidate(sh2_repo):
    """Safety check 7: active candidate binding → fail-closed."""
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)
    # Create a candidate ref for the same task
    _git(sh2_repo["controller"], "update-ref",
         f"refs/nexus-candidates/{contract.task_id}/candidate-1", salvage_commit)
    with pytest.raises(RuntimeError, match="Safety check 7 failed"):
        manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)


def test_restore_rejects_active_candidate_legacy(sh2_repo):
    """Safety check 7: legacy candidate ref → fail-closed."""
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)
    _git(sh2_repo["controller"], "update-ref",
         f"refs/nexus-candidates/{contract.task_id}", salvage_commit)
    with pytest.raises(RuntimeError, match="Safety check 7 failed"):
        manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)


def test_restore_rejects_active_candidate_commit(sh2_repo):
    """Safety check 7: candidate-commit ref → fail-closed."""
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)
    _git(sh2_repo["controller"], "update-ref",
         f"refs/nexus-candidate-commits/{contract.task_id}/{salvage_commit}", salvage_commit)
    with pytest.raises(RuntimeError, match="Safety check 7 failed"):
        manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)


def test_restore_rejects_registered_target(sh2_repo):
    """Safety check 6: Target still registered → fail-closed."""
    contract = _contract(sh2_repo, task_id="reg-target-test")
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]))
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "src" / "allowed.txt").write_text("salvaged\n", encoding="utf-8")
    _git(target, "add", "src/allowed.txt")
    _git(target, "commit", "-m", "salvage commit before restore")
    salvage_commit = _git(target, "rev-parse", "HEAD")
    salvage_ref = f"refs/nexus-salvage/worktree/{contract.task_id}-attempt-1"
    _git(sh2_repo["controller"], "update-ref", salvage_ref, salvage_commit)
    # Do NOT cleanup — target is still registered
    with pytest.raises(RuntimeError, match="Safety check 6 failed"):
        manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)


def test_restore_rejects_concurrent_branch_modification(sh2_repo):
    """Branch moved to a third SHA before restore → fail-closed (caught by check 2 or 8)."""
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)
    branch_ref = f"refs/heads/nexus/task/{contract.task_id}"
    unrelated = _git(sh2_repo["controller"], "rev-parse", "HEAD")
    _git(sh2_repo["controller"], "update-ref", branch_ref, unrelated)
    with pytest.raises(RuntimeError, match="Safety check [28] failed"):
        manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)


def test_restore_fails_on_second_call(sh2_repo):
    """Repeated restore is safe: second call fails-closed (idempotent by exclusion).

    Corresponds to LC1 test 10: idempotent re-cleanup/reconcile.
    """
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)
    # First call succeeds
    restored = manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)
    assert restored["decision"] == "RESTORED"
    assert restored["restored_to"] == lease.initial_head
    # Second call: branch already at initial_head → ALREADY_RESTORED
    already = manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)
    assert already["decision"] == "ALREADY_RESTORED"
    assert already["restored_to"] == lease.initial_head
    # No ref or branch mutation on second call
    branch_ref = f"refs/heads/nexus/task/{contract.task_id}"
    assert _git(sh2_repo["controller"], "rev-parse", branch_ref) == lease.initial_head
    assert _git(sh2_repo["controller"], "rev-parse", salvage_ref) == salvage_commit


def test_existing_salvage_retry_test_unchanged(sh2_repo):
    """LC1 test 11: ensure existing salvage+retry test still works unchanged.

    This exact test was already passing before the LC1 change and must not regress.
    """
    original = _contract(sh2_repo)
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]))
    lease = manager.create_lease(original)
    target = Path(lease.target_worktree)
    (target / "src" / "allowed.txt").write_text("salvaged\n", encoding="utf-8")
    _git(target, "add", "src/allowed.txt")
    _git(target, "commit", "-m", "salvage snapshot")
    salvage = _git(target, "rev-parse", "HEAD")
    _git(sh2_repo["controller"],
         "update-ref", f"refs/nexus-salvage/worktree/{original.task_id}-attempt-1", salvage)
    assert manager.cleanup_terminal_target(
        original, lease,
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
    refreshed = refreshed.model_copy(update={
        "controller_revision": refreshed_sha,
        "target_base_revision": refreshed_sha,
    })
    retried = manager.create_lease(refreshed)
    assert retried.target_detached is True
    assert retried.initial_head == refreshed_sha
    assert _git(sh2_repo["controller"],
                "rev-parse", f"refs/heads/{retried.target_branch}") == original.target_base_revision


# ---------------------------------------------------------------------------
# LC2: restore_task_branch_for_retry — idempotent ALREADY_RESTORED
# ---------------------------------------------------------------------------

def test_restore_returns_already_restored_on_second_call(sh2_repo):
    """LC2 test 2: second restore returns ALREADY_RESTORED, no error."""
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)
    first = manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)
    assert first["decision"] == "RESTORED"
    second = manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)
    assert second["decision"] == "ALREADY_RESTORED"


def test_restore_already_restored_no_ref_or_branch_mutation(sh2_repo):
    """LC2 test 3: ALREADY_RESTORED does not touch ref or branch."""
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)
    manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)
    branch_ref = f"refs/heads/nexus/task/{contract.task_id}"
    branch_before = _git(sh2_repo["controller"], "rev-parse", branch_ref)
    salvage_before = _git(sh2_repo["controller"], "rev-parse", salvage_ref)
    manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)
    assert _git(sh2_repo["controller"], "rev-parse", branch_ref) == branch_before
    assert _git(sh2_repo["controller"], "rev-parse", salvage_ref) == salvage_before


def test_restore_fails_on_third_sha(sh2_repo):
    """LC2 test 4: branch at third SHA → fail closed."""
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)
    branch_ref = f"refs/heads/nexus/task/{contract.task_id}"
    _git(sh2_repo["controller"], "update-ref", branch_ref, contract.target_base_revision)
    # Create a third unrelated commit
    (sh2_repo["controller"] / "third.txt").write_text("third\n", encoding="utf-8")
    _git(sh2_repo["controller"], "add", "third.txt")
    _git(sh2_repo["controller"], "commit", "-m", "third commit")
    third_sha = _git(sh2_repo["controller"], "rev-parse", "HEAD")
    _git(sh2_repo["controller"], "update-ref", branch_ref, third_sha)
    with pytest.raises(RuntimeError, match="Safety check 2 failed"):
        manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)


def test_restore_already_restored_fails_with_wrong_salvage_ref(sh2_repo):
    """LC2 test 5: branch at initial_head but salvage ref missing → fail closed."""
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)
    manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)
    # Delete salvage ref
    _git(sh2_repo["controller"], "update-ref", "-d", salvage_ref)
    with pytest.raises(RuntimeError, match="Safety check 3 failed"):
        manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)


def test_restore_rejects_wrong_salvage_parent(sh2_repo):
    """LC2 test 6: salvage parent ≠ lease.initial_head → fail closed."""
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)
    controller = sh2_repo["controller"]
    # Create a new commit that is not the original base
    (controller / "extra.txt").write_text("extra\n", encoding="utf-8")
    _git(controller, "add", "extra.txt")
    _git(controller, "commit", "-m", "extra commit")
    extra_sha = _git(controller, "rev-parse", "HEAD")
    # Create a salvage commit from wrong parent
    branch_ref = f"refs/heads/nexus/task/{contract.task_id}"
    _git(controller, "checkout", branch_ref)
    _git(controller, "reset", "--soft", extra_sha)
    _git(controller, "commit", "-m", "salvage from wrong parent")
    wrong_salvage = _git(controller, "rev-parse", "HEAD")
    _git(controller, "update-ref", branch_ref, wrong_salvage)
    _git(controller, "update-ref", salvage_ref, wrong_salvage)
    with pytest.raises(RuntimeError, match="Safety check 5 failed"):
        manager.restore_task_branch_for_retry(contract, lease, wrong_salvage, salvage_ref)


def test_restore_rejects_registered_target_lc2(sh2_repo):
    """LC2 test 7: Target still registered → fail closed."""
    contract = _contract(sh2_repo, task_id="reg-target-lc2")
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]))
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "src" / "allowed.txt").write_text("salvaged\n", encoding="utf-8")
    _git(target, "add", "src/allowed.txt")
    _git(target, "commit", "-m", "salvage commit")
    salvage_commit = _git(target, "rev-parse", "HEAD")
    salvage_ref = f"refs/nexus-salvage/worktree/{contract.task_id}-attempt-1"
    _git(sh2_repo["controller"], "update-ref", salvage_ref, salvage_commit)
    # Do NOT cleanup — target is still registered
    with pytest.raises(RuntimeError, match="Safety check 6 failed"):
        manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)


def test_restore_rejects_candidate_binding(sh2_repo):
    """LC2 test 8: candidate binding exists → fail closed."""
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)
    _git(sh2_repo["controller"], "update-ref",
         f"refs/nexus-candidates/{contract.task_id}/c1", salvage_commit)
    with pytest.raises(RuntimeError, match="Safety check 7 failed"):
        manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)


def test_restore_cas_uses_salvage_commit_as_old_value(sh2_repo):
    """LC2 test 9: CAS uses salvage_commit as old-value guard."""
    contract, manager, lease, salvage_commit, salvage_ref = _setup_salvage_scenario(sh2_repo)
    branch_ref = f"refs/heads/nexus/task/{contract.task_id}"
    # Tamper branch to a third SHA (not salvage_commit, not initial_head)
    unrelated = _git(sh2_repo["controller"], "rev-parse", "HEAD")
    _git(sh2_repo["controller"], "update-ref", branch_ref, unrelated)
    with pytest.raises(RuntimeError, match="Safety check 2 failed"):
        manager.restore_task_branch_for_retry(contract, lease, salvage_commit, salvage_ref)
    # Branch is NOT at initial_head — tamper survived
    assert _git(sh2_repo["controller"], "rev-parse", branch_ref) != lease.initial_head


def test_restore_rejects_refreshed_contract_with_stale_lease(sh2_repo):
    """LC2 test 10: refreshed contract cannot use stale lease → identity mismatch."""
    original = _contract(sh2_repo)
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]))
    lease = manager.create_lease(original)
    target = Path(lease.target_worktree)
    (target / "src" / "allowed.txt").write_text("salvaged\n", encoding="utf-8")
    _git(target, "add", "src/allowed.txt")
    _git(target, "commit", "-m", "salvage")
    salvage_commit = _git(target, "rev-parse", "HEAD")
    salvage_ref = f"refs/nexus-salvage/worktree/{original.task_id}-attempt-1"
    _git(sh2_repo["controller"], "update-ref", salvage_ref, salvage_commit)
    assert manager.cleanup_terminal_target(
        original, lease,
        salvage_commit=salvage_commit,
        salvage_ref=salvage_ref,
    ).decision == "REMOVED"

    # Refresh contract to a different revision
    (sh2_repo["controller"] / "new.txt").write_text("new\n", encoding="utf-8")
    _git(sh2_repo["controller"], "add", "new.txt")
    _git(sh2_repo["controller"], "commit", "-m", "new base")
    refreshed_sha = _git(sh2_repo["controller"], "rev-parse", "HEAD")
    refreshed = original.model_copy(update={
        "controller_revision": refreshed_sha,
        "target_base_revision": refreshed_sha,
    })
    # Restore rejects the stale lease (identity mismatch)
    with pytest.raises(RuntimeError, match="contract and lease identity mismatch"):
        manager.restore_task_branch_for_retry(refreshed, lease, salvage_commit, salvage_ref)


# integrity-seal: 1776512137


# ---------------------------------------------------------------------------
# Workspace Convergence & Reusable Slot Tests (Card 02)
# ---------------------------------------------------------------------------

def test_workspace_inventory_and_classification(sh2_repo):
    controller = sh2_repo["controller"]
    target_root = sh2_repo["target_root"]
    manager = WorktreeManager(root_dir=str(target_root))

    # Create one terminal task worktree (clean, reachable)
    contract1 = _contract(sh2_repo, task_id="term-clean")
    lease1 = manager.create_lease(contract1)

    # Create unmapped clean worktree
    unmapped_dir = target_root / "unmapped-clean"
    _git(controller, "worktree", "add", "-b", "nexus/task/unmapped-clean", str(unmapped_dir), sh2_repo["target_base_revision"])

    # Build inventory
    task_states = {
        "term-clean": {
            "task_id": "term-clean",
            "status": "INTEGRATED",
            "lease": lease1.__dict__,
            "contract": contract1.model_dump() if hasattr(contract1, "model_dump") else contract1.__dict__,
        }
    }
    inventory = manager.get_workspace_inventory(controller_root=controller, task_states=task_states)

    assert inventory.schema == "nexus.workspace_inventory.v1"
    assert inventory.controller_root == str(controller.resolve())
    assert len(inventory.inventory_hash) == 64

    class_map = {w.path: w.classification for w in inventory.worktrees}
    assert class_map[str(controller.resolve())] == "KEEP_CONTROLLER"
    assert class_map[str(Path(lease1.target_worktree).resolve())] == "RELEASABLE_TERMINAL_TARGET"
    assert class_map[str(unmapped_dir.resolve())] == "RELEASABLE_REDUNDANT_CLEAN"


def test_dirty_or_unknown_worktree_kept(sh2_repo):
    controller = sh2_repo["controller"]
    target_root = sh2_repo["target_root"]
    manager = WorktreeManager(root_dir=str(target_root))

    contract = _contract(sh2_repo, task_id="term-dirty")
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "src" / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")

    task_states = {
        "term-dirty": {
            "task_id": "term-dirty",
            "status": "INTEGRATED",
            "lease": lease.__dict__,
            "contract": contract.model_dump() if hasattr(contract, "model_dump") else contract.__dict__,
        }
    }
    inventory = manager.get_workspace_inventory(controller_root=controller, task_states=task_states)

    class_map = {w.path: w.classification for w in inventory.worktrees}
    assert class_map[str(target.resolve())] == "KEEP_DIRTY_OR_UNKNOWN"


def test_active_or_retained_target_kept(sh2_repo):
    controller = sh2_repo["controller"]
    target_root = sh2_repo["target_root"]
    manager = WorktreeManager(root_dir=str(target_root))

    contract = _contract(sh2_repo, task_id="task-active")
    lease = manager.create_lease(contract)

    task_states = {
        "task-active": {
            "task_id": "task-active",
            "status": "RUNNING",
            "lease": lease.__dict__,
            "contract": contract.model_dump() if hasattr(contract, "model_dump") else contract.__dict__,
        }
    }
    inventory = manager.get_workspace_inventory(controller_root=controller, task_states=task_states)

    class_map = {w.path: w.classification for w in inventory.worktrees}
    assert class_map[str(Path(lease.target_worktree).resolve())] == "KEEP_ACTIVE_OR_RETAINED"


def test_direct_completion_audit_blocks_active_target(sh2_repo):
    controller = sh2_repo["controller"]
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]))
    contract = _contract(sh2_repo, task_id="direct-active")
    lease = manager.create_lease(contract)
    task_states = {
        "direct-active": {
            "task_id": "direct-active",
            "status": "RUNNING",
            "lease": lease.__dict__,
            "contract": contract.model_dump() if hasattr(contract, "model_dump") else contract.__dict__,
        }
    }

    audit = manager.audit_direct_completion(
        controller_root=controller,
        expected_head=_git(controller, "rev-parse", "HEAD"),
        expected_branch="main",
        allowed_files=["src/allowed.txt"],
        task_states=task_states,
    )

    assert any(blocker.startswith("active_target:") for blocker in audit["blockers"])


def test_direct_completion_audit_blocks_dirty_managed_overlap(sh2_repo):
    controller = sh2_repo["controller"]
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]))
    contract = _contract(sh2_repo, task_id="direct-dirty", allowed_files=["src/"])
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "src" / "allowed.txt").write_text("dirty\n", encoding="utf-8")
    task_states = {
        "direct-dirty": {
            "task_id": "direct-dirty",
            "status": "INTEGRATED",
            "lease": lease.__dict__,
            "contract": contract.model_dump() if hasattr(contract, "model_dump") else contract.__dict__,
        }
    }

    audit = manager.audit_direct_completion(
        controller_root=controller,
        expected_head=_git(controller, "rev-parse", "HEAD"),
        expected_branch="main",
        allowed_files=["src/"],
        task_states=task_states,
    )

    assert any(blocker.startswith("dirty_allowed_overlap:") for blocker in audit["blockers"]), audit


def test_unique_commit_without_protection_is_blocked(sh2_repo):
    controller = sh2_repo["controller"]
    target_root = sh2_repo["target_root"]
    manager = WorktreeManager(root_dir=str(target_root))

    target = target_root / "unprotected-unique"
    _git(controller, "worktree", "add", "--detach", str(target), _git(controller, "rev-parse", "HEAD"))
    (target / "src" / "allowed.txt").write_text("unique content\n", encoding="utf-8")
    _git(target, "add", "src/allowed.txt")
    _git(target, "commit", "-m", "unprotected unique commit")

    task_states = {
        "unprotected-unique": {
            "task_id": "unprotected-unique",
            "status": "SUPERSEDED",
            "lease": {},
            "contract": {},
        }
    }
    inventory = manager.get_workspace_inventory(controller_root=controller, task_states=task_states)
    plan = manager.plan_convergence(inventory)

    assert str(target.resolve()) in plan.groups["BLOCKED_UNPROTECTED_UNIQUE_COMMIT"]
    assert str(target.resolve()) not in plan.releasable_paths


def test_inventory_exposes_deterministic_disposition_evidence(sh2_repo):
    controller = sh2_repo["controller"]
    target_root = sh2_repo["target_root"]
    manager = WorktreeManager(root_dir=str(target_root), process_checker=lambda _path: False)
    passive = target_root / "passive-evidence"
    _git(controller, "worktree", "add", "--detach", str(passive), _git(controller, "rev-parse", "HEAD"))

    first = manager.get_workspace_inventory(controller_root=controller)
    second = manager.get_workspace_inventory(controller_root=controller)
    assert first.inventory_hash == second.inventory_hash
    entry = next(item for item in first.worktrees if item.path == str(passive.resolve()))
    assert entry.disposition == "RELEASABLE_REDUNDANT_CLEAN"
    assert entry.process_active is False
    assert entry.lock_present is False
    assert entry.unique_commits == ()


def test_active_process_is_fail_closed_in_direct_audit(sh2_repo):
    controller = sh2_repo["controller"]
    target_root = sh2_repo["target_root"]
    manager = WorktreeManager(root_dir=str(target_root), process_checker=lambda _path: True)
    passive = target_root / "active-evidence"
    _git(controller, "worktree", "add", "--detach", str(passive), _git(controller, "rev-parse", "HEAD"))

    audit = manager.audit_direct_completion(
        controller_root=controller,
        expected_head=_git(controller, "rev-parse", "HEAD"),
        expected_branch="main",
        task_states={},
    )
    record = next(item for item in audit["aux_records"] if item["path"] == str(passive.resolve()))
    assert record["process_active"] is True
    assert "active_or_locked_worktree" in record["blockers"]
    plan = manager.plan_convergence(manager.get_workspace_inventory(controller_root=controller))
    assert str(passive.resolve()) in plan.blocked_paths
    assert str(passive.resolve()) not in plan.releasable_paths


def test_process_evidence_unavailable_is_surfaced_and_blocked(sh2_repo):
    controller = sh2_repo["controller"]
    target_root = sh2_repo["target_root"]
    manager = WorktreeManager(root_dir=str(target_root), process_checker=lambda _path: None)
    passive = target_root / "unknown-process-evidence"
    _git(controller, "worktree", "add", "--detach", str(passive), _git(controller, "rev-parse", "HEAD"))
    inventory = manager.get_workspace_inventory(controller_root=controller)
    entry = next(item for item in inventory.worktrees if item.path == str(passive.resolve()))
    assert entry.process_evidence_unavailable is True
    assert entry.disposition == "OWNER_DECISION_REQUIRED"
    audit = manager.audit_direct_completion(
        controller_root=controller,
        expected_head=_git(controller, "rev-parse", "HEAD"),
        expected_branch="main",
        task_states={},
    )
    assert any(item.startswith("process_evidence_unavailable:") for item in audit["blockers"])


def test_inventory_skips_process_probe_for_controller(sh2_repo):
    controller = sh2_repo["controller"]
    target_root = sh2_repo["target_root"]
    probed = []
    manager = WorktreeManager(root_dir=str(target_root), process_checker=lambda path: probed.append(path) or False)
    passive = target_root / "probe-aux"
    _git(controller, "worktree", "add", "--detach", str(passive), _git(controller, "rev-parse", "HEAD"))
    manager.get_workspace_inventory(controller_root=controller)
    assert controller.resolve() not in probed
    assert passive.resolve() in probed


def test_unique_commit_with_protected_branch_is_retained(sh2_repo):
    controller = sh2_repo["controller"]
    target_root = sh2_repo["target_root"]
    manager = WorktreeManager(root_dir=str(target_root), process_checker=lambda _path: False)
    passive = target_root / "protected-unique"
    _git(controller, "worktree", "add", "-b", "codex/protected-unique", str(passive), _git(controller, "rev-parse", "HEAD"))
    (passive / "protected.txt").write_text("protected\n", encoding="utf-8")
    _git(passive, "add", "protected.txt")
    _git(passive, "commit", "-m", "protected unique")
    inventory = manager.get_workspace_inventory(controller_root=controller)
    entry = next(item for item in inventory.worktrees if item.path == str(passive.resolve()))
    assert entry.branch_protected is True
    assert entry.disposition == "FORENSIC_RETAIN"
    plan = manager.plan_convergence(inventory)
    assert str(passive.resolve()) not in plan.releasable_paths


def test_lsof_error_is_unavailable_not_clean(monkeypatch, tmp_path):
    class Result:
        returncode = 1
        stdout = ""
        stderr = "lsof: permission denied"

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Result())
    with pytest.raises(RuntimeError, match="process probe unavailable"):
        WorktreeManager._path_has_process(tmp_path)


def test_clean_redundant_terminal_classified_releasable_without_removal(sh2_repo):
    controller = sh2_repo["controller"]
    target_root = sh2_repo["target_root"]
    manager = WorktreeManager(root_dir=str(target_root))

    contract = _contract(sh2_repo, task_id="term-releasable")
    lease = manager.create_lease(contract)

    task_states = {
        "term-releasable": {
            "task_id": "term-releasable",
            "status": "INTEGRATED",
            "lease": lease.__dict__,
            "contract": contract.model_dump() if hasattr(contract, "model_dump") else contract.__dict__,
        }
    }
    inventory = manager.get_workspace_inventory(controller_root=controller, task_states=task_states)
    plan = manager.plan_convergence(inventory)

    target_path = Path(lease.target_worktree).resolve()
    assert str(target_path) in plan.releasable_paths
    # Verify worktree is classified releasable without being removed on disk
    assert target_path.exists()


def test_convergence_plan_and_apply(sh2_repo):
    controller = sh2_repo["controller"]
    target_root = sh2_repo["target_root"]
    manager = WorktreeManager(root_dir=str(target_root))

    contract = _contract(sh2_repo, task_id="releasable-1")
    lease = manager.create_lease(contract)

    task_states = {
        "releasable-1": {
            "task_id": "releasable-1",
            "status": "INTEGRATED",
            "lease": lease.__dict__,
            "contract": contract.model_dump() if hasattr(contract, "model_dump") else contract.__dict__,
        }
    }
    inventory = manager.get_workspace_inventory(controller_root=controller, task_states=task_states)
    plan = manager.plan_convergence(inventory, expected_controller_revision=sh2_repo["controller_revision"])

    assert plan.schema == "nexus.workspace_convergence_plan.v1"
    assert str(Path(lease.target_worktree).resolve()) in plan.releasable_paths
    assert plan.deletion_count == 1
    assert plan.next_allowed_gate == "INDEPENDENT_CANDIDATE_REVIEW"

    # Test apply seam on temporary repository fixture
    receipt = manager.apply_convergence_plan(
        plan,
        expected_controller_revision=sh2_repo["controller_revision"],
        expected_plan_hash=plan.plan_hash,
    )
    assert receipt.applied is True
    assert str(Path(lease.target_worktree).resolve()) in receipt.released_paths
    assert not Path(lease.target_worktree).exists()


def test_controller_revision_drift_invalidates_plan(sh2_repo):
    controller = sh2_repo["controller"]
    target_root = sh2_repo["target_root"]
    manager = WorktreeManager(root_dir=str(target_root))

    inventory = manager.get_workspace_inventory(controller_root=controller)
    plan = manager.plan_convergence(inventory, expected_controller_revision=sh2_repo["controller_revision"])

    with pytest.raises(RuntimeError, match="CONTROLLER_REVISION_DRIFT"):
        manager.apply_convergence_plan(
            plan,
            expected_controller_revision="wrong_sha_1234567890123456789012345678901234567890",
            expected_plan_hash=plan.plan_hash,
        )


def test_dirty_reusable_slot_fails_closed(sh2_repo):
    controller = sh2_repo["controller"]
    target_root = sh2_repo["target_root"]
    manager = WorktreeManager(root_dir=str(target_root))

    contract = _contract(sh2_repo, task_id="slot-task-dirty")
    slot_lease = manager.prepare_reusable_slot(
        contract,
        campaign_id="campaign-dirty",
        slot_index=0,
    )
    slot_path = Path(slot_lease.slot_path)
    (slot_path / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    contract2 = _contract(sh2_repo, task_id="slot-task-next")
    blocked_lease = manager.prepare_reusable_slot(
        contract2,
        campaign_id="campaign-dirty",
        slot_index=0,
    )

    assert blocked_lease.status == "BLOCKED"
    assert "BLOCKED_DIRTY_SLOT" in (blocked_lease.blocker or "")
    assert (slot_path / "dirty.txt").exists()


def test_reusable_slot_preparation_and_idempotency(sh2_repo):
    controller = sh2_repo["controller"]
    target_root = sh2_repo["target_root"]
    manager = WorktreeManager(root_dir=str(target_root))

    contract = _contract(sh2_repo, task_id="slot-task-1")
    slot_lease = manager.prepare_reusable_slot(
        contract,
        campaign_id="campaign-test",
        slot_index=0,
    )

    assert slot_lease.status == "READY"
    assert "slot-0" in slot_lease.slot_path

    # Second preparation with exact same contract is idempotent
    second_lease = manager.prepare_reusable_slot(
        contract,
        campaign_id="campaign-test",
        slot_index=0,
    )
    assert second_lease.status == "READY"
    assert second_lease.slot_path == slot_lease.slot_path


def test_reusable_slot_is_one_physical_serial_slot_across_campaigns(sh2_repo):
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]))
    first = manager.prepare_reusable_slot(_contract(sh2_repo, task_id="slot-shared-1"), campaign_id="campaign-one", slot_index=0)
    second = manager.get_reusable_slot_status(
        campaign_id="campaign-two",
        slot_index=0,
        controller_root=sh2_repo["controller"],
        task_states={},
    )

    assert first.slot_path == second.slot_path
    assert "/serial-slot/slot-0" in first.slot_path


def test_different_base_slot_reuse_blocks_until_verified_release(sh2_repo):
    controller = sh2_repo["controller"]
    target_root = sh2_repo["target_root"]
    manager = WorktreeManager(root_dir=str(target_root))

    contract1 = _contract(sh2_repo, task_id="slot-task-base1")
    slot_lease1 = manager.prepare_reusable_slot(
        contract1,
        campaign_id="campaign-diffbase",
        slot_index=0,
    )
    slot_path = Path(slot_lease1.slot_path)

    # Commit an unprotected unique commit to slot
    (slot_path / "src" / "allowed.txt").write_text("unique work in slot\n", encoding="utf-8")
    _git(slot_path, "add", "src/allowed.txt")
    _git(slot_path, "commit", "-m", "unprotected slot commit")

    # Create new base commit on controller
    (controller / "new_base.txt").write_text("new base\n", encoding="utf-8")
    _git(controller, "add", "new_base.txt")
    _git(controller, "commit", "-m", "controller new base")
    new_base_sha = _git(controller, "rev-parse", "HEAD")

    contract2 = _contract(sh2_repo, task_id="slot-task-base2")
    contract2 = contract2.model_copy(update={
        "controller_revision": new_base_sha,
        "target_base_revision": new_base_sha,
    })

    # Prepare reusable slot with different base: must block because slot has unprotected unique commit
    blocked_lease = manager.prepare_reusable_slot(
        contract2,
        campaign_id="campaign-diffbase",
        slot_index=0,
    )
    assert blocked_lease.status == "BLOCKED"
    assert "BLOCKED_UNPROTECTED_UNIQUE_COMMIT" in (blocked_lease.blocker or "")


# ---------------------------------------------------------------------------
# Physical Ownership Record Lifecycle & Safety Tests
# ---------------------------------------------------------------------------

def test_cleanup_terminal_target_successful_exact_release_removes_ownership_record(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo, task_id="owner-release")
    controller = Path(contract.controller_repo_root).resolve()
    record_path = manager._ownership_record_path(controller, contract.task_id)

    assert target.exists()
    assert record_path.exists()

    receipt = manager.cleanup_terminal_target(contract, lease)
    assert receipt.decision == "REMOVED"
    assert receipt.performed is True
    assert not target.exists()
    assert not record_path.exists()

    # Idempotent second cleanup call
    second = manager.cleanup_terminal_target(contract, lease)
    assert second.decision == "ALREADY_REMOVED"
    assert not record_path.exists()


def test_cleanup_terminal_target_failed_release_preserves_ownership_record(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo, task_id="owner-failed")
    controller = Path(contract.controller_repo_root).resolve()
    record_path = manager._ownership_record_path(controller, contract.task_id)
    (target / "src" / "allowed.txt").write_text("uncommitted dirty\n", encoding="utf-8")

    receipt = manager.cleanup_terminal_target(contract, lease)
    assert receipt.decision == "BLOCKED_BY_UNSAVED_CHANGES"
    assert receipt.performed is False
    assert target.exists()
    assert record_path.exists()


def test_cleanup_terminal_target_process_blocked_preserves_ownership_record(sh2_repo):
    contract = _contract(sh2_repo, task_id="owner-process")
    manager = WorktreeManager(root_dir=str(sh2_repo["target_root"]), process_checker=lambda _: True)
    lease = manager.create_lease(contract)
    controller = Path(contract.controller_repo_root).resolve()
    record_path = manager._ownership_record_path(controller, contract.task_id)

    receipt = manager.cleanup_terminal_target(contract, lease)
    assert receipt.decision == "BLOCKED_BY_PROCESS"
    assert receipt.performed is False
    assert record_path.exists()


def test_cleanup_terminal_target_rejects_symlink_or_non_regular_ownership_record(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo, task_id="owner-symlink")
    controller = Path(contract.controller_repo_root).resolve()
    record_path = manager._ownership_record_path(controller, contract.task_id)

    # Replace ownership record with a symlink to outside file
    outside = controller / "outside.txt"
    record_path.unlink()
    record_path.symlink_to(outside)

    receipt = manager.cleanup_terminal_target(contract, lease)
    assert receipt.decision == "BLOCKED_BY_UNSAVED_CHANGES"
    assert "not a regular file" in (receipt.blocker or "")
    assert target.exists()


def test_cleanup_terminal_target_rejects_tampered_integrity_ownership_record(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo, task_id="owner-tamper")
    controller = Path(contract.controller_repo_root).resolve()
    record_path = manager._ownership_record_path(controller, contract.task_id)

    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["integrity_sha256"] = "0" * 64
    record_path.write_text(json.dumps(record), encoding="utf-8")

    receipt = manager.cleanup_terminal_target(contract, lease)
    assert receipt.decision == "BLOCKED_BY_UNSAVED_CHANGES"
    assert "integrity is invalid" in (receipt.blocker or "")
    assert target.exists()


def test_cleanup_terminal_target_rejects_mismatched_lease_binding(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo, task_id="owner-mismatch")
    controller = Path(contract.controller_repo_root).resolve()
    record_path = manager._ownership_record_path(controller, contract.task_id)

    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["lease_id"] = "different-lease-id"
    record["attempt_id"] = "different-lease-id"
    record["expected_lease_id"] = "different-lease-id"
    record["expected_attempt_id"] = "different-lease-id"
    record["integrity_sha256"] = manager._ownership_digest(record)
    record_path.write_text(json.dumps(record), encoding="utf-8")

    receipt = manager.cleanup_terminal_target(contract, lease)
    assert receipt.decision == "BLOCKED_BY_UNSAVED_CHANGES"
    assert "identity binding mismatch" in (receipt.blocker or "")
    assert target.exists()


def test_cleanup_terminal_target_dry_run_preserves_worktree_and_ownership_record(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo, task_id="owner-dryrun")
    controller = Path(contract.controller_repo_root).resolve()
    record_path = manager._ownership_record_path(controller, contract.task_id)

    receipt = manager.cleanup_terminal_target(contract, lease, dry_run=True)
    assert receipt.decision == "REMOVED"
    assert receipt.performed is False
    assert receipt.eligible is True
    assert target.exists()
    assert record_path.exists()


def test_cleanup_terminal_target_with_salvage_removes_ownership_record(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo, task_id="owner-salvage")
    controller = Path(contract.controller_repo_root).resolve()
    record_path = manager._ownership_record_path(controller, contract.task_id)

    (target / "src" / "allowed.txt").write_text("salvaged\n", encoding="utf-8")
    _git(target, "add", "src/allowed.txt")
    _git(target, "commit", "-m", "salvage commit")
    salvage_sha = _git(target, "rev-parse", "HEAD")
    salvage_ref = manager.salvage_ref_for(contract.task_id, "attempt-1")
    _git(controller, "update-ref", salvage_ref, salvage_sha)

    receipt = manager.cleanup_terminal_target(
        contract,
        lease,
        salvage_commit=salvage_sha,
        salvage_ref=salvage_ref,
    )
    assert receipt.decision == "REMOVED"
    assert receipt.performed is True
    assert not target.exists()
    assert not record_path.exists()


def test_cleanup_terminal_target_with_candidate_removes_ownership_record(sh2_repo):
    contract, manager, lease, target = _prepare_candidate(sh2_repo, task_id="owner-candidate")
    controller = Path(contract.controller_repo_root).resolve()
    record_path = manager._ownership_record_path(controller, contract.task_id)

    (target / "src" / "allowed.txt").write_text("candidate\n", encoding="utf-8")
    _git(target, "add", "src/allowed.txt")
    _git(target, "commit", "-m", "candidate commit")
    candidate_sha = _git(target, "rev-parse", "HEAD")
    candidate_ref = manager.protect_candidate(contract, lease, candidate_sha)

    receipt = manager.cleanup_terminal_target(
        contract,
        lease,
        candidate_commit=candidate_sha,
        candidate_ref=candidate_ref,
    )
    assert receipt.decision == "REMOVED"
    assert receipt.performed is True
    assert not target.exists()
    assert not record_path.exists()


def test_cleanup_terminal_target_cas_swap_race_preserves_record(sh2_repo, monkeypatch):
    contract, manager, lease, target = _prepare_candidate(sh2_repo, task_id="owner-cas-swap")
    controller = Path(contract.controller_repo_root).resolve()
    record_path = manager._ownership_record_path(controller, contract.task_id)

    orig_run_git = manager._run_git

    def swapped_run_git(args, **kwargs):
        res = orig_run_git(args, **kwargs)
        if args and args[0] == "worktree" and args[1] == "remove":
            # Simulate a swap race: unlink and recreate a new file with different content/inode
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["lease_id"] = "swapped-lease-id"
            record["integrity_sha256"] = manager._ownership_digest(record)
            record_path.unlink()
            record_path.write_text(json.dumps(record), encoding="utf-8")
        return res

    monkeypatch.setattr(manager, "_run_git", swapped_run_git)

    receipt = manager.cleanup_terminal_target(contract, lease)
    assert receipt.decision == "BLOCKED_BY_UNSAVED_CHANGES"
    assert "ownership record" in (receipt.blocker or "")
    # The swapped record must be preserved
    assert record_path.exists()
