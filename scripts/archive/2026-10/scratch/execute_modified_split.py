import subprocess
import os
import json

repo_root = "/Users/jameschen/Workspace/nexus"
out_dir = os.path.join(repo_root, "artifacts/runtime/modified_files_review_packet_split_v0")
os.makedirs(out_dir, exist_ok=True)

# 1. 讀取 git status
res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=repo_root)
lines = res.stdout.splitlines()

modified_files = []
untracked_count = 0
tracked_deleted_count = 0
staged_count = 0

for line in lines:
    if not line.strip():
        continue
    status = line[:2]
    path = line[3:].strip().strip('"')
    
    if "M" in status:
        modified_files.append(path)
    elif "D" in status:
        tracked_deleted_count += 1
    elif status == "??":
        untracked_count += 1
        
    if status.startswith("A") or status.startswith("M") and not status.startswith(" "):
        staged_count += 1

# 2. 分類 modified files
runtime_code_candidates = []
test_candidates = []
docs_evidence_candidates = []
generated_cache_modified = []
scratch_debug_modified = []
benchmark_experiment_modified = []
unknown_candidates = []

classified_items = []

for path in modified_files:
    path_lower = path.lower()
    
    category = "unknown_requires_owner_review"
    reason = "Requires explicit classification review."
    
    # 規則判定
    if "__pycache__" in path_lower or path_lower.endswith(".pyc") or path == ".tmp_build":
        category = "generated_cache_modified"
        reason = "Python cache or compile artifact modified by runtime environment."
        generated_cache_modified.append(path)
    elif path.startswith("nexus-core-rs/src/") or (path.startswith("nexus/") and not "experimental" in path and not "__pycache__" in path):
        category = "runtime_code_candidate"
        reason = "Local model repair or core engine runtime source code modified."
        runtime_code_candidates.append(path)
    elif path.startswith("tests/") and not "__pycache__" in path:
        category = "test_candidate"
        reason = "Test suite file modified."
        test_candidates.append(path)
    elif path == "Daily_Log.md" or path == "implementation_plan.md" or path.startswith("docs/reports/") or path.startswith(".nexus/"):
        category = "docs_or_evidence_candidate"
        reason = "Workspace log, planning document, or historical execution reports."
        docs_evidence_candidates.append(path)
    elif path.startswith("scratch/") or path.startswith("scripts/") or "parse_test" in path_lower:
        category = "scratch_or_debug_modified"
        reason = "Ad-hoc debugging or helper automation script."
        scratch_debug_modified.append(path)
    elif path.startswith("benchmarking/"):
        category = "benchmark_or_experiment_modified"
        reason = "Benchmark prediction output modified."
        benchmark_experiment_modified.append(path)
    else:
        unknown_candidates.append(path)
        
    classified_items.append({
        "path": path,
        "category": category,
        "reason": reason
    })

# 寫入 classification_table.jsonl
with open(os.path.join(out_dir, "modified_file_classification_table.jsonl"), "w", encoding="utf-8") as f:
    for item in classified_items:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

# A. 寫入 source_validation.json
source_val = {
    "schema": "nexus.modified_files_review_packet_split_source_validation.v0",
    "archive_status": "PAUSED_ARCHIVED",
    "duplicate_adr_cleanup_only_v0_evidence_committed": True,
    "untracked_duplicate_adr_removed": True,
    "no_execution_authorized": True,
    "source_validation_status": "PASS"
}
with open(os.path.join(out_dir, "source_validation.json"), "w", encoding="utf-8") as f:
    json.dump(source_val, f, indent=2, ensure_ascii=False)

# B. 寫入 current_modified_status_snapshot.json
snapshot = {
    "schema": "nexus.modified_files_current_modified_status_snapshot.v0",
    "current_branch": "feature/bridge-fastmatcher-20260606",
    "head_commit": "f328f58a",
    "tracked_modified_count": len(modified_files),
    "tracked_deleted_count": tracked_deleted_count,
    "untracked_count": untracked_count,
    "staged_count": staged_count,
    "top_level_modified_paths": sorted(list(set([p.split("/")[0] for p in modified_files])))
}
with open(os.path.join(out_dir, "current_modified_status_snapshot.json"), "w", encoding="utf-8") as f:
    json.dump(snapshot, f, indent=2, ensure_ascii=False)

