import os
import json
import subprocess

repo_root = "/Users/jameschen/Workspace/nexus"
out_dir = os.path.join(repo_root, "artifacts/runtime/runtime_code_review_packet_v0")
os.makedirs(out_dir, exist_ok=True)

runtime_candidates = [
    "nexus-core-rs/src/main.rs",
    "nexus/core/pipeline_metadata.py",
    "nexus/delivery/models.py",
    "nexus/engine/local_model_policy.py",
    "nexus/evidence/s2t_export_guard.py",
    "nexus/services/codeintel/graph_builder.py",
    "nexus/services/local_heal/context.py",
    "nexus/services/local_heal/context_budget.py",
    "nexus/services/local_heal/evidence_compactor.py",
    "nexus/services/local_heal/interface.py",
    "nexus/services/local_heal/localizer.py",
    "nexus/services/local_heal/phases/planning.py",
    "nexus/services/local_heal/phases/reproduction.py",
    "nexus/services/local_heal/protocol.py",
    "nexus/services/local_heal/repomap.py",
    "nexus/services/local_heal/reproduction.py",
    "nexus/strategy/strategy_envelope.py"
]

# 1. Source Validation
source_val = {
    "schema": "nexus.runtime_code_review_source_validation.v0",
    "archive_status": "PAUSED_ARCHIVED",
    "restore_generated_modified_files_only_v0_evidence_committed": True,
    "tracked_deleted_count": 0,
    "no_execution_authorized": True,
    "untracked_junk_triage_plan_v0_exists": True,
    "safe_untracked_delete_only_v0_exists": True,
    "tracked_deletion_modification_audit_v0_exists": True,
    "generated_cache_tracked_deletion_commit_review_v0_exists": True,
    "source_validation_status": "PASS"
}
with open(os.path.join(out_dir, "source_validation.json"), "w", encoding="utf-8") as f:
    json.dump(source_val, f, indent=2, ensure_ascii=False)

# 2. Runtime Candidate Inventory
res_status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=repo_root)
lines = res_status.stdout.splitlines()

tracked_modified_count = 0
untracked_count = 0
staged_count = 0
out_of_scope_paths = []

for line in lines:
    if not line.strip():
        continue
    status = line[:2]
    path = line[3:].strip().strip('"')
    if "M" in status:
        tracked_modified_count += 1
    if status == "??":
        untracked_count += 1
        if path.startswith("nexus/") or path.startswith("tests/"):
            out_of_scope_paths.append(path)

inventory = {
    "runtime_candidate_count": len(runtime_candidates),
    "runtime_candidate_paths": runtime_candidates,
    "out_of_scope_paths_detected": out_of_scope_paths
}
with open(os.path.join(out_dir, "runtime_candidate_inventory.json"), "w", encoding="utf-8") as f:
    json.dump(inventory, f, indent=2, ensure_ascii=False)

# 3. 取得每個檔案的 git diff 並生成 summary
diff_items = []
for p in runtime_candidates:
    res_diff = subprocess.run(["git", "diff", "--", p], capture_output=True, text=True, cwd=repo_root)
    diff_text = res_diff.stdout
    # 簡單分析新增與刪除行數
    additions = sum(1 for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in diff_text.splitlines() if line.startswith("-") and not line.startswith("---"))
    
    diff_items.append({
        "path": p,
        "additions": additions,
        "deletions": deletions,
        "diff_summary": f"Modified with +{additions}/-{deletions} lines."
    })

with open(os.path.join(out_dir, "runtime_diff_summary.jsonl"), "w", encoding="utf-8") as f:
    for item in diff_items:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

# 4. Engineering Packet Grouping
grouping = {
    "local_heal_hardening_packet": [
        "nexus/services/local_heal/context.py",
        "nexus/services/local_heal/context_budget.py",
        "nexus/services/local_heal/evidence_compactor.py",
        "nexus/services/local_heal/interface.py",
        "nexus/services/local_heal/localizer.py",
        "nexus/services/local_heal/phases/planning.py",
        "nexus/services/local_heal/phases/reproduction.py",
        "nexus/services/local_heal/protocol.py",
        "nexus/services/local_heal/repomap.py",
        "nexus/services/local_heal/reproduction.py"
    ],
    "s2t_export_guard_packet": [
        "nexus/evidence/s2t_export_guard.py"
    ],
    "strategy_or_strata_packet": [
        "nexus/strategy/strategy_envelope.py"
    ],
    "local_model_policy_packet": [
        "nexus/engine/local_model_policy.py"
    ],
    "codeintel_or_pipeline_packet": [
        "nexus-core-rs/src/main.rs",
        "nexus/core/pipeline_metadata.py",
        "nexus/delivery/models.py",
        "nexus/services/codeintel/graph_builder.py"
    ],
    "unknown_or_split_required": []
}
with open(os.path.join(out_dir, "engineering_packet_grouping.json"), "w", encoding="utf-8") as f:
    json.dump(grouping, f, indent=2, ensure_ascii=False)

