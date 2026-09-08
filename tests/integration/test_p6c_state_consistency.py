from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path

import pytest

from nexus.events.state_owner_manifest import (
    COMMITTED_STATUS,
    StateOwnerBinding,
    StateOwnerSelection,
    OwnerConflict,
    classify,
    commit_owner_transaction,
    owner_transaction_guard,
    read_manifest,
)
from nexus.events.effect_journal import EffectDispatchPort, EffectJournal, EffectReconcilePort
from nexus.events.log_store import JsonlEventLogStore
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.events.writer_generation import EventWriterGeneration, install_generation
from nexus.events.writer_generation import GenerationError
from nexus.services.unified_runtime import UnifiedRuntime, UnifiedRuntimeRequest


class _Planner:
    def plan(self, **_kwargs):
        from nexus.engine.capability_planner import CapabilityPlan

        return CapabilityPlan(
            schema_version="nexus_capability_plan_v1",
            selected_capabilities=[],
            required_capabilities=[],
            optional_capabilities=[],
            conditional_capabilities=[],
            pending_capabilities=[],
            forbidden_capabilities=[],
            constraints=["claim_fail_closed"],
            decision_trace=[],
            replan_trace=[],
            score=1.0,
            signal_snapshot={"route_truth_source": "CapabilityPlanner"},
        )


def _request(task_id: str = "p6c-runtime") -> UnifiedRuntimeRequest:
    return UnifiedRuntimeRequest(
        task_id=task_id,
        workspace_revision="rev-1",
        task_statement="record one bounded local runtime receipt",
        task_type="repair",
        route={"recommended_flow": "direct"},
        online_enabled=True,
        local_enabled=False,
    )


def _owner(root: Path, transaction_id: str) -> StateOwnerBinding:
    return StateOwnerBinding("p6c-test-owner", root.resolve(), 1, transaction_id)


def test_runtime_receipt_uses_prepared_owner_and_commits_atomic_manifest(tmp_path):
    install_generation(tmp_path, EventWriterGeneration(1, "p6c-writer"))
    receipt_path = tmp_path / "runtime" / "receipt.json"
    binding = _owner(tmp_path, "tx-runtime")
    selection = StateOwnerSelection("receipt:p6c-runtime", "runtime_receipt", "runtime/receipt.json")
    runtime = UnifiedRuntime(planner=_Planner())

    with owner_transaction_guard(binding, writer_generation=EventWriterGeneration(1, "p6c-writer"), selections=(selection,)) as context:
        receipt = runtime.run(
            _request(),
            online_invoker=lambda payload: {
                "task_id": payload["task_id"],
                "invoked": True,
                "status": "SUCCEEDED",
                "gate_passed": True,
                "evidence_refs": ["fixture:runtime"],
                "response": {"ok": True},
            },
            verifier=lambda payload: {
                "task_id": payload["task_id"],
                "invoked": True,
                "status": "FAILED",
                "gate_passed": False,
                "evidence_refs": ["fixture:failed-verifier"],
            },
            learning=lambda payload: {
                "task_id": payload["task_id"],
                "invoked": True,
                "status": "FAILED",
                "gate_passed": False,
                "evidence_refs": ["fixture:failed-learning"],
            },
            receipt_path=receipt_path,
            owner_context=context,
        )
        assert receipt["terminal_status"] == "INCOMPLETE"
        committed = commit_owner_transaction(context)

    assert receipt_path.is_file()
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["task_id"] == "p6c-runtime"
    assert committed.state == "COMMITTED"
    assert classify(binding).status == COMMITTED_STATUS
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.files[0].relative_path == "runtime/receipt.json"

    second_binding = _owner(tmp_path, "tx-replan")
    with owner_transaction_guard(
        second_binding,
        writer_generation=EventWriterGeneration(1, "p6c-writer"),
        selections=(selection,),
        previous_manifest_sha256=committed.manifest_sha256,
    ) as context:
        replanned = runtime.run_replan(
            receipt,
            _request(),
            online_invoker=lambda payload: {
                "task_id": payload["task_id"],
                "invoked": True,
                "status": "SUCCEEDED",
                "gate_passed": True,
                "evidence_refs": ["fixture:replan"],
            },
            verifier=lambda payload: {
                "task_id": payload["task_id"],
                "invoked": True,
                "status": "FAILED",
                "gate_passed": False,
                "evidence_refs": ["fixture:failed-replan-verifier"],
            },
            learning=lambda payload: {
                "task_id": payload["task_id"],
                "invoked": True,
                "status": "FAILED",
                "gate_passed": False,
                "evidence_refs": ["fixture:failed-replan-learning"],
            },
            receipt_path=receipt_path,
            owner_context=context,
        )
        assert replanned["execution_attempt"]["attempt_number"] == 2
        committed_replan = commit_owner_transaction(context)

    third_binding = _owner(tmp_path, "tx-finalize")
    with owner_transaction_guard(
        third_binding,
        writer_generation=EventWriterGeneration(1, "p6c-writer"),
        selections=(selection,),
        previous_manifest_sha256=committed_replan.manifest_sha256,
    ) as context:
        finalized = runtime.finalize_receipt(
            replanned,
            verifier={"task_id": "p6c-runtime", "invoked": True, "status": "FAILED", "gate_passed": False, "evidence_refs": ["fixture:final-verifier"]},
            learning={"task_id": "p6c-runtime", "invoked": True, "status": "FAILED", "gate_passed": False, "evidence_refs": ["fixture:final-learning"]},
            receipt_path=receipt_path,
            owner_context=context,
        )
        assert finalized["terminal_status"] == "INCOMPLETE"
        commit_owner_transaction(context)

    assert classify(third_binding).status == COMMITTED_STATUS


