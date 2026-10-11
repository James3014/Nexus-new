"""ExecutionCoordinator.run_owned_attempt(custom_runner=...) (and launch(custom_runner=...))
never calls _ensure_effect_authorization / _ensure_tool_projection / host preparation.
A durable request that REQUIRES effect authorization but carries an EXPIRED and
TAMPERED authorization is rejected by execute_attempt yet runs to
PENDING_HUMAN_APPROVAL via the custom-runner path. Uses the repo's own test stubs.
Also: the authorization hash is unkeyed -> a widened authorization rebuilt by the
caller is accepted by execute_attempt (integrity only, not authority)."""
import copy, sys
sys.path[:0] = ["/home/user/nexus-runtime/src", "/home/user/nexus-runtime"]
import tests.test_execution_coordination as T
from nexus_runtime.execution_coordination import EffectAuthorization, MissingExecutionBindingError, WorkerOutcome

def bad_request():
    req = T._effect_authorized_request()
    a = req["effect_authorization"]
    a["expires_at"] = "2000-01-01T00:00:00+00:00"                     # expired
    a["effects"]["filesystem"]["write_paths"].append("/etc/passwd")    # tampered (hash now stale)
    return req

# 1) canonical path rejects
coord, state, worker, target, fin = T.build([T.Receipt("codex", WorkerOutcome.EXECUTION_COMPLETED.value, True)])
state.snapshot["request"] = bad_request()
try:
    coord.execute_attempt("task", "att"); print("execute_attempt: ACCEPTED (unexpected)")
except MissingExecutionBindingError as e:
    print("execute_attempt: REJECTED ->", e, "| leases:", target.initial_leases)

# 2) alternate custom_runner path on the same durable request
coord, state, worker, target, fin = T.build([])
state.snapshot["request"] = bad_request()
ran = []
def custom_runner(contract, request, update):
    ran.append(request["effect_authorization"]["effects"]["filesystem"]["write_paths"])
    update("CUSTOM_EFFECTS_DONE", {"wrote": "/etc/passwd"})
    return {"promotion_status": "PENDING_HUMAN_APPROVAL"}
coord.run_owned_attempt("task", "att", custom_runner)
print("run_owned_attempt(custom_runner): status =", state.snapshot["status"], "| events =", state.events,
      "| failures =", fin.failures, "| effect_authorization persisted:", "effect_authorization" in state.snapshot)

# 3) authority is self-asserted: caller rebuilds a WIDER authorization with a fresh valid hash
coord, state, worker, target, fin = T.build([T.Receipt("codex", WorkerOutcome.EXECUTION_COMPLETED.value, True)])
req = T._effect_authorized_request()
a = EffectAuthorization.from_mapping(req["effect_authorization"])
wide = EffectAuthorization.build(authority_id="anyone", authority_ref="nothing#0", operation_id=a.operation_id,
    attempt_id=a.attempt_id, repository=a.repository, source_revision=a.source_revision, base_revision=a.base_revision,
    workspace_id=a.workspace_id, target_id=a.target_id,
    effects={**copy.deepcopy(dict(a.effects)), "filesystem": {"write_paths": ["src/a.py", "/"]}, "network": {"hosts": ["*"]}})
req["effect_authorization"] = wide.to_dict()
state.snapshot["request"] = req
coord.execute_attempt("task", "att")
print("execute_attempt with self-minted wider authorization: worker invocations =", worker.invocations,
      "| durable authority_id =", state.snapshot["effect_authorization"]["authority_id"])
