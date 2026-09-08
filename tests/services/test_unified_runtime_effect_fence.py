from __future__ import annotations
import shutil
import pytest
from nexus.events.effect_journal import EffectDispatchPort, EffectJournal, EffectJournalError, EffectReconcilePort
from nexus.engine.capability_contracts import CapabilityPlan
from nexus.events.writer_generation import EventWriterGeneration, install_generation
from nexus.services.unified_runtime import UnifiedRuntime
from tests.services.test_unified_runtime import _LocalService, _Planner, _online, _request, normalize_online_invoker_payload


def _ports(calls=None):
    calls = calls if calls is not None else []
    return (
        EffectDispatchPort(lambda operation: calls.append("dispatch") or operation()),
        EffectReconcilePort(lambda _record: None),
    )

def test_runtime_online_effect_is_reserved_before_dispatch(tmp_path):
    token = EventWriterGeneration(1, "runtime-test"); install_generation(tmp_path, token)
    journal = EffectJournal(tmp_path, token); calls=[]; port_calls=[]
    def dispatch(ctx):
        calls.append(ctx["task_id"])
        return normalize_online_invoker_payload(provider="fixture", task_id=ctx["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response={"ok": True}, evidence_refs=["fixture:effect"])
    dispatch_port = EffectDispatchPort(lambda operation: port_calls.append("dispatch") or operation())
    reconcile_port = EffectReconcilePort(lambda record: None)
    runtime = UnifiedRuntime(planner=_Planner())
    req = _request()
    out = runtime.run(req, online_invoker=dispatch, effect_journal=journal, effect_dispatch=dispatch_port, effect_reconcile=reconcile_port, effect_fenced=True, verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "evidence": "v"}, learning=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "evidence": "l"})
    assert calls == [req.task_id]
    assert port_calls == ["dispatch"]
    assert out["online"]["status"] == "SUCCEEDED"

def test_finalize_requires_journal_readback_for_fenced_receipt(tmp_path):
    token = EventWriterGeneration(1, "finalize-test"); install_generation(tmp_path, token)
    journal = EffectJournal(tmp_path, token)
    class _FinalizePlanner:
        def plan(self, **_):
            from nexus.engine.capability_contracts import CapabilityPlan
            return CapabilityPlan(schema_version="nexus_capability_plan_v1", selected_capabilities=[], required_capabilities=[], optional_capabilities=[], conditional_capabilities=[], pending_capabilities=[], forbidden_capabilities=[], constraints=[], decision_trace=[], replan_trace=[], score=1.0, signal_snapshot={})
    runtime = UnifiedRuntime(planner=_FinalizePlanner()); req = _request()
    payload=lambda ctx: normalize_online_invoker_payload(provider="fixture", task_id=ctx["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response={"ok": True}, evidence_refs=["fixture:effect"])
    receipt=runtime.run(req, online_invoker=payload, effect_journal=journal, effect_dispatch=EffectDispatchPort(lambda operation: operation()), effect_reconcile=EffectReconcilePort(lambda _: None), effect_fenced=True, verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "evidence": "v"}, learning=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "evidence": "l"})
    assert receipt["effect_journal_bindings"]
    missing=runtime.finalize_receipt(receipt, verifier={"invoked": True, "gate_passed": True, "evidence": "v"}, learning={"invoked": True, "gate_passed": True, "evidence": "l"})
    assert missing["receipt_complete"] is False
    complete=runtime.finalize_receipt(receipt, verifier={"invoked": True, "gate_passed": True, "evidence": "v"}, learning={"invoked": True, "gate_passed": True, "evidence": "l"}, effect_journal=journal)
    assert complete["receipt_complete"] is True

def test_fake_journal_rejected_even_without_fenced_flag(tmp_path):
    class Fake:
        def execute(self, **_): return {}
        def get(self, _): return None
    runtime = UnifiedRuntime(planner=_Planner())
    with pytest.raises(ValueError, match="canonical_effect_journal_required"):
        runtime.run(_request(), online_invoker=lambda _: {}, effect_journal=Fake(), effect_reconcile=lambda _: None)

def test_fenced_requires_separate_reconcile_port(tmp_path):
    token = EventWriterGeneration(1, "ports"); install_generation(tmp_path, token)
    with pytest.raises(ValueError, match="effect_reconcile_port_required"):
        UnifiedRuntime(planner=_Planner()).run(_request(), online_invoker=lambda _: {}, effect_journal=EffectJournal(tmp_path, token), effect_dispatch=EffectDispatchPort(lambda operation: operation()), effect_fenced=True)


