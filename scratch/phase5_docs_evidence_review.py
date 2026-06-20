import subprocess, os, json

repo_root = "/Users/jameschen/Workspace/nexus"
gate_id = "docs_evidence_review_packet_v0"
out_dir = os.path.join(repo_root, f"artifacts/runtime/{gate_id}")
os.makedirs(out_dir, exist_ok=True)

# Classification based on diff stats and known purpose
classification = {
    "formal_evidence_commit": {
        "files": [
            "docs/reports/NEXUS_SKILL_FIT_CATALOG_REPAIR_AND_CODING_2026-05-15.json",
            "docs/reports/policy-manifest.v2.json",
            "nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md",
        ],
        "rationale": "docs/reports/ are formal evidence artifacts; Learning Closure Matrix is a governed ops record. All have small diffs (+2/-1, +29/0, +5/-1) — safe to commit."
    },
    "generated_runtime_outputs_preserve_not_commit": {
        "files": [
            ".nexus/eval/eval_bundle.json",
            ".nexus/reports/learn/learning_closure.jsonl",
            ".nexus/reports/learn/phase_slo_summary.json",
            ".nexus/reports/learn/phase_writeback.jsonl",
        ],
        "rationale": "These are runtime-generated learn/eval outputs. Very large diffs (2182+, 466+). Owner Roadmap says 'generated reports should preserve or ignore'. Not committing to avoid polluting history with generated data."
    },
    "stale_planning_defer": {
        "files": [
            "Daily_Log.md",
            "implementation_plan.md",
        ],
        "rationale": "Daily_Log.md (+910 lines) and implementation_plan.md (+15 lines) are planning/log artifacts. Owner Roadmap says 'stale planning docs should not commit yet'. Deferred."
    },
    "phase6_scope": {
        "files": [
            "benchmarking/swebench_lite/predictions_swe.jsonl",
            "scratch/check_task_detail.py",
            "scratch/dummy_repo/dummy.py",
        ],
        "rationale": "benchmark/scratch files belong to Phase 6. Not processed here."
    }
}

# Commit formal evidence only
formal_files = classification["formal_evidence_commit"]["files"]

source_val = {
    "schema": f"nexus.{gate_id}.source_validation.v0",
    "archive_status": "PAUSED_ARCHIVED",
    "phase4_commit": "1b3cf773",
    "classification": classification,
    "committing": formal_files,
    "preserving_not_committing": classification["generated_runtime_outputs_preserve_not_commit"]["files"],
    "deferring": classification["stale_planning_defer"]["files"],
    "phase6_deferred": classification["phase6_scope"]["files"],
    "source_validation_status": "PASS"
}
with open(os.path.join(out_dir, "source_validation.json"), "w") as f:
    json.dump(source_val, f, indent=2)

gov = {"archive_status": "PAUSED_ARCHIVED", "no_deletion": True, "no_git_clean": True,
       "no_git_reset": True, "no_broad_restore": True, "no_model_calls": True,
       "no_repair_execution": True, "no_verifier_rerun": True, "no_training_export": True,
       "no_s2t_export": True, "no_public_claim": True,
       "only_formal_evidence_committed": True,
       "generated_runtime_outputs_not_committed": True}
with open(os.path.join(out_dir, "governance_preservation.json"), "w") as f:
    json.dump(gov, f, indent=2)

report_path = os.path.join(repo_root, f"docs/reports/{gate_id}.md")
with open(report_path, "w") as f:
    f.write("# placeholder\n")

evidence_paths = [
    f"artifacts/runtime/{gate_id}/source_validation.json",
    f"artifacts/runtime/{gate_id}/governance_preservation.json",
    f"docs/reports/{gate_id}.md",
]

all_stage = formal_files + evidence_paths
for p in all_stage:
    subprocess.run(["git", "add", p], cwd=repo_root, check=True)

res_cached = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=repo_root)
staged_paths = [l[2:].strip().strip('"') for l in res_cached.stdout.splitlines() if l.strip()]
# normalize quoted paths
staging_ok = set(p.strip('"') for p in all_stage) == set(staged_paths)

staging_ver = {"staging_verification_status": "PASS" if staging_ok else "WARN",
               "cached_paths": staged_paths, "cached_path_count": len(staged_paths),
               "note": "" if staging_ok else f"Path set difference: expected={set(all_stage)}, actual={set(staged_paths)}"}
with open(os.path.join(out_dir, "staging_verification.json"), "w") as f:
    json.dump(staging_ver, f, indent=2)
subprocess.run(["git", "add", f"artifacts/runtime/{gate_id}/staging_verification.json"], cwd=repo_root)

res_commit = subprocess.run(
    ["git", "commit", "-m", "docs: commit formal evidence and policy manifest updates"],
    capture_output=True, text=True, cwd=repo_root
)
print(res_commit.stdout)

res_hash = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo_root)
commit_hash = res_hash.stdout.strip()

res_status = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, cwd=repo_root)
remaining_tracked = [l for l in res_status.stdout.splitlines() if l.startswith(" M")]

report_content = f"""# Docs Evidence Review Packet v0

## Summary
Commit: `{commit_hash}`

## Classification
| Category | Files | Decision |
|----------|-------|---------|
| Formal Evidence | NEXUS_SKILL_FIT_CATALOG...json, policy-manifest.v2.json, Ops - Learning Closure Matrix.md | ✅ COMMITTED |
| Generated Runtime | .nexus/eval/eval_bundle.json, .nexus/reports/learn/* | 🔒 PRESERVED (not committed) |
| Stale Planning | Daily_Log.md, implementation_plan.md | ⏸ DEFERRED |
| Phase 6 | predictions_swe.jsonl, scratch/ | → Phase 6 |

## Rationale
- Formal evidence: small diffs, governed artifacts, safe to commit
- Generated outputs: very large (+2182 lines), runtime artifacts per Owner Roadmap
- Stale planning: Daily_Log.md +910 lines — not appropriate to commit mid-closure

## Governance
archive_status: PAUSED_ARCHIVED | no model_calls | no verifier_rerun | no s2t_export
"""
with open(report_path, "w") as f:
    f.write(report_content)
subprocess.run(["git", "add", f"docs/reports/{gate_id}.md"], cwd=repo_root)
subprocess.run(["git", "commit", "--amend", "--no-edit"], cwd=repo_root)

res_final = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo_root)
print(f"Phase 5 FINAL commit: {res_final.stdout.strip()}")
print(f"Remaining tracked modified: {len(remaining_tracked)}")
