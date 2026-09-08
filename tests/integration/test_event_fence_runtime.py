from __future__ import annotations
import multiprocessing
from nexus.events.effect_journal import EffectDispatchPort, EffectJournal, EffectReconcilePort, deterministic_effect_id
from nexus.engine.capability_contracts import CapabilityPlan
from nexus.services.unified_runtime import UnifiedRuntime, UnifiedRuntimeRequest
from nexus.events.writer_generation import EventWriterGeneration, install_generation

def _child(root, queue):
    token=EventWriterGeneration(1,"runtime-process")
    j=EffectJournal(root, token)
    identity={"task_id":"process-task","workspace_revision":"r1","planner_decision_id":"p1","attempt":1,"action":"online","subject_revision":"s1","request_digest":"d1"}
    try:
        result=j.execute(identity=identity, subject="process-task", request_digest="d1", dispatch=lambda: {"marker":"durable"}, reconcile=lambda r: {"marker":"reconciled"})
        queue.put(result)
    except Exception as exc:
        queue.put(type(exc).__name__)

def test_two_process_restart_reconciles_without_redispatch(tmp_path):
    token=EventWriterGeneration(1,"runtime-process"); install_generation(tmp_path, token)
    q=multiprocessing.Queue(); p=multiprocessing.Process(target=_child,args=(tmp_path,q)); p.start(); p.join(10)
    assert p.exitcode == 0; assert q.get(timeout=2)=={"marker":"durable"}
    j=EffectJournal(tmp_path, token)
    identity={"task_id":"process-task","workspace_revision":"r1","planner_decision_id":"p1","attempt":1,"action":"online","subject_revision":"s1","request_digest":"d1"}
    assert j.get(deterministic_effect_id(identity))["state"] == "COMPLETED"
    assert j.execute(identity=identity, subject="process-task", request_digest="d1", dispatch=lambda: (_ for _ in ()).throw(AssertionError("redispatch")), reconcile=lambda _: None)=={"marker":"durable"}


class _RuntimePlanner:
    def plan(self, **_):
        return CapabilityPlan(schema_version="nexus_capability_plan_v1", selected_capabilities=[], required_capabilities=[], optional_capabilities=[], conditional_capabilities=[], pending_capabilities=[], forbidden_capabilities=[], constraints=[], decision_trace=[], replan_trace=[], score=1.0, signal_snapshot={"route_truth_source": "CapabilityPlanner"})

def _crash_after_effect_marker(root, marker):
    token=EventWriterGeneration(1,"crash-process")
    j=EffectJournal(root, token)
    def dispatch(ctx):
        marker.write_text("effect-once", encoding="utf-8")
        with marker.open("a", encoding="utf-8") as fh:
            fh.flush()
            import os
            os.fsync(fh.fileno())
        os._exit(23)
    request = UnifiedRuntimeRequest(task_id="crash-task", workspace_revision="r1", task_statement="crash probe", task_type="repair", route={"injected_transport": True}, online_enabled=True)
    UnifiedRuntime(planner=_RuntimePlanner()).run(request, online_invoker=dispatch, effect_journal=j, effect_dispatch=EffectDispatchPort(lambda operation: operation()), effect_reconcile=EffectReconcilePort(lambda _: None), effect_fenced=True, verifier=lambda _: {"invoked": True, "gate_passed": True, "evidence": "v"}, learning=lambda _: {"invoked": True, "gate_passed": True, "evidence": "l"})

def test_crash_after_effect_marker_reconciles_without_second_dispatch(tmp_path):
    token=EventWriterGeneration(1,"crash-process"); install_generation(tmp_path, token)
    marker=tmp_path / "effect.marker"
    p=multiprocessing.Process(target=_crash_after_effect_marker,args=(tmp_path,marker)); p.start(); p.join(10)
    assert p.exitcode == 23
    assert marker.read_text(encoding="utf-8") == "effect-once"
    j=EffectJournal(tmp_path, token)
    import json
    saved=json.loads((tmp_path / ".nexus/events/effect_journal.v1.json").read_text(encoding="utf-8"))["records"]
    effect, record = next(iter(saved.items()))
    assert record["state"] == "DISPATCHED"
    observed=j.reconcile(effect, {"operation_id": record["operation_id"], "effect_id": record["effect_id"], "subject": record["subject"], "request_digest": record["request_digest"], "generation": record["generation"], "result": {"marker": marker.read_text(encoding="utf-8")}})
    assert observed == {"marker":"effect-once"}
    assert j.get(effect)["state"] == "COMPLETED"

def test_reserved_pending_crash_without_reconciler_is_unknown(tmp_path):
    token=EventWriterGeneration(1,"pending-process"); install_generation(tmp_path, token)
    j=EffectJournal(tmp_path, token)
    identity={"task_id":"pending-task","workspace_revision":"r1","planner_decision_id":"p1","attempt":1,"action":"local","subject_revision":"s1","request_digest":"pending"}
    record=j.reserve(identity=identity, subject="pending-task", request_digest="pending")
    assert record["state"] == "PENDING"
    unknown=j.execute(identity=identity, subject="pending-task", request_digest="pending", dispatch=lambda: (_ for _ in ()).throw(AssertionError("dispatch")), reconcile=None)
    assert unknown is None
    assert j.get(deterministic_effect_id(identity))["state"] == "UNKNOWN"
