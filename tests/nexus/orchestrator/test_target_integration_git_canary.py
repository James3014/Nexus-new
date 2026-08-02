import subprocess
import sys
from pathlib import Path

import pytest

from nexus.orchestrator.target_integration_lifecycle import TargetIntegrationLifecycle


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


def make_repo(tmp_path: Path) -> tuple[Path, str, str]:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "canary")
    git(root, "config", "user.email", "canary@example.invalid")
    (root / "value.txt").write_text("base\n")
    git(root, "add", "value.txt")
    git(root, "commit", "-m", "base")
    base = git(root, "rev-parse", "HEAD")
    git(root, "branch", "candidate")
    git(root, "checkout", "candidate")
    (root / "value.txt").write_text("candidate\n")
    git(root, "commit", "-am", "candidate")
    candidate = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "main")
    return root, base, candidate


def test_real_git_staging_failure_and_success_do_not_fake_ancestry(tmp_path: Path):
    root, base, candidate = make_repo(tmp_path)
    status_hash = TargetIntegrationLifecycle.git_status_hash(root)
    with pytest.raises(RuntimeError, match="staging verifier failed"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=base, expected_status_hash=status_hash,
            staging_root=tmp_path / "failed-stage",
            verifier_commands=((sys.executable, "-c", "raise SystemExit(1)"),),
        )
    assert git(root, "rev-parse", "HEAD") == base
    assert not (tmp_path / "failed-stage").exists()

    receipt = TargetIntegrationLifecycle.transactional_integration(
        task_id="task-1", canonical_root=root, candidate_commit=candidate,
        expected_canonical_head=base, expected_status_hash=status_hash,
        staging_root=tmp_path / "good-stage",
        verifier_commands=((sys.executable, "-c", "raise SystemExit(0)"),),
    )
    assert receipt.staged is True
    assert receipt.applied is False
    assert git(root, "rev-parse", "HEAD") == base
    assert not (tmp_path / "good-stage").exists()


def test_real_git_canary_detects_canonical_drift_and_applies_verified_result(tmp_path: Path):
    root, base, candidate = make_repo(tmp_path)
    expected = TargetIntegrationLifecycle.git_status_hash(root)
    (root / "unrelated.txt").write_text("dirty\n")
    with pytest.raises(RuntimeError, match="dirty state drift"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=base, expected_status_hash=expected,
            staging_root=tmp_path / "drift-stage",
        )
    (root / "unrelated.txt").unlink()
    receipt = TargetIntegrationLifecycle.transactional_integration(
        task_id="task-1", canonical_root=root, candidate_commit=candidate,
        expected_canonical_head=base, expected_status_hash=expected,
        staging_root=tmp_path / "apply-stage", apply=True,
    )
    assert receipt.applied is True
    assert git(root, "merge-base", "--is-ancestor", candidate, git(root, "rev-parse", "HEAD")) == ""


def test_real_git_conflict_and_owned_cleanup_are_fail_closed(tmp_path: Path):
    root, base, candidate = make_repo(tmp_path)
    git(root, "checkout", "main")
    (root / "value.txt").write_text("canonical-conflict\n")
    git(root, "commit", "-am", "canonical conflicting change")
    drifted_head = git(root, "rev-parse", "HEAD")
    with pytest.raises(RuntimeError, match="git merge"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=drifted_head,
            expected_status_hash=TargetIntegrationLifecycle.git_status_hash(root),
            staging_root=tmp_path / "conflict-stage",
        )
    assert git(root, "rev-parse", "HEAD") == drifted_head

    target = tmp_path / "owned-target"
    git(root, "worktree", "add", "--detach", str(target), drifted_head)
    decision = TargetIntegrationLifecycle.cleanup_decision(
        task_id="task-1", target_id="target-1", target_owner="task-1",
        target_is_canonical=False, reviewer_worktree=False, dirty=False,
        untracked=False, active_process=False, accepted=True, integrated=True,
        canonical_contains_result=True, durable_ref_verified=True,
        receipts_complete=True, unique_unprotected_commits=False,
    )
    result = TargetIntegrationLifecycle.cleanup_target(
        decision=decision, target_path=target, canonical_root=root, apply=True,
    )
    assert result["performed"] is True
    assert not target.exists()
