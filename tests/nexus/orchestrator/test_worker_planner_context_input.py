from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService, _sha256_json


def _fixture(tmp_path):
    task_id = "worker-context-1"
    attempt_id = "attempt-1"
    envelope = {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "planner_decision_hash": "d" * 64,
        "planner_plan_hash": "p" * 64,
        "worker_id": "worker-1",
        "provider": "codex",
        "model": "model-1",
    }
    request = {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "what": "bounded worker context",
        "planner_output": {
            "decision_hash": "d" * 64,
            "plan_hash": "p" * 64,
            "selected_capabilities": ["memory"],
        },
        "canonical_dispatch_envelope": envelope,
        "provider": "codex",
        "model": "model-1",
        "action_request_hash": "a" * 64,
        "signed_marker": {"action": "unchanged"},
    }
    state = {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "status": "SUBMITTED",
        "request": deepcopy(request),
        "action": {"signed": True},
        "action_request_hash": request["action_request_hash"],
        "controller_revision": "c" * 40,
        "canonical_dispatch_envelope": envelope,
    }
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state(task_id, state)
    contract = SimpleNamespace(controller_revision="c" * 40, target_base_revision="t" * 40, target_worktree_root=str(tmp_path), task_id=task_id, preferred_provider="codex", fallback_provider=None, provider_order=("codex",), maximum_provider_calls=1, maximum_attempts_per_task=1, maximum_provider_attempts=1, allowed_files=("x.py",), verifier_commands=("true",), goal=SimpleNamespace(what="w", why="w"))
    lease = SimpleNamespace(target_worktree=str(tmp_path / "leased-target"), initial_head="t" * 40)
    return service, request, state, contract, lease


def test_worker_context_materialization_claims_persists_and_reuses_bundle(tmp_path, monkeypatch):
    service, request, state, contract, lease = _fixture(tmp_path)
    calls = {"materialize": 0}
    from nexus.services.capability_evidence_bundle import build_capability_evidence_bundle
    bundle = build_capability_evidence_bundle(
        task_id=state["task_id"], workspace_revision="t" * 40,
        task_statement=request["what"], plan_payload=request["planner_output"],
        plan_hash="p" * 64, planner_decision_id="d" * 64,
        capability_results={"memory": {
            "task_id": state["task_id"], "invoked": True, "gate_passed": True,
            "status": "SUCCEEDED", "evidence_refs": ["evidence:memory"],
            "consumer_payload": {"fields": {"summary": "UNIQUE_MATERIALIZED_PAYLOAD"}},
        }}, selected_capabilities=["memory"], source_hash="s" * 64,
    )

    monkeypatch.setattr(
        "nexus.services.mainchain_entry.build_mainchain_capability_invokers",
        lambda **_: {"memory": lambda _: {"status": "SUCCEEDED"}},
    )

    def materialize(**kwargs):
        calls["materialize"] += 1
        assert kwargs["capability_context"]["target_worktree"] == str(lease.target_worktree)
        return {}, bundle

    monkeypatch.setattr("nexus.services.unified_runtime.materialize_selected_capability_evidence", materialize)
    monkeypatch.setattr(service, "_prompt", staticmethod(lambda _: "BASE_PROMPT"))

    original_request = deepcopy(request)
    first = service._worker_context_materialization(
        request=request, state=state, task_id=state["task_id"], attempt_id=state["attempt_id"],
        fresh_submission=True, contract=contract, lease=lease, base_prompt="BASE_PROMPT",
        actual_provider="codex", actual_model="model-1",
    )
    persisted = service._read_state(state["task_id"])
    assert first[0].startswith("BASE_PROMPT\n\n[NEXUS MODEL CONTEXT]\n")
    assert "UNIQUE_MATERIALIZED_PAYLOAD" in first[0]
    assert first[1]["status"] == "PASS"
    assert first[1]["selected_capability_ids"] == ["memory"]
    assert persisted["worker_model_context_materialization"]["status"] == "COMPLETE"
    assert persisted["worker_model_context_materialization"]["bundle_hash"] == _sha256_json(bundle)
    assert request == original_request
    assert persisted["request"] == state["request"]
    assert persisted["action"] == state["action"]

    second = service._worker_context_materialization(
        request=request, state=persisted, task_id=state["task_id"], attempt_id=state["attempt_id"],
        fresh_submission=False, contract=contract, lease=lease, base_prompt="BASE_PROMPT",
            actual_provider="codex", actual_model="model-1",
    )
    assert second == first
    assert calls["materialize"] == 1


