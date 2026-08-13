# ruff: noqa: E402

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

repo_root = str(Path(__file__).resolve().parents[3])
if repo_root in sys.path:
    sys.path.remove(repo_root)
sys.path.insert(0, repo_root)

import pytest

from nexus.contracts.lifecycle_action import (
    ContractKind,
    LifecycleActionType,
    build_action_envelope,
    build_owner_inline_contract,
    canonical_request_hash,
)
from nexus.contracts.operator_outcome_receipt import build_operator_outcome_receipt
from nexus.contracts.target_integration_lifecycle import (
    ExternalAcceptanceReceipt,
    IntegrationAuthorizationEnvelope,
)
from nexus.engine.canonical_task_seam import (
    VerifiedTaskCardIdentity,
    build_canonical_dispatch_envelope,
    build_canonical_planner_admission,
)
from nexus.executors.worker_contract import (
    SUPPORTED_WORKER_PROVIDERS,
    WorkerExecutionReceipt,
    WorkerOutcome,
    WorkerPreflight,
)
from nexus.executors.worker_registry import WorkerRegistry
from nexus.orchestrator.repository_contract_gate import (
    RepositoryContractGate,
    RepositoryContractGateReceipt,
)
from nexus.orchestrator.self_hosted_task_service import (
    SelfHostedTaskService,
    resolve_canonical_target_roots,
    resolve_execution_lane,
    validate_task_card_binding,
    validate_workforce_dispatch_binding,
)
from nexus.events.transport import NexusEventBus
from nexus.orchestrator.worktree_manager import (
    TargetWorktreeLease,
    WorktreeManager,
    get_canonical_git_hooks_dir,
)
from nexus.services.model_workforce_policy import WorkforcePolicyLoader
from nexus.services.runtime_workforce_admission import evaluate_runtime_workforce_admission


def _operator_provenance(kind="operator"):
    source = {"source_ref": "authenticated-submission"}
    if kind == "system":
        source = {"source_hash": "c" * 64}
    return {
        field: {"provenance": kind, **source}
        for field in (
            "observed_outcome",
            "observation_basis",
            "reason_code",
            "observed_at",
            "source_revision",
            "runtime_receipt_hash",
        )
    }


def _request(tmp_path: Path, **overrides):
    values = {
        "task_id": "mcp-task-001",
        "what": "Add one bounded canary test",
        "why": "Prove the MCP request becomes a governed task",
        "controller_revision": "a" * 40,
        "target_base_revision": "b" * 40,
        "controller_repo_root": str(tmp_path / "controller"),
        "target_repo_root": str(tmp_path / "targets" / "mcp-task-001"),
        "target_worktree_root": str(tmp_path / "targets"),
        "allowed_files": ["nexus_canary.txt"],
        "forbidden_files": ["nexus/orchestrator/"],
        "verifier_commands": ["python3 -c 'print(\"pass\")'"],
        "protected_contracts": ["candidate-receipt-v1"],
        "worker": "codex",
    }
    values.update(overrides)
    return values


def test_operator_outcome_persists_idempotently_and_projects(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("task-1", {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": "task-1",
        "status": "SUBMITTED",
        "attempt_id": "attempt-1",
        "action_id": "action-1",
        "lifecycle_revision": "life-1",
        "controller_revision": "a" * 40,
        "runtime_receipt_hash": "b" * 64,
        "status_history": [],
    })
    receipt = build_operator_outcome_receipt(
        task_id="task-1", attempt_id="attempt-1", action_id="action-1",
        lifecycle_revision="life-1", source_revision="a" * 40,
        runtime_receipt_hash="b" * 64, observed_outcome="SUCCESS",
        observation_basis="OPERATOR_REPORT", reason_code="OPERATOR_CONFIRMED",
        idempotency_key="idem-1", field_provenance=_operator_provenance(),
    )
    first = service.record_operator_outcome("task-1", receipt)
    second = service.record_operator_outcome("task-1", receipt)
    assert first == second
    projected = service.get_receipt("task-1")
    assert projected["operator_outcome_receipt"] == first
    assert len(projected["operator_outcome_receipts"]) == 1
    assert "operator_outcome_receipt" not in service.get_task("task-1")
    conflict = receipt.model_dump(mode="json")
    conflict["observed_outcome"] = "FAILURE"
    conflict["receipt_id"] = "0" * 64
    with pytest.raises(ValueError, match="PAYLOAD_HASH"):
        service.record_operator_outcome("task-1", conflict)


def test_operator_outcome_rejects_supersession_cycle_unknown_target_and_order(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("task-1", {
        "schema": "nexus.self_hosted_task_state.v1", "task_id": "task-1", "status": "SUBMITTED",
        "attempt_id": "attempt-1", "action_id": "action-1", "lifecycle_revision": "life-1", "controller_revision": "a" * 40,
        "runtime_receipt_hash": "b" * 64, "status_history": [],
    })
    kwargs = dict(task_id="task-1", attempt_id="attempt-1", action_id="action-1", lifecycle_revision="life-1",
                  source_revision="a" * 40, runtime_receipt_hash="b" * 64,
                  observed_outcome="SUCCESS", observation_basis="OPERATOR_REPORT", reason_code="OPERATOR_CONFIRMED",
                  field_provenance=_operator_provenance())
    unknown = build_operator_outcome_receipt(**kwargs, idempotency_key="idem-unknown", supersedes_receipt_id="c" * 64)
    with pytest.raises(ValueError, match="SUPERSESSION_TARGET_MISSING"):
        service.record_operator_outcome("task-1", unknown)

    parent = build_operator_outcome_receipt(
        **kwargs, idempotency_key="parent", observed_at=datetime.now(timezone.utc)
    )
    service.record_operator_outcome("task-1", parent)
    older_child = build_operator_outcome_receipt(
        **kwargs, idempotency_key="older-child",
        observed_at=datetime.now(timezone.utc) - timedelta(seconds=30),
        supersedes_receipt_id=parent.receipt_id,
    )
    with pytest.raises(ValueError, match="SUPERSESSION_ORDER_INVALID"):
        service.record_operator_outcome("task-1", older_child)


def test_operator_outcome_optional_runtime_receipt_binds_current_evidence(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("task-1", {"task_id": "task-1", "attempt_id": "a", "action_id": "x", "lifecycle_revision": "l",
                                    "controller_revision": "a" * 40, "runtime_receipt_hash": "b" * 64, "status": "SUBMITTED"})
    receipt = build_operator_outcome_receipt(task_id="task-1", attempt_id="a", action_id="x", lifecycle_revision="l",
        source_revision="a" * 40, runtime_receipt_hash="c" * 64, observed_outcome="SUCCESS",
        observation_basis="SYSTEM_OBSERVATION", reason_code="SYSTEM_RECORDED", idempotency_key="i",
        field_provenance=_operator_provenance("system"))
    with pytest.raises(ValueError, match="RUNTIME_RECEIPT_HASH_MISMATCH"):
        service.record_operator_outcome("task-1", receipt)
    optional = build_operator_outcome_receipt(
        task_id="task-1", attempt_id="a", lifecycle_revision="l",
        observed_outcome="NOT_OBSERVED", observation_basis="NOT_OBSERVED",
        reason_code="NOT_PROVIDED", idempotency_key="optional",
        field_provenance={
            field: {"provenance": "operator", "source_ref": "authenticated-submission"}
            for field in ("observed_outcome", "observation_basis", "reason_code", "observed_at")
        },
    )
    assert service.record_operator_outcome("task-1", optional)["action_id"] is None


def test_operator_outcome_rejects_malformed_persisted_chain(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    runtime_hash = "b" * 64
    malformed = build_operator_outcome_receipt(
        task_id="task-1", attempt_id="attempt-1", action_id="action-1", lifecycle_revision="life-1",
        source_revision="a" * 40, runtime_receipt_hash=runtime_hash, observed_outcome="SUCCESS",
        observation_basis="OPERATOR_REPORT", reason_code="OPERATOR_CONFIRMED", idempotency_key="old", supersedes_receipt_id="c" * 64,
        field_provenance=_operator_provenance(),
    )
    service._write_state("task-1", {"schema": "nexus.self_hosted_task_state.v1", "task_id": "task-1", "status": "SUBMITTED", "attempt_id": "attempt-1", "lifecycle_revision": "life-1",
                                    "controller_revision": "a" * 40, "action_id": "action-1", "runtime_receipt_hash": runtime_hash,
                                    "operator_outcome_receipts": [malformed.model_dump(mode="json")],
                                    "operator_outcome_receipt": malformed.model_dump(mode="json")})
    candidate = build_operator_outcome_receipt(task_id="task-1", attempt_id="attempt-1", action_id="action-1", lifecycle_revision="life-1",
            source_revision="a" * 40, runtime_receipt_hash=runtime_hash, observed_outcome="SUCCESS", observation_basis="OPERATOR_REPORT",
            reason_code="OPERATOR_CONFIRMED", idempotency_key="new", field_provenance=_operator_provenance())
    with pytest.raises(ValueError, match="PERSISTED_SUPERSESSION_TARGET_MISSING"):
        service.record_operator_outcome("task-1", candidate)


def test_operator_outcome_stale_history_remains_valid_and_detailed_snapshot_is_private(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    state = {"schema": "nexus.self_hosted_task_state.v1", "task_id": "task-1", "status": "SUBMITTED",
             "attempt_id": "attempt-1", "action_id": "action-1", "lifecycle_revision": "life-1",
             "controller_revision": "a" * 40, "runtime_receipt_hash": "b" * 64}
    kwargs = dict(task_id="task-1", attempt_id="attempt-1", action_id="action-1", lifecycle_revision="life-1",
                  source_revision="a" * 40, runtime_receipt_hash="b" * 64,
                  observation_basis="OPERATOR_REPORT", reason_code="OPERATOR_CONFIRMED",
                  field_provenance=_operator_provenance())
    stale = build_operator_outcome_receipt(**kwargs, observed_outcome="SUCCESS", idempotency_key="old",
                                           observed_at=datetime.now(timezone.utc) - timedelta(minutes=10))
    state["operator_outcome_receipts"] = [stale.model_dump(mode="json")]
    state["operator_outcome_receipt"] = stale.model_dump(mode="json")
    service._write_state("task-1", state)
    fresh = build_operator_outcome_receipt(**kwargs, observed_outcome="FAILURE", idempotency_key="new")
    service.record_operator_outcome("task-1", fresh)
    assert len(service.get_receipt("task-1")["operator_outcome_receipts"]) == 2
    detailed = service.get_task_snapshot("task-1", include_details=True)
    assert "operator_outcome_receipt" not in detailed
    assert "operator_outcome_receipts" not in detailed
    completed_wait = service.wait_task("task-1", include_details=True)
    assert "operator_outcome_receipt" not in completed_wait
    assert "operator_outcome_receipts" not in completed_wait
    state["status"] = "RUNNING"
    service._write_state("task-1", state)
    timed_out_wait = service.wait_task(
        "task-1", timeout_seconds=0, include_details=True
    )
    assert "operator_outcome_receipt" not in timed_out_wait
    assert "operator_outcome_receipts" not in timed_out_wait


def test_operator_outcome_revalidates_identity_inside_locked_append(tmp_path, monkeypatch):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    service._write_state(
        "task-1",
        {
            "schema": "nexus.self_hosted_task_state.v1",
            "task_id": "task-1",
            "status": "SUBMITTED",
            "attempt_id": "attempt-1",
            "action_id": "action-1",
            "lifecycle_revision": "life-1",
            "controller_revision": "a" * 40,
            "runtime_receipt_hash": "b" * 64,
        },
    )
    receipt = build_operator_outcome_receipt(
        task_id="task-1",
        attempt_id="attempt-1",
        action_id="action-1",
        lifecycle_revision="life-1",
        source_revision="a" * 40,
        runtime_receipt_hash="b" * 64,
        observed_outcome="SUCCESS",
        observation_basis="OPERATOR_REPORT",
        reason_code="OPERATOR_CONFIRMED",
        idempotency_key="race",
        field_provenance=_operator_provenance(),
    )
    original_mutate = service._mutate_state

    def drift_then_mutate(task_id, mutator):
        state = service._read_state(task_id)
        state["attempt_id"] = "attempt-2"
        state["lifecycle_revision"] = "life-2"
        service._write_state(task_id, state)
        return original_mutate(task_id, mutator)

    monkeypatch.setattr(service, "_mutate_state", drift_then_mutate)
    with pytest.raises(ValueError, match="ATTEMPT_ID_MISMATCH"):
        service.record_operator_outcome("task-1", receipt)
    assert not service._read_state("task-1").get("operator_outcome_receipts")


def test_operator_outcome_preserves_valid_prior_attempt_history(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    prior = build_operator_outcome_receipt(
        task_id="task-1",
        attempt_id="attempt-1",
        action_id="action-1",
        lifecycle_revision="life-1",
        source_revision="a" * 40,
        runtime_receipt_hash="b" * 64,
        observed_outcome="FAILURE",
        observation_basis="OPERATOR_REPORT",
        reason_code="OPERATOR_CONFIRMED",
        idempotency_key="prior-attempt",
        observed_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        field_provenance=_operator_provenance(),
    )
    service._write_state(
        "task-1",
        {
            "schema": "nexus.self_hosted_task_state.v1",
            "task_id": "task-1",
            "status": "SUBMITTED",
            "attempt_id": "attempt-2",
            "action_id": "action-2",
            "lifecycle_revision": "life-2",
            "controller_revision": "c" * 40,
            "runtime_receipt_hash": "d" * 64,
            "operator_outcome_receipt": prior.model_dump(mode="json"),
            "operator_outcome_receipts": [prior.model_dump(mode="json")],
        },
    )
    current = build_operator_outcome_receipt(
        task_id="task-1",
        attempt_id="attempt-2",
        action_id="action-2",
        lifecycle_revision="life-2",
        source_revision="c" * 40,
        runtime_receipt_hash="d" * 64,
        observed_outcome="SUCCESS",
        observation_basis="OPERATOR_REPORT",
        reason_code="OPERATOR_CONFIRMED",
        idempotency_key="current-attempt",
        field_provenance=_operator_provenance(),
    )
    service.record_operator_outcome("task-1", current)
    projected = service.get_receipt("task-1")
    assert [item["attempt_id"] for item in projected["operator_outcome_receipts"]] == [
        "attempt-1",
        "attempt-2",
    ]
    cross_attempt = build_operator_outcome_receipt(
        task_id="task-1",
        attempt_id="attempt-2",
        action_id="action-2",
        lifecycle_revision="life-2",
        source_revision="c" * 40,
        runtime_receipt_hash="d" * 64,
        observed_outcome="SUCCESS",
        observation_basis="OPERATOR_REPORT",
        reason_code="OPERATOR_CONFIRMED",
        idempotency_key="cross-attempt",
        supersedes_receipt_id=prior.receipt_id,
        field_provenance=_operator_provenance(),
    )
    with pytest.raises(ValueError, match="SUPERSESSION_ATTEMPT_MISMATCH"):
        service.record_operator_outcome("task-1", cross_attempt)


@pytest.mark.parametrize(
    "malformed_history",
    [
        {"unexpected": "mapping"},
        ["malformed-non-object"],
        [None],
    ],
)
def test_operator_outcome_rejects_malformed_history_container_or_element(
    tmp_path, malformed_history
):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    state = {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": "task-1",
        "status": "SUBMITTED",
        "attempt_id": "attempt-1",
        "action_id": "action-1",
        "lifecycle_revision": "life-1",
        "controller_revision": "a" * 40,
        "runtime_receipt_hash": "b" * 64,
        "operator_outcome_receipts": malformed_history,
    }
    service._write_state("task-1", state)
    candidate = build_operator_outcome_receipt(
        task_id="task-1",
        attempt_id="attempt-1",
        action_id="action-1",
        lifecycle_revision="life-1",
        source_revision="a" * 40,
        runtime_receipt_hash="b" * 64,
        observed_outcome="SUCCESS",
        observation_basis="OPERATOR_REPORT",
        reason_code="OPERATOR_CONFIRMED",
        idempotency_key="new",
        field_provenance=_operator_provenance(),
    )
    with pytest.raises(ValueError, match="PERSISTED_RECEIPT_TAMPERED"):
        service.record_operator_outcome("task-1", candidate)
    assert service._read_state("task-1")["operator_outcome_receipts"] == malformed_history


def test_operator_outcome_rejects_singular_history_projection_mismatch(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    common = dict(
        task_id="task-1",
        attempt_id="attempt-1",
        action_id="action-1",
        lifecycle_revision="life-1",
        source_revision="a" * 40,
        runtime_receipt_hash="b" * 64,
        observed_outcome="SUCCESS",
        observation_basis="OPERATOR_REPORT",
        reason_code="OPERATOR_CONFIRMED",
        field_provenance=_operator_provenance(),
    )
    listed = build_operator_outcome_receipt(**common, idempotency_key="listed")
    singular = build_operator_outcome_receipt(**common, idempotency_key="singular")
    service._write_state(
        "task-1",
        {
            "schema": "nexus.self_hosted_task_state.v1",
            "task_id": "task-1",
            "status": "SUBMITTED",
            "attempt_id": "attempt-1",
            "action_id": "action-1",
            "lifecycle_revision": "life-1",
            "controller_revision": "a" * 40,
            "runtime_receipt_hash": "b" * 64,
            "operator_outcome_receipts": [listed.model_dump(mode="json")],
            "operator_outcome_receipt": singular.model_dump(mode="json"),
        },
    )
    candidate = build_operator_outcome_receipt(**common, idempotency_key="new")
    with pytest.raises(ValueError, match="PERSISTED_RECEIPT_TAMPERED"):
        service.record_operator_outcome("task-1", candidate)
    assert len(service._read_state("task-1")["operator_outcome_receipts"]) == 1


def test_operator_outcome_rejects_nonempty_history_without_singular_projection(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    common = dict(
        task_id="task-1", attempt_id="attempt-1", action_id="action-1",
        lifecycle_revision="life-1", source_revision="a" * 40,
        runtime_receipt_hash="b" * 64, observed_outcome="SUCCESS",
        observation_basis="OPERATOR_REPORT", reason_code="OPERATOR_CONFIRMED",
        field_provenance=_operator_provenance(),
    )
    prior = build_operator_outcome_receipt(**common, idempotency_key="prior")
    service._write_state("task-1", {
        "schema": "nexus.self_hosted_task_state.v1", "task_id": "task-1",
        "status": "SUBMITTED", "attempt_id": "attempt-1", "action_id": "action-1",
        "lifecycle_revision": "life-1", "controller_revision": "a" * 40,
        "runtime_receipt_hash": "b" * 64,
        "operator_outcome_receipts": [prior.model_dump(mode="json")],
    })
    candidate = build_operator_outcome_receipt(**common, idempotency_key="new")
    with pytest.raises(ValueError, match="PERSISTED_RECEIPT_TAMPERED"):
        service.record_operator_outcome("task-1", candidate)
    assert len(service._read_state("task-1")["operator_outcome_receipts"]) == 1


def test_operator_outcome_allows_empty_history_without_singular_projection(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    service._write_state("task-1", {
        "schema": "nexus.self_hosted_task_state.v1", "task_id": "task-1",
        "status": "SUBMITTED", "attempt_id": "attempt-1", "action_id": "action-1",
        "lifecycle_revision": "life-1", "controller_revision": "a" * 40,
        "runtime_receipt_hash": "b" * 64, "operator_outcome_receipts": [],
    })
    candidate = build_operator_outcome_receipt(
        task_id="task-1", attempt_id="attempt-1", action_id="action-1",
        lifecycle_revision="life-1", source_revision="a" * 40,
        runtime_receipt_hash="b" * 64, observed_outcome="SUCCESS",
        observation_basis="OPERATOR_REPORT", reason_code="OPERATOR_CONFIRMED",
        idempotency_key="first", field_provenance=_operator_provenance(),
    )
    persisted = service.record_operator_outcome("task-1", candidate)
    assert persisted["receipt_id"] == candidate.receipt_id


def _valid_local_dispatch():
    demands = {
        "schema": "nexus.workforce_demands.v1",
        "route_authority": "CapabilityPlanner",
        "demands": [{
            "schema": "nexus.workforce_demand.v1",
            "demand_id": "dispatch-local-1",
            "execution_channel": "local",
            "requested_role": "bounded_code_candidate",
            "minimum_autonomy": "L1",
            "context_class": "nexus_bounded",
            "mutation_intent": True,
            "external_verification_required": True,
            "route_authority": "CapabilityPlanner",
        }],
    }
    admission = evaluate_runtime_workforce_admission(
        demands,
        {"local": {
            "worker_id": "local_coder_7b",
            "provider": "ollama",
            "model": "qwen2.5-coder:7b-instruct",
            "controls": ["focused_tests", "compile", "parser", "small_scope", "reversible_application"],
        }},
        WorkforcePolicyLoader(Path(repo_root) / "nexus/config/model_workforce.yaml"),
    ).to_dict()
    return demands, admission


def test_workforce_dispatch_binding_is_canonical_and_fail_closed():
    demands, admission = _valid_local_dispatch()
    binding = validate_workforce_dispatch_binding({
        "workforce_demands": demands,
        "workforce_admission": admission,
    })
    assert binding is not None
    assert binding["worker_id"] == "local_coder_7b"
    assert binding["provider"] == "ollama"
    assert binding["model"] == "qwen2.5-coder:7b-instruct"
    assert binding["aggregate_binding_hash"] == admission["aggregate_binding_hash"]

    blocked = dict(admission)
    blocked["overall_decision"] = "BLOCK"
    with pytest.raises(RuntimeError, match="WORKFORCE_ADMISSION_BINDING_INVALID"):
        validate_workforce_dispatch_binding({"workforce_demands": demands, "workforce_admission": blocked})

    mismatched = json.loads(json.dumps(admission))
    mismatched["records"][0]["decision"]["resolved_model"] = "tampered-model"
    with pytest.raises(RuntimeError, match="WORKFORCE_ADMISSION_BINDING_INVALID"):
        validate_workforce_dispatch_binding({"workforce_demands": demands, "workforce_admission": mismatched})


def test_build_contract_binds_selected_admission_identity_and_rejects_override(tmp_path):
    demands, admission = _valid_local_dispatch()
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _request(
        tmp_path,
        task_id="admitted-dispatch",
        worker="auto",
        model="qwen2.5-coder:7b-instruct",
        execution_lane="ISOLATED_TARGET",
        workforce_demands=demands,
        workforce_admission=admission,
    )
    contract = service.build_contract(request)
    assert contract.preferred_provider == "ollama"
    assert contract.provider_order == ["ollama"]

    with pytest.raises(RuntimeError, match="WORKFORCE_ADMISSION_FALLBACK_UNADMITTED"):
        service.build_contract({**request, "fallback_worker": "opencode"})

    with pytest.raises(RuntimeError, match="WORKFORCE_ADMISSION_MODEL_MISMATCH"):
        service.build_contract({**request, "model": "tampered-model"})


def test_admitted_agy_worker_registry_execution_persists_identity_and_receipt(tmp_path, monkeypatch):
    task_id = "service-online-agy-1"
    card_path = "tasks/campaign/service-online-agy-1.md"
    card = tmp_path / card_path
    card.parent.mkdir(parents=True)
    card.write_text(f"task_id: `{task_id}`\nAUTO_CHAIN: false\n", encoding="utf-8")
    card_hash = hashlib.sha256(card.read_bytes()).hexdigest()
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT",
        tmp_path,
    )
    internal = build_canonical_planner_admission(
        task_id=task_id,
        task_text="bounded online change",
        allowed_files=("nexus_canary.txt",),
        verifier_command=("python3 -c 'print(\"pass\")'",),
        task_card_identity=VerifiedTaskCardIdentity(
            task_id=task_id,
            task_card_path=card_path,
            canonical_task_card_path=str(card.resolve()),
            task_card_hash=card_hash,
        ),
    )
    demands = internal["workforce_demands"]
    admission = internal["workforce_admission"]
    calls = []

    class FakeAgyAdapter:
        provider = "agy"

        def preflight(self):
            return WorkerPreflight(
                provider="agy", executable="/bin/agy", executable_available=True,
                authorized=True, implementation_status="IMPLEMENTED", ready=True, reason="ready",
            )

        def invoke(self, contract, lease, *, prompt, model=None, **options):
            calls.append((self.provider, model, contract.task_id, lease.target_worktree))
            return WorkerExecutionReceipt(
                provider="agy", task_id=contract.task_id,
                target_worktree=lease.target_worktree, worker_status="COMPLETED",
                outcome=WorkerOutcome.EXECUTION_COMPLETED.value, exit_code=0,
                executable_identity="/bin/agy", argv=("agy", model or ""),
                stdout_sha256="a" * 64, stderr_sha256="b" * 64, wall_time_ms=1,
                process_group_id=None, process_group_killed=False, timed_out=False,
                provider_calls=1, evidence_complete=True, commit_created=False,
                merge_performed=False, push_performed=False,
            )

    adapter = FakeAgyAdapter()
    registry = WorkerRegistry({provider: adapter for provider in SUPPORTED_WORKER_PROVIDERS})
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", worker_registry=registry, auto_reconcile=False, ephemeral=True,
    )
    attempt_id = "a" * 32
    request = _request(
        tmp_path, task_id=task_id, worker="auto",
        model="gemini-3.6-flash-high", execution_lane="ISOLATED_TARGET",
        workforce_demands=demands, workforce_admission=admission,
        planner_output=internal["planner_output"],
        task_card_path=card_path, task_card_hash=card_hash,
        contract_kind=ContractKind.TRACKED_TASK_CARD.value,
        worker_candidate_ingress=True,
        attempt_id=attempt_id,
    )
    request["canonical_dispatch_envelope"] = build_canonical_dispatch_envelope(
        internal["planner_output"],
        internal["binding"],
        task_id=task_id,
        attempt_id=attempt_id,
        task_card_path=card_path,
        task_card_hash=card_hash,
    ).to_dict()
    contract = service.build_contract(request)
    binding = validate_workforce_dispatch_binding(request)
    assert binding is not None
    service._write_state(contract.task_id, {
        "task_id": contract.task_id, "status": "SUBMITTED", "attempt_id": attempt_id,
        "task_card_path": card_path, "task_card_hash": card_hash,
        "contract_kind": ContractKind.TRACKED_TASK_CARD.value,
        "request": request, "workforce_dispatch": binding,
        "canonical_dispatch_envelope": binding["canonical_dispatch_envelope"],
        "workforce_policy_hash": binding["policy_hash"], "workforce_binding_hash": binding["binding_hash"],
        "workforce_aggregate_binding_hash": binding["aggregate_binding_hash"],
        "selected_worker_id": binding["worker_id"], "selected_provider": binding["provider"],
        "selected_model": binding["model"], "provider_order": [binding["provider"]],
        "worker_provider": binding["provider"], "fallback_lineage": [], "attempts": [{"attempt_id": attempt_id}],
        "executions": [], "submitted_at": datetime.now(timezone.utc).isoformat(),
    })

    class FakeManager:
        def __init__(self, root_dir):
            self.root_dir = root_dir

    class FakeController:
        def __init__(self, worktree_manager):
            pass

        def prepare_task(self, contract):
            return TargetWorktreeLease(
                schema="nexus.target_worktree_lease.v1", lease_id="agy-lease",
                task_id=contract.task_id, controller_revision=contract.controller_revision,
                target_base_revision=contract.target_base_revision,
                target_worktree=str(tmp_path / "target"), target_branch="nexus/task/agy",
                initial_head="b" * 40, initial_status_sha256="0" * 64,
                controller_status_sha256="0" * 64, created_from_exact_revision=True,
                commit_created=False, merge_performed=False,
            )

    class FakeVerifier:
        @staticmethod
        def validate_static_contract(contract, target):
            return None

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", FakeManager)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.SelfHostedDevelopmentController", FakeController)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CandidateVerifier", FakeVerifier)

    def update(status, values):
        service._checkpoint(contract.task_id, status, values, attempt_id=attempt_id)
        if status == "WORKER_COMPLETED":
            raise RuntimeError("stop after registry receipt")

    with pytest.raises(RuntimeError, match="stop after registry receipt"):
        service._run_default_resumable(
            contract, request, update, task_id=contract.task_id, attempt_id=attempt_id,
        )

    persisted = service._read_state(contract.task_id)
    assert calls == [("agy", "gemini-3.6-flash-high", contract.task_id, str(tmp_path / "target"))]
    assert persisted["selected_worker_id"] == "agy_flash"
    assert persisted["selected_provider"] == "agy"
    assert persisted["selected_model"] == "gemini-3.6-flash-high"
    assert persisted["task_card_path"] == request["canonical_dispatch_envelope"]["task_card_path"]
    assert persisted["task_card_hash"] == request["canonical_dispatch_envelope"]["task_card_hash"]
    assert persisted["execution"]["provider"] == "agy"
    assert persisted["execution"]["outcome"] == WorkerOutcome.EXECUTION_COMPLETED.value
    assert persisted["fallback_lineage"] == []


def test_tracked_card_mutated_after_submit_fails_before_preflight_or_registry(
    tmp_path,
    monkeypatch,
):
    task_id = "service-card-drift-after-submit"
    attempt_id = "d" * 32
    card_path = f"tasks/campaign/{task_id}.md"
    card = tmp_path / card_path
    card.parent.mkdir(parents=True)
    card.write_text(f"task_id: `{task_id}`\nAUTO_CHAIN: false\n", encoding="utf-8")
    card_hash = hashlib.sha256(card.read_bytes()).hexdigest()
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT",
        tmp_path,
    )
    internal = build_canonical_planner_admission(
        task_id=task_id,
        task_text="bounded online change",
        allowed_files=("nexus_canary.txt",),
        verifier_command=("python3 -c 'print(\"pass\")'",),
        task_card_identity=VerifiedTaskCardIdentity(
            task_id=task_id,
            task_card_path=card_path,
            canonical_task_card_path=str(card.resolve()),
            task_card_hash=card_hash,
        ),
    )
    request = _request(
        tmp_path,
        task_id=task_id,
        worker="auto",
        model="gemini-3.6-flash-high",
        execution_lane="ISOLATED_TARGET",
        workforce_demands=internal["workforce_demands"],
        workforce_admission=internal["workforce_admission"],
        planner_output=internal["planner_output"],
        task_card_path=card_path,
        task_card_hash=card_hash,
        contract_kind=ContractKind.TRACKED_TASK_CARD.value,
        worker_candidate_ingress=True,
        attempt_id=attempt_id,
    )
    request["canonical_dispatch_envelope"] = build_canonical_dispatch_envelope(
        internal["planner_output"],
        internal["binding"],
        task_id=task_id,
        attempt_id=attempt_id,
        task_card_path=card_path,
        task_card_hash=card_hash,
    ).to_dict()
    calls = {"preflight": 0, "invoke": 0}

    class RejectAfterDriftAdapter:
        provider = "agy"

        def preflight(self):
            calls["preflight"] += 1
            raise AssertionError("card drift reached provider preflight")

        def invoke(self, *args, **kwargs):
            calls["invoke"] += 1
            raise AssertionError("card drift reached WorkerRegistry invocation")

    adapter = RejectAfterDriftAdapter()
    registry = WorkerRegistry(
        {provider: adapter for provider in SUPPORTED_WORKER_PROVIDERS}
    )
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        worker_registry=registry,
        auto_reconcile=False,
        ephemeral=True,
    )
    transport = _action_transport(
        request,
        attempt_id=attempt_id,
        action_id="action-card-drift-after-submit",
        idempotency_key="card-drift-after-submit:attempt-1",
    )

    def mutate_after_submit_then_run(owned_task_id, owned_attempt_id):
        submitted = service._read_state(owned_task_id)
        assert submitted is not None
        assert submitted["status"] == "SUBMITTED"
        card.write_text(
            f"task_id: `{task_id}`\nAUTO_CHAIN: false\ndrift: true\n",
            encoding="utf-8",
        )
        service._run_owned_task(owned_task_id, owned_attempt_id)
        return service._read_state(owned_task_id)

    monkeypatch.setattr(service, "_launch_worker", mutate_after_submit_then_run)
    result = service.submit_task(transport)

    assert result["status"] == "FINAL_BLOCK"
    assert "TASK_CARD_BINDING_MISMATCH" in result["error"]
    assert calls == {"preflight": 0, "invoke": 0}


def test_governed_tracked_request_without_dispatch_binding_final_blocks_zero_call(
    tmp_path,
    monkeypatch,
):
    task_id = "service-tracked-dispatch-missing"
    attempt_id = "e" * 32
    card_path = f"tasks/campaign/{task_id}.md"
    card = tmp_path / card_path
    card.parent.mkdir(parents=True)
    card.write_text(f"task_id: `{task_id}`\nAUTO_CHAIN: false\n", encoding="utf-8")
    card_hash = hashlib.sha256(card.read_bytes()).hexdigest()
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT",
        tmp_path,
    )
    calls = {"preflight": 0, "invoke": 0}

    class RejectUnboundAdapter:
        provider = "agy"

        def preflight(self):
            calls["preflight"] += 1
            raise AssertionError("unbound tracked request reached provider preflight")

        def invoke(self, *args, **kwargs):
            calls["invoke"] += 1
            raise AssertionError("unbound tracked request reached WorkerRegistry")

    adapter = RejectUnboundAdapter()
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        worker_registry=WorkerRegistry(
            {provider: adapter for provider in SUPPORTED_WORKER_PROVIDERS}
        ),
        auto_reconcile=False,
        ephemeral=True,
    )
    request = _request(
        tmp_path,
        task_id=task_id,
        worker="agy",
        provider="agy",
        model="caller-selected-model",
        execution_lane="ISOLATED_TARGET",
        task_card_path=card_path,
        task_card_hash=card_hash,
        contract_kind=ContractKind.TRACKED_TASK_CARD.value,
        worker_candidate_ingress=True,
        attempt_id=attempt_id,
    )
    transport = _action_transport(
        request,
        attempt_id=attempt_id,
        action_id="action-tracked-dispatch-missing",
        idempotency_key="tracked-dispatch-missing:attempt-1",
    )

    def run_inline(owned_task_id, owned_attempt_id):
        service._run_owned_task(owned_task_id, owned_attempt_id)
        return service._read_state(owned_task_id)

    monkeypatch.setattr(service, "_launch_worker", run_inline)
    result = service.submit_task(transport)

    assert result["status"] == "FINAL_BLOCK"
    assert "WORKFORCE_ADMISSION_BINDING_MISSING" in result["error"]
    assert result["selected_worker_id"] is None
    assert result["selected_provider"] is None
    assert result["selected_model"] is None
    assert calls == {"preflight": 0, "invoke": 0}


@pytest.mark.parametrize(
    ("mutate_card", "expected_error"),
    [
        (True, "TASK_CARD_BINDING_MISMATCH"),
        (False, "WORKFORCE_DISPATCH_ACTIVE_PROVIDER_DRIFT"),
    ],
    ids=("card-drift", "no-card-drift-unadmitted-fallback"),
)
def test_unadmitted_fallback_blocks_before_provider_side_work(
    tmp_path,
    monkeypatch,
    mutate_card,
    expected_error,
):
    task_id = "service-card-drift-before-escalation"
    attempt_id = "f" * 32
    card_path = f"tasks/campaign/{task_id}.md"
    card = tmp_path / card_path
    card.parent.mkdir(parents=True)
    card.write_text(f"task_id: `{task_id}`\nAUTO_CHAIN: false\n", encoding="utf-8")
    card_hash = hashlib.sha256(card.read_bytes()).hexdigest()
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT",
        tmp_path,
    )
    internal = build_canonical_planner_admission(
        task_id=task_id,
        task_text="bounded online change",
        allowed_files=("nexus_canary.txt",),
        verifier_command=("python3 -c 'print(\"pass\")'",),
        task_card_identity=VerifiedTaskCardIdentity(
            task_id=task_id,
            task_card_path=card_path,
            canonical_task_card_path=str(card.resolve()),
            task_card_hash=card_hash,
        ),
    )
    request = _request(
        tmp_path,
        task_id=task_id,
        worker="auto",
        model="gemini-3.6-flash-high",
        execution_lane="ISOLATED_TARGET",
        workforce_demands=internal["workforce_demands"],
        workforce_admission=internal["workforce_admission"],
        planner_output=internal["planner_output"],
        task_card_path=card_path,
        task_card_hash=card_hash,
        contract_kind=ContractKind.TRACKED_TASK_CARD.value,
        worker_candidate_ingress=True,
        attempt_id=attempt_id,
    )
    request["canonical_dispatch_envelope"] = build_canonical_dispatch_envelope(
        internal["planner_output"],
        internal["binding"],
        task_id=task_id,
        attempt_id=attempt_id,
        task_card_path=card_path,
        task_card_hash=card_hash,
    ).to_dict()
    calls = {
        "admitted": {"preflight": 0, "provider_calls": 0},
        "fallback": {"preflight": 0, "provider_calls": 0},
        "replacement": 0,
    }

    class EscalationAdapter:
        def __init__(self, provider):
            self.provider = provider

        def preflight(self):
            key = "admitted" if self.provider == "agy" else "fallback"
            calls[key]["preflight"] += 1
            return WorkerPreflight(
                provider=self.provider,
                executable=f"/bin/{self.provider}",
                executable_available=True,
                authorized=True,
                implementation_status="IMPLEMENTED",
                ready=True,
                reason="ready",
            )

        def invoke(self, contract, lease, *, prompt, model=None, **options):
            key = "admitted" if self.provider == "agy" else "fallback"
            calls[key]["provider_calls"] += 1
            assert self.provider == "agy"
            if mutate_card:
                card.write_text(
                    f"task_id: `{task_id}`\nAUTO_CHAIN: false\ndrift: true\n",
                    encoding="utf-8",
                )
            return WorkerExecutionReceipt(
                provider=self.provider,
                task_id=contract.task_id,
                target_worktree=lease.target_worktree,
                worker_status="TIMED_OUT",
                outcome=WorkerOutcome.INCOMPLETE.value,
                exit_code=124,
                executable_identity=f"/bin/{self.provider}",
                argv=(self.provider, model or ""),
                stdout_sha256="a" * 64,
                stderr_sha256="b" * 64,
                wall_time_ms=1,
                process_group_id=None,
                process_group_killed=True,
                timed_out=True,
                provider_calls=1,
                evidence_complete=True,
                commit_created=False,
                merge_performed=False,
                push_performed=False,
                failure_reason="provider timeout",
            )

    registry = WorkerRegistry(
        {
            provider: EscalationAdapter(provider)
            for provider in SUPPORTED_WORKER_PROVIDERS
        }
    )
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        worker_registry=registry,
        auto_reconcile=False,
        ephemeral=True,
    )
    real_build_contract = service.build_contract

    def build_escalating_contract(bound_request):
        contract = real_build_contract(bound_request)
        return contract.model_copy(
            update={
                "fallback_provider": "grok",
                "provider_order": ["agy", "grok"],
                "maximum_provider_calls": 2,
            }
        )

    monkeypatch.setattr(service, "build_contract", build_escalating_contract)

    class FakeManager:
        def __init__(self, root_dir):
            self.root_dir = root_dir

        def verify_controller_unchanged(self, contract, **kwargs):
            return None

        def _run_git(self, args, *, cwd):
            return "b" * 40

        def cleanup(self, task_id, *, force=False):
            calls["replacement"] += 1
            return None

        def cleanup_terminal_target(self, contract, lease, **kwargs):
            return SimpleNamespace(
                decision="REMOVED",
                blocker=None,
                performed=True,
                eligible=True,
            )

    class FakeController:
        def __init__(self, worktree_manager):
            self.worktree_manager = worktree_manager

        def prepare_task(self, contract):
            return TargetWorktreeLease(
                schema="nexus.target_worktree_lease.v1",
                lease_id="escalation-lease",
                task_id=contract.task_id,
                controller_revision=contract.controller_revision,
                target_base_revision=contract.target_base_revision,
                target_worktree=str(tmp_path / "target"),
                target_branch="nexus/task/escalation-drift",
                initial_head="b" * 40,
                initial_status_sha256="0" * 64,
                controller_status_sha256="0" * 64,
                created_from_exact_revision=True,
                commit_created=False,
                merge_performed=False,
            )

    class FakeVerifier:
        @staticmethod
        def validate_static_contract(contract, target):
            return None

    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.WorktreeManager",
        FakeManager,
    )
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.SelfHostedDevelopmentController",
        FakeController,
    )
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.CandidateVerifier",
        FakeVerifier,
    )
    transport = _action_transport(
        request,
        attempt_id=attempt_id,
        action_id="action-card-drift-before-escalation",
        idempotency_key="card-drift-before-escalation:attempt-1",
    )

    def run_inline(owned_task_id, owned_attempt_id):
        service._run_owned_task(owned_task_id, owned_attempt_id)
        return service._read_state(owned_task_id)

    monkeypatch.setattr(service, "_launch_worker", run_inline)
    result = service.submit_task(transport)

    assert result["status"] == "FINAL_BLOCK"
    assert expected_error in result["error"]
    assert calls["admitted"] == {"preflight": 2, "provider_calls": 1}
    assert calls["fallback"] == {"preflight": 0, "provider_calls": 0}
    assert calls["replacement"] == 0