def test_runtime_owner_context_rejects_unselected_receipt_before_write(tmp_path):
    install_generation(tmp_path, EventWriterGeneration(1, "p6c-writer"))
    selected = tmp_path / "runtime" / "receipt.json"
    rejected = tmp_path / "runtime" / "rejected.json"
    binding = _owner(tmp_path, "tx-reject")
    selection = StateOwnerSelection("receipt:p6c-runtime", "runtime_receipt", "runtime/receipt.json")
    runtime = UnifiedRuntime(planner=_Planner())

    with owner_transaction_guard(binding, writer_generation=EventWriterGeneration(1, "p6c-writer"), selections=(selection,)) as context:
        calls = []
        try:
            runtime.run(
                _request(),
                online_invoker=lambda payload: calls.append(payload) or {"task_id": payload["task_id"], "invoked": True, "status": "SUCCEEDED", "gate_passed": True},
                receipt_path=rejected,
                owner_context=context,
            )
        except Exception as exc:
            assert "write is outside the frozen owner selection" in str(exc)
        else:
            raise AssertionError("unselected receipt path unexpectedly wrote")
        assert calls == []
    assert not rejected.exists()
    assert not selected.exists()


def _crash_after_runtime_receipt(root: str) -> None:
    project = Path(root)
    binding = _owner(project, "tx-crash-receipt")
    selection = StateOwnerSelection("receipt:p6c-crash", "runtime_receipt", "runtime/receipt.json")
    runtime = UnifiedRuntime(planner=_Planner())
    with owner_transaction_guard(
        binding,
        writer_generation=EventWriterGeneration(1, "p6c-writer"),
        selections=(selection,),
    ) as context:
        runtime.run(
            _request("p6c-crash"),
            online_invoker=lambda payload: {
                "task_id": payload["task_id"],
                "invoked": True,
                "status": "SUCCEEDED",
                "gate_passed": True,
            },
            receipt_path=project / "runtime" / "receipt.json",
            owner_context=context,
        )
        os._exit(17)


def test_child_exit_after_runtime_receipt_is_prepared_unknown(tmp_path):
    install_generation(tmp_path, EventWriterGeneration(1, "p6c-writer"))
    child = multiprocessing.Process(target=_crash_after_runtime_receipt, args=(str(tmp_path),))
    child.start()
    child.join(timeout=10)
    assert child.exitcode == 17
    outcome = classify(_owner(tmp_path, "tx-crash-receipt"))
    assert outcome.status == "PREPARED_UNKNOWN"
    assert outcome.reconcile_only is True
    assert (tmp_path / "runtime" / "receipt.json").is_file()