@pytest.mark.parametrize("field", ["task_id", "attempt_id", "planner_plan_hash", "planner_decision_hash", "provider", "model"])
def test_worker_context_binding_substitution_denies_before_adapter(tmp_path, monkeypatch, field):
    service, request, state, contract, lease = _fixture(tmp_path)
    calls = {"materialize": 0}
    monkeypatch.setattr("nexus.services.mainchain_entry.build_mainchain_capability_invokers", lambda **_: {"memory": lambda _: calls.__setitem__("materialize", calls["materialize"] + 1)})
    values = {
        "task_id": request["task_id"], "attempt_id": request["attempt_id"],
        "planner_plan_hash": "p" * 64, "planner_decision_hash": "d" * 64,
        "provider": "codex", "model": "model-1",
    }
    values[field] = "wrong"
    if field in {"task_id", "attempt_id"}:
        request[field] = values[field]
    else:
        request["canonical_dispatch_envelope"][field] = values[field]
    with pytest.raises((ValueError, RuntimeError)):
        service._worker_context_materialization(
            request=request, state=state, task_id=state["task_id"], attempt_id=state["attempt_id"],
            fresh_submission=True, contract=contract, lease=lease, base_prompt="BASE_PROMPT",
            actual_provider="codex", actual_model="model-1",
        )
    assert calls["materialize"] == 0


def test_worker_context_started_without_completion_is_unknown_and_not_replayed(tmp_path):
    service, request, state, contract, lease = _fixture(tmp_path)
    state["status"] = "WORKER_RUNNING"
    state["worker_model_context_materialization"] = {
        "schema": "nexus.worker_model_context_materialization.v1",
        "status": "STARTED",
        "task_id": state["task_id"],
        "attempt_id": state["attempt_id"],
    }
    service._write_state(state["task_id"], state)
    with pytest.raises(RuntimeError, match="OUTCOME_UNKNOWN"):
        service._worker_context_materialization(
            request=request, state=state, task_id=state["task_id"], attempt_id=state["attempt_id"],
            fresh_submission=False, contract=contract, lease=lease, base_prompt="BASE_PROMPT",
            actual_provider="codex", actual_model="model-1",
        )


