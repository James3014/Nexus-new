"""UnifiedRuntime.run_replan trusts the caller-supplied previous receipt: its receipt_hash
is recomputed only over lineage fields; `effect_journal_bindings` are NOT covered. Removing `effect_journal_bindings` from an INCOMPLETE receipt whose
effect ended UNKNOWN (dispatch crashed) skips the replan_effect_binding_incomplete
guard, and attempt 2 RE-DISPATCHES the same logical effect under a new effect id
(identity includes attempt_number) -> OUTCOME_UNKNOWN becomes blind retry."""
import sys, tempfile
from pathlib import Path
sys.path[:0] = ["/home/user/nexus-runtime/src", "/home/user/nexus-runtime"]
import tests.test_runtime_operations as T
from nexus_runtime.support import build_runtime_exports
from nexus_runtime.kernel.events.writer_generation import EventWriterGeneration, install_generation
from nexus_runtime.kernel.events.effect_journal import EffectJournal, EffectDispatchPort, EffectReconcilePort

exports = build_runtime_exports()
request = exports.UnifiedRuntimeRequest(
    task_id="unk-effect", workspace_revision="rev-1", task_statement="bounded failed verifier trace",
    task_type="repair",
    route={"recommended_flow": "direct", "online_policy": "deny", "workforce_admission_enabled": True,
           "workforce_bindings": {"online": {"worker_id": "agy_flash", "provider": "agy", "model": "gemini-3.6-flash-high",
                                             "controls": ["task_card", "allowed_files", "mandatory_commands", "independent_verification"]}}},
    online_enabled=True, local_enabled=False)

root = Path(tempfile.mkdtemp())
gen = install_generation(root, EventWriterGeneration(1, "writer-a"))
journal = EffectJournal(root, gen)
dispatches = []
def dispatch(op):
    dispatches.append(len(dispatches) + 1)
    if len(dispatches) == 1:
        raise TimeoutError("connection lost after send: outcome unknown")
    return op()
port = EffectDispatchPort(dispatch)
reconcile = EffectReconcilePort(lambda record: None)   # readback unavailable

base = T._failure_invokers(exports, request)
name = sorted(base)[0]
def effectful(ctx, _f=base[name]): return _f(ctx)
effectful.effectful = True
invokers = {**base, name: effectful}
def failed_verifier(ctx):
    return {"task_id": ctx["task_id"], "invoked": True, "status": "FAILED", "gate_passed": False,
            "evidence_present": True, "evidence_refs": ["fixture:failed-verifier"]}

kw = dict(capability_invokers=invokers, verifier=failed_verifier, effect_journal=journal,
          effect_dispatch=port, effect_reconcile=reconcile)
first = exports.UnifiedRuntime().run(request, **kw)
print("first:", first["terminal_status"], "| bindings:", [(b.get("action"), b.get("state")) for b in first.get("effect_journal_bindings", [])],
      "| journal states:", [r["state"] for r in journal._locked(lambda d: list(d["records"].values()))])
try:
    exports.UnifiedRuntime().run_replan(first, request, **kw); print("honest replan: ACCEPTED")
except ValueError as e:
    print("honest replan: REJECTED ->", e)

tampered = dict(first); tampered.pop("effect_journal_bindings", None)
second = exports.UnifiedRuntime().run_replan(tampered, request, **kw)
print("tampered replan:", second["terminal_status"], "attempt", second["execution_attempt"]["attempt_number"],
      "| total dispatches of the same logical effect:", len(dispatches),
      "| journal states:", [r["state"] for r in journal._locked(lambda d: list(d["records"].values()))])

# effect_journal_bindings are outside the receipt_hash lineage: stripped receipt still validates strict
from nexus_runtime.planning.evidence.receipt_base import validate_receipt_base
print("validate_receipt_base(strict) on stripped receipt:", validate_receipt_base(tampered, mode="strict")["ok"],
      "| receipt_hash unchanged:", tampered["receipt_hash"] == first["receipt_hash"])
