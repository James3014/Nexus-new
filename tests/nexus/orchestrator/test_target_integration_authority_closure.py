"""Corrective RED probes for the rejected Target integration Candidate."""

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.contracts.lifecycle_action import build_owner_inline_contract
from nexus.contracts.target_integration_lifecycle import (
    CleanupDecision,
    ExternalAcceptanceReceipt,
    IntegrationAuthorizationEnvelope,
    TargetResolutionMode,
)
from nexus.contracts.workforce_admission import WorkforceDemand
from nexus.executors.cli_worker import bounded_environment_receipt
from nexus.orchestrator.governed_integration import (
    ControlledIntegrationManager,
    IntegrationExecutionError,
    IntegrationReceipt,
)
from nexus.orchestrator.repository_contract_gate import RepositoryContractGate
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.target_integration_lifecycle import TargetIntegrationLifecycle
from nexus.orchestrator.worktree_manager import WorktreeManager
from nexus.services.runtime_workforce_admission import _binding_payload, _sha256_json


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, str, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "canary")
    _git(root, "config", "user.email", "canary@example.invalid")
    (root / "value.txt").write_text("base\n")
    _git(root, "add", "value.txt")
    _git(root, "commit", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    _git(root, "branch", "candidate")
    _git(root, "checkout", "candidate")
    (root / "value.txt").write_text("candidate\n")
    _git(root, "commit", "-am", "candidate")
    candidate = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "main")
    _git(root, "checkout", "-b", "nexus/integration/canary")
    return root, base, candidate


def _status_hash(root: Path) -> str:
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    return hashlib.sha256(status.encode()).hexdigest()


def test_direct_service_approval_uses_nested_owner_inline_hash(
    tmp_path: Path, monkeypatch
):
    task_id = "service-inline-approval"
    attempt_id = "attempt-inline-approval"
    head = "a" * 40
    inline = build_owner_inline_contract(
        task_id=task_id,
        objective="approve exact nested Owner Inline identity",
        allowed_files=["README.md"],
        verifier_commands=["git diff --check"],
        expected_head=head,
        issued_at=datetime.now(timezone.utc).isoformat(),
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
    )
    packet = {
        "candidate_commit_sha": "b" * 40,
        "candidate_tree_sha": "c" * 40,
        "candidate_state_hash": "d" * 64,
        "verified_receipt_hash": hashlib.sha256(b'{"verified":true}').hexdigest(),
    }
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=False
    )
    service._write_state(task_id, {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "status": "PENDING_HUMAN_APPROVAL",
        "promotion_status": "PENDING_HUMAN_APPROVAL",
        "controller_revision": head,
        "contract_kind": "OWNER_INLINE",
        "contract_hash": "f" * 64,
        "task_card_hash": None,
        "owner_inline_contract": inline,
        "request": {},
        "promotion_packet": packet,
        "verified_receipt": {"verified": True},
    })
    now = datetime.now(timezone.utc)
    approval = {
        "schema": "nexus.approval.v2",
        "approval_id": "approval-inline",
        "approved_by": "James",
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "bound_task_id": task_id,
        "bound_attempt_id": attempt_id,
        "bound_action_type": "CANDIDATE_APPROVE",
        "approval_scope": "ALLOW_ACTION_ONCE",
        "contract_kind": "OWNER_INLINE",
        "contract_hash": "f" * 64,
        "task_card_hash": None,
        "tool_manifest_hash": "1" * 64,
        "full_tool_schema_hash": "2" * 64,
        "permission_policy_hash": "3" * 64,
        "lifecycle_revision": "nexus.lifecycle.gateway.v2",
        "server_instance_id": "server-inline",
    }
    before = service._state_path(task_id).read_bytes()
    with pytest.raises(RuntimeError, match="CONTRACT_HASH_MISMATCH|APPROVAL_BINDING_MISMATCH"):
        service.approve_promotion(task_id, approval_context=approval, **packet)
    assert service._state_path(task_id).read_bytes() == before

    approval["contract_hash"] = inline["contract_hash"]
    valid_state = service._read_state(task_id)
    for tamper in (
        lambda state: state.update(controller_revision="9" * 40),
        lambda state: state.update(
            owner_inline_contract={**inline, "task_id": "other-task"}
        ),
    ):
        altered = json.loads(json.dumps(valid_state))
        tamper(altered)
        service._write_state(task_id, altered)
        tampered_bytes = service._state_path(task_id).read_bytes()
        with pytest.raises(RuntimeError, match="CONTRACT_HASH_MISMATCH"):
            service.approve_promotion(task_id, approval_context=approval, **packet)
        assert service._state_path(task_id).read_bytes() == tampered_bytes
    service._write_state(task_id, valid_state)

    raced_inline = build_owner_inline_contract(
        task_id=task_id,
        objective="different valid contract introduced during approval",
        allowed_files=["README.md"],
        verifier_commands=["git diff --check"],
        expected_head=head,
        issued_at=inline["issued_at"],
        expires_at=inline["expires_at"],
    )
    original_mutate = service._mutate_state
    raced_bytes = None

    def race_before_lock(race_task_id, mutator):
        nonlocal raced_bytes
        raced = service._read_state(race_task_id)
        raced["owner_inline_contract"] = raced_inline
        service._write_state(race_task_id, raced)
        raced_bytes = service._state_path(race_task_id).read_bytes()
        return original_mutate(race_task_id, mutator)

    monkeypatch.setattr(service, "_mutate_state", race_before_lock)
    with pytest.raises(RuntimeError, match="APPROVAL_BINDING_CONCURRENCY_DRIFT"):
        service.approve_promotion(task_id, approval_context=approval, **packet)
    assert service._state_path(task_id).read_bytes() == raced_bytes

    monkeypatch.setattr(service, "_mutate_state", original_mutate)
    service._write_state(task_id, valid_state)
    result = service.approve_promotion(task_id, approval_context=approval, **packet)
    assert result["status"] == "APPROVED"
    stored = service._read_state(task_id)
    assert stored["approved_binding"]["approval_grant"]["contract_hash"] == inline["contract_hash"]


def test_owner_inline_service_bind_and_integrate_use_nested_hash(
    tmp_path: Path, monkeypatch
):
    service, root, base, _, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    inline = build_owner_inline_contract(
        task_id="closure-bind",
        objective="bind and integrate exact nested Owner Inline identity",
        allowed_files=["value.txt"],
        verifier_commands=["/usr/bin/true"],
        expected_head=base,
        issued_at=datetime.now(timezone.utc).isoformat(),
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
    )
    state = service._read_state("closure-bind")
    state.update({
        "contract_kind": "OWNER_INLINE",
        "contract_hash": "f" * 64,
        "task_card_hash": None,
        "owner_inline_contract": inline,
    })
    service._write_state("closure-bind", state)
    owner_approval = {
        **approval,
        "contract_kind": "OWNER_INLINE",
        "contract_hash": inline["contract_hash"],
        "task_card_hash": None,
    }
    top_level_approval = {**owner_approval, "contract_hash": "f" * 64}
    before = service._state_path("closure-bind").read_bytes()
    with pytest.raises(RuntimeError, match="CLOSURE_RUNTIME_IDENTITY_MISMATCH"):
        service.bind_candidate_integration_closure(
            "closure-bind",
            external_acceptance=acceptance,
            approval=owner_approval,
            runtime_identity={**runtime, "contract_hash": "f" * 64},
            expected_canonical_head=base,
            integration_branch="nexus/integration/canary",
        )
    assert service._state_path("closure-bind").read_bytes() == before
    with pytest.raises(RuntimeError, match="CONTRACT_HASH_MISMATCH|APPROVAL_BINDING_MISMATCH"):
        service.bind_candidate_integration_closure(
            "closure-bind",
            external_acceptance=acceptance,
            approval=top_level_approval,
            runtime_identity=runtime,
            expected_canonical_head=base,
            integration_branch="nexus/integration/canary",
        )
    assert service._state_path("closure-bind").read_bytes() == before

    bound = service.bind_candidate_integration_closure(
        "closure-bind",
        external_acceptance=acceptance,
        approval=owner_approval,
        runtime_identity=runtime,
        expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    assert bound["integration_performed"] is False
    stored = service._read_state("closure-bind")
    assert stored["integration_approval_grant"]["contract_hash"] == inline["contract_hash"]
    assert stored["integration_closure_binding"]["contract_hash"] == inline["contract_hash"]
    bound_bytes = service._state_path("closure-bind").read_bytes()
    with pytest.raises(RuntimeError, match="APPROVAL_RUNTIME_IDENTITY_MISMATCH"):
        service.integrate_approved(
            "closure-bind",
            integration_branch="nexus/integration/canary",
            runtime_identity={**runtime, "contract_hash": "f" * 64},
        )
    assert service._state_path("closure-bind").read_bytes() == bound_bytes

    monkeypatch.setattr(
        service,
        "_record_integration",
        lambda receipt, *, task_id=None: {
            "status": "INTEGRATED",
            "promotion_status": "INTEGRATED",
            "task_id": task_id,
        },
    )
    monkeypatch.setattr(
        RepositoryContractGate,
        "evaluate_committed_candidate",
        lambda *args, **kwargs: SimpleNamespace(passed=True, blocking_reasons=()),
    )

    class FakeIntegrationManager:
        calls = 0

        def __init__(self, **kwargs):
            pass

        def integrate_authorized_task_state(self, *args, **kwargs):
            type(self).calls += 1
            return SimpleNamespace()

    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.ControlledIntegrationManager",
        FakeIntegrationManager,
    )
    bound_state = json.loads(json.dumps(service._read_state("closure-bind")))
    raced_inline = build_owner_inline_contract(
        task_id="closure-bind",
        objective="different valid contract introduced before apply",
        allowed_files=["value.txt"],
        verifier_commands=["/usr/bin/true"],
        expected_head=base,
        issued_at=inline["issued_at"],
        expires_at=inline["expires_at"],
    )
    original_checkpoint = service._checkpoint

    def race_at_integrating(task_id, status, updates, *, attempt_id=None):
        result = original_checkpoint(
            task_id, status, updates, attempt_id=attempt_id
        )
        if status == "INTEGRATING":
            raced = service._read_state(task_id)
            raced["owner_inline_contract"] = raced_inline
            service._write_state(task_id, raced)
        return result

    monkeypatch.setattr(service, "_checkpoint", race_at_integrating)
    with pytest.raises(RuntimeError, match="INTEGRATION_BINDING_DRIFT_AT_APPLY_BOUNDARY"):
        service.integrate_approved(
            "closure-bind",
            integration_branch="nexus/integration/canary",
            runtime_identity=runtime,
        )
    assert FakeIntegrationManager.calls == 0

    monkeypatch.setattr(service, "_checkpoint", original_checkpoint)
    service._write_state("closure-bind", bound_state)
    result = service.integrate_approved(
        "closure-bind",
        integration_branch="nexus/integration/canary",
        runtime_identity=runtime,
    )
    assert result["status"] == "INTEGRATED"
    assert FakeIntegrationManager.calls == 1


