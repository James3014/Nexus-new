import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.contracts.target_integration_lifecycle import (
    CleanupDecision,
    ExternalAcceptanceReceipt,
    IntegrationAuthorizationEnvelope,
)
from nexus.orchestrator.target_integration_lifecycle import TargetIntegrationLifecycle


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


def status_hash(root: Path) -> str:
    return hashlib.sha256(git(root, "status", "--porcelain=v1", "--untracked-files=all").encode()).hexdigest()


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
    git(root, "checkout", "-b", "nexus/integration/canary")
    return root, base, candidate


def acceptance(candidate: str) -> ExternalAcceptanceReceipt:
    return ExternalAcceptanceReceipt(
        schema="nexus.external_acceptance_receipt.v1", task_id="task-1",
        attempt_id="attempt-1", candidate_commit=candidate, receipt_hash="b" * 64,
        reviewer_id="reviewer-1", passed=True, verifier_artifact="artifact-1",
    )


def authorization(root: Path, base: str, candidate: str, receipt: ExternalAcceptanceReceipt) -> IntegrationAuthorizationEnvelope:
    return IntegrationAuthorizationEnvelope(
        schema="nexus.integration_authorization.v1", task_id="task-1",
        campaign_id="campaign", attempt_id="attempt-1", task_card_hash="c" * 64,
        candidate_commit=candidate, candidate_tree_sha=git(root, "rev-parse", f"{candidate}^{{tree}}"),
        candidate_state_hash="d" * 64, candidate_receipt_hash="e" * 64,
        acceptance_receipt_hash=receipt.receipt_hash, reviewer_id=receipt.reviewer_id,
        verifier_artifact_hash="f" * 64, canonical_root=str(root.resolve()),
        canonical_branch="nexus/integration/canary", expected_canonical_head=base,
        canonical_dirty_baseline=status_hash(root), integration_plan_hash="1" * 64,
        strategy="EPHEMERAL_WORKTREE_MERGE_THEN_APPLY", verification_commands_hash="2" * 64,
        post_apply_commands_hash="3" * 64, cleanup_target_id="target-1",
        cleanup_target_path=str(root / "target"), durable_ref="refs/nexus-candidate/task-1",
        rollback="retain target", cleanup_requested=True,
        action_set=("ACCEPT_DISPOSITION", "INTEGRATION_STAGING", "APPLY_VERIFIED_INTEGRATION", "POST_INTEGRATION_VERIFY", "CLEANUP_OWNED_TARGET"),
        issued_at="2026-08-02T00:00:00+00:00",
    )


def test_real_git_staging_failure_and_success_do_not_fake_ancestry(tmp_path: Path):
    root, base, candidate = make_repo(tmp_path)
    receipt = acceptance(candidate)
    auth = authorization(root, base, candidate, receipt)
    with pytest.raises(RuntimeError, match="staging verifier failed"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=base, expected_status_hash=status_hash(root),
            staging_root=str(tmp_path / "failed-stage"),
            verifier_commands=((sys.executable, "-c", "raise SystemExit(1)"),),
            external_acceptance=receipt, authorization=auth,
        )
    assert git(root, "rev-parse", "HEAD") == base
    assert not (tmp_path / "failed-stage" / "task-1").exists()

    staged = TargetIntegrationLifecycle.transactional_integration(
        task_id="task-1", canonical_root=root, candidate_commit=candidate,
        expected_canonical_head=base, expected_status_hash=status_hash(root),
        staging_root=str(tmp_path / "good-stage"),
        verifier_commands=((sys.executable, "-c", "raise SystemExit(0)"),),
        external_acceptance=receipt, authorization=auth,
    )
    assert staged.staged is True
    assert staged.applied is False
    assert git(root, "rev-parse", "HEAD") == base


def test_real_git_canary_detects_canonical_drift_and_applies_verified_result(tmp_path: Path):
    root, base, candidate = make_repo(tmp_path)
    receipt = acceptance(candidate)
    auth = authorization(root, base, candidate, receipt)
    (root / "unrelated.txt").write_text("dirty\n")
    with pytest.raises(RuntimeError, match="canonical.*clean"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=base, expected_status_hash=status_hash(root),
            staging_root=str(tmp_path / "drift-stage"), apply=True,
            external_acceptance=receipt, authorization=auth,
        )
    (root / "unrelated.txt").unlink()
    applied = TargetIntegrationLifecycle.transactional_integration(
        task_id="task-1", canonical_root=root, candidate_commit=candidate,
        expected_canonical_head=base, expected_status_hash=status_hash(root),
        staging_root=str(tmp_path / "apply-stage"), apply=True,
        external_acceptance=receipt, authorization=auth,
    )
    assert applied.applied is True
    assert git(root, "rev-parse", "HEAD") == applied.integration_commit
    assert git(root, "merge-base", "--is-ancestor", candidate, git(root, "rev-parse", "HEAD")) == ""


def test_real_git_conflict_and_forged_cleanup_are_fail_closed(tmp_path: Path):
    root, base, candidate = make_repo(tmp_path)
    (root / "value.txt").write_text("canonical-conflict\n")
    git(root, "commit", "-am", "canonical conflicting change")
    drifted_head = git(root, "rev-parse", "HEAD")
    receipt = acceptance(candidate)
    auth = authorization(root, drifted_head, candidate, receipt)
    with pytest.raises(RuntimeError, match="git merge"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=drifted_head, expected_status_hash=status_hash(root),
            staging_root=str(tmp_path / "conflict-stage"), apply=True,
            external_acceptance=receipt, authorization=auth,
        )
    assert git(root, "rev-parse", "HEAD") == drifted_head

    target = tmp_path / "owned-target"
    git(root, "worktree", "add", "--detach", str(target), drifted_head)
    forged = CleanupDecision(
        schema="nexus.target_cleanup_decision.v1", decision="ELIGIBLE",
        task_id="task-1", target_id="target-1",
    )
    result = TargetIntegrationLifecycle.cleanup_target(
        decision=forged, target_path=target, canonical_root=root, apply=True,
    )
    assert result["performed"] is False
    assert target.exists()
