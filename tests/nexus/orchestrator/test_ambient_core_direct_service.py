from __future__ import annotations

import subprocess
import pytest
from pathlib import Path
from unittest.mock import Mock

from nexus.orchestrator.self_hosted_task_service import (
    SelfHostedTaskService,
)
from nexus.orchestrator.candidate_commit import (
    CandidateCommitter,
)


def _init_repo(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "branch", "-M", "nexus/integration/main"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "--allow-empty", "-m", "init"], check=True)
    return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()


def test_direct_canonical_submits_core_mutation_binding(tmp_path, monkeypatch):
    controller = tmp_path / "canonical"
    base = _init_repo(controller)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT", controller.resolve())
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)

    request = {
        "task_id": "direct-submit-test",
        "controller_repo_root": str(controller),
        "controller_revision": base,
        "allowed_files": ["src/module_a.py"],
        "verifier_commands": ["/usr/bin/true"],
        "primary_agent": True,
        "worker": "primary",
        "execution_lane": "DIRECT_CANONICAL",
    }
    submission = service.submit_task(request)

    assert submission["status"] == "DIRECT_CANONICAL_READY"
    binding = submission["core_mutation_binding"]
    assert binding is not None
    assert binding["schema"] == "nexus.repository_mutation_binding.v1"
    assert binding["operation_id"] == submission["action_id"]
    assert binding["integration_authority"]["execution_lane"] == "DIRECT_CANONICAL"
    assert binding["core"]["acceptance_contract"]["allowed_paths"] == ["src/module_a.py"]
    assert binding["core"]["acceptance_contract"]["required_verifier_ids"] == ["/usr/bin/true"]
    assert binding["binding_hash"].startswith("sha256:")

    # Durable state check
    state = service._read_state_snapshot("direct-submit-test")
    assert state is not None
    assert state.get("core_mutation_binding") == binding


def test_direct_canonical_completes_with_core_verified_status(tmp_path, monkeypatch):
    controller = tmp_path / "canonical"
    base = _init_repo(controller)

    # Worker modifies allowed file
    (controller / "src").mkdir()
    target_file = controller / "src" / "feature.py"
    target_file.write_text("x = 42\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(controller), "add", "src/feature.py"], check=True)
    subprocess.run(["git", "-C", str(controller), "commit", "-m", "add feature"], check=True)
    head = subprocess.run(["git", "-C", str(controller), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT", controller.resolve())
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)

    request = {
        "task_id": "direct-complete-test",
        "controller_repo_root": str(controller),
        "controller_revision": base,
        "allowed_files": ["src/feature.py"],
        "verifier_commands": ["/usr/bin/true"],
        "primary_agent": True,
        "worker": "primary",
        "execution_lane": "DIRECT_CANONICAL",
    }
    service.submit_task(request)

    receipt = service.complete_direct_canonical(request, expected_commit_sha=head)

    assert receipt["status"] == "DIRECT_CANONICAL_COMPLETED"
    assert receipt["commit_sha"] == head

    # Ambient Core verification evidence check
    core_verif = receipt.get("core_verification")
    assert core_verif is not None
    assert core_verif["status"] == "VERIFIED"
    assert core_verif["reason_codes"] == []
    assert core_verif["integrity"] == "VALID"
    assert receipt.get("core_mutation_binding_hash") is not None
    assert receipt["core_mutation_binding_hash"].startswith("sha256:")
    assert "src/feature.py" in core_verif["changed_files"]


def test_direct_canonical_fails_closed_when_core_rejects_scope(tmp_path, monkeypatch):
    controller = tmp_path / "canonical"
    base = _init_repo(controller)

    (controller / "src").mkdir()
    (controller / "src" / "forbidden.py").write_text("evil = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(controller), "add", "src/forbidden.py"], check=True)
    subprocess.run(["git", "-C", str(controller), "commit", "-m", "add forbidden"], check=True)
    head = subprocess.run(["git", "-C", str(controller), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT", controller.resolve())
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)

    request = {
        "task_id": "direct-forbidden-scope",
        "controller_repo_root": str(controller),
        "controller_revision": base,
        "allowed_files": ["src/allowed_only.py"],
        "verifier_commands": ["/usr/bin/true"],
        "primary_agent": True,
        "worker": "primary",
        "execution_lane": "DIRECT_CANONICAL",
    }
    service.submit_task(request)

    # Must fail closed
    with pytest.raises(RuntimeError) as exc:
        service.complete_direct_canonical(request, expected_commit_sha=head)
    assert "SCOPE_MISMATCH" in str(exc.value) or "CORE_VERIFICATION_FAILED" in str(exc.value)


def test_candidate_commit_blocks_unverified_core_mutation():
    contract = Mock()
    lease = Mock()
    receipt = Mock()
    receipt.verified = True
    receipt.candidate_commit_allowed = True
    receipt.core_verification_status = "UNVERIFIABLE"
    receipt.core_mutation_binding_hash = "sha256:" + "0" * 64

    committer = CandidateCommitter(worktree_manager=Mock())

    # When core_verification_status is not VERIFIED, create_candidate_commit must fail closed
    with pytest.raises(RuntimeError) as exc:
        committer.create_candidate_commit(contract, lease, receipt)

    assert "Candidate Core verification is not VERIFIED: UNVERIFIABLE" in str(exc.value)

