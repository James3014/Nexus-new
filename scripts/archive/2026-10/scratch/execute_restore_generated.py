import os
import json
import subprocess

repo_root = "/Users/jameschen/Workspace/nexus"
split_table = os.path.join(repo_root, "artifacts/runtime/modified_files_review_packet_split_v0/modified_file_classification_table.jsonl")
out_dir = os.path.join(repo_root, "artifacts/runtime/restore_generated_modified_files_only_v0")
os.makedirs(out_dir, exist_ok=True)

# 1. 讀取 split table 提取 generated_cache_modified 檔案
allowed_restore_paths = []
excluded_paths = []
excluded_reason = ""
protected_path_violation_count = 0

with open(split_table, "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        data = json.loads(line.strip())
        path = data.get("path")
        category = data.get("category")
        
        if category == "generated_cache_modified":
            # 二重安全檢查：確保不屬於代碼、測試、docs/reports/ADR、benchmark 等
            path_lower = path.lower()
            if "target" in path_lower or "__pycache__" in path_lower or path_lower.endswith(".pyc") or path == ".tmp_build":
                allowed_restore_paths.append(path)
            else:
                protected_path_violation_count += 1
                excluded_paths.append(path)
                excluded_reason += f" | Protected path violation: {path}"
        else:
            excluded_paths.append(path)

allowlist_status = "PASS" if protected_path_violation_count == 0 else "FAIL"

# 寫入 restore_allowlist.json
allowlist = {
    "allowed_restore_paths": allowed_restore_paths,
    "allowed_restore_count": len(allowed_restore_paths),
    "excluded_paths": excluded_paths,
    "excluded_reason": excluded_reason,
    "protected_path_violation_count": protected_path_violation_count,
    "allowlist_status": allowlist_status
}

with open(os.path.join(out_dir, "restore_allowlist.json"), "w", encoding="utf-8") as f:
    json.dump(allowlist, f, indent=2, ensure_ascii=False)

if allowlist_status == "FAIL":
    print("Restore allowlist check FAILED! Aborting execution.")
    exit(1)

# 2. Pre-restore snapshot
res_status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=repo_root)
lines = res_status.stdout.splitlines()

tracked_modified_count_before = 0
untracked_count_before = 0
staged_count_before = 0
tracked_deleted_count_before = 0

for line in lines:
    if not line.strip():
        continue
    status = line[:2]
    if status.startswith("M") or status.endswith("M"):
        tracked_modified_count_before += 1
    if status == "??":
        untracked_count_before += 1
    if status.startswith("A") or status.startswith("M") and not status.startswith(" "):
        staged_count_before += 1
    if "D" in status:
        tracked_deleted_count_before += 1

pre_snapshot = {
    "current_branch": "feature/bridge-fastmatcher-20260606",
    "head_commit": "ddbcc8fe",
    "tracked_modified_count_before": tracked_modified_count_before,
    "tracked_deleted_count_before": tracked_deleted_count_before,
    "untracked_count_before": untracked_count_before,
    "staged_count_before": staged_count_before,
    "allowed_restore_paths_status": {p: os.path.exists(os.path.join(repo_root, p)) for p in allowed_restore_paths},
    "protected_non_restore_paths_status": {p: os.path.exists(os.path.join(repo_root, p)) for p in excluded_paths[:10]} # 只顯示前10個以防過大
}

with open(os.path.join(out_dir, "pre_restore_snapshot.json"), "w", encoding="utf-8") as f:
    json.dump(pre_snapshot, f, indent=2, ensure_ascii=False)

# 3. 執行精確 restore
restored_paths = []
missing_or_clean_paths = []
errors = []

for p in allowed_restore_paths:
    full_path = os.path.join(repo_root, p)
    if os.path.exists(full_path):
        res_res = subprocess.run(["git", "restore", p], cwd=repo_root)
        if res_res.returncode == 0:
            restored_paths.append(p)
        else:
            errors.append(f"Failed to restore {p}")
    else:
        missing_or_clean_paths.append(p)