# C. 寫入 runtime_code_review_packet_proposal.json
runtime_prop = {
    "category": "runtime_code_candidate",
    "count": len(runtime_code_candidates),
    "paths": runtime_code_candidates,
    "recommended_owner_action": "APPROVE_RUNTIME_CODE_REVIEW_PACKET",
    "explanation": "These are active source code modifications. They should be reviewed in a dedicated step before deciding to discard (git restore) or commit."
}
with open(os.path.join(out_dir, "runtime_code_review_packet_proposal.json"), "w", encoding="utf-8") as f:
    json.dump(runtime_prop, f, indent=2, ensure_ascii=False)

# D. 寫入 test_review_packet_proposal.json
test_prop = {
    "category": "test_candidate",
    "count": len(test_candidates),
    "paths": test_candidates,
    "recommended_owner_action": "APPROVE_TEST_REVIEW_PACKET",
    "explanation": "Test suite file modifications. Should be reviewed separately to ensure test alignment."
}
with open(os.path.join(out_dir, "test_review_packet_proposal.json"), "w", encoding="utf-8") as f:
    json.dump(test_prop, f, indent=2, ensure_ascii=False)

# E. 寫入 docs_evidence_review_packet_proposal.json
docs_prop = {
    "category": "docs_or_evidence_candidate",
    "count": len(docs_evidence_candidates),
    "paths": docs_evidence_candidates,
    "recommended_owner_action": "APPROVE_DOCS_EVIDENCE_REVIEW_PACKET",
    "explanation": "Planning logs or phase execution summaries. Safe to commit or preserve."
}
with open(os.path.join(out_dir, "docs_evidence_review_packet_proposal.json"), "w", encoding="utf-8") as f:
    json.dump(docs_prop, f, indent=2, ensure_ascii=False)

# F. 寫入 restore_ignore_candidate_proposal.json
restore_prop = {
    "category": "generated_cache_modified",
    "count": len(generated_cache_modified),
    "paths": generated_cache_modified,
    "recommended_owner_action": "APPROVE_RESTORE_GENERATED_MODIFIED_FILES_ONLY",
    "explanation": "These are dynamic pycache artifacts. We can safely restore them using `git restore` since they are generated dynamically by Python."
}
with open(os.path.join(out_dir, "restore_ignore_candidate_proposal.json"), "w", encoding="utf-8") as f:
    json.dump(restore_prop, f, indent=2, ensure_ascii=False)

# G. 寫入 owner_decision_options.json
options = {
    "schema": "nexus.modified_files_split_owner_options.v0",
    "current_state": "SPLIT_READY",
    "default_decision": "AWAIT_OWNER_APPROVAL",
    "options": [
        "APPROVE_RESTORE_GENERATED_MODIFIED_FILES_ONLY",
        "APPROVE_RUNTIME_CODE_REVIEW_PACKET",
        "APPROVE_TEST_REVIEW_PACKET",
        "APPROVE_DOCS_EVIDENCE_REVIEW_PACKET",
        "REMAIN_PAUSED_NO_ACTION"
    ]
}
with open(os.path.join(out_dir, "owner_decision_options.json"), "w", encoding="utf-8") as f:
    json.dump(options, f, indent=2, ensure_ascii=False)

# H. 寫入 governance_preservation.json
gov = {
    "schema": "nexus.local_7b_14b_repair_split_governance_preservation.v0",
    "archive_status": "PAUSED_ARCHIVED",
    "no_deletion": True,
    "no_git_clean": True,
    "no_git_reset": True,
    "no_git_restore": True,
    "no_staging": True,
    "no_commit": True,
    "no_source_modification": True,
    "no_test_modification": True,
    "no_model_calls": True,
    "no_repair_execution": True,
    "no_verifier_rerun": True,
    "no_training_export": True,
    "no_s2t_export": True,
    "no_public_claim": True,
    "no_runtime_routing_integration": True,
    "no_strata_s1_connection": True,
    "no_next_expansion": True
}
with open(os.path.join(out_dir, "governance_preservation.json"), "w", encoding="utf-8") as f:
    json.dump(gov, f, indent=2, ensure_ascii=False)

print("Classification and proposals generated successfully.")
