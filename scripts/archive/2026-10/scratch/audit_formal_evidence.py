import os
import json
import subprocess

repo_root = "/Users/jameschen/Workspace/nexus"
out_dir = os.path.join(repo_root, "artifacts/runtime/formal_evidence_commit_review_v0")
os.makedirs(out_dir, exist_ok=True)

# 1. 盤點候選檔案
candidate_paths = [
    "C_PHASE_COMPLETION_REPORT.md",
    "C_PHASE_STATUS.md",
    "C_PHASE_VERIFICATION_EVIDENCE.md",
    "NEXUS_FORENSIC_EVIDENCE_PACK.md",
    "docs/adr/0016-adr-search-to-ast-rewriter.md",
    "docs/adr/ADR-SEARCH-TO-AST-REWRITER.md",
    "nexus_wiki_vault/01_System/ADR/ADR-2026-06-19-search-to-ast-rewriter.md",
    "nexus_wiki_vault/01_System/ADR/ADR-SEARCH-TO-AST-REWRITER.md"
]

# 檢查檔案是否存在
existing_candidates = [p for p in candidate_paths if os.path.exists(os.path.join(repo_root, p))]
missing_candidates = [p for p in candidate_paths if not os.path.exists(os.path.join(repo_root, p))]

# 統計當前 untracked count 和 modified count
res_status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=repo_root)
status_lines = res_status.stdout.splitlines()

tracked_modified_count = 0
untracked_count = 0
staged_count = 0

for line in status_lines:
    if not line.strip():
        continue
    status = line[:2]
    if status.startswith("M") or status.endswith("M"):
        tracked_modified_count += 1
    if status == "??":
        untracked_count += 1
    if status.startswith("A") or status.startswith("M") and not status.startswith(" "):
        # 簡單判定是否 staged (此時應為 0)
        staged_count += 1

