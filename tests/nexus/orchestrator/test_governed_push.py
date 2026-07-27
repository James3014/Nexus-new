import subprocess
from pathlib import Path

import pytest

from nexus.orchestrator.governed_push import GovernedPushManager


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def test_governed_push_requires_authorization_and_allowlisted_integration_branch(tmp_path):
    repo = tmp_path / "repo"
    remote = tmp_path / "remote.git"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "file.txt").write_text("base\n")
    _git(repo, "add", "file.txt")
    _git(repo, "commit", "-m", "base")
    _git(repo, "branch", "nexus/integration")
    _git(repo, "init", "--bare", str(remote))
    _git(repo, "remote", "add", "origin", str(remote))
    expected = _git(repo, "rev-parse", "nexus/integration")
    manager = GovernedPushManager(repo_root=repo, allowed_remotes={"origin"})

    with pytest.raises(PermissionError):
        manager.push(remote="origin", branch="nexus/integration", expected_sha=expected, authorized=False)

    receipt = manager.push(
        remote="origin",
        branch="nexus/integration",
        expected_sha=expected,
        authorized=True,
    )

    assert receipt.push_performed is True
    assert receipt.force_push is False
    assert receipt.remote_commit_sha == expected


def test_governed_push_rejects_main(tmp_path):
    manager = GovernedPushManager(repo_root=tmp_path, allowed_remotes={"origin"})

    with pytest.raises(PermissionError, match="branch"):
        manager.push(
            remote="origin",
            branch="main",
            expected_sha="a" * 40,
            authorized=True,
        )
