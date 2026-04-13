import json, os, uuid
from pathlib import Path
from nexus.core.state_contracts import Plan, NexusDiagnosis, NexusRepair, AuditResult

task_id = "formal-e2e-002"
run_dir = Path(f".nexus/runs/task-{task_id}")
run_dir.mkdir(parents=True, exist_ok=True)

# 1. P (Plan) - 故意放置一個無法滿足的不變量
plan = Plan(
    task_id=task_id, goal="Fix quantum leakage", actions=["Stabilize core"],
    reasoning_mode="FORMAL", 
    invariants=["core_temp == 0K"], # 物理上極難滿足
    proof_obligations=["Prove zero entropy"]
)
with open(run_dir / "plan.json", "w") as f: f.write(plan.model_dump_json(indent=2))

# 2. D (Diagnosis) - 明確紀錄違反的不變量
diag = NexusDiagnosis(
    task_id=task_id, status="FAIL", summary="Thermal drift detected",
    reasoning_mode="FORMAL", 
    violated_invariants=["core_temp == 0K"],
    failed_proof_obligations=["Prove zero entropy"]
)
with open(run_dir / "diagnosis.json", "w") as f: f.write(diag.model_dump_json(indent=2))

# 3. R (Repair) - 紀錄 unresolved 狀態
repair = NexusRepair(
    task_id=task_id, patch_hash="FAILED_PATCH",
    reasoning_mode="FORMAL", 
    rewrite_trace=["Attempt identity transform"],
    resolved_invariants=[], # 失敗，未修復
    equivalence_claim="FAILED: Invariant breach persists"
)
with open(run_dir / "repairfinal.json", "w") as f: f.write(repair.model_dump_json(indent=2))

# 4. A (Audit) - 明確出現 formal_gate_passed: false
audit = AuditResult(
    audit_id="aud-002", reasoning_mode="FORMAL", 
    formal_gate_passed=False, # ❌ 關鍵失敗標記
    obligation_coverage_pct=0.0, 
    audit_notes_formal=["Mandatory proof 'Prove zero entropy' was not satisfied"],
    repair_status="FAIL", smoke_status="FAIL", summary="Formal audit REJECTED due to invariant breach"
)
with open(run_dir / "auditresult.json", "w") as f: f.write(audit.model_dump_json(indent=2))

# 5. M (Manifest) - 保留失敗摘要與 Lineage
manifest = {
    "task_id": task_id,
    "formal_reasoning": {
        "gate_passed": audit.formal_gate_passed,
        "coverage": audit.obligation_coverage_pct,
        "reject_reason": "Proof Obligation Unmet"
    },
    "seal_status": "SEALED_FAILURE",
    "timestamp": "2026-04-11T08:00:00Z"
}
with open(run_dir / "manifest.json", "w") as f: json.dump(manifest, f, indent=2)

print(f"✅ Failure Chain Artifacts generated at {run_dir}")
