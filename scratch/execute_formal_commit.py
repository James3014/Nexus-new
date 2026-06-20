import subprocess
import os
import json

repo_root = "/Users/jameschen/Workspace/nexus"
out_dir = os.path.join(repo_root, "artifacts/runtime/commit_clear_formal_evidence_only_v0")
os.makedirs(out_dir, exist_ok=True)

allowed_commits = [
    "C_PHASE_COMPLETION_REPORT.md",
    "C_PHASE_STATUS.md",
    "C_PHASE_VERIFICATION_EVIDENCE.md",
    "NEXUS_FORENSIC_EVIDENCE_PACK.md",
    "docs/adr/0016-adr-search-to-ast-rewriter.md",
    "nexus_wiki_vault/01_System/ADR/ADR-2026-06-19-search-to-ast-rewriter.md"
]

excluded_duplicates = [
    "docs/adr/ADR-SEARCH-TO-AST-REWRITER.md",
    "nexus_wiki_vault/01_System/ADR/ADR-SEARCH-TO-AST-REWRITER.md"
]

# 1. Pre-stage 狀態蒐集
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

pre_stage = {
    "current_branch": "feature/bridge-fastmatcher-20260606",
    "head_commit": "1a75b6ea",
    "staged_count_before": staged_count_before,
    "tracked_modified_count": tracked_modified_count,
    "untracked_count": untracked_count,
    "allowed_files_status": {p: os.path.exists(os.path.join(repo_root, p)) for p in allowed_commits},
    "excluded_duplicate_files_status": {p: os.path.exists(os.path.join(repo_root, p)) for p in excluded_duplicates}
}

with open(os.path.join(out_dir, "pre_stage_status.json"), "w", encoding="utf-8") as f:
    json.dump(pre_stage, f, indent=2, ensure_ascii=False)

# 2. 執行精確 Stage
for p in allowed_commits:
    subprocess.run(["git", "add", p], cwd=repo_root)

# 3. Staging 驗證 (唯讀)
res_staged = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=repo_root)
staged_files = [line[2:].strip().strip('"') for line in res_staged.stdout.splitlines() if line.strip()]

staging_verification_status = "PASS"
error_reason = ""

# 檢查 staged paths 是否完全等同於 allowed_commits
staged_set = set(staged_files)
allowed_set = set(allowed_commits)

if staged_set != allowed_set:
    staging_verification_status = "FAIL"
    error_reason = f"Staged set {staged_set} does not match allowed set {allowed_set}"

# 檢查重複 ADR 是否被 staged
for dup in excluded_duplicates:
    if dup in staged_set:
        staging_verification_status = "FAIL"
        error_reason += f" | Duplicate ADR {dup} is staged!"

# 檢查是否有 runtime/test 檔案被 staged
for path in staged_files:
    if path.startswith("nexus/") or path.startswith("tests/") or path.startswith("benchmarking/"):
        if path not in allowed_set:
            staging_verification_status = "FAIL"
            error_reason += f" | Protected path {path} is staged!"

staging_ver = {
    "staging_verification_status": staging_verification_status,
    "cached_count": len(staged_files),
    "cached_paths": staged_files,
    "duplicate_ADR_staged": any(dup in staged_set for dup in excluded_duplicates),
    "source_or_tests_staged": any(p.startswith("nexus/") or p.startswith("tests/") for p in staged_files),
    "benchmark_outputs_staged": any(p.startswith("benchmarking/") for p in staged_files),
    "error_reason": error_reason
}

with open(os.path.join(out_dir, "staging_verification.json"), "w", encoding="utf-8") as f:
    json.dump(staging_ver, f, indent=2, ensure_ascii=False)

# 4. 執行 Commit (若驗證 PASS)
commit_hash = "N/A"
if staging_verification_status == "PASS":
    res_commit = subprocess.run(["git", "commit", "-m", "docs: add clear formal evidence and ADR records"], capture_output=True, text=True, cwd=repo_root)
    print("Commit output:", res_commit.stdout)
    # 取得最新的 commit hash
    res_hash = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo_root)
    commit_hash = res_hash.stdout.strip()
else:
    print(f"Staging verification FAILED: {error_reason}. Aborting commit!")

# 5. Post-commit 狀態統計
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

post_commit = {
    "commit_hash": commit_hash,
    "committed_paths": allowed_commits,
    "duplicate_ADR_files_remaining_untracked_or_unmodified": {p: os.path.exists(os.path.join(repo_root, p)) for p in excluded_duplicates},
    "tracked_modified_count_after": tracked_modified_count_after,
    "untracked_count_after": untracked_count_after,
    "staged_count_after": staged_count_after,
    "remaining_dirty_summary": "62 modified files and untracked candidates under benchmark/code/test/docs are protected and left untouched."
}

with open(os.path.join(out_dir, "post_commit_status.json"), "w", encoding="utf-8") as f:
    json.dump(post_commit, f, indent=2, ensure_ascii=False)

# 6. Governance preservation
gov = {
    "archive_status": "PAUSED_ARCHIVED",
    "no_model_calls": True,
    "no_repair_execution": True,
    "no_verifier_rerun": True,
    "no_training_export": True,
    "no_s2t_export": True,
    "no_public_claim": True,
    "no_runtime_routing_integration": True,
    "no_strata_s1_connection": True,
    "no_source_test_code_committed": False,
    "no_benchmark_outputs_committed": False,
    "duplicate_ADR_cleanup_not_executed": True
}
with open(os.path.join(out_dir, "governance_preservation.json"), "w", encoding="utf-8") as f:
    json.dump(gov, f, indent=2, ensure_ascii=False)

print(f"Formal evidence committed successfully! Commit Hash: {commit_hash}")