def test_checkpoint_telemetry_aggregates_attempts_and_keeps_cost_unmeasured(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    now = datetime.now(timezone.utc).isoformat()
    service._write_state("telemetry-task", {
        "task_id": "telemetry-task",
        "status": "SUBMITTED",
        "submitted_at": now,
        "worker_started_at": now,
        "executions": [
            {"provider_calls": 2, "provider_attempt_count": 2, "wall_time_ms": 7},
            {"provider_calls": 1, "provider_attempt_count": 1, "wall_time_ms": 3},
        ],
    })
    service._checkpoint("telemetry-task", "WORKER_COMPLETED")
    telemetry = service._read_state("telemetry-task")["telemetry"]
    assert telemetry["provider_calls"] == 3
    assert telemetry["provider_attempts"] == 3
    assert telemetry["tokens"] is None
    assert telemetry["cost"] is None
    assert telemetry["token_status"] == "unmeasured"
    assert telemetry["cost_status"] == "unmeasured"
    assert telemetry["savings_claim_allowed"] is False


def _closure_context(
    task_id: str,
    candidate: str,
    attempt_id: str = "attempt-1",
    *,
    candidate_tree_sha: str = "d" * 40,
    candidate_state_hash: str = "e" * 64,
    candidate_receipt_hash: str = "f" * 64,
):
    acceptance = ExternalAcceptanceReceipt(
        schema="nexus.external_acceptance_receipt.v1", task_id=task_id,
        attempt_id=attempt_id, candidate_commit=candidate, receipt_hash="b" * 64,
        reviewer_id="reviewer-1", passed=True, verifier_artifact="artifact-1",
    )
    authorization = IntegrationAuthorizationEnvelope(
        schema="nexus.integration_authorization.v1", task_id=task_id,
        campaign_id="campaign", attempt_id=attempt_id, task_card_hash="c" * 64,
        candidate_commit=candidate, candidate_tree_sha=candidate_tree_sha,
        candidate_state_hash=candidate_state_hash, candidate_receipt_hash=candidate_receipt_hash,
        acceptance_receipt_hash=acceptance.receipt_hash, reviewer_id="reviewer-1",
        verifier_artifact_hash="1" * 64, canonical_root="/tmp/repo",
        canonical_branch="nexus/integration/main", expected_canonical_head="a" * 40,
        canonical_dirty_baseline="2" * 64, integration_plan_hash="3" * 64,
        strategy="EPHEMERAL_WORKTREE_MERGE_THEN_APPLY", verification_commands_hash="4" * 64,
        post_apply_commands_hash="5" * 64, cleanup_target_id="target-1",
        cleanup_target_path="/tmp/target", durable_ref=f"refs/nexus-candidate/{task_id}",
        rollback="retain target", cleanup_requested=True,
        action_set=("ACCEPT_DISPOSITION", "INTEGRATION_STAGING", "APPLY_VERIFIED_INTEGRATION", "POST_INTEGRATION_VERIFY", "CLEANUP_OWNED_TARGET"),
        issued_at="2026-08-02T00:00:00+00:00",
    )
    grant = {
        "schema": "nexus.approval.v2", "approval_id": f"approval-{task_id}",
        "approval_scope": "ALLOW_ACTION_ONCE", "contract_kind": "TRACKED_TASK_CARD",
        "contract_hash": "c" * 64, "task_card_hash": "c" * 64,
    }
    return {
        "approval_context": grant,
        "external_acceptance": acceptance.to_dict(),
        "integration_authorization": authorization.to_dict(),
    }


def _git(cwd: Path, *args: str) -> str:
    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", *args],
        cwd=cwd, check=True, capture_output=True, text=True, env=env,
    ).stdout.strip()


def _init_repo(path: Path) -> None:
    """Initialize a git repo with hooks disabled, regardless of user global config."""
    _git(path, "init", "-b", "main")
    _git(path, "config", "core.hooksPath", "/dev/null")


def _real_request(tmp_path: Path, task_id: str = "real-reconcile"):
    controller = tmp_path / "controller"
    controller.mkdir(exist_ok=True)
    git_dir = controller / ".git"
    if not git_dir.exists():
        _init_repo(controller)
        _git(controller, "config", "user.name", "Lifecycle Test")
        _git(controller, "config", "user.email", "lifecycle@example.test")
        (controller / "README").write_text("base\n")
        _git(controller, "add", "README")
        _git(controller, "commit", "-m", "base")
    head = _git(controller, "rev-parse", "HEAD")
    target_root = tmp_path / "targets"
    return _request(
        tmp_path, task_id=task_id, controller_revision=head,
        target_base_revision=head, controller_repo_root=str(controller),
        target_repo_root=str(target_root / task_id), target_worktree_root=str(target_root),
    )


def _wait_for_status(service: SelfHostedTaskService, task_id: str, status: str):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        current = service.get_task(task_id)
        if current and current["status"] == status:
            return current
        time.sleep(0.01)
    return service.get_task(task_id)


