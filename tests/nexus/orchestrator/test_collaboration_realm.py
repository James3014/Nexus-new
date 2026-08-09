"""M1 RED integration contract for the sanitized collaboration realm."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest


def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
    result = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_repo(path: Path, *, bare: bool = False) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if bare:
        _git(path, "init", "--bare")
        return
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "M1 integration test")
    _git(path, "config", "user.email", "m1@example.test")


def _clone(source: Path, destination: Path) -> None:
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
    subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "clone", str(source), str(destination)],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    _git(destination, "config", "user.name", "M1 integration test")
    _git(destination, "config", "user.email", "m1@example.test")


CANONICAL_REMOTE = "ssh://git@github.com/James3014/Nexus-new.git"


@pytest.fixture
def collaboration_fixture(tmp_path: Path, monkeypatch) -> dict[str, Path | str]:
    seed = tmp_path / "seed"
    remote = tmp_path / "sanitized.git"
    control = tmp_path / "control-plane"
    collaboration = tmp_path / "collaboration"
    execution_root = tmp_path / "execution"
    ssh_command = tmp_path / "local-ssh"
    remote_path = str(remote)
    ssh_command.write_text(
        "#!/bin/sh\n"
        "for arg in \"$@\"; do\n"
        "  case \"$arg\" in\n"
        f"    git-upload-pack*) exec git-upload-pack '{remote_path}' ;;\n"
        f"    git-receive-pack*) exec git-receive-pack '{remote_path}' ;;\n"
        "  esac\n"
        "done\n"
        "exit 1\n",
        encoding="utf-8",
    )
    ssh_command.chmod(0o700)
    monkeypatch.setenv("GIT_SSH_COMMAND", str(ssh_command))

    _init_repo(seed)
    (seed / "README.md").write_text("sanitized base\n", encoding="utf-8")
    _git(seed, "add", "README.md")
    _git(seed, "commit", "-m", "sanitized base")
    _init_repo(remote, bare=True)
    _git(seed, "remote", "add", "origin", str(remote))
    _git(seed, "push", "origin", "main")
    _git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
    _clone(remote, control)
    _clone(remote, collaboration)
    _git(collaboration, "remote", "set-url", "origin", CANONICAL_REMOTE)
    base_sha = _git(collaboration, "rev-parse", "refs/remotes/origin/main")
    return {
        "remote": remote,
        "control": control,
        "collaboration": collaboration,
        "execution_root": execution_root,
        "base_sha": base_sha,
    }


def _realm_model(fixture: dict[str, Path | str], **overrides: Any) -> Any:
    from nexus.contracts.collaboration_realm import CollaborationExecutionRealm

    control = Path(fixture["control"])
    collaboration = Path(fixture["collaboration"])
    execution_root = Path(fixture["execution_root"])
    values: dict[str, Any] = {
        "control_plane": {
            "repo_root": str(control),
            "revision": fixture["base_sha"],
        },
        "collaboration": {
            "repository": {
                "repository_id": "James3014/Nexus-new",
                "canonical_remote": CANONICAL_REMOTE,
            },
            "base": {"branch": "main", "head_sha": fixture["base_sha"]},
            "repo_root": str(collaboration),
            "remote_name": "origin",
        },
        "runtime_activation": {
            "realm_id": "m1-local-runtime",
            "activation_authorized": False,
        },
        "execution_root": str(execution_root),
    }
    values.update(overrides)
    return CollaborationExecutionRealm.issue(**values)


def _realm_payload(fixture: dict[str, Path | str], **overrides: Any) -> dict[str, Any]:
    return _realm_model(fixture, **overrides).model_dump(mode="json")


def _request(
    fixture: dict[str, Path | str],
    *,
    task_id: str = "m1-realm-task",
    collaboration_realm: dict[str, Any] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    execution_root = Path(fixture["execution_root"])
    request: dict[str, Any] = {
        "task_id": task_id,
        "what": "Bind a GitHub collaboration target",
        "why": "Prove sanitized repository ancestry before M1 execution",
        "worker": "codex",
        "execution_lane": "ISOLATED_TARGET",
        "primary_agent": False,
        "controller_repo_root": str(fixture["collaboration"]),
        "controller_revision": fixture["base_sha"],
        "target_base_revision": fixture["base_sha"],
        "target_worktree_root": str(execution_root),
        "target_repo_root": str(execution_root / task_id),
        "allowed_files": ["nexus/"],
        "verifier_commands": [],
    }
    if collaboration_realm is not None:
        request["collaboration_realm"] = collaboration_realm
    request.update(overrides)
    return request


def _contract(fixture: dict[str, Path | str], **overrides: Any) -> Any:
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

    service = SelfHostedTaskService(
        state_dir=Path(fixture["execution_root"]).parent / "contract-state",
        auto_reconcile=False,
        ephemeral=True,
    )
    realm = overrides.pop("collaboration_realm", _realm_payload(fixture))
    return service.build_contract(_request(fixture, collaboration_realm=realm, **overrides))


def test_m1_01_valid_sanitized_remote_and_base_pass(collaboration_fixture):
    from nexus.orchestrator.collaboration_realm import CollaborationRealmVerifier

    provenance = CollaborationRealmVerifier.verify_submission(_contract(collaboration_fixture))

    assert provenance["remote_base_verified"] is True
    assert provenance["sanitized_ancestry_verified"] is False
    assert provenance["repository_id"] == "James3014/Nexus-new"
    assert provenance["canonical_remote"] == CANONICAL_REMOTE
    assert provenance["base_sha"] == collaboration_fixture["base_sha"]


def test_m1_02_valid_target_uses_collaboration_worktree_and_ancestry_passes(collaboration_fixture):
    from nexus.orchestrator.collaboration_realm import CollaborationRealmVerifier

    contract = _contract(collaboration_fixture, task_id="m1-target-pass")
    collaboration = Path(collaboration_fixture["collaboration"])
    target = Path(collaboration_fixture["execution_root"]) / "m1-target-pass"
    _git(
        collaboration,
        "worktree",
        "add",
        "-b",
        "nexus/task/m1-target-pass",
        str(target),
        collaboration_fixture["base_sha"],
    )
    (target / "nexus-change.txt").write_text("M1\n", encoding="utf-8")
    _git(target, "add", "nexus-change.txt")
    _git(target, "commit", "-m", "collaboration target")
    target_head = _git(target, "rev-parse", "HEAD")

    provenance = CollaborationRealmVerifier.verify_target(contract, target, target_head)

    assert provenance["remote_base_verified"] is True
    assert provenance["sanitized_ancestry_verified"] is True
    assert provenance["base_sha"] == collaboration_fixture["base_sha"]


def test_m1_03_remote_url_mismatch_fails_closed(collaboration_fixture):
    from nexus.orchestrator.collaboration_realm import CollaborationRealmVerifier

    realm = _realm_payload(
        collaboration_fixture,
        collaboration={
            **_realm_model(collaboration_fixture).collaboration.model_dump(mode="json"),
            "repository": {
                "repository_id": "James3014/Nexus-new",
                "canonical_remote": "ssh://git@other.example/James3014/Nexus-new.git",
            },
        },
    )
    contract = _contract(collaboration_fixture, collaboration_realm=realm)

    with pytest.raises(RuntimeError, match="COLLABORATION_REALM_REMOTE_MISMATCH"):
        CollaborationRealmVerifier.verify_submission(contract)


def test_m1_04_remote_main_branch_drift_fails_closed(collaboration_fixture):
    from nexus.orchestrator.collaboration_realm import CollaborationRealmVerifier

    drift = Path(collaboration_fixture["execution_root"]).parent / "remote-drift"
    _clone(Path(collaboration_fixture["remote"]), drift)
    _git(drift, "remote", "set-url", "origin", CANONICAL_REMOTE)
    (drift / "drift.txt").write_text("drift\n", encoding="utf-8")
    _git(drift, "add", "drift.txt")
    _git(drift, "commit", "-m", "remote branch drift")
    _git(drift, "push", "origin", "main")
    contract = _contract(collaboration_fixture)

    with pytest.raises(RuntimeError, match="COLLABORATION_REALM_REMOTE_BASE_DRIFT"):
        CollaborationRealmVerifier.verify_submission(contract)


def test_m1_05_shared_control_git_common_dir_is_rejected(collaboration_fixture):
    from nexus.orchestrator.collaboration_realm import CollaborationRealmVerifier

    control = Path(collaboration_fixture["control"])
    impostor = Path(collaboration_fixture["execution_root"]).parent / "control-worktree-impostor"
    _git(control, "worktree", "add", "--detach", str(impostor), collaboration_fixture["base_sha"])
    realm = _realm_model(collaboration_fixture, collaboration={
        **_realm_model(collaboration_fixture).collaboration.model_dump(mode="python"),
        "repo_root": str(impostor),
    })
    contract = _contract(
        collaboration_fixture,
        collaboration_realm=realm.model_dump(mode="json"),
        controller_repo_root=str(impostor),
    )

    with pytest.raises(RuntimeError, match="COLLABORATION_REALM_LOCAL_HISTORY_REJECTED"):
        CollaborationRealmVerifier.verify_submission(contract)


def test_m1_06_independent_clone_target_is_rejected(collaboration_fixture):
    from nexus.orchestrator.collaboration_realm import CollaborationRealmVerifier

    contract = _contract(collaboration_fixture, task_id="m1-independent-target")
    target = Path(collaboration_fixture["execution_root"]) / "m1-independent-target"
    _clone(Path(collaboration_fixture["remote"]), target)
    target_head = _git(target, "rev-parse", "HEAD")

    with pytest.raises(RuntimeError, match="COLLABORATION_REALM_TARGET_REPOSITORY_MISMATCH"):
        CollaborationRealmVerifier.verify_target(contract, target, target_head)


def test_m1_07_local_non_descendant_target_is_rejected(collaboration_fixture):
    from nexus.orchestrator.collaboration_realm import CollaborationRealmVerifier

    contract = _contract(collaboration_fixture, task_id="m1-local-history-target")
    collaboration = Path(collaboration_fixture["collaboration"])
    target = Path(collaboration_fixture["execution_root"]) / "m1-local-history-target"
    _git(
        collaboration,
        "worktree",
        "add",
        "--detach",
        str(target),
        collaboration_fixture["base_sha"],
    )
    _git(target, "switch", "--orphan", "local-history")
    for child in target.iterdir():
        if child.name != ".git":
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    (target / "local-only.txt").write_text("unsanitized\n", encoding="utf-8")
    _git(target, "add", "local-only.txt")
    _git(target, "commit", "-m", "local unsanitized history")
    target_head = _git(target, "rev-parse", "HEAD")

    with pytest.raises(RuntimeError, match="COLLABORATION_REALM_TARGET_ANCESTRY_MISMATCH"):
        CollaborationRealmVerifier.verify_target(contract, target, target_head)


def test_m1_08_service_fails_before_state_on_invalid_realm(collaboration_fixture, tmp_path):
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

    state_dir = tmp_path / "state"
    service = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    realm = _realm_payload(
        collaboration_fixture,
        collaboration={
            **_realm_model(collaboration_fixture).collaboration.model_dump(mode="json"),
            "repository": {
                "repository_id": "James3014/Nexus-new",
                "canonical_remote": "ssh://git@other.example/James3014/Nexus-new.git",
            },
        },
    )

    with pytest.raises(RuntimeError, match="COLLABORATION_REALM_REMOTE_MISMATCH"):
        service.submit_task(
            _request(
                collaboration_fixture,
                task_id="m1-physical-fail-closed",
                collaboration_realm=realm,
            )
        )

    assert not (state_dir / "m1-physical-fail-closed.json").exists()
    assert not list(state_dir.glob("**/m1-physical-fail-closed*"))


def test_m1_09_receipt_exposes_typed_realm_and_provenance(collaboration_fixture, tmp_path):
    from nexus.orchestrator.collaboration_realm import CollaborationRealmVerifier
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

    service = SelfHostedTaskService(state_dir=tmp_path / "receipt-state", auto_reconcile=False, ephemeral=True)
    contract = _contract(collaboration_fixture, task_id="m1-receipt")
    provenance = CollaborationRealmVerifier.verify_submission(contract)
    service._write_state(
        "m1-receipt",
        {
            "task_id": "m1-receipt",
            "status": "PENDING_HUMAN_APPROVAL",
            "attempt_id": "attempt-1",
            "contract": contract.model_dump(mode="json"),
            "collaboration_realm": contract.collaboration_realm.model_dump(mode="json"),
            "collaboration_provenance": provenance,
        },
    )

    receipt = service.get_receipt("m1-receipt")

    assert receipt is not None
    assert receipt["collaboration_realm"]["schema"] == "nexus.collaboration_execution_realm.v1"
    assert receipt["collaboration_realm"]["binding_hash"] == contract.collaboration_realm.binding_hash
    assert receipt["collaboration_provenance"]["remote_base_verified"] is True
    assert receipt["collaboration_provenance"]["base_sha"] == collaboration_fixture["base_sha"]


def test_m1_10_without_realm_preserves_local_create_and_capture(collaboration_fixture):
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
    from nexus.orchestrator.worktree_manager import WorktreeManager

    service = SelfHostedTaskService(
        state_dir=Path(collaboration_fixture["execution_root"]).parent / "local-state",
        auto_reconcile=False,
        ephemeral=True,
    )
    request = _request(collaboration_fixture, task_id="local-no-collaboration")
    request.pop("collaboration_realm", None)
    contract = service.build_contract(request)
    manager = WorktreeManager(root_dir=str(collaboration_fixture["execution_root"]))

    lease = manager.create_lease(contract)
    receipt = manager.capture_candidate(contract, lease)

    assert contract.collaboration_realm is None
    assert lease.collaboration_provenance is None
    assert receipt.collaboration_provenance is None
    assert receipt.allowed_scope_passed is True


def test_m1_11_mcp_submit_schema_is_closed_and_exposes_collaboration_realm():
    from nexus.orchestrator.self_hosted_mcp import NexusSelfHostedMCPServer

    submit = next(
        spec for spec in NexusSelfHostedMCPServer._tool_specs()
        if spec["name"] == "nexus_self_hosted_submit_task"
    )
    realm_schema = submit["inputSchema"]["properties"]["collaboration_realm"]

    assert realm_schema["additionalProperties"] is False
    assert set(realm_schema["required"]) == {
        "schema",
        "control_plane",
        "collaboration",
        "runtime_activation",
        "execution_root",
        "binding_hash",
    }
    assert realm_schema["properties"]["collaboration"]["additionalProperties"] is False
    assert realm_schema["properties"]["runtime_activation"]["properties"][
        "activation_authorized"
    ]["const"] is False


def test_m1_12_git_global_credentials_remain_available_without_prompt(tmp_path, monkeypatch):
    from nexus.orchestrator.collaboration_realm import CollaborationRealmVerifier

    global_config = tmp_path / "gitconfig"
    subprocess.run(
        [
            "git",
            "config",
            "--file",
            str(global_config),
            "credential.helper",
            "nexus-private-repository-helper",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    monkeypatch.delenv("GIT_TERMINAL_PROMPT", raising=False)

    configured_helper = CollaborationRealmVerifier._git(
        tmp_path,
        "config",
        "--global",
        "--get",
        "credential.helper",
    )

    assert configured_helper == "nexus-private-repository-helper"


def test_m1_13_receipt_promotes_target_bound_provenance_through_candidate_commit(
    collaboration_fixture,
    tmp_path,
):
    from nexus.orchestrator.candidate_commit import CandidateCommitter
    from nexus.orchestrator.candidate_verifier import CandidateVerifier
    from nexus.orchestrator.collaboration_realm import CollaborationRealmVerifier
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
    from nexus.orchestrator.worktree_manager import WorktreeManager

    contract = _contract(
        collaboration_fixture,
        task_id="m1-full-receipt",
        verifier_commands=["python3 -c 'print(\"pass\")'"],
    )
    manager = WorktreeManager(str(collaboration_fixture["execution_root"]))
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "nexus").mkdir()
    (target / "nexus" / "m1-realm.txt").write_text("target-bound\n", encoding="utf-8")
    candidate = manager.capture_candidate(contract, lease)
    verified = CandidateVerifier(manager).verify(contract, lease, candidate)
    packet = CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)
    submission_provenance = CollaborationRealmVerifier.verify_submission(contract)

    service = SelfHostedTaskService(
        state_dir=tmp_path / "full-receipt-state",
        auto_reconcile=False,
        ephemeral=True,
    )
    service._write_state(
        contract.task_id,
        {
            "task_id": contract.task_id,
            "status": "PENDING_HUMAN_APPROVAL",
            "attempt_id": "attempt-1",
            "contract": contract.model_dump(mode="json"),
            "lease": asdict(lease),
            "candidate": asdict(candidate),
            "verified_receipt": asdict(verified),
            "promotion_packet": asdict(packet),
            "collaboration_realm": contract.collaboration_realm.model_dump(mode="json"),
            "submission_collaboration_provenance": submission_provenance,
            "collaboration_provenance": submission_provenance,
        },
    )

    receipt = service.get_receipt(contract.task_id)

    assert receipt is not None
    assert receipt["submission_collaboration_provenance"]["sanitized_ancestry_verified"] is False
    assert receipt["collaboration_provenance"]["sanitized_ancestry_verified"] is True
    assert receipt["candidate_collaboration_provenance"] == packet.collaboration_provenance
    assert receipt["collaboration_provenance"]["target_head"] == candidate.target_head
    assert receipt["collaboration_provenance"]["binding_hash"] == contract.collaboration_realm.binding_hash
    assert _git(target, "merge-base", "--is-ancestor", candidate.target_head, packet.candidate_commit_sha) == ""


def test_m1_14_post_creation_provenance_failure_rolls_back_target_and_branch(
    collaboration_fixture,
    monkeypatch,
):
    from nexus.orchestrator.collaboration_realm import CollaborationRealmVerifier
    from nexus.orchestrator.worktree_manager import WorktreeManager

    contract = _contract(collaboration_fixture, task_id="m1-race-rollback")
    manager = WorktreeManager(str(collaboration_fixture["execution_root"]))
    target = Path(contract.target_repo_root)

    def fail_after_target_creation(*_args, **_kwargs):
        raise RuntimeError("COLLABORATION_REALM_REMOTE_BASE_DRIFT")

    monkeypatch.setattr(
        CollaborationRealmVerifier,
        "verify_target",
        fail_after_target_creation,
    )

    with pytest.raises(RuntimeError, match="COLLABORATION_REALM_REMOTE_BASE_DRIFT"):
        manager.create_lease(contract)

    collaboration = Path(collaboration_fixture["collaboration"])
    assert not target.exists()
    assert str(target) not in _git(collaboration, "worktree", "list", "--porcelain")
    branch = subprocess.run(
        [
            "git",
            "show-ref",
            "--verify",
            "--quiet",
            "refs/heads/nexus/task/m1-race-rollback",
        ],
        cwd=collaboration,
        check=False,
    )
    assert branch.returncode == 1
