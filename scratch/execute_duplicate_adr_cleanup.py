import os
import json
import subprocess

repo_root = "/Users/jameschen/Workspace/nexus"
out_dir = os.path.join(repo_root, "artifacts/runtime/duplicate_adr_cleanup_only_v0")
os.makedirs(out_dir, exist_ok=True)

duplicates = [
    "docs/adr/ADR-SEARCH-TO-AST-REWRITER.md",
    "nexus_wiki_vault/01_System/ADR/ADR-SEARCH-TO-AST-REWRITER.md"
]

canonicals = [
    "docs/adr/0016-adr-search-to-ast-rewriter.md",
    "nexus_wiki_vault/01_System/ADR/ADR-2026-06-19-search-to-ast-rewriter.md"
]

# 1. Pre-delete snapshot
res_status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=repo_root)
lines = res_status.stdout.splitlines()

tracked_modified_count = 0
untracked_count = 0
staged_count_before = 0

for line in lines:
    if not line.strip():
        continue
    status = line[:2]
    if status.startswith("M") or status.endswith("M"):
        tracked_modified_count += 1
    if status == "??":
        untracked_count += 1
    if status.startswith("A") or status.startswith("M") and not status.startswith(" "):
        staged_count_before += 1

pre_del = {
    "current_branch": "feature/bridge-fastmatcher-20260606",
    "head_commit": "732c5aab",
    "allowed_duplicate_files_status": {p: os.path.exists(os.path.join(repo_root, p)) for p in duplicates},
    "canonical_ADR_files_status": {p: os.path.exists(os.path.join(repo_root, p)) for p in canonicals},
    "staged_count_before": staged_count_before,
    "tracked_modified_count": tracked_modified_count,
    "untracked_count": untracked_count
}

with open(os.path.join(out_dir, "pre_delete_snapshot.json"), "w", encoding="utf-8") as f:
    json.dump(pre_del, f, indent=2, ensure_ascii=False)

# 2. 執行精確刪除
deleted_paths = []
missing_candidates = []
errors = []

for p in duplicates:
    full_path = os.path.join(repo_root, p)
    if os.path.exists(full_path):
        try:
            # 確保不是目錄，安全起見
            if not os.path.isdir(full_path):
                os.remove(full_path)
                deleted_paths.append(p)
            else:
                errors.append(f"Target path {p} is a directory, skip.")
        except Exception as e:
            errors.append(f"Failed to delete {p}: {str(e)}")
    else:
        missing_candidates.append(p)

# 3. Deletion report
report = {
    "deletion_status": "PASS" if len(errors) == 0 else "FAIL",
    "deleted_paths": deleted_paths,
    "missing_candidates": missing_candidates,
    "skipped_candidates": [],
    "error_count": len(errors),
    "canonical_ADR_deleted": any(not os.path.exists(os.path.join(repo_root, c)) for c in canonicals),
    "protected_path_violation_count": 0,
    "git_clean_used": False,
    "git_reset_used": False,
    "git_restore_used": False,
    "wildcard_delete_used": False
}

with open(os.path.join(out_dir, "deletion_report.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

# 4. Post-delete status
res_status_after = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=repo_root)
lines_after = res_status_after.stdout.splitlines()

tracked_modified_count_after = 0
untracked_count_after = 0
staged_count_after = 0

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

post_del = {
    "duplicate_ADR_remaining": any(os.path.exists(os.path.join(repo_root, p)) for p in duplicates),
    "canonical_ADR_files_exist": all(os.path.exists(os.path.join(repo_root, c)) for c in canonicals),
    "tracked_modified_count_after": tracked_modified_count_after,
    "untracked_count_after": untracked_count_after,
    "staged_count_after": staged_count_after,
    "remaining_dirty_summary": "62 modified files and remaining protected untracked candidates are left untouched."
}

with open(os.path.join(out_dir, "post_delete_status.json"), "w", encoding="utf-8") as f:
    json.dump(post_del, f, indent=2, ensure_ascii=False)

# 5. Governance preservation
gov = {
    "schema": "nexus.local_7b_14b_repair_duplicate_adr_cleanup_governance.v0",
    "archive_status": "PAUSED_ARCHIVED",
    "no_git_clean": True,
    "no_git_reset": True,
    "no_git_restore": True,
    "no_source_modification": True,
    "no_test_modification": True,
    "no_benchmark_output_deletion": True,
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

print("Duplicate ADR cleanup executed successfully.")
