from dataclasses import asdict
import json
import subprocess
from pathlib import Path

import pytest

from nexus.orchestrator.candidate_commit import CandidateCommitter
from nexus.orchestrator.candidate_verifier import CandidateVerifier
from nexus.orchestrator.self_hosted_controller import SelfHostedDevelopmentController
from nexus.orchestrator.task_contract import MutationMode, SelfHostedTaskContract
from nexus.orchestrator.worktree_manager import WorktreeManager


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _scenario(tmp_path: Path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    controller_root.mkdir()
    target_root.mkdir()
    _git(controller_root, "init")
    _git(controller_root, "config", "user.email", "commit@example.test")
    _git(controller_root, "config", "user.name", "Commit Test")
    (controller_root / "bounded.txt").write_text("base\n", encoding="utf-8")
    _git(controller_root, "add", "bounded.txt")
    _git(controller_root, "commit", "-m", "base")
    target_sha = _git(controller_root, "rev-parse", "HEAD")
    _git(controller_root, "commit", "--allow-empty", "-m", "controller")
    controller_sha = _git(controller_root, "rev-parse", "HEAD")
    contract = SelfHostedTaskContract(
        task_id="candidate-commit",
        objective="Create one isolated candidate commit",
        controller_revision=controller_sha,
        target_base_revision=target_sha,
        controller_repo_root=str(controller_root),
        target_repo_root=str(target_root / "candidate-commit"),
        target_worktree_root=str(target_root),
        allowed_files=["bounded.txt"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
        protected_contracts=["candidate-receipt-v1"],
        preferred_provider="codex",
        maximum_provider_calls=1,
        mutation_mode=MutationMode.WORKING_TREE_ONLY,
        human_approval_required=True,
    )
    manager = WorktreeManager(str(target_root))
    controller = SelfHostedDevelopmentController(manager)
    lease = controller.prepare_task(contract)
    Path(lease.target_worktree, "bounded.txt").write_text("candidate\n", encoding="utf-8")
    candidate = controller.collect_candidate(contract, lease)
    verified = CandidateVerifier(manager).verify(contract, lease, candidate)
    return contract, lease, verified, manager


def test_candidate_commit_is_automatic_but_promotion_pending(tmp_path):
    contract, lease, verified, manager = _scenario(tmp_path)

    packet = CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)

    assert packet.candidate_commit_created is True
    assert packet.promotion_status == "PENDING_HUMAN_APPROVAL"
    assert packet.merge_performed is False
    assert packet.push_performed is False
    assert len(packet.candidate_commit_sha) == 40
    assert len(packet.candidate_tree_sha) == 40
    assert packet.verified_receipt_hash
    assert _git(Path(lease.target_worktree), "status", "--short") == ""
    assert _git(Path(lease.target_worktree), "rev-parse", "HEAD") == packet.candidate_commit_sha
    changed = _git(Path(lease.target_worktree), "diff-tree", "--no-commit-id", "--name-only", "-r", packet.candidate_commit_sha)
    assert changed.splitlines() == ["bounded.txt"]


def test_candidate_commit_rejects_unverified_receipt(tmp_path):
    contract, lease, verified, manager = _scenario(tmp_path)
    object.__setattr__(verified, "verified", False)

    with pytest.raises(RuntimeError, match="Verified Candidate Receipt"):
        CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)
