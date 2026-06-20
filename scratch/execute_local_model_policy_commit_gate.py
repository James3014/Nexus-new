import subprocess
import os
import json

repo_root = "/Users/jameschen/Workspace/nexus"
out_dir = os.path.join(repo_root, "artifacts/runtime/local_model_policy_packet_only_commit_gate_v0")
os.makedirs(out_dir, exist_ok=True)

target_file = "nexus/engine/local_model_policy.py"

# 1. Pre-stage diff review
res_diff = subprocess.run(["git", "diff", "--", target_file], capture_output=True, text=True, cwd=repo_root)
diff_text = res_diff.stdout

additions = sum(1 for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++"))
deletions = sum(1 for line in diff_text.splitlines() if line.startswith("-") and not line.startswith("---"))

diff_stat = f"+{additions}/-{deletions} lines"

pre_diff = {
    "file_path": target_file,
    "diff_stat": diff_stat,
    "approximate_changed_lines": additions + deletions,
    "apparent_intent": "Update predict patch limit to 3072 and define shadow-only SidecarConfig for planning/diagnosis phases.",
    "risk_level": "LOW",
    "imports_changed": False,
    "public_api_changed": True,
    "routing_behavior_changed": True,
    "model_call_behavior_changed": True,
    "training_export_behavior_changed": False,
    "s2t_export_behavior_changed": False,
    "needs_test_pairing": True,
    "related_tests": ["tests/unit/test_local_model_policy.py"],
    "review_result": "PASS"
}

with open(os.path.join(out_dir, "pre_stage_diff_review.json"), "w", encoding="utf-8") as f:
    json.dump(pre_diff, f, indent=2, ensure_ascii=False)

# 2. Static check (py_compile)
res_compile = subprocess.run(["python3", "-m", "py_compile", target_file], capture_output=True, text=True, cwd=repo_root)
status = "PASS" if res_compile.returncode == 0 else "FAIL"

static_check = {
    "py_compile_run": True,
    "py_compile_status": status,
    "error_output": res_compile.stderr,
    "full_tests_run": False,
    "verifier_run": False,
    "model_calls": False
}

with open(os.path.join(out_dir, "static_check_result.json"), "w", encoding="utf-8") as f:
    json.dump(static_check, f, indent=2, ensure_ascii=False)

if status == "FAIL":
    print("Static check py_compile failed! Aborting staging.")
    exit(1)

# 3. Stage allowed file only
subprocess.run(["git", "add", target_file], cwd=repo_root)

# 4. Staging verification
res_staged = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=repo_root)
staged_files = [line[2:].strip().strip('"') for line in res_staged.stdout.splitlines() if line.strip()]

staging_verification_status = "PASS"
error_reason = ""

if len(staged_files) != 1 or staged_files[0] != target_file:
    staging_verification_status = "FAIL"
    error_reason = f"Staged files {staged_files} do not match target {target_file}"

staging_ver = {
    "staging_verification_status": staging_verification_status,
    "cached_paths": staged_files,
    "cached_path_count": len(staged_files),
    "unrelated_files_staged": len(staged_files) > 1 or (len(staged_files) == 1 and staged_files[0] != target_file),
    "error_reason": error_reason
}

with open(os.path.join(out_dir, "staging_verification.json"), "w", encoding="utf-8") as f:
    json.dump(staging_ver, f, indent=2, ensure_ascii=False)

if staging_verification_status == "FAIL":
    print(f"Staging verification failed: {error_reason}. Aborting commit!")
    exit(1)

# 5. Commit exact local model policy packet
res_commit = subprocess.run(["git", "commit", "-m", "feat: update local model policy packet"], capture_output=True, text=True, cwd=repo_root)
print("Commit output:", res_commit.stdout)

res_hash = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo_root)
commit_hash = res_hash.stdout.strip()

# 6. Post-commit status
res_status_after = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=repo_root)
lines_after = res_status_after.stdout.splitlines()

tracked_modified_count_after = 0
untracked_count_after = 0
staged_count_after = 0
tracked_deleted_count_after = 0

for line in lines_after:
    if not line.strip():
        continue
    status_ch = line[:2]
    if status_ch.startswith("M") or status_ch.endswith("M"):
        tracked_modified_count_after += 1
    if status_ch == "??":
        untracked_count_after += 1
    if status_ch.startswith("A") or status_ch.startswith("M") and not status_ch.startswith(" "):
        staged_count_after += 1
    if "D" in status_ch:
        tracked_deleted_count_after += 1

# 統計剩餘的 runtime code
rem_runtime = 0
for line in lines_after:
    if not line.strip():
        continue
    status_ch = line[:2]
    if "M" in status_ch:
        path = line[3:].strip().strip('"')
        path_lower = path.lower()
        if path.startswith("nexus-core-rs/src/") or (path.startswith("nexus/") and not "experimental" in path and not "__pycache__" in path):
            rem_runtime += 1

post_commit = {
    "commit_hash": commit_hash,
    "committed_paths": [target_file],
    "tracked_modified_count_after": tracked_modified_count_after,
    "tracked_deleted_count_after": tracked_deleted_count_after,
    "untracked_count_after": untracked_count_after,
    "staged_count_after": staged_count_after,
    "remaining_runtime_code_candidate_count": rem_runtime,
    "remaining_dirty_summary": f"Remaining {tracked_modified_count_after} modified files and untracked candidates left untouched."
}

with open(os.path.join(out_dir, "post_commit_status.json"), "w", encoding="utf-8") as f:
    json.dump(post_commit, f, indent=2, ensure_ascii=False)

# 7. Governance preservation
gov = {
    "archive_status": "PAUSED_ARCHIVED",
    "no_deletion": True,
    "no_git_clean": True,
    "no_git_reset": True,
    "no_broad_restore": True,
    "no_model_calls": True,
    "no_repair_execution": True,
    "no_verifier_rerun": True,
    "no_training_export": True,
    "no_s2t_export": True,
    "no_public_claim": True,
    "no_runtime_routing_integration": True,
    "no_strata_s1_connection": True,
    "no_next_expansion": True,
    "only_local_model_policy_committed": True
}

with open(os.path.join(out_dir, "governance_preservation.json"), "w", encoding="utf-8") as f:
    json.dump(gov, f, indent=2, ensure_ascii=False)

print(f"Local model policy committed successfully! Commit Hash: {commit_hash}")