def test_resumable_worker_registry_receives_real_bounded_context_and_receipt(tmp_path, monkeypatch):
    service, request, state, contract, lease = _fixture(tmp_path)
    calls = {"adapter": 0, "provider": 0}
    request["planner_output"]["selected_capabilities"] = ["memory"]
    request["canonical_dispatch_envelope"]["planner_decision_hash"] = "d" * 64
    request["canonical_dispatch_envelope"]["planner_plan_hash"] = "p" * 64
    request["planner_output"]["decision_hash"] = "d" * 64
    request["planner_output"]["plan_hash"] = "p" * 64
    state["request"] = deepcopy(request)
    state["canonical_dispatch_envelope"] = request["canonical_dispatch_envelope"]
    state["action_request_hash"] = request["action_request_hash"]
    service._write_state(state["task_id"], state)

    monkeypatch.setattr(
        "nexus.services.mainchain_entry.build_mainchain_capability_invokers",
        lambda **_: {"memory": lambda context: (calls.__setitem__("adapter", calls["adapter"] + 1) or {
            "task_id": context["task_id"], "invoked": True, "gate_passed": True,
            "status": "SUCCEEDED", "evidence_refs": ["memory"],
            "consumer_payload": {"result": "actual bounded memory"},
        })},
    )
    monkeypatch.setattr(service, "build_contract", lambda req: contract)
    monkeypatch.setattr(service, "_revalidate_tracked_dispatch_task_card", lambda *args: None)
    monkeypatch.setattr(service, "_assert_persisted_workforce_dispatch", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_revalidate_provider_boundary", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_escalation_policy", staticmethod(lambda _: None))
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CandidateVerifier.validate_static_contract", staticmethod(lambda *args: None))
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", lambda **_: object())
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.SelfHostedDevelopmentController", lambda **_: SimpleNamespace(
        prepare_task=lambda c: lease,
    ))

    from nexus.executors.worker_contract import WorkerExecutionReceipt, WorkerOutcome
    def invoke(provider, contract_arg, lease_arg, *, prompt, model=None, **kwargs):
        calls["provider"] += 1
        assert "actual bounded memory" in prompt
        return WorkerExecutionReceipt(
            provider=provider, task_id=contract_arg.task_id, target_worktree=lease_arg.target_worktree,
            worker_status="COMPLETED", outcome=WorkerOutcome.EXECUTION_COMPLETED.value, exit_code=0,
            executable_identity="fake", argv=("fake",), stdout_sha256="a" * 64, stderr_sha256="b" * 64,
            wall_time_ms=1, process_group_id=None, process_group_killed=False, timed_out=False,
            provider_calls=1, provider_attempt_count=1, evidence_complete=True, commit_created=False,
            merge_performed=False, push_performed=False,
        )
    service.worker_registry = SimpleNamespace(invoke=invoke, preflight=lambda _: SimpleNamespace(ready=True))
    def update(status, values):
        service._checkpoint(state["task_id"], status, values, attempt_id=state["attempt_id"])
        if status == "WORKER_COMPLETED":
            raise RuntimeError("stop after bounded receipt")
    with pytest.raises(RuntimeError, match="stop after bounded receipt"):
        service._run_default_resumable(contract, request, update, task_id=state["task_id"], attempt_id=state["attempt_id"])
    persisted = service._read_state(state["task_id"])
    assert calls == {"adapter": 1, "provider": 1}
    assert persisted["worker_model_context_materialization"]["status"] == "COMPLETE"
    assert persisted["worker_model_context_consumption"]["proof_basis"] == "WORKER_REGISTRY_INVOCATION"


def test_genuine_legacy_worker_does_not_require_optional_runtime(tmp_path, monkeypatch):
    service, request, state, contract, lease = _fixture(tmp_path)
    request.pop("planner_output")
    request.pop("canonical_dispatch_envelope")
    state.pop("canonical_dispatch_envelope")
    state["request"] = deepcopy(request)
    service._write_state(state["task_id"], state)
    service._worker_context_materialization = lambda **_: None
    monkeypatch.setattr(service, "build_contract", lambda req: contract)
    monkeypatch.setattr(service, "_revalidate_tracked_dispatch_task_card", lambda *args: None)
    monkeypatch.setattr(service, "_assert_persisted_workforce_dispatch", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_revalidate_provider_boundary", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_escalation_policy", staticmethod(lambda _: None))
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CandidateVerifier.validate_static_contract", staticmethod(lambda *args: None))
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", lambda **_: object())
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.SelfHostedDevelopmentController", lambda **_: SimpleNamespace(
        prepare_task=lambda c: lease,
    ))
    from nexus.executors.worker_contract import WorkerExecutionReceipt, WorkerOutcome

    def invoke(provider, contract_arg, lease_arg, *, prompt, model=None, **kwargs):
        return WorkerExecutionReceipt(
            provider=provider, task_id=contract_arg.task_id, target_worktree=lease_arg.target_worktree,
            worker_status="COMPLETED", outcome=WorkerOutcome.EXECUTION_COMPLETED.value, exit_code=0,
            executable_identity="fake", argv=("fake",), stdout_sha256="a" * 64, stderr_sha256="b" * 64,
            wall_time_ms=1, process_group_id=None, process_group_killed=False, timed_out=False,
            provider_calls=1, provider_attempt_count=1, evidence_complete=True, commit_created=False,
            merge_performed=False, push_performed=False,
        )

    service.worker_registry = SimpleNamespace(invoke=invoke, preflight=lambda _: SimpleNamespace(ready=True))
    original_import = __import__

    def reject_optional_runtime(name, *args, **kwargs):
        if name == "nexus_runtime.task_context":
            raise ModuleNotFoundError("optional nexus_runtime unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", reject_optional_runtime)
    completed = []

    def update(status, values):
        completed.append(status)
        if status == "WORKER_COMPLETED":
            raise RuntimeError("legacy worker completed")

    with pytest.raises(RuntimeError, match="legacy worker completed"):
        service._run_default_resumable(contract, request, update, task_id=state["task_id"], attempt_id=state["attempt_id"])
    assert "WORKER_COMPLETED" in completed