def _child_crash_matrix(root: str, cutpoint: str) -> None:
    project = Path(root)
    token = EventWriterGeneration(1, "p6c-writer")
    binding = _owner(project, f"tx-{cutpoint}")
    if cutpoint == "task":
        relative = "task-state/p6c-task.json"
        role = "task_state"
    elif cutpoint == "event":
        relative = ".nexus/events/event_log.jsonl"
        role = "event_log"
    elif cutpoint == "effect":
        relative = ".nexus/events/effect_journal.v1.json"
        role = "effect_journal"
    else:
        relative = "runtime/receipt.json"
        role = "runtime_receipt"
    selection = StateOwnerSelection(f"{role}:{cutpoint}", role, relative)
    with owner_transaction_guard(binding, writer_generation=token, selections=(selection,)) as context:
        if cutpoint == "task":
            service = SelfHostedTaskService(
                state_dir=project / "task-state",
                ephemeral=True,
                auto_reconcile=False,
                owner_context=context,
            )
            service._write_state("p6c-task", {"task_id": "p6c-task", "state": "PENDING"}, owner_context=context)
        elif cutpoint == "event":
            store = JsonlEventLogStore()
            store.configure(project, writer_generation=token, enforce_generation=True, owner_context=context)
            store.append_record({"event_type": "p6c_cutpoint", "payload": {"cutpoint": "event"}}, owner_context=context)
        elif cutpoint == "effect":
            journal = EffectJournal(project, token)
            identity = {
                "task_id": "p6c-effect",
                "workspace_revision": "rev-1",
                "planner_decision_id": "planner-1",
                "attempt": 1,
                "action": "fixture-effect",
                "subject_revision": "subject-1",
                "request_digest": "request-1",
            }
            journal.execute(
                identity=identity,
                subject="p6c-effect",
                request_digest="request-1",
                dispatch=lambda: {"fixture": "effect"},
                reconcile=None,
            )
        elif cutpoint == "receipt":
            UnifiedRuntime(planner=_Planner()).run(
                _request("p6c-receipt"),
                online_invoker=lambda payload: {"task_id": payload["task_id"], "invoked": True, "status": "SUCCEEDED", "gate_passed": True},
                receipt_path=project / "runtime" / "receipt.json",
                owner_context=context,
            )
        elif cutpoint == "prepare":
            pass
        else:
            raise AssertionError(f"unknown cutpoint: {cutpoint}")
        os._exit(17)


def _child_commit_cutpoint(root: str) -> None:
    project = Path(root)
    token = EventWriterGeneration(1, "p6c-writer")
    binding = _owner(project, "tx-commit")
    selection = StateOwnerSelection("receipt:commit", "runtime_receipt", "runtime/receipt.json")
    with owner_transaction_guard(binding, writer_generation=token, selections=(selection,)) as context:
        UnifiedRuntime(planner=_Planner()).run(
            _request("p6c-commit"),
            online_invoker=lambda payload: {"task_id": payload["task_id"], "invoked": True, "status": "SUCCEEDED", "gate_passed": True},
            receipt_path=project / "runtime" / "receipt.json",
            owner_context=context,
        )
        commit_owner_transaction(context)
        os._exit(17)


def test_actual_writer_crash_matrix_classifies_restart_without_success_inference(tmp_path):
    for cutpoint in ("prepare", "task", "event", "effect", "receipt"):
        project = tmp_path / cutpoint
        project.mkdir()
        install_generation(project, EventWriterGeneration(1, "p6c-writer"))
        child = multiprocessing.Process(target=_child_crash_matrix, args=(str(project), cutpoint))
        child.start()
        child.join(timeout=10)
        assert child.exitcode == 17, cutpoint
        outcome = classify(_owner(project, f"tx-{cutpoint}"))
        assert outcome.status == "PREPARED_UNKNOWN", (cutpoint, outcome)
        assert outcome.reconcile_only is True

    committed_root = tmp_path / "commit"
    committed_root.mkdir()
    install_generation(committed_root, EventWriterGeneration(1, "p6c-writer"))
    child = multiprocessing.Process(target=_child_commit_cutpoint, args=(str(committed_root),))
    child.start()
    child.join(timeout=10)
    assert child.exitcode == 17
    assert classify(_owner(committed_root, "tx-commit")).status == COMMITTED_STATUS