def _receipt_hash(receipt: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _verifier_evidence(command: str) -> list[dict[str, object]]:
    executable = Path(command)
    return [{
        "command": command,
        "status": "COMPLETED",
        "exit_code": 0,
        "executable_identity": str(executable),
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "argv": [],
        "env": bounded_environment_receipt({"PYTHONDONTWRITEBYTECODE": "1"}),
        "timed_out": False,
        "process_group_killed": False,
    }]


def _manifest(verified_receipt: dict[str, object], contract) -> list[dict[str, object]]:
    return list(ControlledIntegrationManager._admitted_manifest(
        {"verified_receipt": verified_receipt}, contract.model_dump(mode="json"),
    ))


def _verified_gate_proof(root: Path, contract) -> dict[str, object]:
    """Build the exact policy proof consumed by integration recheck."""
    gate = RepositoryContractGate(
        WorktreeManager(root_dir=str(root), create_root=False)
    )
    policy_inputs = gate._policy_input_hashes(
        root.resolve(), contract.target_base_revision
    )
    return {
        "repository_contract_gate_passed": True,
        "repository_contract_policy_revision_hash": gate._policy_revision_hash(
            contract.target_base_revision, policy_inputs
        ),
    }


def _acceptance(candidate: str) -> ExternalAcceptanceReceipt:
    return ExternalAcceptanceReceipt(
        schema="nexus.external_acceptance_receipt.v1", task_id="task-1",
        attempt_id="attempt-1", candidate_commit=candidate,
        receipt_hash="b" * 64, reviewer_id="reviewer-1", passed=True,
        verifier_artifact="artifact-1",
    )


def _authorization(root: Path, base: str, candidate: str, acceptance: ExternalAcceptanceReceipt) -> IntegrationAuthorizationEnvelope:
    return IntegrationAuthorizationEnvelope(
        schema="nexus.integration_authorization.v1", task_id="task-1",
        campaign_id="campaign", task_card_hash="c" * 64, attempt_id="attempt-1",
        candidate_commit=candidate, candidate_tree_sha=_git(root, "rev-parse", f"{candidate}^{{tree}}"),
        candidate_state_hash="d" * 64, candidate_receipt_hash="e" * 64,
        acceptance_receipt_hash=acceptance.receipt_hash, reviewer_id=acceptance.reviewer_id,
        verifier_artifact_hash="f" * 64, canonical_root=str(root.resolve()),
        canonical_branch="nexus/integration/canary", expected_canonical_head=base,
        canonical_dirty_baseline=_status_hash(root), integration_plan_hash="1" * 64,
        strategy="EPHEMERAL_WORKTREE_MERGE_THEN_APPLY", verification_commands_hash="2" * 64,
        post_apply_commands_hash="3" * 64, cleanup_target_id="target-1",
        cleanup_target_path=str(root / "target"), durable_ref="refs/nexus-candidate/task-1",
        cleanup_requested=True, rollback="retain target", issued_at="2026-08-02T00:00:00+00:00",
        action_set=("ACCEPT_DISPOSITION", "INTEGRATION_STAGING", "APPLY_VERIFIED_INTEGRATION", "POST_INTEGRATION_VERIFY", "CLEANUP_OWNED_TARGET"),
    )


def test_integration_without_external_acceptance_is_blocked(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    with pytest.raises(RuntimeError, match="external acceptance"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=base,
                expected_status_hash=_status_hash(root),
            staging_root=tmp_path / "stage", apply=True,
            external_acceptance=None, authorization=None,
        )
    assert _git(root, "rev-parse", "HEAD") == base


def test_integration_without_owner_authorization_is_blocked(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    with pytest.raises(RuntimeError, match="Owner authorization"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=base,
            expected_status_hash=_status_hash(root),
            staging_root=tmp_path / "stage", apply=True,
            external_acceptance=_acceptance(candidate), authorization=None,
        )


def test_authorization_is_consumed_once():
    authorization = {"approval_scope": "ALLOW_ACTION_ONCE"}
    consumed = TargetIntegrationLifecycle.consume_authorization(authorization, consumed_at="2026-08-02T00:00:00+00:00")
    assert consumed["consumed_at"]
    with pytest.raises(RuntimeError, match="ALREADY_CONSUMED"):
        TargetIntegrationLifecycle.consume_authorization(consumed, consumed_at="2026-08-02T00:01:00+00:00")


def test_authorization_candidate_drift_is_blocked(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    receipt = _acceptance(candidate)
    auth = _authorization(root, base, candidate, receipt)
    with pytest.raises(RuntimeError, match="candidate drift"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit="f" * 40,
            expected_canonical_head=base, staging_root=str(tmp_path / "stage"),
            external_acceptance=receipt, authorization=auth,
        )


def test_authorization_task_card_drift_is_blocked(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    receipt = _acceptance(candidate)
    auth = _authorization(root, base, candidate, receipt)
    with pytest.raises(RuntimeError, match="task card drift"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=base, staging_root=str(tmp_path / "stage"),
            external_acceptance=receipt, authorization=auth,
            current_task_card_hash="f" * 64,
        )


def test_authorization_plan_drift_is_blocked(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    receipt = _acceptance(candidate)
    auth = _authorization(root, base, candidate, receipt)
    with pytest.raises(RuntimeError, match="integration plan drift"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=base, staging_root=str(tmp_path / "stage"),
            external_acceptance=receipt, authorization=auth,
            current_integration_plan_hash="f" * 64,
        )


def test_target_lifecycle_adapter_does_not_execute_raw_git_mutations():
    source = Path(TargetIntegrationLifecycle.__module__.replace(".", "/") + ".py").read_text()
    assert "subprocess" not in source
    assert "git merge" not in source
    assert "worktree add" not in source
    assert "worktree remove" not in source


def test_integration_delegates_to_controlled_integration_manager():
    assert hasattr(TargetIntegrationLifecycle, "delegate_integration")


def test_cleanup_delegates_to_worktree_manager():
    assert hasattr(TargetIntegrationLifecycle, "delegate_cleanup")


def test_dirty_canonical_blocks_apply_even_when_status_hash_matches(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    (root / "value.txt").write_text("unrelated dirty\n")
    with pytest.raises(RuntimeError, match="canonical.*clean"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=base,
                expected_status_hash=_status_hash(root),
                staging_root=tmp_path / "stage", apply=True,
                external_acceptance=_acceptance(candidate), authorization=_authorization(root, base, candidate, _acceptance(candidate)),
        )


def test_untracked_canonical_blocks_apply(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    (root / "untracked.txt").write_text("untracked\n")
    with pytest.raises(RuntimeError, match="canonical.*clean"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=base,
                expected_status_hash=_status_hash(root),
                staging_root=tmp_path / "stage", apply=True,
                external_acceptance=_acceptance(candidate), authorization=_authorization(root, base, candidate, _acceptance(candidate)),
        )


def test_forged_cleanup_decision_cannot_remove_worktree(tmp_path: Path):
    root, _, _ = _repo(tmp_path)
    target = tmp_path / "target"
    _git(root, "worktree", "add", "--detach", str(target), "HEAD")
    decision = CleanupDecision(
        schema="nexus.target_cleanup_decision.v1", decision="ELIGIBLE",
        task_id="task-1", target_id="target-1",
    )
    result = TargetIntegrationLifecycle.cleanup_target(
        decision=decision, target_path=target, canonical_root=root, apply=True,
        authorization=None, lifecycle_state=None,
    )
    assert result["performed"] is False
    assert target.exists()


def test_cleanup_without_integration_receipt_is_blocked(tmp_path: Path):
    root, _, _ = _repo(tmp_path)
    target = tmp_path / "target"
    _git(root, "worktree", "add", "--detach", str(target), "HEAD")
    decision = TargetIntegrationLifecycle.cleanup_decision(
        task_id="task-1", target_id="target-1", target_owner="task-1",
        target_is_canonical=False, reviewer_worktree=False, dirty=False,
        untracked=False, active_process=False, accepted=True, integrated=True,
        canonical_contains_result=True, durable_ref_verified=True,
        receipts_complete=False, unique_unprotected_commits=False,
    )
    result = TargetIntegrationLifecycle.cleanup_target(
        decision=decision, target_path=target, canonical_root=root, apply=True,
        authorization={"cleanup_requested": True}, lifecycle_state={"status": "INTEGRATED"},
    )
    assert result["performed"] is False
    assert target.exists()


def test_cleanup_without_durable_ref_is_blocked(tmp_path: Path):
    root, _, _ = _repo(tmp_path)
    target = tmp_path / "target"
    _git(root, "worktree", "add", "--detach", str(target), "HEAD")
    decision = TargetIntegrationLifecycle.cleanup_decision(
        task_id="task-1", target_id="target-1", target_owner="task-1",
        target_is_canonical=False, reviewer_worktree=False, dirty=False,
        untracked=False, active_process=False, accepted=True, integrated=True,
        canonical_contains_result=True, durable_ref_verified=False,
        receipts_complete=True, unique_unprotected_commits=False,
    )
    result = TargetIntegrationLifecycle.cleanup_target(
        decision=decision, target_path=target, canonical_root=root, apply=True,
        authorization={"cleanup_requested": True}, lifecycle_state={"status": "INTEGRATED"},
    )
    assert result["performed"] is False
    assert target.exists()


def test_post_apply_verification_failure_blocks_cleanup(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    with pytest.raises(RuntimeError, match="post-apply"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=base,
                expected_status_hash=_status_hash(root),
                staging_root=tmp_path / "stage", apply=True,
                external_acceptance=_acceptance(candidate), authorization=_authorization(root, base, candidate, _acceptance(candidate)),
            post_apply_commands=(("/bin/sh", "-c", "exit 1"),),
        )


def test_multiple_active_targets_returns_typed_block():
    decision = TargetIntegrationLifecycle.resolve_target(
        task_id="task-1", campaign_id="campaign", attempt_id="attempt-2",
        base_revision="a" * 40,
        existing_targets=[
            {"task_id": "task-1", "campaign_id": "campaign", "target_id": "t1", "target_path": "/tmp/t1", "target_branch": "b1", "base_revision": "a" * 40},
            {"task_id": "task-1", "campaign_id": "campaign", "target_id": "t2", "target_path": "/tmp/t2", "target_branch": "b2", "base_revision": "a" * 40},
        ],
    )
    assert decision.mode is TargetResolutionMode.BLOCK
    assert decision.target_id is None
    assert decision.reason == "SERIAL_TASK_MULTIPLE_ACTIVE_TARGETS"


def _receipt_service(tmp_path: Path) -> SelfHostedTaskService:
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("task-1", {
        "task_id": "task-1", "attempt_id": "attempt-1", "status": "INTEGRATING",
        "promotion_status": "INTEGRATING", "status_history": [], "request": {},
    })
    return service


def test_integration_receipt_survives_fresh_service_reload(tmp_path: Path):
    service = _receipt_service(tmp_path)
    returned_state = TargetIntegrationLifecycle.persist_receipt(
        service, "task-1", receipt_name="integration_receipt",
        receipt={"schema": "nexus.integration_receipt.v1", "post_apply_verified": True},
    )
    fresh = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    assert TargetIntegrationLifecycle.reload_receipt(fresh, "task-1", receipt_name="integration_receipt") == returned_state["integration_receipt"]


def test_cleanup_receipt_survives_fresh_service_reload(tmp_path: Path):
    service = _receipt_service(tmp_path)
    receipt = {"schema": "nexus.target_cleanup_receipt.v1", "decision": "RETAIN"}
    TargetIntegrationLifecycle.persist_receipt(service, "task-1", receipt_name="cleanup_receipt", receipt=receipt)
    fresh = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    assert TargetIntegrationLifecycle.reload_receipt(fresh, "task-1", receipt_name="cleanup_receipt") == receipt


def test_persisted_receipts_equal_returned_receipts():
    assert hasattr(TargetIntegrationLifecycle, "persist_receipt")
    assert hasattr(TargetIntegrationLifecycle, "reload_receipt")


def test_authorize_default_action_set_excludes_branch_deletion(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    receipt = _acceptance(candidate)
    preview = TargetIntegrationLifecycle.build_preview(
        task_id="task-1", target_id="target-1", candidate_commit=candidate,
        acceptance=receipt, canonical_branch="nexus/integration/canary",
        expected_canonical_head=base, verification_commands=(),
        cleanup_target_id="target-1", rollback="retain target",
    )
    auth = TargetIntegrationLifecycle.authorize(
        task_id="task-1", campaign_id="campaign-1", task_card_hash="c" * 64,
        candidate_commit=candidate, candidate_receipt_hash="d" * 64,
        acceptance_receipt_hash=receipt.receipt_hash, canonical_root=str(root),
        canonical_branch="nexus/integration/canary", expected_canonical_head=base,
        canonical_dirty_baseline=_status_hash(root), preview=preview,
        cleanup_target_id="target-1", cleanup_target_path=str(root / "target"),
        durable_ref="refs/nexus-candidate/task-1", rollback="retain target",
        issued_at="2026-08-02T00:00:00+00:00",
    )
    assert auth.action_set == (
        "ACCEPT_DISPOSITION", "INTEGRATION_STAGING", "APPLY_VERIFIED_INTEGRATION",
        "POST_INTEGRATION_VERIFY", "CLEANUP_OWNED_TARGET",
    )


def test_owner_finish_delegates_full_authorized_integration_then_cleanup(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    receipt = _acceptance(candidate)
    auth = _authorization(root, base, candidate, receipt)
    target = tmp_path / "targets" / "task-1"
    target.parent.mkdir()
    _git(root, "worktree", "add", "-b", "nexus/task/task-1", str(target), base)
    _git(target, "merge", "--ff-only", candidate)
    durable_ref = "refs/nexus-candidate/task-1"
    _git(root, "update-ref", durable_ref, candidate)
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = {
        "task_id": "task-1", "what": "authorized integration", "why": "closure",
        "controller_revision": base, "target_base_revision": base,
        "controller_repo_root": str(root), "target_repo_root": str(target),
        "target_worktree_root": str(target.parent), "allowed_files": ["value.txt"],
        "verifier_commands": ["/usr/bin/true"], "worker": "codex",
    }
    contract = service.build_contract(request)
    # Approval recomputes the verified receipt hash (#1758): bind a real one.
    verified_receipt = {
        **_verified_gate_proof(root, contract),
        "verifier_evidence": _verifier_evidence("/usr/bin/true"),
        "verified": True,
    }
    verified_receipt_hash = _receipt_hash(verified_receipt)
    auth = replace(auth, candidate_receipt_hash=verified_receipt_hash)
    lease_id = WorktreeManager(root_dir=str(target.parent), create_root=False)._lease_id(
        contract, target, "nexus/task/task-1"
    )
    service._write_state("task-1", {
        "task_id": "task-1", "attempt_id": "attempt-1", "status": "CANDIDATE_CAPTURED",
        "promotion_status": "PENDING_HUMAN_APPROVAL", "request": request,
        "contract": contract.model_dump(mode="json"), "contract_hash": contract.contract_hash,
        "task_card_hash": "c" * 64,
        "verified_receipt": verified_receipt, "integration_verifier_manifest": _manifest(verified_receipt, contract),
        "promotion_packet": {
            "candidate_commit_sha": candidate,
            "candidate_tree_sha": _git(root, "rev-parse", f"{candidate}^{{tree}}"),
            "candidate_state_hash": "d" * 64, "verified_receipt_hash": verified_receipt_hash,
        },
        "candidate_ref": durable_ref,
        "lease": {
            "schema": "nexus.target_worktree_lease.v1", "lease_id": lease_id,
            "task_id": "task-1", "controller_revision": base, "target_base_revision": base,
            "target_worktree": str(target), "target_branch": "nexus/task/task-1",
            "initial_head": base, "initial_status_sha256": "0" * 64,
            "controller_status_sha256": "0" * 64, "created_from_exact_revision": True,
            "commit_created": True, "merge_performed": False,
        },
    })
    context = _bound_tracked_approval("task-1", contract.contract_hash)
    result = service.owner_finish(
        "task-1", candidate_commit_sha=candidate,
        candidate_tree_sha=_git(root, "rev-parse", f"{candidate}^{{tree}}"),
        candidate_state_hash="d" * 64, verified_receipt_hash=verified_receipt_hash,
        integration_branch="nexus/integration/canary", approval_context=context,
        external_acceptance=receipt.to_dict(), integration_authorization={
            **auth.to_dict(), "canonical_branch": "nexus/integration/canary",
            "cleanup_target_path": str(target), "durable_ref": durable_ref,
        },
    )
    assert result["status"] == "INTEGRATED_AND_CLEANED"
    assert result["cleanup_status"] == "CLEANED"
    assert result["finalization_receipt"]["terminal"]["final_status"] == "INTEGRATED_AND_CLEANED"
    stored = service._read_state("task-1") or service._latest_archived_state("task-1")[1]
    assert stored["integration_receipt"]["post_apply_verified"] is True
    assert stored["integration_receipt"]["acceptance_receipt_hash"] == receipt.receipt_hash
    assert stored["cleanup_receipt"]["performed"] is True
    assert stored["finalization_receipt"] == result["finalization_receipt"]
    fresh_integration = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    persisted_integration = fresh_integration._read_state("task-1") or fresh_integration._latest_archived_state("task-1")[1]
    assert persisted_integration["integration_receipt"] == result["integration_receipt"]
    fresh = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    persisted = fresh._read_state("task-1") or fresh._latest_archived_state("task-1")[1]
    assert persisted["cleanup_receipt"] == result["cleanup_receipt"]
    assert persisted["cleanup_receipt_hash"] == hashlib.sha256(
        json.dumps(result["cleanup_receipt"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    assert not target.exists()
    assert _git(root, "show-ref", "--verify", "refs/heads/nexus/task/task-1")
    assert _git(root, "show-ref", "--verify", durable_ref)


def test_owner_finish_single_confirmation_integrates_and_cleans_owned_target(tmp_path: Path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    calls: list[str] = []

    monkeypatch.setattr(service, "approve_promotion", lambda task_id, **kwargs: calls.append("approve") or {"status": "APPROVED", "promotion_status": "APPROVED"})
    monkeypatch.setattr(service, "integrate_approved", lambda task_id, *, integration_branch: calls.append("integrate") or {"status": "INTEGRATED", "promotion_status": "INTEGRATED", "integration_receipt": {"schema": "nexus.integration_receipt.v1"}})
    monkeypatch.setattr(service, "cleanup_tasks", lambda *, task_id, dry_run: calls.append("cleanup") or {"dry_run": False, "decisions": [{"task_id": task_id, "cleanup_performed": True, "cleanup_eligible": True, "cleanup_decision": "REMOVED", "cleanup_receipt": {"performed": True, "eligible": True, "decision": "REMOVED", "target_present_after": False}}]})
    monkeypatch.setattr(service, "archive_states", lambda *, dry_run: calls.append("archive") or {"dry_run": dry_run, "entries": []})

    result = service.owner_finish(
        "single-confirmation", candidate_commit_sha="a" * 40,
        candidate_tree_sha="b" * 40, candidate_state_hash="c" * 64,
        verified_receipt_hash="d" * 64, external_acceptance={"passed": True},
        integration_authorization={"cleanup_requested": True, "cleanup_target_path": str(tmp_path / "target"), "action_set": ["CLEANUP_OWNED_TARGET"]},
    )

    assert calls == ["approve", "integrate", "cleanup", "archive"]
    assert result["status"] == "INTEGRATED_AND_CLEANED"


def test_owner_finish_retains_noneligible_target_with_typed_reason(tmp_path: Path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    calls: list[str] = []
    monkeypatch.setattr(service, "approve_promotion", lambda task_id, **kwargs: {"status": "APPROVED", "promotion_status": "APPROVED"})
    monkeypatch.setattr(service, "integrate_approved", lambda task_id, *, integration_branch: {"status": "INTEGRATED", "promotion_status": "INTEGRATED", "integration_receipt": {"schema": "nexus.integration_receipt.v1"}})
    monkeypatch.setattr(service, "cleanup_tasks", lambda *, task_id, dry_run: calls.append("cleanup") or {"dry_run": False, "decisions": [{"task_id": task_id, "cleanup_performed": False, "cleanup_eligible": False, "cleanup_decision": "BLOCKED_BY_PROCESS", "cleanup_blocker": "active process uses Target", "cleanup_receipt": {"performed": False, "eligible": False, "decision": "BLOCKED_BY_PROCESS", "blocker": "active process uses Target", "target_present_after": True}}]})
    monkeypatch.setattr(service, "archive_states", lambda **kwargs: (_ for _ in ()).throw(AssertionError("retained state must not archive")))

    result = service.owner_finish(
        "retained", candidate_commit_sha="a" * 40,
        candidate_tree_sha="b" * 40, candidate_state_hash="c" * 64,
        verified_receipt_hash="d" * 64, external_acceptance={"passed": True},
        integration_authorization={"cleanup_requested": True, "cleanup_target_path": str(tmp_path / "target"), "action_set": ["CLEANUP_OWNED_TARGET"]},
    )

    assert calls == ["cleanup"]
    assert result["status"] == "INTEGRATED_TARGET_RETAINED"
    assert result["retention_reason"] == "active process uses Target"
    assert result["next_action"] == "retry_cleanup"
    assert result["archive_eligible"] is False


def test_owner_finish_does_not_archive_cleanup_pending_or_retained_state(tmp_path: Path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    order: list[str] = []
    monkeypatch.setattr(service, "approve_promotion", lambda task_id, **kwargs: {"status": "APPROVED", "promotion_status": "APPROVED"})
    monkeypatch.setattr(service, "integrate_approved", lambda task_id, *, integration_branch: order.append("integrate") or {"status": "INTEGRATED", "promotion_status": "INTEGRATED"})
    monkeypatch.setattr(service, "cleanup_tasks", lambda *, task_id, dry_run: order.append("cleanup") or {"dry_run": False, "decisions": [{"cleanup_performed": False, "cleanup_eligible": False, "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES", "cleanup_blocker": "dirty Target"}]})
    monkeypatch.setattr(service, "archive_states", lambda **kwargs: order.append("archive") or {"entries": []})
    result = service.owner_finish(
        "no-premature-archive", candidate_commit_sha="a" * 40,
        candidate_tree_sha="b" * 40, candidate_state_hash="c" * 64,
        verified_receipt_hash="d" * 64, external_acceptance={"passed": True},
        integration_authorization={"cleanup_requested": True, "cleanup_target_path": str(tmp_path / "target"), "action_set": ["CLEANUP_OWNED_TARGET"]},
    )
    assert result["status"] == "INTEGRATED_TARGET_RETAINED"
    assert order == ["integrate", "cleanup"]


def test_post_apply_physical_truth_is_typed_and_persistable(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    receipt = _acceptance(candidate)
    auth = _authorization(root, base, candidate, receipt)
    state = {
        "task_id": "task-1", "contract": {"controller_repo_root": str(root)},
        "promotion_packet": {"candidate_commit_sha": candidate},
        "integration_authorization": auth.to_dict(),
        "external_acceptance": receipt.to_dict(),
        "lease": {"target_branch": "nexus/task/task-1"},
    }
    with pytest.raises(RuntimeError) as raised:
        ControlledIntegrationManager(integration_root=root).integrate_authorized_task_state(
            state, integration_branch="nexus/integration/canary",
            staging_root=tmp_path / "stage", post_apply_commands=(("/bin/sh", "-c", "exit 1"),),
        )
    assert raised.value.merge_performed is True
    assert raised.value.post_apply_verified is False
    assert raised.value.branch_head_before == base
    assert raised.value.branch_head_after != base
    assert raised.value.integration_result_sha == raised.value.branch_head_after


def _separate_controller_worktree(tmp_path: Path, root: Path, base: str) -> Path:
    controller = tmp_path / "controller"
    _git(root, "worktree", "add", "--detach", str(controller), base)
    return controller.resolve()


def _separate_controller(tmp_path: Path) -> tuple[Path, Path, str, str]:
    """Primary checkout on main plus a detached Controller worktree (#1939)."""
    root, base, candidate = _repo(tmp_path)
    _git(root, "checkout", "main")
    return root, _separate_controller_worktree(tmp_path, root, base), base, candidate


def _separate_controller_integrate(
    tmp_path: Path, controller: Path, base: str, candidate: str, **kwargs
):
    receipt = _acceptance(candidate)
    auth = _authorization(controller, base, candidate, receipt)
    state = {
        "task_id": "task-1",
        "contract": {"controller_repo_root": str(controller)},
        "promotion_packet": {"candidate_commit_sha": candidate},
        "integration_authorization": auth.to_dict(),
        "external_acceptance": receipt.to_dict(),
        "lease": {"target_branch": "nexus/task/task-1"},
    }
    return ControlledIntegrationManager(
        integration_root=controller
    ).integrate_authorized_task_state(
        state,
        integration_branch="nexus/integration/canary",
        staging_root=tmp_path / "stage",
        **kwargs,
    )


def test_separate_controller_post_apply_output_never_lands_in_controller(tmp_path: Path):
    """#2230 F3(b): post-apply output must not poison the Controller worktree."""
    _root, controller, base, candidate = _separate_controller(tmp_path)
    result = _separate_controller_integrate(
        tmp_path,
        controller,
        base,
        candidate,
        post_apply_commands=(("/bin/sh", "-c", "echo out > post-apply-output.txt"),),
    )
    assert result.post_apply_verified is True
    assert _git(controller, "status", "--porcelain=v1", "--untracked-files=all", "--ignored") == ""
    assert _git(controller, "rev-parse", "HEAD") == base
    assert not (tmp_path / "stage" / ".post-apply" / "task-1").exists()
    assert ".post-apply" not in _git(controller, "worktree", "list", "--porcelain")


def test_separate_controller_post_apply_verifies_integrated_tree(tmp_path: Path):
    """#2230 F3(b): post-apply checks the integrated commit, not the stale Controller."""
    _root, controller, base, candidate = _separate_controller(tmp_path)
    result = _separate_controller_integrate(
        tmp_path,
        controller,
        base,
        candidate,
        post_apply_commands=(
            ("/bin/sh", "-c", "grep -qx candidate value.txt"),
            (
                "/bin/sh",
                "-c",
                'test "$(git rev-parse HEAD)" = "$(git rev-parse nexus/integration/canary)"',
            ),
        ),
    )
    assert result.merge_performed is True
    assert result.integration_commit_sha == _git(
        controller, "rev-parse", "nexus/integration/canary"
    )
    assert (controller / "value.txt").read_text() == "base\n"


def test_separate_controller_pending_task_card_does_not_block_integration(tmp_path: Path):
    """#2230 F3(a): an untracked pending Task Card under tasks/ is not dirt."""
    _root, controller, base, candidate = _separate_controller(tmp_path)
    card = controller / "tasks" / "active" / "pending-card.md"
    card.parent.mkdir(parents=True)
    card.write_text("pending\n")
    result = _separate_controller_integrate(tmp_path, controller, base, candidate)
    assert result.merge_performed is True
    assert (
        _git(controller, "merge-base", "--is-ancestor", candidate, "nexus/integration/canary") == ""
    )
    assert card.read_text() == "pending\n"
    assert _git(controller, "rev-parse", "HEAD") == base


@pytest.mark.parametrize("dirt", ["untracked-outside", "tracked-edit", "tasks-symlink"])
def test_separate_controller_other_dirt_still_blocks_integration(tmp_path: Path, dirt: str):
    _root, controller, base, candidate = _separate_controller(tmp_path)
    if dirt == "untracked-outside":
        (controller / "stray.txt").write_text("stray\n")
    elif dirt == "tracked-edit":
        (controller / "value.txt").write_text("edited\n")
    else:
        (controller / "tasks").mkdir()
        (controller / "tasks" / "card.md").symlink_to(controller / "value.txt")
    with pytest.raises(RuntimeError, match="canonical.*clean"):
        _separate_controller_integrate(tmp_path, controller, base, candidate)
    assert _git(controller, "rev-parse", "nexus/integration/canary") == base


def test_controller_on_integration_branch_still_rejects_pending_task_card(tmp_path: Path):
    """When apply fast-forwards the Controller worktree, it stays fully clean."""
    root, base, candidate = _repo(tmp_path)
    (root / "tasks").mkdir()
    (root / "tasks" / "pending-card.md").write_text("pending\n")
    with pytest.raises(RuntimeError, match="canonical.*clean"):
        _separate_controller_integrate(tmp_path, root.resolve(), base, candidate)
    assert _git(root, "rev-parse", "HEAD") == base


def test_primary_checkout_on_main_still_rejects_pending_task_card(tmp_path: Path):
    """#2230 F3: only a separate detached Controller may hold pending cards."""
    root, base, candidate = _repo(tmp_path)
    _git(root, "checkout", "main")
    (root / "tasks").mkdir()
    (root / "tasks" / "pending-card.md").write_text("pending\n")
    with pytest.raises(RuntimeError, match="canonical.*clean"):
        _separate_controller_integrate(tmp_path, root.resolve(), base, candidate)
    assert _git(root, "rev-parse", "nexus/integration/canary") == base


def test_linked_worktree_on_a_branch_still_rejects_pending_task_card(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    _git(root, "checkout", "main")
    controller = tmp_path / "on-branch"
    _git(root, "worktree", "add", "-b", "nexus/other", str(controller), base)
    (controller / "tasks").mkdir()
    (controller / "tasks" / "pending-card.md").write_text("pending\n")
    with pytest.raises(RuntimeError, match="canonical.*clean"):
        _separate_controller_integrate(tmp_path, controller.resolve(), base, candidate)
    assert _git(root, "rev-parse", "nexus/integration/canary") == base


@pytest.mark.parametrize("trick", ["symlinked-dir", "nested-dot-git", "hardlink"])
def test_separate_controller_task_card_path_tricks_block_integration(tmp_path: Path, trick: str):
    _root, controller, base, candidate = _separate_controller(tmp_path)
    tasks = controller / "tasks"
    tasks.mkdir()
    if trick == "symlinked-dir":
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "payload.txt").write_text("outside\n")
        (tasks / "symdir").symlink_to(outside, target_is_directory=True)
    elif trick == "nested-dot-git":
        (tasks / "x" / ".git").mkdir(parents=True)
        (tasks / "x" / ".git" / "config").write_text("[core]\n")
    else:
        outside = tmp_path / "outside.txt"
        outside.write_text("outside\n")
        (tasks / "card.md").hardlink_to(outside)
    with pytest.raises(RuntimeError, match="canonical.*clean"):
        _separate_controller_integrate(tmp_path, controller, base, candidate)
    assert _git(controller, "rev-parse", "nexus/integration/canary") == base


@pytest.mark.parametrize("kind", ["directory", "dangling-symlink"])
def test_pre_existing_post_apply_path_is_refused_and_kept(tmp_path: Path, kind: str):
    """A path this run did not create is never removed, and the error is not masked."""
    _root, controller, base, candidate = _separate_controller(tmp_path)
    occupied = tmp_path / "stage" / ".post-apply" / "task-1"
    occupied.parent.mkdir(parents=True)
    if kind == "directory":
        occupied.mkdir()
        (occupied / "keep.txt").write_text("keep\n")
    else:
        occupied.symlink_to(tmp_path / "missing-target")
    with pytest.raises(RuntimeError, match="post-apply verification Target already exists"):
        _separate_controller_integrate(
            tmp_path,
            controller,
            base,
            candidate,
            post_apply_commands=(("/bin/sh", "-c", "true"),),
        )
    assert os.path.lexists(occupied)
    if kind == "directory":
        assert (occupied / "keep.txt").read_text() == "keep\n"
    assert _git(controller, "rev-parse", "nexus/integration/canary") == base
    assert "stage" not in _git(controller, "worktree", "list", "--porcelain")


def test_dangling_symlink_staging_path_is_refused_and_kept(tmp_path: Path):
    _root, controller, base, candidate = _separate_controller(tmp_path)
    occupied = tmp_path / "stage" / "task-1"
    occupied.parent.mkdir(parents=True)
    occupied.symlink_to(tmp_path / "missing-target")
    with pytest.raises(RuntimeError, match="staging Target already exists"):
        _separate_controller_integrate(tmp_path, controller, base, candidate)
    assert occupied.is_symlink()
    assert _git(controller, "rev-parse", "nexus/integration/canary") == base


def test_post_apply_cleanup_failure_keeps_typed_applied_truth(tmp_path: Path):
    """Claude F1: a locked post-apply worktree must not erase merge_performed=True."""
    _root, controller, base, candidate = _separate_controller(tmp_path)
    with pytest.raises(IntegrationExecutionError) as raised:
        _separate_controller_integrate(
            tmp_path,
            controller,
            base,
            candidate,
            post_apply_commands=(("/bin/sh", "-c", 'git worktree lock "$PWD"'),),
        )
    error = raised.value
    assert error.merge_performed is True
    assert error.stage == "POST_APPLY_CLEANUP"
    assert error.post_apply_verified is True
    assert error.cleanup_failure and "task-1" in error.cleanup_failure
    assert error.branch_head_after == _git(controller, "rev-parse", "nexus/integration/canary")
    assert error.branch_head_after != base
    assert not (tmp_path / "stage" / "task-1").exists()
    locked = tmp_path / "stage" / ".post-apply" / "task-1"
    _git(controller, "worktree", "unlock", str(locked))
    _git(controller, "worktree", "remove", "--force", str(locked))


def test_post_apply_failure_with_cleanup_failure_keeps_verification_stage(tmp_path: Path):
    _root, controller, base, candidate = _separate_controller(tmp_path)
    with pytest.raises(IntegrationExecutionError) as raised:
        _separate_controller_integrate(
            tmp_path,
            controller,
            base,
            candidate,
            post_apply_commands=(("/bin/sh", "-c", 'git worktree lock "$PWD"; exit 3'),),
        )
    error = raised.value
    assert error.stage == "POST_APPLY_VERIFICATION"
    assert error.merge_performed is True
    assert error.post_apply_verified is False
    assert "post-apply verification failed" in error.failure_reason
    assert error.cleanup_failure
    locked = tmp_path / "stage" / ".post-apply" / "task-1"
    _git(controller, "worktree", "unlock", str(locked))
    _git(controller, "worktree", "remove", "--force", str(locked))


def test_post_apply_failure_removes_its_worktree_and_stays_typed(tmp_path: Path):
    _root, controller, base, candidate = _separate_controller(tmp_path)
    with pytest.raises(IntegrationExecutionError) as raised:
        _separate_controller_integrate(
            tmp_path,
            controller,
            base,
            candidate,
            post_apply_commands=(("/bin/sh", "-c", "echo dirt > dirt.txt; exit 1"),),
        )
    assert raised.value.merge_performed is True
    assert raised.value.cleanup_failure is None
    assert not (tmp_path / "stage" / ".post-apply" / "task-1").exists()
    assert ".post-apply" not in _git(controller, "worktree", "list", "--porcelain")
    assert _git(controller, "status", "--porcelain=v1", "--untracked-files=all") == ""


def _bound_tracked_approval(task_id: str, contract_hash: str) -> dict:
    """Full versioned grant naming its approver, bound to task, attempt and action (#1758)."""
    now = datetime.now(timezone.utc)
    return {
        "schema": "nexus.approval.v2", "approval_id": f"approval-{task_id}",
        "approved_by": "owner", "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "bound_task_id": task_id, "bound_attempt_id": "attempt-1",
        "bound_action_type": "CANDIDATE_APPROVE", "approval_scope": "ALLOW_ACTION_ONCE",
        "contract_kind": "TRACKED_TASK_CARD", "contract_hash": contract_hash, "task_card_hash": "c" * 64,
        "tool_manifest_hash": "1" * 64, "full_tool_schema_hash": "2" * 64,
        "permission_policy_hash": "3" * 64, "lifecycle_revision": "test-lifecycle-revision",
        "server_instance_id": "test-server",
    }


def test_service_post_apply_failure_persists_physical_truth_and_blocks_cleanup(tmp_path: Path, monkeypatch):
    root, base, candidate = _repo(tmp_path)
    receipt = replace(_acceptance(candidate), task_id="post-apply-task")
    auth = replace(
        _authorization(root, base, candidate, receipt),
        task_id="post-apply-task",
        acceptance_receipt_hash=receipt.receipt_hash,
        cleanup_target_id="post-apply-task",
    )
    target = tmp_path / "targets" / "post-apply-task"
    target.parent.mkdir()
    _git(root, "worktree", "add", "-b", "nexus/task/post-apply-task", str(target), base)
    _git(target, "merge", "--ff-only", candidate)
    durable_ref = "refs/nexus-candidate/post-apply-task"
    _git(root, "update-ref", durable_ref, candidate)
    # Paths under /tmp are rewritten to the default target root; pin it so the
    # persisted contract keeps the real target the lease was created for.
    monkeypatch.setenv("NEXUS_TARGET_ROOT_OVERRIDE", str(target.parent))
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = {
        "task_id": "post-apply-task", "what": "post apply truth", "why": "closure",
        "controller_revision": base, "target_base_revision": base,
        "controller_repo_root": str(root), "target_repo_root": str(target),
        "target_worktree_root": str(target.parent), "allowed_files": ["value.txt"],
        "verifier_commands": ["/usr/bin/true"], "worker": "codex",
    }
    contract = service.build_contract(request)
    # Approval recomputes the verified receipt hash (#1758): bind a real one.
    verified_receipt = {
        **_verified_gate_proof(root, contract),
        "verifier_evidence": _verifier_evidence("/usr/bin/true"),
        "verified": True,
    }
    verified_receipt_hash = _receipt_hash(verified_receipt)
    auth = replace(auth, candidate_receipt_hash=verified_receipt_hash)
    lease_id = WorktreeManager(root_dir=str(target.parent), create_root=False)._lease_id(contract, target, "nexus/task/post-apply-task")
    packet = {
        "candidate_commit_sha": candidate,
        "candidate_tree_sha": _git(root, "rev-parse", f"{candidate}^{{tree}}"),
        "candidate_state_hash": "d" * 64, "verified_receipt_hash": verified_receipt_hash,
    }
    service._write_state("post-apply-task", {
        "task_id": "post-apply-task", "attempt_id": "attempt-1",
        "status": "CANDIDATE_CAPTURED", "promotion_status": "PENDING_HUMAN_APPROVAL",
        "request": request, "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash, "task_card_hash": "c" * 64,
        "verified_receipt": verified_receipt, "integration_verifier_manifest": _manifest(verified_receipt, contract),
        "promotion_packet": packet, "candidate_ref": durable_ref,
        "post_apply_commands": [["/bin/sh", "-c", "exit 1"]],
        "lease": {
            "schema": "nexus.target_worktree_lease.v1", "lease_id": lease_id,
            "task_id": "post-apply-task", "controller_revision": base,
            "target_base_revision": base, "target_worktree": str(target),
            "target_branch": "nexus/task/post-apply-task", "initial_head": base,
            "initial_status_sha256": "0" * 64, "controller_status_sha256": "0" * 64,
            "created_from_exact_revision": True, "commit_created": True,
            "merge_performed": False,
        },
    })
    context = _bound_tracked_approval("post-apply-task", contract.contract_hash)
    with pytest.raises(RuntimeError, match="post-apply verification failed"):
        service.owner_finish(
            "post-apply-task", candidate_commit_sha=candidate,
            candidate_tree_sha=packet["candidate_tree_sha"], candidate_state_hash="d" * 64,
            verified_receipt_hash=verified_receipt_hash, integration_branch="nexus/integration/canary",
            approval_context=context, external_acceptance=receipt.to_dict(),
            integration_authorization={**auth.to_dict(), "canonical_branch": "nexus/integration/canary", "cleanup_target_path": str(target), "durable_ref": durable_ref},
        )
    branch_head = _git(root, "rev-parse", "nexus/integration/canary")
    assert branch_head != base
    assert _git(root, "merge-base", "--is-ancestor", candidate, branch_head) == ""
    state = service._read_state("post-apply-task")
    assert state["status"] == "INTEGRATION_VERIFY_FAILED_AFTER_APPLY"
    assert state["merge_performed"] is True
    assert state["integration_result_sha"] == branch_head
    assert state["integration_execution"]["post_apply_verified"] is False
    cleanup = service.cleanup_tasks(task_id="post-apply-task", dry_run=False)
    assert cleanup["decisions"][0]["cleanup_performed"] is False
    assert "post-apply" in cleanup["decisions"][0]["cleanup_blocker"]


def test_post_apply_failure_cannot_retry_integration(tmp_path: Path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("post-apply-retry", {"task_id": "post-apply-retry", "status": "INTEGRATION_VERIFY_FAILED_AFTER_APPLY", "promotion_status": "INTEGRATION_VERIFY_FAILED_AFTER_APPLY", "merge_performed": True, "approved_binding": {"candidate_commit_sha": "a" * 40}})
    with pytest.raises(RuntimeError, match="INTEGRATION_ALREADY_APPLIED_RETRY_FORBIDDEN"):
        service.retry_integration("post-apply-retry")


def test_post_apply_failure_never_runs_cleanup(tmp_path: Path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("post-apply-cleanup", {"task_id": "post-apply-cleanup", "status": "INTEGRATION_VERIFY_FAILED_AFTER_APPLY", "promotion_status": "INTEGRATION_VERIFY_FAILED_AFTER_APPLY", "merge_performed": True, "lease": {}})
    result = service.cleanup_tasks(task_id="post-apply-cleanup", dry_run=False)
    assert result["decisions"][0]["cleanup_performed"] is False
    assert "post-apply" in result["decisions"][0]["cleanup_blocker"]


def test_finalization_failure_and_retention_actions_remain_fail_closed():
    post_apply = SelfHostedTaskService._task_action_envelope({
        "task_id": "post-apply-action", "status": "INTEGRATION_VERIFY_FAILED_AFTER_APPLY",
        "promotion_status": "INTEGRATION_VERIFY_FAILED_AFTER_APPLY", "merge_performed": True,
    })
    assert post_apply["action_state"] == "FINAL_BLOCK"
    assert post_apply["next_action"] == "owner_review_post_apply_failure"
    pre_apply = SelfHostedTaskService._task_action_envelope({
        "task_id": "pre-apply-action", "status": "INTEGRATION_FAILED_PRE_APPLY",
        "promotion_status": "INTEGRATION_FAILED_PRE_APPLY", "merge_performed": False,
    })
    assert pre_apply["next_action"] == "retry_integration_same_task"
    retained = SelfHostedTaskService._task_action_envelope({
        "task_id": "retained-action", "status": "INTEGRATED_TARGET_RETAINED",
        "promotion_status": "INTEGRATED", "archive_eligible": False,
    })
    assert retained["action_state"] == "ACTION_REQUIRED"
    assert retained["next_action"] == "retry_cleanup"


def test_pre_apply_failure_leaves_branch_unchanged_and_is_retryable(tmp_path: Path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("pre-apply-retry", {"task_id": "pre-apply-retry", "status": "INTEGRATION_FAILED_PRE_APPLY", "promotion_status": "INTEGRATION_FAILED_PRE_APPLY", "merge_performed": False, "approved_binding": {"candidate_commit_sha": "a" * 40}})
    called = []
    service.integrate_approved = lambda task_id, *, integration_branch: called.append((task_id, integration_branch)) or {"status": "INTEGRATED"}
    result = service.retry_integration("pre-apply-retry")
    assert called == [("pre-apply-retry", "nexus/integration/main")]
    assert result["status"] == "INTEGRATED"


def test_finalization_receipt_survives_fresh_service_reload(tmp_path: Path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    monkeypatch.setattr(service, "approve_promotion", lambda task_id, **kwargs: {"status": "APPROVED", "promotion_status": "APPROVED"})
    monkeypatch.setattr(service, "integrate_approved", lambda task_id, *, integration_branch: {"status": "INTEGRATED", "promotion_status": "INTEGRATED", "integration_receipt": {"schema": "nexus.integration_receipt.v1", "integration_commit_sha": "a" * 40}})
    monkeypatch.setattr(service, "cleanup_tasks", lambda *, task_id, dry_run: {"dry_run": False, "decisions": [{"cleanup_performed": True, "cleanup_eligible": True, "cleanup_decision": "REMOVED", "cleanup_receipt": {"performed": True, "eligible": True, "target_present_after": False}}]})
    monkeypatch.setattr(service, "archive_states", lambda **kwargs: {"entries": []})
    result = service.owner_finish("reload-finalization", candidate_commit_sha="a" * 40, candidate_tree_sha="b" * 40, candidate_state_hash="c" * 64, verified_receipt_hash="d" * 64, external_acceptance={"passed": True}, integration_authorization={"cleanup_requested": True, "cleanup_target_path": str(tmp_path / "target")})
    fresh = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    stored = fresh._read_state("reload-finalization") or fresh._latest_archived_state("reload-finalization")[1]
    assert stored["finalization_receipt"] == result["finalization_receipt"]


def test_owner_finish_replay_is_idempotent(tmp_path: Path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    calls: list[str] = []
    monkeypatch.setattr(service, "approve_promotion", lambda task_id, **kwargs: calls.append("approve") or {"status": "APPROVED", "promotion_status": "APPROVED"})
    monkeypatch.setattr(service, "integrate_approved", lambda task_id, *, integration_branch: calls.append("integrate") or {"status": "INTEGRATED", "promotion_status": "INTEGRATED", "integration_receipt": {"schema": "nexus.integration_receipt.v1"}})
    monkeypatch.setattr(service, "cleanup_tasks", lambda *, task_id, dry_run: calls.append("cleanup") or {"dry_run": False, "decisions": [{"cleanup_performed": True, "cleanup_eligible": True, "cleanup_decision": "REMOVED", "cleanup_receipt": {"performed": True, "eligible": True, "target_present_after": False}}]})
    monkeypatch.setattr(service, "archive_states", lambda **kwargs: {"entries": []})
    kwargs = dict(candidate_commit_sha="a" * 40, candidate_tree_sha="b" * 40, candidate_state_hash="c" * 64, verified_receipt_hash="d" * 64, external_acceptance={"passed": True}, integration_authorization={"cleanup_requested": True, "cleanup_target_path": str(tmp_path / "target"), "action_set": ["CLEANUP_OWNED_TARGET"]})
    first = service.owner_finish("replay", **kwargs)
    second = service.owner_finish("replay", **kwargs)
    assert calls == ["approve", "integrate", "cleanup"]
    assert second["duplicate"] is True
    assert second["finalization_receipt"] == first["finalization_receipt"]


def test_owner_finish_never_deletes_task_branch_or_candidate_ref(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    receipt = _acceptance(candidate)
    auth = _authorization(root, base, candidate, receipt)
    target = tmp_path / "targets" / "task-branch"
    target.parent.mkdir()
    _git(root, "worktree", "add", "-b", "nexus/task/task-branch", str(target), base)
    _git(target, "merge", "--ff-only", candidate)
    durable_ref = "refs/nexus-candidate/task-branch"
    _git(root, "update-ref", durable_ref, candidate)
    assert _git(root, "show-ref", "--verify", "refs/heads/nexus/task/task-branch")
    assert _git(root, "show-ref", "--verify", durable_ref)


def test_owner_finish_retains_real_dirty_target_with_typed_reason(tmp_path: Path, monkeypatch):
    root, base, candidate = _repo(tmp_path)
    receipt = replace(_acceptance(candidate), task_id="dirty-owner-finish")
    auth = replace(
        _authorization(root, base, candidate, receipt),
        task_id="dirty-owner-finish",
        cleanup_target_id="dirty-owner-finish",
    )
    target = tmp_path / "targets" / "dirty-owner-finish"
    target.parent.mkdir()
    _git(root, "worktree", "add", "-b", "nexus/task/dirty-owner-finish", str(target), base)
    _git(target, "merge", "--ff-only", candidate)
    durable_ref = "refs/nexus-candidate/dirty-owner-finish"
    _git(root, "update-ref", durable_ref, candidate)
    (target / "untracked.txt").write_text("must retain\n", encoding="utf-8")
    # Paths under /tmp are rewritten to the default target root; pin it so the
    # persisted contract keeps the real target the lease was created for.
    monkeypatch.setenv("NEXUS_TARGET_ROOT_OVERRIDE", str(target.parent))
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = {
        "task_id": "dirty-owner-finish", "what": "dirty retention", "why": "closure",
        "controller_revision": base, "target_base_revision": base,
        "controller_repo_root": str(root), "target_repo_root": str(target),
        "target_worktree_root": str(target.parent), "allowed_files": ["value.txt"],
        "verifier_commands": ["/usr/bin/true"], "worker": "codex",
    }
    contract = service.build_contract(request)
    # Approval recomputes the verified receipt hash (#1758): bind a real one.
    verified_receipt = {
        **_verified_gate_proof(root, contract),
        "verifier_evidence": _verifier_evidence("/usr/bin/true"),
        "verified": True,
    }
    verified_receipt_hash = _receipt_hash(verified_receipt)
    auth = replace(auth, candidate_receipt_hash=verified_receipt_hash)
    lease_id = WorktreeManager(root_dir=str(target.parent), create_root=False)._lease_id(contract, target, "nexus/task/dirty-owner-finish")
    packet = {"candidate_commit_sha": candidate, "candidate_tree_sha": _git(root, "rev-parse", f"{candidate}^{{tree}}"), "candidate_state_hash": "d" * 64, "verified_receipt_hash": verified_receipt_hash}
    service._write_state("dirty-owner-finish", {
        "task_id": "dirty-owner-finish", "attempt_id": "attempt-1", "status": "CANDIDATE_CAPTURED", "promotion_status": "PENDING_HUMAN_APPROVAL", "request": request, "contract": contract.model_dump(mode="json"), "contract_hash": contract.contract_hash, "task_card_hash": "c" * 64, "verified_receipt": verified_receipt, "integration_verifier_manifest": _manifest(verified_receipt, contract), "promotion_packet": packet, "candidate_ref": durable_ref,
        "lease": {"schema": "nexus.target_worktree_lease.v1", "lease_id": lease_id, "task_id": "dirty-owner-finish", "controller_revision": base, "target_base_revision": base, "target_worktree": str(target), "target_branch": "nexus/task/dirty-owner-finish", "initial_head": base, "initial_status_sha256": "0" * 64, "controller_status_sha256": "0" * 64, "created_from_exact_revision": True, "commit_created": True, "merge_performed": False},
    })
    context = _bound_tracked_approval("dirty-owner-finish", contract.contract_hash)
    result = service.owner_finish(
        "dirty-owner-finish", candidate_commit_sha=candidate,
        candidate_tree_sha=packet["candidate_tree_sha"], candidate_state_hash="d" * 64,
        verified_receipt_hash=verified_receipt_hash, integration_branch="nexus/integration/canary",
        approval_context=context, external_acceptance=receipt.to_dict(),
        integration_authorization={**auth.to_dict(), "canonical_branch": "nexus/integration/canary", "cleanup_target_path": str(target), "durable_ref": durable_ref},
    )
    assert result["status"] == "INTEGRATED_TARGET_RETAINED"
    assert result["cleanup_status"] == "RETAINED"
    assert result["retention_reason"]
    assert result["next_action"] == "retry_cleanup"
    assert result["archive_eligible"] is False
    assert target.exists()
    assert (target / "untracked.txt").read_text(encoding="utf-8") == "must retain\n"


def _approved_closure_service(tmp_path: Path, *, separate_controller: bool = False):
    root, base, candidate = _repo(tmp_path)
    if separate_controller:
        # #2229/#2231 shape: primary checkout on main, Controller is a
        # detached linked worktree and the integration branch is checked out
        # nowhere.
        _git(root, "checkout", "main")
        root = _separate_controller_worktree(tmp_path, root, base)
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    verifier_executable = Path("/usr/bin/true")
    verifier_command = str(verifier_executable)
    request = {
        "task_id": "closure-bind", "campaign_id": "campaign", "what": "closure", "why": "closure",
        "controller_revision": base, "target_base_revision": base,
        "controller_repo_root": str(root), "target_repo_root": str(tmp_path / "target"),
        "target_worktree_root": str(tmp_path), "allowed_files": ["value.txt"],
        "verifier_commands": [verifier_command], "worker": "codex",
    }
    contract = service.build_contract(request)
    packet = {
        "candidate_commit_sha": candidate,
        "candidate_tree_sha": _git(root, "rev-parse", f"{candidate}^{{tree}}"),
        "candidate_state_hash": "d" * 64, "verified_receipt_hash": "e" * 64,
    }
    verified_receipt = _verified_gate_proof(root, contract)
    verified_receipt["verifier_evidence"] = [{
        "command": verifier_command,
        "status": "COMPLETED",
        "exit_code": 0,
        "executable_identity": str(verifier_executable),
        "executable_sha256": hashlib.sha256(
            verifier_executable.read_bytes()
        ).hexdigest(),
        "argv": [],
        "env": bounded_environment_receipt({"PYTHONDONTWRITEBYTECODE": "1"}),
        "timed_out": False,
        "process_group_killed": False,
    }]
    service._write_state("closure-bind", {
        "task_id": "closure-bind", "attempt_id": "attempt-1", "status": "APPROVED", "promotion_status": "APPROVED",
        "request": request, "contract": contract.model_dump(mode="json"), "contract_hash": contract.contract_hash,
        "contract_kind": "TRACKED_TASK_CARD", "task_card_hash": "c" * 64,
        "candidate_ref": f"refs/nexus-candidates/closure-bind/{candidate}",
        "controller_revision": base, "promotion_packet": packet,
        "verified_receipt": verified_receipt,
        "approved_binding": {**packet, "approval_grant": {"approval_scope": "ALLOW_ACTION_ONCE", "consumed_at": "2026-08-08T00:00:00+00:00"}},
        "lease": {"lease_id": "lease-closure-bind", "target_worktree": str(tmp_path / "target"), "target_branch": "candidate"},
    })
    acceptance = _acceptance(candidate)
    artifact_dir = tmp_path / "state" / "acceptance-artifacts" / "closure-bind"
    artifact_dir.mkdir(parents=True)
    artifact = artifact_dir / "verifier.txt"
    artifact.write_text("accepted\n", encoding="utf-8")
    artifact_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
    acceptance = replace(acceptance, task_id="closure-bind", attempt_id="attempt-1", receipt_hash=artifact_hash, verifier_artifact=str(artifact))
    runtime = {"tool_manifest_hash": "1" * 64, "full_tool_schema_hash": "2" * 64, "permission_policy_hash": "3" * 64, "lifecycle_revision": "lifecycle", "server_instance_id": "server"}
    approval = {
        "schema": "nexus.approval.v2", "approval_id": "integrate-approval", "approved_by": "owner",
        "issued_at": "2026-08-08T00:00:00+00:00", "expires_at": "2099-08-08T00:00:00+00:00",
        "bound_task_id": "closure-bind", "bound_attempt_id": "attempt-1", "bound_action_type": "CANDIDATE_INTEGRATE",
        "approval_scope": "ALLOW_ACTION_ONCE", "contract_kind": "TRACKED_TASK_CARD", "contract_hash": contract.contract_hash,
        "task_card_hash": "c" * 64, "expected_canonical_head": base, "integration_branch": "nexus/integration/canary",
        "candidate_commit_sha": candidate, "candidate_tree_sha": packet["candidate_tree_sha"], "candidate_state_hash": packet["candidate_state_hash"], "verified_receipt_hash": packet["verified_receipt_hash"], "acceptance_receipt_hash": acceptance.receipt_hash, **runtime,
    }
    return service, root, base, candidate, acceptance, approval, runtime


def test_service_closure_binding_is_typed_idempotent_and_does_not_integrate(tmp_path: Path, monkeypatch):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    monkeypatch.setattr(service, "integrate_approved", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("bind must not integrate")))
    first = service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    assert first["integration_performed"] is False
    assert first["status"] == "APPROVED"
    second = service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    assert second["duplicate"] is True
    assert second["integration_performed"] is False
    assert (service._read_state("closure-bind") or {})["integration_approval_grant"]["consumed_at"]


def test_service_closure_binding_rejects_tamper_and_head_drift(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    with pytest.raises(RuntimeError, match="CLOSURE_APPROVAL_SCHEMA_CLOSED"):
        service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval={**approval, "action_set": ["APPLY_VERIFIED_INTEGRATION"]}, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    with pytest.raises(RuntimeError, match="EXTERNAL_ACCEPTANCE_BINDING_MISMATCH"):
        service.bind_candidate_integration_closure("closure-bind", external_acceptance=replace(acceptance, candidate_commit="f" * 40), approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    (root / "value.txt").write_text("drift\n")
    _git(root, "commit", "-am", "head drift")
    with pytest.raises(RuntimeError, match="CLOSURE_CANONICAL_HEAD_DRIFT"):
        service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")


def _bind_task_card(controller: Path, name: str) -> str:
    """A tasks/-only Task Card bind commit on the detached Controller (#1939)."""
    card = controller / "tasks" / "bound" / name
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_text(f"{name}\n")
    _git(controller, "add", str(card.relative_to(controller)))
    _git(controller, "commit", "-m", f"bind {name}")
    return _git(controller, "rev-parse", "HEAD")


def _separate_closure_kwargs(acceptance, approval, runtime, head: str) -> dict:
    return {
        "external_acceptance": acceptance,
        "approval": approval,
        "runtime_identity": runtime,
        "expected_canonical_head": head,
        "integration_branch": "nexus/integration/canary",
    }


def test_separate_controller_closure_then_integrate_end_to_end(tmp_path: Path, monkeypatch):
    """#2230: a detached Controller with bind commits and a pending card integrates."""
    service, controller, base, candidate, acceptance, approval, runtime = _approved_closure_service(
        tmp_path, separate_controller=True
    )
    state = service._read_state("closure-bind")
    state["integration_staging_root"] = str(tmp_path / "stage")
    service._write_state("closure-bind", state)
    _bind_task_card(controller, "already-bound.md")
    pending = controller / "tasks" / "active" / "pending-card.md"
    pending.parent.mkdir(parents=True)
    pending.write_text("pending\n")
    monkeypatch.setattr(
        RepositoryContractGate,
        "evaluate_committed_candidate",
        lambda *args, **kwargs: SimpleNamespace(passed=True, blocking_reasons=()),
    )

    bound = service.bind_candidate_integration_closure(
        "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
    )
    closure = bound["closure_binding"]
    assert closure["canonical_head"] == base
    assert closure["controller_shape"] == "SEPARATE_DETACHED_WORKTREE"
    assert closure["controller_head"] == _git(controller, "rev-parse", "HEAD")
    assert service._read_state("closure-bind")["integration_authorization"]["expected_canonical_head"] == base

    # A Task Card bind commit between closure and integrate moves the
    # Controller HEAD; integration CASes the branch ref and is unaffected.
    controller_head = _bind_task_card(controller, "bound-after-closure.md")
    result = service.integrate_approved(
        "closure-bind", integration_branch="nexus/integration/canary", runtime_identity=runtime
    )
    assert result["status"] in {"INTEGRATED", "INTEGRATED_TARGET_RETAINED", "INTEGRATED_AND_CLEANED"}
    integrated = _git(controller, "rev-parse", "nexus/integration/canary")
    assert integrated != base
    assert _git(controller, "merge-base", "--is-ancestor", candidate, integrated) == ""
    assert _git(controller, "rev-parse", "HEAD") == controller_head
    assert pending.read_text() == "pending\n"
    assert (controller / "value.txt").read_text() == "base\n"


@pytest.mark.parametrize("dirt", ["untracked-outside", "tracked-edit", "tasks-symlink", "tracked-tasks-edit"])
def test_separate_controller_closure_still_blocks_non_card_dirt(tmp_path: Path, dirt: str):
    service, controller, base, _candidate, acceptance, approval, runtime = _approved_closure_service(
        tmp_path, separate_controller=True
    )
    if dirt == "untracked-outside":
        (controller / "stray.txt").write_text("stray\n")
    elif dirt == "tracked-edit":
        (controller / "value.txt").write_text("edited\n")
    elif dirt == "tasks-symlink":
        (controller / "tasks").mkdir()
        (controller / "tasks" / "card.md").symlink_to(controller / "value.txt")
    else:
        _bind_task_card(controller, "card.md")
        (controller / "tasks" / "bound" / "card.md").write_text("edited\n")
    before = service._state_path("closure-bind").read_bytes()
    with pytest.raises(RuntimeError, match="CLOSURE_CANONICAL_DIRTY"):
        service.bind_candidate_integration_closure(
            "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
        )
    assert service._state_path("closure-bind").read_bytes() == before


def test_separate_controller_closure_binds_branch_ref_not_controller_head(tmp_path: Path):
    service, controller, base, _candidate, acceptance, approval, runtime = _approved_closure_service(
        tmp_path, separate_controller=True
    )
    controller_head = _bind_task_card(controller, "card.md")
    before = service._state_path("closure-bind").read_bytes()
    with pytest.raises(RuntimeError, match="CLOSURE_CANONICAL_HEAD_DRIFT"):
        service.bind_candidate_integration_closure(
            "closure-bind",
            **_separate_closure_kwargs(
                acceptance, {**approval, "expected_canonical_head": controller_head}, runtime, controller_head
            ),
        )
    assert service._state_path("closure-bind").read_bytes() == before


def test_separate_controller_closure_refuses_checked_out_integration_branch(tmp_path: Path):
    service, controller, base, _candidate, acceptance, approval, runtime = _approved_closure_service(
        tmp_path, separate_controller=True
    )
    _git(tmp_path / "repo", "checkout", "nexus/integration/canary")
    with pytest.raises(RuntimeError, match="CLOSURE_INTEGRATION_BRANCH_CHECKED_OUT"):
        service.bind_candidate_integration_closure(
            "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
        )


@pytest.mark.parametrize("race", ["ref-moved", "dirt-appeared"])
def test_separate_controller_closure_rechecks_under_state_lock(tmp_path: Path, monkeypatch, race: str):
    service, controller, base, candidate, acceptance, approval, runtime = _approved_closure_service(
        tmp_path, separate_controller=True
    )
    original = service._mutate_state

    def racing_mutate(task_id, mutate):
        if race == "ref-moved":
            _git(controller, "update-ref", "refs/heads/nexus/integration/canary", candidate)
        else:
            (controller / "stray.txt").write_text("stray\n")
        return original(task_id, mutate)

    monkeypatch.setattr(service, "_mutate_state", racing_mutate)
    before = service._state_path("closure-bind").read_bytes()
    expected = "CLOSURE_CANONICAL_HEAD_DRIFT" if race == "ref-moved" else "CLOSURE_CANONICAL_REBIND_DRIFT"
    with pytest.raises(RuntimeError, match=expected):
        service.bind_candidate_integration_closure(
            "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
        )
    assert service._state_path("closure-bind").read_bytes() == before


def test_strict_controller_closure_still_rejects_pending_card(tmp_path: Path):
    """The checked-out integration branch keeps the fully clean rule."""
    service, root, base, _candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    (root / "tasks").mkdir()
    (root / "tasks" / "pending-card.md").write_text("pending\n")
    with pytest.raises(RuntimeError, match="CLOSURE_CANONICAL_DIRTY"):
        service.bind_candidate_integration_closure(
            "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
        )


def test_main_checkout_on_main_closure_still_strict(tmp_path: Path):
    """A primary checkout on main is not a separate Controller: branch drift."""
    service, root, base, _candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    _git(root, "checkout", "main")
    before = service._state_path("closure-bind").read_bytes()
    with pytest.raises(RuntimeError, match="CLOSURE_CANONICAL_BRANCH_DRIFT"):
        service.bind_candidate_integration_closure(
            "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
        )
    (root / "tasks").mkdir()
    (root / "tasks" / "pending-card.md").write_text("pending\n")
    with pytest.raises(RuntimeError, match="CLOSURE_CANONICAL_DIRTY"):
        service.bind_candidate_integration_closure(
            "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
        )
    assert service._state_path("closure-bind").read_bytes() == before


# --- #2248 review round 1: symref / checkout / rebase / ref-syntax / hidden dirt ---

_CANARY = "nexus/integration/canary"
_CANARY_REF = f"refs/heads/{_CANARY}"


def _integrate_ready(service, monkeypatch, tmp_path: Path) -> None:
    state = service._read_state("closure-bind")
    state["integration_staging_root"] = str(tmp_path / "stage")
    service._write_state("closure-bind", state)
    monkeypatch.setattr(
        RepositoryContractGate,
        "evaluate_committed_candidate",
        lambda *args, **kwargs: SimpleNamespace(passed=True, blocking_reasons=()),
    )


def test_separate_controller_closure_refuses_symbolic_integration_branch(tmp_path: Path):
    """A symref integration branch would let update-ref move main under the primary checkout."""
    service, controller, base, _candidate, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path, separate_controller=True)
    )
    root = tmp_path / "repo"
    _git(root, "symbolic-ref", _CANARY_REF, "refs/heads/main")
    before = service._state_path("closure-bind").read_bytes()
    with pytest.raises(RuntimeError, match="CLOSURE_INTEGRATION_BRANCH_SYMBOLIC"):
        service.bind_candidate_integration_closure(
            "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
        )
    assert service._state_path("closure-bind").read_bytes() == before
    assert _git(root, "rev-parse", "refs/heads/main") == base


def test_separate_controller_apply_refuses_symref_created_after_bind(tmp_path: Path, monkeypatch):
    service, controller, base, _candidate, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path, separate_controller=True)
    )
    _integrate_ready(service, monkeypatch, tmp_path)
    service.bind_candidate_integration_closure(
        "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
    )
    root = tmp_path / "repo"
    _git(root, "symbolic-ref", _CANARY_REF, "refs/heads/main")
    with pytest.raises(
        RuntimeError,
        match="INTEGRATION_BRANCH_REFUSED_AT_APPLY: CLOSURE_INTEGRATION_BRANCH_SYMBOLIC",
    ):
        service.integrate_approved(
            "closure-bind", integration_branch=_CANARY, runtime_identity=runtime
        )
    assert _git(root, "rev-parse", "refs/heads/main") == base
    assert _git(root, "symbolic-ref", _CANARY_REF) == "refs/heads/main"
    assert _git(root, "status", "--porcelain=v1", "--untracked-files=all") == ""


def test_apply_update_ref_never_follows_an_integration_symref(tmp_path: Path, monkeypatch):
    """update-ref --no-deref: even with the apply-time in-use guard bypassed, main never moves."""
    monkeypatch.setattr(
        ControlledIntegrationManager,
        "_require_integration_branch_not_in_use",
        classmethod(lambda cls, root, branch: None),
    )
    root, base, candidate = _repo(tmp_path)
    _git(root, "checkout", "main")
    _git(root, "symbolic-ref", _CANARY_REF, "refs/heads/main")
    result = _separate_controller_integrate(tmp_path, root.resolve(), base, candidate)
    assert _git(root, "rev-parse", "refs/heads/main") == base
    assert (
        subprocess.run(
            ["git", "symbolic-ref", "-q", _CANARY_REF], cwd=root, capture_output=True
        ).returncode
        == 1
    )
    assert result.branch_head_after == _git(root, "rev-parse", _CANARY_REF) != base
    assert _git(root, "status", "--porcelain=v1", "--untracked-files=all") == ""


def test_non_separate_update_ref_apply_still_integrates(tmp_path: Path):
    """Primary checkout on main integrating a free canary branch: the legitimate update-ref flow."""
    root, base, candidate = _repo(tmp_path)
    _git(root, "checkout", "main")
    result = _separate_controller_integrate(tmp_path, root.resolve(), base, candidate)
    assert result.merge_performed is True
    assert result.branch_head_after == _git(root, "rev-parse", _CANARY_REF) != base
    assert _git(root, "rev-parse", "refs/heads/main") == base
    assert _git(root, "status", "--porcelain=v1", "--untracked-files=all") == ""


def test_non_separate_apply_refuses_symbolic_integration_branch(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    _git(root, "checkout", "main")
    _git(root, "symbolic-ref", _CANARY_REF, "refs/heads/main")
    with pytest.raises(
        IntegrationExecutionError,
        match="INTEGRATION_BRANCH_REFUSED_AT_APPLY: CLOSURE_INTEGRATION_BRANCH_SYMBOLIC",
    ) as raised:
        _separate_controller_integrate(tmp_path, root.resolve(), base, candidate)
    assert raised.value.merge_performed is False
    assert _git(root, "rev-parse", "refs/heads/main") == base
    assert _git(root, "symbolic-ref", _CANARY_REF) == "refs/heads/main"


def test_strict_closure_apply_refuses_branch_checked_out_after_bind(tmp_path: Path, monkeypatch):
    """Round 2: strict closure binds, the primary leaves canary, another worktree checks it out."""
    service, root, base, _candidate, acceptance, approval, runtime = _approved_closure_service(
        tmp_path
    )
    _integrate_ready(service, monkeypatch, tmp_path)
    service.bind_candidate_integration_closure(
        "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
    )
    _git(root, "checkout", "main")
    other = tmp_path / "other"
    _git(root, "worktree", "add", str(other), _CANARY)
    with pytest.raises(
        IntegrationExecutionError,
        match="INTEGRATION_BRANCH_REFUSED_AT_APPLY: CLOSURE_INTEGRATION_BRANCH_CHECKED_OUT",
    ) as raised:
        service.integrate_approved(
            "closure-bind", integration_branch=_CANARY, runtime_identity=runtime
        )
    assert raised.value.merge_performed is False
    assert _git(root, "rev-parse", _CANARY_REF) == base
    assert _git(other, "status", "--porcelain=v1", "--untracked-files=all") == ""
    assert service._read_state("closure-bind")["status"] == "INTEGRATION_FAILED_PRE_APPLY"


def test_separate_controller_closure_refuses_branch_in_rebase_update_refs(tmp_path: Path):
    """``git rebase -i --update-refs`` will move canary: Git treats it as in use."""
    service, controller, base, candidate, acceptance, approval, runtime = _approved_closure_service(
        tmp_path, separate_controller=True
    )
    root = tmp_path / "repo"
    other = tmp_path / "other"
    _git(root, "worktree", "add", "-b", "topic", str(other), base)
    (other / "first.txt").write_text("first\n")
    _git(other, "add", "first.txt")
    _git(other, "commit", "-m", "first")
    first = _git(other, "rev-parse", "HEAD")
    _git(root, "update-ref", _CANARY_REF, first)
    (other / "second.txt").write_text("second\n")
    _git(other, "add", "second.txt")
    _git(other, "commit", "-m", "second")
    editor = tmp_path / "seq-editor.sh"
    editor.write_text('#!/bin/sh\n{ echo break; cat "$1"; } > "$1.new" && mv "$1.new" "$1"\n')
    editor.chmod(0o755)
    stopped = subprocess.run(
        ["git", "rebase", "-i", "--update-refs", candidate],
        cwd=other,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_SEQUENCE_EDITOR": str(editor)},
    )
    assert stopped.returncode == 0, stopped.stderr
    admin = Path(_git(other, "rev-parse", "--absolute-git-dir"))
    assert _CANARY_REF in (admin / "rebase-merge" / "update-refs").read_text().splitlines()
    before = service._state_path("closure-bind").read_bytes()
    with pytest.raises(RuntimeError, match="CLOSURE_INTEGRATION_BRANCH_CHECKED_OUT"):
        service.bind_candidate_integration_closure(
            "closure-bind",
            **_separate_closure_kwargs(
                acceptance, {**approval, "expected_canonical_head": first}, runtime, first
            ),
        )
    assert service._state_path("closure-bind").read_bytes() == before


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads mode-000 directories")
def test_separate_controller_closure_refuses_unreadable_tasks_subdirectory(tmp_path: Path):
    service, controller, base, _candidate, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path, separate_controller=True)
    )
    locked = controller / "tasks" / "active" / "locked"
    locked.mkdir(parents=True)
    (locked / "card.md").write_text("hidden\n")
    locked.chmod(0o000)
    try:
        before = service._state_path("closure-bind").read_bytes()
        with pytest.raises(RuntimeError, match="CLOSURE_CANONICAL_DIRTY"):
            service.bind_candidate_integration_closure(
                "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
            )
        assert service._state_path("closure-bind").read_bytes() == before
    finally:
        locked.chmod(0o755)


@pytest.mark.parametrize("kind", ["blob", "annotated-tag"])
def test_separate_controller_closure_refuses_non_commit_branch_ref(tmp_path: Path, kind: str):
    """The ref exists but does not name a commit itself: INVALID, not MISSING."""
    service, controller, base, _candidate, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path, separate_controller=True)
    )
    root = tmp_path / "repo"
    if kind == "blob":
        target = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=root,
            input="blob\n",
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    else:
        _git(root, "tag", "-a", "-m", "annotated", "annotated", base)
        target = _git(root, "rev-parse", "refs/tags/annotated")
    common = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    (common / "refs" / "heads" / "nexus" / "integration" / "canary").write_text(target + "\n")
    assert _git(root, "show-ref", "--verify", "--hash", _CANARY_REF) == target
    before = service._state_path("closure-bind").read_bytes()
    with pytest.raises(RuntimeError, match="CLOSURE_INTEGRATION_BRANCH_INVALID"):
        service.bind_candidate_integration_closure(
            "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
        )
    assert service._state_path("closure-bind").read_bytes() == before


@pytest.mark.parametrize("where", ["linked-worktree", "primary-checkout"])
def test_alias_symref_to_integration_branch_checked_out_is_refused(
    tmp_path: Path, monkeypatch, where: str
):
    """A different branch that is a symref to canary, checked out anywhere, counts as canary."""
    service, controller, base, _candidate, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path, separate_controller=True)
    )
    _integrate_ready(service, monkeypatch, tmp_path)
    service.bind_candidate_integration_closure(
        "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
    )
    root = tmp_path / "repo"
    _git(root, "symbolic-ref", "refs/heads/alias", _CANARY_REF)
    if where == "linked-worktree":
        _git(root, "worktree", "add", str(tmp_path / "other"), "alias")
    else:
        _git(root, "checkout", "alias")
    with pytest.raises(RuntimeError, match="CLOSURE_INTEGRATION_BRANCH_CHECKED_OUT"):
        ControlledIntegrationManager.separate_controller_integration_head(controller, _CANARY)
    with pytest.raises(
        IntegrationExecutionError,
        match="INTEGRATION_BRANCH_REFUSED_AT_APPLY: CLOSURE_INTEGRATION_BRANCH_CHECKED_OUT",
    ) as raised:
        service.integrate_approved(
            "closure-bind", integration_branch=_CANARY, runtime_identity=runtime
        )
    assert raised.value.merge_performed is False
    assert _git(root, "rev-parse", _CANARY_REF) == base


def test_separate_controller_closure_refuses_branch_checked_out_in_linked_worktree(tmp_path: Path):
    service, controller, base, _candidate, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path, separate_controller=True)
    )
    _git(tmp_path / "repo", "worktree", "add", str(tmp_path / "other"), _CANARY)
    before = service._state_path("closure-bind").read_bytes()
    with pytest.raises(RuntimeError, match="CLOSURE_INTEGRATION_BRANCH_CHECKED_OUT"):
        service.bind_candidate_integration_closure(
            "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
        )
    assert service._state_path("closure-bind").read_bytes() == before


@pytest.mark.parametrize("operation", ["rebase", "bisect"])
def test_separate_controller_closure_refuses_branch_mid_rebase_or_bisect(
    tmp_path: Path, operation: str
):
    """worktree list shows the worktree detached, but the branch is still in use there."""
    service, controller, base, candidate, acceptance, approval, runtime = _approved_closure_service(
        tmp_path, separate_controller=True
    )
    other = tmp_path / "other"
    _git(tmp_path / "repo", "worktree", "add", str(other), _CANARY)
    for text in ("integration\n", "integration two\n"):
        (other / "value.txt").write_text(text)
        _git(other, "commit", "-am", text.strip())
    if operation == "rebase":
        stopped = subprocess.run(
            ["git", "rebase", candidate], cwd=other, capture_output=True, text=True
        )
        assert stopped.returncode != 0
    else:
        _git(other, "bisect", "start", "HEAD", base)
    assert (
        "detached"
        in _git(other, "worktree", "list", "--porcelain")
        .split("worktree " + str(other.resolve()))[1]
        .split("\n\n")[0]
    )
    head = _git(tmp_path / "repo", "rev-parse", _CANARY_REF)
    before = service._state_path("closure-bind").read_bytes()
    with pytest.raises(RuntimeError, match="CLOSURE_INTEGRATION_BRANCH_CHECKED_OUT"):
        service.bind_candidate_integration_closure(
            "closure-bind",
            **_separate_closure_kwargs(
                acceptance, {**approval, "expected_canonical_head": head}, runtime, head
            ),
        )
    assert service._state_path("closure-bind").read_bytes() == before


@pytest.mark.parametrize("where", ["linked-worktree", "primary-checkout"])
def test_separate_controller_apply_rechecks_branch_checkout(
    tmp_path: Path, monkeypatch, where: str
):
    """Bound while free; checked out before apply: integrate fails closed, zero ref movement."""
    service, controller, base, _candidate, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path, separate_controller=True)
    )
    _integrate_ready(service, monkeypatch, tmp_path)
    service.bind_candidate_integration_closure(
        "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
    )
    root = tmp_path / "repo"
    if where == "linked-worktree":
        _git(root, "worktree", "add", str(tmp_path / "other"), _CANARY)
    else:
        _git(root, "checkout", _CANARY)
    with pytest.raises(
        IntegrationExecutionError,
        match="INTEGRATION_BRANCH_REFUSED_AT_APPLY: CLOSURE_INTEGRATION_BRANCH_CHECKED_OUT",
    ) as raised:
        service.integrate_approved(
            "closure-bind", integration_branch=_CANARY, runtime_identity=runtime
        )
    assert raised.value.merge_performed is False
    assert _git(root, "rev-parse", _CANARY_REF) == base
    assert _git(root, "rev-parse", "refs/heads/main") == base
    assert service._read_state("closure-bind")["status"] == "INTEGRATION_FAILED_PRE_APPLY"


def test_integration_resolves_branch_not_same_named_tag(tmp_path: Path):
    _root, controller, base, candidate = _separate_controller(tmp_path)
    _git(controller, "tag", _CANARY, base)
    result = _separate_controller_integrate(tmp_path, controller, base, candidate)
    branch_head = _git(controller, "rev-parse", _CANARY_REF)
    assert branch_head != base
    assert result.branch_head_after == result.integration_commit_sha == branch_head
    assert _git(controller, "rev-parse", f"refs/tags/{_CANARY}") == base


@pytest.mark.parametrize(
    ("branch", "code"),
    [
        ("feature/not-integration", "CLOSURE_INTEGRATION_BRANCH_INVALID"),
        (f"{_CANARY}~1", "CLOSURE_INTEGRATION_BRANCH_INVALID"),
        (_CANARY, "CLOSURE_INTEGRATION_BRANCH_MISSING"),
    ],
)
def test_separate_controller_closure_refuses_invalid_or_missing_branch(
    tmp_path: Path, branch: str, code: str
):
    service, controller, base, _candidate, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path, separate_controller=True)
    )
    root = tmp_path / "repo"
    if code == "CLOSURE_INTEGRATION_BRANCH_MISSING":
        _git(root, "branch", "-D", _CANARY)
    else:
        # canary~1 == base: a revision expression would bind a non-head commit.
        child = _git(root, "commit-tree", f"{base}^{{tree}}", "-p", base, "-m", "child")
        _git(root, "update-ref", _CANARY_REF, child)
    before = service._state_path("closure-bind").read_bytes()
    with pytest.raises(RuntimeError, match=code):
        service.bind_candidate_integration_closure(
            "closure-bind",
            external_acceptance=acceptance,
            approval={**approval, "integration_branch": branch},
            runtime_identity=runtime,
            expected_canonical_head=base,
            integration_branch=branch,
        )
    assert service._state_path("closure-bind").read_bytes() == before


def test_separate_controller_closure_refuses_shape_flip_under_lock(tmp_path: Path, monkeypatch):
    """The locked still_separate check: the Controller checks out a branch mid-bind."""
    service, controller, base, _candidate, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path, separate_controller=True)
    )
    original = service._mutate_state

    def racing_mutate(task_id, mutate):
        _git(controller, "checkout", "-q", "-b", "flipped")
        return original(task_id, mutate)

    monkeypatch.setattr(service, "_mutate_state", racing_mutate)
    before = service._state_path("closure-bind").read_bytes()
    with pytest.raises(RuntimeError, match="CLOSURE_CANONICAL_REBIND_DRIFT"):
        service.bind_candidate_integration_closure(
            "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
        )
    assert service._state_path("closure-bind").read_bytes() == before


def test_separate_controller_closure_seals_lock_time_controller_head(tmp_path: Path, monkeypatch):
    service, controller, base, _candidate, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path, separate_controller=True)
    )
    original = service._mutate_state
    moved: list[str] = []

    def racing_mutate(task_id, mutate):
        moved.append(_bind_task_card(controller, "bound-mid-closure.md"))
        return original(task_id, mutate)

    monkeypatch.setattr(service, "_mutate_state", racing_mutate)
    bound = service.bind_candidate_integration_closure(
        "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
    )
    persisted = service._read_state("closure-bind")
    closure = persisted["integration_closure_binding"]
    assert closure["controller_head"] == moved[0] == bound["closure_binding"]["controller_head"]
    unsealed = {key: value for key, value in closure.items() if key != "binding_hash"}
    digest = hashlib.sha256(
        json.dumps(unsealed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    assert closure["binding_hash"] == persisted["integration_closure_binding_hash"] == digest


@pytest.mark.parametrize(
    "dirt",
    [
        "nested-git-dir",
        "hardlinked-pending-card",
        "ignored-hardlink-exclude",
        "ignored-file-exclude",
        "tasks-gitignore",
        "skip-worktree",
        "assume-unchanged",
    ],
)
def test_separate_controller_closure_refuses_hidden_tasks_dirt(tmp_path: Path, dirt: str):
    """Dirt git status cannot see (nested .git, ignore rules, index flags) still blocks."""
    service, controller, base, _candidate, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path, separate_controller=True)
    )
    active = controller / "tasks" / "active"
    active.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n")
    exclude = (
        Path(_git(controller, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        / "info"
        / "exclude"
    )
    if dirt == "nested-git-dir":
        (active / "nested" / ".git").mkdir(parents=True)
        (active / "nested" / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    elif dirt == "hardlinked-pending-card":
        os.link(outside, active / "card.md")
    elif dirt in {"ignored-hardlink-exclude", "ignored-file-exclude"}:
        exclude.parent.mkdir(exist_ok=True)
        exclude.write_text("*.pyc\n")
        if dirt == "ignored-hardlink-exclude":
            os.link(outside, active / "card.pyc")
        else:
            (active / "card.pyc").write_text("hidden\n")
        assert _git(controller, "status", "--porcelain=v1", "--untracked-files=all") == ""
    elif dirt == "tasks-gitignore":
        (controller / "tasks" / ".gitignore").write_text("*\n.gitignore\n")
        (active / "hidden.md").write_text("hidden\n")
        assert _git(controller, "status", "--porcelain=v1", "--untracked-files=all") == ""
    else:
        _bind_task_card(controller, "card.md")
        flag = "--skip-worktree" if dirt == "skip-worktree" else "--assume-unchanged"
        _git(controller, "update-index", flag, "tasks/bound/card.md")
        (controller / "tasks" / "bound" / "card.md").write_text("edited\n")
        assert _git(controller, "status", "--porcelain=v1", "--untracked-files=all") == ""
    before = service._state_path("closure-bind").read_bytes()
    with pytest.raises(RuntimeError, match="CLOSURE_CANONICAL_DIRTY"):
        service.bind_candidate_integration_closure(
            "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
        )
    assert service._state_path("closure-bind").read_bytes() == before


def _separate_controller_interrupted_after_update_ref(tmp_path: Path):
    """#2251: closure bound, then apply's update-ref ran and the run died.

    The integration branch already holds the no-ff staging merge (exactly
    what #2243's apply writes with ``update-ref <branch> <staging> <base>``),
    but no result was recorded, so the task is still INTEGRATING.
    """
    service, controller, base, candidate, acceptance, approval, runtime = _approved_closure_service(
        tmp_path, separate_controller=True
    )
    service.bind_candidate_integration_closure(
        "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
    )
    _bind_task_card(controller, "already-bound.md")
    pending = controller / "tasks" / "active" / "pending-card.md"
    pending.parent.mkdir(parents=True)
    pending.write_text("pending\n")
    applied = _git(
        controller,
        "commit-tree",
        f"{candidate}^{{tree}}",
        "-p",
        base,
        "-p",
        candidate,
        "-m",
        "applied",
    )
    _git(controller, "update-ref", "refs/heads/nexus/integration/canary", applied, base)
    state = service._read_state("closure-bind") or {}
    _git(controller, "update-ref", state["candidate_ref"], candidate)
    state.update(
        status="INTEGRATING",
        promotion_status="INTEGRATING",
        merge_performed=False,
        integration_receipt=None,
        integration_result_sha=None,
        integration_execution=None,
    )
    service._write_state("closure-bind", state)
    recovery_approval = {
        **approval,
        "approval_id": approval["approval_id"] + "-recovery",
        "issued_at": "2026-08-09T00:00:00+00:00",
        "expected_canonical_head": applied,
    }
    return service, controller, base, applied, pending, acceptance, recovery_approval, runtime


def test_separate_controller_integrating_recovery_rebind_succeeds(tmp_path: Path):
    """#2251: recovery binds the integration ref, not the detached Controller HEAD."""
    service, controller, base, applied, pending, acceptance, recovery, runtime = (
        _separate_controller_interrupted_after_update_ref(tmp_path)
    )
    controller_head = _git(controller, "rev-parse", "HEAD")
    controller_status = _status_hash(controller)
    assert controller_head != applied

    rebound = service.bind_candidate_integration_closure(
        "closure-bind", **_separate_closure_kwargs(acceptance, recovery, runtime, applied)
    )
    closure = rebound["integration_closure_binding"]
    assert closure["recovery_only"] is True
    assert closure["recovery_pre_apply_head"] == base
    assert closure["expected_canonical_head"] == applied
    assert closure["controller_shape"] == "SEPARATE_DETACHED_WORKTREE"
    assert closure["controller_head"] == controller_head
    assert rebound["status"] == "INTEGRATING"
    assert rebound["integration_recovery_only"] is True
    assert _git(controller, "rev-parse", "nexus/integration/canary") == applied
    assert _git(controller, "rev-parse", "HEAD") == controller_head
    assert _status_hash(controller) == controller_status
    assert pending.read_text() == "pending\n"
    assert (controller / "value.txt").read_text() == "base\n"
    with pytest.raises(RuntimeError, match="INTEGRATION_RECOVERY_ONLY"):
        service.integrate_approved("closure-bind")


@pytest.mark.parametrize("dirt", ["untracked-outside", "tracked-edit"])
def test_separate_controller_integrating_recovery_still_blocks_non_card_dirt(
    tmp_path: Path, dirt: str
):
    service, controller, _base, applied, _pending, acceptance, recovery, runtime = (
        _separate_controller_interrupted_after_update_ref(tmp_path)
    )
    if dirt == "untracked-outside":
        (controller / "stray.txt").write_text("stray\n")
    else:
        (controller / "value.txt").write_text("edited\n")
    before = service._state_path("closure-bind").read_bytes()
    with pytest.raises(RuntimeError, match="CLOSURE_INTEGRATING_APPLIED_TREE_REQUIRED"):
        service.bind_candidate_integration_closure(
            "closure-bind", **_separate_closure_kwargs(acceptance, recovery, runtime, applied)
        )
    assert service._state_path("closure-bind").read_bytes() == before


@pytest.mark.parametrize("shape", ["primary-on-main-ref-moved", "pending-card"])
def test_primary_checkout_integrating_recovery_still_strict(tmp_path: Path, shape: str):
    """A primary checkout keeps the HEAD tree + full cleanliness recovery rule."""
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(
        tmp_path
    )
    service.bind_candidate_integration_closure(
        "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
    )
    state = service._read_state("closure-bind") or {}
    if shape == "primary-on-main-ref-moved":
        # Today's live shape: primary checkout on main; only the branch ref moved.
        _git(root, "checkout", "main")
        applied = _git(
            root,
            "commit-tree",
            f"{candidate}^{{tree}}",
            "-p",
            base,
            "-p",
            candidate,
            "-m",
            "applied",
        )
        _git(root, "update-ref", "refs/heads/nexus/integration/canary", applied, base)
    else:
        _git(root, "merge", "--no-ff", "candidate", "-m", "applied")
        applied = _git(root, "rev-parse", "HEAD")
        (root / "tasks").mkdir()
        (root / "tasks" / "pending-card.md").write_text("pending\n")
    _git(root, "update-ref", state["candidate_ref"], candidate)
    state.update(
        status="INTEGRATING",
        promotion_status="INTEGRATING",
        merge_performed=False,
        integration_receipt=None,
        integration_result_sha=None,
        integration_execution=None,
    )
    service._write_state("closure-bind", state)
    recovery = {**approval, "approval_id": "integrate-recovery", "expected_canonical_head": applied}
    before = service._state_path("closure-bind").read_bytes()
    with pytest.raises(RuntimeError, match="CLOSURE_INTEGRATING_APPLIED_TREE_REQUIRED"):
        service.bind_candidate_integration_closure(
            "closure-bind", **_separate_closure_kwargs(acceptance, recovery, runtime, applied)
        )
    assert service._state_path("closure-bind").read_bytes() == before


@pytest.mark.parametrize("race", ["ref-moved", "dirt-appeared"])
def test_separate_controller_integrating_recovery_rechecks_under_state_lock(
    tmp_path: Path, monkeypatch, race: str
):
    service, controller, _base, applied, _pending, acceptance, recovery, runtime = (
        _separate_controller_interrupted_after_update_ref(tmp_path)
    )
    original = service._mutate_state

    def racing_mutate(task_id, mutate):
        if race == "ref-moved":
            moved = _git(
                controller, "commit-tree", f"{applied}^{{tree}}", "-p", applied, "-m", "moved"
            )
            _git(controller, "update-ref", "refs/heads/nexus/integration/canary", moved, applied)
        else:
            (controller / "stray.txt").write_text("stray\n")
        return original(task_id, mutate)

    monkeypatch.setattr(service, "_mutate_state", racing_mutate)
    before = service._state_path("closure-bind").read_bytes()
    expected = (
        "CLOSURE_CANONICAL_HEAD_DRIFT" if race == "ref-moved" else "CLOSURE_CANONICAL_REBIND_DRIFT"
    )
    with pytest.raises(RuntimeError, match=expected):
        service.bind_candidate_integration_closure(
            "closure-bind", **_separate_closure_kwargs(acceptance, recovery, runtime, applied)
        )
    assert service._state_path("closure-bind").read_bytes() == before


def _recovery_receipt(service, base: str, applied: str, acceptance, *, misbound_base: bool = False):
    """The receipt an interrupted apply would have written for ``applied``."""
    state = service._read_state("closure-bind") or {}
    packet = state["promotion_packet"]
    recorded_base = "d" * 40 if misbound_base else base
    return IntegrationReceipt(
        schema="nexus.integration_receipt.v1",
        task_id="closure-bind",
        integration_branch="nexus/integration/canary",
        source_branch="candidate",
        candidate_commit_sha=packet["candidate_commit_sha"],
        integration_base_sha=recorded_base,
        integration_commit_sha=applied,
        verifier_passed=True,
        merge_performed=True,
        push_performed=False,
        worktree_removed=False,
        staging_commit_sha=applied,
        post_apply_verified=True,
        acceptance_receipt_hash=acceptance.receipt_hash,
        authorization_hash=state["integration_authorization"]["authorization_hash"],
        task_card_hash=state["task_card_hash"],
        candidate_tree_sha=packet["candidate_tree_sha"],
        candidate_state_hash=packet["candidate_state_hash"],
        verified_receipt_hash=packet["verified_receipt_hash"],
        branch_head_before=recorded_base,
        branch_head_after=applied,
        candidate_is_ancestor=True,
        staging_verified=True,
    )


def _separate_controller_rebound_for_receipt_recovery(tmp_path: Path):
    service, controller, base, applied, pending, acceptance, recovery, runtime = (
        _separate_controller_interrupted_after_update_ref(tmp_path)
    )
    service.bind_candidate_integration_closure(
        "closure-bind", **_separate_closure_kwargs(acceptance, recovery, runtime, applied)
    )
    recovery_runtime = service._read_state("closure-bind")["integration_closure_binding"][
        "runtime_identity"
    ]
    return service, controller, base, applied, pending, acceptance, recovery_runtime


def test_separate_controller_integrating_recovery_completes(tmp_path: Path):
    """#2251: rebind then receipt recovery finish the task on a detached Controller."""
    service, controller, base, applied, pending, acceptance, recovery_runtime = (
        _separate_controller_rebound_for_receipt_recovery(tmp_path)
    )
    controller_head = _git(controller, "rev-parse", "HEAD")
    controller_status = _status_hash(controller)
    receipt = _recovery_receipt(service, base, applied, acceptance)

    recovered = service.recover_applied_integration_receipt(
        "closure-bind", receipt, runtime_identity=recovery_runtime
    )
    assert recovered["status"] == "INTEGRATED"
    assert recovered["integration_result_sha"] == applied
    assert recovered["integration_receipt"] == asdict(receipt)
    replay = service.recover_applied_integration_receipt(
        "closure-bind", receipt, runtime_identity=recovery_runtime
    )
    assert replay["status"] == "INTEGRATED"
    assert _git(controller, "rev-parse", "nexus/integration/canary") == applied
    assert _git(controller, "rev-parse", "HEAD") == controller_head
    assert _status_hash(controller) == controller_status
    assert pending.read_text() == "pending\n"
    assert (controller / "value.txt").read_text() == "base\n"


@pytest.mark.parametrize(
    "drift, message",
    [
        ("ref-not-receipt", "receipt recovery applied HEAD mismatch"),
        ("non-card-dirt", "receipt recovery canonical tree is dirty"),
    ],
)
def test_separate_controller_receipt_recovery_stays_fail_closed(
    tmp_path: Path, drift: str, message: str
):
    service, controller, base, applied, _pending, acceptance, recovery_runtime = (
        _separate_controller_rebound_for_receipt_recovery(tmp_path)
    )
    if drift == "ref-not-receipt":
        moved = _git(controller, "commit-tree", f"{applied}^{{tree}}", "-p", applied, "-m", "moved")
        _git(controller, "update-ref", "refs/heads/nexus/integration/canary", moved, applied)
    else:
        (controller / "stray.txt").write_text("stray\n")
    before = service._state_path("closure-bind").read_bytes()
    with pytest.raises(RuntimeError, match=message):
        service.recover_applied_integration_receipt(
            "closure-bind",
            _recovery_receipt(service, base, applied, acceptance),
            runtime_identity=recovery_runtime,
        )
    assert service._state_path("closure-bind").read_bytes() == before


@pytest.mark.parametrize(
    "shape, message",
    [
        ("pending-card", "receipt recovery canonical tree is dirty"),
        ("checkout-on-main", "receipt recovery applied HEAD mismatch"),
    ],
)
def test_primary_checkout_receipt_recovery_still_strict(tmp_path: Path, shape: str, message: str):
    """A primary checkout keeps HEAD, branch and full cleanliness for receipt recovery."""
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(
        tmp_path
    )
    service.bind_candidate_integration_closure(
        "closure-bind", **_separate_closure_kwargs(acceptance, approval, runtime, base)
    )
    _git(root, "merge", "--no-ff", "candidate", "-m", "applied")
    applied = _git(root, "rev-parse", "HEAD")
    state = service._read_state("closure-bind") or {}
    _git(root, "update-ref", state["candidate_ref"], candidate)
    state.update(
        status="INTEGRATING",
        promotion_status="INTEGRATING",
        merge_performed=False,
        integration_receipt=None,
        integration_result_sha=None,
        integration_execution=None,
    )
    service._write_state("closure-bind", state)
    recovery = {**approval, "approval_id": "integrate-recovery", "expected_canonical_head": applied}
    service.bind_candidate_integration_closure(
        "closure-bind", **_separate_closure_kwargs(acceptance, recovery, runtime, applied)
    )
    recovery_runtime = service._read_state("closure-bind")["integration_closure_binding"][
        "runtime_identity"
    ]
    if shape == "pending-card":
        (root / "tasks").mkdir()
        (root / "tasks" / "pending-card.md").write_text("pending\n")
    else:
        _git(root, "checkout", "main")
    before = service._state_path("closure-bind").read_bytes()
    with pytest.raises(RuntimeError, match=message):
        service.recover_applied_integration_receipt(
            "closure-bind",
            _recovery_receipt(service, base, applied, acceptance),
            runtime_identity=recovery_runtime,
        )
    assert service._state_path("closure-bind").read_bytes() == before


def test_separate_controller_receipt_correction_uses_integration_ref(tmp_path: Path):
    """#2251: receipt correction's physical check binds the integration ref too."""
    service, controller, base, applied, pending, acceptance, recovery_runtime = (
        _separate_controller_rebound_for_receipt_recovery(tmp_path)
    )
    receipt = _recovery_receipt(service, base, applied, acceptance, misbound_base=True)
    service.recover_applied_integration_receipt(
        "closure-bind", receipt, runtime_identity=recovery_runtime
    )
    state = service._read_state("closure-bind") or {}
    candidate = state["promotion_packet"]["candidate_commit_sha"]
    controller_head = _git(controller, "rev-parse", "HEAD")
    kwargs = _correction_kwargs(
        service, state, receipt, base, applied, candidate, acceptance, None, None
    )
    corrected = service.correct_applied_integration_receipt("closure-bind", **kwargs)
    assert corrected["integration_receipt"]["integration_base_sha"] == base
    assert corrected["integration_receipt"]["branch_head_before"] == base
    assert len(corrected["integration_receipt_correction_history"]) == 1
    assert _git(controller, "rev-parse", "HEAD") == controller_head
    assert pending.read_text() == "pending\n"

    # Non-card dirt still blocks the correction's physical binding.
    (controller / "stray.txt").write_text("stray\n")
    replay_kwargs = {
        **kwargs,
        "expected_state_hash": hashlib.sha256(
            service._state_path("closure-bind").read_bytes()
        ).hexdigest(),
    }
    before = service._state_path("closure-bind").read_bytes()
    with pytest.raises(RuntimeError, match="RECEIPT_CORRECTION_PHYSICAL_BINDING_MISMATCH"):
        service.correct_applied_integration_receipt("closure-bind", **replay_kwargs)
    assert service._state_path("closure-bind").read_bytes() == before


def _applied_receipt_correction_fixture(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure(
        "closure-bind", external_acceptance=acceptance, approval=approval,
        runtime_identity=runtime, expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    (root / "preapply.txt").write_text("preapply\n", encoding="utf-8")
    _git(root, "add", "preapply.txt")
    _git(root, "commit", "-m", "preapply")
    preapply = _git(root, "rev-parse", "HEAD")
    _git(root, "merge", "--no-ff", "candidate", "-m", "applied")
    applied = _git(root, "rev-parse", "HEAD")
    state = service._read_state("closure-bind") or {}
    packet = state["promotion_packet"]
    receipt = IntegrationReceipt(
        schema="nexus.integration_receipt.v1", task_id="closure-bind",
        integration_branch="nexus/integration/canary", source_branch="candidate",
        candidate_commit_sha=candidate, integration_base_sha="d" * 40,
        integration_commit_sha=applied, verifier_passed=True,
        merge_performed=True, push_performed=False, worktree_removed=False,
        staging_commit_sha=applied, post_apply_verified=True,
        acceptance_receipt_hash=acceptance.receipt_hash,
        authorization_hash=state["integration_authorization"]["authorization_hash"],
        task_card_hash=state["task_card_hash"], candidate_tree_sha=packet["candidate_tree_sha"],
        candidate_state_hash=packet["candidate_state_hash"],
        verified_receipt_hash=packet["verified_receipt_hash"],
        branch_head_before="d" * 40, branch_head_after=applied,
        candidate_is_ancestor=True, staging_verified=True,
    )
    closure = {
        **state["integration_closure_binding"], "recovery_only": True,
        "recovery_pre_apply_head": preapply,
    }
    closure_payload = {key: value for key, value in closure.items() if key != "binding_hash"}
    closure["binding_hash"] = hashlib.sha256(
        json.dumps(closure_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    state.update(
        status="INTEGRATED", promotion_status="INTEGRATED", merge_performed=True,
        integration_branch="nexus/integration/canary", integration_base_sha="d" * 40,
        integration_result_sha=applied, integration_receipt=asdict(receipt),
        integration_recovery_only=True,
        integration_closure_binding=closure,
    )
    service._write_state("closure-bind", state)
    state = service._read_state("closure-bind") or state
    return service, root, state, receipt, preapply, applied, candidate, acceptance, approval, runtime


def _correction_kwargs(service, state, receipt, preapply, applied, candidate, acceptance, approval, runtime):
    closure = state["integration_closure_binding"]
    return dict(
        expected_state_hash=hashlib.sha256(
            service._state_path("closure-bind").read_bytes()
        ).hexdigest(),
        original_receipt_hash=hashlib.sha256(
            json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest(),
        attempt_id=state["attempt_id"], candidate_commit_sha=candidate,
        candidate_tree_sha=receipt.candidate_tree_sha,
        acceptance_receipt_hash=acceptance.receipt_hash,
        approval=state["integration_approval_grant"],
        authorization=state["integration_authorization"],
        runtime_identity=closure["runtime_identity"],
        closure_binding=closure,
        integration_branch="nexus/integration/canary", expected_applied_head=applied,
        corrected_base_sha=preapply,
    )


def test_receipt_correction_is_append_only_exact_cas_and_idempotent(tmp_path: Path):
    fixture = _applied_receipt_correction_fixture(tmp_path)
    service, root, state, receipt, preapply, applied, candidate, acceptance, approval, runtime = fixture
    kwargs = _correction_kwargs(service, state, receipt, preapply, applied, candidate, acceptance, approval, runtime)
    corrected = service.correct_applied_integration_receipt("closure-bind", **kwargs)
    assert corrected["integration_base_sha"] == preapply
    assert corrected["integration_receipt"]["integration_base_sha"] == preapply
    assert corrected["integration_receipt"]["branch_head_before"] == preapply
    assert corrected["integration_receipt"]["integration_commit_sha"] == applied
    assert corrected["integration_receipt"]["staging_commit_sha"] == applied
    assert corrected["integration_receipt"]["branch_head_after"] == applied
    assert corrected["integration_result_sha"] == applied
    history = corrected["integration_receipt_correction_history"]
    assert len(history) == 1
    assert history[0]["original_receipt_hash"] == kwargs["original_receipt_hash"]
    assert history[0]["original_receipt"] == asdict(receipt)
    replay_kwargs = {**kwargs, "expected_state_hash": hashlib.sha256(
        service._state_path("closure-bind").read_bytes()
    ).hexdigest()}
    replay = service.correct_applied_integration_receipt("closure-bind", **replay_kwargs)
    assert replay["duplicate"] is True
    assert len(replay["integration_receipt_correction_history"]) == 1


def test_receipt_correction_canonicalizes_legacy_slash_schema(tmp_path: Path):
    fixture = _applied_receipt_correction_fixture(tmp_path)
    service, root, state, receipt, preapply, applied, candidate, acceptance, approval, runtime = fixture
    state["integration_receipt"]["schema"] = "nexus.integration_receipt/v1"
    service._write_state("closure-bind", state)
    state = service._read_state("closure-bind") or state
    kwargs = _correction_kwargs(service, state, receipt, preapply, applied, candidate, acceptance, approval, runtime)
    kwargs["original_receipt_hash"] = hashlib.sha256(
        json.dumps(state["integration_receipt"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()

    corrected = service.correct_applied_integration_receipt("closure-bind", **kwargs)

    assert corrected["integration_receipt"]["schema"] == "nexus.integration_receipt.v1"
    assert corrected["integration_receipt"]["integration_base_sha"] == preapply
    assert corrected["integration_receipt"]["branch_head_before"] == preapply
    history = corrected["integration_receipt_correction_history"]
    assert history[0]["original_receipt"]["schema"] == "nexus.integration_receipt/v1"
    assert history[0]["correction_deltas"]["schema"] == {
        "from": "nexus.integration_receipt/v1",
        "to": "nexus.integration_receipt.v1",
    }


@pytest.mark.parametrize("tamper", ["state", "receipt", "attempt", "candidate", "acceptance", "approval", "authorization", "runtime", "closure", "head"])
def test_receipt_correction_rejects_any_exact_binding_tamper(tmp_path: Path, tamper: str):
    fixture = _applied_receipt_correction_fixture(tmp_path)
    service, root, state, receipt, preapply, applied, candidate, acceptance, approval, runtime = fixture
    kwargs = _correction_kwargs(service, state, receipt, preapply, applied, candidate, acceptance, approval, runtime)
    if tamper == "state":
        kwargs["expected_state_hash"] = "f" * 40
    elif tamper == "receipt":
        kwargs["original_receipt_hash"] = "f" * 64
    elif tamper == "attempt":
        kwargs["attempt_id"] = "other"
    elif tamper == "candidate":
        kwargs["candidate_commit_sha"] = "f" * 40
    elif tamper == "acceptance":
        kwargs["acceptance_receipt_hash"] = "f" * 64
    elif tamper == "approval":
        kwargs["approval"] = {**kwargs["approval"], "approval_id": "other"}
    elif tamper == "authorization":
        kwargs["authorization"] = {**kwargs["authorization"], "authorization_hash": "f" * 64}
    elif tamper == "runtime":
        kwargs["runtime_identity"] = {**kwargs["runtime_identity"], "server_instance_id": "other"}
    elif tamper == "closure":
        kwargs["closure_binding"] = {**kwargs["closure_binding"], "binding_hash": "f" * 64}
    else:
        kwargs["expected_applied_head"] = preapply
    with pytest.raises(RuntimeError):
        service.correct_applied_integration_receipt("closure-bind", **kwargs)


def test_receipt_correction_rejects_non_direct_parent_topology(tmp_path: Path):
    fixture = _applied_receipt_correction_fixture(tmp_path)
    service, root, state, receipt, preapply, applied, candidate, acceptance, approval, runtime = fixture
    _git(root, "commit", "--allow-empty", "-m", "extra")
    state = service._read_state("closure-bind") or state
    kwargs = _correction_kwargs(service, state, receipt, preapply, applied, candidate, acceptance, approval, runtime)
    with pytest.raises(RuntimeError, match="RECEIPT_CORRECTION_PHYSICAL_BINDING_MISMATCH"):
        service.correct_applied_integration_receipt("closure-bind", **kwargs)


def test_receipt_correction_rejects_persisted_state_mutation_after_capture(tmp_path: Path):
    fixture = _applied_receipt_correction_fixture(tmp_path)
    service, root, state, receipt, preapply, applied, candidate, acceptance, approval, runtime = fixture
    kwargs = _correction_kwargs(service, state, receipt, preapply, applied, candidate, acceptance, approval, runtime)
    state["unexpected_persisted_mutation"] = True
    service._write_state("closure-bind", state)
    with pytest.raises(RuntimeError, match="STATE_(BINDING_MISMATCH|CAS_DRIFT)"):
        service.correct_applied_integration_receipt("closure-bind", **kwargs)


def test_receipt_correction_rejects_persisted_receipt_mutation_after_capture(tmp_path: Path):
    fixture = _applied_receipt_correction_fixture(tmp_path)
    service, root, state, receipt, preapply, applied, candidate, acceptance, approval, runtime = fixture
    kwargs = _correction_kwargs(service, state, receipt, preapply, applied, candidate, acceptance, approval, runtime)
    state["integration_receipt"]["verified_receipt_hash"] = "f" * 64
    service._write_state("closure-bind", state)
    kwargs["expected_state_hash"] = hashlib.sha256(
        service._state_path("closure-bind").read_bytes()
    ).hexdigest()
    with pytest.raises(RuntimeError, match="RECEIPT_CORRECTION_RECEIPT_BINDING_MISMATCH"):
        service.correct_applied_integration_receipt("closure-bind", **kwargs)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "nexus.integration_receipt.v0"),
        ("source_branch", "other"),
        ("worktree_removed", True),
        ("failure_reason", "unexpected"),
        ("post_apply_error", "unexpected"),
        ("candidate_commit_sha", "f" * 40),
        ("candidate_tree_sha", "f" * 40),
        ("candidate_state_hash", "f" * 64),
        ("verified_receipt_hash", "f" * 64),
        ("acceptance_receipt_hash", "f" * 64),
        ("authorization_hash", "f" * 64),
        ("integration_commit_sha", "f" * 40),
        ("staging_commit_sha", "f" * 40),
        ("branch_head_after", "f" * 40),
        ("candidate_is_ancestor", False),
        ("staging_verified", False),
        ("verifier_passed", False),
        ("post_apply_verified", False),
        ("merge_performed", False),
        ("push_performed", True),
    ],
)
def test_receipt_correction_rejects_each_persisted_immutable_receipt_field(
    tmp_path: Path, field: str, value: object
):
    fixture = _applied_receipt_correction_fixture(tmp_path)
    service, root, state, receipt, preapply, applied, candidate, acceptance, approval, runtime = fixture
    kwargs = _correction_kwargs(service, state, receipt, preapply, applied, candidate, acceptance, approval, runtime)
    state["integration_receipt"][field] = value
    service._write_state("closure-bind", state)
    kwargs["expected_state_hash"] = hashlib.sha256(
        service._state_path("closure-bind").read_bytes()
    ).hexdigest()
    with pytest.raises(RuntimeError):
        service.correct_applied_integration_receipt("closure-bind", **kwargs)


def test_receipt_correction_rejects_persisted_top_level_merge_mutation(tmp_path: Path):
    fixture = _applied_receipt_correction_fixture(tmp_path)
    service, root, state, receipt, preapply, applied, candidate, acceptance, approval, runtime = fixture
    kwargs = _correction_kwargs(service, state, receipt, preapply, applied, candidate, acceptance, approval, runtime)
    state["merge_performed"] = False
    service._write_state("closure-bind", state)
    kwargs["expected_state_hash"] = hashlib.sha256(
        service._state_path("closure-bind").read_bytes()
    ).hexdigest()
    with pytest.raises(RuntimeError, match="EFFECT_BINDING_MISMATCH"):
        service.correct_applied_integration_receipt("closure-bind", **kwargs)


def test_integrating_rebind_sets_recovery_fence_and_blocks_normal_paths(tmp_path: Path, monkeypatch):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    _git(root, "merge", "--ff-only", "candidate")
    state = service._read_state("closure-bind") or {}
    _git(root, "update-ref", state["candidate_ref"], candidate)
    state.update(status="INTEGRATING", promotion_status="INTEGRATING", merge_performed=False, integration_receipt=None, integration_result_sha=None, integration_execution=None)
    service._write_state("closure-bind", state)
    recovery_approval = {
        **approval,
        "approval_id": approval["approval_id"] + "-recovery",
        "issued_at": "2026-08-09T00:00:00+00:00",
        "expected_canonical_head": candidate,
    }
    rebound = service.bind_candidate_integration_closure(
        "closure-bind", external_acceptance=acceptance,
        approval=recovery_approval,
        runtime_identity=runtime, expected_canonical_head=candidate,
        integration_branch="nexus/integration/canary",
    )
    assert rebound["integration_closure_binding"]["recovery_only"] is True
    assert rebound["integration_recovery_only"] is True
    with pytest.raises(RuntimeError, match="INTEGRATION_RECOVERY_ONLY"):
        service.integrate_approved("closure-bind")
    with pytest.raises(RuntimeError, match="INTEGRATION_RECOVERY_ONLY"):
        service.retry_integration("closure-bind")


def test_closure_binding_concurrent_status_drift_is_zero_write(tmp_path: Path, monkeypatch):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    original_mutate = service._mutate_state

    def drift_before_locked_mutation(task_id, mutate):
        current = service._read_state(task_id) or {}
        current["status"] = "INTEGRATING"
        current["promotion_status"] = "INTEGRATING"
        service._write_state(task_id, current)
        return original_mutate(task_id, mutate)

    monkeypatch.setattr(service, "_mutate_state", drift_before_locked_mutation)
    with pytest.raises(RuntimeError, match="CLOSURE_BINDING_CONCURRENCY_DRIFT"):
        service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    assert "integration_closure_binding" not in (service._read_state("closure-bind") or {})


@pytest.mark.parametrize("status, promotion_status", [("INTEGRATING", "APPROVED"), ("APPROVED", "INTEGRATING")])
def test_integrating_rebind_rejects_mixed_status_pair(tmp_path: Path, status: str, promotion_status: str):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    state = service._read_state("closure-bind") or {}
    state.update(status=status, promotion_status=promotion_status)
    service._write_state("closure-bind", state)
    with pytest.raises(RuntimeError, match="CLOSURE_APPROVED_CANDIDATE_REQUIRED"):
        service.bind_candidate_integration_closure(
            "closure-bind", external_acceptance=acceptance, approval=approval,
            runtime_identity=runtime, expected_canonical_head=base,
            integration_branch="nexus/integration/canary",
        )


def test_recovery_authority_normalizes_only_historical_mixed_pair(tmp_path: Path, monkeypatch):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    state = service._read_state("closure-bind") or {}
    _git(root, "merge", "--ff-only", "candidate")
    _git(root, "update-ref", state["candidate_ref"], candidate)
    state.update(status="INTEGRATING", promotion_status="APPROVED", merge_performed=False,
                 integration_receipt=None, integration_result_sha=None, integration_execution=None,
                 status_history=[])
    service._write_state("closure-bind", state)
    recovery_approval = {**approval, "approval_id": "integrate-recovery",
                         "expected_canonical_head": candidate}
    rebound = service.normalize_integration_recovery_authority(
        "closure-bind", external_acceptance=acceptance, approval=recovery_approval,
        runtime_identity=runtime, expected_canonical_head=candidate,
        integration_branch="nexus/integration/canary")
    assert rebound["status"] == "INTEGRATING"
    assert rebound["promotion_status"] == "INTEGRATING"
    assert rebound["integration_recovery_only"] is True
    assert rebound["integration_closure_binding"]["recovery_only"] is True
    assert rebound["integration_closure_binding"]["approval_id"] == "integrate-recovery"
    assert rebound["integration_execution"] is None
    with pytest.raises(RuntimeError, match="INTEGRATION_RECOVERY_ONLY"):
        service.integrate_approved("closure-bind")
    with pytest.raises(RuntimeError, match="INTEGRATION_RECOVERY_ONLY"):
        service.retry_integration("closure-bind")


def test_recovery_authority_accepts_no_ff_applied_head_and_bound_candidate_tree(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    state = service._read_state("closure-bind") or {}
    _git(root, "merge", "--no-ff", "candidate", "-m", "applied")
    applied = _git(root, "rev-parse", "HEAD")
    assert applied != candidate
    _git(root, "update-ref", state["candidate_ref"], candidate)
    state.update(status="INTEGRATING", promotion_status="APPROVED", merge_performed=False,
                 integration_receipt=None, integration_result_sha=None, integration_execution=None,
                 status_history=[])
    service._write_state("closure-bind", state)
    rebound = service.normalize_integration_recovery_authority(
        "closure-bind", external_acceptance=acceptance,
        approval={**approval, "approval_id": "recover-no-ff", "expected_canonical_head": applied},
        runtime_identity=runtime, expected_canonical_head=applied,
        integration_branch="nexus/integration/canary")
    assert rebound["status"] == "INTEGRATING"
    assert rebound["integration_closure_binding"]["expected_canonical_head"] == applied


@pytest.mark.parametrize("tamper", ["missing", "binding_hash", "authorization_hash"])
def test_recovery_authority_authenticates_prior_closure_before_head(tmp_path: Path, tamper: str):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    state = service._read_state("closure-bind") or {}
    _git(root, "merge", "--no-ff", "candidate", "-m", "applied")
    applied = _git(root, "rev-parse", "HEAD")
    _git(root, "update-ref", state["candidate_ref"], candidate)
    state.update(status="INTEGRATING", promotion_status="APPROVED", merge_performed=False,
                 integration_receipt=None, integration_result_sha=None, integration_execution=None,
                 status_history=[])
    if tamper == "missing":
        state.pop("integration_closure_binding")
    elif tamper == "binding_hash":
        state["integration_closure_binding"]["binding_hash"] = "f" * 64
    else:
        state["integration_closure_binding"]["authorization_hash"] = "f" * 64
    service._write_state("closure-bind", state)
    with pytest.raises(RuntimeError, match="CLOSURE_INTEGRATING_PRIOR_(CLOSURE_REQUIRED|CLOSURE_HASH_DRIFT)"):
        service.normalize_integration_recovery_authority(
            "closure-bind", external_acceptance=acceptance,
            approval={**approval, "approval_id": "recover-auth", "expected_canonical_head": applied},
            runtime_identity=runtime, expected_canonical_head=applied,
            integration_branch="nexus/integration/canary")


def test_recovery_authority_rejects_extra_same_tree_commit(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    state = service._read_state("closure-bind") or {}
    _git(root, "merge", "--no-ff", "candidate", "-m", "applied")
    _git(root, "commit", "--allow-empty", "-m", "extra")
    applied = _git(root, "rev-parse", "HEAD")
    _git(root, "update-ref", state["candidate_ref"], candidate)
    state.update(status="INTEGRATING", promotion_status="APPROVED", merge_performed=False,
                 integration_receipt=None, integration_result_sha=None, integration_execution=None,
                 status_history=[])
    service._write_state("closure-bind", state)
    with pytest.raises(RuntimeError, match="CLOSURE_INTEGRATING_APPLIED_TOPOLOGY_REQUIRED"):
        service.normalize_integration_recovery_authority(
            "closure-bind", external_acceptance=acceptance,
            approval={**approval, "approval_id": "recover-extra", "expected_canonical_head": applied},
            runtime_identity=runtime, expected_canonical_head=applied,
            integration_branch="nexus/integration/canary")


def test_recovery_authority_rejects_effects_and_other_mixed_pair(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    state = service._read_state("closure-bind") or {}
    state.update(status="INTEGRATING", promotion_status="APPROVED", merge_performed=True)
    service._write_state("closure-bind", state)
    with pytest.raises(RuntimeError, match="RECOVERY_AUTHORITY_EFFECT_ALREADY_RECORDED"):
        service.normalize_integration_recovery_authority(
            "closure-bind", external_acceptance=acceptance, approval=approval,
            runtime_identity=runtime, expected_canonical_head=base,
            integration_branch="nexus/integration/canary")
    state["merge_performed"] = False
    state["promotion_status"] = "INTEGRATING"
    service._write_state("closure-bind", state)
    with pytest.raises(RuntimeError, match="RECOVERY_AUTHORITY_MIXED_STATE_REQUIRED"):
        service.normalize_integration_recovery_authority(
            "closure-bind", external_acceptance=acceptance, approval=approval,
            runtime_identity=runtime, expected_canonical_head=base,
            integration_branch="nexus/integration/canary")


@pytest.mark.parametrize("effect", ["merge_performed", "integration_result_sha", "integration_receipt", "integration_execution"])
def test_recovery_authority_locked_cas_rejects_concurrent_effect_insertion(tmp_path: Path, monkeypatch, effect: str):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    state = service._read_state("closure-bind") or {}
    _git(root, "merge", "--ff-only", "candidate")
    _git(root, "update-ref", state["candidate_ref"], candidate)
    state.update(status="INTEGRATING", promotion_status="APPROVED", merge_performed=False,
                 integration_receipt=None, integration_result_sha=None, integration_execution=None,
                 status_history=[])
    service._write_state("closure-bind", state)
    original_mutate = service._mutate_state
    raced_bytes = None
    def inject(task_id, mutator):
        nonlocal raced_bytes
        current = service._read_state(task_id) or {}
        current[effect] = True if effect == "merge_performed" else {}
        service._write_state(task_id, current)
        raced_bytes = service._state_path(task_id).read_bytes()
        return original_mutate(task_id, mutator)
    monkeypatch.setattr(service, "_mutate_state", inject)
    with pytest.raises(RuntimeError, match="RECOVERY_AUTHORITY_CONCURRENCY_EFFECT_DRIFT"):
        service.normalize_integration_recovery_authority(
            "closure-bind", external_acceptance=acceptance,
            approval={**approval, "approval_id": "recover-cas", "expected_canonical_head": candidate},
            runtime_identity=runtime, expected_canonical_head=candidate,
            integration_branch="nexus/integration/canary")
    assert service._state_path("closure-bind").read_bytes() == raced_bytes


def test_recovery_authority_exact_replay_only(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    state = service._read_state("closure-bind") or {}
    _git(root, "merge", "--ff-only", "candidate")
    _git(root, "update-ref", state["candidate_ref"], candidate)
    state.update(status="INTEGRATING", promotion_status="APPROVED", merge_performed=False,
                 integration_receipt=None, integration_result_sha=None, integration_execution=None,
                 status_history=[])
    service._write_state("closure-bind", state)
    recovery = {**approval, "approval_id": "recover-replay", "expected_canonical_head": candidate}
    first = service.normalize_integration_recovery_authority(
        "closure-bind", external_acceptance=acceptance, approval=recovery,
        runtime_identity=runtime, expected_canonical_head=candidate,
        integration_branch="nexus/integration/canary")
    replay = service.normalize_integration_recovery_authority(
        "closure-bind", external_acceptance=acceptance, approval=recovery,
        runtime_identity=runtime, expected_canonical_head=candidate,
        integration_branch="nexus/integration/canary")
    assert first["integration_recovery_only"] is True
    assert replay["duplicate"] is True
    with pytest.raises(RuntimeError, match="RECOVERY_AUTHORITY_REPLAY_DRIFT"):
        service.normalize_integration_recovery_authority(
            "closure-bind", external_acceptance=acceptance,
            approval={**recovery, "approval_id": "other-recovery"},
            runtime_identity=runtime, expected_canonical_head=candidate,
            integration_branch="nexus/integration/canary")
def test_integrating_rebind_requires_applied_head_and_candidate_ref(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    state = service._read_state("closure-bind") or {}
    state.update(status="INTEGRATING", promotion_status="INTEGRATING", merge_performed=False, integration_receipt=None, integration_result_sha=None, integration_execution=None)
    service._write_state("closure-bind", state)
    with pytest.raises(RuntimeError, match="CLOSURE_INTEGRATING_APPLIED_TREE_REQUIRED"):
        service.bind_candidate_integration_closure(
            "closure-bind", external_acceptance=acceptance, approval=approval,
            runtime_identity=runtime, expected_canonical_head=base,
            integration_branch="nexus/integration/canary",
        )
    _git(root, "merge", "--ff-only", "candidate")
    _git(root, "update-ref", state["candidate_ref"], candidate)
    recovery_approval = {**approval, "approval_id": approval["approval_id"] + "-recovery", "issued_at": "2026-08-09T00:00:00+00:00", "expected_canonical_head": candidate}
    _git(root, "update-ref", "-d", state["candidate_ref"])
    with pytest.raises(RuntimeError, match="CLOSURE_INTEGRATING_CANDIDATE_REF_DRIFT"):
        service.bind_candidate_integration_closure(
            "closure-bind", external_acceptance=acceptance, approval=recovery_approval,
            runtime_identity=runtime, expected_canonical_head=candidate,
            integration_branch="nexus/integration/canary",
        )


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        (lambda state, approval: state["promotion_packet"].update(candidate_tree_sha="f" * 40), "CLOSURE_CANDIDATE_BINDING_DRIFT"),
        (lambda state, approval: state["promotion_packet"].update(candidate_commit_sha="f" * 40), "CLOSURE_CANDIDATE_BINDING_DRIFT"),
        (lambda state, approval: state["promotion_packet"].update(candidate_state_hash="f" * 64), "CLOSURE_CANDIDATE_BINDING_DRIFT"),
        (lambda state, approval: state["promotion_packet"].update(verified_receipt_hash="f" * 64), "CLOSURE_CANDIDATE_BINDING_DRIFT"),
        (lambda state, approval: state.update(task_id="other-task"), "CLOSURE_TASK_ID_DRIFT"),
        (lambda state, approval: approval.update(bound_attempt_id="other-attempt"), "APPROVAL_BINDING_MISMATCH"),
        (lambda state, approval: approval.update(task_card_hash="f" * 64), "APPROVAL_BINDING_MISMATCH"),
        (lambda state, approval: approval.update(acceptance_receipt_hash="f" * 64), "CLOSURE_CANDIDATE_BINDING_DRIFT"),
        (lambda state, approval: approval.update(integration_branch="nexus/integration/main"), "CLOSURE_BRANCH_BINDING_MISMATCH"),
    ],
)
def test_closure_identity_matrix_fails_closed(tmp_path: Path, tamper, message, monkeypatch):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    state = service._read_state("closure-bind")
    tamper(state, approval)
    if state.get("task_id") != "closure-bind":
        monkeypatch.setattr(service, "_read_state", lambda task_id: state)
    else:
        service._write_state("closure-bind", state)
    with pytest.raises((RuntimeError, ValueError), match=message):
        service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")


def test_closure_artifact_hash_mismatch_fails_closed(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    approval = {**approval, "acceptance_receipt_hash": "a" * 64}
    with pytest.raises(RuntimeError, match="EXTERNAL_ACCEPTANCE_ARTIFACT_HASH_MISMATCH"):
        service.bind_candidate_integration_closure("closure-bind", external_acceptance=replace(acceptance, receipt_hash="a" * 64), approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")


def test_bind_then_integrate_uses_fresh_integration_grant(tmp_path: Path, monkeypatch):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    state = service._read_state("closure-bind")
    state["approved_binding"]["approval_grant"]["expires_at"] = "2020-01-01T00:00:00+00:00"
    service._write_state("closure-bind", state)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    monkeypatch.setattr(service, "_record_integration", lambda receipt, *, task_id=None: {"status": "INTEGRATED", "promotion_status": "INTEGRATED", "task_id": task_id})
    monkeypatch.setattr(RepositoryContractGate, "evaluate_committed_candidate", lambda *args, **kwargs: SimpleNamespace(passed=True, blocking_reasons=()))
    class FakeIntegrationManager:
        def __init__(self, **kwargs):
            pass
        def integrate_authorized_task_state(self, *args, **kwargs):
            return SimpleNamespace()
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.ControlledIntegrationManager", FakeIntegrationManager)
    result = service.integrate_approved("closure-bind", integration_branch="nexus/integration/canary", runtime_identity=runtime)
    assert result["status"] == "INTEGRATED"


def test_closure_exact_replay_is_zero_probe_and_rebind_history_preserves_prior(tmp_path: Path, monkeypatch):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    before = json.dumps(service._read_state("closure-bind"), sort_keys=True, separators=(",", ":"))
    monkeypatch.setattr(WorktreeManager, "_run_git", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("exact replay must not probe environment")))
    replay = service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    assert replay["duplicate"] is True
    assert json.dumps(service._read_state("closure-bind"), sort_keys=True, separators=(",", ":")) == before


def _mark_closure_pre_apply_failed(
    service: SelfHostedTaskService,
    base: str,
) -> dict[str, object]:
    state = service._read_state("closure-bind") or {}
    state.update({
        "status": "INTEGRATION_FAILED_PRE_APPLY",
        "promotion_status": "INTEGRATION_FAILED_PRE_APPLY",
        "terminal_status": "INTEGRATION_FAILED_PRE_APPLY",
        "final_disposition": "INTEGRATION_FAILED_PRE_APPLY",
        "integration_status": "NOT_APPLIED",
        "integration_error": "staging verifier failed: digest-only",
        "integration_result_sha": None,
        "merge_performed": False,
        "integration_execution": {
            "stage": "PRE_APPLY",
            "branch_head_before": base,
            "branch_head_after": base,
            "candidate_commit_sha": state["promotion_packet"]["candidate_commit_sha"],
            "merge_performed": False,
            "post_apply_verified": False,
            "failure_reason": "staging verifier failed: digest-only",
        },
        "status_history": [
            {"status": "INTEGRATION_FAILED_PRE_APPLY", "reason": "verifier"}
        ],
    })
    service._write_state("closure-bind", state)
    return state


def _mark_closure_projected_pre_apply_failed(
    service: SelfHostedTaskService,
    base: str,
) -> dict[str, object]:
    state = _mark_closure_pre_apply_failed(service, base)
    state.update({
        "status": "FINAL_BLOCK",
        "promotion_status": "NOT_CREATED",
        "terminal_status": "INTEGRATION_FAILED_PRE_APPLY",
        "final_disposition": "INTEGRATION_FAILED_PRE_APPLY",
        "status_history": [
            *list(state.get("status_history") or []),
            {"status": "FINAL_BLOCK", "reason": "lost_worker_projection"},
        ],
    })
    service._write_state("closure-bind", state)
    return state


def test_failed_pre_apply_closure_rebind_preserves_append_only_evidence(
    tmp_path: Path,
):
    service, _, base, _, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path)
    )
    first = service.bind_candidate_integration_closure(
        "closure-bind",
        external_acceptance=acceptance,
        approval=approval,
        runtime_identity=runtime,
        expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    first_hash = first["closure_binding"]["binding_hash"]
    _mark_closure_pre_apply_failed(service, base)
    fresh = {
        **approval,
        "approval_id": "integrate-after-pre-apply-failure",
        "issued_at": "2026-08-08T00:05:00+00:00",
    }

    rebound = service.bind_candidate_integration_closure(
        "closure-bind",
        external_acceptance=acceptance,
        approval=fresh,
        runtime_identity=runtime,
        expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    stored = service._read_state("closure-bind") or {}

    assert rebound["integration_performed"] is False
    assert stored["status"] == "APPROVED"
    assert stored["promotion_status"] == "APPROVED"
    assert stored["integration_status"] == "REBIND_READY"
    assert stored["integration_execution"] is None
    assert stored["merge_performed"] is False
    assert stored["integration_result_sha"] is None
    assert stored["integration_closure_history"][-1]["binding_hash"] == first_hash
    failure = stored["integration_failure_history"][-1]
    assert failure["status"] == "INTEGRATION_FAILED_PRE_APPLY"
    assert failure["closure_binding_hash"] == first_hash
    assert failure["approval_id"] == approval["approval_id"]
    assert failure["integration_execution"]["stage"] == "PRE_APPLY"
    assert stored["integration_approval_grant"]["approval_id"] == fresh["approval_id"]
    assert stored["integration_verifier_manifest"]
    manifest_hash = hashlib.sha256(
        json.dumps(
            stored["integration_verifier_manifest"],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert stored["integration_closure_binding"]["verifier_manifest_sha256"] == manifest_hash


def test_projected_pre_apply_failure_rebind_restores_ready_and_preserves_evidence(
    tmp_path: Path,
):
    service, _, base, _, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path)
    )
    first = service.bind_candidate_integration_closure(
        "closure-bind",
        external_acceptance=acceptance,
        approval=approval,
        runtime_identity=runtime,
        expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    first_hash = first["closure_binding"]["binding_hash"]
    _mark_closure_projected_pre_apply_failed(service, base)
    fresh = {
        **approval,
        "approval_id": "integrate-after-projected-pre-apply-failure",
        "issued_at": "2026-08-08T00:07:00+00:00",
    }

    with pytest.raises(RuntimeError, match="CLOSURE_APPROVED_CANDIDATE_REQUIRED"):
        service.bind_candidate_integration_closure(
            "closure-bind",
            external_acceptance=acceptance,
            approval=fresh,
            runtime_identity=runtime,
            expected_canonical_head=base,
            integration_branch="nexus/integration/canary",
        )
    reconciled = service.reconcile_task("closure-bind") or {}
    assert reconciled["status"] == "INTEGRATION_FAILED_PRE_APPLY"
    assert reconciled["promotion_status"] == "INTEGRATION_FAILED_PRE_APPLY"
    assert reconciled["integration_reconciliation_history"][-1]["decision"] == (
        "RESTORE_NATIVE_PRE_APPLY_STATUS"
    )
    before_replay = json.dumps(
        service._read_state("closure-bind"), sort_keys=True, separators=(",", ":")
    )
    replay = service.reconcile_task("closure-bind") or {}
    assert replay["status"] == "INTEGRATION_FAILED_PRE_APPLY"
    assert json.dumps(
        service._read_state("closure-bind"), sort_keys=True, separators=(",", ":")
    ) == before_replay

    rebound = service.bind_candidate_integration_closure(
        "closure-bind",
        external_acceptance=acceptance,
        approval=fresh,
        runtime_identity=runtime,
        expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    stored = service._read_state("closure-bind") or {}

    assert rebound["integration_performed"] is False
    assert stored["status"] == "APPROVED"
    assert stored["promotion_status"] == "APPROVED"
    assert stored["terminal_status"] == "APPROVED"
    assert stored["integration_status"] == "REBIND_READY"
    assert stored["integration_execution"] is None
    assert stored["merge_performed"] is False
    assert stored["integration_result_sha"] is None
    assert stored["integration_closure_history"][-1]["binding_hash"] == first_hash
    failure = stored["integration_failure_history"][-1]
    assert failure["status"] == "INTEGRATION_FAILED_PRE_APPLY"
    assert failure["closure_binding_hash"] == first_hash
    assert failure["approval_id"] == approval["approval_id"]
    assert failure["integration_execution"]["stage"] == "PRE_APPLY"
    assert stored["integration_approval_grant"]["approval_id"] == fresh["approval_id"]
    assert stored["status_history"][-1] == {
        "at": stored["status_history"][-1]["at"],
        "status": "APPROVED",
        "reason": "pre_apply_closure_rebind",
    }


def test_failed_pre_apply_closure_rejects_failed_approval_reuse_zero_write(
    tmp_path: Path,
):
    service, _, base, _, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path)
    )
    service.bind_candidate_integration_closure(
        "closure-bind",
        external_acceptance=acceptance,
        approval=approval,
        runtime_identity=runtime,
        expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    _mark_closure_pre_apply_failed(service, base)
    before = json.dumps(
        service._read_state("closure-bind"), sort_keys=True, separators=(",", ":")
    )

    with pytest.raises(RuntimeError, match="CLOSURE_FAILED_APPROVAL_REUSE"):
        service.bind_candidate_integration_closure(
            "closure-bind",
            external_acceptance=acceptance,
            approval=approval,
            runtime_identity=runtime,
            expected_canonical_head=base,
            integration_branch="nexus/integration/canary",
        )

    assert json.dumps(
        service._read_state("closure-bind"), sort_keys=True, separators=(",", ":")
    ) == before


def test_confirmed_pre_apply_candidate_can_be_rejected_once_and_replayed_idempotently(
    tmp_path: Path,
):
    service, _, base, _, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path)
    )
    service.bind_candidate_integration_closure(
        "closure-bind", external_acceptance=acceptance, approval=approval,
        runtime_identity=runtime, expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    _mark_closure_projected_pre_apply_failed(service, base)
    failed = service.reconcile_task("closure-bind") or {}
    failed.update({"cleanup_decision": "ALREADY_REMOVED", "cleanup_performed": True})
    service._write_state("closure-bind", failed)

    rejected = service.dispose_candidate("closure-bind", disposition="REJECTED")
    assert rejected["status"] == "REJECTED"
    assert rejected["promotion_status"] == "REJECTED"
    assert rejected["candidate_history"][-1]["final_disposition"] == "REJECTED"
    assert rejected["candidate_history"][-1]["pre_apply_disposition_basis"]["merge_performed"] is False

    replay = service.dispose_candidate("closure-bind", disposition="REJECTED")
    assert replay["duplicate"] is True
    assert len((service._read_state("closure-bind") or {}).get("candidate_history") or []) == 1


@pytest.mark.parametrize(
    "tamper",
    [
        lambda state: state.update({"merge_performed": True}),
        lambda state: state.update({"integration_receipt": {"post_apply_verified": True}}),
        lambda state: state.update({"cleanup_performed": False}),
        lambda state: state["promotion_packet"].update({"candidate_state_hash": "f" * 64}),
        lambda state: state.update({"integration_approval_grant": None, "approved_binding": {**state["approved_binding"], "approval_grant": None}}),
        lambda state: state["integration_closure_binding"].update({"candidate_commit_sha": "f" * 40}),
        lambda state: state["external_acceptance"].update({"candidate_commit": "f" * 40}),
        lambda state: state["integration_reconciliation_history"][-1].update({"projection_sha256": "f" * 64}),
    ],
)
def test_pre_apply_candidate_rejection_requires_exact_no_apply_evidence(
    tmp_path: Path, tamper,
):
    service, _, base, _, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path)
    )
    service.bind_candidate_integration_closure(
        "closure-bind", external_acceptance=acceptance, approval=approval,
        runtime_identity=runtime, expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    failed = _mark_closure_projected_pre_apply_failed(service, base)
    failed = service.reconcile_task("closure-bind") or failed
    failed.update({"cleanup_decision": "REMOVED", "cleanup_performed": True})
    tamper(failed)
    service._write_state("closure-bind", failed)
    with pytest.raises(RuntimeError, match="PRE_APPLY_REJECTION_EVIDENCE_REQUIRED"):
        service.dispose_candidate("closure-bind", disposition="REJECTED")


def test_pre_apply_candidate_cannot_be_superseded_by_new_disposition(
    tmp_path: Path,
):
    service, _, base, _, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path)
    )
    service.bind_candidate_integration_closure(
        "closure-bind", external_acceptance=acceptance, approval=approval,
        runtime_identity=runtime, expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    failed = _mark_closure_pre_apply_failed(service, base)
    failed.update({"cleanup_decision": "REMOVED", "cleanup_performed": True})
    service._write_state("closure-bind", failed)
    with pytest.raises(RuntimeError, match="candidate is not pending disposition"):
        service.dispose_candidate(
            "closure-bind", disposition="SUPERSEDED", superseded_by="next-task"
        )


def test_forged_minimal_pre_apply_state_cannot_be_rejected(tmp_path: Path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    service._write_state("forged", {
        "task_id": "forged", "attempt_id": "attempt-1",
        "status": "INTEGRATION_FAILED_PRE_APPLY",
        "promotion_status": "INTEGRATION_FAILED_PRE_APPLY",
        "terminal_status": "INTEGRATION_FAILED_PRE_APPLY",
        "final_disposition": "INTEGRATION_FAILED_PRE_APPLY",
        "integration_status": "NOT_APPLIED", "merge_performed": False,
        "integration_result_sha": None, "integration_receipt": None,
        "cleanup_decision": "REMOVED", "cleanup_performed": True,
        "integration_execution": {
            "stage": "PRE_APPLY", "merge_performed": False,
            "post_apply_verified": False, "branch_head_before": "a",
            "branch_head_after": "a",
        },
        "promotion_packet": {
            "candidate_commit_sha": "a" * 40,
            "candidate_tree_sha": "b" * 40,
            "candidate_state_hash": "c" * 64,
            "verified_receipt_hash": "d" * 64,
        },
        "candidate_ref": "refs/nexus-candidates/forged/" + "a" * 40,
        "approved_binding": {
            "candidate_commit_sha": "a" * 40,
            "candidate_tree_sha": "b" * 40,
            "candidate_state_hash": "c" * 64,
            "verified_receipt_hash": "d" * 64,
            "approval_grant": {"consumed_at": "now"},
        },
    })
    with pytest.raises(RuntimeError, match="PRE_APPLY_REJECTION_EVIDENCE_REQUIRED"):
        service.dispose_candidate("forged", disposition="REJECTED")


@pytest.mark.parametrize(
    "tamper",
    [
        lambda state: state.update(merge_performed=True),
        lambda state: state.update(integration_result_sha="f" * 40),
        lambda state: state.update(integration_receipt={"status": "applied"}),
        lambda state: state["integration_execution"].update(
            stage="POST_APPLY_VERIFICATION"
        ),
        lambda state: state["integration_execution"].update(
            branch_head_after="f" * 40
        ),
        lambda state: state.update(
            status="INTEGRATION_VERIFY_FAILED_AFTER_APPLY",
            promotion_status="INTEGRATION_VERIFY_FAILED_AFTER_APPLY",
        ),
    ],
)
def test_closure_recovery_rejects_non_pre_apply_state_zero_write(
    tmp_path: Path,
    tamper,
):
    service, _, base, _, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path)
    )
    service.bind_candidate_integration_closure(
        "closure-bind",
        external_acceptance=acceptance,
        approval=approval,
        runtime_identity=runtime,
        expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    state = _mark_closure_pre_apply_failed(service, base)
    tamper(state)
    service._write_state("closure-bind", state)
    before = json.dumps(
        service._read_state("closure-bind"), sort_keys=True, separators=(",", ":")
    )
    fresh = {
        **approval,
        "approval_id": "fresh-invalid-recovery",
        "issued_at": "2026-08-08T00:06:00+00:00",
    }

    with pytest.raises(RuntimeError):
        service.bind_candidate_integration_closure(
            "closure-bind",
            external_acceptance=acceptance,
            approval=fresh,
            runtime_identity=runtime,
            expected_canonical_head=base,
            integration_branch="nexus/integration/canary",
        )

    assert json.dumps(
        service._read_state("closure-bind"), sort_keys=True, separators=(",", ":")
    ) == before


@pytest.mark.parametrize(
    "tamper",
    [
        lambda state: state.update(terminal_status="FINAL_BLOCK"),
        lambda state: state.update(final_disposition="FINAL_BLOCK"),
        lambda state: state.update(integration_status="APPLIED"),
        lambda state: state.update(merge_performed=True),
        lambda state: state.update(integration_result_sha="f" * 40),
        lambda state: state.update(integration_receipt={"status": "applied"}),
        lambda state: state["integration_execution"].update(post_apply_verified=True),
        lambda state: state["integration_execution"].update(stage="POST_APPLY_VERIFICATION"),
        lambda state: state["integration_execution"].update(branch_head_after="f" * 40),
        lambda state: state.update(status_history=state["status_history"][:-1]),
        lambda state: state["external_acceptance"].update(task_id="other-task"),
        lambda state: state["integration_approval_grant"].update(
            bound_attempt_id="other-attempt"
        ),
        lambda state: state["integration_authorization"].update(
            candidate_commit="f" * 40
        ),
    ],
)
def test_projected_pre_apply_recovery_rejects_drift_zero_write(
    tmp_path: Path,
    tamper,
):
    service, _, base, _, acceptance, approval, runtime = (
        _approved_closure_service(tmp_path)
    )
    service.bind_candidate_integration_closure(
        "closure-bind",
        external_acceptance=acceptance,
        approval=approval,
        runtime_identity=runtime,
        expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    state = _mark_closure_projected_pre_apply_failed(service, base)
    tamper(state)
    service._write_state("closure-bind", state)
    before = json.dumps(
        service._read_state("closure-bind"), sort_keys=True, separators=(",", ":")
    )
    reconciled = service.reconcile_task("closure-bind") or {}
    assert reconciled["status"] == state["status"]
    assert "integration_reconciliation_history" not in reconciled

    assert json.dumps(
        service._read_state("closure-bind"), sort_keys=True, separators=(",", ":")
    ) == before


def test_closure_rebind_records_append_only_history(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    fresh_runtime = {**runtime, "server_instance_id": "server-2"}
    fresh_approval = {**approval, "approval_id": "integrate-approval-2", "issued_at": "2026-08-08T00:01:00+00:00", "server_instance_id": "server-2"}
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=fresh_approval, runtime_identity=fresh_runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    state = service._read_state("closure-bind") or {}
    assert len(state["integration_closure_history"]) == 1
    prior = state["integration_closure_history"][0]
    assert prior["closure_binding"]["binding_hash"]
    assert prior["superseded_by"] == "integrate-approval-2"
    assert prior["reason"] == "pre_apply_rebind"
    assert state["integration_approval_grant"]["approval_id"] == "integrate-approval-2"
    assert state.get("merge_performed") is not True


@pytest.mark.parametrize("tamper", [
    lambda state: state.update(integration_result_sha="f" * 40),
    lambda state: state.update(integration_closure_history=None),
    lambda state: state["promotion_packet"].update(candidate_tree_sha="f" * 40),
])
def test_closure_rebind_rejects_immutable_or_applied_drift_without_write(tmp_path: Path, tamper):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    state = service._read_state("closure-bind") or {}
    tamper(state)
    service._write_state("closure-bind", state)
    before = json.dumps(service._read_state("closure-bind"), sort_keys=True, separators=(",", ":"))
    with pytest.raises(RuntimeError):
        service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    assert json.dumps(service._read_state("closure-bind"), sort_keys=True, separators=(",", ":")) == before


def test_closure_rebind_rejects_acceptance_reviewer_and_artifact_drift(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    before = json.dumps(service._read_state("closure-bind"), sort_keys=True, separators=(",", ":"))
    with pytest.raises(RuntimeError, match="CLOSURE_IMMUTABLE_BINDING_DRIFT"):
        service.bind_candidate_integration_closure("closure-bind", external_acceptance=replace(acceptance, reviewer_id="other"), approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    artifact = Path(acceptance.verifier_artifact)
    artifact.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval={**approval, "approval_id": "fresh-artifact-check", "issued_at": "2026-08-08T00:03:00+00:00"}, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    assert json.dumps(service._read_state("closure-bind"), sort_keys=True, separators=(",", ":")) == before


def test_closure_rebind_accepts_fresh_canonical_head_pre_apply(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    (root / "value.txt").write_text("head drift\n", encoding="utf-8")
    _git(root, "commit", "-am", "advance integration head")
    fresh_head = _git(root, "rev-parse", "HEAD")
    fresh_approval = {**approval, "approval_id": "integrate-approval-head-2", "issued_at": "2026-08-08T00:02:00+00:00", "expected_canonical_head": fresh_head}
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=fresh_approval, runtime_identity=runtime, expected_canonical_head=fresh_head, integration_branch="nexus/integration/canary")
    assert len((service._read_state("closure-bind") or {}).get("integration_closure_history") or []) == 1


@pytest.mark.parametrize("field,value", [
    ("candidate_commit_sha", "f" * 40),
    ("candidate_state_hash", "f" * 64),
    ("verified_receipt_hash", "f" * 64),
    ("contract_hash", "f" * 64),
    ("task_card_hash", "f" * 64),
])
def test_rebind_identity_matrix_is_zero_write(tmp_path: Path, field: str, value: str):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    state = service._read_state("closure-bind") or {}
    if field in {"candidate_commit_sha", "candidate_state_hash", "verified_receipt_hash"}:
        state["promotion_packet"][field] = value
    else:
        state[field] = value
    service._write_state("closure-bind", state)
    before = json.dumps(service._read_state("closure-bind"), sort_keys=True, separators=(",", ":"))
    fresh = {**approval, "approval_id": "matrix-fresh", "issued_at": "2026-08-08T00:04:00+00:00"}
    with pytest.raises(RuntimeError):
        service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=fresh, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    assert json.dumps(service._read_state("closure-bind"), sort_keys=True, separators=(",", ":")) == before


@pytest.mark.parametrize("field,value", [
    ("task_id", "other-task"), ("attempt_id", "other-attempt"),
    ("candidate_tree_sha", "f" * 40), ("contract_kind", "OWNER_INLINE"),
    ("canonical_branch", "nexus/integration/other"),
    ("bound_action_type", "CANDIDATE_APPROVE"), ("approval_scope", "ALLOW_ACTION_TWICE"),
])
def test_rebind_closure_projection_matrix_is_zero_write(tmp_path: Path, field: str, value: str):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    state = service._read_state("closure-bind") or {}
    state["integration_closure_binding"][field] = value
    service._write_state("closure-bind", state)
    before = json.dumps(service._read_state("closure-bind"), sort_keys=True, separators=(",", ":"))
    fresh = {**approval, "approval_id": "projection-fresh", "issued_at": "2026-08-08T00:05:00+00:00"}
    with pytest.raises(RuntimeError):
        service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=fresh, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    assert json.dumps(service._read_state("closure-bind"), sort_keys=True, separators=(",", ":")) == before


def test_exact_replay_tampered_caller_approval_is_not_duplicate(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    before = json.dumps(service._read_state("closure-bind"), sort_keys=True, separators=(",", ":"))
    with pytest.raises(RuntimeError):
        service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval={**approval, "approved_by": "attacker"}, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    assert json.dumps(service._read_state("closure-bind"), sort_keys=True, separators=(",", ":")) == before


def test_h1_integrate_approved_rejects_expired_authorization_before_staging_or_apply(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure(
        "closure-bind",
        external_acceptance=acceptance,
        approval=approval,
        runtime_identity=runtime,
        expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    state = service._read_state("closure-bind") or {}
    auth_envelope = IntegrationAuthorizationEnvelope(
        **{
            **{k: v for k, v in state["integration_authorization"].items() if k != "authorization_hash"},
            "expires_at": "2000-01-01T00:00:00+00:00",
        }
    )
    auth_dict = auth_envelope.to_dict()
    auth_dict["authorization_hash"] = auth_envelope.authorization_hash
    state["integration_authorization"] = auth_dict
    service._write_state("closure-bind", state)

    with pytest.raises(RuntimeError, match="authorization expired"):
        service.integrate_approved(
            "closure-bind",
            integration_branch="nexus/integration/canary",
            runtime_identity=runtime,
        )

    # Mutation Sentinel: no staging or Git merge occurred on canonical root
    assert _git(root, "rev-parse", "HEAD") == base
    final_state = service._read_state("closure-bind") or {}
    assert final_state.get("status") in {"APPROVED", "INTEGRATION_FAILED_PRE_APPLY"}
    assert not final_state.get("merge_performed")


def test_h2_retry_integration_rejects_expired_authorization_before_apply(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure(
        "closure-bind",
        external_acceptance=acceptance,
        approval=approval,
        runtime_identity=runtime,
        expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    state = service._read_state("closure-bind") or {}
    auth_envelope = IntegrationAuthorizationEnvelope(
        **{
            **{k: v for k, v in state["integration_authorization"].items() if k != "authorization_hash"},
            "expires_at": "2000-01-01T00:00:00+00:00",
        }
    )
    auth_dict = auth_envelope.to_dict()
    auth_dict["authorization_hash"] = auth_envelope.authorization_hash
    state["integration_authorization"] = auth_dict
    state["status"] = "INTEGRATION_FAILED_PRE_APPLY"
    state["promotion_status"] = "INTEGRATION_FAILED_PRE_APPLY"
    state["merge_performed"] = False
    service._write_state("closure-bind", state)

    with pytest.raises(RuntimeError, match="authorization expired"):
        service.retry_integration("closure-bind", integration_branch="nexus/integration/canary")

    # Mutation Sentinel: no Git branch update-ref or merge performed
    assert _git(root, "rev-parse", "HEAD") == base
    final_state = service._read_state("closure-bind") or {}
    assert final_state.get("merge_performed") is False


def test_h3_retry_integration_preserves_valid_unexpired_authorization(tmp_path: Path, monkeypatch):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure(
        "closure-bind",
        external_acceptance=acceptance,
        approval=approval,
        runtime_identity=runtime,
        expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    state = service._read_state("closure-bind") or {}
    state["status"] = "INTEGRATION_FAILED_PRE_APPLY"
    state["promotion_status"] = "INTEGRATION_FAILED_PRE_APPLY"
    state["merge_performed"] = False
    service._write_state("closure-bind", state)

    monkeypatch.setattr(
        service,
        "_record_integration",
        lambda receipt, *, task_id=None: {"status": "INTEGRATED", "promotion_status": "INTEGRATED", "task_id": task_id},
    )
    monkeypatch.setattr(
        RepositoryContractGate,
        "evaluate_committed_candidate",
        lambda *args, **kwargs: SimpleNamespace(passed=True, blocking_reasons=()),
    )
    class FakeIntegrationManager:
        def __init__(self, **kwargs):
            pass
        def integrate_authorized_task_state(self, *args, **kwargs):
            return SimpleNamespace()
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.ControlledIntegrationManager",
        FakeIntegrationManager,
    )

    result = service.retry_integration("closure-bind", integration_branch="nexus/integration/canary")
    assert result["status"] == "INTEGRATED"


def test_h4_post_apply_retry_still_forbidden(tmp_path: Path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state(
        "post-apply-retry",
        {
            "task_id": "post-apply-retry",
            "status": "INTEGRATION_VERIFY_FAILED_AFTER_APPLY",
            "promotion_status": "INTEGRATION_VERIFY_FAILED_AFTER_APPLY",
            "merge_performed": True,
            "approved_binding": {"candidate_commit_sha": "a" * 40},
        },
    )
    with pytest.raises(RuntimeError, match="INTEGRATION_ALREADY_APPLIED_RETRY_FORBIDDEN"):
        service.retry_integration("post-apply-retry")


def test_h5_none_expiry_preserved(tmp_path: Path, monkeypatch):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure(
        "closure-bind",
        external_acceptance=acceptance,
        approval=approval,
        runtime_identity=runtime,
        expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    state = service._read_state("closure-bind") or {}
    auth_envelope = IntegrationAuthorizationEnvelope(
        **{
            **{k: v for k, v in state["integration_authorization"].items() if k != "authorization_hash"},
            "expires_at": None,
        }
    )
    auth_dict = auth_envelope.to_dict()
    auth_dict["authorization_hash"] = auth_envelope.authorization_hash
    state["integration_authorization"] = auth_dict
    service._write_state("closure-bind", state)

    monkeypatch.setattr(
        service,
        "_record_integration",
        lambda receipt, *, task_id=None: {"status": "INTEGRATED", "promotion_status": "INTEGRATED", "task_id": task_id},
    )
    monkeypatch.setattr(
        RepositoryContractGate,
        "evaluate_committed_candidate",
        lambda *args, **kwargs: SimpleNamespace(passed=True, blocking_reasons=()),
    )
    class FakeIntegrationManager:
        def __init__(self, **kwargs):
            pass
        def integrate_authorized_task_state(self, *args, **kwargs):
            return SimpleNamespace()
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.ControlledIntegrationManager",
        FakeIntegrationManager,
    )
    result = service.integrate_approved(
        "closure-bind",
        integration_branch="nexus/integration/canary",
        runtime_identity=runtime,
    )
    assert result["status"] == "INTEGRATED"


def test_h6_expiry_hash_tamper_fails_closed(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure(
        "closure-bind",
        external_acceptance=acceptance,
        approval=approval,
        runtime_identity=runtime,
        expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    state = service._read_state("closure-bind") or {}
    state["integration_authorization"]["expires_at"] = "2099-12-31T00:00:00+00:00"
    service._write_state("closure-bind", state)

    with pytest.raises(RuntimeError, match="INTEGRATION_AUTHORIZATION_TAMPERED|INTEGRATION_BINDING_DRIFT_AT_APPLY_BOUNDARY|INTEGRATION_AUTHORIZATION_DRIFT"):
        service.integrate_approved(
            "closure-bind",
            integration_branch="nexus/integration/canary",
            runtime_identity=runtime,
        )


def test_h7_existing_binding_drift_controls_fail_closed(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure(
        "closure-bind",
        external_acceptance=acceptance,
        approval=approval,
        runtime_identity=runtime,
        expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    (root / "value.txt").write_text("drift\n")
    _git(root, "commit", "-am", "drift commit")
    with pytest.raises(RuntimeError):
        service.integrate_approved(
            "closure-bind",
            integration_branch="nexus/integration/canary",
            runtime_identity=runtime,
        )


def test_h8_transactional_integration_rejects_expired_authorization_before_staging_or_apply(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    receipt = _acceptance(candidate)
    auth = replace(
        _authorization(root, base, candidate, receipt),
        expires_at="2000-01-01T00:00:00+00:00",
    )
    with pytest.raises(RuntimeError, match="authorization expired"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1",
            canonical_root=str(root.resolve()),
            candidate_commit=candidate,
            expected_canonical_head=base,
            staging_root=str(tmp_path / "stage"),
            apply=True,
            external_acceptance=receipt,
            authorization=auth,
        )

    # Mutation Sentinel: HEAD is untouched, no staging directory created
    assert _git(root, "rev-parse", "HEAD") == base
    assert not (tmp_path / "stage" / "task-1").exists()


def _persist_replay_workforce(state: dict[str, object]) -> None:
    workforce_demands = {
        "schema": "nexus.workforce_demands.v1",
        "route_authority": "CapabilityPlanner",
        "demands": [{
            "schema": "nexus.workforce_demand.v1",
            "demand_id": "replay",
            "execution_channel": "local",
            "requested_role": "implementation",
            "minimum_autonomy": "L1",
            "context_class": "repository",
            "mutation_intent": True,
            "external_verification_required": True,
            "route_authority": "CapabilityPlanner",
            "reasons": [],
        }],
    }
    workforce_admission = {
        "schema": "nexus.runtime_workforce_admission.v1",
        "policy_identity": {"policy_hash": "1" * 64},
        "overall_decision": "ALLOW",
        "overall_reasons": [],
        "records": [{
            "schema": "nexus.runtime_workforce_admission_record.v1",
            "demand": workforce_demands["demands"][0],
            "request": {
                "requested_worker_id": "worker-replay",
                "provider": "codex",
                "model": "codex-test",
            },
            "decision": {
                "decision": "ALLOW",
                "resolved_worker_id": "worker-replay",
                "resolved_provider": "codex",
                "resolved_model": "codex-test",
            },
            "binding_hash": "2" * 64,
        }],
        "aggregate_binding_hash": "3" * 64,
    }
    record = workforce_admission["records"][0]
    demand_object = WorkforceDemand.from_dict(record["demand"])
    record["binding_hash"] = _sha256_json(
        _binding_payload(
            demand_object, record["request"], record["decision"],
            workforce_admission["policy_identity"],
        )
    )
    workforce_admission["aggregate_binding_hash"] = _sha256_json({
        "policy_hash": "1" * 64,
        "record_hashes": [record["binding_hash"]],
    })
    dispatch_envelope = {
        "schema": "nexus.canonical_dispatch_envelope.v1",
        "task_id": "closure-bind",
        "attempt_id": "attempt-1",
        "task_card_path": "tasks/campaign/task.md",
        "task_card_hash": "c" * 64,
        "demand_id": "replay",
        "planner_decision_hash": "4" * 64,
        "planner_plan_hash": "5" * 64,
        "worker_id": "worker-replay",
        "provider": "codex",
        "model": "codex-test",
        "policy_hash": "1" * 64,
        "binding_hash": record["binding_hash"],
        "aggregate_binding_hash": workforce_admission["aggregate_binding_hash"],
    }
    workforce_dispatch = {
        "demands": workforce_demands,
        "admission": workforce_admission,
        "canonical_dispatch_envelope": dispatch_envelope,
        "demand_id": "replay",
        "worker_id": "worker-replay",
        "provider": "codex",
        "model": "codex-test",
        "policy_hash": "1" * 64,
        "binding_hash": record["binding_hash"],
        "aggregate_binding_hash": workforce_admission["aggregate_binding_hash"],
    }
    request = state["request"]
    assert isinstance(request, dict)
    request.update(
        workforce_demands=workforce_demands,
        workforce_admission=workforce_admission,
        canonical_dispatch_envelope=dispatch_envelope,
    )
    state.update(
        workforce_dispatch=workforce_dispatch,
        canonical_dispatch_envelope=dispatch_envelope,
        task_card_path="tasks/campaign/task.md",
        task_card_hash="c" * 64,
        selected_worker_id="worker-replay",
        selected_provider="codex",
        selected_model="codex-test",
        workforce_policy_hash="1" * 64,
        workforce_binding_hash=record["binding_hash"],
        workforce_aggregate_binding_hash=workforce_admission["aggregate_binding_hash"],
    )


def test_integration_replays_persisted_contract_when_request_workforce_receipt_is_stale(
    tmp_path: Path, monkeypatch
):
    """An approved Candidate replays immutable Workforce data without re-admission."""
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure(
        "closure-bind",
        external_acceptance=acceptance,
        approval=approval,
        runtime_identity=runtime,
        expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    state = service._read_state("closure-bind") or {}
    _persist_replay_workforce(state)
    service._write_state("closure-bind", state)

    def no_recompute(*args, **kwargs):
        raise AssertionError("integration replay must not re-evaluate Workforce admission")

    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.evaluate_runtime_workforce_admission",
        no_recompute,
    )
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.validate_workforce_dispatch_binding",
        no_recompute,
    )
    monkeypatch.setattr(
        RepositoryContractGate,
        "evaluate_committed_candidate",
        lambda *args, **kwargs: SimpleNamespace(passed=True, blocking_reasons=()),
    )
    calls: list[str] = []

    class FakeIntegrationManager:
        def __init__(self, **kwargs):
            pass

        def integrate_authorized_task_state(self, *args, **kwargs):
            calls.append("integration_manager")
            return SimpleNamespace()

    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.ControlledIntegrationManager",
        FakeIntegrationManager,
    )
    monkeypatch.setattr(
        service,
        "_record_integration",
        lambda receipt, *, task_id=None: {
            "status": "INTEGRATED",
            "promotion_status": "INTEGRATED",
            "task_id": task_id,
        },
    )

    result = service.integrate_approved(
        "closure-bind",
        integration_branch="nexus/integration/canary",
        runtime_identity=runtime,
    )

    assert result["status"] == "INTEGRATED"
    assert calls == ["integration_manager"]


def test_record_integration_replays_persisted_contract_after_apply_and_is_idempotent(
    tmp_path: Path, monkeypatch
):
    """Recording an applied receipt must not rebuild a mutable request contract."""
    from nexus.orchestrator.governed_integration import IntegrationReceipt

    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure(
        "closure-bind",
        external_acceptance=acceptance,
        approval=approval,
        runtime_identity=runtime,
        expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    state = service._read_state("closure-bind") or {}
    authorization_hash = str(state["integration_authorization"]["authorization_hash"])
    receipt = IntegrationReceipt(
        schema="nexus.integration_receipt/v1",
        task_id="closure-bind",
        integration_branch="nexus/integration/canary",
        source_branch="nexus/task/closure-bind",
        candidate_commit_sha=candidate,
        integration_base_sha=base,
        integration_commit_sha=candidate,
        verifier_passed=True,
        merge_performed=True,
        push_performed=False,
        worktree_removed=False,
        staging_commit_sha=candidate,
        post_apply_verified=True,
        acceptance_receipt_hash=acceptance.receipt_hash,
        authorization_hash=authorization_hash,
    )

    monkeypatch.setattr(
        service,
        "build_contract",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("recording must replay persisted contract")
        ),
    )
    first = service._record_integration(receipt, task_id="closure-bind")
    second = service.integrate_approved("closure-bind")

    assert first["status"] == "INTEGRATED"
    assert second["status"] == "INTEGRATED"
    assert second["integration_result_sha"] == candidate


def test_receipt_only_recovery_records_applied_integrating_state_without_merge(
    tmp_path: Path, monkeypatch
):
    """Recovery records a witnessed applied HEAD and never reruns integration."""
    from nexus.orchestrator.governed_integration import IntegrationReceipt

    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure(
        "closure-bind",
        external_acceptance=acceptance,
        approval=approval,
        runtime_identity=runtime,
        expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    _git(root, "merge", "--ff-only", "candidate")
    state = service._read_state("closure-bind") or {}
    state.update(
        status="INTEGRATING",
        promotion_status="INTEGRATING",
        integration_branch="nexus/integration/canary",
        merge_performed=False,
        integration_receipt=None,
        integration_result_sha=None,
        integration_execution=None,
    )
    service._write_state("closure-bind", state)
    receipt = IntegrationReceipt(
        schema="nexus.integration_receipt/v1",
        task_id="closure-bind",
        integration_branch="nexus/integration/canary",
        source_branch="nexus/task/closure-bind",
        candidate_commit_sha=candidate,
        integration_base_sha=base,
        integration_commit_sha=candidate,
        verifier_passed=True,
        merge_performed=True,
        push_performed=False,
        worktree_removed=False,
        staging_commit_sha=candidate,
        post_apply_verified=True,
        acceptance_receipt_hash=acceptance.receipt_hash,
        authorization_hash=state["integration_authorization"]["authorization_hash"],
        task_card_hash=state["task_card_hash"],
        candidate_tree_sha=state["promotion_packet"]["candidate_tree_sha"],
        candidate_state_hash=state["promotion_packet"]["candidate_state_hash"],
        verified_receipt_hash=state["promotion_packet"]["verified_receipt_hash"],
    )
    monkeypatch.setattr(
        service,
        "build_contract",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("recovery must not rebuild request contract")
        ),
    )
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.ControlledIntegrationManager",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("recovery must not invoke integration manager")
        ),
    )

    recovery_runtime = state["integration_closure_binding"]["runtime_identity"]
    original_state = json.loads(json.dumps(state))
    state["execution_authority"] = "WORKER_REGISTRY"
    state["request"].pop("workforce_demands", None)
    state["request"].pop("workforce_admission", None)
    state["request"].pop("canonical_dispatch_envelope", None)
    state.pop("workforce_dispatch", None)
    state.pop("canonical_dispatch_envelope", None)
    state["integration_recovery_only"] = True
    state["integration_closure_binding"]["recovery_only"] = True
    closure_payload = {
        key: value for key, value in state["integration_closure_binding"].items()
        if key != "binding_hash"
    }
    state["integration_closure_binding"]["binding_hash"] = hashlib.sha256(
        json.dumps(closure_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    service._write_state("closure-bind", state)
    with pytest.raises(RuntimeError, match="INTEGRATION_WORKFORCE_DISPATCH_DRIFT"):
        service.recover_applied_integration_receipt(
            "closure-bind", receipt, runtime_identity=recovery_runtime
        )
    service._write_state("closure-bind", original_state)
    original_state["integration_recovery_only"] = True
    original_state["integration_closure_binding"]["recovery_only"] = True
    restored_closure = {
        key: value for key, value in original_state["integration_closure_binding"].items()
        if key != "binding_hash"
    }
    original_state["integration_closure_binding"]["binding_hash"] = hashlib.sha256(
        json.dumps(restored_closure, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    service._write_state("closure-bind", original_state)
    first = service.recover_applied_integration_receipt(
        "closure-bind", receipt, runtime_identity=recovery_runtime
    )
    second = service.recover_applied_integration_receipt(
        "closure-bind", receipt, runtime_identity=recovery_runtime
    )

    assert first["status"] == "INTEGRATED"
    assert second["status"] == "INTEGRATED"
    assert second["integration_result_sha"] == candidate
    with pytest.raises(RuntimeError, match="idempotency receipt mismatch"):
        service.recover_applied_integration_receipt(
            "closure-bind", replace(receipt, task_id="unrelated-task"),
            runtime_identity=recovery_runtime,
        )


@pytest.mark.parametrize("tamper", ["request", "dispatch", "hash", "coordinated"])
def test_integration_blocks_persisted_workforce_projection_tamper(
    tmp_path: Path, tamper: str
):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure(
        "closure-bind",
        external_acceptance=acceptance,
        approval=approval,
        runtime_identity=runtime,
        expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    state = service._read_state("closure-bind") or {}
    _persist_replay_workforce(state)
    if tamper == "request":
        state["request"]["workforce_admission"] = {}
    elif tamper == "dispatch":
        state["workforce_dispatch"]["canonical_dispatch_envelope"] = {}
    elif tamper == "coordinated":
        state["request"]["workforce_admission"]["records"][0]["request"]["provider"] = "agy"
        state["request"]["workforce_admission"]["records"][0]["decision"]["resolved_provider"] = "agy"
        state["request"]["canonical_dispatch_envelope"]["provider"] = "agy"
        state["canonical_dispatch_envelope"]["provider"] = "agy"
        state["workforce_dispatch"]["provider"] = "agy"
        state["selected_provider"] = "agy"
        record = state["request"]["workforce_admission"]["records"][0]
        record["binding_hash"] = _sha256_json(
            _binding_payload(
                WorkforceDemand.from_dict(record["demand"]),
                record["request"], record["decision"],
                state["request"]["workforce_admission"]["policy_identity"],
            )
        )
        aggregate_hash = _sha256_json({
            "policy_hash": state["request"]["workforce_admission"]["policy_identity"]["policy_hash"],
            "record_hashes": [record["binding_hash"]],
        })
        state["request"]["workforce_admission"]["aggregate_binding_hash"] = aggregate_hash
        state["workforce_dispatch"]["binding_hash"] = record["binding_hash"]
        state["workforce_dispatch"]["aggregate_binding_hash"] = aggregate_hash
        state["workforce_binding_hash"] = record["binding_hash"]
        state["workforce_aggregate_binding_hash"] = aggregate_hash
        state["request"]["canonical_dispatch_envelope"]["binding_hash"] = record["binding_hash"]
        state["canonical_dispatch_envelope"]["binding_hash"] = record["binding_hash"]
        state["workforce_dispatch"]["canonical_dispatch_envelope"]["binding_hash"] = record["binding_hash"]
        state["request"]["canonical_dispatch_envelope"]["aggregate_binding_hash"] = aggregate_hash
        state["canonical_dispatch_envelope"]["aggregate_binding_hash"] = aggregate_hash
        state["workforce_dispatch"]["canonical_dispatch_envelope"]["aggregate_binding_hash"] = aggregate_hash
    else:
        state["workforce_binding_hash"] = "f" * 64
    service._write_state("closure-bind", state)

    with pytest.raises(RuntimeError, match="INTEGRATION_WORKFORCE_DISPATCH_DRIFT"):
        service.integrate_approved(
            "closure-bind",
            integration_branch="nexus/integration/canary",
            runtime_identity=runtime,
        )


def test_integration_blocks_malformed_persisted_dispatch_envelope(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure(
        "closure-bind", external_acceptance=acceptance, approval=approval,
        runtime_identity=runtime, expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    state = service._read_state("closure-bind") or {}
    _persist_replay_workforce(state)
    state["request"]["canonical_dispatch_envelope"] = {"schema": "wrong"}
    state["canonical_dispatch_envelope"] = state["request"]["canonical_dispatch_envelope"]
    state["workforce_dispatch"]["canonical_dispatch_envelope"] = state["canonical_dispatch_envelope"]
    service._write_state("closure-bind", state)
    with pytest.raises(RuntimeError, match="INTEGRATION_WORKFORCE_DISPATCH_DRIFT"):
        service.integrate_approved(
            "closure-bind", integration_branch="nexus/integration/canary",
            runtime_identity=runtime,
        )


def test_integration_blocks_worker_registry_without_persisted_dispatch(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    service.bind_candidate_integration_closure(
        "closure-bind", external_acceptance=acceptance, approval=approval,
        runtime_identity=runtime, expected_canonical_head=base,
        integration_branch="nexus/integration/canary",
    )
    state = service._read_state("closure-bind") or {}
    state["execution_authority"] = "WORKER_REGISTRY"
    service._write_state("closure-bind", state)
    with pytest.raises(RuntimeError, match="INTEGRATION_WORKFORCE_DISPATCH_DRIFT"):
        service.integrate_approved(
            "closure-bind", integration_branch="nexus/integration/canary",
            runtime_identity=runtime,
        )