def test_started_failure_and_tampered_complete_bundle_never_replay(tmp_path, monkeypatch):
    service, request, state, contract, lease = _fixture(tmp_path)
    calls = {"materialize": 0}
    monkeypatch.setattr("nexus.services.mainchain_entry.build_mainchain_capability_invokers", lambda **_: {})
    def fail(**kwargs):
        calls["materialize"] += 1
        raise RuntimeError("adapter failed after STARTED")
    monkeypatch.setattr("nexus.services.unified_runtime.materialize_selected_capability_evidence", fail)
    with pytest.raises(RuntimeError, match="adapter failed"):
        service._worker_context_materialization(request=request, state=state, task_id=state["task_id"], attempt_id=state["attempt_id"], fresh_submission=True, contract=contract, lease=lease, base_prompt="BASE", actual_provider="codex", actual_model="model-1")
    resumed = service._read_state(state["task_id"])
    assert resumed["worker_model_context_materialization"]["status"] == "STARTED"
    with pytest.raises(RuntimeError, match="OUTCOME_UNKNOWN"):
        service._worker_context_materialization(request=request, state=resumed, task_id=state["task_id"], attempt_id=state["attempt_id"], fresh_submission=False, contract=contract, lease=lease, base_prompt="BASE", actual_provider="codex", actual_model="model-1")
    assert calls["materialize"] == 1


def test_partial_canonical_binding_with_flags_denies(tmp_path):
    service, request, state, contract, lease = _fixture(tmp_path)
    for field in ("planner_output", "canonical_dispatch_envelope"):
        partial = dict(request)
        partial.pop(field)
        partial["worker_candidate_ingress"] = True
        partial_state = dict(state)
        partial_state.pop(field, None)
        with pytest.raises(RuntimeError, match="worker_context_binding_missing"):
            service._worker_context_materialization(request=partial, state=partial_state, task_id=state["task_id"], attempt_id=state["attempt_id"], fresh_submission=True, contract=contract, lease=lease, base_prompt="BASE", actual_provider="codex", actual_model="model-1")


def _complete_worker_context(tmp_path, monkeypatch):
    service, request, state, contract, lease = _fixture(tmp_path)
    from nexus.services.capability_evidence_bundle import build_capability_evidence_bundle
    bundle = build_capability_evidence_bundle(
        task_id=state["task_id"], workspace_revision="t" * 40,
        task_statement=request["what"], plan_payload=request["planner_output"],
        plan_hash="p" * 64, planner_decision_id="d" * 64,
        capability_results={"memory": {
            "task_id": state["task_id"], "invoked": True, "gate_passed": True,
            "status": "SUCCEEDED", "evidence_refs": ["memory"],
            "consumer_payload": {"result": "bounded"},
        }}, selected_capabilities=["memory"], source_hash="s" * 64,
    )
    calls = {"materialize": 0}
    monkeypatch.setattr("nexus.services.mainchain_entry.build_mainchain_capability_invokers", lambda **_: {})
    def materialize(**kwargs):
        calls["materialize"] += 1
        return {}, bundle
    monkeypatch.setattr("nexus.services.unified_runtime.materialize_selected_capability_evidence", materialize)
    service._worker_context_materialization(
        request=request, state=state, task_id=state["task_id"], attempt_id=state["attempt_id"],
        fresh_submission=True, contract=contract, lease=lease, base_prompt="BASE",
        actual_provider="codex", actual_model="model-1",
    )
    return request, state, contract, lease, calls


