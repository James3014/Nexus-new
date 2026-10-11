"""Repro: the Workbench session/notebook/checkpoint target_identity never participates
in execution or completion. An Observation produced by a LocalReadOnlyExecutor bound to a
DIFFERENT Git target (repo B) is accepted as completed lineage for a session whose
notebook/checkpoint target_identity is repo A; ResumeCoordinator.publish advances to COMPLETE."""
import sys, json, subprocess, tempfile
from pathlib import Path
sys.path.insert(0, "/home/user/nexus-workbench/src")
from nexus_workbench import (ActionCell, ActionMode, JsonWorkbenchStore, ResumeCheckpoint, ResumeCoordinator,
                             ResumePhase, ResumeRequest, WorkbenchNotebook)
from nexus_workbench.read_only_executor import LocalReadOnlyExecutor

tmp = Path(tempfile.mkdtemp())
def repo(name, text):
    r = tmp / name; r.mkdir()
    (r / "README.md").write_text(text)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "i"]):
        subprocess.run(["git", *c], cwd=r, check=True)
    return r
A, B = repo("A", "repo A\n"), repo("B", "repo B (wrong target)\n")
exA = LocalReadOnlyExecutor.bind(A, tmp / "scratchA")
exB = LocalReadOnlyExecutor.bind(B, tmp / "scratchB")
S, TARGET = "wb-1", exA.target_identity

store = JsonWorkbenchStore(tmp / "store"); co = ResumeCoordinator(store)
s1 = ActionCell(workbench_session_id=S, step_id="S1", notebook_revision=1, intent="read readme",
                mode=ActionMode.READ_ONLY_PROBE, requested_capabilities=("repo.read",),
                code_or_action=json.dumps({"op": "repo.read", "path": "README.md"}))
nb1 = WorkbenchNotebook(workbench_session_id=S, task_id="t", operation_id="o", attempt_id="a",
                        target_identity=TARGET, goal="inspect repo A", revision=1)
store.save_notebook(nb1)
cp1 = ResumeCheckpoint(checkpoint_id="cp-1", workbench_session_id=S, task_id="t", operation_id="o",
                       attempt_id="a", target_identity=TARGET, sequence=1, notebook_revision=1,
                       notebook_hash=nb1.content_hash, phase=ResumePhase.READY_FOR_ACTION, next_action=s1)
co.publish(cp1)
rcpt = co.resume(ResumeRequest(workbench_session_id=S, task_id="t", operation_id="o", attempt_id="a",
                               target_identity=TARGET, resumer_identity="w", resumer_model_identity="m"))
print("resume disposition:", rcpt.disposition.value)
obs = exB.execute(rcpt.next_action)                 # executed against the WRONG target
store.save_observation(obs)
print("observation outcome:", obs.outcome.value, "| text read:", obs.physical_readback["result"]["text"].strip())
print("session target == observed baseline target?", TARGET == obs.physical_readback["baseline"]["identity"])
nb2 = WorkbenchNotebook(workbench_session_id=S, task_id="t", operation_id="o", attempt_id="a",
                        target_identity=TARGET, goal="inspect repo A", observation_refs=("S1",), revision=2)
store.save_notebook(nb2)
head, inflight = store.load_resume_state(S)
cp3 = ResumeCheckpoint(checkpoint_id="cp-3", workbench_session_id=S, task_id="t", operation_id="o",
                       attempt_id="a", target_identity=TARGET, sequence=inflight.sequence + 1,
                       previous_checkpoint_id=inflight.checkpoint_id, previous_checkpoint_hash=inflight.checkpoint_hash,
                       notebook_revision=2, notebook_hash=nb2.content_hash, phase=ResumePhase.COMPLETE,
                       completed_step_ids=("S1",), observation_refs=("S1",))
co.publish(cp3)
final = co.resume(ResumeRequest(workbench_session_id=S, task_id="t", operation_id="o", attempt_id="a",
                                target_identity=TARGET, resumer_identity="w2", resumer_model_identity="m2"))
print("publish COMPLETE accepted; final resume disposition:", final.disposition.value)
