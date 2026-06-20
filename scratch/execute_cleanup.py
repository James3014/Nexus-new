import os
import shutil
import json

repo_root = "/Users/jameschen/Workspace/nexus"
candidates_json = os.path.join(repo_root, "artifacts/runtime/safe_cache_and_log_cleanup_only_v0/cleanup_candidates.json")

with open(candidates_json, "r", encoding="utf-8") as f:
    data = json.load(f)

candidates = data.get("candidates", [])

deleted_files = 0
deleted_dirs = 0
errors = []

# 安全的關鍵詞過濾，二重防禦
def is_safe_to_delete(path):
    # 確保在工作區內
    if not path.startswith(repo_root):
        return False
    # 禁止刪除 .git
    if ".git" in path:
        return False
    
    # 必須符合 cache/log/debug 特定關鍵字
    path_lower = path.lower()
    safe_keywords = [".hypothesis", "target", ".log", "last_response.txt", "last_patch_call.txt", "last_patch_response.txt"]
    for kw in safe_keywords:
        if kw in path_lower:
            return True
    return False

# 我們先將目錄和檔案分開處理。
# 如果刪除了目錄，其底下的檔案就不用個別刪除。因此我們先處理檔案，最後再處理目錄。
# 或者我們由深到淺排序，這樣就不會發生父目錄已刪除導致子路徑不存在的報錯。
candidates_sorted = sorted(candidates, key=len, reverse=True)

for path in candidates_sorted:
    if not os.path.exists(path):
        continue
    if not is_safe_to_delete(path):
        errors.append(f"Rejected unsafe path: {path}")
        continue
    
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
            deleted_dirs += 1
        else:
            os.remove(path)
            deleted_files += 1
    except Exception as e:
        errors.append(f"Failed to delete {path}: {str(e)}")

report = {
    "schema": "nexus.local_7b_14b_repair_cleanup_execution_report.v0",
    "deleted_files_count": deleted_files,
    "deleted_dirs_count": deleted_dirs,
    "errors": errors,
    "status": "SUCCESS" if len(errors) == 0 else "COMPLETED_WITH_ERRORS"
}

report_path = os.path.join(repo_root, "artifacts/runtime/safe_cache_and_log_cleanup_only_v0/cleanup_execution_report.json")
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print(f"Cleanup finished. Deleted {deleted_files} files, {deleted_dirs} dirs. Errors: {len(errors)}.")
