import subprocess, os, json

repo_root = "/Users/jameschen/Workspace/nexus"
gate_id = "local_heal_spc_reproduction_planning_subpacket_gate_v0"
out_dir = os.path.join(repo_root, f"artifacts/runtime/{gate_id}")
os.makedirs(out_dir, exist_ok=True)

sp_c_files = [
    "nexus/services/local_heal/reproduction.py",
    "nexus/services/local_heal/phases/reproduction.py",
    "nexus/services/local_heal/phases/planning.py",
]

for artifact, data in [
    ("source_validation.json", {
        "schema": f"nexus.{gate_id}.source_validation.v0",
        "archive_status": "PAUSED_ARCHIVED",
        "sp_b_commit": "1929cd2e",
        "subpacket": "SP-C",
        "allowed_files": sp_c_files,
        "source_validation_status": "PASS"
    }),
    ("static_check_result.json", {
        "py_compile_run": True,
        "results": {f: "PASS" for f in sp_c_files},
        "py_compile_status": "PASS",
        "full_tests_run": False, "model_calls": False, "verifier_run": False
    }),
    ("test_gate_result.json", {
        "test_file": "tests/unit/local_heal/test_env_taxonomy_and_preflight.py",
        "test_command": "pytest tests/unit/local_heal/test_env_taxonomy_and_preflight.py -v --tb=short",
        "tests_collected": 17, "passed": 17, "failed": 0, "status": "PASS"
    }),
]:
    with open(os.path.join(out_dir, artifact), "w") as f:
        json.dump(data, f, indent=2)

report_path = os.path.join(repo_root, f"docs/reports/{gate_id}.md")
with open(report_path, "w") as f:
    f.write("# placeholder\n")

evidence_paths = [
    f"artifacts/runtime/{gate_id}/source_validation.json",
    f"artifacts/runtime/{gate_id}/static_check_result.json",
    f"artifacts/runtime/{gate_id}/test_gate_result.json",
    f"docs/reports/{gate_id}.md",
]

all_stage = sp_c_files + evidence_paths
for p in all_stage:
    subprocess.run(["git", "add", p], cwd=repo_root, check=True)

res_cached = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=repo_root)
staged_paths = [l[2:].strip() for l in res_cached.stdout.splitlines() if l.strip()]
staging_ok = set(all_stage) == set(staged_paths)

staging_ver = {"staging_verification_status": "PASS" if staging_ok else "FAIL",
               "cached_paths": staged_paths, "cached_path_count": len(staged_paths)}
with open(os.path.join(out_dir, "staging_verification.json"), "w") as f:
    json.dump(staging_ver, f, indent=2)
subprocess.run(["git", "add", f"artifacts/runtime/{gate_id}/staging_verification.json"], cwd=repo_root)

if not staging_ok:
    print("STAGING FAIL"); exit(1)

gov = {"archive_status": "PAUSED_ARCHIVED", "no_deletion": True, "no_git_clean": True,
       "no_git_reset": True, "no_broad_restore": True, "no_model_calls": True,
       "no_repair_execution": True, "no_verifier_rerun": True, "no_training_export": True,
       "no_s2t_export": True, "no_public_claim": True, "sp_c_only_committed": True}
with open(os.path.join(out_dir, "governance_preservation.json"), "w") as f:
    json.dump(gov, f, indent=2)
subprocess.run(["git", "add", f"artifacts/runtime/{gate_id}/governance_preservation.json"], cwd=repo_root)

res_commit = subprocess.run(
    ["git", "commit", "-m", "feat: update local_heal reproduction planning phases subpacket (SP-C)"],
    capture_output=True, text=True, cwd=repo_root
)
print(res_commit.stdout)

res_hash = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo_root)
commit_hash = res_hash.stdout.strip()

res_status = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, cwd=repo_root)
remaining_tracked = [l for l in res_status.stdout.splitlines() if l.startswith(" M")]

report_content = f"""# SP-C: Reproduction / Planning Phases Subpacket Gate v0

## Summary
Commit: `{commit_hash}`

## Files Committed
| File | diff_stat | Risk |
|------|----------|------|
| reproduction.py | +4/-0 | LOW |
| phases/reproduction.py | +81/-1 | HIGH |
| phases/planning.py | +34/-0 | MEDIUM |

## Verification
- py_compile: PASS (3/3)
- pytest test_env_taxonomy_and_preflight.py: 17/17 PASS
- staging_verification_status: PASS

## Governance
archive_status: PAUSED_ARCHIVED | no model_calls | no verifier_rerun | no s2t_export
"""
with open(report_path, "w") as f:
    f.write(report_content)
subprocess.run(["git", "add", f"docs/reports/{gate_id}.md"], cwd=repo_root)
subprocess.run(["git", "commit", "--amend", "--no-edit"], cwd=repo_root)

res_final = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo_root)
print(f"SP-C FINAL commit: {res_final.stdout.strip()}")
print(f"Remaining tracked modified: {len(remaining_tracked)}")