def test_successor_generation_denies_old_event_and_effect_writers_without_bytes(tmp_path):
    install_generation(tmp_path, EventWriterGeneration(1, "p6c-writer"))
    token = EventWriterGeneration(1, "p6c-writer")
    binding = _owner(tmp_path, "tx-history")
    selections = (
        StateOwnerSelection("event:history", "event_log", ".nexus/events/event_log.jsonl"),
        StateOwnerSelection("effect:history", "effect_journal", ".nexus/events/effect_journal.v1.json"),
    )
    with owner_transaction_guard(binding, writer_generation=token, selections=selections) as context:
        events = JsonlEventLogStore()
        events.configure(tmp_path, writer_generation=token, enforce_generation=True, owner_context=context)
        events.append_record({"event_type": "history", "payload": {"generation": 1}}, owner_context=context)
        old_events = JsonlEventLogStore()
        old_events.configure(tmp_path, writer_generation=token, enforce_generation=True)
        old_identity = {
            "task_id": "history",
            "workspace_revision": "rev-1",
            "planner_decision_id": "planner-1",
            "attempt": 1,
            "action": "history-effect",
            "subject_revision": "subject-1",
            "request_digest": "history-request",
        }
        EffectJournal(tmp_path, token).execute(
            identity=old_identity,
            subject="history",
            request_digest="history-request",
            dispatch=lambda: {"ok": True},
            reconcile=None,
        )
        committed = commit_owner_transaction(context)

    event_bytes = (tmp_path / ".nexus/events/event_log.jsonl").read_bytes()
    effect_bytes = (tmp_path / ".nexus/events/effect_journal.v1.json").read_bytes()
    install_generation(tmp_path, EventWriterGeneration(2, "p6c-writer-2"), expected_generation=1)
    with pytest.raises(GenerationError, match="GENERATION_REQUIRED"):
        old_events.append_record({"event_type": "old-writer", "payload": {}})
    new_identity = dict(old_identity, task_id="new-history", planner_decision_id="planner-2", request_digest="new-request")
    with pytest.raises(GenerationError, match="GENERATION_REQUIRED"):
        EffectJournal(tmp_path, token).execute(
            identity=new_identity,
            subject="new-history",
            request_digest="new-request",
            dispatch=lambda: {"should_not_run": True},
            reconcile=None,
        )
    assert (tmp_path / ".nexus/events/event_log.jsonl").read_bytes() == event_bytes
    assert (tmp_path / ".nexus/events/effect_journal.v1.json").read_bytes() == effect_bytes
    assert committed.state == "COMMITTED"


