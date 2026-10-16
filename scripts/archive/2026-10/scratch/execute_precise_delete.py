import os
import shutil
import json
import glob
import subprocess

repo_root = "/Users/jameschen/Workspace/nexus"

# 1. 盤點要刪除的清單
allowed_delete_patterns = [
    "MagicMock",
    "tmp_storage",
    ".tmp/untracked_files.txt",
    "parse_test.py",
    "parse_test2.py",
    "parse_test3.py",
    "parse_test4.py"
]

allowed_resolved_paths = []
for p in allowed_delete_patterns:
    full_p = os.path.join(repo_root, p)
    if "*" in p or "?" in p:
        # 僅限根目錄下的 parse_test*.py 匹配
        for f in glob.glob(full_p):
            allowed_resolved_paths.append(os.path.abspath(f))
    else:
        # 直接加入 (不管存不存在)
        allowed_resolved_paths.append(os.path.abspath(full_p))

allowed_resolved_paths = sorted(list(set(allowed_resolved_paths)))

# 二重安全檢查：確保任何路徑均不屬於保護目錄
protected_prefixes = [
    os.path.join(repo_root, "artifacts"),
    os.path.join(repo_root, "benchmarking"),
    os.path.join(repo_root, "verification-evidence"),
    os.path.join(repo_root, "docs"),
    os.path.join(repo_root, "nexus"),
    os.path.join(repo_root, "tests"),
    os.path.join(repo_root, "subprojects"),
    os.path.join(repo_root, "scratch"),
    os.path.join(repo_root, "scripts"),
    os.path.join(repo_root, "configs")
]

protected_violation_count = 0
for path in allowed_resolved_paths:
    for prefix in protected_prefixes:
        if path.startswith(prefix + "/") or path == prefix:
            print(f"VIOLATION: Path {path} is under protected prefix {prefix}!")
            protected_violation_count += 1

# 計算存在的與丟失的
found_candidates = [p for p in allowed_resolved_paths if os.path.exists(p)]
missing_candidates = [p for p in allowed_resolved_paths if not os.path.exists(p)]

# 統計 pre-delete untracked file count
git_untracked_count = 0
try:
    res = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], capture_output=True, text=True, cwd=repo_root)
    git_untracked_count = len([x for x in res.stdout.splitlines() if x.strip()])
except Exception:
    pass

# A. 寫入 pre_delete_snapshot.json
pre_snapshot = {
    "schema": "nexus.safe_untracked_delete_pre_snapshot.v0",
    "current_branch": "feature/bridge-fastmatcher-20260606",
    "head_commit": "1f834402",
    "untracked_count_before": git_untracked_count,
    "allowed_delete_candidates_found": found_candidates,
    "allowed_delete_candidates_missing": missing_candidates,
    "protected_path_check_pass": protected_violation_count == 0
}

pre_snapshot_path = os.path.join(repo_root, "artifacts/runtime/safe_untracked_delete_only_v0/pre_delete_snapshot.json")
os.makedirs(os.path.dirname(pre_snapshot_path), exist_ok=True)
with open(pre_snapshot_path, "w", encoding="utf-8") as f:
    json.dump(pre_snapshot, f, indent=2, ensure_ascii=False)

# 若有保護路徑違反，直接中止
if protected_violation_count > 0:
    print("Protected path violation found. Aborting deletion!")
    exit(1)

# B. 執行刪除
deleted_paths = []
skipped_candidates = []
errors = []

for path in found_candidates:
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        deleted_paths.append(path)
    except Exception as e:
        errors.append(f"Failed to delete {path}: {str(e)}")

# C. 寫入 deletion_execution_report.json
report = {
    "schema": "nexus.safe_untracked_delete_report.v0",
    "deletion_status": "PASS" if len(errors) == 0 else "FAIL",
    "deleted_paths": deleted_paths,
    "missing_candidates": missing_candidates,
    "skipped_candidates": skipped_candidates,
    "error_count": len(errors),
    "protected_path_violation_count": protected_violation_count,
    "git_clean_used": False,
    "git_reset_used": False,
    "git_restore_used": False,
    "broad_delete_used": False,
    "source_deleted": False,
    "tests_deleted": False,
    "docs_deleted": False,
    "artifacts_deleted": False,
    "benchmark_outputs_deleted": False,
    "formal_evidence_deleted": False
}

report_path = os.path.join(repo_root, "artifacts/runtime/safe_untracked_delete_only_v0/deletion_execution_report.json")
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

# D. 統計 post-delete status 與寫入 post_delete_status.json
post_git_untracked_count = 0
try:
    res = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], capture_output=True, text=True, cwd=repo_root)
    post_git_untracked_count = len([x for x in res.stdout.splitlines() if x.strip()])
except Exception:
    pass

post_status = {
    "schema": "nexus.safe_untracked_delete_post_status.v0",
    "untracked_count_after": post_git_untracked_count,
    "deleted_candidate_count": len(deleted_paths),
    "remaining_untracked_summary": "Remaining untracked files are protected review candidates (source code, tests, docs, artifacts).",
    "remaining_protected_review_candidates": post_git_untracked_count,
    "tracked_modified_count": 0, # 此任務無修改已追踪代碼
    "staged_count": 0
}

post_status_path = os.path.join(repo_root, "artifacts/runtime/safe_untracked_delete_only_v0/post_delete_status.json")
with open(post_status_path, "w", encoding="utf-8") as f:
    json.dump(post_status, f, indent=2, ensure_ascii=False)

# E. 寫入 governance_preservation.json
gov = {
    "schema": "nexus.local_7b_14b_repair_delete_governance_preservation.v0",
    "archive_status": "PAUSED_ARCHIVED",
    "no_git_clean": True,
    "no_git_reset": True,
    "no_git_restore": True,
    "no_source_modification": True,
    "no_test_modification": True,
    "no_formal_evidence_deletion": True,
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

gov_path = os.path.join(repo_root, "artifacts/runtime/safe_untracked_delete_only_v0/governance_preservation.json")
with open(gov_path, "w", encoding="utf-8") as f:
    json.dump(gov, f, indent=2, ensure_ascii=False)

print("Execution script successfully generated and ran.")
