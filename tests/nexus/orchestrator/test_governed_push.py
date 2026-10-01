import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import nexus.orchestrator.governed_push as governed_push_module
import nexus.orchestrator.standing_grant_store as standing_grant_store
from nexus.contracts.autonomy_goal import (
    AutonomyActionClass,
    StandingGrantContext,
    canonical_autonomy_hash,
)
from nexus.orchestrator.governed_push import GovernedPushManager
from nexus.orchestrator.standing_grant_store import StandingGrantKey, StandingGrantReceipt


def _key():
    return StandingGrantKey(governed_push_module._GITHUB_REPOSITORY, "goal", "scope")


def _physical_keyed_receipt(tmp_path, key, grant_id):
    context = StandingGrantContext.issue(
        owner_id="owner",
        coordinator_id="coordinator",
        repository=key.repository,
        thread_id=key.coordinator_thread,
        goal_id=key.goal_id,
        allowed_actions=(AutonomyActionClass.REPOSITORY_PUSH,),
        issued_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    receipt = StandingGrantReceipt.issue(grant_id=grant_id, context=context)
    path = tmp_path / f"{grant_id}.json"
    path.write_text(
        json.dumps(receipt.model_dump(mode="json"), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return receipt


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _authority(*, competition_id: str, winner_task_id: str, remote: str, branch: str, expected_sha: str):
    effect = {
        "competition_id": competition_id,
        "winner_task_id": winner_task_id,
        "remote": remote,
        "branch": branch,
        "expected_sha": expected_sha,
    }
    payload = {
        "schema": "nexus.standing_grant_effect_authorization.v1",
        "grant_id": "grant-test",
        "grant_receipt_hash": "1" * 64,
        "context_hash": "2" * 64,
        "owner_id": "owner",
        "coordinator_id": "coordinator",
        "repository": {
            "repository_id": "James3014/Nexus-new",
            "canonical_remote": "https://github.com/James3014/Nexus-new.git",
        },
        "goal_id": "goal",
        "action": AutonomyActionClass.REPOSITORY_PUSH.value,
        "requested_at": "2026-08-27T00:00:00+00:00",
        "effect": effect,
        "effect_hash": canonical_autonomy_hash(effect),
        "decision_hash": "3" * 64,
        "mutation_authorized": True,
        "claim_ceiling": "AUTHORIZATION_ONLY_VERIFICATION_REQUIRED",
    }
    return {**payload, "authorization_hash": canonical_autonomy_hash(payload)}


def _repo_with_remote(tmp_path: Path):
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
    return repo, remote, _git(repo, "rev-parse", "nexus/integration")


def test_governed_push_requires_authorization_and_allowlisted_integration_branch(monkeypatch, tmp_path):
    repo, _remote, expected = _repo_with_remote(tmp_path)
    manager = GovernedPushManager(repo_root=repo, allowed_remotes={"origin"})

    def deny(**_kwargs):
        from nexus.orchestrator.standing_grant_store import StandingGrantReceiptError
        raise StandingGrantReceiptError("RECEIPT_MISSING")

    monkeypatch.setattr(governed_push_module, "authorize_durable_standing_grant_effect", deny)
    with pytest.raises(PermissionError, match="durable Owner authorization"):
        manager.push(
            competition_id="competition-1",
            winner_task_id="winner-1",
            remote="origin",
            branch="nexus/integration",
            expected_sha=expected,
            authority_key=_key(),
        )
    assert _git(repo, "ls-remote", "--heads", "origin", "refs/heads/nexus/integration") == ""

    monkeypatch.setattr(
        governed_push_module,
        "authorize_durable_standing_grant_effect",
        lambda **kwargs: _authority(
            competition_id="competition-1",
            winner_task_id="winner-1",
            remote="origin",
            branch="nexus/integration",
            expected_sha=expected,
        ),
    )
    receipt = manager.push(
        competition_id="competition-1",
        winner_task_id="winner-1",
        remote="origin",
        branch="nexus/integration",
        expected_sha=expected,
        authority_key=_key(),
    )
    assert receipt.push_performed is True
    assert receipt.push_attempted is True
    assert receipt.push_acknowledged is True
    assert receipt.remote_commit_sha == expected


def test_governed_push_rejects_main(monkeypatch, tmp_path):
    manager = GovernedPushManager(repo_root=tmp_path, allowed_remotes={"origin"})
    called = False

    def authorize(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("authorization should not be evaluated for forbidden branch")

    monkeypatch.setattr(governed_push_module, "authorize_durable_standing_grant_effect", authorize)
    with pytest.raises(PermissionError, match="branch"):
        manager.push(
            competition_id="competition-1",
            winner_task_id="winner-1",
            remote="origin",
            branch="main",
            expected_sha="a" * 40,
            authority_key=_key(),
        )
    assert called is False


def test_governed_push_rejects_effect_substitution_before_git_push(monkeypatch, tmp_path):
    repo, _remote, expected = _repo_with_remote(tmp_path)
    manager = GovernedPushManager(repo_root=repo, allowed_remotes={"origin"})
    monkeypatch.setattr(
        governed_push_module,
        "authorize_durable_standing_grant_effect",
        lambda **kwargs: _authority(
            competition_id="other",
            winner_task_id="winner-1",
            remote="origin",
            branch="nexus/integration",
            expected_sha=expected,
        ),
    )
    with pytest.raises(PermissionError, match="exact durable Owner authorization"):
        manager.push(
            competition_id="competition-1",
            winner_task_id="winner-1",
            remote="origin",
            branch="nexus/integration",
            expected_sha=expected,
            authority_key=_key(),
        )
    assert _git(repo, "ls-remote", "--heads", "origin", "refs/heads/nexus/integration") == ""


def test_governed_push_reconciles_preexisting_effect_without_repush(monkeypatch, tmp_path):
    repo, _remote, expected = _repo_with_remote(tmp_path)
    _git(repo, "push", "origin", f"{expected}:refs/heads/nexus/integration")
    manager = GovernedPushManager(repo_root=repo, allowed_remotes={"origin"})
    monkeypatch.setattr(
        governed_push_module,
        "authorize_durable_standing_grant_effect",
        lambda **kwargs: _authority(
            competition_id="competition-1",
            winner_task_id="winner-1",
            remote="origin",
            branch="nexus/integration",
            expected_sha=expected,
        ),
    )
    receipt = manager.push(
        competition_id="competition-1",
        winner_task_id="winner-1",
        remote="origin",
        branch="nexus/integration",
        expected_sha=expected,
        authority_key=_key(),
    )
    assert receipt.push_performed is False
    assert receipt.push_attempted is False
    assert receipt.preexisting_effect is True
    assert receipt.effect_present is True


def test_governed_push_uncertain_ack_reconciles_remote_before_return(monkeypatch, tmp_path):
    repo, _remote, expected = _repo_with_remote(tmp_path)
    manager = GovernedPushManager(repo_root=repo, allowed_remotes={"origin"})
    monkeypatch.setattr(
        governed_push_module,
        "authorize_durable_standing_grant_effect",
        lambda **kwargs: _authority(
            competition_id="competition-1",
            winner_task_id="winner-1",
            remote="origin",
            branch="nexus/integration",
            expected_sha=expected,
        ),
    )
    original_git = manager._git
    push_seen = False

    def uncertain(args):
        nonlocal push_seen
        if args and args[0] == "push":
            push_seen = True
            original_git(args)
            raise RuntimeError("lost acknowledgement")
        return original_git(args)

    monkeypatch.setattr(manager, "_git", uncertain)
    receipt = manager.push(
        competition_id="competition-1",
        winner_task_id="winner-1",
        remote="origin",
        branch="nexus/integration",
        expected_sha=expected,
        authority_key=_key(),
    )
    assert push_seen is True
    assert receipt.push_performed is False
    assert receipt.push_attempted is True
    assert receipt.push_acknowledged is False
    assert receipt.reconciled_after_uncertain_ack is True
    assert receipt.effect_present is True


def test_governed_push_exact_key_authorizes_preexisting_remote_without_push(monkeypatch, tmp_path):
    repo, _remote, expected = _repo_with_remote(tmp_path)
    _git(repo, "push", "origin", f"{expected}:refs/heads/nexus/integration")
    key_a = StandingGrantKey(governed_push_module._GITHUB_REPOSITORY, "goal-a", "scope-a")
    key_b = StandingGrantKey(governed_push_module._GITHUB_REPOSITORY, "goal-b", "scope-b")
    keyed_dir = tmp_path / "keyed"
    monkeypatch.setattr(
        standing_grant_store, "_keyed_directory", lambda key: keyed_dir / key.digest
    )
    monkeypatch.setattr(
        standing_grant_store,
        "_keyed_receipt_path",
        lambda key: keyed_dir / key.digest / f"{key.digest}.json",
    )
    receipt_a = _physical_keyed_receipt(tmp_path, key_a, "grant-a")
    receipt_b = _physical_keyed_receipt(tmp_path, key_b, "grant-b")
    for key, receipt in ((key_a, receipt_a), (key_b, receipt_b)):
        (keyed_dir / key.digest).mkdir(parents=True)
        os.chmod(keyed_dir / key.digest, 0o700)
        (keyed_dir / key.digest / f"{key.digest}.json").write_text(
            json.dumps(
                receipt.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ),
            encoding="utf-8",
        )
        os.chmod(keyed_dir / key.digest / f"{key.digest}.json", 0o600)
    manager = GovernedPushManager(repo_root=repo, allowed_remotes={"origin"})
    result = manager.push(
        competition_id="competition-1",
        winner_task_id="winner-1",
        remote="origin",
        branch="nexus/integration",
        expected_sha=expected,
        authority_key=key_a,
    )
    assert result.authorized is True
    assert result.preexisting_effect is True
    assert result.push_performed is False
    assert result.authorization_grant_receipt_hash == receipt_a.receipt_hash


def test_governed_push_wrong_key_type_is_zero_git_calls(monkeypatch, tmp_path):
    repo, _remote, expected = _repo_with_remote(tmp_path)
    manager = GovernedPushManager(repo_root=repo, allowed_remotes={"origin"})
    calls = []
    monkeypatch.setattr(manager, "_git", lambda args: calls.append(args) or expected)
    with pytest.raises(PermissionError, match="exact repository authority key"):
        manager.push(
            competition_id="competition-1", winner_task_id="winner-1", remote="origin",
            branch="nexus/integration", expected_sha=expected, authority_key="wrong",
        )
    assert calls == []