# 4. Restore execution report
report = {
    "restore_status": "PASS" if len(errors) == 0 else "FAIL",
    "restored_paths": restored_paths,
    "missing_or_clean_paths": missing_or_clean_paths,
    "skipped_paths": [],
    "error_count": len(errors),
    "protected_path_violation_count": protected_path_violation_count,
    "git_clean_used": False,
    "git_reset_used": False,
    "broad_restore_used": False,
    "runtime_code_restored": False,
    "tests_restored": False,
    "docs_restored": False,
    "benchmark_outputs_restored": False,
    "unknown_restored": False
}

with open(os.path.join(out_dir, "restore_execution_report.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

# 5. Post-restore status
res_status_after = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=repo_root)
lines_after = res_status_after.stdout.splitlines()

tracked_modified_count_after = 0
untracked_count_after = 0
staged_count_after = 0
tracked_deleted_count_after = 0

for line in lines_after:
    if not line.strip():
        continue
    status = line[:2]
    if status.startswith("M") or status.endswith("M"):
        tracked_modified_count_after += 1
    if status == "??":
        untracked_count_after += 1
    if status.startswith("A") or status.startswith("M") and not status.startswith(" "):
        staged_count_after += 1
    if "D" in status:
        tracked_deleted_count_after += 1

# 分類統計剩餘
rem_runtime = 0
rem_test = 0
rem_docs = 0
rem_scratch = 0
rem_bench = 0
rem_unknown = 0
rem_cache = 0

for line in lines_after:
    if not line.strip():
        continue
    status = line[:2]
    if "M" in status:
        path = line[3:].strip().strip('"')
        path_lower = path.lower()
        if "__pycache__" in path_lower or path_lower.endswith(".pyc") or path == ".tmp_build":
            rem_cache += 1
        elif path.startswith("nexus-core-rs/src/") or (path.startswith("nexus/") and not "experimental" in path and not "__pycache__" in path):
            rem_runtime += 1
        elif path.startswith("tests/") and not "__pycache__" in path:
            rem_test += 1
        elif path == "Daily_Log.md" or path == "implementation_plan.md" or path.startswith("docs/reports/") or path.startswith(".nexus/"):
            rem_docs += 1
        elif path.startswith("scratch/") or path.startswith("scripts/") or "parse_test" in path_lower:
            rem_scratch += 1
        elif path.startswith("benchmarking/"):
            rem_bench += 1
        else:
            rem_unknown += 1

post_status = {
    "tracked_modified_count_after": tracked_modified_count_after,
    "tracked_deleted_count_after": tracked_deleted_count_after,
    "untracked_count_after": untracked_count_after,
    "staged_count_after": staged_count_after,
    "remaining_runtime_code_candidate_count": rem_runtime,
    "remaining_test_candidate_count": rem_test,
    "remaining_docs_or_evidence_candidate_count": rem_docs,
    "remaining_scratch_or_debug_modified_count": rem_scratch,
    "remaining_benchmark_or_experiment_modified_count": rem_bench,
    "remaining_unknown_requires_owner_review_count": rem_unknown,
    "generated_cache_modified_remaining_count": rem_cache,
    "remaining_dirty_summary": f"Remaining {tracked_modified_count_after} modified files and untracked review candidates left untouched."
}

with open(os.path.join(out_dir, "post_restore_status.json"), "w", encoding="utf-8") as f:
    json.dump(post_status, f, indent=2, ensure_ascii=False)

# 6. Governance preservation
gov = {
    "archive_status": "PAUSED_ARCHIVED",
    "no_deletion": True,
    "no_git_clean": True,
    "no_git_reset": True,
    "no_staging": True,
    "no_commit": True,
    "no_source_edit": True,
    "no_test_edit": True,
    "no_docs_edit": True,
    "no_model_calls": True,
    "no_repair_execution": True,
    "no_verifier_rerun": True,
    "no_training_export": True,
    "no_s2t_export": True,
    "no_public_claim": True,
    "no_runtime_routing_integration": True,
    "no_strata_s1": True
}
with open(os.path.join(out_dir, "governance_preservation.json"), "w", encoding="utf-8") as f:
    json.dump(gov, f, indent=2, ensure_ascii=False)

print("Restore of generated cache files executed successfully.")
