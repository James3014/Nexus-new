import json, os, uuid
from pathlib import Path
from nexus.core.state_contracts import Plan, NexusDiagnosis, NexusRepair, AuditResult, NexusDerivation, DerivationStep, NexusManifest

task_id = "formal-e2e-001"
run_dir = Path(f".nexus/runs/task-{task_id}")
run_dir.mkdir(parents=True, exist_ok=True)

# 1. P (Plan)
plan = Plan(
    task_id=task_id, goal="Fix consensus drift", actions=["Verify hash"],
    traceid=str(uuid.uuid4())
)
# Note: Plan model in state_contracts doesn't have reasoning_mode/invariants directly yet, 
# but they are mentioned in taskboard for plan.json. 
# We'll use metadata for extra fields if needed.
with open(run_dir / "plan.json", "w") as f: f.write(plan.model_dump_json(indent=2))

# 2. D (Diagnosis)
diag = NexusDiagnosis(
    task_id=task_id, status="FAIL", summary="Hash drift detected",
    reasoning_mode="FORMAL", violated_invariants=["hash_match == True"]
)
with open(run_dir / "diagnosis.json", "w") as f: f.write(diag.model_dump_json(indent=2))

# 3. E (Derivation) - NEW
derivation = NexusDerivation(
    task_id=task_id, goal="Fix consensus drift",
    invariants=["hash_match == True"],
    steps=[
        DerivationStep(step_index=0, operation="Rewrite", rationale="Apply hash fusion law")
    ],
    final_equivalence_proven=True
)
with open(run_dir / "derivation.json", "w") as f: f.write(derivation.model_dump_json(indent=2))

# 4. R (Repair)
repair = NexusRepair(
    task_id=task_id, patch_hash="abc12345",
    reasoning_mode="FORMAL", rewrite_trace=["apply fusion_law"],
    resolved_invariants=["hash_match == True"]
)
with open(run_dir / "repairfinal.json", "w") as f: f.write(repair.model_dump_json(indent=2))

# 5. A (Audit)
audit = AuditResult(
    audit_id="aud-001", reasoning_mode="FORMAL", formal_gate_passed=True,
    obligation_coverage_pct=100.0, audit_notes_formal=["All proofs verified"],
    repair_status="PASS", smoke_status="PASS", summary="Algebraic audit passed"
)
with open(run_dir / "auditresult.json", "w") as f: f.write(audit.model_dump_json(indent=2))

# 6. M (Manifest) - Updated to use NexusManifest model
manifest = NexusManifest(
    task_id=task_id,
    formal_reasoning={
        "gate_passed": audit.formal_gate_passed,
        "coverage": audit.obligation_coverage_pct
    },
    seal_status="SEALED"
)
with open(run_dir / "manifest.json", "w") as f: f.write(manifest.model_dump_json(indent=2))

print(f"✅ Full Chain Artifacts (including Derivation & Manifest) generated at {run_dir}")
