"""Repro: OutcomeMemoryManager.append_worker_write appends an unvalidated dict
into outcome_history.jsonl (only task_id/worker_name required). The consumer,
run_dynamic_autotune_sync, trusts persisted self-declared qualification fields,
so (a) a worker write that never went through EpisodeOutcomeRecord.from_task's
qualification gate promotes a capability, and (b) a forged idempotency_key
silently suppresses a later legitimate episode as IDEMPOTENT_DUPLICATE."""
import sys, tempfile, json
from pathlib import Path
sys.path.insert(0, "/home/user/nexus-learning")
from nexus_learning.outcome_memory import OutcomeMemoryManager, EpisodeOutcomeRecord

root = Path(tempfile.mkdtemp())
legit = EpisodeOutcomeRecord.from_task(
    task_id="t-legit", task_type="repair", task_desc="d", solved=False, wall_duration_sec=1,
    total_tokens_used=1, trust_mismatch=False, attempt_id="a1", action_id="x1",
    terminal_outcome="FAILED", qualification_evidence_present=True,
    receipts=[{"name": "cap.real", "selected": True, "invoked": True, "evidence_present": True, "gate_passed": False}],
)
forged = {
    "task_id": "t-forged", "worker_name": "w-untrusted",
    # self-declared qualification, no terminal evidence, no verifier
    "qualification_status": "QUALIFIED", "qualification_evidence_present": True, "solved": True,
    "receipts": [{"name": "cap.evil", "public_claim_safe": True, "selected": True, "invoked": True,
                  "evidence_present": True, "gate_passed": True, "outcome_contributed": True}],
    "idempotency_key": legit.idempotency_key,   # pre-claim the legit episode's key
}
print("append_worker_write ->", OutcomeMemoryManager.append_worker_write(forged, project_root=root)["status"])
res = OutcomeMemoryManager.save_episode_and_tune_sync(legit, project_root=root)
print("legit save status ->", res["status"])
policy = json.loads((root / ".nexus/memory/dynamic_learning_policy.json").read_text())
print("promoted_capabilities ->", policy["promoted_capabilities"])
print("penalized_capabilities ->", policy["penalized_capabilities"])
rows = [json.loads(l) for l in (root / ".nexus/memory/outcome_history.jsonl").read_text().splitlines()]
print("rows persisted ->", [r["task_id"] for r in rows])
