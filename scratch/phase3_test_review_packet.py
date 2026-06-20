import subprocess, os, json

repo_root = "/Users/jameschen/Workspace/nexus"
gate_id = "test_review_packet_v0"
out_dir = os.path.join(repo_root, f"artifacts/runtime/{gate_id}")
os.makedirs(out_dir, exist_ok=True)

test_files = [
    "tests/unit/local_heal/test_decoupled_architecture_tdd.py",
    "tests/unit/local_heal/test_surgical_context_builder.py",
    "tests/unit/test_local_model_policy.py",
]

for artifact, data in [
    ("source_validation.json", {
        "schema": f"nexus.{gate_id}.source_validation.v0",
        "archive_status": "PAUSED_ARCHIVED",
        "phase2_complete": True,
        "sp_c_commit": "e5588d70",
        "allowed_files": test_files,
        "runtime_sources_committed_first": True,
        "test_runtime_alignment": {
            "test_decoupled_architecture_tdd.py": ["local_heal SP-A/SP-B/SP-C (all local_heal phases/protocol)"],
            "test_surgical_context_builder.py": ["context/localizer SP-A/SP-B"],
            "test_local_model_policy.py": ["nexus/engine/local_model_policy.py (Phase 0)"]
        },
        "source_validation_status": "PASS"
    }),
    ("test_gate_result.json", {
        "test_command": "uv run pytest test_decoupled_architecture_tdd.py test_surgical_context_builder.py test_local_model_policy.py -v --tb=short",
        "test_runner": "uv run pytest",
        "note": "rank_bm25 requires uv environment; /opt/homebrew/bin/pytest missing rank_bm25",
        "tests_collected": 29, "passed": 29, "failed": 0, "status": "PASS",
        "breakdown": {
            "test_decoupled_architecture_tdd.py": "17 passed",
            "test_surgical_context_builder.py": "3 passed",
            "test_local_model_policy.py": "9 passed"
        }
    }),
    ("known_debt.json", {
        "tests_unit_test_local_resolver_py": {
            "status": "tracked_clean_not_modified",
            "issue": "still imports deprecated Localizer class from localizer.py",
            "risk": "will fail at runtime import after localizer.py deprecation",
            "scope": "Phase 3 debt — should be updated separately or annotated as known skip"
        }
    }),
    ("governance_preservation.json", {
        "archive_status": "PAUSED_ARCHIVED",
        "no_deletion": True, "no_git_clean": True, "no_git_reset": True,
        "no_broad_restore": True, "no_model_calls": True, "no_repair_execution": True,
        "no_verifier_rerun": True, "no_training_export": True, "no_s2t_export": True,
        "no_public_claim": True, "only_tests_committed": True
    }),
]:
    with open(os.path.join(out_dir, artifact), "w") as f:
        json.dump(data, f, indent=2)

report_path = os.path.join(repo_root, f"docs/reports/{gate_id}.md")
with open(report_path, "w") as f:
    f.write("# placeholder\n")

evidence_paths = [
    f"artifacts/runtime/{gate_id}/source_validation.json",
    f"artifacts/runtime/{gate_id}/test_gate_result.json",
    f"artifacts/runtime/{gate_id}/known_debt.json",
    f"artifacts/runtime/{gate_id}/governance_preservation.json",
    f"docs/reports/{gate_id}.md",
]

all_stage = test_files + evidence_paths
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
    print(f"STAGING FAIL: {set(all_stage)} vs {set(staged_paths)}"); exit(1)

res_commit = subprocess.run(
    ["git", "commit", "-m", "test: align local_heal and policy test modifications"],
    capture_output=True, text=True, cwd=repo_root
)
print(res_commit.stdout)

res_hash = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo_root)
commit_hash = res_hash.stdout.strip()

res_status = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, cwd=repo_root)
remaining_tracked = [l for l in res_status.stdout.splitlines() if l.startswith(" M")]

report_content = f"""# Test Review Packet v0

## Summary
Commit: `{commit_hash}`

## Files Committed
| File | Aligned Runtime |
|------|----------------|
| test_decoupled_architecture_tdd.py | local_heal SP-A/SP-B/SP-C |
| test_surgical_context_builder.py | context/localizer SP-A/SP-B |
| test_local_model_policy.py | local_model_policy.py (Phase 0) |

## Verification
- pytest (uv run): 29/29 PASS
  - test_decoupled_architecture_tdd.py: 17 passed
  - test_surgical_context_builder.py: 3 passed
  - test_local_model_policy.py: 9 passed
- staging_verification_status: PASS
- Note: rank_bm25 requires uv environment

## Known Debt
- tests/unit/test_local_resolver.py: still imports deprecated Localizer — tracked-clean, not in this packet scope

## Governance
archive_status: PAUSED_ARCHIVED | no model_calls | no verifier_rerun | no s2t_export
"""
with open(report_path, "w") as f:
    f.write(report_content)
subprocess.run(["git", "add", f"docs/reports/{gate_id}.md"], cwd=repo_root)
subprocess.run(["git", "commit", "--amend", "--no-edit"], cwd=repo_root)

res_final = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo_root)
print(f"Phase 3 FINAL commit: {res_final.stdout.strip()}")
print(f"Remaining tracked modified: {len(remaining_tracked)}")