def test_capability_finalize_and_copy_root_readback_are_bound(tmp_path):
    class Planner:
        def plan(self, **_):
            return CapabilityPlan(
                schema_version="nexus_capability_plan_v1",
                selected_capabilities=["memory"], required_capabilities=["memory"],
                optional_capabilities=[], conditional_capabilities=[], pending_capabilities=[],
                forbidden_capabilities=[], constraints=[], decision_trace=[], replan_trace=[],
                score=1.0, signal_snapshot={},
            )

    class EffectfulMemory:
        effectful = True
        def __call__(self, context):
            return {"task_id": context["task_id"], "invoked": True, "gate_passed": True, "evidence_refs": ["memory:fixture"]}

    token = EventWriterGeneration(1, "capability-binding"); install_generation(tmp_path, token)
    journal = EffectJournal(tmp_path, token); dispatch, reconcile = _ports()
    request = _request()
    receipt = UnifiedRuntime(planner=Planner()).run(
        request, capability_invokers={"memory": EffectfulMemory()}, online_invoker=_online,
        effect_journal=journal, effect_dispatch=dispatch, effect_reconcile=reconcile,
        effect_fenced=True,
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "evidence": "v"},
        learning=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "evidence": "l"},
    )
    assert receipt["effect_journal_bindings"][0]["project_root"] == str(tmp_path)
    assert UnifiedRuntime(planner=Planner()).finalize_receipt(
        receipt, verifier={"invoked": True, "gate_passed": True, "evidence": "v"},
        learning={"invoked": True, "gate_passed": True, "evidence": "l"}, effect_journal=journal,
    )["receipt_complete"] is True
    other = tmp_path / "copy-root"; other.mkdir(); shutil.copytree(tmp_path / ".nexus", other / ".nexus")
    copied = EffectJournal(other, token)
    with pytest.raises(EffectJournalError, match="EFFECT_JOURNAL_ID_MISMATCH"):
        UnifiedRuntime(planner=Planner()).finalize_receipt(
            receipt, verifier={"invoked": True, "gate_passed": True, "evidence": "v"},
            learning={"invoked": True, "gate_passed": True, "evidence": "l"}, effect_journal=copied,
        )


def test_local_effect_finalize_and_copied_journal_are_bound(tmp_path):
    class Planner:
        def plan(self, **_):
            return CapabilityPlan(
                schema_version="nexus_capability_plan_v1",
                selected_capabilities=["local_model_executor"], required_capabilities=["local_model_executor"],
                optional_capabilities=[], conditional_capabilities=[], pending_capabilities=[],
                forbidden_capabilities=[], constraints=[], decision_trace=[], replan_trace=[],
                score=1.0, signal_snapshot={},
            )

    token = EventWriterGeneration(1, "local-binding"); install_generation(tmp_path, token)
    journal = EffectJournal(tmp_path, token); port_calls=[]; dispatch, reconcile = _ports(port_calls)
    request = _request(local_enabled=True, online_enabled=False)
    receipt = UnifiedRuntime(planner=Planner(), local_service=_LocalService()).run(
        request, effect_journal=journal, effect_dispatch=dispatch, effect_reconcile=reconcile,
        effect_fenced=True,
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "evidence": "v"},
        learning=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "evidence": "l"},
    )
    assert receipt["local"]["status"] == "SUCCEEDED"
    assert receipt["effect_journal_bindings"]
    assert port_calls == ["dispatch"]
    finalized = UnifiedRuntime(planner=Planner()).finalize_receipt(
        receipt, verifier={"invoked": True, "gate_passed": True, "evidence": "v"},
        learning={"invoked": True, "gate_passed": True, "evidence": "l"}, effect_journal=journal,
    )
    assert finalized["receipt_complete"] is True
    other = tmp_path / "copy-root"; other.mkdir(); shutil.copytree(tmp_path / ".nexus", other / ".nexus")
    with pytest.raises(EffectJournalError, match="EFFECT_JOURNAL_ID_MISMATCH"):
        UnifiedRuntime(planner=Planner()).finalize_receipt(
            receipt, verifier={"invoked": True, "gate_passed": True, "evidence": "v"},
            learning={"invoked": True, "gate_passed": True, "evidence": "l"}, effect_journal=EffectJournal(other, token),
        )


def test_replan_reads_parent_effects_and_rejects_other_root(tmp_path):
    token = EventWriterGeneration(1, "replan-binding"); install_generation(tmp_path, token)
    journal = EffectJournal(tmp_path, token); dispatch, reconcile = _ports(); calls=[]
    def online(context):
        calls.append(context["task_id"])
        return normalize_online_invoker_payload(provider="fixture", task_id=context["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response={"ok": True}, evidence_refs=["fixture:effect"])
    runtime = UnifiedRuntime(planner=_Planner()); request = _request()
    failed = runtime.run(request, online_invoker=online, effect_journal=journal, effect_dispatch=dispatch, effect_reconcile=reconcile, effect_fenced=True, verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "v"}, learning=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "evidence": "l"})
    assert failed["terminal_status"] == "INCOMPLETE"
    retried = runtime.run_replan(failed, request, online_invoker=online, effect_journal=journal, effect_dispatch=dispatch, effect_reconcile=reconcile, effect_fenced=True, verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "status": "SUCCEEDED", "evidence": "v"}, learning=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "evidence": "l"})
    assert retried["execution_attempt"]["attempt_number"] == 2
    assert len(calls) == 2
    other = tmp_path / "other"; install_generation(other, token)
    with pytest.raises(ValueError, match="replan_effect_binding_mismatch"):
        runtime.run_replan(failed, request, online_invoker=online, effect_journal=EffectJournal(other, token), effect_dispatch=dispatch, effect_reconcile=reconcile, effect_fenced=True)