def _child_cross_store_crash(root: str, cutpoint: str, effect_calls) -> None:
    project = Path(root)
    token = EventWriterGeneration(1, "p6c-writer")
    binding = _owner(project, f"tx-cross-{cutpoint}")
    selections = (
        StateOwnerSelection("task:p6c-cross", "task_state", "task-state/p6c-cross.json"),
        StateOwnerSelection("event:p6c-cross", "event_log", ".nexus/events/event_log.jsonl"),
        StateOwnerSelection("effect:p6c-cross", "effect_journal", ".nexus/events/effect_journal.v1.json"),
        StateOwnerSelection("receipt:p6c-cross", "runtime_receipt", "runtime/receipt.json"),
    )
    with owner_transaction_guard(binding, writer_generation=token, selections=selections) as context:
        service = SelfHostedTaskService(
            state_dir=project / "task-state",
            ephemeral=True,
            auto_reconcile=False,
            owner_context=context,
        )
        service._write_state("p6c-cross", {"task_id": "p6c-cross", "state": "PENDING"}, owner_context=context)
        if cutpoint == "task":
            os._exit(17)

        events = JsonlEventLogStore()
        events.configure(project, writer_generation=token, enforce_generation=True, owner_context=context)
        events.append_record({"event_type": "p6c_cross_store", "payload": {"cutpoint": "event"}}, owner_context=context)
        if cutpoint == "event":
            os._exit(17)

        identity = {
            "task_id": "p6c-cross",
            "workspace_revision": "rev-1",
            "planner_decision_id": "planner-cross",
            "attempt": 1,
            "action": "cross-store-effect",
            "subject_revision": "subject-cross",
            "request_digest": "request-cross",
        }
        EffectJournal(project, token).execute(
            identity=identity,
            subject="p6c-cross",
            request_digest="request-cross",
            dispatch=lambda: _count_effect(effect_calls),
            reconcile=None,
        )
        if cutpoint == "effect":
            os._exit(17)

        UnifiedRuntime(planner=_Planner()).run(
            _request("p6c-cross"),
            online_invoker=lambda payload: {"task_id": payload["task_id"], "invoked": True, "status": "SUCCEEDED", "gate_passed": True},
            receipt_path=project / "runtime" / "receipt.json",
            owner_context=context,
        )
        if cutpoint == "receipt":
            os._exit(17)
        commit_owner_transaction(context)
        os._exit(17)


def _count_effect(effect_calls):
    with effect_calls.get_lock():
        effect_calls.value += 1
    return {"ok": True}


def test_cross_store_crash_matrix_preserves_prefix_and_never_replays_effect(tmp_path):
    expected_roles = {
        "task": {"task_state"},
        "event": {"task_state", "event_log"},
        "effect": {"task_state", "event_log", "effect_journal"},
        "receipt": {"task_state", "event_log", "effect_journal", "runtime_receipt"},
    }
    relative_paths = {
        "task_state": "task-state/p6c-cross.json",
        "event_log": ".nexus/events/event_log.jsonl",
        "effect_journal": ".nexus/events/effect_journal.v1.json",
        "runtime_receipt": "runtime/receipt.json",
    }
    for cutpoint in expected_roles:
        project = tmp_path / f"cross-{cutpoint}"
        project.mkdir()
        install_generation(project, EventWriterGeneration(1, "p6c-writer"))
        effect_calls = multiprocessing.Value("i", 0)
        child = multiprocessing.Process(target=_child_cross_store_crash, args=(str(project), cutpoint, effect_calls))
        child.start()
        child.join(timeout=10)
        assert child.exitcode == 17, cutpoint
        before_classify = {
            role: (project / relative).read_bytes() if (project / relative).is_file() else None
            for role, relative in relative_paths.items()
        }
        for role, relative in relative_paths.items():
            assert (before_classify[role] is not None) == (role in expected_roles[cutpoint]), (cutpoint, role)
        outcome = classify(_owner(project, f"tx-cross-{cutpoint}"))
        if cutpoint == "commit":
            assert outcome.status == COMMITTED_STATUS
        else:
            assert outcome.status == "PREPARED_UNKNOWN"
            assert outcome.reconcile_only is True
        after_classify = {
            role: (project / relative).read_bytes() if (project / relative).is_file() else None
            for role, relative in relative_paths.items()
        }
        assert after_classify == before_classify
        assert effect_calls.value == (1 if cutpoint in {"effect", "receipt", "commit"} else 0)