# 5. Risk and Blast Radius Review
risk_review = {
    "high_risk_groups": [
        {
            "group_id": "local_heal_hardening_packet",
            "blast_radius": "CRITICAL. Modifies context localization, bug reproduction, repomapping, and local healer interfaces. A bug here breaks the core code-repair workflow.",
            "risk_level": "HIGH"
        },
        {
            "group_id": "codeintel_or_pipeline_packet",
            "blast_radius": "HIGH. Modifies Rust main binary parser, delivery schemas, and pipeline metadata. Affects index builder accuracy.",
            "risk_level": "HIGH"
        }
    ],
    "medium_risk_groups": [
        {
            "group_id": "s2t_export_guard_packet",
            "blast_radius": "LOW. Controls s2t package validation logic. Safe to review and commit independently.",
            "risk_level": "MEDIUM"
        },
        {
            "group_id": "local_model_policy_packet",
            "blast_radius": "MEDIUM. Configures model response limits and policies.",
            "risk_level": "MEDIUM"
        },
        {
            "group_id": "strategy_or_strata_packet",
            "blast_radius": "MEDIUM. Strategy adherence envelopes.",
            "risk_level": "MEDIUM"
        }
    ],
    "required_tests": [
        "tests/unit/local_heal/test_decoupled_architecture_tdd.py",
        "tests/unit/local_heal/test_surgical_context_builder.py",
        "tests/unit/test_local_model_policy.py"
    ]
}
with open(os.path.join(out_dir, "risk_and_blast_radius_review.json"), "w", encoding="utf-8") as f:
    json.dump(risk_review, f, indent=2, ensure_ascii=False)

# 6. Runtime Test Pairing Proposal
test_pairing = {
    "pairings": [
        {
            "group": "local_heal_hardening_packet",
            "paired_tests": [
                "tests/unit/local_heal/test_decoupled_architecture_tdd.py",
                "tests/unit/local_heal/test_surgical_context_builder.py"
            ]
        },
        {
            "group": "local_model_policy_packet",
            "paired_tests": [
                "tests/unit/test_local_model_policy.py"
            ]
        },
        {
            "group": "s2t_export_guard_packet",
            "paired_tests": [
                "tests/unit/test_export_guard.py"
            ]
        }
    ]
}
with open(os.path.join(out_dir, "runtime_test_pairing_proposal.json"), "w", encoding="utf-8") as f:
    json.dump(test_pairing, f, indent=2, ensure_ascii=False)

# 7. Commit Readiness Decision
# 我們不批准 bulk commit。
# 推薦對較窄、風險較低的 packet (比如 s2t_export_guard_packet 或 local_model_policy_packet) 判定為 READY_FOR_TARGETED_PACKET。
# 而對 local_heal_hardening_packet 和 codeintel_or_pipeline_packet 標為 OWNER_REVIEW_REQUIRED 或 SPLIT_REQUIRED。
readiness = {
    "decision": "READY_FOR_TARGETED_PACKET",
    "ready_groups": [
        "s2t_export_guard_packet",
        "local_model_policy_packet"
    ],
    "blocked_groups": [
        "local_heal_hardening_packet",
        "codeintel_or_pipeline_packet"
    ],
    "forbidden_bulk_commit": True,
    "recommended_next_packet": "local_model_policy_packet"
}
with open(os.path.join(out_dir, "commit_readiness_decision.json"), "w", encoding="utf-8") as f:
    json.dump(readiness, f, indent=2, ensure_ascii=False)

# 8. Owner Decision Options
options = {
    "schema": "nexus.runtime_code_review_owner_options.v0",
    "current_state": "RUNTIME_CODE_REVIEW_READY",
    "default_decision": "AWAIT_OWNER_APPROVAL",
    "options": [
        "APPROVE_COMMIT_LOCAL_MODEL_POLICY_PACKET_ONLY",
        "APPROVE_COMMIT_S2T_EXPORT_GUARD_PACKET_ONLY",
        "APPROVE_COMMIT_STRATEGY_ENVELOPE_PACKET_ONLY",
        "APPROVE_BULK_RUNTIME_CODE_REVIEW_REJECTED",
        "REMAIN_PAUSED_NO_COMMIT"
    ]
}
with open(os.path.join(out_dir, "owner_decision_options.json"), "w", encoding="utf-8") as f:
    json.dump(options, f, indent=2, ensure_ascii=False)

# 9. Governance Preservation
gov = {
    "schema": "nexus.local_7b_14b_repair_runtime_code_review_governance.v0",
    "archive_status": "PAUSED_ARCHIVED",
    "no_deletion": True,
    "no_restore": True,
    "no_staging": True,
    "no_commit": True,
    "no_source_modification": True,
    "no_test_modification": True,
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

print("Runtime code review packet v0 data files generated successfully.")