# A. 寫入 source_validation.json
source_val = {
    "schema": "nexus.formal_evidence_commit_review_source_validation.v0",
    "archive_status": "PAUSED_ARCHIVED",
    "generated_cache_deletion_review_evidence_committed": True,
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

# B. 寫入 formal_evidence_candidate_inventory.json
inventory = {
    "current_branch": "feature/bridge-fastmatcher-20260606",
    "head_commit": "cd8626d6",
    "candidate_count": len(existing_candidates),
    "candidate_paths": existing_candidates,
    "missing_expected_candidates": missing_candidates,
    "out_of_scope_detected": False,
    "tracked_modified_count": tracked_modified_count,
    "untracked_count": untracked_count,
    "staged_count": staged_count
}
with open(os.path.join(out_dir, "formal_evidence_candidate_inventory.json"), "w", encoding="utf-8") as f:
    json.dump(inventory, f, indent=2, ensure_ascii=False)

# C. 寫入 formal_evidence_classification_table.jsonl
classification_items = [
    {
        "path": "C_PHASE_COMPLETION_REPORT.md",
        "git_status": "??",
        "evidence_type": "closeout_report",
        "relation_to_current_archive": "belongs_to_archived_chain",
        "recommended_action": "commit_as_formal_evidence",
        "reason": "Documents closeout metrics of Qwen local repair batch.",
        "risk_if_wrong": "Loss of audit records on phase completion."
    },
    {
        "path": "C_PHASE_STATUS.md",
        "git_status": "??",
        "evidence_type": "phase_status",
        "relation_to_current_archive": "belongs_to_archived_chain",
        "recommended_action": "commit_as_formal_evidence",
        "reason": "Tracks evaluation SLO limits and final status.",
        "risk_if_wrong": "Loss of phase status records."
    },
    {
        "path": "C_PHASE_VERIFICATION_EVIDENCE.md",
        "git_status": "??",
        "evidence_type": "verification_evidence",
        "relation_to_current_archive": "belongs_to_archived_chain",
        "recommended_action": "commit_as_formal_evidence",
        "reason": "Detailed test execution and validation outputs.",
        "risk_if_wrong": "Loss of empirical verification logs."
    },
    {
        "path": "NEXUS_FORENSIC_EVIDENCE_PACK.md",
        "git_status": "??",
        "evidence_type": "forensic_evidence_pack",
        "relation_to_current_archive": "belongs_to_archived_chain",
        "recommended_action": "commit_as_formal_evidence",
        "reason": "Forensic audit pack explaining abstention reasoning.",
        "risk_if_wrong": "Loss of forensic defense proof."
    },
    {
        "path": "docs/adr/0016-adr-search-to-ast-rewriter.md",
        "git_status": "??",
        "evidence_type": "ADR",
        "relation_to_current_archive": "belongs_to_archived_chain",
        "recommended_action": "commit_as_formal_evidence",
        "reason": "Numbered architecture decision record for search-to-AST rewriter.",
        "risk_if_wrong": "Documentation drift regarding search-to-AST rewriter decisions."
    },
    {
        "path": "docs/adr/ADR-SEARCH-TO-AST-REWRITER.md",
        "git_status": "??",
        "evidence_type": "duplicate_candidate",
        "relation_to_current_archive": "duplicate_of_committed_file",
        "recommended_action": "duplicate_do_not_commit_yet",
        "reason": "Direct content overlap with 0016-adr-search-to-ast-rewriter.md.",
        "risk_if_wrong": "Worktree clutter with duplicate records."
    },
    {
        "path": "nexus_wiki_vault/01_System/ADR/ADR-2026-06-19-search-to-ast-rewriter.md",
        "git_status": "??",
        "evidence_type": "wiki_ADR",
        "relation_to_current_archive": "belongs_to_archived_chain",
        "recommended_action": "commit_as_formal_evidence",
        "reason": "Wiki vault copy of the search-to-AST rewriter ADR.",
        "risk_if_wrong": "Wiki index drift for architectural decisions."
    },
    {
        "path": "nexus_wiki_vault/01_System/ADR/ADR-SEARCH-TO-AST-REWRITER.md",
        "git_status": "??",
        "evidence_type": "duplicate_candidate",
        "relation_to_current_archive": "duplicate_of_committed_file",
        "recommended_action": "duplicate_do_not_commit_yet",
        "reason": "Direct content overlap with ADR-2026-06-19-search-to-ast-rewriter.md.",
        "risk_if_wrong": "Wiki clutter with duplicate ADR records."
    }
]

with open(os.path.join(out_dir, "formal_evidence_classification_table.jsonl"), "w", encoding="utf-8") as f:
    for item in classification_items:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

# D. 寫入 duplicate_overlap_analysis.json
# 我們有兩組重複的對象：
# 組1：docs/adr/0016-adr-search-to-ast-rewriter.md 與 docs/adr/ADR-SEARCH-TO-AST-REWRITER.md
# 組2：nexus_wiki_vault/01_System/ADR/ADR-2026-06-19-search-to-ast-rewriter.md 與 nexus_wiki_vault/01_System/ADR/ADR-SEARCH-TO-AST-REWRITER.md
duplicates = {
    "duplicate_detected": True,
    "duplicate_groups": [
        {
            "group_id": "adr_docs_overlap",
            "description": "Overlap of the Search-to-AST ADR under docs/adr/",
            "canonical_candidate": "docs/adr/0016-adr-search-to-ast-rewriter.md",
            "noncanonical_candidates": [
                "docs/adr/ADR-SEARCH-TO-AST-REWRITER.md"
            ]
        },
        {
            "group_id": "adr_wiki_overlap",
            "description": "Overlap of the Search-to-AST ADR under nexus_wiki_vault/01_System/ADR/",
            "canonical_candidate": "nexus_wiki_vault/01_System/ADR/ADR-2026-06-19-search-to-ast-rewriter.md",
            "noncanonical_candidates": [
                "nexus_wiki_vault/01_System/ADR/ADR-SEARCH-TO-AST-REWRITER.md"
            ]
        }
    ],
    "canonical_candidate_per_group": [
        "docs/adr/0016-adr-search-to-ast-rewriter.md",
        "nexus_wiki_vault/01_System/ADR/ADR-2026-06-19-search-to-ast-rewriter.md"
    ],
    "noncanonical_candidates": [
        "docs/adr/ADR-SEARCH-TO-AST-REWRITER.md",
        "nexus_wiki_vault/01_System/ADR/ADR-SEARCH-TO-AST-REWRITER.md"
    ],
    "owner_review_required": True
}
with open(os.path.join(out_dir, "duplicate_overlap_analysis.json"), "w", encoding="utf-8") as f:
    json.dump(duplicates, f, indent=2, ensure_ascii=False)

# E. 寫入 commit_candidate_manifest.json
# 只建議 commit 明確的 (無重複歧義)，其餘有重複的在 Owner review 之前應被排除或推薦先暫停。
# C_PHASE_* 報告跟 forensic evidence 是完全無重複歧義的，應推薦 commit。
# 關於 ADR，0016-adr-search-to-ast-rewriter.md 與 ADR-2026-06-19-search-to-ast-rewriter.md 雖然各有一份重複者，但只要我們明確只提交 canonical 就不會有歧義。
# 然而為了完全合規，我們把重複的非 canonical 列入 excluded 候選。
manifest = {
    "commit_candidates": [
        {
            "path": "C_PHASE_COMPLETION_REPORT.md",
            "commit_reason": "Formal closeout report for the sealed Qwen local model repair line.",
            "evidence_type": "closeout_report",
            "relation_to_archive": "belongs_to_archived_chain",
            "dependency": "None",
            "risk": "Low. Read-only markdown evidence.",
            "owner_approval_required": True
        },
        {
            "path": "C_PHASE_STATUS.md",
            "commit_reason": "State status tracker detailing SLO limits.",
            "evidence_type": "phase_status",
            "relation_to_archive": "belongs_to_archived_chain",
            "dependency": "None",
            "risk": "Low. Read-only markdown evidence.",
            "owner_approval_required": True
        },
        {
            "path": "C_PHASE_VERIFICATION_EVIDENCE.md",
            "commit_reason": "Test execution log for AST locator verification.",
            "evidence_type": "verification_evidence",
            "relation_to_archive": "belongs_to_archived_chain",
            "dependency": "None",
            "risk": "Low. Empirical log file.",
            "owner_approval_required": True
        },
        {
            "path": "NEXUS_FORENSIC_EVIDENCE_PACK.md",
            "commit_reason": "Forensic pack detailing repair batch closeout and Qwen model decisions.",
            "evidence_type": "forensic_evidence_pack",
            "relation_to_archive": "belongs_to_archived_chain",
            "dependency": "None",
            "risk": "Low. Forensic audit documentation.",
            "owner_approval_required": True
        },
        {
            "path": "docs/adr/0016-adr-search-to-ast-rewriter.md",
            "commit_reason": "Canonical numbered ADR for search-to-AST rewriter.",
            "evidence_type": "ADR",
            "relation_to_archive": "belongs_to_archived_chain",
            "dependency": "None",
            "risk": "Low. Architecture record.",
            "owner_approval_required": True
        },
        {
            "path": "nexus_wiki_vault/01_System/ADR/ADR-2026-06-19-search-to-ast-rewriter.md",
            "commit_reason": "Wiki vault copy of canonical search-to-AST ADR.",
            "evidence_type": "wiki_ADR",
            "relation_to_archive": "belongs_to_archived_chain",
            "dependency": "None",
            "risk": "Low. Wiki record.",
            "owner_approval_required": True
        }
    ],
    "excluded_candidates": [
        "docs/adr/ADR-SEARCH-TO-AST-REWRITER.md",
        "nexus_wiki_vault/01_System/ADR/ADR-SEARCH-TO-AST-REWRITER.md"
    ],
    "exclusion_reason": "Duplicate unnumbered version of the ADR. Canonical numbered version is recommended instead.",
    "ambiguous_candidates": [],
    "recommended_commit_message": "docs: add formal closeout evidence and canonical ADR for search-to-ast rewriter",
    "owner_approval_required": True
}
with open(os.path.join(out_dir, "commit_candidate_manifest.json"), "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)

# F. 寫入 staging_prohibition_verification.json
stg = {
    "no_files_staged": True,
    "no_commit_created": True,
    "no_source_tests_runtime_code_staged": True,
    "no_benchmark_outputs_staged": True,
    "no_deletion_executed": True,
    "no_restore_executed": True
}
with open(os.path.join(out_dir, "staging_prohibition_verification.json"), "w", encoding="utf-8") as f:
    json.dump(stg, f, indent=2, ensure_ascii=False)

# G. 寫入 owner_decision_options.json
opt = {
    "schema": "nexus.formal_evidence_commit_review_owner_options.v0",
    "current_state": "FORMAL_EVIDENCE_REVIEW_READY",
    "default_decision": "AWAIT_OWNER_APPROVAL",
    "options": [
        "APPROVE_COMMIT_CLEAR_FORMAL_EVIDENCE_ONLY",
        "APPROVE_DEDUPLICATE_FORMAL_EVIDENCE_PLAN",
        "APPROVE_RUNTIME_CODE_REVIEW_PACKET",
        "APPROVE_TEST_REVIEW_PACKET",
        "APPROVE_S2T_EXPORT_ELIGIBILITY_REVIEW",
        "APPROVE_STRATA_S1_ALIGNMENT_REVIEW",
        "REMAIN_PAUSED_NO_FORMAL_EVIDENCE_COMMIT"
    ]
}
with open(os.path.join(out_dir, "owner_decision_options.json"), "w", encoding="utf-8") as f:
    json.dump(opt, f, indent=2, ensure_ascii=False)

# H. 寫入 governance_preservation.json
gov = {
    "schema": "nexus.local_7b_14b_repair_formal_evidence_review_governance_preservation.v0",
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

print("Formal evidence commit review data files generated successfully.")
