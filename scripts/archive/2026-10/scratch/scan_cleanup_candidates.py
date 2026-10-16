import os
import glob
import json

# 專案根目錄
repo_root = "/Users/jameschen/Workspace/nexus"

candidates = []

# 1. .hypothesis/ 目錄
hypo_path = os.path.join(repo_root, ".hypothesis")
if os.path.exists(hypo_path):
    candidates.append(hypo_path)
    for root, dirs, files in os.walk(hypo_path):
        for name in files:
            candidates.append(os.path.join(root, name))
        for name in dirs:
            candidates.append(os.path.join(root, name))

# 2. **/target/ 目錄 (主要是 nexus-core-rs/target/)
for root, dirs, files in os.walk(repo_root):
    if "target" in dirs:
        target_dir = os.path.join(root, "target")
        # 排除包含在 .git 內或 dummy 的 target
        if ".git" not in target_dir:
            candidates.append(target_dir)
            for sub_root, sub_dirs, sub_files in os.walk(target_dir):
                for name in sub_files:
                    candidates.append(os.path.join(sub_root, name))
                for name in sub_dirs:
                    candidates.append(os.path.join(sub_root, name))

# 3. 根目錄下的 *.log
for f in glob.glob(os.path.join(repo_root, "*.log")):
    candidates.append(f)

# 4. scratch/*.log
for f in glob.glob(os.path.join(repo_root, "scratch", "*.log")):
    candidates.append(f)

# 5. ollama_calls.log & run_output*.log & last_response.txt & last_patch_call.txt & last_patch_response.txt
special_patterns = [
    "ollama_calls.log",
    "run_output*.log",
    "last_response.txt",
    "last_patch_call.txt",
    "last_patch_response.txt"
]
for pattern in special_patterns:
    for f in glob.glob(os.path.join(repo_root, pattern)):
        candidates.append(f)
    for f in glob.glob(os.path.join(repo_root, "**", pattern), recursive=True):
        if ".git" not in f:
            candidates.append(f)

# 去重並過濾為絕對路徑且確實存在者
candidates = sorted(list(set([os.path.abspath(c) for c in candidates if os.path.exists(c)])))

# 輸出為 JSON
output_data = {
    "schema": "nexus.local_7b_14b_repair_cleanup_candidates.v0",
    "total_candidates_found": len(candidates),
    "candidates": candidates
}

out_path = os.path.join(repo_root, "artifacts/runtime/safe_cache_and_log_cleanup_only_v0/cleanup_candidates.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output_data, f, indent=2, ensure_ascii=False)

print(f"Successfully generated candidate list with {len(candidates)} items.")