def test_what_why_are_mapped_to_architect_contract(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state")

    contract = service.build_contract(_request(tmp_path))

    assert contract.schema == "nexus.self_hosted_task_contract.v2"
    assert contract.objective == "Add one bounded canary test"
    assert contract.goal.what == contract.objective
    assert contract.goal.why == "Prove the MCP request becomes a governed task"


def test_task_card_relative_path_resolves_from_canonical_root(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state")
    request = _request(
        tmp_path,
        task_id="agy-gateway-executable-authority-convergence",
        task_card_path="tasks/agy-account-pool-runtime/02-agy-gateway-executable-authority-convergence.md",
    )
    contract = service.build_contract(request)

    validate_task_card_binding(contract, request)
    assert contract.preferred_provider == "codex"
    assert contract.human_approval_required is True


def test_production_bound_ephemeral_receipt_cannot_be_approved(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "ephemeral-production-bound"
    service._write_state(task_id, {
        "task_id": task_id,
        "status": "PENDING_HUMAN_APPROVAL",
        "promotion_status": "PENDING_HUMAN_APPROVAL",
        "request": {"task_card_required": True, "lifecycle_identity_required": True},
        "promotion_packet": {
            "candidate_commit_sha": "c" * 40,
            "candidate_tree_sha": "d" * 40,
            "candidate_state_hash": "e" * 64,
            "verified_receipt_hash": "f" * 64,
        },
    })

    with pytest.raises(RuntimeError, match="EPHEMERAL_PROMOTION_FORBIDDEN"):
        service.approve_promotion(
            task_id,
            candidate_commit_sha="c" * 40,
            candidate_tree_sha="d" * 40,
            candidate_state_hash="e" * 64,
            verified_receipt_hash="f" * 64,
        )


def test_status_snapshot_does_not_reconcile_or_expand_details(tmp_path, monkeypatch):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    task_id = "snapshot-only"
    service._write_state(
        task_id,
        {
            "task_id": task_id,
            "status": "FINAL_BLOCK",
            "promotion_status": "NOT_CREATED",
            "attempts": [{"attempt_id": "a"}],
        },
    )
    monkeypatch.setattr(
        service, "reconcile_task", lambda *_: (_ for _ in ()).throw(AssertionError("reconciled"))
    )

    compact = service.get_task_snapshot(task_id)
    detailed = service.get_task_snapshot(task_id, include_details=True)

    assert compact["schema"] == "nexus.self_hosted_task_status.v1"
    assert compact["task_action"]["next_action"] == "inspect_receipt_and_candidate"
    assert "attempts" not in compact
    assert detailed["attempts"] == [{"attempt_id": "a"}]
    assert compact["approval_requirements"] == detailed["approval_requirements"]
    assert compact["approval_requirements"]["status"] == "NOT_REQUIRED"
    assert compact["approval_requirements"]["reasons"] == []


def _approval_requirement_state(*, required=True):
    return {
        "task_id": "approval-projection",
        "attempt_id": "attempt-1",
        "status": "CANDIDATE_COMMITTED",
        "promotion_status": "PENDING_HUMAN_APPROVAL",
        "promotion_packet": {
            "candidate_commit_sha": "c" * 40,
            "candidate_tree_sha": "d" * 40,
            "authority_change_required": required,
            "authority_findings_sha256": "a" * 64,
        },
        "candidate": {
            "commit_sha": "c" * 40,
            "tree_sha": "d" * 40,
        },
        "verified_receipt": {
            "candidate_commit_sha": "c" * 40,
            "candidate_tree_sha": "d" * 40,
            "authority_change_required": required,
            "authority_findings_sha256": "a" * 64,
        },
    }


def test_snapshot_projects_complete_architecture_approval_requirements(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    service._write_state("approval-projection", _approval_requirement_state())

    requirements = service.get_task_snapshot("approval-projection")["approval_requirements"]

    assert requirements["status"] == "APPROVABLE"
    assert requirements["completeness"] == "COMPLETE"
    assert requirements["approvability"] == "APPROVABLE"
    assert requirements["reasons"] == []
    assert requirements["binding"] == {
        "bound_task_id": "approval-projection",
        "bound_attempt_id": "attempt-1",
        "candidate_commit_sha": "c" * 40,
        "candidate_tree_sha": "d" * 40,
        "authority_findings_sha256": "a" * 64,
    }
    assert "approval_id" not in requirements


def test_compact_and_detailed_snapshots_share_pure_approval_projection(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    state = _approval_requirement_state()
    state["attempts"] = [{"attempt_id": "attempt-1"}]
    service._write_state("approval-projection", state)
    state_path = service._state_path("approval-projection")
    durable_before = state_path.read_bytes()

    compact = service.get_task_snapshot("approval-projection")
    detailed = service.get_task_snapshot("approval-projection", include_details=True)

    assert compact["approval_requirements"] == detailed["approval_requirements"]
    assert "attempts" not in compact
    assert detailed["attempts"] == [{"attempt_id": "attempt-1"}]
    assert state_path.read_bytes() == durable_before
    assert "approval_requirements" not in json.loads(durable_before)


def test_malformed_approval_source_containers_fail_closed_without_mutation(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    state = _approval_requirement_state(required=False)
    state["promotion_packet"] = []
    state["verified_receipt"] = []
    expected_reasons = [
        "malformed_source:promotion_packet:expected_mapping",
        "malformed_source:verified_receipt:expected_mapping",
    ]
    direct = service._approval_requirements(state)
    service.state_dir.mkdir(parents=True)
    state_path = service._state_path("approval-projection")
    state_path.write_text(json.dumps(state), encoding="utf-8")
    durable_before = state_path.read_bytes()

    compact = service.get_task_snapshot("approval-projection")
    detailed = service.get_task_snapshot("approval-projection", include_details=True)

    assert direct["status"] == "NOT_APPROVABLE"
    assert direct["reasons"] == expected_reasons
    assert compact["approval_requirements"] == detailed["approval_requirements"]
    assert compact["approval_requirements"]["required"] is False
    assert compact["approval_requirements"]["status"] == "NOT_APPROVABLE"
    assert compact["approval_requirements"]["reasons"] == expected_reasons
    assert state_path.read_bytes() == durable_before


@pytest.mark.parametrize(
    "empty_sources",
    [
        ("promotion_packet",),
        ("verified_receipt",),
        ("promotion_packet", "verified_receipt"),
    ],
)
def test_empty_approval_sources_fail_closed_without_mutation(tmp_path, empty_sources):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    state = _approval_requirement_state(required=False)
    for source_name in empty_sources:
        state[source_name] = {}
    expected_reasons = sorted(
        f"malformed_source:{name}:empty_or_missing_contract_fields" for name in empty_sources
    )
    direct = service._approval_requirements(state)
    service.state_dir.mkdir(parents=True)
    state_path = service._state_path("approval-projection")
    state_path.write_text(json.dumps(state), encoding="utf-8")
    durable_before = state_path.read_bytes()

    compact = service.get_task_snapshot("approval-projection")
    detailed = service.get_task_snapshot("approval-projection", include_details=True)

    assert direct["status"] == "NOT_APPROVABLE"
    assert direct["reasons"] == expected_reasons
    assert compact["approval_requirements"] == detailed["approval_requirements"]
    assert compact["approval_requirements"]["required"] is False
    assert compact["approval_requirements"]["status"] == "NOT_APPROVABLE"
    assert compact["approval_requirements"]["reasons"] == expected_reasons
    assert state_path.read_bytes() == durable_before


def test_none_approval_sources_remain_non_required_without_mutation(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    state = _approval_requirement_state(required=False)
    state["promotion_packet"] = None
    state["verified_receipt"] = None
    service.state_dir.mkdir(parents=True)
    state_path = service._state_path("approval-projection")
    state_path.write_text(json.dumps(state), encoding="utf-8")
    durable_before = state_path.read_bytes()

    compact = service.get_task_snapshot("approval-projection")
    detailed = service.get_task_snapshot("approval-projection", include_details=True)

    assert compact["approval_requirements"] == detailed["approval_requirements"]
    assert compact["approval_requirements"]["status"] == "NOT_REQUIRED"
    assert compact["approval_requirements"]["reasons"] == []
    assert state_path.read_bytes() == durable_before


@pytest.mark.parametrize(
    ("change", "expected_reason"),
    [
        (None, "missing:bound_attempt_id"),
        (
            lambda state: state["promotion_packet"].update(candidate_commit_sha="bad"),
            "invalid_format:promotion_packet.candidate_commit_sha",
        ),
        (
            lambda state: state["verified_receipt"].update(authority_findings_sha256="bad"),
            "invalid_format:verified_receipt.authority_findings_sha256",
        ),
    ],
)
def test_snapshot_missing_or_malformed_approval_inputs_fail_closed(
    tmp_path, change, expected_reason
):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    state = _approval_requirement_state()
    if change is None:
        state.pop("attempt_id")
    else:
        change(state)
    service._write_state("approval-projection", state)

    requirements = service.get_task_snapshot("approval-projection")["approval_requirements"]

    assert requirements["status"] == "NOT_APPROVABLE"
    assert requirements["approvability"] == "NOT_APPROVABLE"
    assert expected_reason in requirements["reasons"]


@pytest.mark.parametrize("invalid_value", ["false", 1, [], {}])
@pytest.mark.parametrize("source_name", ["promotion_packet", "verified_receipt"])
def test_snapshot_rejects_non_bool_authority_requirement(tmp_path, invalid_value, source_name):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    state = _approval_requirement_state(required=False)
    state[source_name]["authority_change_required"] = invalid_value
    service._write_state("approval-projection", state)

    requirements = service.get_task_snapshot("approval-projection")["approval_requirements"]

    assert requirements["required"] is False
    assert requirements["status"] == "NOT_APPROVABLE"
    assert requirements["reasons"] == [f"invalid_type:{source_name}.authority_change_required"]


@pytest.mark.parametrize(
    ("change", "expected_reason"),
    [
        (
            lambda state: state.update(attempt_id=7),
            "invalid_type:task.attempt_id",
        ),
        (
            lambda state: state["promotion_packet"].update(candidate_commit_sha=7),
            "invalid_type:promotion_packet.candidate_commit_sha",
        ),
        (
            lambda state: state["candidate"].update(tree_sha=[]),
            "invalid_type:candidate.tree_sha",
        ),
        (
            lambda state: state["verified_receipt"].update(authority_findings_sha256={}),
            "invalid_type:verified_receipt.authority_findings_sha256",
        ),
    ],
)
def test_snapshot_rejects_non_string_binding_fields(tmp_path, change, expected_reason):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    state = _approval_requirement_state()
    change(state)
    service._write_state("approval-projection", state)

    requirements = service.get_task_snapshot("approval-projection")["approval_requirements"]

    assert requirements["status"] == "NOT_APPROVABLE"
    assert expected_reason in requirements["reasons"]


def test_snapshot_rejects_non_string_durable_task_id_without_coercion(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    state = _approval_requirement_state()
    state["task_id"] = {"not": "a string"}
    service._write_state("approval-projection", state)

    compact = service.get_task_snapshot("approval-projection")
    detailed = service.get_task_snapshot("approval-projection", include_details=True)

    assert compact["approval_requirements"] == detailed["approval_requirements"]
    assert compact["approval_requirements"]["status"] == "NOT_APPROVABLE"
    assert compact["approval_requirements"]["reasons"] == ["invalid_state:STATE_FIELD_INVALID"]


def test_snapshot_mismatch_and_stale_approval_inputs_fail_closed(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    mismatch = _approval_requirement_state()
    mismatch["candidate"]["tree_sha"] = "e" * 40
    service._write_state("approval-projection", mismatch)
    result = service.get_task_snapshot("approval-projection")["approval_requirements"]
    assert result["status"] == "NOT_APPROVABLE"
    assert "candidate_tree_sha" in result["mismatches"]
    assert "mismatch:candidate_tree_sha" in result["reasons"]

    stale = _approval_requirement_state()
    stale["promotion_status"] = "APPROVED"
    service._write_state("approval-projection", stale)
    result = service.get_task_snapshot("approval-projection")["approval_requirements"]
    assert result["stale"] is True
    assert result["status"] == "NOT_APPROVABLE"
    assert "stale:approval_requirements" in result["reasons"]


def test_snapshot_non_required_approval_is_deterministic(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    state = _approval_requirement_state(required=False)
    state["approved_binding"] = {"architecture_approval": {"schema": "stale"}}
    service._write_state("approval-projection", state)

    requirements = service.get_task_snapshot("approval-projection")["approval_requirements"]

    assert requirements["required"] is False
    assert requirements["status"] == "NOT_REQUIRED"
    assert requirements["completeness"] == "NOT_REQUIRED"
    assert requirements["approvability"] == "NOT_REQUIRED"
    assert requirements["stale"] is True


@pytest.mark.parametrize(
    ("payload", "blocker_code"),
    [
        ("null\n", "STATE_NOT_OBJECT"),
        ("[]\n", "STATE_NOT_OBJECT"),
        ("{not-json\n", "STATE_JSON_INVALID"),
        (
            json.dumps({
                "task_id": "malformed-status",
                "status": "FINAL_BLOCK",
                "attempts": None,
            }),
            "STATE_FIELD_INVALID",
        ),
    ],
)
def test_status_surfaces_fail_closed_on_malformed_state_without_mutation(
    tmp_path,
    payload,
    blocker_code,
):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        auto_reconcile=False,
        ephemeral=True,
    )
    service.state_dir.mkdir(parents=True)
    state_path = service.state_dir / "malformed-status.json"
    state_path.write_text(payload, encoding="utf-8")
    before = state_path.read_bytes()

    snapshot = service.get_task_snapshot("malformed-status", include_details=True)
    fetched = service.get_task("malformed-status")
    waited = service.wait_task("malformed-status", timeout_seconds=0)
    actionable = service.list_actionable_tasks(include_details=True)
    lifecycle = service.lifecycle_status()
    retry = service.retry_task("malformed-status")

    for status in (snapshot, fetched, waited):
        assert status["status"] == "BLOCKED_INVALID_STATE"
        assert status["state_valid"] is False
        assert status["blocker"]["code"] == blocker_code
        assert status["retry_authorized"] is False
        assert status["task_action"]["next_action"] == "inspect_lifecycle_state"
        assert status["task_action"]["recommended_tool"] is None
    assert actionable["actionable_count"] == 1
    assert actionable["tasks"][0]["status"] == "BLOCKED_INVALID_STATE"
    assert lifecycle["invalid_states"] == 1
    assert lifecycle["active_tasks"] == 0
    assert lifecycle["blockers"][0]["code"] == blocker_code
    assert retry["retry"]["decision"] == "BLOCKED_INVALID_STATE"
    assert retry["retry"]["blocker"] == blocker_code
    assert state_path.read_bytes() == before
    assert not service._lock_path().exists()


@pytest.mark.parametrize(
    ("payload", "blocker_code"),
    [
        ("null\n", "STATE_NOT_OBJECT"),
        ("{not-json\n", "STATE_JSON_INVALID"),
    ],
)
@pytest.mark.parametrize("entrypoint", ["submit", "direct"])
def test_submission_scan_blocks_invalid_durable_state_without_mutation(
    tmp_path,
    payload,
    blocker_code,
    entrypoint,
):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        auto_reconcile=False,
        ephemeral=True,
    )
    service.state_dir.mkdir(parents=True)
    corrupt_path = service.state_dir / "corrupt-state.json"
    corrupt_path.write_text(payload, encoding="utf-8")
    before = corrupt_path.read_bytes()
    request = _request(
        tmp_path,
        task_id="new-submission",
        execution_lane="DIRECT_CANONICAL",
        primary_agent=True,
        worker="primary",
    )

    with pytest.raises(
        RuntimeError,
        match=rf"INVALID_DURABLE_STATE_BLOCKS_SUBMISSION:corrupt-state:{blocker_code}",
    ):
        if entrypoint == "submit":
            service.submit_task(request)
        else:
            service._submit_direct_canonical(request, "new-submission")

    assert corrupt_path.read_bytes() == before
    assert sorted(path.name for path in service.state_dir.glob("*.json")) == [
        "corrupt-state.json"
    ]
    assert not service._lock_path().exists()


def test_state_root_inventory_classifies_nested_receipts_and_conflicts(tmp_path, monkeypatch):
    canonical = tmp_path / "canonical-state"
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", str(canonical))
    service = SelfHostedTaskService(state_dir=canonical, auto_reconcile=False)
    canonical.mkdir()
    (canonical / "task-a.json").write_text(json.dumps({"task_id": "task-a", "status": "FINAL_BLOCK"}))
    nested = canonical / "rehearsal-v1"
    nested.mkdir()
    (nested / "task-a.json").write_text(json.dumps({"task_id": "task-a", "status": "PENDING_HUMAN_APPROVAL"}))

    inventory = service.state_root_inventory()

    assert inventory["authority_conflict"] is False
    assert inventory["conflict_task_ids"] == []
    assert inventory["evidence_duplicate_task_ids"] == ["task-a"]
    assert {entry["authority"] for entry in inventory["entries"]} == {
        "CANONICAL_AUTHORITY", "REHEARSAL_EVIDENCE",
    }
    assert len(inventory["inventory_sha256"]) == 64


def test_custom_runner_rejected_for_canonical_non_ephemeral_state(tmp_path, monkeypatch):
    canonical = Path("/nexus-canonical-state-test")
    calls = []

    def custom_runner(*args):
        calls.append(args)
        return {"promotion_status": "PENDING_HUMAN_APPROVAL"}

    monkeypatch.setattr(
        SelfHostedTaskService,
        "canonical_state_dir",
        staticmethod(lambda: canonical),
    )

    def initialize_and_submit():
        service = SelfHostedTaskService(
            state_dir=canonical,
            runner=custom_runner,
            auto_reconcile=False,
        )
        return service.submit_task(
            _request(
                tmp_path,
                task_id="forbidden-production-custom-runner",
                execution_lane="ISOLATED_TARGET",
            )
        )

    with pytest.raises(RuntimeError, match="^CUSTOM_RUNNER_REQUIRES_EPHEMERAL_STATE$"):
        initialize_and_submit()

    assert calls == []


def test_explicit_ephemeral_custom_runner_is_test_only_and_cannot_claim(tmp_path):
    calls = []

    def custom_runner(contract, request, update):
        calls.append(contract.task_id)
        update(
            "WORKER_COMPLETED",
            {
                "execution": {"provider": "forged-provider"},
                "workforce_dispatch": {"overall_decision": "ALLOW"},
                "verified_receipt": {"verified": True},
                "provider_receipt_authoritative": True,
                "workforce_admission_authoritative": True,
                "public_claim_allowed": True,
                "production_ready": True,
            },
        )
        return {
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "candidate_commit_created": True,
            "provider_receipt_authoritative": True,
            "workforce_admission_authoritative": True,
            "public_claim_allowed": True,
            "production_ready": True,
        }

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        runner=custom_runner,
        auto_reconcile=False,
        ephemeral=True,
    )
    request = _request(
        tmp_path,
        task_id="ephemeral-custom-runner-boundary",
        execution_lane="ISOLATED_TARGET",
    )

    service.submit_task(request)
    state = _wait_for_status(
        service,
        request["task_id"],
        "PENDING_HUMAN_APPROVAL",
    )
    receipt = service.get_receipt(request["task_id"])
    packet = service.get_promotion_packet(request["task_id"])

    assert calls == [request["task_id"]]
    assert state["execution_authority"] == "EPHEMERAL_TEST_RUNNER"
    assert state["provider_receipt_authoritative"] is False
    assert state["workforce_admission_authoritative"] is False
    assert state["public_claim_allowed"] is False
    assert state["production_ready"] is False
    assert state["promotion_eligible"] is False
    assert state.get("workforce_dispatch") is None
    assert state.get("verified_receipt") is None
    assert receipt["execution_authority"] == "EPHEMERAL_TEST_RUNNER"
    assert receipt["provider_receipt_authoritative"] is False
    assert receipt["workforce_admission_authoritative"] is False
    assert packet["public_claim_allowed"] is False
    assert packet["production_ready"] is False

    with pytest.raises(RuntimeError, match="^CUSTOM_RUNNER_PRODUCTION_CLAIM_FORBIDDEN$"):
        service.approve_promotion(
            request["task_id"],
            candidate_commit_sha="c" * 40,
            candidate_tree_sha="d" * 40,
            candidate_state_hash="e" * 64,
            verified_receipt_hash="f" * 64,
        )


def test_submit_persists_idempotent_task_state(tmp_path):
    calls = []

    def fake_runner(contract, request, update):
        calls.append(contract.task_id)
        update("CANDIDATE_COMMITTED", {"candidate_commit_sha": "c" * 40})
        return {
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "candidate_commit_created": True,
        }

    service = SelfHostedTaskService(state_dir=tmp_path / "state", runner=fake_runner)
    request = _request(tmp_path)

    first = service.submit_task(request)
    assert first["status"] in {"SUBMITTED", "CANDIDATE_COMMITTED"}
    _wait_for_status(service, request["task_id"], "CANDIDATE_COMMITTED")
    second = service.submit_task(request)

    assert first["task_id"] == "mcp-task-001"
    assert first["status"] == "SUBMITTED"
    assert second["candidate_commit_sha"] == "c" * 40
    assert calls == ["mcp-task-001"]
    persisted = json.loads((tmp_path / "state" / "mcp-task-001.json").read_text())
    assert persisted == second


def test_submitted_at_matches_initial_submitted_history_entry(tmp_path):
    release = __import__("threading").Event()

    def fake_runner(contract, request, update):
        release.wait(2)
        return {"promotion_status": "PENDING_HUMAN_APPROVAL", "candidate_commit_created": True}

    service = SelfHostedTaskService(state_dir=tmp_path / "state", runner=fake_runner)
    request = _request(tmp_path, task_id="submitted-at-initial")

    submitted = service.submit_task(request)

    assert submitted["status"] == "SUBMITTED"
    assert submitted["submitted_at"] == submitted["status_history"][0]["at"]
    assert submitted["status_history"][0]["status"] == "SUBMITTED"
    release.set()
    assert _wait_for_status(service, request["task_id"], "PENDING_HUMAN_APPROVAL")["status"] == "PENDING_HUMAN_APPROVAL"


def test_submitted_at_is_immutable_after_background_completion_and_in_receipt(tmp_path):
    release = __import__("threading").Event()

    def fake_runner(contract, request, update):
        release.wait(2)
        update("WORKER_COMPLETED", {"execution": {"provider": "codex"}})
        update("VERIFIED", {"submitted_at": "2099-01-01T00:00:00+00:00"})
        return {"promotion_status": "PENDING_HUMAN_APPROVAL", "candidate_commit_created": True}

    service = SelfHostedTaskService(state_dir=tmp_path / "state", runner=fake_runner)
    request = _request(tmp_path, task_id="submitted-at-completion")
    submitted = service.submit_task(request)
    submitted_at = submitted["submitted_at"]

    release.set()
    completed = _wait_for_status(service, request["task_id"], "PENDING_HUMAN_APPROVAL")
    receipt = service.get_receipt(request["task_id"])

    assert completed["submitted_at"] == submitted_at
    assert completed["status_history"][0]["at"] == submitted_at
    assert receipt["submitted_at"] == submitted_at


def test_submitted_at_is_stable_across_idempotent_resubmission(tmp_path):
    calls = []

    def fake_runner(contract, request, update):
        calls.append(contract.task_id)
        return {"promotion_status": "PENDING_HUMAN_APPROVAL", "candidate_commit_created": True}

    service = SelfHostedTaskService(state_dir=tmp_path / "state", runner=fake_runner)
    request = _request(tmp_path, task_id="submitted-at-idempotent")

    first = service.submit_task(request)
    completed = _wait_for_status(service, request["task_id"], "PENDING_HUMAN_APPROVAL")
    second = service.submit_task(request)

    assert first["submitted_at"] == first["status_history"][0]["at"]
    assert completed["submitted_at"] == first["submitted_at"]
    assert second["submitted_at"] == first["submitted_at"]
    assert calls == ["submitted-at-idempotent"]



def test_submit_returns_before_background_runner_finishes(tmp_path):
    started = __import__("threading").Event()
    release = __import__("threading").Event()

    def fake_runner(contract, request, update):
        started.set()
        release.wait(2)
        update("WORKER_COMPLETED", {"execution": {"provider": "codex"}})
        return {"promotion_status": "PENDING_HUMAN_APPROVAL", "candidate_commit_created": True}

    service = SelfHostedTaskService(state_dir=tmp_path / "state", runner=fake_runner)
    request = _request(tmp_path, task_id="async-task-001")
    submitted = service.submit_task(request)

    assert submitted["status"] == "SUBMITTED"
    assert started.wait(1)
    running = service.get_task(request["task_id"])
    assert running["status"] in {"SUBMITTED", "WORKER_COMPLETED", "CANDIDATE_COMMITTED"}
    assert running["attempt_id"]
    assert running["worker_pid"]
    assert running["heartbeat_at"]
    release.set()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and service.get_task(request["task_id"])["status"] != "PENDING_HUMAN_APPROVAL":
        time.sleep(0.01)
    assert service.get_task(request["task_id"])["status"] == "PENDING_HUMAN_APPROVAL"


def test_reconcile_fails_closed_when_worker_lost_before_receipt(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    request = _request(tmp_path, task_id="lost-task-001")
    service._write_state(
        request["task_id"],
        {
            "task_id": request["task_id"],
            "status": "WORKER_RUNNING",
            "attempt_id": "a" * 32,
            "worker_pid": 999999,
            "worker_pgid": 999999,
            "worker_child_pgid": None,
            "heartbeat_at": "2026-01-01T00:00:00+00:00",
            "request": request,
            "promotion_status": "NOT_CREATED",
        },
    )

    reconciled = service.reconcile_task(request["task_id"])

    assert reconciled["status"] == "FINAL_BLOCK"
    assert "lost before recoverable execution evidence" in reconciled["error"]


def test_pid_permission_error_is_treated_as_alive(monkeypatch):
    monkeypatch.setattr("os.kill", lambda pid, signal: (_ for _ in ()).throw(PermissionError()))

    assert SelfHostedTaskService._pid_alive(12345) is True


def test_submit_rejects_raw_prompt_and_unknown_worker(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state")

    with pytest.raises(ValueError, match="prompt"):
        service.build_contract(_request(tmp_path, prompt="run arbitrary shell"))
    contract = service.build_contract(_request(tmp_path, worker="gemini"))
    assert contract.preferred_provider == "gemini"
    escalated = service.build_contract(_request(tmp_path, worker="codex", fallback_worker="opencode"))
    assert escalated.fallback_provider == "opencode"
    assert escalated.maximum_provider_calls == 2
    auto = service.build_contract(
        _request(tmp_path, worker="auto", worker_order=["gemini", "codex", "ollama"])
    )
    assert auto.preferred_provider == "gemini"
    assert auto.fallback_provider == "codex"
    assert auto.provider_order == ["gemini", "codex", "ollama"]
    assert auto.maximum_provider_calls == 3
    with pytest.raises(ValueError, match="one of"):
        service.build_contract(_request(tmp_path, worker="unknown"))


def test_approval_is_hash_bound_and_does_not_merge(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state")
    request = _request(tmp_path)

    service._write_state(
        request["task_id"],
        {
            "task_id": request["task_id"],
            "status": "CANDIDATE_COMMITTED",
            "promotion_packet": {
                "candidate_commit_sha": "c" * 40,
                "candidate_tree_sha": "d" * 40,
                "candidate_state_hash": "e" * 64,
                "verified_receipt_hash": "f" * 64,
            },
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "merge_performed": False,
            "push_performed": False,
        },
    )

    approved = service.approve_promotion(
        request["task_id"],
        candidate_commit_sha="c" * 40,
        candidate_tree_sha="d" * 40,
        candidate_state_hash="e" * 64,
        verified_receipt_hash="f" * 64,
    )

    assert approved["promotion_status"] == "APPROVED"
    assert approved["merge_performed"] is False
    assert approved["push_performed"] is False


def test_marked_authority_approval_requires_exact_nested_ack_and_persists(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "authority-ack"
    packet = {"candidate_commit_sha": "c"*40, "candidate_tree_sha": "d"*40, "candidate_state_hash": "e"*64, "verified_receipt_hash": "f"*64, "authority_change_required": True, "authority_findings_sha256": "a"*64}
    service._write_state(task_id, {"task_id": task_id, "attempt_id": "attempt-1", "status": "CANDIDATE_COMMITTED", "promotion_status": "PENDING_HUMAN_APPROVAL", "promotion_packet": packet, "verified_receipt": {"authority_change_required": True, "authority_findings_sha256": "a"*64}})
    with pytest.raises(RuntimeError, match="OWNER_ARCHITECTURE_APPROVAL_REQUIRED"):
        service.approve_promotion(task_id, **{k: packet[k] for k in ("candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash")}, approval_context={"schema":"nexus.approval.v2", "approval_id":"p", "approved_by":"owner", "approval_scope":"ALLOW_ACTION_ONCE"})
    now = datetime.now(timezone.utc)
    arch = {"schema":"nexus.architecture_approval.v1", "approval_id":"arch", "approved_by":"owner", "issued_at":now.isoformat(), "expires_at":(now+timedelta(minutes=5)).isoformat(), "approval_scope":"ALLOW_ACTION_ONCE", "bound_task_id":task_id, "bound_attempt_id":"attempt-1", "candidate_commit_sha":"c"*40, "candidate_tree_sha":"d"*40, "authority_findings_sha256":"a"*64}
    approved = service.approve_promotion(task_id, **{k: packet[k] for k in ("candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash")}, approval_context={"schema":"nexus.approval.v2", "approval_id":"p", "approved_by":"owner", "approval_scope":"ALLOW_ACTION_ONCE", "architecture_approval":arch})
    assert approved["promotion_status"] == "APPROVED"
    assert approved["approved_binding"]["architecture_approval"]["authority_findings_sha256"] == "a"*64
    assert approved["approved_binding"]["architecture_approval"].get("consumed_at")
    assert "consumed_at" not in arch


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("bound_task_id", "other", "ARCHITECTURE_APPROVAL_BINDING_MISMATCH"),
        ("bound_attempt_id", "other", "ARCHITECTURE_APPROVAL_BINDING_MISMATCH"),
        ("candidate_commit_sha", "f" * 40, "ARCHITECTURE_APPROVAL_BINDING_MISMATCH"),
        ("candidate_tree_sha", "f" * 40, "ARCHITECTURE_APPROVAL_BINDING_MISMATCH"),
        ("authority_findings_sha256", "b" * 64, "ARCHITECTURE_APPROVAL_BINDING_MISMATCH"),
        # Keep the parametrized node id stable across exact-base/head runs.
        # A runtime-generated timestamp makes identical source collect as two
        # different tests and invalidates revision-bound comparison evidence.
        ("expires_at", "2000-01-01T00:00:00+00:00", "ARCHITECTURE_APPROVAL_EXPIRY_INVALID"),
        ("unknown", "reject", "ARCHITECTURE_APPROVAL_UNKNOWN_FIELDS"),
    ],
)
def test_marked_authority_approval_service_rejects_tamper_and_expiry(tmp_path, field, value, code):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "authority-service-negative"
    packet = {"candidate_commit_sha": "c" * 40, "candidate_tree_sha": "d" * 40, "candidate_state_hash": "e" * 64, "verified_receipt_hash": "f" * 64, "authority_change_required": True, "authority_findings_sha256": "a" * 64}
    service._write_state(task_id, {"task_id": task_id, "attempt_id": "attempt-1", "status": "CANDIDATE_COMMITTED", "promotion_status": "PENDING_HUMAN_APPROVAL", "promotion_packet": packet, "verified_receipt": packet})
    now = datetime.now(timezone.utc)
    architecture = {"schema": "nexus.architecture_approval.v1", "approval_id": "arch", "approved_by": "owner", "issued_at": now.isoformat(), "expires_at": (now + timedelta(minutes=5)).isoformat(), "approval_scope": "ALLOW_ACTION_ONCE", "bound_task_id": task_id, "bound_attempt_id": "attempt-1", "candidate_commit_sha": "c" * 40, "candidate_tree_sha": "d" * 40, "authority_findings_sha256": "a" * 64}
    architecture[field] = value
    with pytest.raises(RuntimeError, match=code):
        service.approve_promotion(task_id, **{k: packet[k] for k in ("candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash")}, approval_context={"schema": "nexus.approval.v2", "approval_id": "p", "approved_by": "owner", "approval_scope": "ALLOW_ACTION_ONCE", "architecture_approval": architecture})


def test_versioned_allow_action_once_is_consumed_atomically_and_replay_is_idempotent(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "approval-once"
    packet = {
        "candidate_commit_sha": "c" * 40,
        "candidate_tree_sha": "d" * 40,
        "candidate_state_hash": "e" * 64,
        "verified_receipt_hash": "f" * 64,
    }
    service._write_state(task_id, {
        "task_id": task_id,
        "attempt_id": "attempt-1",
        "status": "PENDING_HUMAN_APPROVAL",
        "promotion_status": "PENDING_HUMAN_APPROVAL",
        "promotion_packet": packet,
    })
    grant = {
        "schema": "nexus.approval.v2",
        "approval_id": "approval-once-id",
        "approved_by": "James",
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "approval_scope": "ALLOW_ACTION_ONCE",
    }
    first = service.approve_promotion(task_id, **packet, approval_context=grant)
    consumed_at = first["approved_binding"]["approval_grant"]["consumed_at"]
    assert consumed_at
    replay = service.approve_promotion(task_id, **packet, approval_context=grant)
    assert replay["duplicate"] is True
    assert replay["approved_binding"]["approval_grant"]["consumed_at"] == consumed_at


def test_integrate_revalidates_persisted_approval_definition_identity(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    packet = {
        "candidate_commit_sha": "c" * 40,
        "candidate_tree_sha": "d" * 40,
        "candidate_state_hash": "e" * 64,
        "verified_receipt_hash": "f" * 64,
    }
    grant = {
        "schema": "nexus.approval.v2",
        "approval_id": "p6-drift-approval",
        "approved_by": "James",
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "bound_task_id": "p6-drift",
        "bound_attempt_id": "attempt-1",
        "bound_action_type": "CANDIDATE_APPROVE",
        "approval_scope": "ALLOW_ACTION_ONCE",
        "contract_kind": "TRACKED_TASK_CARD",
        "contract_hash": "a" * 64,
        "task_card_hash": "a" * 64,
        "tool_manifest_hash": "b" * 64,
        "full_tool_schema_hash": "c" * 64,
        "permission_policy_hash": "d" * 64,
        "lifecycle_revision": "nexus.lifecycle.gateway.v2",
        "server_instance_id": "old-instance",
        "consumed_at": datetime.now(timezone.utc).isoformat(),
    }
    service._write_state("p6-drift", {
        "task_id": "p6-drift",
        "attempt_id": "attempt-1",
        "status": "APPROVED",
        "promotion_status": "APPROVED",
        "contract_kind": "TRACKED_TASK_CARD",
        "contract_hash": "a" * 64,
        "task_card_hash": "a" * 64,
        "promotion_packet": packet,
        "approved_binding": {**packet, "approval_grant": grant},
    })
    with pytest.raises(RuntimeError, match="APPROVAL_DEFINITION_DRIFT"):
        service.integrate_approved(
            "p6-drift",
            runtime_identity={
                "task_card_hash": "a" * 64,
                "tool_manifest_hash": "b" * 64,
                "full_tool_schema_hash": "c" * 64,
                "permission_policy_hash": "d" * 64,
                "lifecycle_revision": "nexus.lifecycle.gateway.v2",
                "server_instance_id": "new-instance",
            },
        )


def test_owner_inline_contract_is_persisted_and_hash_tampering_fails_closed(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    now = datetime.now(timezone.utc)
    contract = build_owner_inline_contract(
        task_id="inline-state",
        objective="bounded repair",
        allowed_files=["README.md"],
        verifier_commands=["git diff --check"],
        expected_head="a" * 40,
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=5)).isoformat(),
    )
    request = {
        "task_id": "inline-state", "what": "bounded repair", "why": "inline state",
        "controller_revision": "a" * 40, "allowed_files": ["README.md"],
        "verifier_commands": ["git diff --check"], "controller_repo_root": str(tmp_path),
        "target_repo_root": str(tmp_path / "target"), "target_worktree_root": str(tmp_path),
        "execution_lane": "DIRECT_CANONICAL", "primary_agent": True, "worker": "primary",
        "contract_kind": "OWNER_INLINE", "contract_hash": contract["contract_hash"],
        "owner_inline_contract": contract,
    }
    result = service._submit_direct_canonical(request, "inline-state")
    assert result["state_created"] is True
    state = service._read_state("inline-state")
    assert state["contract_kind"] == "OWNER_INLINE"
    assert state["contract_hash"] == contract["contract_hash"]
    tampered = {**request, "task_id": "inline-state-2"}
    tampered["owner_inline_contract"] = {**contract, "task_id": "inline-state-2", "objective": "changed"}
    with pytest.raises(RuntimeError, match="CONTRACT_HASH_MISMATCH"):
        service._submit_direct_canonical(tampered, "inline-state-2")


def test_owner_inline_approved_integration_revalidates_generic_contract_binding(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    now = datetime.now(timezone.utc)
    contract = build_owner_inline_contract(
        task_id="inline-approval", objective="bounded owner inline candidate", allowed_files=["README.md"],
        verifier_commands=["git diff --check"], expected_head="a" * 40, issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=5)).isoformat(),
    )
    packet = {"candidate_commit_sha": "c" * 40, "candidate_tree_sha": "d" * 40, "candidate_state_hash": "e" * 64, "verified_receipt_hash": "f" * 64}
    grant = {
        "schema": "nexus.approval.v2", "approval_id": "inline-approval-grant", "approved_by": "James",
        "issued_at": now.isoformat(), "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "bound_task_id": "inline-approval", "bound_attempt_id": "attempt-1", "bound_action_type": "CANDIDATE_APPROVE",
        "approval_scope": "ALLOW_ACTION_ONCE", "contract_kind": "OWNER_INLINE", "contract_hash": contract["contract_hash"],
        "task_card_hash": None, "tool_manifest_hash": "b" * 64, "full_tool_schema_hash": "c" * 64,
        "permission_policy_hash": "d" * 64, "lifecycle_revision": "nexus.lifecycle.gateway.v2",
        "server_instance_id": "server-1", "consumed_at": now.isoformat(),
    }
    service._write_state("inline-approval", {
        "task_id": "inline-approval", "attempt_id": "attempt-1", "status": "APPROVED", "promotion_status": "APPROVED",
        "controller_revision": "a" * 40, "contract_kind": "OWNER_INLINE", "contract_hash": contract["contract_hash"],
        "owner_inline_contract": {**contract, "objective": "tampered"}, "task_card_hash": None,
        "promotion_packet": packet, "approved_binding": {**packet, "approval_grant": grant},
    })
    with pytest.raises(RuntimeError, match="CONTRACT_HASH_MISMATCH"):
        service.integrate_approved("inline-approval", runtime_identity={
            "tool_manifest_hash": "b" * 64, "full_tool_schema_hash": "c" * 64,
            "permission_policy_hash": "d" * 64, "lifecycle_revision": "nexus.lifecycle.gateway.v2", "server_instance_id": "server-1",
        })


def test_approved_task_action_envelope_requires_integration_not_terminal(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _request(tmp_path, task_id="approved-action")
    service._write_state(
        "approved-action",
        {
            "task_id": "approved-action",
            "status": "APPROVED",
            "request": request,
            "promotion_status": "APPROVED",
            "promotion_packet": {
                "candidate_commit_sha": "c" * 40,
                "candidate_tree_sha": "d" * 40,
                "candidate_state_hash": "e" * 64,
                "verified_receipt_hash": "f" * 64,
            },
            "cleanup_decision": "REMOVED",
            "cleanup_performed": True,
        },
    )

    state = service.get_task("approved-action")

    assert state["task_action"]["action_state"] == "ACTION_REQUIRED"
    assert state["task_action"]["attention_required"] is True
    assert state["task_action"]["next_action"] == "integrate_approved_candidate"
    assert state["task_action"]["recommended_tool"] == "nexus_self_hosted_integrate_approved"
    assert state["task_action"]["candidate_commit_sha"] == "c" * 40
    assert state["task_action"]["cleanup_status"]["cleanup_decision"] == "REMOVED"


def test_approval_mismatch_returns_action_required_envelope(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _request(tmp_path, task_id="approval-mismatch")
    service._write_state(
        "approval-mismatch",
        {
            "task_id": "approval-mismatch",
            "status": "PENDING_HUMAN_APPROVAL",
            "request": request,
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "promotion_packet": {
                "candidate_commit_sha": "c" * 40,
                "candidate_tree_sha": "d" * 40,
                "candidate_state_hash": "e" * 64,
                "verified_receipt_hash": "f" * 64,
            },
            "merge_performed": False,
            "push_performed": False,
        },
    )

    result = service.approve_promotion(
        "approval-mismatch",
        candidate_commit_sha="c" * 40,
        candidate_tree_sha="0" * 40,
        candidate_state_hash="e" * 64,
        verified_receipt_hash="f" * 64,
    )

    assert result["status"] == "APPROVAL_INVALIDATED"
    assert result["task_action"]["action_state"] == "ACTION_REQUIRED"
    assert result["task_action"]["attention_required"] is True
    assert result["task_action"]["next_action"] == "resubmit_exact_approval_binding"
    assert result["task_action"]["recommended_tool"] == "nexus_self_hosted_approve_promotion"


def test_terminal_retry_keeps_task_identity_and_increments_attempt(tmp_path):
    calls = []

    def runner(contract, request, update):
        calls.append(contract.task_id)
        update("FINAL_BLOCK", {"cleanup_decision": "REMOVED", "cleanup_performed": True})
        return {"promotion_status": "NOT_CREATED"}

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", runner=runner, auto_reconcile=False, ephemeral=True
    )
    request = _request(tmp_path, task_id="stable-task")
    first = service.submit_task(request)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and service._read_state("stable-task")["status"] != "FINAL_BLOCK":
        time.sleep(0.01)
    first_attempt = service._read_state("stable-task")["attempt_id"]
    service.submit_task(request)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and len(calls) < 2:
        time.sleep(0.01)
    state = service._read_state("stable-task")

    assert first["task_id"] == state["task_id"] == "stable-task"
    assert state["attempt_id"] != first_attempt
    assert len(state["attempts"]) == 2
    assert calls == ["stable-task", "stable-task"]


def test_retry_task_reuses_terminal_request_without_duplicate_task(tmp_path):
    calls = []

    def runner(contract, request, update):
        calls.append(contract.task_id)
        update("FINAL_BLOCK", {"cleanup_decision": "REMOVED", "cleanup_performed": True})
        return {"promotion_status": "NOT_CREATED"}

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", runner=runner, auto_reconcile=False, ephemeral=True
    )
    request = _request(tmp_path, task_id="retry-surface-task")
    service.submit_task(request)
    assert _wait_for_status(service, "retry-surface-task", "FINAL_BLOCK")

    retried = service.retry_task("retry-surface-task")
    assert retried["task_id"] == "retry-surface-task"
    assert retried["retry"]["decision"] == "REUSED_TASK_ID"
    assert retried["retry"]["attempts"] == 2
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and len(calls) < 2:
        time.sleep(0.01)
    assert calls == ["retry-surface-task", "retry-surface-task"]


def test_retry_task_creates_attempt_scoped_identity_without_mutating_history(tmp_path):
    calls = []

    def runner(contract, request, update):
        calls.append(
            {
                "task_id": contract.task_id,
                "attempt_id": request.get("attempt_id"),
                "action_id": request.get("action_id"),
                "idempotency_key": request.get("idempotency_key"),
            }
        )
        update("FINAL_BLOCK", {"cleanup_decision": "REMOVED", "cleanup_performed": True})
        return {"promotion_status": "NOT_CREATED"}

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        runner=runner,
        auto_reconcile=False,
        ephemeral=True,
    )
    request = _request(
        tmp_path,
        task_id="retry-scoped-identity",
        idempotency_key="retry-scoped-identity:v1",
        action_id="action-initial",
        action_request_hash="1" * 64,
        task_card_path="tasks/campaign/card.md",
        task_card_hash="2" * 64,
        contract_kind=ContractKind.TRACKED_TASK_CARD.value,
        contract_hash="3" * 64,
    )
    service.submit_task(request)
    assert _wait_for_status(service, request["task_id"], "FINAL_BLOCK")
    before = copy.deepcopy(service._read_state(request["task_id"]))

    retried = service.retry_task(request["task_id"])
    assert retried["retry"]["decision"] == "REUSED_TASK_ID"
    assert _wait_for_status(service, request["task_id"], "FINAL_BLOCK")
    after = service._read_state(request["task_id"])

    assert after["task_id"] == before["task_id"]
    assert after["task_card_hash"] == before["task_card_hash"]
    assert after["contract_hash"] == before["contract_hash"]
    assert after["attempt_id"] != before["attempt_id"]
    assert after["action_id"] != before["action_id"]
    assert after["idempotency_key"].startswith("retry-scoped-identity:v1:retry-")
    assert after["request"]["idempotency_key"] == after["idempotency_key"]
    assert after["request"]["action_id"] == after["action_id"]
    assert after["request"]["attempt_id"] == after["attempt_id"]
    assert after["attempts"][0] == before["attempts"][0]
    assert len(after["attempts"]) == 2
    assert calls[0]["task_id"] == calls[1]["task_id"] == request["task_id"]
    assert calls[0]["idempotency_key"] != calls[1]["idempotency_key"]


def test_idempotency_key_is_duplicate_only_for_same_exact_action_request(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _request(
        tmp_path,
        task_id="idempotency-exact-request",
        idempotency_key="exact-key",
    )
    first = service.submit_task(request)
    duplicate = service.submit_task(dict(request))

    assert duplicate["duplicate"] is True
    assert duplicate["attempt_id"] == first["attempt_id"]

    conflicting = dict(request, what="different physical request")
    with pytest.raises(ValueError, match="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"):
        service.submit_task(conflicting)


def test_action_bound_retry_rebinds_envelope_to_fresh_attempt_identity(tmp_path):
    seen = []

    def runner(contract, request, update):
        seen.append(copy.deepcopy(dict(request)))
        update("FINAL_BLOCK", {"cleanup_decision": "REMOVED", "cleanup_performed": True})
        return {"promotion_status": "NOT_CREATED"}

    bound = _bound_action_request(
        tmp_path,
        execution_lane="ISOLATED_TARGET",
        task_card_path="tasks/campaign/card.md",
        task_card_hash="b" * 64,
        contract_kind=ContractKind.TRACKED_TASK_CARD.value,
        contract_hash="c" * 64,
    )
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        runner=runner,
        auto_reconcile=False,
        ephemeral=True,
    )
    first = service.submit_task(_action_transport(bound))
    assert _wait_for_status(service, bound["task_id"], "FINAL_BLOCK")
    before = copy.deepcopy(service._read_state(bound["task_id"]))

    retried = service.retry_task(bound["task_id"])
    assert retried["retry"]["decision"] == "REUSED_TASK_ID"
    assert _wait_for_status(service, bound["task_id"], "FINAL_BLOCK")
    after = service._read_state(bound["task_id"])
    retry_request = seen[1]

    assert first["task_id"] == after["task_id"] == bound["task_id"]
    assert retry_request["action"]["action_type"] == LifecycleActionType.TASK_RETRY.value
    assert retry_request["attempt_id"] == retry_request["action"]["attempt_id"] == after["attempt_id"]
    assert retry_request["action_id"] == retry_request["action"]["action_id"] == after["action_id"]
    assert retry_request["idempotency_key"] == retry_request["action"]["idempotency_key"] == after["idempotency_key"]
    assert retry_request["bound_action_request"]["attempt_id"] == after["attempt_id"]
    assert retry_request["bound_action_request"]["action_id"] == after["action_id"]
    assert retry_request["bound_action_request"]["idempotency_key"] == after["idempotency_key"]
    assert retry_request["controller_revision"] == before["request"]["controller_revision"]
    assert retry_request["allowed_files"] == before["request"]["allowed_files"]
    assert retry_request["task_card_hash"] == before["request"]["task_card_hash"]
    assert retry_request["contract_hash"] == before["request"]["contract_hash"]
    assert after["attempts"][0] == before["attempts"][0]

    duplicate = service.submit_task(copy.deepcopy(retry_request))
    assert duplicate["duplicate"] is True
    assert duplicate["attempt_id"] == after["attempt_id"]
    assert len(duplicate["attempts"]) == 2

    conflicting = copy.deepcopy(retry_request)
    conflicting["bound_action_request"]["what"] = "different physical retry request"
    conflicting["what"] = "different physical retry request"
    conflicting_hash = canonical_request_hash(conflicting["bound_action_request"])
    conflicting["action"]["request_hash"] = conflicting_hash
    conflicting["action_request_hash"] = conflicting_hash
    with pytest.raises(ValueError, match="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"):
        service.submit_task(conflicting)


def test_retry_task_blocks_retained_review_without_disposition(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state(
        "retained-retry-task",
        {
            "task_id": "retained-retry-task",
            "status": "RETAINED_FOR_REVIEW",
            "attempt_id": "attempt-1",
            "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES",
            "request": {"task_id": "retained-retry-task"},
        },
    )

    result = service.retry_task("retained-retry-task")
    assert result["retry"]["decision"] == "BLOCKED_RETAINED_REVIEW"


def test_retry_task_reuses_clean_retained_no_candidate_after_cleanup(tmp_path):
    calls = []

    def runner(contract, request, update):
        calls.append(contract.task_id)
        update("RETAINED_FOR_REVIEW", {
            "promotion_status": "NOT_CREATED",
            "cleanup_decision": "REMOVED",
            "cleanup_performed": True,
        })
        return {"promotion_status": "NOT_CREATED"}

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", runner=runner, auto_reconcile=False, ephemeral=True
    )
    request = _request(tmp_path, task_id="retained-retry-clean")
    service.submit_task(request)
    assert _wait_for_status(service, "retained-retry-clean", "RETAINED_FOR_REVIEW")

    retried = service.retry_task("retained-retry-clean")
    assert retried["task_id"] == "retained-retry-clean"
    assert retried["retry"]["decision"] == "REUSED_TASK_ID"
    assert retried["retry"]["attempts"] == 2
    assert _wait_for_status(service, "retained-retry-clean", "RETAINED_FOR_REVIEW")
    assert calls == ["retained-retry-clean", "retained-retry-clean"]


def test_safe_hooks_directory_does_not_require_rewrite(tmp_path, monkeypatch):
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    hooks.chmod(0o700)
    monkeypatch.setenv("NEXUS_CANONICAL_GIT_HOOKS_DIR", str(hooks))

    def failing_chmod(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "chmod", failing_chmod)
    assert get_canonical_git_hooks_dir() == hooks.resolve()


def test_noncanonical_state_root_requires_ephemeral_mode(tmp_path):
    with pytest.raises(ValueError, match="canonical state root"):
        SelfHostedTaskService(state_dir="/Users/jameschen/Workspace/nexus-sibling-state", auto_reconcile=False)


def test_default_state_root_uses_configured_canonical_root(tmp_path, monkeypatch):
    canonical = tmp_path / "canonical"
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", str(canonical))

    service = SelfHostedTaskService(auto_reconcile=False)

    assert service.state_dir == canonical.resolve()


def test_archive_manifest_hash_is_reproducible(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("done", {"task_id": "done", "status": "FINAL_BLOCK"})

    first = service.archive_states(dry_run=True)
    second = service.archive_states(dry_run=True)

    assert first["manifest_hash"] == second["manifest_hash"]
    assert first["entries"][0]["receipt_hash"]


def test_archive_apply_persists_manifest_and_remains_readable(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("done", {"task_id": "done", "status": "FINAL_BLOCK", "updated_at": "2026-01-01T00:00:00+00:00"})
    preview = service.archive_states(dry_run=True)

    applied = service.archive_states(dry_run=False)
    repeated = service.archive_states(dry_run=False)

    assert applied["manifest_hash"] == preview["manifest_hash"]
    assert Path(applied["manifest_path"]).is_file()
    assert not (tmp_path / "state" / "done.json").exists()
    assert service.get_task("done")["status"] == "FINAL_BLOCK"
    assert repeated["entries"] == []


def test_archived_integrated_task_retries_with_same_identity_and_versions_receipt(tmp_path):
    calls = []

    def runner(contract, request, update):
        calls.append(contract.task_id)
        update("FINAL_BLOCK", {"cleanup_decision": "REMOVED", "cleanup_performed": True})
        return {"promotion_status": "NOT_CREATED"}

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", runner=runner, auto_reconcile=False, ephemeral=True
    )
    request = _request(tmp_path, task_id="archived-integrated")
    contract = service.build_contract(request)
    first_attempt = "a" * 32
    service._write_state("archived-integrated", {
        "task_id": "archived-integrated", "status": "INTEGRATED",
        "attempt_id": first_attempt, "attempts": [{"attempt_id": first_attempt}],
        "request": request, "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash, "promotion_status": "INTEGRATED",
        "candidate_ref": "refs/nexus-candidates/archived-integrated/old",
        "promotion_packet": {"candidate_commit_sha": "c" * 40},
        "final_disposition": "INTEGRATED", "cleanup_decision": "REMOVED",
        "cleanup_performed": True, "updated_at": "2026-01-01T00:00:00+00:00",
    })
    first_archive = service.archive_states(dry_run=False)

    submitted = service.submit_task(request)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        current = service._read_state("archived-integrated")
        if current and current["status"] == "FINAL_BLOCK":
            break
        time.sleep(0.01)
    current = service._read_state("archived-integrated")
    second_archive = service.archive_states(dry_run=False)

    assert submitted["task_id"] == "archived-integrated"
    assert current["attempt_id"] != first_attempt
    assert len(current["attempts"]) == 2
    assert current["candidate_ref"] is None
    assert current["candidate_history"][0]["final_disposition"] == "INTEGRATED"
    assert calls == ["archived-integrated"]
    assert Path(first_archive["entries"][0]["archive_location"]).is_file()
    assert Path(second_archive["entries"][0]["archive_location"]).is_file()
    assert first_archive["entries"][0]["archive_location"] != second_archive["entries"][0]["archive_location"]
    assert service.get_task("archived-integrated")["attempt_id"] == current["attempt_id"]


def test_terminal_retry_accepts_revision_fast_forward_and_preserves_contract_history(tmp_path):
    calls = []

    def runner(contract, request, update):
        calls.append((contract.controller_revision, contract.target_base_revision))
        update("FINAL_BLOCK", {"cleanup_decision": "REMOVED", "cleanup_performed": True})
        return {"promotion_status": "NOT_CREATED"}

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", runner=runner, auto_reconcile=False, ephemeral=True
    )
    request = _real_request(tmp_path, task_id="activation-retry")
    first_contract = service.build_contract(request)
    first_attempt = "a" * 32
    service._write_state("activation-retry", {
        "task_id": "activation-retry", "status": "FINAL_BLOCK",
        "attempt_id": first_attempt, "attempts": [{"attempt_id": first_attempt}],
        "request": request, "contract": first_contract.model_dump(mode="json"),
        "contract_hash": first_contract.contract_hash, "promotion_status": "NOT_CREATED",
        "final_disposition": "FINAL_BLOCK", "cleanup_decision": "ALREADY_REMOVED",
        "cleanup_performed": False,
    })

    controller = Path(request["controller_repo_root"])
    (controller / "README").write_text("activation\n")
    _git(controller, "add", "README")
    _git(controller, "commit", "-m", "activate lifecycle")
    activated_head = _git(controller, "rev-parse", "HEAD")
    refreshed = {
        **request,
        "controller_revision": activated_head,
        "target_base_revision": activated_head,
    }

    submitted = service.submit_task(refreshed)
    current = _wait_for_status(service, "activation-retry", "FINAL_BLOCK")

    assert submitted["attempt_id"] != first_attempt
    assert current["attempt_id"] == submitted["attempt_id"]
    assert len(current["attempts"]) == 2
    assert current["contract_hash"] == service.build_contract(refreshed).contract_hash
    assert current["controller_revision"] == activated_head
    assert current["target_initial_revision"] == activated_head
    assert current["contract_history"] == [{
        "attempt_id": first_attempt,
        "contract_hash": first_contract.contract_hash,
        "controller_revision": request["controller_revision"],
        "target_base_revision": request["target_base_revision"],
        "final_disposition": "FINAL_BLOCK",
    }]
    assert calls == [(activated_head, activated_head)]


def test_terminal_retry_rejects_non_revision_contract_change(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", runner=lambda *_: {}, auto_reconcile=False, ephemeral=True
    )
    request = _real_request(tmp_path, task_id="semantic-drift-retry")
    contract = service.build_contract(request)
    service._write_state("semantic-drift-retry", {
        "task_id": "semantic-drift-retry", "status": "FINAL_BLOCK",
        "attempt_id": "a" * 32, "attempts": [{"attempt_id": "a" * 32}],
        "request": request, "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash, "promotion_status": "NOT_CREATED",
        "cleanup_decision": "ALREADY_REMOVED",
    })

    changed = {**request, "what": "Silently change the task objective"}

    with pytest.raises(ValueError, match="different contract"):
        service.submit_task(changed)


def test_pending_candidate_blocks_retry_until_superseded(tmp_path):
    calls = []

    def runner(contract, request, update):
        calls.append(contract.task_id)
        update("FINAL_BLOCK", {"cleanup_decision": "REMOVED", "cleanup_performed": True})
        return {"promotion_status": "NOT_CREATED"}

    service = SelfHostedTaskService(state_dir=tmp_path / "state", runner=runner, auto_reconcile=False, ephemeral=True)
    request = _request(tmp_path, task_id="pending-task")
    contract = service.build_contract(request)
    service._write_state("pending-task", {
        "task_id": "pending-task", "status": "PENDING_HUMAN_APPROVAL",
        "attempt_id": "a" * 32, "attempts": [{"attempt_id": "a" * 32}],
        "request": request, "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash, "promotion_status": "PENDING_HUMAN_APPROVAL",
        "cleanup_decision": "REMOVED", "cleanup_performed": True,
    })

    blocked = service.submit_task(request)
    assert blocked["attempt_id"] == "a" * 32
    assert calls == []

    service.dispose_candidate("pending-task", disposition="SUPERSEDED", superseded_by="next")
    retried = service.submit_task(request)
    assert retried["attempt_id"] != "a" * 32


def test_cleanup_apply_invokes_governed_worktree_cleanup(tmp_path, monkeypatch):
    calls = []
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _request(tmp_path, task_id="cleanup-task")
    contract = service.build_contract(request)
    lease = TargetWorktreeLease(
        schema="nexus.target_worktree_lease.v1", lease_id="lease", task_id="cleanup-task",
        controller_revision=contract.controller_revision, target_base_revision=contract.target_base_revision,
        target_worktree=request["target_repo_root"], target_branch="nexus/task/cleanup-task",
        initial_head=contract.target_base_revision, initial_status_sha256="0" * 64,
        controller_status_sha256="0" * 64, created_from_exact_revision=True,
        commit_created=False, merge_performed=False,
    )
    service._write_state("cleanup-task", {
        "task_id": "cleanup-task", "status": "FINAL_BLOCK", "request": request,
        "contract": contract.model_dump(mode="json"), "contract_hash": contract.contract_hash,
        "attempt_id": "a" * 32, "lease": lease.__dict__,
    })

    class FakeManager:
        def __init__(self, root_dir):
            pass
        def cleanup_terminal_target(self, contract, lease, **kwargs):
            calls.append(kwargs["dry_run"])
            return SimpleNamespace(decision="REMOVED", blocker=None, performed=not kwargs["dry_run"], eligible=True)

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", FakeManager)
    planned = service.cleanup_tasks(task_id="cleanup-task", dry_run=True)
    applied = service.cleanup_tasks(task_id="cleanup-task", dry_run=False)

    assert calls == []
    assert planned["decisions"][0]["cleanup_decision"] == "BLOCKED_BY_AUTHORITY"
    assert applied["decisions"][0]["cleanup_decision"] == "BLOCKED_BY_AUTHORITY"


def test_cleanup_rejects_approved_binding_mismatch(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _request(tmp_path, task_id="binding-cleanup")
    contract = service.build_contract(request)
    lease = TargetWorktreeLease(
        schema="nexus.target_worktree_lease.v1", lease_id="lease", task_id="binding-cleanup",
        controller_revision=contract.controller_revision, target_base_revision=contract.target_base_revision,
        target_worktree=request["target_repo_root"], target_branch="nexus/task/binding-cleanup",
        initial_head=contract.target_base_revision, initial_status_sha256="0" * 64,
        controller_status_sha256="0" * 64, created_from_exact_revision=True,
        commit_created=False, merge_performed=False,
    )
    service._write_state("binding-cleanup", {
        "task_id": "binding-cleanup", "status": "INTEGRATED", "request": request,
        "contract": contract.model_dump(mode="json"), "attempt_id": "a" * 32,
        "lease": lease.__dict__, "promotion_status": "INTEGRATED",
        "promotion_packet": {"candidate_commit_sha": "c" * 40},
        "approved_binding": {"candidate_commit_sha": "d" * 40},
    })

    decision = service.cleanup_tasks(task_id="binding-cleanup", dry_run=False)["decisions"][0]

    assert decision["cleanup_decision"] == "BLOCKED_BY_AUTHORITY"
    assert "external acceptance receipt" in decision["cleanup_blocker"]


def test_integration_failure_is_persisted(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("integration-fail", {
        "task_id": "integration-fail", "status": "APPROVED", "attempt_id": "a" * 32,
        "promotion_status": "APPROVED", "contract": {"target_worktree_root": str(tmp_path / "targets")},
    })

    class FailingIntegration:
        def __init__(self, integration_root):
            pass
        def integrate_task_state(self, state, integration_branch):
            raise RuntimeError("integration verifier failed")

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.ControlledIntegrationManager", FailingIntegration)
    with pytest.raises(RuntimeError, match="EXTERNAL_ACCEPTANCE_REQUIRED"):
        service.integrate_approved("integration-fail")

    state = service._read_state("integration-fail")
    assert state["status"] == "APPROVED"
    assert state["promotion_status"] == "APPROVED"
    assert state.get("push_performed") is not True


def test_integrate_approved_rechecks_exact_candidate_before_integration(tmp_path, monkeypatch):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    task_id = "integration-recheck"
    request = _real_request(tmp_path, task_id=task_id)
    request["allowed_files"] = ["README"]
    contract = service.build_contract(request)
    controller = Path(request["controller_repo_root"])
    (controller / "README").write_text("candidate\n", encoding="utf-8")
    _git(controller, "add", "README")
    _git(controller, "commit", "-m", "candidate")
    candidate_commit = _git(controller, "rev-parse", "HEAD")
    candidate_tree = _git(controller, "rev-parse", "HEAD^{tree}")
    packet = {
        "candidate_commit_sha": candidate_commit,
        "candidate_tree_sha": candidate_tree,
        "candidate_state_hash": "e" * 64,
        "verified_receipt_hash": "f" * 64,
        "authority_change_required": True,
        "authority_findings_sha256": "a" * 64,
    }
    closure = _closure_context(
        task_id,
        candidate_commit,
        candidate_tree_sha=candidate_tree,
    )
    grant = {
        **closure["approval_context"],
        "consumed_at": datetime.now(timezone.utc).isoformat(),
    }
    architecture_approval = {
        "schema": "nexus.architecture_approval.v1",
        "approval_id": "arch-integration",
        "approved_by": "owner",
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "approval_scope": "ALLOW_ACTION_ONCE",
        "bound_task_id": task_id,
        "bound_attempt_id": "attempt-1",
        "candidate_commit_sha": candidate_commit,
        "candidate_tree_sha": candidate_tree,
        "authority_findings_sha256": "a" * 64,
    }
    service._write_state(
        task_id,
        {
            "task_id": task_id,
            "attempt_id": "attempt-1",
            "status": "APPROVED",
            "promotion_status": "APPROVED",
            "request": request,
            "contract": contract.model_dump(mode="json"),
            "promotion_packet": packet,
            "verified_receipt": {
                "repository_contract_gate_passed": True,
                "repository_contract_policy_revision_hash": "a" * 64,
                "authority_change_required": True,
                "authority_findings_sha256": "a" * 64,
            },
            "approved_binding": {**packet, "approval_grant": grant, "architecture_approval": architecture_approval},
            "external_acceptance": closure["external_acceptance"],
            "integration_authorization": closure["integration_authorization"],
        },
    )
    seen = {}

    def block_recheck(self, **kwargs):
        seen.update(kwargs)
        return RepositoryContractGateReceipt(
            passed=False,
            mode="shadow",
            policy_revision_hash="a" * 64,
            findings=(),
            blocking_reasons=("integration_candidate_identity_mismatch",),
        )

    monkeypatch.setattr(
        RepositoryContractGate, "evaluate_committed_candidate", block_recheck
    )
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.ControlledIntegrationManager",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("integration invoked")),
    )

    with pytest.raises(RuntimeError, match="REPOSITORY_CONTRACT_RECHECK_FAILED"):
        service.integrate_approved(task_id)

    assert seen["candidate_commit"] == candidate_commit
    assert seen["candidate_tree_sha"] == candidate_tree
    assert seen["expected_policy_revision_hash"] == "a" * 64
    assert seen["architecture_approval"] == architecture_approval
    assert seen["attempt_id"] == "attempt-1"
    assert service._read_state(task_id)["status"] == "APPROVED"


def test_integrate_approved_rechecks_again_at_locked_apply_boundary(tmp_path, monkeypatch):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    task_id = "integration-apply-boundary-recheck"
    request = _real_request(tmp_path, task_id=task_id)
    request["allowed_files"] = ["README"]
    contract = service.build_contract(request)
    controller = Path(request["controller_repo_root"])
    (controller / "README").write_text("candidate\n", encoding="utf-8")
    _git(controller, "add", "README")
    _git(controller, "commit", "-m", "candidate")
    candidate_commit = _git(controller, "rev-parse", "HEAD")
    candidate_tree = _git(controller, "rev-parse", "HEAD^{tree}")
    packet = {
        "candidate_commit_sha": candidate_commit,
        "candidate_tree_sha": candidate_tree,
        "candidate_state_hash": "e" * 64,
        "verified_receipt_hash": "f" * 64,
        "authority_change_required": True,
        "authority_findings_sha256": "a" * 64,
    }
    closure = _closure_context(task_id, candidate_commit, candidate_tree_sha=candidate_tree)
    grant = {
        **closure["approval_context"],
        "consumed_at": datetime.now(timezone.utc).isoformat(),
    }
    architecture_approval = {
        "schema": "nexus.architecture_approval.v1",
        "approval_id": "arch-integration",
        "approved_by": "owner",
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "approval_scope": "ALLOW_ACTION_ONCE",
        "bound_task_id": task_id,
        "bound_attempt_id": "attempt-1",
        "candidate_commit_sha": candidate_commit,
        "candidate_tree_sha": candidate_tree,
        "authority_findings_sha256": "a" * 64,
    }
    service._write_state(
        task_id,
        {
            "task_id": task_id,
            "attempt_id": "attempt-1",
            "status": "APPROVED",
            "promotion_status": "APPROVED",
            "request": request,
            "contract": contract.model_dump(mode="json"),
            "promotion_packet": packet,
            "verified_receipt": {
                "repository_contract_gate_passed": True,
                "repository_contract_policy_revision_hash": "a" * 64,
                "authority_change_required": True,
                "authority_findings_sha256": "a" * 64,
            },
            "approved_binding": {**packet, "approval_grant": grant, "architecture_approval": architecture_approval},
            "external_acceptance": closure["external_acceptance"],
            "integration_authorization": closure["integration_authorization"],
        },
    )
    calls = []

    def two_phase_recheck(self, **kwargs):
        calls.append(kwargs)
        return RepositoryContractGateReceipt(
            passed=len(calls) == 1,
            mode="shadow",
            policy_revision_hash="a" * 64,
            findings=(),
            blocking_reasons=(
                () if len(calls) == 1 else ("integration_candidate_identity_mismatch",)
            ),
        )

    monkeypatch.setattr(
        RepositoryContractGate, "evaluate_committed_candidate", two_phase_recheck
    )
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.ControlledIntegrationManager",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("integration invoked")),
    )

    with pytest.raises(RuntimeError, match="REPOSITORY_CONTRACT_RECHECK_FAILED"):
        service.integrate_approved(task_id)

    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert calls[0]["architecture_approval"] == architecture_approval
    assert service._read_state(task_id)["merge_performed"] is False


def test_exact_approved_integration_is_idempotent(tmp_path, monkeypatch):
    calls = []
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("integration-once", {
        "task_id": "integration-once", "status": "APPROVED", "attempt_id": "a" * 32,
        "promotion_status": "APPROVED", "contract": {"target_worktree_root": str(tmp_path / "targets")},
    })

    from nexus.orchestrator.governed_integration import IntegrationReceipt

    class SuccessfulIntegration:
        def __init__(self, integration_root):
            pass
        def integrate_task_state(self, state, integration_branch):
            calls.append(integration_branch)
            return IntegrationReceipt(
                schema="nexus.integration_receipt/v1",
                task_id="integration-once",
                integration_branch=integration_branch,
                source_branch="nexus/task/integration-once",
                candidate_commit_sha="c" * 40,
                integration_base_sha="b" * 40,
                integration_commit_sha="c" * 40,
                verifier_passed=True,
                merge_performed=True,
                push_performed=False,
                worktree_removed=True,
            )

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.ControlledIntegrationManager", SuccessfulIntegration)
    with pytest.raises(RuntimeError, match="EXTERNAL_ACCEPTANCE_REQUIRED"):
        service.integrate_approved("integration-once")
    assert calls == []


def test_gb042_valid_approved_integration_is_one_side_effect_and_stable_duplicate(
    tmp_path, monkeypatch
):
    """GB-042: a valid acceptance/approval binding integrates once only."""
    from nexus.orchestrator.governed_integration import IntegrationReceipt

    task_id = "gb042-integration-once"
    candidate = "c" * 40
    request = _request(tmp_path, task_id=task_id)
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    contract = service.build_contract(request)
    closure = _closure_context(task_id, candidate)
    authorization_hash = IntegrationAuthorizationEnvelope(
        **closure["integration_authorization"]
    ).authorization_hash
    closure["integration_authorization"]["authorization_hash"] = authorization_hash
    packet = {
        "candidate_commit_sha": candidate,
        "candidate_tree_sha": "d" * 40,
        "candidate_state_hash": "e" * 64,
        "verified_receipt_hash": "f" * 64,
    }
    grant = {
        **closure["approval_context"],
        "consumed_at": datetime.now(timezone.utc).isoformat(),
    }
    service._write_state(
        task_id,
        {
            "task_id": task_id,
            "status": "APPROVED",
            "promotion_status": "APPROVED",
            "attempt_id": "attempt-1",
            "request": request,
            "contract": contract.model_dump(mode="json"),
            "promotion_packet": packet,
            "approved_binding": {**packet, "approval_grant": grant},
            "external_acceptance": closure["external_acceptance"],
            "integration_authorization": closure["integration_authorization"],
            "verified_receipt": {
                "repository_contract_gate_passed": True,
                "repository_contract_policy_revision_hash": "a" * 64,
            },
        },
    )
    gate_calls = []
    integration_calls = []

    def passing_gate(self, **kwargs):
        gate_calls.append(kwargs)
        return RepositoryContractGateReceipt(
            passed=True,
            mode="shadow",
            policy_revision_hash="a" * 64,
            findings=(),
            blocking_reasons=(),
        )

    class SuccessfulIntegration:
        def __init__(self, integration_root):
            pass

        def integrate_authorized_task_state(self, state, **kwargs):
            integration_calls.append(kwargs)
            return IntegrationReceipt(
                schema="nexus.integration_receipt/v1",
                task_id=task_id,
                integration_branch="nexus/integration/main",
                source_branch="nexus/task/gb042-integration-once",
                candidate_commit_sha=candidate,
                integration_base_sha="b" * 40,
                integration_commit_sha="1" * 40,
                verifier_passed=True,
                merge_performed=True,
                push_performed=False,
                worktree_removed=True,
                staging_commit_sha="1" * 40,
                post_apply_verified=True,
                acceptance_receipt_hash=closure["external_acceptance"]["receipt_hash"],
                authorization_hash=authorization_hash,
            )

    monkeypatch.setattr(RepositoryContractGate, "evaluate_committed_candidate", passing_gate)
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.ControlledIntegrationManager",
        SuccessfulIntegration,
    )

    first = service.integrate_approved(task_id)
    second = service.integrate_approved(task_id)

    assert len(integration_calls) == 1
    assert len(gate_calls) == 2  # preflight and locked apply recheck
    assert first["status"] == "INTEGRATED"
    assert second["status"] == "INTEGRATED"
    assert second["integration_result_sha"] == first["integration_result_sha"] == "1" * 40
    assert second["integration_receipt"] == first["integration_receipt"]


def test_lifecycle_receipt_exposes_required_fields(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("receipt", {"task_id": "receipt", "status": "FINAL_BLOCK"})

    receipt = service.get_receipt("receipt")

    required = {
        "task_id", "attempt_id", "status", "submitted_at", "controller_worktree", "controller_revision",
        "controller_status_sha256", "target_worktree", "target_initial_revision",
        "target_branch", "target_created_at", "worker_provider", "worker_pid",
        "heartbeat_at", "execution_outcome", "verification_verdict",
        "candidate_commit_sha", "candidate_tree_sha", "candidate_ref",
        "candidate_state_hash", "verified_receipt_hash", "promotion_status",
        "approved_binding", "integration_branch", "integration_base_sha",
        "integration_result_sha", "terminal_status", "cleanup_eligible",
        "cleanup_decision", "cleanup_blocker", "cleanup_performed",
        "cleanup_performed_at", "state_retention_status", "archive_eligible",
        "archive_location",
    }
    assert required <= receipt.keys()


def test_replace_failed_target_forwards_fresh_task_states():
    captured = {}

    class FakeManager:
        def verify_controller_unchanged(self, contract, expected_status_sha256=None):
            return expected_status_sha256

        def _run_git(self, args, cwd=None):
            return "h" * 40

        def cleanup(self, task_id, force=False):
            assert force is True

    class FakeController:
        def prepare_task(self, contract, *, task_states=None):
            captured["task_states"] = task_states
            return "replacement-lease"

    lease = SimpleNamespace(target_worktree="/tmp/target", initial_head="h" * 40, controller_status_sha256="s" * 64)
    states = {"retained": {"status": "FINAL_BLOCK"}}
    result = SelfHostedTaskService._replace_failed_target(
        FakeManager(), FakeController(), SimpleNamespace(task_id="task"), lease,
        task_states=states,
    )

    assert result == "replacement-lease"
    assert captured["task_states"] is states


def test_orphan_clean_target_is_reconciled_and_removed(tmp_path):
    request = _real_request(tmp_path)
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    contract = service.build_contract(request)
    from nexus.orchestrator.worktree_manager import WorktreeManager
    lease = WorktreeManager(root_dir=contract.target_worktree_root).create_lease(contract)
    service._write_state(contract.task_id, {
        "task_id": contract.task_id, "status": "TARGET_LEASED",
        "attempt_id": "a" * 32, "attempts": [{"attempt_id": "a" * 32}],
        "request": request, "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash, "lease": lease.__dict__,
        "worker_pid": 999999, "heartbeat_at": "2026-01-01T00:00:00+00:00",
    })

    reconciled = service.reconcile_task(contract.task_id)

    assert reconciled["status"] == "FINAL_BLOCK"
    assert reconciled["cleanup_decision"] == "REMOVED"
    assert reconciled["cleanup_performed"] is True
    assert not Path(lease.target_worktree).exists()


def test_orphan_candidate_checkpoint_resumes_ref_and_cleanup(tmp_path):
    request = _real_request(tmp_path, task_id="candidate-recovery")
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    contract = service.build_contract(request)
    from nexus.orchestrator.worktree_manager import WorktreeManager
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "nexus_canary.txt").write_text("candidate\n")
    _git(target, "add", "nexus_canary.txt")
    _git(target, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "candidate")
    candidate = _git(target, "rev-parse", "HEAD")
    tree = _git(target, "rev-parse", "HEAD^{tree}")
    service._write_state(contract.task_id, {
        "task_id": contract.task_id, "status": "CANDIDATE_COMMITTED",
        "attempt_id": "a" * 32, "attempts": [{"attempt_id": "a" * 32}],
        "request": request, "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash, "lease": lease.__dict__,
        "promotion_packet": {
            "candidate_commit_sha": candidate, "candidate_tree_sha": tree,
            "candidate_state_hash": "c" * 64, "verified_receipt_hash": "d" * 64,
        },
        "worker_pid": 999999, "heartbeat_at": "2026-01-01T00:00:00+00:00",
    })

    reconciled = service.reconcile_task(contract.task_id)

    assert reconciled["status"] == "PENDING_HUMAN_APPROVAL"
    assert reconciled["cleanup_decision"] == "REMOVED"
    assert not target.exists()
    assert _git(Path(contract.controller_repo_root), "rev-parse", reconciled["candidate_ref"]) == candidate


def test_verified_retained_candidate_can_resume_ref_protection_and_cleanup(tmp_path):
    request = _real_request(tmp_path, task_id="retained-candidate-recovery")
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    contract = service.build_contract(request)
    from nexus.orchestrator.worktree_manager import WorktreeManager
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "nexus_canary.txt").write_text("candidate\n")
    _git(target, "add", "nexus_canary.txt")
    _git(target, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "candidate")
    candidate = _git(target, "rev-parse", "HEAD")
    tree = _git(target, "rev-parse", "HEAD^{tree}")
    service._write_state(contract.task_id, {
        "task_id": contract.task_id, "status": "RETAINED_FOR_REVIEW",
        "attempt_id": "a" * 32, "attempts": [{"attempt_id": "a" * 32}],
        "request": request, "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash, "lease": lease.__dict__,
        "promotion_packet": {
            "candidate_commit_sha": candidate, "candidate_tree_sha": tree,
            "candidate_state_hash": "c" * 64, "verified_receipt_hash": "d" * 64,
            "promotion_status": "PENDING_HUMAN_APPROVAL",
        },
        "verified_receipt": {"verified": True},
        "promotion_status": "NOT_CREATED", "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES",
        "worker_pid": 999999, "heartbeat_at": "2026-01-01T00:00:00+00:00",
    })

    recovered = service.recover_retained_candidate(contract.task_id)

    assert recovered["status"] == "PENDING_HUMAN_APPROVAL"
    assert recovered["cleanup_decision"] == "REMOVED"
    assert not target.exists()
    assert _git(Path(contract.controller_repo_root), "rev-parse", recovered["candidate_ref"]) == candidate


def test_live_target_lease_is_not_reconciled_away(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("live", {
        "task_id": "live", "status": "TARGET_LEASED", "attempt_id": "a" * 32,
        "worker_pid": os.getpid(), "heartbeat_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    })

    state = service.reconcile_task("live")

    assert state["status"] == "TARGET_LEASED"


def test_five_terminal_retries_keep_one_task_identity(tmp_path):
    calls = []

    def runner(contract, request, update):
        calls.append(contract.task_id)
        update("FINAL_BLOCK", {"cleanup_decision": "REMOVED", "cleanup_performed": True})
        return {"promotion_status": "NOT_CREATED"}

    service = SelfHostedTaskService(state_dir=tmp_path / "state", runner=runner, auto_reconcile=False, ephemeral=True)
    request = _request(tmp_path, task_id="five-attempts")
    for expected in range(1, 6):
        service.submit_task(request)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            state = service._read_state("five-attempts")
            if state["status"] == "FINAL_BLOCK" and len(calls) == expected:
                break
            time.sleep(0.01)

    state = service._read_state("five-attempts")
    assert state["task_id"] == "five-attempts"
    assert len(state["attempts"]) == 5
    assert len({attempt["attempt_id"] for attempt in state["attempts"]}) == 5
    assert calls == ["five-attempts"] * 5


def test_same_task_id_different_contract_fails_closed(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", runner=lambda *args: {}, auto_reconcile=False, ephemeral=True)
    request = _request(tmp_path, task_id="contract-bound")
    service.submit_task(request)

    with pytest.raises(ValueError, match="different contract"):
        service.submit_task({**request, "why": "different"})


def test_different_active_controller_is_rejected(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", runner=lambda *args: {}, auto_reconcile=False, ephemeral=True)
    first = _request(tmp_path, task_id="first-active")
    contract = service.build_contract(first)
    service._write_state("first-active", {
        "task_id": "first-active", "status": "WORKER_RUNNING",
        "contract": contract.model_dump(mode="json"), "contract_hash": contract.contract_hash,
    })
    second = _request(
        tmp_path, task_id="second-active",
        controller_repo_root=str(tmp_path / "different-controller"),
        target_repo_root=str(tmp_path / "targets" / "second-active"),
    )

    with pytest.raises(RuntimeError, match="active Controller lease"):
        service.submit_task(second)


def test_wait_task_polls_until_action_required(tmp_path):
    release = __import__("threading").Event()

    def runner(contract, request, update):
        release.wait(2)
        return {"promotion_status": "PENDING_HUMAN_APPROVAL", "candidate_commit_created": True}

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        runner=runner,
        auto_reconcile=False,
        ephemeral=True,
    )
    request = _request(tmp_path, task_id="wait-poll")
    service.submit_task(request)

    release.set()
    waited = service.wait_task("wait-poll", timeout_seconds=1.0, poll_interval_seconds=0.01)

    assert waited["status"] == "PENDING_HUMAN_APPROVAL"
    assert waited["wait"]["timed_out"] is False
    assert waited["task_action"]["action_state"] == "ACTION_REQUIRED"
    assert waited["task_action"]["recommended_tool"] == "nexus_self_hosted_approve_promotion"


def test_wait_task_timeout_returns_in_progress_envelope(tmp_path):
    release = __import__("threading").Event()

    def runner(contract, request, update):
        release.wait(2)
        return {"promotion_status": "PENDING_HUMAN_APPROVAL", "candidate_commit_created": True}

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        runner=runner,
        auto_reconcile=False,
        ephemeral=True,
    )
    request = _request(tmp_path, task_id="wait-timeout")
    service.submit_task(request)

    waited = service.wait_task("wait-timeout", timeout_seconds=0.01, poll_interval_seconds=0.001)

    assert waited["wait"]["timed_out"] is True
    assert waited["task_action"]["action_state"] == "IN_PROGRESS"
    assert waited["task_action"]["next_action"] == "wait_for_task"
    assert waited["task_action"]["recommended_tool"] == "nexus_self_hosted_wait_task"
    release.set()
    service.wait_task("wait-timeout", timeout_seconds=2.0)


def test_wait_task_reads_snapshot_without_state_lock(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("wait-lock-free", {
        "task_id": "wait-lock-free",
        "status": "PENDING_HUMAN_APPROVAL",
        "promotion_status": "PENDING_HUMAN_APPROVAL",
    })

    def fail_lock():
        raise AssertionError("wait_task must not acquire the state lock")

    monkeypatch.setattr(service, "_state_lock", fail_lock)
    waited = service.wait_task("wait-lock-free", timeout_seconds=0)

    assert waited["wait"]["timed_out"] is False
    assert waited["task_action"]["action_state"] == "ACTION_REQUIRED"


def test_compact_status_and_wait_project_terminal_worker_failure_read_only(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    error = "  provider\n\tfailed   " + ("x" * 600)
    service._write_state("worker-failed", {
        "task_id": "worker-failed",
        "status": "FINAL_BLOCK",
        "promotion_status": "NOT_CREATED",
        "worker_provider": "agy",
        "request": {"model": "qwen2.5-coder:7b"},
        "exit_code": "17",
        "execution_outcome": "FAILED",
        "error": error,
    })
    path = service._state_path("worker-failed")
    before = path.read_bytes()

    compact = service.get_task_snapshot("worker-failed")
    waited = service.wait_task("worker-failed", timeout_seconds=0)

    for result in (compact, waited):
        blocker = result["blocker"]
        assert blocker["code"] == "WORKER_EXECUTION_FAILED"
        assert blocker["failure_stage"] == "worker_execution"
        assert blocker["provider"] == "agy"
        assert blocker["model"] == "qwen2.5-coder:7b"
        assert blocker["exit_code"] == 17
        assert blocker["execution_outcome"] == "FAILED"
        assert blocker["detail"] == "worker execution failed"
        assert len(blocker["detail"]) <= 512
        assert "\n" not in blocker["detail"] and "\t" not in blocker["detail"]
        assert blocker["error_sha256"] == hashlib.sha256(error.encode("utf-8")).hexdigest()
        assert "provider" not in blocker["detail"]
        assert "x" * 32 not in blocker["detail"]
    assert path.read_bytes() == before


def test_compact_failure_projection_preserves_explicit_blocker_and_fabricates_nothing(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    explicit = {"code": "EXPLICIT_BLOCK", "detail": "human disposition required"}
    service._write_state("explicit", {
        "task_id": "explicit", "status": "FINAL_BLOCK", "blocker": explicit,
        "error": "worker failed", "request": {"model": "model"},
    })
    service._write_state("explicit-falsey", {
        "task_id": "explicit-falsey", "status": "FINAL_BLOCK", "blocker": {},
        "error": "worker failed", "request": {"model": "model"},
    })
    service._write_state("without-error", {
        "task_id": "without-error", "status": "FINAL_BLOCK", "request": {"model": "model"},
    })
    service._write_state("running-with-error", {
        "task_id": "running-with-error", "status": "SUBMITTED", "error": "worker failed",
    })

    assert service.get_task_snapshot("explicit")["blocker"] == explicit
    assert service.wait_task("explicit", timeout_seconds=0)["blocker"] == explicit
    assert service.get_task_snapshot("explicit-falsey")["blocker"] == {}
    assert service.wait_task("explicit-falsey", timeout_seconds=0)["blocker"] == {}
    assert service.get_task_snapshot("without-error")["blocker"] is None
    assert service.wait_task("without-error", timeout_seconds=0)["blocker"] is None
    assert service.get_task_snapshot("running-with-error")["blocker"] is None
    timed_out = service.wait_task("running-with-error", timeout_seconds=0)
    assert timed_out["blocker"] is None


def test_verify_task_reads_snapshot_without_state_lock(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)

    def fail_lock():
        raise AssertionError("verify_task must not acquire the state lock")

    monkeypatch.setattr(service, "_state_lock", fail_lock)
    result = service.verify_task("verify-lock-free-missing")

    assert result["verdict"] == "STATE_MISSING"


def test_list_actionable_tasks_excludes_integrated_terminal_state(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    packet = {
        "candidate_commit_sha": "c" * 40,
        "candidate_tree_sha": "d" * 40,
        "candidate_state_hash": "e" * 64,
        "verified_receipt_hash": "f" * 64,
    }
    service._write_state("needs-approval", {
        "task_id": "needs-approval",
        "status": "PENDING_HUMAN_APPROVAL",
        "promotion_status": "PENDING_HUMAN_APPROVAL",
        "promotion_packet": packet,
    })
    service._write_state("needs-integration", {
        "task_id": "needs-integration",
        "status": "APPROVED",
        "promotion_status": "APPROVED",
        "promotion_packet": packet,
    })
    service._write_state("done", {
        "task_id": "done",
        "status": "INTEGRATED",
        "promotion_status": "INTEGRATED",
        "promotion_packet": packet,
        "terminal_status": "INTEGRATED",
    })

    result = service.list_actionable_tasks()

    assert [item["task_id"] for item in result["tasks"]] == ["needs-approval", "needs-integration"]
    assert result["actionable_count"] == 2
    assert result["tasks"][0]["task_action"]["next_action"] == "approve_candidate"
    assert result["tasks"][1]["task_action"]["next_action"] == "integrate_approved_candidate"


def test_list_actionable_tasks_is_compact_and_does_not_reconcile(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("blocked", {
        "task_id": "blocked",
        "status": "FINAL_BLOCK",
        "promotion_status": "NOT_CREATED",
        "error": "worker failed",
        "request": {"large": "x" * 10000},
    })
    service._lock_path().unlink()

    def fail_reconcile(_task_id):
        raise AssertionError("list_actionable_tasks must not reconcile task state")

    def fail_lock():
        raise AssertionError("read-only actionable listing must not acquire the state lock")

    monkeypatch.setattr(service, "reconcile_task", fail_reconcile)
    monkeypatch.setattr(service, "_state_lock", fail_lock)
    result = service.list_actionable_tasks()

    assert result["details_included"] is False
    assert result["actionable_count"] == 1
    assert result["tasks"][0]["task_id"] == "blocked"
    assert "error" not in result["tasks"][0]
    assert not service._lock_path().exists()


def test_workspace_inventory_plan_and_slot_status_are_read_only(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="workspace-service")
    contract = service.build_contract(request)
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    before = sorted(path.name for path in (tmp_path / "state").iterdir())

    inventory = service.workspace_inventory(controller_root=contract.controller_repo_root)
    plan = service.workspace_convergence_plan(
        controller_root=contract.controller_repo_root,
        expected_controller_revision=contract.controller_revision,
    )
    slot = service.workspace_slot_status(
        campaign_id="workspace-service",
        controller_root=contract.controller_repo_root,
    )

    assert inventory["schema"] == "nexus.workspace_inventory.v1"
    assert plan["schema"] == "nexus.workspace_convergence_plan.v1"
    assert plan["controller_revision"] == contract.controller_revision
    assert slot["status"] in {"READY", "BLOCKED"}
    assert Path(lease.target_worktree).exists()
    assert sorted(path.name for path in (tmp_path / "state").iterdir()) == before


def test_workspace_read_only_calls_do_not_create_missing_target_root(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    controller = tmp_path / "controller"
    controller.mkdir()
    subprocess.run(["git", "init", "-q", str(controller)], check=True)
    subprocess.run(["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "-C", str(controller), "commit", "--allow-empty", "-m", "init"], check=True, capture_output=True)
    missing_root = tmp_path / "missing-target-root"
    assert not missing_root.exists()

    service.workspace_inventory(controller_root=controller)
    service.workspace_convergence_plan(controller_root=controller)
    service.workspace_slot_status(campaign_id="read-only", controller_root=controller)

    assert not missing_root.exists()
    assert not (controller.parent / "nexus-runtime-targets").exists()


def test_direct_canonical_lane_records_intent_without_target(tmp_path, monkeypatch):
    controller = tmp_path / "canonical"
    controller.mkdir()
    subprocess.run(["git", "init", "-q", str(controller)], check=True)
    subprocess.run(["git", "-C", str(controller), "branch", "-M", "nexus/integration/main"], check=True)
    subprocess.run(["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "-C", str(controller), "commit", "--allow-empty", "-m", "init"], check=True, capture_output=True)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT", controller.resolve())

    request = {
        "task_id": "direct-canary",
        "what": "bounded direct canary",
        "why": "prove ordinary work does not allocate a Target",
        "controller_repo_root": str(controller),
        "allowed_files": ["src/one.py"],
        "verifier_commands": ["true"],
        "primary_agent": True,
        "worker": "primary",
        "execution_lane": "DIRECT_CANONICAL",
    }
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)

    result = service.submit_task(request)

    assert result["status"] == "DIRECT_CANONICAL_READY"
    assert result["execution_lane"] == "DIRECT_CANONICAL"
    assert result["state_created"] is True
    assert result["durable_status"] == "DIRECT_INTENT_RECORDED"
    assert (tmp_path / "state" / "direct-canary.json").exists()
    assert result["task_action"]["next_action"] == "nexus_task_finish"


def test_ordinary_primary_request_defaults_to_direct_canonical(tmp_path, monkeypatch):
    controller = tmp_path / "canonical"
    controller.mkdir()
    _init_repo(controller)
    _git(controller, "branch", "-M", "nexus/integration/main")
    _git(controller, "commit", "--allow-empty", "-m", "init")
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT", controller.resolve())

    lane = resolve_execution_lane({
        "controller_repo_root": str(controller),
        "allowed_files": ["src/ordinary.py"],
        "verifier_commands": ["/usr/bin/true"],
        "primary_agent": True,
        "worker": "primary",
    })

    assert lane["execution_lane"] == "DIRECT_CANONICAL"
    assert lane["eligible"] is True

    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    handoff = service.submit_task({
        "task_id": "ordinary-default-direct",
        "what": "ordinary bounded edit",
        "why": "prove the default lane does not allocate a Target",
        "controller_repo_root": str(controller),
        "allowed_files": ["src/ordinary.py"],
        "verifier_commands": ["/usr/bin/true"],
        "primary_agent": True,
        "worker": "primary",
    })
    assert handoff["execution_lane"] == "DIRECT_CANONICAL"
    assert handoff["target_created"] is False
    assert handoff["state_created"] is True
    assert handoff["durable_status"] == "DIRECT_INTENT_RECORDED"
    assert not (tmp_path / "nexus-runtime-targets").exists()


def test_direct_canonical_lane_fails_closed_to_isolated_for_delegated_worker(tmp_path, monkeypatch):
    controller = tmp_path / "canonical"
    controller.mkdir()
    subprocess.run(["git", "init", "-q", str(controller)], check=True)
    subprocess.run(["git", "-C", str(controller), "branch", "-M", "nexus/integration/main"], check=True)
    subprocess.run(["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "-C", str(controller), "commit", "--allow-empty", "-m", "init"], check=True, capture_output=True)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT", controller.resolve())

    lane = resolve_execution_lane({
        "controller_repo_root": str(controller),
        "allowed_files": ["src/one.py"],
        "primary_agent": False,
        "worker": "agy",
        "execution_lane": "DIRECT_CANONICAL",
    })

    assert lane["execution_lane"] == "ISOLATED_TARGET"
    assert "primary_agent_attestation_required" in lane["blockers"]
    assert "delegated_worker_forbidden" in lane["blockers"]


def test_direct_canonical_completion_verifies_scoped_commit_with_durable_state(tmp_path, monkeypatch):
    controller = tmp_path / "canonical"
    controller.mkdir()
    subprocess.run(["git", "init", "-q", str(controller)], check=True)
    subprocess.run(["git", "-C", str(controller), "branch", "-M", "nexus/integration/main"], check=True)
    subprocess.run(["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "-C", str(controller), "commit", "--allow-empty", "-m", "init"], check=True, capture_output=True)
    base = subprocess.run(["git", "-C", str(controller), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    (controller / "src").mkdir()
    (controller / "src" / "canary.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(controller), "add", "src/canary.py"], check=True)
    subprocess.run(["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "-C", str(controller), "commit", "-m", "direct canary"], check=True, capture_output=True)
    head = subprocess.run(["git", "-C", str(controller), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT", controller.resolve())
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = {
        "task_id": "direct-complete",
        "controller_repo_root": str(controller),
        "controller_revision": base,
        "allowed_files": ["src/canary.py"],
        "verifier_commands": ["/usr/bin/true"],
        "primary_agent": True,
        "worker": "primary",
        "execution_lane": "DIRECT_CANONICAL",
    }
    service.submit_task(request)

    receipt = service.complete_direct_canonical(request, expected_commit_sha=head)

    assert receipt["status"] == "DIRECT_CANONICAL_COMPLETED"
    assert receipt["commit_sha"] == head
    assert receipt["candidate_created"] is False
    assert receipt["target_created"] is False
    assert receipt["state_created"] is True
    assert receipt["telemetry"]["overhead_ms"] >= 0
    assert receipt["reconciliation_status"] == "RECONCILED"
    assert service.get_task("direct-complete")["status"] == "DIRECT_COMPLETED"


def test_direct_completion_allows_clean_passive_registered_worktree_and_records_audit(tmp_path, monkeypatch):
    controller = tmp_path / "canonical"
    controller.mkdir()
    _init_repo(controller)
    _git(controller, "branch", "-M", "nexus/integration/main")
    _git(controller, "commit", "--allow-empty", "-m", "init")
    base = _git(controller, "rev-parse", "HEAD")
    passive = tmp_path / "passive"
    _git(controller, "worktree", "add", "--detach", str(passive), base)
    (controller / "src").mkdir()
    (controller / "src" / "passive.py").write_text("value = 1\n", encoding="utf-8")
    _git(controller, "add", "src/passive.py")
    _git(controller, "commit", "-m", "direct with passive worktree")
    head = _git(controller, "rev-parse", "HEAD")
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT", controller.resolve())
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = {
        "task_id": "direct-passive-worktree",
        "controller_repo_root": str(controller),
        "controller_revision": base,
        "allowed_files": ["src/passive.py"],
        "verifier_commands": ["/usr/bin/true"],
        "primary_agent": True,
        "worker": "primary",
        "execution_lane": "DIRECT_CANONICAL",
    }
    service.submit_task(request)

    receipt = service.complete_direct_canonical(request, expected_commit_sha=head)

    assert receipt["status"] == "DIRECT_CANONICAL_COMPLETED"
    audit = receipt["worktree_audit"]
    assert audit["registered_count"] == 2
    assert audit["blockers"] == []
    assert audit["revision"] == head
    assert any(record["path"] == str(passive.resolve()) for record in audit["aux_records"])


def test_direct_canonical_duplicate_finish_reuses_receipt_without_second_commit(tmp_path, monkeypatch):
    controller = tmp_path / "canonical"
    controller.mkdir()
    _init_repo(controller)
    _git(controller, "branch", "-M", "nexus/integration/main")
    _git(controller, "commit", "--allow-empty", "-m", "init")
    base = _git(controller, "rev-parse", "HEAD")
    (controller / "src").mkdir()
    (controller / "src" / "duplicate.py").write_text("value = 1\n", encoding="utf-8")
    _git(controller, "add", "src/duplicate.py")
    _git(controller, "commit", "-m", "direct duplicate")
    head = _git(controller, "rev-parse", "HEAD")
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT", controller.resolve())
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = {
        "task_id": "direct-duplicate",
        "controller_repo_root": str(controller),
        "controller_revision": base,
        "allowed_files": ["src/duplicate.py"],
        "verifier_commands": ["/usr/bin/true"],
        "primary_agent": True,
        "worker": "primary",
        "execution_lane": "DIRECT_CANONICAL",
    }
    service.submit_task(request)
    first = service.complete_direct_canonical(request, expected_commit_sha=head)
    second = service.complete_direct_canonical(request, expected_commit_sha=head)
    assert first["commit_sha"] == second["commit_sha"] == head
    assert second["duplicate"] is True
    assert _git(controller, "rev-list", "--count", f"{base}..HEAD") == "1"


def test_direct_canonical_interrupted_state_reconciles_without_replay(tmp_path, monkeypatch):
    controller = tmp_path / "canonical"
    controller.mkdir()
    _init_repo(controller)
    _git(controller, "branch", "-M", "nexus/integration/main")
    _git(controller, "commit", "--allow-empty", "-m", "init")
    base = _git(controller, "rev-parse", "HEAD")
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT", controller.resolve())
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = {
        "task_id": "direct-interrupted",
        "controller_repo_root": str(controller),
        "controller_revision": base,
        "allowed_files": ["src/interrupted.py"],
        "verifier_commands": ["/usr/bin/true"],
        "primary_agent": True,
        "worker": "primary",
        "execution_lane": "DIRECT_CANONICAL",
    }
    service.submit_task(request)
    service._mutate_state("direct-interrupted", lambda state: state.update({"status": "DIRECT_STARTED"}))
    reconciled = service.reconcile_task("direct-interrupted")
    assert reconciled["status"] == "DIRECT_RECONCILE_REQUIRED"
    assert reconciled["reconciliation_required"] is True
    assert reconciled["canonical_action"]["reconciliation"]["blocker"] == "UNKNOWN_REQUIRES_RECONCILE"
    assert reconciled["target_worktree"] is None

    closed = service.reconcile_task("direct-interrupted")
    assert closed["status"] == "FINAL_BLOCK"
    assert closed["reconciliation_status"] == "RECONCILED"
    assert closed["reconciliation_decision"] == "NO_MUTATION_OBSERVED"
    assert closed["reconciliation_required"] is False
    assert closed["cleanup_decision"] == "ALREADY_REMOVED"
    assert closed["task_action"]["next_action"] == "retry_same_task"
    repeated = service.reconcile_task("direct-interrupted")
    assert repeated["status"] == "FINAL_BLOCK"
    assert repeated["reconciliation_decision"] == "NO_MUTATION_OBSERVED"


def test_direct_canonical_idempotency_key_reuse_fails_closed_across_tasks(tmp_path, monkeypatch):
    controller = tmp_path / "canonical"
    controller.mkdir()
    _init_repo(controller)
    _git(controller, "branch", "-M", "nexus/integration/main")
    _git(controller, "commit", "--allow-empty", "-m", "init")
    base = _git(controller, "rev-parse", "HEAD")
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT", controller.resolve())
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    common = {
        "controller_repo_root": str(controller),
        "controller_revision": base,
        "allowed_files": ["src/idempotent.py"],
        "verifier_commands": ["/usr/bin/true"],
        "primary_agent": True,
        "worker": "primary",
        "execution_lane": "DIRECT_CANONICAL",
        "idempotency_key": "shared-idempotency-key",
    }
    service.submit_task({**common, "task_id": "direct-idempotency-a"})
    with pytest.raises(ValueError, match="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"):
        service.submit_task({**common, "task_id": "direct-idempotency-b"})


def test_direct_lane_rejects_lockfile_and_active_mutation_task():
    lane = resolve_execution_lane({
        "controller_repo_root": "/Users/jameschen/Workspace/nexus",
        "allowed_files": ["package-lock.json"],
        "primary_agent": True,
        "worker": "primary",
        "execution_lane": "DIRECT_CANONICAL",
    }, active_mutation_tasks=1)

    assert lane["execution_lane"] == "ISOLATED_TARGET"
    assert "lockfile_change_forbidden" in lane["blockers"]
    assert "another_mutation_task_is_active" in lane["blockers"]


def test_owner_finish_approves_exact_binding_then_integrates_once(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    calls: list[tuple[str, str]] = []

    def approve(task_id, **kwargs):
        calls.append(("approve", task_id))
        assert kwargs["candidate_commit_sha"] == "a" * 40
        return {"status": "APPROVED", "promotion_status": "APPROVED"}

    def integrate(task_id, *, integration_branch):
        calls.append(("integrate", integration_branch))
        return {"status": "INTEGRATED", "promotion_status": "INTEGRATED"}

    monkeypatch.setattr(service, "archive_states", lambda *, dry_run: {"dry_run": dry_run, "entries": [{"task_id": "owner-finish-canary"}]})

    monkeypatch.setattr(service, "approve_promotion", approve)
    monkeypatch.setattr(service, "integrate_approved", integrate)

    result = service.owner_finish(
        "owner-finish-canary",
        candidate_commit_sha="a" * 40,
        candidate_tree_sha="b" * 40,
        candidate_state_hash="c" * 64,
        verified_receipt_hash="d" * 64,
        **_closure_context(
            "owner-finish-canary", "a" * 40,
            candidate_tree_sha="b" * 40,
            candidate_state_hash="c" * 64,
            candidate_receipt_hash="d" * 64,
        ),
    )

    assert result["status"] == "INTEGRATED_AND_CLEANED"
    assert calls == [("approve", "owner-finish-canary"), ("integrate", "nexus/integration/main")]
    assert result["owner_finish"]["archive"]["dry_run"] is False


def test_owner_finish_ten_candidate_matrix_archives_each_terminal(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    calls = []
    original_approve = service.approve_promotion

    def approve(task_id, **kwargs):
        calls.append(("approve", task_id))
        return original_approve(task_id, **kwargs)

    def integrate(task_id, *, integration_branch):
        calls.append(("integrate", task_id, integration_branch))
        state = service._read_state(task_id)
        return service._checkpoint(task_id, "INTEGRATED", {
            "promotion_status": "INTEGRATED",
            "terminal_status": "INTEGRATED",
            "state_retention_status": "TERMINAL",
            "archive_eligible": True,
            "merge_performed": True,
            "integration_branch": integration_branch,
            "integration_result_sha": "f" * 40,
        }, attempt_id=state.get("attempt_id"))

    monkeypatch.setattr(service, "approve_promotion", approve)
    monkeypatch.setattr(service, "integrate_approved", integrate)

    for index in range(10):
        task_id = f"owner-finish-matrix-{index}"
        binding = {
            "candidate_commit_sha": f"{index + 1:040x}",
            "candidate_tree_sha": f"{index + 101:040x}",
            "candidate_state_hash": f"{index + 201:064x}",
            "verified_receipt_hash": f"{index + 301:064x}",
        }
        service._write_state(task_id, {
            "task_id": task_id,
            "status": "CANDIDATE_CAPTURED",
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "promotion_packet": binding,
            "request": {},
            "attempt_id": f"attempt-{index}",
            "attempts": [{"attempt_id": f"attempt-{index}"}],
        })

        result = service.owner_finish(
            task_id,
            **binding,
            **_closure_context(
                task_id,
                binding["candidate_commit_sha"],
                f"attempt-{index}",
                candidate_tree_sha=binding["candidate_tree_sha"],
                candidate_state_hash=binding["candidate_state_hash"],
                candidate_receipt_hash=binding["verified_receipt_hash"],
            ),
        )

        assert result["status"] == "INTEGRATED_AND_CLEANED"
        assert not service._state_path(task_id).exists()
        assert service._archive_state_path(task_id).is_file()

    assert len(calls) == 20
    assert [item[0] for item in calls].count("approve") == 10
    assert [item[0] for item in calls].count("integrate") == 10


def test_owner_finish_does_not_integrate_invalid_binding(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    integrated = False
    monkeypatch.setattr(service, "approve_promotion", lambda *_args, **_kwargs: {"status": "APPROVAL_INVALIDATED", "promotion_status": "APPROVAL_INVALIDATED"})
    monkeypatch.setattr(service, "integrate_approved", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("integrated")))

    with pytest.raises(RuntimeError, match="exact approved candidate binding"):
        service.owner_finish(
            "owner-finish-invalid",
            candidate_commit_sha="a" * 40,
            candidate_tree_sha="b" * 40,
            candidate_state_hash="c" * 64,
            verified_receipt_hash="d" * 64,
            **_closure_context("owner-finish-invalid", "a" * 40),
        )


def test_final_block_clean_no_candidate_recommends_same_task_retry(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    state = {
        "task_id": "retry-action",
        "status": "FINAL_BLOCK",
        "promotion_status": "NOT_CREATED",
        "cleanup_decision": "REMOVED",
    }

    action = service._task_action_envelope(state)

    assert action["next_action"] == "retry_same_task"
    assert action["recommended_tool"] == "nexus_self_hosted_retry"
    assert action["action_state"] == "TERMINAL"
    assert action["attention_required"] is False


@pytest.mark.parametrize("cleanup_decision", ["REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"])
def test_clean_candidate_less_final_block_preserves_optional_retry_and_evidence(tmp_path, cleanup_decision):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("settled-failure", {
        "task_id": "settled-failure",
        "status": "FINAL_BLOCK",
        "promotion_status": "NOT_CREATED",
        "cleanup_decision": cleanup_decision,
        "candidate_created": False,
        "candidate_status": "FINAL_BLOCK",
        "state_retention_status": "TERMINAL",
        "reconciliation_status": "RECONCILED",
        "reconciliation_decision": "NO_MUTATION_OBSERVED",
        "uncertain_mutation": False,
        "error": "provider failed",
    })

    state = service.get_task("settled-failure")
    action = state["task_action"]

    assert action["action_state"] == "TERMINAL"
    assert action["attention_required"] is False
    assert action["next_action"] == "retry_same_task"
    assert action["recommended_tool"] == "nexus_self_hosted_retry"
    assert state["error"] == "provider failed"
    assert service.list_actionable_tasks()["actionable_count"] == 0


@pytest.mark.parametrize("state", [
    {"status": "FINAL_BLOCK", "promotion_status": "NOT_CREATED"},
    {"status": "FINAL_BLOCK", "promotion_status": "NOT_CREATED", "cleanup_decision": "REMOVED", "cleanup_blocker": "unknown"},
    {"status": "FINAL_BLOCK", "promotion_status": "NOT_CREATED", "cleanup_decision": "REMOVED", "reconciliation_required": True},
    {"status": "FINAL_BLOCK", "promotion_status": "NOT_CREATED", "cleanup_decision": "REMOVED", "promotion_packet": {"candidate_commit_sha": "c" * 40}},
    {"status": "FINAL_BLOCK", "promotion_status": "PENDING_HUMAN_APPROVAL", "cleanup_decision": "REMOVED"},
    {"status": "RETAINED_FOR_REVIEW", "promotion_status": "NOT_CREATED", "cleanup_decision": "REMOVED"},
    {"status": "INTEGRATION_FAILED", "promotion_status": "INTEGRATION_FAILED", "cleanup_decision": "REMOVED", "approved_binding": {"candidate_commit_sha": "c" * 40}},
])
def test_unresolved_failure_states_remain_actionable(state):
    action = SelfHostedTaskService._task_action_envelope({"task_id": "unresolved", **state})

    assert action["attention_required"] is True


@pytest.mark.parametrize(("field", "value"), [
    ("candidate_created", True),
    ("candidate_status", "PENDING_HUMAN_APPROVAL"),
    ("state_retention_status", "ACTIVE"),
    ("reconciliation_decision", "RETAINED_FOR_REVIEW"),
    ("uncertain_mutation", True),
])
def test_clean_final_block_fails_closed_on_hidden_unresolved_state(field, value):
    state = {
        "task_id": "hidden-unresolved",
        "status": "FINAL_BLOCK",
        "promotion_status": "NOT_CREATED",
        "cleanup_decision": "REMOVED",
        field: value,
    }

    action = SelfHostedTaskService._task_action_envelope(state)

    assert action["attention_required"] is True
    assert action["action_state"] == "FINAL_BLOCK"


def test_duplicate_task_card_hash_returns_existing_task_and_retry_action(tmp_path):
    card = tmp_path / "card.md"
    card.write_text("task_id: logical-new\n", encoding="utf-8")
    card_hash = hashlib.sha256(card.read_bytes()).hexdigest()
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("logical-old", {"task_id": "logical-old", "status": "FINAL_BLOCK", "task_card_hash": card_hash})
    request = _request(tmp_path, task_id="logical-new", task_card_path=str(card), allow_unbound_test_identity=True)

    result = service.submit_task(request)

    assert result["task_id"] == "logical-old"
    assert result["duplicate"]["code"] == "DUPLICATE_LOGICAL_TASK"
    assert result["duplicate"]["existing_task_id"] == "logical-old"
    assert result["duplicate"]["recommended_tool"] == "nexus_self_hosted_get_receipt"


def test_receipt_exposes_numeric_telemetry(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("telemetry-task", {
        "task_id": "telemetry-task",
        "status": "FINAL_BLOCK",
        "submitted_at": "2026-01-01T00:00:00+00:00",
        "telemetry": {"wall_time_ms": 12, "overhead_ms": 4},
    })

    receipt = service.get_receipt("telemetry-task")

    assert receipt["telemetry"]["wall_time_ms"] == 12
    assert receipt["telemetry"]["overhead_ms"] == 4


def test_failure_action_envelope_exposes_one_precise_recovery_surface():
    assert SelfHostedTaskService._task_action_envelope({
        "task_id": "integration-failure",
        "status": "INTEGRATION_FAILED",
        "promotion_status": "INTEGRATION_FAILED",
        "merge_performed": False,
    })["recommended_tool"] == "nexus_self_hosted_retry_integration"
    assert SelfHostedTaskService._task_action_envelope({
        "task_id": "verified-uncommitted",
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "verified_receipt": {"verified": True},
        "attempt_resolution": {"verdict": "PROVEN"},
    })["recommended_tool"] == "nexus_self_hosted_recover_verified_uncommitted_candidate"
    assert SelfHostedTaskService._task_action_envelope({
        "task_id": "dirty-retained",
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES",
    })["recommended_tool"] == "nexus_self_hosted_cleanup"


def test_retry_integration_reuses_approved_binding_without_worker_retry(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("integration-retry", {
        "task_id": "integration-retry",
        "status": "INTEGRATION_FAILED",
        "promotion_status": "INTEGRATION_FAILED",
        "merge_performed": False,
        "approved_binding": {"candidate_commit_sha": "a" * 40},
        "attempt_id": "attempt-1",
        "attempts": [{"attempt_id": "attempt-1"}],
        "request": {"what": "x", "why": "y"},
    })
    monkeypatch.setattr(service, "integrate_approved", lambda task_id, *, integration_branch: {"task_id": task_id, "status": "INTEGRATED", "integration_branch": integration_branch})

    result = service.retry_integration("integration-retry")

    assert result["status"] == "INTEGRATED"
    state = service._read_state("integration-retry")
    assert state["status"] == "INTEGRATING"
    assert state["integration_retry"] is True


def test_default_production_target_root_is_outside_disabled_worktree_namespace(monkeypatch):
    monkeypatch.chdir("/Users/jameschen/Workspace/nexus")

    root, target = resolve_canonical_target_roots("root-test")

    assert str(root) == "/Users/jameschen/Workspace/nexus-runtime-targets"
    assert str(target) == "/Users/jameschen/Workspace/nexus-runtime-targets/root-test"


def test_activation_root_derives_target_namespace_from_bound_source_root(monkeypatch, tmp_path):
    import nexus.orchestrator.self_hosted_task_service as service_module

    activation_root = tmp_path / "clean-activation"
    activation_root.mkdir()
    monkeypatch.setattr(service_module, "CANONICAL_SOURCE_ROOT", activation_root)
    monkeypatch.chdir(activation_root)

    root, target = resolve_canonical_target_roots("activation-root-test")

    assert root == tmp_path / "nexus-runtime-targets"
    assert target == root / "activation-root-test"


def test_disabled_target_root_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="DISABLED_TARGET_ROOT"):
        resolve_canonical_target_roots(
            "retired-root",
            requested_target_worktree_root=str(tmp_path / "nexus-worktrees" / "runtime-targets"),
        )


def test_checkpoint_telemetry_separates_provider_verifier_and_control_plane(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("telemetry-breakdown", {
        "task_id": "telemetry-breakdown",
        "status": "WORKER_RUNNING",
        "submitted_at": "2026-01-01T00:00:00+00:00",
        "attempt_id": "a",
        "attempts": [{"attempt_id": "a"}],
        "execution": {"wall_time_ms": 17},
        "executions": [{"wall_time_ms": 17}],
        "verified_receipt": {"verifier_evidence": [{"wall_time_ms": 5}]},
        "telemetry": {"worktree_time_ms": 3, "commit_hook_time_ms": 2, "cleanup_time_ms": 1},
    })

    result = service._checkpoint("telemetry-breakdown", "FINAL_BLOCK", attempt_id="a")

    telemetry = result["telemetry"]
    assert telemetry["provider_time_ms"] == 17
    assert telemetry["verifier_time_ms"] == 5
    assert telemetry["worktree_time_ms"] == 3
    assert telemetry["commit_hook_time_ms"] == 2
    assert telemetry["cleanup_time_ms"] == 1
    assert telemetry["overhead_ms"] >= 0


def test_thirty_task_cutover_matrix_uses_one_of_two_explicit_lanes(tmp_path, monkeypatch):
    controller = tmp_path / "canonical"
    controller.mkdir()
    subprocess.run(["git", "init", "-q", str(controller)], check=True)
    subprocess.run(["git", "-C", str(controller), "branch", "-M", "nexus/integration/main"], check=True)
    subprocess.run(["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "-C", str(controller), "commit", "--allow-empty", "-m", "init"], check=True, capture_output=True)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT", controller.resolve())
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)

    direct_results = []
    isolated_results = []
    for index in range(30):
        request = {
            "task_id": f"matrix-direct-{index}",
            "what": "matrix direct canary",
            "why": "prove no Target allocation",
            "controller_repo_root": str(controller),
            "allowed_files": ["src/canary.py"],
            "verifier_commands": ["true"],
            "primary_agent": True,
            "worker": "primary",
            "execution_lane": "DIRECT_CANONICAL",
        }
        direct = service.submit_task(request)
        service.record_canonical_action_failure(request["task_id"], "MATRIX_ABORTED")
        direct_results.append(direct)
        isolated_results.append(resolve_execution_lane({"execution_lane": "ISOLATED_TARGET"}))

    assert len(direct_results) == 30
    assert {result["execution_lane"] for result in direct_results} == {"DIRECT_CANONICAL"}
    assert all(result["state_created"] is True and result["target_created"] is False for result in direct_results)
    assert all(result["execution_lane"] == "ISOLATED_TARGET" for result in isolated_results)
    assert (tmp_path / "state").exists()
    assert not (tmp_path / "nexus-runtime-targets").exists()


def test_revalidation_15_direct_10_isolated_5_fault_matrix(tmp_path, monkeypatch):
    """P7 physical matrix: real commits, real Target cleanup, and fault actions."""
    controller = tmp_path / "canonical"
    controller.mkdir()
    _init_repo(controller)
    _git(controller, "config", "user.name", "P7 Matrix")
    _git(controller, "config", "user.email", "p7@example.test")
    _git(controller, "commit", "--allow-empty", "-m", "matrix base")
    _git(controller, "branch", "-M", "nexus/integration/main")
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT", controller.resolve())
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)

    direct_receipts = []
    for index in range(15):
        base = _git(controller, "rev-parse", "HEAD")
        relative = f"src/direct-{index}.py"
        (controller / "src").mkdir(exist_ok=True)
        (controller / relative).write_text(f"value = {index}\n", encoding="utf-8")
        _git(controller, "add", relative)
        _git(controller, "commit", "-m", f"direct matrix {index}")
        head = _git(controller, "rev-parse", "HEAD")
        request = {
            "task_id": f"direct-matrix-{index}",
            "controller_repo_root": str(controller),
            "controller_revision": base,
            "allowed_files": [relative],
            "verifier_commands": ["/usr/bin/true"],
            "primary_agent": True,
            "worker": "primary",
            "execution_lane": "DIRECT_CANONICAL",
        }
        service.submit_task(request)
        direct_receipts.append(service.complete_direct_canonical(request, expected_commit_sha=head))

    assert len(direct_receipts) == 15
    assert all(item["target_created"] is False and item["state_created"] is True for item in direct_receipts)
    direct_overheads = sorted(item["telemetry"]["overhead_ms"] for item in direct_receipts)
    assert direct_overheads[int(len(direct_overheads) * 0.95) - 1] < 1000

    target_root = tmp_path / "isolated-targets"
    manager = WorktreeManager(root_dir=str(target_root))
    isolated_controller = tmp_path / "isolated-controller"
    isolated_controller.mkdir()
    _init_repo(isolated_controller)
    _git(isolated_controller, "config", "user.name", "P7 Isolated")
    _git(isolated_controller, "config", "user.email", "p7-isolated@example.test")
    (isolated_controller / "README").write_text("base\n", encoding="utf-8")
    _git(isolated_controller, "add", "README")
    _git(isolated_controller, "commit", "-m", "isolated base")
    isolated_base = _git(isolated_controller, "rev-parse", "HEAD")
    prepare_ms = []
    release_ms = []
    for index in range(10):
        request = _request(
            tmp_path,
            task_id=f"isolated-matrix-{index}",
            controller_revision=isolated_base,
            target_base_revision=isolated_base,
            controller_repo_root=str(isolated_controller),
            target_repo_root=str(target_root / f"placeholder-{index}"),
            target_worktree_root=str(target_root),
            allowed_files=["src/"],
        )
        contract = service.build_contract(request)
        started = time.perf_counter()
        slot = manager.prepare_reusable_slot(contract, campaign_id=f"matrix-{index}", slot_index=0, task_states={})
        prepare_ms.append((time.perf_counter() - started) * 1000)
        assert slot.status == "READY"
        slot_contract = contract.model_copy(update={
            "target_repo_root": slot.slot_path,
            "target_worktree_root": str(Path(slot.slot_path).parent),
        })
        lease = manager.create_lease(slot_contract)
        target = Path(lease.target_worktree)
        (target / "src").mkdir(exist_ok=True)
        (target / "src" / f"isolated-{index}.txt").write_text("bounded\n", encoding="utf-8")
        _git(target, "add", "src")
        _git(target, "commit", "-m", f"isolated matrix {index}")
        salvage = manager.protect_salvage_head(slot_contract, lease, f"matrix-{index}")
        started = time.perf_counter()
        cleanup = manager.cleanup_terminal_target(
            slot_contract,
            lease,
            salvage_commit=str(salvage["salvage_commit_sha"]),
            salvage_ref=str(salvage["salvage_ref"]),
        )
        release_ms.append((time.perf_counter() - started) * 1000)
        assert cleanup.decision in {"REMOVED", "ALREADY_REMOVED"}
        assert not target.exists()

    fault_cases = [
        {"status": "FINAL_BLOCK", "promotion_status": "NOT_CREATED", "cleanup_decision": "REMOVED"},
        {"status": "FINAL_BLOCK", "promotion_status": "NOT_CREATED", "cleanup_decision": "REMOVED", "error": "provider"},
        {"status": "RETAINED_FOR_REVIEW", "promotion_status": "NOT_CREATED", "cleanup_decision": "REMOVED", "error": "verifier", "verified_receipt": {"verified": True}, "attempt_resolution": {"verdict": "PROVEN"}},
        {"status": "RETAINED_FOR_REVIEW", "promotion_status": "NOT_CREATED", "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES", "error": "commit"},
        {"status": "INTEGRATION_FAILED", "promotion_status": "INTEGRATION_FAILED", "merge_performed": False, "approved_binding": {"candidate_commit_sha": "a" * 40}},
    ]
    expected_tools = [
        "nexus_self_hosted_retry", "nexus_self_hosted_retry", "nexus_self_hosted_retry",
        "nexus_self_hosted_cleanup", "nexus_self_hosted_retry_integration",
    ]
    actions = [SelfHostedTaskService._task_action_envelope({"task_id": f"fault-{i}", **case}) for i, case in enumerate(fault_cases)]
    assert [action["recommended_tool"] for action in actions] == expected_tools
    assert all(action["next_action"] for action in actions)
    assert sorted(prepare_ms)[int(len(prepare_ms) * 0.95) - 1] < 5000
    assert sorted(release_ms)[int(len(release_ms) * 0.95) - 1] < 5000
    assert not (target_root / "serial-slot" / "slot-0").exists()


def test_original_gate_20_fault_retry_cases_keep_identity_and_one_action(tmp_path):
    """Original P4 gate: five fault classes, four bounded repetitions each."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    cases = [
        ("timeout", {"status": "FINAL_BLOCK", "promotion_status": "NOT_CREATED", "cleanup_decision": "REMOVED"}, "nexus_self_hosted_retry"),
        ("provider", {"status": "FINAL_BLOCK", "promotion_status": "NOT_CREATED", "cleanup_decision": "REMOVED"}, "nexus_self_hosted_retry"),
        ("verifier", {
            "status": "RETAINED_FOR_REVIEW", "promotion_status": "NOT_CREATED", "cleanup_decision": "REMOVED",
            "verified_receipt": {"verified": True}, "attempt_resolution": {"verdict": "PROVEN"},
        }, "nexus_self_hosted_retry"),
        ("commit", {
            "status": "RETAINED_FOR_REVIEW", "promotion_status": "NOT_CREATED",
            "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES",
        }, "nexus_self_hosted_cleanup"),
        ("integration", {
            "status": "INTEGRATION_FAILED", "promotion_status": "INTEGRATION_FAILED",
            "merge_performed": False, "approved_binding": {"candidate_commit_sha": "a" * 40},
        }, "nexus_self_hosted_retry_integration"),
    ]

    actions = []
    for fault, state, expected_tool in cases:
        for repetition in range(4):
            task_id = f"original-gate-{fault}-{repetition}"
            action = SelfHostedTaskService._task_action_envelope({"task_id": task_id, **state})
            assert action["task_id"] == task_id
            assert action["recommended_tool"] == expected_tool
            assert action["next_action"]
            assert sum(bool(action.get(key)) for key in ("recommended_tool", "next_action")) == 2
            actions.append(action)

    assert len(actions) == 20
    assert len({action["task_id"] for action in actions}) == 20
    assert not (tmp_path / "state").exists()


def test_original_gate_read_p95_stays_below_300ms_without_side_effects(tmp_path, monkeypatch):
    state_root = tmp_path / "state"
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", str(state_root))
    service = SelfHostedTaskService(state_dir=state_root, auto_reconcile=False)
    samples = []

    for _ in range(20):
        started = time.perf_counter()
        service.list_actionable_tasks()
        service.state_root_inventory()
        samples.append((time.perf_counter() - started) * 1000)

    assert sorted(samples)[int(len(samples) * 0.95) - 1] < 300
    assert not state_root.exists()


def test_workspace_apply_requires_exact_plan_binding(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="workspace-apply")
    contract = service.build_contract(request)
    plan = service.workspace_convergence_plan(controller_root=contract.controller_repo_root)

    with pytest.raises(RuntimeError, match="PLAN_HASH_MISMATCH"):
        service.apply_workspace_convergence(
            controller_root=contract.controller_repo_root,
            expected_controller_revision=contract.controller_revision,
            expected_plan_hash="0" * 64,
            apply=True,
        )

    preview = service.apply_workspace_convergence(
        controller_root=contract.controller_repo_root,
        expected_controller_revision=contract.controller_revision,
        expected_plan_hash=plan["plan_hash"],
        apply=False,
    )
    assert preview["applied"] is False
    assert preview["next_gate"] == "EXPLICIT_APPLY"


def test_workspace_slot_prepare_is_idempotent_and_reuses_same_path(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="slot-service")

    first = service.workspace_slot_prepare(request, campaign_id="slot-campaign", slot_index=0)
    second = service.workspace_slot_prepare(request, campaign_id="slot-campaign", slot_index=0)

    assert first["status"] == "READY"
    assert second["status"] == "READY"
    assert first["slot_path"] == second["slot_path"]
    assert Path(first["slot_path"]).exists()


def test_integrated_task_action_envelope_is_terminal(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("integrated", {
        "task_id": "integrated",
        "status": "INTEGRATED",
        "promotion_status": "INTEGRATED",
        "terminal_status": "INTEGRATED",
        "integration_result_sha": "c" * 40,
        "cleanup_decision": "REMOVED",
        "cleanup_performed": True,
    })

    state = service.get_task("integrated")

    assert state["task_action"]["action_state"] == "TERMINAL"
    assert state["task_action"]["attention_required"] is False
    assert state["task_action"]["next_action"] == "none"
    assert state["task_action"]["recommended_tool"] is None


def test_integrating_task_action_envelope_remains_in_progress(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("integrating", {
        "task_id": "integrating",
        "status": "INTEGRATING",
        "promotion_status": "APPROVED",
        "integration_branch": "nexus/integration",
    })

    state = service.get_task("integrating")

    assert state["task_action"]["action_state"] == "IN_PROGRESS"
    assert state["task_action"]["attention_required"] is False
    assert state["task_action"]["recommended_tool"] == "nexus_self_hosted_wait_task"


def test_cancelled_task_records_terminal_cleanup_decision(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("cancel-me", {
        "task_id": "cancel-me", "status": "SUBMITTED", "attempt_id": "a" * 32,
        "worker_pid": None,
    })

    cancelled = service.cancel_task("cancel-me")

    assert cancelled["status"] == "CANCELLED"
    assert cancelled["cleanup_decision"] == "ALREADY_REMOVED"
    assert cancelled["final_disposition"] == "CANCELLED"


def test_default_runner_escalates_after_failed_cheap_worker(tmp_path, monkeypatch):
    calls = []

    class FakeAdapter:
        def __init__(self, provider):
            self.provider = provider

        def preflight(self):
            return WorkerPreflight(
                provider=self.provider,
                executable=f"/bin/{self.provider}",
                executable_available=True,
                authorized=True,
                implementation_status="IMPLEMENTED",
                ready=True,
                reason="ready",
            )

        def invoke(self, contract, lease, *, prompt, **options):
            calls.append(self.provider)
            outcome = WorkerOutcome.FAILED.value if self.provider == "codex" else WorkerOutcome.EXECUTION_COMPLETED.value
            return WorkerExecutionReceipt(
                provider=self.provider,
                task_id=contract.task_id,
                target_worktree=lease.target_worktree,
                worker_status="COMPLETED",
                outcome=outcome,
                exit_code=1 if outcome == WorkerOutcome.FAILED.value else 0,
                executable_identity=f"/bin/{self.provider}",
                argv=(self.provider,),
                stdout_sha256="a" * 64,
                stderr_sha256="b" * 64,
                wall_time_ms=1,
                process_group_id=None,
                process_group_killed=False,
                timed_out=False,
                provider_calls=1,
                evidence_complete=outcome == WorkerOutcome.EXECUTION_COMPLETED.value,
                commit_created=False,
                merge_performed=False,
                push_performed=False,
                failure_reason=None if outcome == WorkerOutcome.EXECUTION_COMPLETED.value else "codex failed",
            )

    registry = WorkerRegistry({provider: FakeAdapter(provider) for provider in ("codex", "gemini", "opencode", "mimo", "ollama")})
    service = SelfHostedTaskService(state_dir=tmp_path / "state", worker_registry=registry, auto_reconcile=False)
    request = _request(tmp_path, worker="codex", fallback_worker="opencode", task_id="escalate-task")
    contract = service.build_contract(request)
    state = {"status": "SUBMITTED", "attempt_id": "a" * 32}
    monkeypatch.setattr(service, "_read_state", lambda task_id: state)

    class FakeManager:
        cleanup_calls = 0

        def __init__(self, root_dir):
            self.root_dir = root_dir

        def verify_controller_unchanged(self, contract, expected_status_sha256=None):
            return expected_status_sha256 or "0" * 64

        def _run_git(self, args, cwd=None):
            return "b" * 40

        def cleanup(self, task_id, force=False):
            FakeManager.cleanup_calls += 1

        def protect_candidate(self, contract, lease, candidate_commit):
            assert state["status"] == "CANDIDATE_COMMITTED"
            assert state["promotion_packet"].candidate_commit_sha == candidate_commit
            return f"refs/nexus-candidates/{contract.task_id}"

        def cleanup_terminal_target(self, contract, lease, **kwargs):
            assert state["status"] == "CANDIDATE_REF_PROTECTED"
            assert state["candidate_ref"] == f"refs/nexus-candidates/{contract.task_id}"
            return SimpleNamespace(decision="REMOVED", blocker=None, performed=True, eligible=True)

    lease_count = 0

    class FakeController:
        def __init__(self, worktree_manager):
            self.worktree_manager = worktree_manager

        def prepare_task(self, contract):
            nonlocal lease_count
            lease_count += 1
            return TargetWorktreeLease(
                schema="nexus.target_worktree_lease.v1",
                lease_id=f"lease-{lease_count}",
                task_id=contract.task_id,
                controller_revision=contract.controller_revision,
                target_base_revision=contract.target_base_revision,
                target_worktree=str(tmp_path / "target"),
                target_branch=f"nexus/task/{contract.task_id}",
                initial_head="b" * 40,
                initial_status_sha256="0" * 64,
                controller_status_sha256="0" * 64,
                created_from_exact_revision=True,
                commit_created=False,
                merge_performed=False,
            )

        def collect_candidate(self, contract, lease):
            return SimpleNamespace(candidate_state_hash="c" * 64, changed_files=["nexus_canary.txt"])

    class FakeVerifier:
        def __init__(self, manager):
            pass

        def verify(self, contract, lease, candidate, protected_paths=None):
            return SimpleNamespace(
                verified=True,
                scope_gate_passed=True,
                deletion_gate_passed=True,
                controller_gate_passed=True,
                protected_contract_gate_passed=True,
                verifier_gate_passed=True,
                failure_reasons=[],
            )

    class FakeCommitter:
        def __init__(self, manager):
            pass

        def create_candidate_commit(self, contract, lease, verified):
            return SimpleNamespace(
                candidate_commit_sha="d" * 40,
                promotion_status="PENDING_HUMAN_APPROVAL",
                candidate_commit_created=True,
                public_claim_allowed=False,
                production_ready=False,
                merge_performed=False,
                push_performed=False,
            )

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", FakeManager)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.SelfHostedDevelopmentController", FakeController)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CandidateVerifier", FakeVerifier)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CandidateCommitter", FakeCommitter)

    def update(status, values):
        state["status"] = status
        state.update(values)

    result = service._run_default_resumable(
        contract,
        request,
        update,
        task_id=contract.task_id,
        attempt_id=state["attempt_id"],
    )

    assert calls == ["codex", "opencode"]
    assert FakeManager.cleanup_calls == 1
    assert lease_count == 2
    assert result["execution"].provider == "opencode"
    assert result["attempt_resolution"].verdict == "PROVEN"


def test_empty_candidate_fails_closed_and_blocks_candidate_commit(tmp_path, monkeypatch):
    class FakeAdapter:
        provider = "codex"

        def preflight(self):
            return WorkerPreflight(
                provider="codex",
                executable="/bin/codex",
                executable_available=True,
                authorized=True,
                implementation_status="IMPLEMENTED",
                ready=True,
                reason="ready",
            )

        def invoke(self, contract, lease, *, prompt, **options):
            return WorkerExecutionReceipt(
                provider="codex",
                task_id=contract.task_id,
                target_worktree=lease.target_worktree,
                worker_status="COMPLETED",
                outcome=WorkerOutcome.EXECUTION_COMPLETED.value,
                exit_code=0,
                executable_identity="/bin/codex",
                argv=("codex",),
                stdout_sha256="a" * 64,
                stderr_sha256="b" * 64,
                wall_time_ms=1,
                process_group_id=None,
                process_group_killed=False,
                timed_out=False,
                provider_calls=1,
                evidence_complete=True,
                commit_created=False,
                merge_performed=False,
                push_performed=False,
            )

    registry = WorkerRegistry({"codex": FakeAdapter(), "gemini": FakeAdapter(), "opencode": FakeAdapter(), "mimo": FakeAdapter(), "ollama": FakeAdapter()})
    service = SelfHostedTaskService(state_dir=tmp_path / "state", worker_registry=registry, auto_reconcile=False)
    request = _request(tmp_path, worker="codex", task_id="empty-cand-task")
    contract = service.build_contract(request)
    checkpoint_history = []
    state = {"status": "SUBMITTED", "attempt_id": "a" * 32}
    monkeypatch.setattr(service, "_read_state", lambda task_id: state)

    class FakeManager:
        def __init__(self, root_dir):
            pass

    class FakeController:
        def __init__(self, worktree_manager):
            pass

        def prepare_task(self, contract):
            return TargetWorktreeLease(
                schema="nexus.target_worktree_lease.v1",
                lease_id="lease-1",
                task_id=contract.task_id,
                controller_revision=contract.controller_revision,
                target_base_revision=contract.target_base_revision,
                target_worktree=str(tmp_path / "target"),
                target_branch="branch",
                initial_head="b" * 40,
                initial_status_sha256="0" * 64,
                controller_status_sha256="0" * 64,
                created_from_exact_revision=True,
                commit_created=False,
                merge_performed=False,
            )

        def collect_candidate(self, contract, lease):
            # empty diff
            return SimpleNamespace(candidate_state_hash="c" * 64, changed_files=[], untracked_files=[], deleted_files=[])

    class FakeVerifier:
        def __init__(self, manager):
            pass

        def verify(self, contract, lease, candidate, protected_paths=None):
            return SimpleNamespace(
                verified=True,
                scope_gate_passed=True,
                deletion_gate_passed=True,
                controller_gate_passed=True,
                protected_contract_gate_passed=True,
                verifier_gate_passed=True,
                failure_reasons=[],
            )

    committer_called = False

    class FakeCommitter:
        def __init__(self, manager):
            pass

        def create_candidate_commit(self, contract, lease, verified):
            nonlocal committer_called
            committer_called = True

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", FakeManager)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.SelfHostedDevelopmentController", FakeController)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CandidateVerifier", FakeVerifier)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CandidateCommitter", FakeCommitter)

    def update(status, values):
        state["status"] = status
        state.update(values)
        checkpoint_history.append((status, values.get("attempt_resolution")))

    with pytest.raises(RuntimeError, match="candidate verification failed: candidate diff is empty"):
        service._run_default_resumable(
            contract,
            request,
            update,
            task_id=contract.task_id,
            attempt_id=state["attempt_id"],
        )

    assert committer_called is False
    verified_checkpoints = [v for s, v in checkpoint_history if s == "VERIFIED"]
    assert len(verified_checkpoints) == 1
    assert verified_checkpoints[0].verdict == "FAILED"
    assert verified_checkpoints[0].candidate_non_empty is False


def test_legacy_proven_outcome_fails_closed_in_service(tmp_path, monkeypatch):
    class FakeAdapter:
        provider = "codex"

        def preflight(self):
            return WorkerPreflight(
                provider="codex",
                executable="/bin/codex",
                executable_available=True,
                authorized=True,
                implementation_status="IMPLEMENTED",
                ready=True,
                reason="ready",
            )

        def invoke(self, contract, lease, *, prompt, **options):
            return WorkerExecutionReceipt(
                provider="codex",
                task_id=contract.task_id,
                target_worktree=lease.target_worktree,
                worker_status="COMPLETED",
                outcome=WorkerOutcome.PROVEN.value,
                exit_code=0,
                executable_identity="/bin/codex",
                argv=("codex",),
                stdout_sha256="a" * 64,
                stderr_sha256="b" * 64,
                wall_time_ms=1,
                process_group_id=None,
                process_group_killed=False,
                timed_out=False,
                provider_calls=1,
                evidence_complete=True,
                commit_created=False,
                merge_performed=False,
                push_performed=False,
            )

    registry = WorkerRegistry({provider: FakeAdapter() for provider in ("codex", "gemini", "opencode", "mimo", "ollama")})
    service = SelfHostedTaskService(state_dir=tmp_path / "state", worker_registry=registry, auto_reconcile=False)
    request = _request(tmp_path, worker="codex", task_id="legacy-proven-task")
    contract = service.build_contract(request)
    checkpoint_history = []
    state = {"status": "SUBMITTED", "attempt_id": "a" * 32}
    monkeypatch.setattr(service, "_read_state", lambda task_id: state)

    class FakeManager:
        def __init__(self, root_dir):
            pass

    class FakeController:
        def __init__(self, worktree_manager):
            pass

        def prepare_task(self, contract):
            return TargetWorktreeLease(
                schema="nexus.target_worktree_lease.v1",
                lease_id="lease-1",
                task_id=contract.task_id,
                controller_revision=contract.controller_revision,
                target_base_revision=contract.target_base_revision,
                target_worktree=str(tmp_path / "target"),
                target_branch="branch",
                initial_head="b" * 40,
                initial_status_sha256="0" * 64,
                controller_status_sha256="0" * 64,
                created_from_exact_revision=True,
                commit_created=False,
                merge_performed=False,
            )

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", FakeManager)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.SelfHostedDevelopmentController", FakeController)

    def update(status, values):
        state["status"] = status
        state.update(values)
        checkpoint_history.append((status, values.get("attempt_resolution")))

    with pytest.raises(RuntimeError):
        service._run_default_resumable(
            contract,
            request,
            update,
            task_id=contract.task_id,
            attempt_id=state["attempt_id"],
        )

    verified_checkpoints = [v for s, v in checkpoint_history if s == "VERIFIED"]
    assert len(verified_checkpoints) == 0


def test_close_retained_without_candidate_success_with_missing_target(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "retained-no-candidate-001"
    target_path = tmp_path / "targets" / task_id
    assert not target_path.exists()

    state = {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": task_id,
        "status": "RETAINED_FOR_REVIEW",
        "submitted_at": "2026-07-28T10:00:00+00:00",
        "status_history": [{"status": "RETAINED_FOR_REVIEW", "at": "2026-07-28T10:00:00+00:00"}],
        "request": _request(tmp_path, task_id=task_id),
        "contract": service.build_contract(_request(tmp_path, task_id=task_id)).model_dump(mode="json"),
        "target_worktree": str(target_path),
        "controller_worktree": str(tmp_path / "controller"),
        "attempt_id": "att-001",
        "promotion_status": "NOT_CREATED",
        "worker_pid": None,
        "execution": {"provider": "codex", "outcome": "EXECUTION_FAILED"},
        "error": "worker crashed before candidate",
        "cleanup_decision": "REMOVED",
        "cleanup_eligible": True,
        "cleanup_performed": True,
        "cleanup_performed_at": "2026-07-28T10:05:00+00:00",
        "state_retention_status": "TERMINAL",
        "archive_eligible": False,
    }
    service._write_state(task_id, state)

    result = service.close_retained_without_candidate(task_id, superseded_by="ref-evidence-456")

    assert result["status"] == "SUPERSEDED"
    assert result["final_disposition"] == "SUPERSEDED"
    assert result["terminal_status"] == "SUPERSEDED"
    assert result["state_retention_status"] == "TERMINAL"
    assert result["archive_eligible"] is True
    assert result["merge_performed"] is False
    assert result["push_performed"] is False
    assert result["superseded_by"] == "ref-evidence-456"
    assert result["promotion_status"] == "NOT_CREATED"
    assert result["execution"] == {"provider": "codex", "outcome": "EXECUTION_FAILED"}
    assert result["error"] == "worker crashed before candidate"
    assert result["cleanup_decision"] == "REMOVED"
    assert result["cleanup_eligible"] is True
    assert result["cleanup_performed"] is True
    assert result["cleanup_performed_at"] == "2026-07-28T10:05:00+00:00"

    archive_result = service.archive_states(dry_run=False)
    assert any(entry["task_id"] == task_id for entry in archive_result["entries"])


def test_close_retained_without_candidate_accepts_hash_only_diagnostics(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "retained-no-candidate-hash-only"
    target_path = tmp_path / "targets" / task_id
    assert not target_path.exists()

    state = {
        "task_id": task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "target_worktree": str(target_path),
        "candidate_state_hash": "c" * 64,
        "verified_receipt_hash": "d" * 64,
        "verified_receipt": {"candidate_state_hash": "c" * 64},
        "candidate": {"candidate_state_hash": "c" * 64, "commit_created": False},
        "promotion_packet": None,
        "candidate_commit_sha": None,
        "candidate_ref": None,
        "candidate_commit_created": False,
    }
    service._write_state(task_id, state)

    result = service.close_retained_without_candidate(
        task_id,
        superseded_by="integration:hash-only-diagnostics-covered",
    )

    assert result["status"] == "SUPERSEDED"
    assert result["promotion_status"] == "NOT_CREATED"
    assert result["superseded_by"] == "integration:hash-only-diagnostics-covered"
    assert result["merge_performed"] is False
    assert result["push_performed"] is False


def test_close_retained_without_candidate_fails_closed_missing_superseded_by(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "retained-no-candidate-002"
    state = {
        "task_id": task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "target_worktree": str(tmp_path / "nonexistent"),
    }
    service._write_state(task_id, state)

    with pytest.raises(ValueError, match="superseded_by"):
        service.close_retained_without_candidate(task_id, superseded_by="")

    with pytest.raises(ValueError, match="superseded_by"):
        service.close_retained_without_candidate(task_id, superseded_by="   ")


def test_close_retained_without_candidate_fails_closed_wrong_status(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "retained-no-candidate-003"
    state = {
        "task_id": task_id,
        "status": "FINAL_BLOCK",
        "promotion_status": "NOT_CREATED",
        "target_worktree": str(tmp_path / "nonexistent"),
    }
    service._write_state(task_id, state)

    with pytest.raises(RuntimeError, match="RETAINED_FOR_REVIEW"):
        service.close_retained_without_candidate(task_id, superseded_by="ref-123")


def test_close_retained_without_candidate_fails_closed_candidate_present(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "retained-no-candidate-004"
    state = {
        "task_id": task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "PENDING_HUMAN_APPROVAL",
        "candidate_commit_sha": "a" * 40,
        "target_worktree": str(tmp_path / "nonexistent"),
    }
    service._write_state(task_id, state)

    with pytest.raises(RuntimeError):
        service.close_retained_without_candidate(task_id, superseded_by="ref-123")


def test_close_retained_without_candidate_fails_closed_active_process(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "retained-no-candidate-005"
    state = {
        "task_id": task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "worker_pid": 12345,
        "target_worktree": str(tmp_path / "nonexistent"),
    }
    service._write_state(task_id, state)

    monkeypatch.setattr(service, "_pid_alive", staticmethod(lambda pid: True))

    with pytest.raises(RuntimeError, match="active worker process"):
        service.close_retained_without_candidate(task_id, superseded_by="ref-123")


def test_close_retained_without_candidate_fails_closed_active_child_pgid(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "retained-no-candidate-005b"
    state = {
        "task_id": task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "worker_pid": None,
        "worker_child_pgid": 54321,
        "target_worktree": str(tmp_path / "nonexistent"),
    }
    service._write_state(task_id, state)

    monkeypatch.setattr(service, "_pid_alive", staticmethod(lambda pid: True))

    with pytest.raises(RuntimeError, match="active worker child process"):
        service.close_retained_without_candidate(task_id, superseded_by="ref-123")


def test_close_retained_without_candidate_fails_closed_existing_dirty_target(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "retained-no-candidate-006"
    target_dir = tmp_path / "targets" / task_id
    target_dir.mkdir(parents=True)
    (target_dir / "dirty.txt").write_text("unsaved work")

    state = {
        "task_id": task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "target_worktree": str(target_dir),
    }
    service._write_state(task_id, state)

    with pytest.raises(RuntimeError, match="Target path exists"):
        service.close_retained_without_candidate(task_id, superseded_by="ref-123")


def test_close_retained_dirty_salvage_requires_integrated_replacement(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    request = _real_request(tmp_path, task_id="retained-salvage-gated")
    contract = service.build_contract(request)
    from nexus.orchestrator.worktree_manager import WorktreeManager
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "dirty.txt").write_text("verifier side effect\n", encoding="utf-8")
    service._write_state(request["task_id"], {
        "task_id": request["task_id"],
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "target_worktree": str(target),
        "attempt_id": "attempt-salvage-gated",
        "worker_pid": None,
        "worker_child_pgid": None,
    })

    with pytest.raises(RuntimeError, match="superseded_by must name"):
        service.close_retained_without_candidate(
            request["task_id"], superseded_by="missing-integrated-task"
        )

    assert target.exists()
    assert (target / "dirty.txt").exists()
    assert service._read_state(request["task_id"])["status"] == "RETAINED_FOR_REVIEW"


def test_close_retained_clean_target_uses_archived_integrated_replacement(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    request = _real_request(tmp_path, task_id="retained-clean-target")
    contract = service.build_contract(request)
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    replacement_id = "workspace-convergence-retained-without-candidate-closure-hardening"
    service._write_state(replacement_id, {
        "task_id": replacement_id,
        "status": "INTEGRATED",
        "promotion_status": "INTEGRATED",
        "integration_result_sha": "i" * 40,
    })
    service.archive_states(dry_run=False)
    service._write_state(request["task_id"], {
        "task_id": request["task_id"],
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "target_worktree": str(lease.target_worktree),
        "attempt_id": "attempt-retained-clean-target",
        "worker_pid": None,
        "worker_child_pgid": None,
    })

    result = service.close_retained_without_candidate(
        request["task_id"], superseded_by=replacement_id
    )

    assert result["status"] == "SUPERSEDED"
    assert result["superseded_by"] == replacement_id
    assert result["cleanup_decision"] == "REMOVED"
    assert result["cleanup_performed"] is True
    assert not Path(lease.target_worktree).exists()


def test_close_retained_dirty_salvage_rejects_mismatched_replacement_identity(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    request = _real_request(tmp_path, task_id="retained-salvage-identity-gated")
    contract = service.build_contract(request)
    from nexus.orchestrator.worktree_manager import WorktreeManager
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "dirty.txt").write_text("must remain untouched\n", encoding="utf-8")
    replacement_id = "integrated-replacement-requested"
    service._write_state(replacement_id, {
        "task_id": "different-integrated-task",
        "status": "INTEGRATED",
        "promotion_status": "INTEGRATED",
        "integration_result_sha": "i" * 40,
    })
    service._write_state(request["task_id"], {
        "task_id": request["task_id"],
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "target_worktree": str(target),
        "attempt_id": "attempt-salvage-identity-gated",
        "worker_pid": None,
        "worker_child_pgid": None,
    })

    controller = Path(request["controller_repo_root"])
    refs_before = _git(controller, "show-ref")
    worktrees_before = _git(controller, "worktree", "list", "--porcelain")

    with pytest.raises(RuntimeError, match="superseded_by must name"):
        service.close_retained_without_candidate(
            request["task_id"], superseded_by=replacement_id
        )

    assert target.exists()
    assert (target / "dirty.txt").read_text(encoding="utf-8") == "must remain untouched\n"
    assert _git(controller, "show-ref") == refs_before
    assert _git(
        controller,
        "for-each-ref",
        "--format=%(refname)",
        "refs/nexus-salvage/worktree/",
    ) == ""
    assert _git(controller, "worktree", "list", "--porcelain") == worktrees_before
    assert service._read_state(request["task_id"])["status"] == "RETAINED_FOR_REVIEW"


def test_close_retained_dirty_salvage_protects_ref_and_never_becomes_candidate(tmp_path, monkeypatch):
    for env_var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(env_var, raising=False)
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    request = _real_request(tmp_path, task_id="retained-salvage-success")
    contract = service.build_contract(request)
    from nexus.orchestrator.worktree_manager import WorktreeManager
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "README").write_text("dirty verifier state\n", encoding="utf-8")
    (target / "untracked.txt").write_text("complete salvage\n", encoding="utf-8")
    replacement_id = "integrated-replacement"
    service._write_state(replacement_id, {
        "task_id": replacement_id,
        "status": "INTEGRATED",
        "promotion_status": "INTEGRATED",
        "integration_result_sha": "i" * 40,
    })
    service._write_state(request["task_id"], {
        "task_id": request["task_id"],
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "target_worktree": str(target),
        "attempt_id": "attempt-salvage-success",
        "worker_pid": None,
        "worker_child_pgid": None,
    })

    result = service.close_retained_without_candidate(
        request["task_id"], superseded_by=replacement_id
    )

    salvage_commit = result["salvage_commit_sha"]
    salvage_ref = result["salvage_ref"]
    controller = Path(request["controller_repo_root"])
    assert result["status"] == "SUPERSEDED"
    assert result["promotion_status"] == "NOT_CREATED"
    assert result["salvage_only"] is True
    assert result["promotion_eligible"] is False
    assert result["superseded_by"] == replacement_id
    assert result.get("candidate_commit_sha") is None
    assert result.get("candidate_ref") is None
    assert result.get("promotion_packet") is None
    assert not target.exists()
    assert _git(controller, "rev-parse", salvage_ref) == salvage_commit
    assert _git(controller, "show", "-s", "--format=%an", salvage_commit) == "Nexus Salvage Bot"
    assert _git(controller, "show", "-s", "--format=%ae", salvage_commit) == "nexus-salvage-bot@nexus.local"
    assert _git(controller, "show", "-s", "--format=%s", salvage_commit) == (
        "Nexus Salvage Bot: salvage-only snapshot retained-salvage-success/attempt-salvage-success"
    )
    assert _git(controller, "show", f"{salvage_commit}:untracked.txt") == "complete salvage"


def test_close_retained_dirty_salvage_ref_mismatch_keeps_target_and_task_retained(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    request = _real_request(tmp_path, task_id="retained-salvage-ref-failure")
    contract = service.build_contract(request)
    from nexus.orchestrator.worktree_manager import WorktreeManager
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "dirty.txt").write_text("must remain\n", encoding="utf-8")
    replacement_id = "integrated-replacement-ref-failure"
    service._write_state(replacement_id, {
        "task_id": replacement_id,
        "status": "INTEGRATED",
        "promotion_status": "INTEGRATED",
        "integration_result_sha": "r" * 40,
    })
    service._write_state(request["task_id"], {
        "task_id": request["task_id"],
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "target_worktree": str(target),
        "attempt_id": "attempt-salvage-ref-failure",
        "worker_pid": None,
        "worker_child_pgid": None,
    })
    original = WorktreeManager.create_salvage_snapshot

    def mismatched_ref(self, contract, lease, attempt_id):
        snapshot = original(self, contract, lease, attempt_id)
        return {**snapshot, "salvage_ref": snapshot["salvage_ref"] + "-mismatch"}

    monkeypatch.setattr(WorktreeManager, "create_salvage_snapshot", mismatched_ref)

    result = service.close_retained_without_candidate(
        request["task_id"], superseded_by=replacement_id
    )

    assert result["status"] == "RETAINED_FOR_REVIEW"
    assert result["cleanup_decision"] == "BLOCKED_BY_MISSING_REF"
    assert result["salvage_only"] is True
    assert result["promotion_eligible"] is False
    assert target.exists()
    assert result["promotion_status"] == "NOT_CREATED"
    assert result.get("candidate_commit_sha") is None
    assert result.get("candidate_ref") is None


def test_close_task_without_candidate_final_block_success(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "final-block-no-candidate-001"
    target_path = tmp_path / "targets" / task_id
    assert not target_path.exists()

    state = {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": task_id,
        "status": "FINAL_BLOCK",
        "submitted_at": "2026-07-28T10:00:00+00:00",
        "status_history": [{"status": "FINAL_BLOCK", "at": "2026-07-28T10:00:00+00:00"}],
        "request": _request(tmp_path, task_id=task_id),
        "contract": service.build_contract(_request(tmp_path, task_id=task_id)).model_dump(mode="json"),
        "target_worktree": str(target_path),
        "controller_worktree": str(tmp_path / "controller"),
        "attempt_id": "att-001",
        "promotion_status": "NOT_CREATED",
        "worker_pid": None,
        "execution": {"provider": "codex", "outcome": "EXECUTION_FAILED"},
        "error": "worker crashed without producing candidate",
        "cleanup_decision": "REMOVED",
        "cleanup_eligible": True,
        "cleanup_performed": True,
        "cleanup_performed_at": "2026-07-28T10:05:00+00:00",
        "state_retention_status": "TERMINAL",
        "archive_eligible": False,
    }
    service._write_state(task_id, state)

    actionable_before = service.list_actionable_tasks()
    assert not any(t["task_id"] == task_id for t in actionable_before["tasks"])

    result = service.close_task_without_candidate(task_id, superseded_by="ref-evidence-789")

    assert result["status"] == "SUPERSEDED"
    assert result["final_disposition"] == "SUPERSEDED"
    assert result["terminal_status"] == "SUPERSEDED"
    assert result["state_retention_status"] == "TERMINAL"
    assert result["archive_eligible"] is True
    assert result["superseded_by"] == "ref-evidence-789"
    assert result["promotion_status"] == "NOT_CREATED"

    actionable_after = service.list_actionable_tasks()
    assert not any(t["task_id"] == task_id for t in actionable_after["tasks"])


def test_close_task_without_candidate_retained_for_review_success(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "retained-gen-no-candidate-001"
    target_path = tmp_path / "targets" / task_id
    assert not target_path.exists()

    state = {
        "task_id": task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "target_worktree": str(target_path),
    }
    service._write_state(task_id, state)

    result = service.close_task_without_candidate(task_id, superseded_by="ref-gen-123")

    assert result["status"] == "SUPERSEDED"
    assert result["superseded_by"] == "ref-gen-123"


def test_close_task_without_candidate_fails_closed_other_status(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "other-status-no-candidate-001"
    state = {
        "task_id": task_id,
        "status": "SUBMITTED",
        "promotion_status": "NOT_CREATED",
        "target_worktree": str(tmp_path / "nonexistent"),
    }
    service._write_state(task_id, state)

    with pytest.raises(RuntimeError, match="RETAINED_FOR_REVIEW or FINAL_BLOCK"):
        service.close_task_without_candidate(task_id, superseded_by="ref-123")


# --- 00c: Self-hosted Retained Target Auto Closeout RED tests ---

def test_cleanup_retained_dirty_target_salvages_and_removes(tmp_path, monkeypatch):
    """RED: retained dirty Target currently remains registered after cleanup_tasks(..., dry_run=False)."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="retained-dirty-cleanup")
    contract = service.build_contract(request)
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "dirty.txt").write_text("dirty work\n", encoding="utf-8")
    for env_var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(env_var, raising=False)
    service._write_state(contract.task_id, {
        "task_id": contract.task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "attempt_id": "att-retained-dirty",
        "worker_pid": None,
        "worker_child_pgid": None,
    })

    result = service.cleanup_tasks(task_id=contract.task_id, dry_run=False)
    decision = result["decisions"][0]
    state_after = service._read_state(contract.task_id)

    assert decision["cleanup_decision"] != "BLOCKED_BY_UNSAVED_CHANGES", (
        "retained dirty Target should not be blocked by unsaved changes when salvage is available"
    )
    assert decision["cleanup_performed"] is True
    assert not target.exists(), "Target worktree should be removed after salvage"
    assert state_after["status"] == "RETAINED_FOR_REVIEW"
    assert state_after.get("salvage_commit_sha") is not None
    assert state_after.get("salvage_ref") is not None


def test_cleanup_retained_clean_changed_head_salvages_head_and_removes(tmp_path):
    """RED: retained clean changed-HEAD Target currently remains registered without a durable binding."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="retained-clean-head-cleanup")
    contract = service.build_contract(request)
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    _git(target, "config", "user.name", "Test")
    _git(target, "config", "user.email", "test@example.com")
    _git(target, "commit", "--allow-empty", "-m", "drift")
    assert _git(target, "rev-parse", "HEAD") != lease.initial_head
    service._write_state(contract.task_id, {
        "task_id": contract.task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "attempt_id": "att-retained-clean-head",
        "worker_pid": None,
        "worker_child_pgid": None,
    })

    result = service.cleanup_tasks(task_id=contract.task_id, dry_run=False)
    decision = result["decisions"][0]

    assert decision["cleanup_performed"] is True
    assert not target.exists()


def test_cleanup_retained_discover_existing_salvage_ref(tmp_path, monkeypatch):
    """RED: existing exact salvage ref currently is not discovered when state metadata is absent."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="retained-existing-salvage")
    contract = service.build_contract(request)
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "dirty.txt").write_text("salvage me\n", encoding="utf-8")
    for env_var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(env_var, raising=False)
    attempt_id = "att-existing-salvage"
    snapshot = manager.create_salvage_snapshot(contract, lease, attempt_id)
    salvage_ref = snapshot["salvage_ref"]
    salvage_commit = snapshot["salvage_commit_sha"]
    service._write_state(contract.task_id, {
        "task_id": contract.task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "attempt_id": attempt_id,
        "worker_pid": None,
        "worker_child_pgid": None,
    })

    result = service.cleanup_tasks(task_id=contract.task_id, dry_run=False)
    decision = result["decisions"][0]
    state_after = service._read_state(contract.task_id)

    assert decision["cleanup_performed"] is True
    assert not target.exists()
    assert state_after["status"] == "RETAINED_FOR_REVIEW"
    assert state_after.get("salvage_commit_sha") == salvage_commit
    assert state_after.get("salvage_ref") == salvage_ref


def test_cleanup_retained_active_process_preserves_target(tmp_path, monkeypatch):
    """RED: active process must not allow Target removal."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="retained-active-process")
    contract = service.build_contract(request)
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    service._write_state(contract.task_id, {
        "task_id": contract.task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "attempt_id": "att-retained-active",
        "worker_pid": 12345,
        "worker_child_pgid": None,
    })
    monkeypatch.setattr(SelfHostedTaskService, "_pid_alive", staticmethod(lambda pid: True))

    result = service.cleanup_tasks(task_id=contract.task_id, dry_run=False)
    decision = result["decisions"][0]

    assert decision["cleanup_performed"] is False
    assert target.exists()


def test_cleanup_retained_dry_run_does_not_mutate_state(tmp_path, monkeypatch):
    """RED: dry-run currently cannot describe a salvage-and-remove plan because retained tasks are rejected."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="retained-dry-run")
    contract = service.build_contract(request)
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    for env_var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(env_var, raising=False)
    service._write_state(contract.task_id, {
        "task_id": contract.task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "attempt_id": "att-retained-dry-run",
        "worker_pid": None,
        "worker_child_pgid": None,
    })

    result = service.cleanup_tasks(task_id=contract.task_id, dry_run=True)
    decision = result["decisions"][0]
    state_after = service._read_state(contract.task_id)

    assert decision["cleanup_performed"] is False
    assert target.exists(), "dry-run must not remove Target"
    assert state_after.get("salvage_commit_sha") is None, "dry-run must not create salvage"
    assert state_after.get("salvage_ref") is None, "dry-run must not record salvage ref"


def test_cleanup_dry_run_reads_snapshot_without_state_lock(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "cleanup-dry-run-lock-free"
    service._write_state(task_id, {
        "task_id": task_id,
        "status": "FINAL_BLOCK",
        "promotion_status": "NOT_CREATED",
        "cleanup_decision": "REMOVED",
    })
    service._lock_path().unlink()

    def fail_lock():
        raise AssertionError("cleanup dry-run must not acquire the state lock")

    monkeypatch.setattr(service, "_state_lock", fail_lock)
    result = service.cleanup_tasks(task_id=task_id, dry_run=True)

    assert result["decisions"][0]["cleanup_decision"] == "ALREADY_REMOVED"
    assert not service._lock_path().exists()


# ---------- LC2: terminal failure restore wiring tests ----------


class _FailingRunner:
    """Runner that raises to trigger the terminal-failure exception handler."""

    def __init__(self, exc: Exception = None):
        self._exc = exc or RuntimeError("deliberate terminal failure")

    def __call__(self, contract, request, update):
        raise self._exc


def _setup_lc2_task(tmp_path, service, task_id):
    """Create a real task with lease for LC2 testing."""
    request = _real_request(tmp_path, task_id=task_id)
    contract = service.build_contract(request)
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    attempt_id = "att-" + task_id
    service._write_state(task_id, {
        "task_id": task_id,
        "status": "LEASED",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash,
        "lease": lease.__dict__,
        "attempt_id": attempt_id,
        "worker_pid": None,
        "worker_child_pgid": None,
    })
    return contract, lease, attempt_id


def test_run_owned_task_terminal_failure_calls_restore(tmp_path, monkeypatch):
    """Happy path: salvage + cleanup REMOVED → restore called with RESTORED."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "lc2-restore"
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    restore_called = {"n": 0}

    class SpyManager:
        def __init__(self, root_dir):
            pass

        def cleanup_terminal_target(self, contract, lease, **kw):
            if kw.get("salvage_commit"):
                return SimpleNamespace(decision="REMOVED", blocker=None, performed=True, eligible=True)
            return SimpleNamespace(decision="BLOCKED_BY_UNSAVED_CHANGES", blocker="dirty", performed=False, eligible=True)

        def create_salvage_snapshot(self, contract, lease, attempt_id):
            return {"salvage_commit_sha": "c" * 40, "salvage_ref": "refs/nexus-salvages/lc2-restore"}

        def restore_task_branch_for_retry(self, contract, lease, salvage_commit, salvage_ref):
            restore_called["n"] += 1
            assert salvage_commit == "c" * 40
            return {"decision": "RESTORED", "restored_to": "b" * 40}

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", SpyManager)
    service._custom_runner = _FailingRunner()
    # Directly invoke _run_owned_task (bypasses submit_task lease creation)
    service._run_owned_task(task_id, attempt_id)

    state = service._read_state(task_id)
    assert restore_called["n"] == 1
    assert state["task_branch_restore_decision"] == "RESTORED"
    assert state["task_branch_restored_to"] == "b" * 40
    assert state["task_branch_restore_performed"] is True
    assert state["task_branch_restore_verified"] is True
    assert state["salvage_commit_sha"] == "c" * 40
    assert state["salvage_ref"] == "refs/nexus-salvages/lc2-restore"


def test_run_owned_task_terminal_failure_already_restored(tmp_path, monkeypatch):
    """Second failure: restore sees ALREADY_RESTORED → state recorded, no mutation."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "lc2-already-restored"
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    restore_calls = {"n": 0}

    class SpyManager:
        def __init__(self, root_dir):
            pass

        def cleanup_terminal_target(self, contract, lease, **kw):
            if kw.get("salvage_commit"):
                return SimpleNamespace(decision="REMOVED", blocker=None, performed=True, eligible=True)
            return SimpleNamespace(decision="BLOCKED_BY_UNSAVED_CHANGES", blocker="dirty", performed=False, eligible=True)

        def create_salvage_snapshot(self, contract, lease, attempt_id):
            return {"salvage_commit_sha": "c" * 40, "salvage_ref": "refs/nexus-salvages/lc2-already-restored"}

        def restore_task_branch_for_retry(self, contract, lease, salvage_commit, salvage_ref):
            restore_calls["n"] += 1
            return {"decision": "ALREADY_RESTORED", "restored_to": "b" * 40}

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", SpyManager)
    service._custom_runner = _FailingRunner()
    service._run_owned_task(task_id, attempt_id)

    state = service._read_state(task_id)
    assert restore_calls["n"] == 1
    assert state["task_branch_restore_decision"] == "ALREADY_RESTORED"
    assert state["salvage_commit_sha"] == "c" * 40


def test_run_owned_task_terminal_failure_restored_with_state_writeback(tmp_path, monkeypatch):
    """Verify all six state fields are written after RESTORED."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "lc2-writeback"
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    class SpyManager:
        def __init__(self, root_dir):
            pass

        def cleanup_terminal_target(self, contract, lease, **kw):
            if kw.get("salvage_commit"):
                return SimpleNamespace(decision="REMOVED", blocker=None, performed=True, eligible=True)
            return SimpleNamespace(decision="BLOCKED_BY_UNSAVED_CHANGES", blocker="dirty", performed=False, eligible=True)

        def create_salvage_snapshot(self, contract, lease, attempt_id):
            return {"salvage_commit_sha": "c" * 40, "salvage_ref": "refs/nexus-salvages/lc2-wb"}

        def restore_task_branch_for_retry(self, contract, lease, salvage_commit, salvage_ref):
            return {"decision": "RESTORED", "restored_to": "b" * 40}

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", SpyManager)
    service._custom_runner = _FailingRunner()
    service._run_owned_task(task_id, attempt_id)

    state = service._read_state(task_id)
    for key in ("task_branch_restore_decision", "task_branch_restored_to",
                 "task_branch_restore_performed", "task_branch_restore_verified",
                 "salvage_commit_sha", "salvage_ref"):
        assert key in state and state[key] is not None, f"missing or None: {key}"
    assert state["task_branch_restore_performed"] is True
    assert state["task_branch_restore_verified"] is True


def test_run_owned_task_terminal_failure_restore_failure(tmp_path, monkeypatch):
    """restore_task_branch_for_retry raises → RESTORE_BLOCKED, RETAINED_FOR_REVIEW."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "lc2-restore-fail"
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    class SpyManager:
        def __init__(self, root_dir):
            pass

        def cleanup_terminal_target(self, contract, lease, **kw):
            if kw.get("salvage_commit"):
                return SimpleNamespace(decision="REMOVED", blocker=None, performed=True, eligible=True)
            return SimpleNamespace(decision="BLOCKED_BY_UNSAVED_CHANGES", blocker="dirty", performed=False, eligible=True)

        def create_salvage_snapshot(self, contract, lease, attempt_id):
            return {"salvage_commit_sha": "c" * 40, "salvage_ref": "refs/nexus-salvages/lc2-rf"}

        def restore_task_branch_for_retry(self, contract, lease, salvage_commit, salvage_ref):
            raise RuntimeError("restore validation failed: bad parent")

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", SpyManager)
    service._custom_runner = _FailingRunner()
    service._run_owned_task(task_id, attempt_id)

    state = service._read_state(task_id)
    assert state["task_branch_restore_decision"] == "RESTORE_BLOCKED"
    assert state["task_branch_restore_performed"] is False
    assert state["task_branch_restore_verified"] is False
    assert state["terminal_status"] == "RETAINED_FOR_REVIEW"


def test_run_owned_task_terminal_failure_salvage_failure(tmp_path, monkeypatch):
    """create_salvage_snapshot raises → CLEANUP_BLOCKED, no restore called."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "lc2-salvage-fail"
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    restore_called = {"n": 0}

    class SpyManager:
        def __init__(self, root_dir):
            pass

        def cleanup_terminal_target(self, contract, lease, **kw):
            return SimpleNamespace(decision="BLOCKED_BY_UNSAVED_CHANGES", blocker="dirty", performed=False, eligible=True)

        def create_salvage_snapshot(self, contract, lease, attempt_id):
            raise RuntimeError("git snapshot failed: permission denied")

        def restore_task_branch_for_retry(self, contract, lease, salvage_commit, salvage_ref):
            restore_called["n"] += 1
            return {"decision": "RESTORED", "restored_to": "b" * 40}

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", SpyManager)
    service._custom_runner = _FailingRunner()
    service._run_owned_task(task_id, attempt_id)

    state = service._read_state(task_id)
    assert state["cleanup_decision"] == "CLEANUP_BLOCKED"
    assert "permission denied" in state["cleanup_blocker"]
    assert restore_called["n"] == 0
    assert state.get("task_branch_restore_decision") is None


def test_run_owned_task_terminal_failure_cleanup_blocked(tmp_path, monkeypatch):
    """cleanup_terminal_target raises → CLEANUP_BLOCKED, no restore."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "lc2-cleanup-blocked"
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    restore_called = {"n": 0}

    class SpyManager:
        def __init__(self, root_dir):
            pass

        def cleanup_terminal_target(self, contract, lease, **kw):
            raise RuntimeError("cleanup failed: git lock held")

        def create_salvage_snapshot(self, contract, lease, attempt_id):
            return {"salvage_commit_sha": "c" * 40, "salvage_ref": "refs/nexus-salvages/lc2-cb"}

        def restore_task_branch_for_retry(self, contract, lease, salvage_commit, salvage_ref):
            restore_called["n"] += 1
            return {"decision": "RESTORED", "restored_to": "b" * 40}

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", SpyManager)
    service._custom_runner = _FailingRunner()
    service._run_owned_task(task_id, attempt_id)

    state = service._read_state(task_id)
    assert state["cleanup_decision"] == "CLEANUP_BLOCKED"
    assert "git lock" in state["cleanup_blocker"]
    assert restore_called["n"] == 0


def test_run_owned_task_terminal_failure_no_lease(tmp_path, monkeypatch):
    """No lease in state → no cleanup, no restore, FINAL_BLOCK."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="lc2-no-lease")
    task_id = request["task_id"]
    service._write_state(task_id, {
        "task_id": task_id,
        "status": "SUBMITTED",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "attempt_id": "att-no-lease",
        "worker_pid": None,
        "worker_child_pgid": None,
        # no lease
    })

    service._custom_runner = _FailingRunner()
    service._run_owned_task(task_id, "att-no-lease")

    state = service._read_state(task_id)
    assert state["status"] == "FINAL_BLOCK"
    assert state["terminal_status"] == "FINAL_BLOCK"
    assert state.get("cleanup_decision") == "ALREADY_REMOVED"
    assert state.get("task_branch_restore_decision") is None


def test_run_owned_task_terminal_failure_restore_already_restored_with_state(tmp_path, monkeypatch):
    """ALREADY_RESTORED with salvage metadata written by a prior run → state fields consistent."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "lc2-ar-state"
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    # Simulate prior run already wrote salvage metadata
    service._write_state(task_id, {
        **service._read_state(task_id),
        "salvage_commit_sha": "c" * 40,
        "salvage_ref": "refs/nexus-salvages/lc2-ar-state",
        "task_branch_restored_to": "b" * 40,
        "task_branch_restore_decision": "RESTORED",
    })

    class SpyManager:
        def __init__(self, root_dir):
            pass

        def cleanup_terminal_target(self, contract, lease, **kw):
            if kw.get("salvage_commit"):
                return SimpleNamespace(decision="REMOVED", blocker=None, performed=True, eligible=True)
            return SimpleNamespace(decision="BLOCKED_BY_UNSAVED_CHANGES", blocker="dirty", performed=False, eligible=True)

        def create_salvage_snapshot(self, contract, lease, attempt_id):
            return {"salvage_commit_sha": "c" * 40, "salvage_ref": "refs/nexus-salvages/lc2-ar-state"}

        def restore_task_branch_for_retry(self, contract, lease, salvage_commit, salvage_ref):
            return {"decision": "ALREADY_RESTORED", "restored_to": "b" * 40}

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", SpyManager)
    service._custom_runner = _FailingRunner()
    service._run_owned_task(task_id, attempt_id)

    state = service._read_state(task_id)
    assert state["task_branch_restore_decision"] == "ALREADY_RESTORED"
    assert state["salvage_commit_sha"] == "c" * 40
    assert state["salvage_ref"] == "refs/nexus-salvages/lc2-ar-state"
    assert state["task_branch_restored_to"] == "b" * 40


# ---------- LC3: Real timeout / salvage / retry canary ----------




def test_lc3_service_path_canary(tmp_path, monkeypatch):
    """LC3: Formal service-path canary for timeout/salvage/retry.

    Flow through formal service path:
    1. Pre-set state with SUBMITTED + lease pointing to real Target worktree
    2. Custom runner creates dirty mutation in allowed path, raises timeout
    3. _run_default_resumable exception propagates to _run_owned_task handler
    4. Exception handler: salvage commit/ref → cleanup REMOVED → restore → terminal
    5. Retry with refreshed revision → new attempt, detached Target

    Prohibited: manual create_salvage_snapshot, cleanup_terminal_target,
    restore_task_branch_for_retry, _write_state to manufacture terminal receipt.
    """
    # --- Phase 1: Real controller and target repos ---
    controller = tmp_path / "controller"
    controller.mkdir()
    _init_repo(controller)
    _git(controller, "config", "user.name", "LC3 Service Test")
    _git(controller, "config", "user.email", "lc3-svc@test.com")
    (controller / "README").write_text("base\n")
    _git(controller, "add", "README")
    _git(controller, "commit", "-m", "base commit")
    base_sha = _git(controller, "rev-parse", "HEAD")

    target_root = tmp_path / "targets"
    target_root.mkdir()

    request = {
        "task_id": "lc3-svc-canary",
        "what": "lc3 service path canary",
        "why": "prove formal exception path",
        "controller_revision": base_sha,
        "target_base_revision": base_sha,
        "controller_repo_root": str(controller),
        "target_repo_root": str(target_root / "lc3-svc-canary"),
        "target_worktree_root": str(target_root),
        "allowed_files": ["src/"],
        "forbidden_files": [],
        "verifier_commands": [],
        "protected_contracts": [],
        "worker": "codex",
    }

    # --- Phase 2: Create real lease (worktree) via WorktreeManager ---
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    manager = WorktreeManager(root_dir=str(target_root))
    contract = service.build_contract(request)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    assert target.exists(), "Target worktree must exist after real lease"

    # --- Phase 3: Pre-set state with SUBMITTED + lease ---
    attempt_id = "attempt-1-lc3-svc"
    service._write_state("lc3-svc-canary", {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": "lc3-svc-canary",
        "status": "WORKER_RUNNING",
        "submitted_at": "2026-01-01T00:00:00Z",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash,
        "controller_worktree": str(controller),
        "controller_revision": base_sha,
        "target_worktree": str(target),
        "target_branch": f"nexus/task/lc3-svc-canary",
        "attempt_id": attempt_id,
        "attempts": [{"attempt_id": attempt_id, "started_at": "2026-01-01T00:00:00Z"}],
        "lease": lease.__dict__,
        "worker_pid": None,
        "worker_child_pgid": None,
        "active_provider": "codex",
        "promotion_status": "NOT_CREATED",
        "execution_lane": "FAST_LANE",
        "fast_lane_eligible": True,
        "maximum_provider_calls": 1,
        "maximum_replans": 0,
        "fallback_disabled": True,
    })

    # --- Phase 4: Custom runner creates dirty mutation + raises timeout ---
    def timeout_runner(contract_arg, request_arg, update_fn):
        # Make dirty mutation in the allowed path
        src = target / "src"
        src.mkdir(exist_ok=True)
        (src / "worker.txt").write_text("dirty mutation\n", encoding="utf-8")
        raise RuntimeError("worker timeout: execution exceeded deadline")

    service._custom_runner = timeout_runner

    # --- Phase 5: Execute via _run_owned_task (formal exception path) ---
    service._run_owned_task("lc3-svc-canary", attempt_id)

    # --- Phase 6: Verify terminal state set by exception handler ---
    state = service._read_state("lc3-svc-canary")
    assert state is not None, "state must exist after exception handler"

    # Exception handler should have run salvage + cleanup + restore
    salvage_commit = state.get("salvage_commit_sha")
    salvage_ref = state.get("salvage_ref")
    assert salvage_commit, "salvage_commit_sha must be set by exception handler"
    assert salvage_ref, "salvage_ref must be set by exception handler"

    # Salvage ref resolves to salvage commit in controller
    resolved_salvage = _git(controller, "rev-parse", salvage_ref)
    assert resolved_salvage == salvage_commit, "salvage ref must resolve to salvage commit"

    # Cleanup decision
    cleanup_decision = state.get("cleanup_decision")
    assert cleanup_decision in {"REMOVED", "ALREADY_REMOVED"}, \
        f"cleanup must succeed, got {cleanup_decision}"

    # Restore decision
    restore_decision = state.get("task_branch_restore_decision")
    assert restore_decision in {"RESTORED", "ALREADY_RESTORED"}, \
        f"restore must succeed, got {restore_decision}"

    # Terminal status
    terminal_status = state.get("terminal_status")
    assert terminal_status in {"FINAL_BLOCK", "RETAINED_FOR_REVIEW"}, \
        f"terminal status must be set, got {terminal_status}"

    # Target no longer exists or is detached
    target_still_registered = False
    try:
        registered = manager._registered_worktrees(controller)
        target_still_registered = any(
            "worktree" in e and Path(e["worktree"]).resolve() == target.resolve()
            for e in registered
        )
    except Exception:
        pass
    assert not target_still_registered, "Target must not be registered after cleanup"

    # --- Phase 7: Revision-forward retry reactivates the task and permits a detached Target ---
    first_attempt_id = state["attempt_id"]
    (controller / "refreshed.txt").write_text("refreshed revision\n", encoding="utf-8")
    _git(controller, "add", "refreshed.txt")
    _git(controller, "commit", "-m", "refresh integration revision")
    refreshed_sha = _git(controller, "rev-parse", "HEAD")
    refreshed_request = {
        **request,
        "controller_revision": refreshed_sha,
        "target_base_revision": refreshed_sha,
    }

    # Keep the retry at SUBMITTED so the test can inspect the physical lease deterministically.
    monkeypatch.setattr(
        service,
        "_launch_worker",
        lambda task_id, attempt_id: service._read_state(task_id),
    )
    retried = service.submit_task(refreshed_request)
    assert retried["attempt_id"] != first_attempt_id
    assert retried["status"] == "SUBMITTED"

    refreshed_contract = service.build_contract(refreshed_request)
    retry_lease = manager.create_lease(refreshed_contract)
    assert retry_lease.target_detached is True
    assert retry_lease.initial_head == refreshed_sha
    assert Path(retry_lease.target_worktree).exists()


# ---------- W0: Read-only verification entrypoint tests ----------


def test_verify_task_returns_state_missing_for_unknown_task(tmp_path):
    """W0: verify_task returns STATE_MISSING for non-existent task."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    result = service.verify_task("nonexistent")
    assert result["verdict"] == "STATE_MISSING"
    assert result["verified"] is False
    assert "state_not_found" in result["failure_reasons"]
    assert result["provider_calls"] == 0


def test_verify_task_passes_for_valid_task(tmp_path):
    """W0: verify_task passes for a valid task with clean state."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="verify-valid")
    task_id = request["task_id"]
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    # Add a simple verifier command
    contract_data = service._read_state(task_id).get("contract", {})
    contract_data["verifier_commands"] = ["echo pass"]
    service._write_state(task_id, {
        **service._read_state(task_id),
        "contract": contract_data,
    })

    result = service.verify_task(task_id)
    assert result["verdict"] == "VERIFIED"
    assert result["verified"] is True
    assert result["provider_calls"] == 0
    assert result["failure_reasons"] == []
    assert result["state_intact"] is True
    assert "verifier_commands_executed" in result
    assert result["next_action"] == "wait_for_task"
    assert result["recommended_tool"] == "nexus_self_hosted_wait_task"


def test_verify_task_detects_state_hash_drift(tmp_path):
    """W0: verify_task detects contract hash drift between reads."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="verify-drift")
    task_id = request["task_id"]
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    # Tamper with state between reads
    original_read = service._read_state_snapshot
    call_count = {"n": 0}
    def tampering_read(task_id):
        state = original_read(task_id)
        call_count["n"] += 1
        if call_count["n"] == 2 and state:
            # Second read: tamper with contract_hash
            state = {**state, "contract_hash": "tampered"}
        return state
    service._read_state_snapshot = tampering_read

    result = service.verify_task(task_id)
    assert result["verified"] is False
    assert "contract_hash_drift" in result["failure_reasons"]


def test_verify_task_detects_attempt_drift(tmp_path):
    """W0: verify_task detects attempt ID drift between reads."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="verify-attempt-drift")
    task_id = request["task_id"]
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    # Tamper with attempt_id between reads
    original_read = service._read_state_snapshot
    call_count = {"n": 0}
    def tampering_read(task_id):
        state = original_read(task_id)
        call_count["n"] += 1
        if call_count["n"] == 2 and state:
            state = {**state, "attempt_id": "tampered_attempt"}
        return state
    service._read_state_snapshot = tampering_read

    result = service.verify_task(task_id)
    assert result["verified"] is False
    assert "attempt_drift" in result["failure_reasons"]


def test_verify_task_detects_state_deletion(tmp_path):
    """W0: verify_task detects state deletion between reads."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="verify-deleted")
    task_id = request["task_id"]
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    # Delete state between reads
    original_read = service._read_state_snapshot
    call_count = {"n": 0}
    def deleting_read(task_id):
        state = original_read(task_id)
        call_count["n"] += 1
        if call_count["n"] == 2:
            return None
        return state
    service._read_state_snapshot = deleting_read

    result = service.verify_task(task_id)
    assert result["verified"] is False
    assert "state_deleted_between_reads" in result["failure_reasons"]


def test_verify_task_no_state_mutation(tmp_path):
    """W0: verify_task does not modify task state."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="verify-no-mutate")
    task_id = request["task_id"]
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    state_before = service._read_state(task_id)
    result = service.verify_task(task_id)
    state_after = service._read_state(task_id)

    # State must be identical
    assert state_before == state_after, "verify_task must not mutate state"
    assert result["verified"] is True


def test_verify_task_repeated_calls_consistent(tmp_path):
    """W0: repeated verify calls on same state produce consistent verdict."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="verify-consistent")
    task_id = request["task_id"]
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    result_1 = service.verify_task(task_id)
    result_2 = service.verify_task(task_id)

    assert result_1["verdict"] == result_2["verdict"]
    assert result_1["verified"] == result_2["verified"]
    assert result_1["failure_reasons"] == result_2["failure_reasons"]
    assert result_1["provider_calls"] == result_2["provider_calls"]


def test_verify_task_no_commit_no_push_no_cleanup(tmp_path):
    """W0: verify_task must not commit, push, approve, integrate, or cleanup."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="verify-no-ops")
    task_id = request["task_id"]
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    # Record git state before
    controller = Path(contract.controller_repo_root)
    commits_before = _git(controller, "rev-parse", "HEAD")

    result = service.verify_task(task_id)

    # Git state must be unchanged
    commits_after = _git(controller, "rev-parse", "HEAD")
    assert commits_before == commits_after, "verify must not commit"
    assert result["verified"] is True


def test_verify_task_fails_on_missing_target(tmp_path):
    """W0: verify_task fails when target worktree is missing."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="verify-no-target")
    task_id = request["task_id"]
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    # Remove target worktree
    import shutil
    target_path = Path(lease.target_worktree)
    if target_path.exists():
        shutil.rmtree(target_path)

    result = service.verify_task(task_id)
    assert result["verified"] is False
    assert "target_missing" in result["failure_reasons"]
    assert result["next_action"] == "wait_for_task"


def test_verify_task_fails_closed_when_verifier_mutates_target(tmp_path, monkeypatch):
    """A verifier-created file must invalidate the read-only verification."""
    monkeypatch.setenv("NEXUS_TARGET_ROOT_OVERRIDE", str(tmp_path / "targets"))
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    request = _real_request(tmp_path, task_id="verify-target-mutation")
    request["verifier_commands"] = [
        "python3 -c \"from pathlib import Path; "
        "Path('verifier-artifact.txt').write_text('created')\""
    ]
    contract = service.build_contract(request)
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    attempt_id = "att-verify-target-mutation"
    service._write_state(contract.task_id, {
        "task_id": contract.task_id,
        "status": "LEASED",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash,
        "lease": lease.__dict__,
        "attempt_id": attempt_id,
        "worker_pid": None,
        "worker_child_pgid": None,
    })

    result = service.verify_task(contract.task_id)

    assert Path(lease.target_worktree, "verifier-artifact.txt").exists()
    assert result["verified"] is False, result
    assert "target_digest_drift_during_verification" in result["failure_reasons"]


# ---------- W1: End-to-end fast lane canary ----------


def test_w1_service_path_canary(tmp_path):
    """W1: Formal service-path canary for the owner-controlled happy path.

    Flow through formal service path:
    1. submit_task creates durable task state
    2. _run_default_resumable creates the real Target lease
    3. Mock worker makes bounded mutation and returns EXECUTION_COMPLETED
    4. CandidateVerifier -> commit -> durable ref -> cleanup
    5. Final state: PENDING_HUMAN_APPROVAL, cleanup REMOVED

    Prohibited: manual commit, manual protect candidate ref, manual _write_state
    to force candidate status, BLOCKED_BY_UNSAVED_CHANGES as success.
    """
    # --- Phase 1: Real controller and target repos ---
    controller = tmp_path / "controller"
    controller.mkdir()
    _init_repo(controller)
    _git(controller, "config", "user.name", "W1 Service Test")
    _git(controller, "config", "user.email", "w1-svc@test.com")
    (controller / "README").write_text("base\n")
    _git(controller, "add", "README")
    _git(controller, "commit", "-m", "base commit")
    base_sha = _git(controller, "rev-parse", "HEAD")

    target_root = tmp_path / "targets"
    target_root.mkdir()

    # Verifier command that always passes
    verifier_script = tmp_path / "verify.sh"
    verifier_script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    verifier_script.chmod(0o755)

    request = {
        "task_id": "w1-svc-canary",
        "what": "w1 service path canary",
        "why": "prove formal happy path",
        "controller_revision": base_sha,
        "target_base_revision": base_sha,
        "controller_repo_root": str(controller),
        "target_repo_root": str(target_root / "w1-svc-canary"),
        "target_worktree_root": str(target_root),
        "allowed_files": ["src/"],
        "forbidden_files": [],
        "verifier_commands": [f"/bin/sh {verifier_script}"],
        "protected_contracts": [],
        "worker": "codex",
    }

    # --- Phase 2: Configure a deterministic worker and run submit_task inline ---
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    manager = WorktreeManager(root_dir=str(target_root))

    from unittest.mock import MagicMock

    observed_target: dict[str, Path] = {}

    def mock_invoke(provider, contract_arg, lease_arg, *, prompt, **kwargs):
        target_path = Path(lease_arg.target_worktree)
        observed_target["path"] = target_path
        src = target_path / "src"
        src.mkdir(exist_ok=True)
        (src / "canary.txt").write_text("worker bounded mutation\n", encoding="utf-8")
        return WorkerExecutionReceipt(
            provider=provider,
            task_id=contract_arg.task_id,
            target_worktree=str(target_path),
            worker_status="completed",
            outcome=WorkerOutcome.EXECUTION_COMPLETED.value,
            exit_code=0,
            executable_identity="mock-codex",
            argv=("mock-codex",),
            stdout_sha256="a" * 64,
            stderr_sha256="b" * 64,
            wall_time_ms=100,
            process_group_id=os.getpid(),
            process_group_killed=False,
            timed_out=False,
            provider_calls=1,
            evidence_complete=True,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
        )

    service.worker_registry = MagicMock()
    service.worker_registry.invoke = mock_invoke
    service.worker_registry.preflight.return_value = WorkerPreflight(
        provider="codex",
        executable="mock-codex",
        executable_available=True,
        authorized=True,
        implementation_status="ready",
        ready=True,
        reason=None,
    )

    def launch_inline(task_id, attempt_id):
        service._run_owned_task(task_id, attempt_id)
        return service._read_state(task_id)

    service._launch_worker = launch_inline
    submitted = service.submit_task(request)

    # --- Phase 3: Verify final state written by the full submit/owner path ---
    state = service._read_state("w1-svc-canary")
    assert submitted["status"] == "PENDING_HUMAN_APPROVAL"
    lease = TargetWorktreeLease(**state["lease"])
    target = Path(lease.target_worktree)
    assert observed_target["path"] == target
    assert state is not None, "state must exist"
    assert state.get("terminal_status") == "PENDING_HUMAN_APPROVAL", \
        f"must reach PENDING_HUMAN_APPROVAL, got {state.get('terminal_status')}"
    assert state.get("candidate_status") == "PENDING_HUMAN_APPROVAL"
    assert state.get("cleanup_decision") == "REMOVED", \
        f"cleanup must be REMOVED, got {state.get('cleanup_decision')}"

    # --- Phase 7: Verify candidate commit and ref ---
    candidate_ref = state.get("candidate_ref")
    packet = state.get("promotion_packet") or {}
    candidate_commit = packet.get("candidate_commit_sha")
    assert candidate_ref, "candidate_ref must be set"
    assert candidate_commit, "candidate_commit_sha must be set"

    resolved_ref = _git(controller, "rev-parse", candidate_ref)
    assert resolved_ref == candidate_commit, "candidate ref must resolve to candidate commit"

    # --- Phase 8: Verify Target removed ---
    assert not target.exists(), "Target worktree must be removed after cleanup"

    target_registered = False
    try:
        registered = manager._registered_worktrees(controller)
        target_registered = any(
            "worktree" in e and Path(e["worktree"]).resolve() == target.resolve()
            for e in registered
        )
    except Exception:
        pass
    assert not target_registered, "Target must not be registered after cleanup"

    # --- Phase 9: Verify durable verified receipt present ---
    verified_receipt = state.get("verified_receipt") or {}
    assert verified_receipt.get("verified") is True, "receipt must be verified"
    assert state.get("candidate_commit_sha") == candidate_commit
    assert state.get("candidate_ref") == candidate_ref
    assert state.get("status") == "PENDING_HUMAN_APPROVAL"
    assert state.get("promotion_status") == "PENDING_HUMAN_APPROVAL"

    # --- Phase 10: W0 must verify the protected Candidate after Target cleanup ---
    read_only_verification = service.verify_task("w1-svc-canary")
    assert read_only_verification["verified"] is True, read_only_verification
    assert read_only_verification["verdict"] == "VERIFIED"
    assert read_only_verification["verification_mode"] == "durable_candidate_receipt"
    assert read_only_verification["provider_calls"] == 0
    assert read_only_verification["verifier_commands_executed"] == []

    # A recreated path at the old Target location must not switch verification back
    # to mutable Target mode after durable cleanup.
    target.mkdir(parents=True)
    (target / "untrusted.txt").write_text("not authoritative\n", encoding="utf-8")
    recreated_target_result = service.verify_task("w1-svc-canary")
    assert recreated_target_result["verified"] is True, recreated_target_result
    assert recreated_target_result["verification_mode"] == "durable_candidate_receipt"
    assert recreated_target_result["provider_calls"] == 0
    shutil.rmtree(target)

    # --- Phase 11: Governance invariants ---
    assert state.get("merge_performed") is not True, "no auto merge"
    assert state.get("push_performed") is not True, "no auto push"
    assert state.get("approved_binding") is None, "no auto approval"
    assert state.get("public_claim_allowed") is not True, "no auto public claim"
    assert state.get("production_ready") is not True, "no auto production ready"

    # --- Phase 12: Verify verified receipt details ---
    assert verified_receipt.get("scope_gate_passed") is True, "scope gate must pass"
    assert verified_receipt.get("deletion_gate_passed") is True, "deletion gate must pass"
    assert verified_receipt.get("controller_gate_passed") is True, "controller gate must pass"
    assert verified_receipt.get("verifier_gate_passed") is True, "verifier gate must pass"
    assert verified_receipt.get("public_claim_allowed") is False, "public claim must not be allowed"
    assert verified_receipt.get("production_ready") is False, "must not be production ready"

    # --- Phase 13: Durable verification must fail closed on ref or receipt tamper ---
    original_state = service._read_state("w1-svc-canary")

    target.mkdir(parents=True)
    (target / "recreated.txt").write_text("untrusted replacement\n", encoding="utf-8")
    missing_binding = copy.deepcopy(original_state)
    missing_binding["candidate_commit_sha"] = None
    missing_binding["candidate_tree_sha"] = None
    missing_binding["candidate_ref"] = None
    missing_binding["candidate_state_hash"] = None
    missing_binding["verified_receipt_hash"] = None
    missing_binding["promotion_packet"] = {}
    service._write_state("w1-svc-canary", missing_binding)
    missing_binding_result = service.verify_task("w1-svc-canary")
    assert missing_binding_result["verified"] is False
    assert "durable_candidate_binding_missing" in missing_binding_result["failure_reasons"]
    shutil.rmtree(target)

    tampered_ref = copy.deepcopy(original_state)
    tampered_ref["candidate_ref"] = "refs/heads/main"
    service._write_state("w1-svc-canary", tampered_ref)
    tampered_ref_result = service.verify_task("w1-svc-canary")
    assert tampered_ref_result["verified"] is False
    assert "candidate_ref_namespace_invalid" in tampered_ref_result["failure_reasons"]

    tampered_hash = copy.deepcopy(original_state)
    tampered_hash["promotion_packet"]["verified_receipt_hash"] = "0" * 64
    tampered_hash["verified_receipt_hash"] = "0" * 64
    service._write_state("w1-svc-canary", tampered_hash)
    tampered_hash_result = service.verify_task("w1-svc-canary")
    assert tampered_hash_result["verified"] is False
    assert "verified_receipt_hash_mismatch" in tampered_hash_result["failure_reasons"]


def _bound_action_request(tmp_path: Path, **overrides):
    bound = _request(tmp_path, task_id="bound-action-task")
    bound.update(overrides)
    return bound


def _action_transport(
    bound: dict,
    *,
    action_type=LifecycleActionType.TASK_RUN,
    attempt_id="attempt-bound-1",
    action_id="action-bound-1",
    idempotency_key="idempotency-bound-1",
    **outer_overrides,
):
    contract_kind = ContractKind(str(bound.get("contract_kind") or ContractKind.NONE.value))
    physical_bound = {
        **bound,
        "attempt_id": attempt_id,
        "action_id": action_id,
        "idempotency_key": idempotency_key,
        "action_type": action_type.value,
        "contract_kind": contract_kind.value,
    }
    action = build_action_envelope(
        task_id=str(physical_bound["task_id"]),
        action_type=action_type,
        request=physical_bound,
        tool_manifest_hash="a" * 64,
        expected_head=physical_bound.get("controller_revision"),
        allowed_paths=tuple(physical_bound.get("allowed_files") or ()),
        mutation=False,
        task_card_path=physical_bound.get("task_card_path"),
        task_card_hash=physical_bound.get("task_card_hash"),
        contract_kind=contract_kind,
        contract_hash=physical_bound.get("contract_hash"),
        attempt_id=attempt_id,
        action_id=action_id,
        idempotency_key=idempotency_key,
    ).model_dump(mode="json")
    transport = {
        **physical_bound,
        "action": action,
        "bound_action_request": dict(physical_bound),
        "action_id": action["action_id"],
        "attempt_id": action["attempt_id"],
        "idempotency_key": action["idempotency_key"],
        "action_request_hash": action["request_hash"],
    }
    transport.update(outer_overrides)
    return transport


def test_action_transport_tampered_bound_payload_fails_before_task_resolution(tmp_path, monkeypatch):
    bound = _bound_action_request(tmp_path)
    transport = _action_transport(bound)
    transport["bound_action_request"]["what"] = "tampered"
    service = SelfHostedTaskService(state_dir=tmp_path / "state", ephemeral=True)
    monkeypatch.setattr(service, "_resolve_current_execution_task_id", lambda *_: pytest.fail("task resolution ran"))

    with pytest.raises(ValueError, match="BOUND_ACTION_REQUEST_HASH_MISMATCH"):
        service.submit_task(transport)


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("task_id", "outer-task"),
        ("attempt_id", "outer-attempt"),
        ("action_id", "outer-action"),
        ("idempotency_key", "outer-key"),
        ("controller_revision", "f" * 40),
        ("allowed_files", ["other.py"]),
        ("task_card_path", "tasks/other.md"),
        ("task_card_hash", "e" * 64),
        ("contract_kind", ContractKind.OWNER_INLINE.value),
        ("contract_hash", "d" * 64),
    ],
)
def test_action_transport_outer_identity_overrides_fail_before_state_access(
    tmp_path,
    monkeypatch,
    field,
    tampered,
):
    bound = _bound_action_request(tmp_path)
    transport = _action_transport(bound)
    transport[field] = tampered
    service = SelfHostedTaskService(state_dir=tmp_path / "state", ephemeral=True)
    monkeypatch.setattr(service, "_workspace_task_states", lambda: pytest.fail("state access ran"))

    with pytest.raises(ValueError, match="ACTION_IDENTITY_MISMATCH"):
        service.submit_task(transport)


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("attempt_id", "attempt-envelope-tamper"),
        ("action_id", "action-envelope-tamper"),
        ("idempotency_key", "envelope-key-tamper"),
        ("expected_head", None),
        ("allowed_paths", []),
        ("contract_hash", "d" * 64),
    ],
)
def test_action_transport_envelope_identity_tamper_fails_before_state_access(
    tmp_path,
    monkeypatch,
    field,
    tampered,
):
    bound = _bound_action_request(
        tmp_path,
        contract_kind=ContractKind.TRACKED_TASK_CARD.value,
        task_card_path="tasks/campaign/card.md",
        task_card_hash="b" * 64,
        contract_hash="c" * 64,
    )
    transport = _action_transport(bound)
    transport["action"][field] = tampered
    service = SelfHostedTaskService(state_dir=tmp_path / "state", ephemeral=True)
    monkeypatch.setattr(service, "_workspace_task_states", lambda: pytest.fail("state access ran"))

    with pytest.raises(ValueError, match="ACTION_IDENTITY_MISMATCH"):
        service.submit_task(transport)


def test_action_transport_requires_mapping_bound_payload_before_state_access(tmp_path, monkeypatch):
    bound = _bound_action_request(tmp_path)
    transport = _action_transport(bound, bound_action_request=[("task_id", bound["task_id"])])
    service = SelfHostedTaskService(state_dir=tmp_path / "state", ephemeral=True)
    monkeypatch.setattr(service, "_workspace_task_states", lambda: pytest.fail("state access ran"))

    with pytest.raises(ValueError, match="BOUND_ACTION_REQUEST_REQUIRED"):
        service.submit_task(transport)


def test_task_retry_action_cannot_create_a_new_semantic_task(tmp_path, monkeypatch):
    bound = _bound_action_request(tmp_path, task_id="unknown-retry-task")
    transport = _action_transport(
        bound,
        action_type=LifecycleActionType.TASK_RETRY,
        attempt_id="attempt-retry-1",
        action_id="action-retry-1",
        idempotency_key="unknown-retry-task:retry-1",
    )
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    monkeypatch.setattr(service, "_launch_worker", lambda *_: pytest.fail("worker launch ran"))

    with pytest.raises(ValueError, match="RETRY_REQUIRES_EXISTING_TASK"):
        service.submit_task(transport)

    assert service._read_state_snapshot(bound["task_id"]) is None


def test_task_retry_action_type_cannot_be_tampered_to_task_run(tmp_path, monkeypatch):
    bound = _bound_action_request(tmp_path, task_id="retry-action-type-tamper")
    transport = _action_transport(
        bound,
        action_type=LifecycleActionType.TASK_RETRY,
        attempt_id="attempt-retry-type",
        action_id="action-retry-type",
        idempotency_key="retry-action-type-tamper:retry-1",
    )
    transport["action"]["action_type"] = LifecycleActionType.TASK_RUN.value
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    monkeypatch.setattr(service, "_workspace_task_states", lambda: pytest.fail("state access ran"))

    with pytest.raises(ValueError, match="ACTION_IDENTITY_MISMATCH: action_type"):
        service.submit_task(transport)


@pytest.mark.parametrize(
    "missing_field",
    ["task_id", "attempt_id", "action_id", "idempotency_key", "action_type", "contract_kind"],
)
def test_action_transport_requires_identity_inside_bound_payload(tmp_path, monkeypatch, missing_field):
    bound = _bound_action_request(tmp_path, task_id="missing-bound-action-type")
    transport = _action_transport(bound)
    transport["bound_action_request"].pop(missing_field)
    transport["action"]["request_hash"] = canonical_request_hash(transport["bound_action_request"])
    transport["action_request_hash"] = transport["action"]["request_hash"]
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    monkeypatch.setattr(service, "_workspace_task_states", lambda: pytest.fail("state access ran"))

    with pytest.raises(ValueError, match=f"ACTION_IDENTITY_MISSING: {missing_field}"):
        service.submit_task(transport)


@pytest.mark.parametrize(
    ("missing_field", "identity_name"),
    [
        ("controller_revision", "expected_head"),
        ("allowed_files", "allowed_paths"),
        ("task_card_path", "task_card_path"),
        ("task_card_hash", "task_card_hash"),
        ("contract_hash", "contract_hash"),
    ],
)
def test_action_transport_requires_scope_and_contract_inside_bound_payload(
    tmp_path,
    monkeypatch,
    missing_field,
    identity_name,
):
    bound = _bound_action_request(
        tmp_path,
        task_id="missing-bound-scope",
        contract_kind=ContractKind.TRACKED_TASK_CARD.value,
        task_card_path="tasks/campaign/card.md",
        task_card_hash="b" * 64,
        contract_hash="c" * 64,
    )
    transport = _action_transport(bound)
    transport["bound_action_request"].pop(missing_field)
    transport["action"]["request_hash"] = canonical_request_hash(transport["bound_action_request"])
    transport["action_request_hash"] = transport["action"]["request_hash"]
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    monkeypatch.setattr(service, "_workspace_task_states", lambda: pytest.fail("state access ran"))

    with pytest.raises(ValueError, match=f"ACTION_IDENTITY_MISSING: {identity_name}"):
        service.submit_task(transport)


@pytest.mark.parametrize(
    "retry_change",
    [
        {"what": "different semantic task"},
        {"allowed_files": ["different.py"]},
    ],
)
def test_task_retry_action_cannot_change_semantic_task_or_scope(tmp_path, retry_change):
    def runner(contract, request, update):
        update("FINAL_BLOCK", {"cleanup_decision": "REMOVED", "cleanup_performed": True})
        return {"promotion_status": "NOT_CREATED"}

    bound = _bound_action_request(tmp_path, task_id="bound-retry-task")
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        runner=runner,
        auto_reconcile=False,
        ephemeral=True,
    )
    service.submit_task(_action_transport(bound))
    assert _wait_for_status(service, bound["task_id"], "FINAL_BLOCK")

    changed = {**bound, **retry_change}
    transport = _action_transport(
        changed,
        action_type=LifecycleActionType.TASK_RETRY,
        attempt_id="attempt-retry-2",
        action_id="action-retry-2",
        idempotency_key="bound-retry-task:retry-2",
    )
    with pytest.raises(ValueError, match="RETRY_SEMANTIC_TASK_MISMATCH"):
        service.submit_task(transport)


def test_task_retry_action_requires_fresh_attempt_scoped_identity(tmp_path):
    def runner(contract, request, update):
        update("FINAL_BLOCK", {"cleanup_decision": "REMOVED", "cleanup_performed": True})
        return {"promotion_status": "NOT_CREATED"}

    bound = _bound_action_request(tmp_path, task_id="stale-retry-identity")
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        runner=runner,
        auto_reconcile=False,
        ephemeral=True,
    )
    service.submit_task(_action_transport(bound))
    assert _wait_for_status(service, bound["task_id"], "FINAL_BLOCK")

    stale = _action_transport(
        bound,
        action_type=LifecycleActionType.TASK_RETRY,
        attempt_id="attempt-bound-1",
        action_id="action-stale-retry",
        idempotency_key="stale-retry-identity:retry-stale",
    )
    with pytest.raises(ValueError, match="RETRY_ATTEMPT_ID_REUSED"):
        service.submit_task(stale)


@pytest.mark.parametrize(
    "action_type",
    [
        LifecycleActionType.TASK_FINISH,
        LifecycleActionType.CANDIDATE_APPROVE,
        LifecycleActionType.CANDIDATE_INTEGRATE,
        LifecycleActionType.CANDIDATE_DISPOSE,
    ],
)
def test_task_submission_rejects_cross_domain_action_types_before_state_access(
    tmp_path,
    monkeypatch,
    action_type,
):
    bound = _bound_action_request(tmp_path)
    transport = _action_transport(bound)
    transport["action"]["action_type"] = action_type.value
    service = SelfHostedTaskService(state_dir=tmp_path / "state", ephemeral=True)
    monkeypatch.setattr(service, "_workspace_task_states", lambda: pytest.fail("state access ran"))

    with pytest.raises(ValueError, match="ACTION_TYPE_UNSUPPORTED_FOR_TASK_SUBMISSION"):
        service.submit_task(transport)


def test_action_transport_uses_bound_payload_and_preserves_card_contract_identity(tmp_path):
    bound = _bound_action_request(
        tmp_path,
        execution_lane="ISOLATED_TARGET",
        task_card_path="tasks/campaign/card.md",
        task_card_hash="b" * 64,
        contract_kind=ContractKind.TRACKED_TASK_CARD.value,
        contract_hash="c" * 64,
    )
    transport = _action_transport(bound, what="untrusted outer copy")
    seen = []

    def fake_runner(contract, request, update):
        seen.append(dict(request))
        return {"promotion_status": "PENDING_HUMAN_APPROVAL", "candidate_commit_created": False}

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        runner=fake_runner,
        ephemeral=True,
        auto_reconcile=False,
    )
    result = service.submit_task(transport)
    _wait_for_status(service, result["task_id"], "PENDING_HUMAN_APPROVAL")

    executed = seen[0]
    durable = service._read_state(result["task_id"])
    assert executed["what"] == bound["what"]
    assert executed["task_id"] == bound["task_id"]
    assert executed["attempt_id"] == transport["action"]["attempt_id"]
    assert executed["action_id"] == transport["action"]["action_id"]
    assert executed["controller_revision"] == transport["action"]["expected_head"]
    assert executed["allowed_files"] == transport["action"]["allowed_paths"]
    assert executed["task_card_hash"] == bound["task_card_hash"]
    assert executed["contract_hash"] == bound["contract_hash"]
    assert durable["attempt_id"] == transport["action"]["attempt_id"]
    assert durable["action_id"] == transport["action"]["action_id"]
    assert durable["idempotency_key"] == transport["action"]["idempotency_key"]


def test_m3c_build_contract_maps_all_four_execution_ceilings(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    contract = service.build_contract(_request(
        tmp_path,
        maximum_attempts_per_task=2,
        maximum_wall_time_seconds=17.5,
        maximum_changed_files=4,
        maximum_deleted_files=3,
    ))
    assert contract.maximum_attempts_per_task == 2
    assert contract.maximum_wall_time_seconds == 17.5
    assert contract.maximum_changed_files == 4
    assert contract.maximum_deleted_files == 3


def test_m3c_retry_attempt_cap_blocks_before_durable_append_or_launch(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="m3c-attempt-cap")
    request["maximum_attempts_per_task"] = 1
    contract = service.build_contract(request)
    original = {
        "task_id": request["task_id"], "status": "FINAL_BLOCK", "terminal_status": "FINAL_BLOCK",
        "cleanup_decision": "REMOVED", "promotion_status": "NOT_CREATED", "acceptance_decision": "NOT_REPAIRABLE",
        "request": request, "contract": contract.model_dump(mode="json"), "attempt_id": "old-attempt",
        "attempts": [{"attempt_id": "old-attempt"}],
    }
    service._write_state(request["task_id"], original)
    monkeypatch.setattr(service, "_launch_worker", lambda *_: pytest.fail("launch must not run"))
    result = service.retry_task(request["task_id"])
    assert result["retry"]["blocker"] == "ATTEMPT_BUDGET_EXHAUSTED"
    assert service._read_state(request["task_id"])["attempts"] == original["attempts"]


def _m3c_receipt(task_id, target, *, calls=1, attempts=1):
    return WorkerExecutionReceipt(
        provider="codex", task_id=task_id, target_worktree=str(target), worker_status="completed",
        outcome=WorkerOutcome.EXECUTION_COMPLETED.value, exit_code=0, executable_identity="fake",
        argv=("fake",), stdout_sha256="a" * 64, stderr_sha256="b" * 64, wall_time_ms=1,
        process_group_id=None, process_group_killed=False, timed_out=False, provider_calls=calls,
        provider_attempt_count=attempts, evidence_complete=True, commit_created=False,
        merge_performed=False, push_performed=False,
    )


def test_m3c_aggregate_provider_budget_blocks_before_extra_invoke(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, "m3c-provider-cap")
    state = service._read_state(contract.task_id)
    prior = _m3c_receipt(contract.task_id, lease.target_worktree)
    state.update({"status": "WORKER_RUNNING", "active_provider": "codex", "attempts": [{"attempt_id": attempt_id}],
                  "executions": [prior.__dict__], "maximum_provider_calls": 1})
    service._write_state(contract.task_id, state)
    calls = {"invoke": 0}
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CandidateVerifier",
                        SimpleNamespace(validate_static_contract=lambda *_: None))
    monkeypatch.setattr(service.worker_registry, "invoke", lambda *a, **k: calls.__setitem__("invoke", calls["invoke"] + 1))
    with pytest.raises(RuntimeError, match="maximum_provider_calls aggregate budget exhausted"):
        service._run_default_resumable(contract, state["request"], lambda *_: None,
                                       task_id=contract.task_id, attempt_id=attempt_id)
    assert calls["invoke"] == 0


def test_m3c_absolute_deadline_passes_remaining_timeout_and_blocks_overrun(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, "m3c-deadline")
    request = {**service._read_state(contract.task_id)["request"], "maximum_wall_time_seconds": 1.0,
               "timeout_seconds": 9.0}
    contract = service.build_contract(request)
    state = service._read_state(contract.task_id)
    state.update({"status": "WORKER_RUNNING", "active_provider": "codex", "submitted_at": "1970-01-01T00:01:40+00:00",
                  "contract": contract.model_dump(mode="json"), "request": request,
                  "attempts": [{"attempt_id": attempt_id}], "executions": []})
    service._write_state(contract.task_id, state)
    observed = {}
    clock = {"now": 100.0}
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.time.time", lambda: clock["now"])
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CandidateVerifier",
                        SimpleNamespace(validate_static_contract=lambda *_: None))
    def invoke(provider, contract_arg, lease_arg, **kw):
        observed.update(kw)
        clock["now"] = 101.2
        return _m3c_receipt(contract_arg.task_id, lease_arg.target_worktree)
    monkeypatch.setattr(service.worker_registry, "invoke", invoke)
    with pytest.raises(RuntimeError, match="WALL_TIME_BUDGET_EXHAUSTED"):
        service._run_default_resumable(contract, request, lambda *_: None,
                                       task_id=contract.task_id, attempt_id=attempt_id)
    assert observed["timeout_seconds"] == pytest.approx(1.0, abs=0.01)


def test_m3c_retry_preserves_execution_history_and_aggregate_budget_blocks_invoke(tmp_path, monkeypatch):
    """A terminal retry keeps prior receipts; their calls still consume the cap."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="m3c-history-retry")
    request.update({"execution_lane": "ISOLATED_TARGET", "maximum_attempts_per_task": 2})
    contract = service.build_contract(request)
    prior = _m3c_receipt(contract.task_id, str(tmp_path / "old-target"), calls=1, attempts=1)
    original = {
        "task_id": contract.task_id, "status": "FINAL_BLOCK", "terminal_status": "FINAL_BLOCK",
        "cleanup_decision": "REMOVED", "promotion_status": "NOT_CREATED", "request": request,
        "contract": contract.model_dump(mode="json"), "contract_hash": contract.contract_hash,
        "attempt_id": "old-attempt", "attempts": [{"attempt_id": "old-attempt"}],
        "executions": [prior.__dict__],
    }
    service._write_state(contract.task_id, original)
    monkeypatch.setattr(service, "_launch_worker", lambda task_id, attempt_id: service._read_state(task_id))
    retried = service.submit_task(request)
    durable = service._read_state(contract.task_id)
    assert retried["attempt_id"] != "old-attempt"
    assert len(durable["executions"]) == 1
    assert durable["executions"][0]["provider_calls"] == 1
    assert durable["executions"][0]["provider_attempt_count"] == 1
    assert durable["executions"][0]["stdout_sha256"] == prior.stdout_sha256
    assert len(durable["attempts"]) == 2

    # The retained receipt consumes the whole one-call budget before any invoke.
    retry_contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, "m3c-history-budget")
    state = service._read_state(retry_contract.task_id)
    state.update({"status": "WORKER_RUNNING", "active_provider": "codex",
                  "attempts": [{"attempt_id": attempt_id}], "executions": [prior.__dict__]})
    service._write_state(retry_contract.task_id, state)
    invoked = {"n": 0}
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CandidateVerifier",
                        SimpleNamespace(validate_static_contract=lambda *_: None))
    monkeypatch.setattr(service.worker_registry, "invoke",
                        lambda *args, **kwargs: invoked.__setitem__("n", invoked["n"] + 1))
    with pytest.raises(RuntimeError, match="maximum_provider_calls aggregate budget exhausted"):
        service._run_default_resumable(retry_contract, state["request"], lambda *_: None,
                                       task_id=retry_contract.task_id, attempt_id=attempt_id)
    assert invoked["n"] == 0


def _m3c_repairable_workforce_state(tmp_path, monkeypatch, *, task_id):
    card_path = f"tasks/issue-7/{task_id}.md"
    card = tmp_path / card_path
    card.parent.mkdir(parents=True)
    card.write_text(f"task_id: `{task_id}`\nAUTO_CHAIN: false\n", encoding="utf-8")
    card_hash = hashlib.sha256(card.read_bytes()).hexdigest()
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.CANONICAL_SOURCE_ROOT",
        tmp_path,
    )
    internal = build_canonical_planner_admission(
        task_id=task_id,
        task_text="repair one bounded candidate",
        allowed_files=("nexus_canary.txt",),
        verifier_command=("python3 -c 'print(\"pass\")'",),
        task_card_identity=VerifiedTaskCardIdentity(
            task_id=task_id,
            task_card_path=card_path,
            canonical_task_card_path=str(card.resolve()),
            task_card_hash=card_hash,
        ),
    )
    old_attempt_id = "attempt-old-repair"
    request = _real_request(tmp_path, task_id=task_id)
    request.update({
        "execution_lane": "ISOLATED_TARGET",
        "maximum_attempts_per_task": 2,
        "worker": "auto",
        "model": internal["binding"]["model"],
        "workforce_demands": internal["workforce_demands"],
        "workforce_admission": internal["workforce_admission"],
        "planner_output": internal["planner_output"],
        "task_card_path": card_path,
        "task_card_hash": card_hash,
        "contract_kind": ContractKind.TRACKED_TASK_CARD.value,
        "worker_candidate_ingress": True,
        "attempt_id": old_attempt_id,
    })
    old_envelope = build_canonical_dispatch_envelope(
        internal["planner_output"],
        internal["binding"],
        task_id=task_id,
        attempt_id=old_attempt_id,
        task_card_path=card_path,
        task_card_hash=card_hash,
    ).to_dict()
    request["canonical_dispatch_envelope"] = old_envelope
    binding = validate_workforce_dispatch_binding(request)
    assert binding is not None
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        auto_reconcile=False,
        ephemeral=True,
    )
    contract = service.build_contract(request)
    old_receipt = _m3c_receipt(task_id, tmp_path / "old-target").__dict__
    old_verified_receipt = {
        "schema": "nexus.candidate_verification_receipt.v1",
        "verified": True,
        "candidate_commit_sha": "c" * 40,
        "receipt_hash": "e" * 64,
    }
    service._write_state(task_id, {
        "task_id": task_id,
        "status": "FINAL_BLOCK",
        "terminal_status": "FINAL_BLOCK",
        "final_disposition": "FINAL_BLOCK",
        "cleanup_decision": "REMOVED",
        "promotion_status": "NOT_CREATED",
        "acceptance_decision": "REPAIRABLE",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash,
        "contract_kind": ContractKind.TRACKED_TASK_CARD.value,
        "task_card_path": card_path,
        "task_card_hash": card_hash,
        "attempt_id": old_attempt_id,
        "attempts": [{
            "attempt_id": old_attempt_id,
            "canonical_dispatch_envelope": copy.deepcopy(old_envelope),
            "workforce_dispatch": copy.deepcopy(binding),
            "verified_receipt": copy.deepcopy(old_verified_receipt),
        }],
        "executions": [copy.deepcopy(old_receipt)],
        "workforce_dispatch": copy.deepcopy(binding),
        "canonical_dispatch_envelope": copy.deepcopy(old_envelope),
        "workforce_policy_hash": binding["policy_hash"],
        "workforce_binding_hash": binding["binding_hash"],
        "workforce_aggregate_binding_hash": binding["aggregate_binding_hash"],
        "selected_worker_id": binding["worker_id"],
        "selected_provider": binding["provider"],
        "selected_model": binding["model"],
        "candidate_commit_sha": "c" * 40,
        "candidate_ref": f"refs/nexus/candidates/{task_id}/old",
        "candidate_state_hash": "d" * 64,
        "verified_receipt_hash": "e" * 64,
        "verified_receipt": copy.deepcopy(old_verified_receipt),
        "promotion_packet": {
            "candidate_commit_sha": "c" * 40,
            "candidate_state_hash": "d" * 64,
            "verified_receipt_hash": "e" * 64,
        },
    })
    return service, request, old_envelope, old_receipt, old_verified_receipt


@pytest.mark.parametrize("binding_fault", ["missing", "tampered"])
def test_m3c_repair_retry_invalid_persisted_workforce_binding_blocks_zero_launch(
    tmp_path,
    monkeypatch,
    binding_fault,
):
    service, _, _, _, _ = _m3c_repairable_workforce_state(
        tmp_path,
        monkeypatch,
        task_id=f"m3c-repair-binding-{binding_fault}",
    )
    state = service._read_state(f"m3c-repair-binding-{binding_fault}")
    if binding_fault == "missing":
        state["request"].pop("workforce_admission")
    else:
        state["request"]["workforce_admission"]["aggregate_binding_hash"] = "0" * 64
    service._write_state(state["task_id"], state)

    calls = {"launch": 0, "invoke": 0}
    monkeypatch.setattr(
        service,
        "_launch_worker",
        lambda *_: calls.__setitem__("launch", calls["launch"] + 1),
    )
    monkeypatch.setattr(
        service.worker_registry,
        "invoke",
        lambda *_args, **_kwargs: calls.__setitem__("invoke", calls["invoke"] + 1),
    )

    result = service.retry_task(state["task_id"])

    assert result["retry"]["decision"] == "BLOCK"
    assert result["retry"]["blocker"].startswith("WORKFORCE_ADMISSION_BINDING_")
    assert calls == {"launch": 0, "invoke": 0}
    assert service._read_state(state["task_id"])["attempts"] == state["attempts"]


def test_m3c_repair_retry_rebinds_fresh_attempt_and_preserves_old_evidence(
    tmp_path,
    monkeypatch,
):
    task_id = "m3c-repair-fresh-envelope"
    service, _, old_envelope, old_receipt, old_verified_receipt = (
        _m3c_repairable_workforce_state(tmp_path, monkeypatch, task_id=task_id)
    )
    old_attempt_bytes = json.dumps(
        service._read_state(task_id)["attempts"][0], sort_keys=True
    )
    old_execution_bytes = json.dumps(old_receipt, sort_keys=True)
    monkeypatch.setattr(
        service,
        "_launch_worker",
        lambda owned_task_id, _attempt_id: service._read_state(owned_task_id),
    )

    result = service.retry_task(task_id)
    durable = service._read_state(task_id)
    fresh_attempt_id = durable["attempt_id"]
    fresh_envelope = durable["canonical_dispatch_envelope"]

    assert result["retry"]["decision"] == "REUSED_TASK_ID"
    assert fresh_attempt_id != "attempt-old-repair"
    assert fresh_envelope != old_envelope
    assert fresh_envelope["task_id"] == task_id
    assert fresh_envelope["attempt_id"] == fresh_attempt_id
    assert fresh_envelope["task_card_path"] == durable["task_card_path"]
    assert fresh_envelope["task_card_hash"] == durable["task_card_hash"]
    assert fresh_envelope["worker_id"] == durable["selected_worker_id"]
    assert fresh_envelope["provider"] == durable["selected_provider"]
    assert fresh_envelope["model"] == durable["selected_model"]
    assert json.dumps(durable["attempts"][0], sort_keys=True) == old_attempt_bytes
    assert json.dumps(durable["executions"][0], sort_keys=True) == old_execution_bytes
    assert durable["attempts"][0]["verified_receipt"] == old_verified_receipt

    assert durable["candidate_history"] == [{
        "candidate_commit": "c" * 40,
        "candidate_ref": f"refs/nexus/candidates/{task_id}/old",
        "candidate_state_hash": "d" * 64,
        "verified_receipt_hash": "e" * 64,
        "approval_binding": None,
        "integration_branch": None,
        "integration_commit": None,
        "final_disposition": "FINAL_BLOCK",
    }]
    for field in (
        "candidate",
        "candidate_commit_sha",
        "candidate_tree_sha",
        "candidate_ref",
        "candidate_state_hash",
        "verified_receipt_hash",
        "verified_receipt",
        "promotion_packet",
    ):
        assert durable[field] is None


def test_m3d_event_append_failure_persists_reconciliation_debt(tmp_path, monkeypatch):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    task_id = "m3d-event-append-failure"
    attempt_id = "attempt-m3d-event-failure"
    service._write_state(
        task_id,
        {
            "task_id": task_id,
            "attempt_id": attempt_id,
            "status": "SUBMITTED",
            "status_history": [{"status": "SUBMITTED", "at": "2026-01-01T00:00:00+00:00"}],
        },
    )
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.NexusEventBus.emit_attempt_transition",
        lambda _event: (_ for _ in ()).throw(OSError("event append failed")),
    )

    with pytest.raises(OSError, match="event append failed"):
        service._checkpoint(task_id, "WORKER_RUNNING", attempt_id=attempt_id)

    durable = service._read_state(task_id)
    assert durable["status"] == "WORKER_RUNNING"
    assert durable["event_reconciliation_required"] is True
    assert durable["event_append_failure"]["status"] == "BLOCKED"
    assert durable["event_append_failure"]["error_type"] == "OSError"
    assert len(durable["event_append_failure"]["error_sha256"]) == 64


def test_canonical_continuity_read_preserves_event_store_integrity_error(monkeypatch):
    class ExplodingStore:
        event_log_path = None

        def read_recent(self, **_kwargs):
            raise ValueError("tampered event log")

    monkeypatch.setattr(NexusEventBus, "_log_store", ExplodingStore())
    monkeypatch.setattr(NexusEventBus, "_event_log_path", None)
    with pytest.raises(ValueError, match="tampered event log"):
        SelfHostedTaskService.read_canonical_attempt_events("task-1", "attempt-1")