def test_runtime_denies_cross_root_and_generation_effect_journal_before_dispatch(tmp_path):
    root_a = tmp_path / "root-a"
    root_b = tmp_path / "root-b"
    root_a.mkdir()
    root_b.mkdir()
    token_a = EventWriterGeneration(1, "p6c-writer-a")
    token_b = EventWriterGeneration(1, "p6c-writer-b")
    install_generation(root_a, token_a)
    install_generation(root_b, token_b)
    selection = StateOwnerSelection("receipt:coupling", "runtime_receipt", "runtime/receipt.json")
    dispatch_calls = []
    dispatch = EffectDispatchPort(lambda operation: dispatch_calls.append(1) or operation())
    reconcile = EffectReconcilePort(lambda record: None)
    receipt_path = root_a / "runtime" / "receipt.json"

    with owner_transaction_guard(_owner(root_a, "tx-cross-root"), writer_generation=token_a, selections=(selection,)) as context:
        with pytest.raises(ValueError, match="runtime_effect_owner_root_mismatch"):
            UnifiedRuntime(planner=_Planner()).run(
                _request("cross-root"),
                online_invoker=lambda payload: {"task_id": payload["task_id"], "invoked": True, "status": "SUCCEEDED", "gate_passed": True},
                receipt_path=receipt_path,
                owner_context=context,
                effect_journal=EffectJournal(root_b, token_b),
                effect_dispatch=dispatch,
                effect_reconcile=reconcile,
            )
    assert dispatch_calls == []
    assert not (root_b / ".nexus/events/effect_journal.v1.json").exists()

    root_c = tmp_path / "root-c"
    root_c.mkdir()
    install_generation(root_c, token_a)
    receipt_path_c = root_c / "runtime" / "receipt.json"
    with owner_transaction_guard(_owner(root_c, "tx-generation"), writer_generation=token_a, selections=(selection,)) as context:
        with pytest.raises(ValueError, match="runtime_effect_owner_generation_mismatch"):
            UnifiedRuntime(planner=_Planner()).run(
                _request("cross-generation"),
                online_invoker=lambda payload: {"task_id": payload["task_id"], "invoked": True, "status": "SUCCEEDED", "gate_passed": True},
                receipt_path=receipt_path_c,
                owner_context=context,
                effect_journal=EffectJournal(root_c, EventWriterGeneration(2, "p6c-writer-a-2")),
                effect_dispatch=dispatch,
                effect_reconcile=reconcile,
            )
    assert dispatch_calls == []

    root_d = tmp_path / "root-d"
    root_d.mkdir()
    install_generation(root_d, token_a)
    receipt_path_d = root_d / "runtime" / "receipt.json"
    with owner_transaction_guard(_owner(root_d, "tx-unselected-effect"), writer_generation=token_a, selections=(selection,)) as context:
        with pytest.raises(OwnerConflict, match="write is outside the frozen owner selection"):
            UnifiedRuntime(planner=_Planner()).run(
                _request("unselected-effect"),
                online_invoker=lambda payload: {"task_id": payload["task_id"], "invoked": True, "status": "SUCCEEDED", "gate_passed": True},
                receipt_path=receipt_path_d,
                owner_context=context,
                effect_journal=EffectJournal(root_d, token_a),
                effect_dispatch=dispatch,
                effect_reconcile=reconcile,
            )
    assert dispatch_calls == []


def test_runtime_owner_receipt_symlink_alias_denied_before_dispatch(tmp_path):
    token = EventWriterGeneration(1, "p6c-writer")
    install_generation(tmp_path, token)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    outside = tmp_path.parent / "p6c-outside-receipt.json"
    (runtime_dir / "alias.json").symlink_to(outside)
    selection = StateOwnerSelection("receipt:symlink", "runtime_receipt", "runtime/receipt.json")
    calls = []
    with owner_transaction_guard(_owner(tmp_path, "tx-symlink"), writer_generation=token, selections=(selection,)) as context:
        with pytest.raises(ValueError, match="runtime_receipt_owner_path_invalid"):
            UnifiedRuntime(planner=_Planner()).run(
                _request("symlink"),
                online_invoker=lambda payload: calls.append(payload) or {"task_id": payload["task_id"], "invoked": True, "status": "SUCCEEDED", "gate_passed": True},
                receipt_path=runtime_dir / "alias.json",
                owner_context=context,
            )
    assert calls == []
    assert not outside.exists()


