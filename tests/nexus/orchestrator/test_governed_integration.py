import subprocess
from pathlib import Path

import pytest

from nexus.orchestrator.governed_integration import ControlledIntegrationManager


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _candidate_state(repo: Path, base: str, candidate: str, tree: str):
    return {
        "task_id": "integration-task",
        "status": "CANDIDATE_COMMITTED",
        "contract": {
            "task_id": "integration-task",
            "controller_repo_root": str(repo),
            "target_base_revision": base,
            "verifier_commands": ["python3 -c 'print(\"integration-pass\")'"],
        },
        "lease": {"target_branch": "nexus/task/integration-task"},
        "promotion_packet": {
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "candidate_commit_sha": candidate,
            "candidate_tree_sha": tree,
            "candidate_state_hash": "a" * 64,
            "verified_receipt_hash": "b" * 64,
        },
        "promotion_status": "APPROVED",
        "approved_binding": {
            "candidate_commit_sha": candidate,
            "candidate_tree_sha": tree,
            "candidate_state_hash": "a" * 64,
            "verified_receipt_hash": "b" * 64,
        },
    }


def test_controlled_integration_merges_only_to_nexus_integration(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README").write_text("base\n")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "branch", "nexus/integration", base)
    _git(repo, "branch", "nexus/task/integration-task", base)
    target = tmp_path / "target"
    _git(repo, "worktree", "add", str(target), "nexus/task/integration-task")
    (target / "change.txt").write_text("candidate\n")
    _git(target, "add", "change.txt")
    _git(target, "commit", "-m", "candidate")
    candidate = _git(target, "rev-parse", "HEAD")
    tree = _git(target, "rev-parse", "HEAD^{tree}")

    receipt = ControlledIntegrationManager(integration_root=tmp_path / "integrations").integrate_task_state(
        _candidate_state(repo, base, candidate, tree)
    )

    assert receipt.integration_branch == "nexus/integration"
    assert receipt.merge_performed is True
    assert receipt.push_performed is False
    assert _git(repo, "rev-parse", "nexus/integration") == receipt.integration_commit_sha
    assert _git(repo, "rev-parse", "main") == base
    assert not (tmp_path / "integrations" / "integration-task").exists()


def test_controlled_integration_rejects_protected_branch(tmp_path):
    manager = ControlledIntegrationManager(integration_root=tmp_path / "integrations")

    with pytest.raises(ValueError, match="protected"):
        manager._validate_branch("main")


def test_controlled_integration_requires_exact_approved_binding(tmp_path):
    manager = ControlledIntegrationManager(integration_root=tmp_path / "integrations")
    state = {"status": "CANDIDATE_COMMITTED", "promotion_status": "APPROVED"}

    with pytest.raises(RuntimeError, match="approved binding"):
        manager.integrate_task_state(state)


def test_controlled_integration_rolls_back_failed_verifier(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README").write_text("base\n")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "branch", "nexus/integration/test", base)
    _git(repo, "branch", "nexus/task/integration-task", base)
    target = tmp_path / "target"
    _git(repo, "worktree", "add", str(target), "nexus/task/integration-task")
    (target / "change.txt").write_text("candidate\n")
    _git(target, "add", "change.txt")
    _git(target, "commit", "-m", "candidate")
    candidate = _git(target, "rev-parse", "HEAD")
    tree = _git(target, "rev-parse", "HEAD^{tree}")
    state = _candidate_state(repo, base, candidate, tree)
    state["contract"]["verifier_commands"] = ["python3 -c 'raise SystemExit(1)'"]

    with pytest.raises(RuntimeError, match="integration verifier failed"):
        ControlledIntegrationManager(integration_root=tmp_path / "integrations").integrate_task_state(
            state, integration_branch="nexus/integration/test"
        )

    assert _git(repo, "rev-parse", "nexus/integration/test") == base
    assert not (tmp_path / "integrations" / "integration-task").exists()
