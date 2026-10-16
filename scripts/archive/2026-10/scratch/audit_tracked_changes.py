import subprocess
import os
import json

repo_root = "/Users/jameschen/Workspace/nexus"
out_dir = os.path.join(repo_root, "artifacts/runtime/tracked_deletion_modification_audit_v0")
os.makedirs(out_dir, exist_ok=True)

# 1. 取得 git status --porcelain 輸出
res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=repo_root)
lines = res.stdout.splitlines()

deleted_files = []
modified_files = []

for line in lines:
    if not line.strip():
        continue
    status = line[:2]
    path = line[3:].strip().strip('"') # 移除引號
    
    if "D" in status:
        deleted_files.append(path)
    elif "M" in status:
        modified_files.append(path)

# 2. 進行 Deletions 分類
deleted_classified = []
high_risk_deletions = []

# 分類統計
deleted_stats = {
    "generated_cache_tracked_deleted": 0,
    "accidental_source_deleted": 0,
    "accidental_test_deleted": 0,
    "formal_evidence_deleted": 0,
    "benchmark_output_deleted": 0,
    "unknown_tracked_deleted_requires_owner_review": 0
}

for path in deleted_files:
    # 預設分類
    category = "unknown_tracked_deleted_requires_owner_review"
    reason = "Unhandled deletion path."
    risk = "HIGH"
    
    path_lower = path.lower()
    if "target/" in path_lower or path_lower.endswith(".log") or "__pycache__" in path_lower or path_lower.endswith(".pyc"):
        category = "generated_cache_tracked_deleted"
        reason = "Tracked build artifact or debug log file removed during cleanup."
        risk = "LOW"
    elif path.startswith("nexus/"):
        category = "accidental_source_deleted"
        reason = "Source code file deleted!"
        risk = "CRITICAL"
        high_risk_deletions.append(path)
    elif path.startswith("tests/"):
        category = "accidental_test_deleted"
        reason = "Test file deleted!"
        risk = "CRITICAL"
        high_risk_deletions.append(path)
    elif path.startswith("docs/reports/") or path.startswith("artifacts/"):
        category = "formal_evidence_deleted"
        reason = "Formal evidence or report document deleted."
        risk = "HIGH"
        high_risk_deletions.append(path)
    elif path.startswith("benchmarking/") or path.startswith("verification-evidence/"):
        category = "benchmark_output_deleted"
        reason = "Benchmark or verification output deleted."
        risk = "HIGH"
        high_risk_deletions.append(path)
        
    deleted_stats[category] += 1
    deleted_classified.append({
        "path": path,
        "category": category,
        "reason": reason,
        "risk": risk
    })

# 3. 進行 Modifications 分類
modified_classified = []
high_risk_modifications = []

modified_stats = {
    "runtime_code_candidate": 0,
    "test_candidate": 0,
    "docs_candidate": 0,
    "formal_evidence_candidate": 0,
    "generated_cache_modified": 0,
    "scratch_or_debug_modified": 0,
    "unknown_modified_requires_owner_review": 0
}

for path in modified_files:
    category = "unknown_modified_requires_owner_review"
    reason = "Unhandled modification path."
    
    path_lower = path.lower()
    if "__pycache__" in path_lower or path_lower.endswith(".pyc") or path == ".tmp_build":
        category = "generated_cache_modified"
        reason = "Python cache file modified by execution."
    elif path.startswith("nexus/"):
        category = "runtime_code_candidate"
        reason = "Runtime source file modified on current branch."
    elif path.startswith("tests/"):
        category = "test_candidate"
        reason = "Unit or integration test file modified."
    elif path.startswith("docs/adr/"):
        category = "docs_candidate"
        reason = "Architecture Decision Record modified."
    elif path.startswith("docs/reports/") or path.startswith("artifacts/"):
        category = "formal_evidence_candidate"
        reason = "Report or evidence artifact modified."
    elif path.startswith("scratch/") or path.startswith("scripts/") or "parse_test" in path_lower:
        category = "scratch_or_debug_modified"
        reason = "Scratch script modified."
    elif path == ".gitignore" or path == "Daily_Log.md" or path == "implementation_plan.md":
        category = "docs_candidate"
        reason = "Workspace config or log documentation."

    modified_stats[category] += 1
    modified_classified.append({
        "path": path,
        "category": category,
        "reason": reason
    })

# 4. 寫入 jsonl 檔案
with open(os.path.join(out_dir, "tracked_deletion_classification.jsonl"), "w", encoding="utf-8") as f:
    for item in deleted_classified:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

with open(os.path.join(out_dir, "tracked_modification_classification.jsonl"), "w", encoding="utf-8") as f:
    for item in modified_classified:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

# 5. 寫入 high_risk_path_alert.json
alert = {
    "schema": "nexus.tracked_cleanup_high_risk_alert.v0",
    "high_risk_paths_detected": len(high_risk_deletions) > 0,
    "paths": high_risk_deletions
}
with open(os.path.join(out_dir, "high_risk_path_alert.json"), "w", encoding="utf-8") as f:
    json.dump(alert, f, indent=2, ensure_ascii=False)

# 6. 寫入 restore_remove_decision_matrix.json
decision_matrix = {
    "schema": "nexus.tracked_cleanup_restore_remove_decision_matrix.v0",
    "categories": [
        {
            "category": "generated_cache_tracked_deleted",
            "count": deleted_stats["generated_cache_tracked_deleted"],
            "recommended_action": "REMOVE_FROM_GIT_INDEX",
            "explanation": "These are generated build files. Keeping them in git index is unnecessary. We should use `git rm --cached` or commit their deletion."
        },
        {
            "category": "accidental_source_deleted",
            "count": deleted_stats["accidental_source_deleted"],
            "recommended_action": "GIT_RESTORE",
            "explanation": "Critical source files should not be deleted. Must restore if any are present."
        },
        {
            "category": "accidental_test_deleted",
            "count": deleted_stats["accidental_test_deleted"],
            "recommended_action": "GIT_RESTORE",
            "explanation": "Critical test files should not be deleted."
        }
    ]
}
with open(os.path.join(out_dir, "restore_remove_decision_matrix.json"), "w", encoding="utf-8") as f:
    json.dump(decision_matrix, f, indent=2, ensure_ascii=False)

# 7. 寫入 current_tracked_status_snapshot.json
status_snapshot = {
    "schema": "nexus.tracked_cleanup_status_snapshot.v0",
    "current_branch": "feature/bridge-fastmatcher-20260606",
    "head_commit": "36394676",
    "tracked_deleted_count": len(deleted_files),
    "tracked_modified_count": len(modified_files),
    "staged_count": 0,
    "top_level_deleted_paths": sorted(list(set([p.split("/")[0] for p in deleted_files]))),
    "top_level_modified_paths": sorted(list(set([p.split("/")[0] for p in modified_files])))
}
with open(os.path.join(out_dir, "current_tracked_status_snapshot.json"), "w", encoding="utf-8") as f:
    json.dump(status_snapshot, f, indent=2, ensure_ascii=False)

print(f"Audit finished. Tracked deletions: {len(deleted_files)} (High risk: {len(high_risk_deletions)}). Tracked modifications: {len(modified_files)}.")