@pytest.mark.parametrize("tamper", ["bundle", "task_id", "target_worktree"])
def test_complete_worker_context_tamper_denies_without_adapter_replay(tmp_path, monkeypatch, tamper):
    request, state, contract, lease, calls = _complete_worker_context(tmp_path, monkeypatch)
    persisted = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)._read_state(state["task_id"])
    record = dict(persisted["worker_model_context_materialization"])
    if tamper == "bundle":
        record["bundle"] = {**record["bundle"], "entries": [{"name": "tampered"}]}
    elif tamper == "task_id":
        record["task_id"] = "wrong-task"
    else:
        record["target_worktree"] = str(tmp_path / "wrong-target")
    persisted["worker_model_context_materialization"] = record
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state(state["task_id"], persisted)
    monkeypatch.setattr("nexus.services.unified_runtime.materialize_selected_capability_evidence", lambda **_: (_ for _ in ()).throw(AssertionError("adapter replay")))
    with pytest.raises(RuntimeError):
        service._worker_context_materialization(
            request=request, state=persisted, task_id=state["task_id"], attempt_id=state["attempt_id"],
            fresh_submission=False, contract=contract, lease=lease, base_prompt="BASE",
            actual_provider="codex", actual_model="model-1",
        )
    assert calls["materialize"] == 1


def test_missing_resumed_journal_and_reloaded_started_state_never_retry(tmp_path, monkeypatch):
    service, request, state, contract, lease = _fixture(tmp_path)
    service._write_state(state["task_id"], {**state, "status": "WORKER_RUNNING"})
    calls = {"materialize": 0}
    monkeypatch.setattr("nexus.services.unified_runtime.materialize_selected_capability_evidence", lambda **_: calls.__setitem__("materialize", calls["materialize"] + 1))
    with pytest.raises(RuntimeError, match="OUTCOME_UNKNOWN"):
        service._worker_context_materialization(request=request, state=state, task_id=state["task_id"], attempt_id=state["attempt_id"], fresh_submission=False, contract=contract, lease=lease, base_prompt="BASE", actual_provider="codex", actual_model="model-1")
    assert calls["materialize"] == 0

    def fail(**kwargs):
        calls["materialize"] += 1
        raise RuntimeError("materialization interrupted")
    monkeypatch.setattr("nexus.services.unified_runtime.materialize_selected_capability_evidence", fail)
    with pytest.raises(RuntimeError, match="materialization interrupted"):
        service._worker_context_materialization(request=request, state=state, task_id=state["task_id"], attempt_id=state["attempt_id"], fresh_submission=True, contract=contract, lease=lease, base_prompt="BASE", actual_provider="codex", actual_model="model-1")
    reloaded = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    reloaded_state = reloaded._read_state(state["task_id"])
    with pytest.raises(RuntimeError, match="OUTCOME_UNKNOWN"):
        reloaded._worker_context_materialization(request=request, state=reloaded_state, task_id=state["task_id"], attempt_id=state["attempt_id"], fresh_submission=False, contract=contract, lease=lease, base_prompt="BASE", actual_provider="codex", actual_model="model-1")
    assert calls["materialize"] == 1


def test_both_canonical_fields_missing_with_workforce_binding_denies(tmp_path):
    service, request, state, contract, lease = _fixture(tmp_path)
    partial = dict(request)
    partial.pop("planner_output")
    partial.pop("canonical_dispatch_envelope")
    flagged_state = {**state, "workforce_dispatch": {"binding": "existing"}}
    flagged_state.pop("canonical_dispatch_envelope", None)
    with pytest.raises(RuntimeError, match="worker_context_binding_missing"):
        service._worker_context_materialization(request=partial, state=flagged_state, task_id=state["task_id"], attempt_id=state["attempt_id"], fresh_submission=True, contract=contract, lease=lease, base_prompt="BASE", actual_provider="codex", actual_model="model-1")