def _make_effect_receipt(root: Path, token: EventWriterGeneration, tx: str):
    selection = (
        StateOwnerSelection("effect:receipt", "effect_journal", ".nexus/events/effect_journal.v1.json"),
        StateOwnerSelection("receipt:receipt", "runtime_receipt", "runtime/receipt.json"),
    )
    receipt_path = root / "runtime" / "receipt.json"
    with owner_transaction_guard(_owner(root, tx), writer_generation=token, selections=selection) as context:
        receipt = UnifiedRuntime(planner=_Planner()).run(
            _request("journaled-receipt"),
            online_invoker=lambda payload: {"task_id": payload["task_id"], "invoked": True, "status": "SUCCEEDED", "gate_passed": True},
            verifier=lambda payload: {"task_id": payload["task_id"], "invoked": True, "status": "FAILED", "gate_passed": False, "evidence_refs": ["fixture:failed"]},
            learning=lambda payload: {"task_id": payload["task_id"], "invoked": True, "status": "FAILED", "gate_passed": False, "evidence_refs": ["fixture:failed-learning"]},
            receipt_path=receipt_path,
            owner_context=context,
            effect_journal=EffectJournal(root, token),
            effect_dispatch=EffectDispatchPort(lambda operation: operation()),
            effect_reconcile=EffectReconcilePort(lambda record: None),
        )
        committed = commit_owner_transaction(context)
    return receipt, receipt_path, committed.manifest_sha256, selection


def test_run_replan_and_finalize_reject_cross_owner_journal_before_receipt_write(tmp_path):
    root_a = tmp_path / "owner-a"
    root_b = tmp_path / "owner-b"
    root_a.mkdir()
    root_b.mkdir()
    token_a = EventWriterGeneration(1, "p6c-owner-a")
    token_b = EventWriterGeneration(1, "p6c-owner-b")
    install_generation(root_a, token_a)
    install_generation(root_b, token_b)
    receipt, receipt_path, previous_manifest_sha, selection = _make_effect_receipt(root_a, token_a, "tx-seed")
    original_bytes = receipt_path.read_bytes()
    dispatch_calls = []
    ports = {
        "effect_dispatch": EffectDispatchPort(lambda operation: dispatch_calls.append(1) or operation()),
        "effect_reconcile": EffectReconcilePort(lambda record: None),
    }

    with owner_transaction_guard(
        _owner(root_a, "tx-replan-cross-root"),
        writer_generation=token_a,
        selections=selection,
        previous_manifest_sha256=previous_manifest_sha,
    ) as context:
        with pytest.raises(ValueError, match="runtime_effect_owner_root_mismatch"):
            UnifiedRuntime(planner=_Planner()).run_replan(
                receipt,
                _request("journaled-receipt"),
                online_invoker=lambda payload: {"task_id": payload["task_id"], "invoked": True, "status": "SUCCEEDED", "gate_passed": True},
                receipt_path=receipt_path,
                owner_context=context,
                effect_journal=EffectJournal(root_b, token_b),
                **ports,
            )
    assert receipt_path.read_bytes() == original_bytes
    assert dispatch_calls == []

    root_c = tmp_path / "owner-c"
    root_d = tmp_path / "owner-d"
    root_c.mkdir()
    root_d.mkdir()
    install_generation(root_c, token_a)
    install_generation(root_d, token_b)
    finalize_receipt, finalize_path, finalize_previous, finalize_selection = _make_effect_receipt(root_c, token_a, "tx-finalize-seed")
    finalize_original = finalize_path.read_bytes()
    with owner_transaction_guard(
        _owner(root_c, "tx-finalize-cross-root"),
        writer_generation=token_a,
        selections=finalize_selection,
        previous_manifest_sha256=finalize_previous,
    ) as context:
        with pytest.raises(ValueError, match="runtime_effect_owner_root_mismatch"):
            UnifiedRuntime(planner=_Planner()).finalize_receipt(
                finalize_receipt,
                verifier={"task_id": "journaled-receipt", "invoked": True, "status": "FAILED", "gate_passed": False, "evidence_refs": ["fixture:final"]},
                learning={"task_id": "journaled-receipt", "invoked": True, "status": "FAILED", "gate_passed": False, "evidence_refs": ["fixture:final-learning"]},
                receipt_path=finalize_path,
                owner_context=context,
                effect_journal=EffectJournal(root_d, token_b),
            )
    assert finalize_path.read_bytes() == finalize_original
    assert dispatch_calls == []
