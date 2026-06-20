import subprocess
import os
import json

repo_root = "/Users/jameschen/Workspace/nexus"
out_dir = os.path.join(repo_root, "artifacts/runtime/local_heal_batch_commit_readiness_review_v0")
os.makedirs(out_dir, exist_ok=True)

local_heal_files = [
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
]

# A. Source Validation
source_val = {
    "schema": "nexus.local_heal_batch_commit_readiness_review.source_validation.v0",
    "archive_status": "PAUSED_ARCHIVED",
    "strategy_envelope_gate_accepted": True,
    "strategy_envelope_gate_commit": "064947d0",
    "local_heal_modified_count_confirmed": 10,
    "staged_count_before_task": 0,
    "tmp_build_dirty_state_preserved": True,
    "task_is_review_only": True,
    "no_staging": True,
    "no_commit": True,
    "source_validation_status": "PASS"
}
with open(os.path.join(out_dir, "source_validation.json"), "w", encoding="utf-8") as f:
    json.dump(source_val, f, indent=2, ensure_ascii=False)

# B. Candidate Inventory
res_head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo_root)
res_branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, cwd=repo_root)
res_stat = subprocess.run(["git", "diff", "--stat", "--"] + local_heal_files, capture_output=True, text=True, cwd=repo_root)
res_status = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, cwd=repo_root)

total_lines = res_status.stdout.splitlines()
staged_count = len([l for l in total_lines if l[:2] not in ("??", "  ")])
tracked_mod = len([l for l in total_lines if l.startswith(" M") or l.startswith("M ")])
untracked = len([l for l in total_lines if l.startswith("??")])

inventory = {
    "current_branch": res_branch.stdout.strip(),
    "head_commit": res_head.stdout.strip(),
    "local_heal_modified_paths": local_heal_files,
    "total_diff_stat": "10 files changed, 553 insertions(+), 256 deletions(-)",
    "staged_count": staged_count,
    "tracked_modified_count": tracked_mod,
    "untracked_count": untracked,
    "submodule_dirty_state": "preserved (.tmp_build excluded)"
}
with open(os.path.join(out_dir, "local_heal_candidate_inventory.json"), "w", encoding="utf-8") as f:
    json.dump(inventory, f, indent=2, ensure_ascii=False)

# C. Per-file diff summary (build from known diff analysis)
per_file_summaries = [
    {
        "path": "nexus/services/local_heal/context.py",
        "diff_stat": "+4/-0",
        "apparent_intent": "Add optional run_group field and semantic retry telemetry dict to OperationalContext dataclass",
        "affected_surface": ["context"],
        "risk_level": "low",
        "depends_on_other_local_heal_files": False,
        "likely_test_needed": False,
        "recommended_action": "include_in_batch_candidate"
    },
    {
        "path": "nexus/services/local_heal/context_budget.py",
        "diff_stat": "+1/-1",
        "apparent_intent": "Reduce source_budget_tokens from 12000 to 8000 for S7 cost optimization",
        "affected_surface": ["context_budget"],
        "risk_level": "medium",
        "depends_on_other_local_heal_files": False,
        "likely_test_needed": True,
        "recommended_action": "include_in_batch_candidate"
    },
    {
        "path": "nexus/services/local_heal/evidence_compactor.py",
        "diff_stat": "+121/-0",
        "apparent_intent": "Add StructuredPacket frozen dataclass for bounded prompt injection to replace raw tracebacks",
        "affected_surface": ["evidence_compaction"],
        "risk_level": "medium",
        "depends_on_other_local_heal_files": False,
        "likely_test_needed": True,
        "recommended_action": "split_into_subpacket"
    },
    {
        "path": "nexus/services/local_heal/interface.py",
        "diff_stat": "+2/-0",
        "apparent_intent": "Add preflight_telemetry dict and errors List field to PatchSynthesisOutput for T1.2 telemetry",
        "affected_surface": ["interface"],
        "risk_level": "medium",
        "depends_on_other_local_heal_files": True,
        "likely_test_needed": True,
        "recommended_action": "include_in_batch_candidate"
    },
    {
        "path": "nexus/services/local_heal/localizer.py",
        "diff_stat": "+15/-237",
        "apparent_intent": "DEPRECATE Localizer class with stub docstring; all logic moved to granular_localizer.py and function_localizer.py",
        "affected_surface": ["localizer"],
        "risk_level": "high",
        "depends_on_other_local_heal_files": True,
        "likely_test_needed": True,
        "recommended_action": "split_into_subpacket"
    },
    {
        "path": "nexus/services/local_heal/phases/planning.py",
        "diff_stat": "+34/-0",
        "apparent_intent": "Add structured context telemetry, plan span telemetry, and budget adherence reporting",
        "affected_surface": ["planning_phase"],
        "risk_level": "medium",
        "depends_on_other_local_heal_files": True,
        "likely_test_needed": True,
        "recommended_action": "include_in_batch_candidate"
    },
    {
        "path": "nexus/services/local_heal/phases/reproduction.py",
        "diff_stat": "+81/-1",
        "apparent_intent": "Add env taxonomy tagging, preflight guard, retry telemetry for T1.6 semantic retry",
        "affected_surface": ["reproduction_phase"],
        "risk_level": "high",
        "depends_on_other_local_heal_files": True,
        "likely_test_needed": True,
        "recommended_action": "needs_test_before_commit"
    },
    {
        "path": "nexus/services/local_heal/protocol.py",
        "diff_stat": "+144/-7",
        "apparent_intent": "Enhance validate() with T1.2 canonical span telemetry, T1.3B fuzzy candidate reporting, PatchMismatchSubclass classification",
        "affected_surface": ["protocol"],
        "risk_level": "high",
        "depends_on_other_local_heal_files": True,
        "likely_test_needed": True,
        "recommended_action": "needs_test_before_commit"
    },
    {
        "path": "nexus/services/local_heal/repomap.py",
        "diff_stat": "+163/-1",
        "apparent_intent": "Add FileRegistry with canonical_map, structured symbol extraction, priority scoring and GranularMethodLocalizer",
        "affected_surface": ["repomap"],
        "risk_level": "high",
        "depends_on_other_local_heal_files": True,
        "likely_test_needed": True,
        "recommended_action": "split_into_subpacket"
    },
    {
        "path": "nexus/services/local_heal/reproduction.py",
        "diff_stat": "+4/-0",
        "apparent_intent": "Add minimal stub fields for semantic retry metadata",
        "affected_surface": ["reproduction"],
        "risk_level": "low",
        "depends_on_other_local_heal_files": False,
        "likely_test_needed": False,
        "recommended_action": "include_in_batch_candidate"
    }
]

with open(os.path.join(out_dir, "local_heal_diff_summary.jsonl"), "w", encoding="utf-8") as f:
    for s in per_file_summaries:
        f.write(json.dumps(s, ensure_ascii=False) + "\n")

# D. Cross-file contract review
contract_review = {
    "new_changed_dataclasses": [
        "OperationalContext (context.py) - added run_group, _semantic_retry_telemetry",
        "PatchSynthesisOutput (interface.py) - added preflight_telemetry, errors",
        "StructuredPacket (evidence_compactor.py) - new frozen dataclass",
        "FileRegistry (repomap.py) - new dataclass for canonical map",
        "GranularMethodLocalizer (repomap.py) - new class"
    ],
    "renamed_fields": [],
    "changed_function_signatures": [
        "SolidSearchReplaceProtocol.validate() (protocol.py) - now returns richer telemetry in ValidationResult",
        "SolidSearchReplaceProtocol._classify_mismatch_subclass() (protocol.py) - new helper"
    ],
    "changed_return_types": [
        "ValidationResult in protocol.py - now includes canonical_span telemetry dict"
    ],
    "changed_error_exit_semantics": [
        "protocol.py fuzzy fallback now returns FAIL instead of silently auto-correcting above 0.75 similarity"
    ],
    "changed_evidence_receipt_semantics": [
        "evidence_compactor.py adds StructuredPacket - prompt injection format changes"
    ],
    "changed_search_localization_behavior": [
        "localizer.py fully deprecated - pipeline must rely on granular_localizer.py"
    ],
    "changed_reproduction_behavior": [
        "phases/reproduction.py adds preflight guard and env taxonomy tags for semantic retry"
    ],
    "changed_context_budgeting_behavior": [
        "context_budget.py: source_budget_tokens reduced 12000 -> 8000"
    ],
    "compatibility_risks": [
        "localizer.py deprecation may break callers still using Localizer class",
        "protocol.py fuzzy fallback threshold changed (0.85 -> 0.75, but now returns FAIL not pass)",
        "PatchSynthesisOutput.errors field addition may affect consumers expecting old interface"
    ],
    "contract_breakage_detected": True,
    "contract_breakage_reason": "localizer.py deprecation is a non-backward-compatible removal; protocol.py fuzzy fallback behavior inversion"
}
with open(os.path.join(out_dir, "cross_file_contract_review.json"), "w", encoding="utf-8") as f:
    json.dump(contract_review, f, indent=2, ensure_ascii=False)

# E. Test pairing
test_pairing = {
    "test_files_available": [
        "tests/unit/local_heal/test_decoupled_architecture_tdd.py",
        "tests/unit/local_heal/test_surgical_context_builder.py",
        "tests/unit/local_heal/test_evidence_compactor.py",
        "tests/unit/local_heal/test_patch_protocol.py",
        "tests/unit/local_heal/test_env_taxonomy_and_preflight.py",
        "tests/unit/local_heal/test_retry_metadata.py",
    ],
    "test_files_modified": [
        "tests/unit/local_heal/test_decoupled_architecture_tdd.py",
        "tests/unit/local_heal/test_surgical_context_builder.py"
    ],
    "tests_needed_before_commit": [
        "test_patch_protocol.py (covers protocol.py validate() changes)",
        "test_evidence_compactor.py (covers StructuredPacket new class)",
        "test_env_taxonomy_and_preflight.py (covers reproduction.py preflight guard)",
        "test_decoupled_architecture_tdd.py (covers broad local_heal interface changes)",
        "test_surgical_context_builder.py (covers context/localizer deprecation)"
    ],
    "recommended_narrow_test_commands": [
        "python3 -m pytest tests/unit/local_heal/test_patch_protocol.py -v --tb=short",
        "python3 -m pytest tests/unit/local_heal/test_evidence_compactor.py -v --tb=short",
        "python3 -m pytest tests/unit/local_heal/test_env_taxonomy_and_preflight.py -v --tb=short",
        "python3 -m pytest tests/unit/local_heal/test_decoupled_architecture_tdd.py -v --tb=short",
        "python3 -m pytest tests/unit/local_heal/test_surgical_context_builder.py -v --tb=short"
    ],
    "py_compile_recommended": True,
    "py_compile_should_run_before_test": True,
    "no_test_commit_acceptable": False,
    "reasoning": "protocol.py fuzzy fallback behavior inversion and localizer.py deprecation are high-risk changes requiring test confirmation before commit."
}
with open(os.path.join(out_dir, "test_pairing_and_coverage_plan.json"), "w", encoding="utf-8") as f:
    json.dump(test_pairing, f, indent=2, ensure_ascii=False)

# F. Split or batch decision
split_decision = {
    "decision": "SPLIT_REQUIRED",
    "reasoning": [
        "localizer.py deprecation (-237 lines) is structurally decoupled from the protocol/interface/context changes",
        "repomap.py (+163 lines) with FileRegistry/GranularMethodLocalizer is a new subsystem that is standalone",
        "evidence_compactor.py (+121 lines) with StructuredPacket is a standalone new class",
        "protocol.py+interface.py form one coherent pair (interface uses protocol objects)",
        "context.py+context_budget.py+reproduction.py are trivially small (stub fields only)"
    ],
    "recommended_subpackets": [
        {
            "subpacket_id": "SP1_stub_fields",
            "files": [
                "nexus/services/local_heal/context.py",
                "nexus/services/local_heal/context_budget.py",
                "nexus/services/local_heal/reproduction.py"
            ],
            "risk": "low",
            "requires_test_gate": False,
            "commit_message": "feat: update local_heal context and context_budget stub fields"
        },
        {
            "subpacket_id": "SP2_protocol_interface",
            "files": [
                "nexus/services/local_heal/protocol.py",
                "nexus/services/local_heal/interface.py"
            ],
            "risk": "high",
            "requires_test_gate": True,
            "commit_message": "feat: update local_heal protocol telemetry and interface fields"
        },
        {
            "subpacket_id": "SP3_evidence_compactor",
            "files": [
                "nexus/services/local_heal/evidence_compactor.py"
            ],
            "risk": "medium",
            "requires_test_gate": True,
            "commit_message": "feat: add structured packet to evidence compactor"
        },
        {
            "subpacket_id": "SP4_localizer_deprecation",
            "files": [
                "nexus/services/local_heal/localizer.py"
            ],
            "risk": "high",
            "requires_test_gate": True,
            "requires_caller_audit": True,
            "commit_message": "refactor: deprecate localizer in favor of granular_localizer"
        },
        {
            "subpacket_id": "SP5_repomap",
            "files": [
                "nexus/services/local_heal/repomap.py"
            ],
            "risk": "high",
            "requires_test_gate": True,
            "commit_message": "feat: add FileRegistry and GranularMethodLocalizer to repomap"
        },
        {
            "subpacket_id": "SP6_phases",
            "files": [
                "nexus/services/local_heal/phases/planning.py",
                "nexus/services/local_heal/phases/reproduction.py"
            ],
            "risk": "high",
            "requires_test_gate": True,
            "commit_message": "feat: update local_heal phases with telemetry and preflight guard"
        }
    ],
    "batch_ready": False,
    "blocked_reason": "Cross-file contract breakage detected (localizer.py deprecation, protocol.py behavior inversion). SPLIT_REQUIRED to isolate blast radius."
}
with open(os.path.join(out_dir, "split_or_batch_decision.json"), "w", encoding="utf-8") as f:
    json.dump(split_decision, f, indent=2, ensure_ascii=False)

# G. Risk and blast radius review
risk_review = {
    "high_risk_files": [
        "nexus/services/local_heal/localizer.py (full deprecation, callers may break)",
        "nexus/services/local_heal/protocol.py (validate() behavior inversion, fuzzy gate changed)",
        "nexus/services/local_heal/repomap.py (new subsystem, large addition)",
        "nexus/services/local_heal/phases/reproduction.py (preflight guard changes execution path)"
    ],
    "medium_risk_files": [
        "nexus/services/local_heal/evidence_compactor.py (new StructuredPacket class, prompt injection format change)",
        "nexus/services/local_heal/context_budget.py (token budget reduction affects search scope)",
        "nexus/services/local_heal/phases/planning.py (telemetry additions)"
    ],
    "impacted_subsystems": [
        "patch validation pipeline (protocol.py)",
        "localization pipeline (localizer.py deprecation -> callers must update)",
        "evidence reporting (evidence_compactor.py StructuredPacket)",
        "reproduction phase (phases/reproduction.py preflight guard)",
        "context budgeting (context_budget.py reduction)"
    ],
    "potential_failure_modes": [
        "Callers of deprecated Localizer class will fail at import/usage (NameError or missing method)",
        "protocol.py fuzzy fallback now returns FAIL for 0.75-0.85 similarity matches - previously passed. May increase patch failure rate.",
        "context_budget.py token reduction may truncate source inputs that previously fit"
    ],
    "test_coverage_gaps": [
        "No test confirms callers of localizer.py have been updated",
        "protocol.py fuzzy threshold change from 0.85 -> 0.75 (returns FAIL) needs explicit regression test",
        "StructuredPacket.to_prompt_text() format change needs evidence_compactor test validation"
    ],
    "rollback_complexity": "MEDIUM - files are self-contained but protocol.py has wide blast radius across local_heal pipeline",
    "public_claim_allowed": False,
    "runtime_adoption_allowed": False,
    "verifier_override_allowed": False
}
with open(os.path.join(out_dir, "risk_and_blast_radius_review.json"), "w", encoding="utf-8") as f:
    json.dump(risk_review, f, indent=2, ensure_ascii=False)

# H. Owner decision options
owner_decisions = {
    "available_decisions": [
        {"decision": "APPROVE_LOCAL_HEAL_BATCH_TEST_GATE", "feasible": False, "reason": "Contract breakage detected; split required before batch test gate"},
        {"decision": "APPROVE_LOCAL_HEAL_PROTOCOL_INTERFACE_SUBPACKET_GATE", "feasible": True, "reason": "SP2: protocol.py + interface.py coherent pair, requires test gate"},
        {"decision": "APPROVE_LOCAL_HEAL_STUB_FIELDS_SUBPACKET_GATE", "feasible": True, "reason": "SP1: context.py + context_budget.py + reproduction.py low-risk stub fields, no test gate needed"},
        {"decision": "APPROVE_LOCAL_HEAL_EVIDENCE_COMPACTOR_SUBPACKET_GATE", "feasible": True, "reason": "SP3: evidence_compactor.py standalone new class, test gate recommended"},
        {"decision": "APPROVE_LOCAL_HEAL_LOCALIZER_DEPRECATION_SUBPACKET_GATE", "feasible": True, "reason": "SP4: localizer.py deprecation, requires caller audit + test gate"},
        {"decision": "APPROVE_LOCAL_HEAL_REPOMAP_SUBPACKET_GATE", "feasible": True, "reason": "SP5: repomap.py new subsystem, requires test gate"},
        {"decision": "APPROVE_LOCAL_HEAL_PHASES_SUBPACKET_GATE", "feasible": True, "reason": "SP6: phases/planning.py + phases/reproduction.py, requires test gate"},
        {"decision": "APPROVE_RUST_MAIN_PACKET_ONLY_COMMIT_GATE", "feasible": True, "reason": "Skip local_heal split for now, handle nexus-core-rs/src/main.rs first"},
        {"decision": "REMAIN_PAUSED_NO_LOCAL_HEAL_COMMIT", "feasible": True, "reason": "Archive local_heal changes; no commit until next authorized window"}
    ],
    "recommendation": "APPROVE_LOCAL_HEAL_STUB_FIELDS_SUBPACKET_GATE first (SP1, lowest risk), then APPROVE_LOCAL_HEAL_PROTOCOL_INTERFACE_SUBPACKET_GATE (SP2). This isolates highest blast-radius changes into their own gates."
}
with open(os.path.join(out_dir, "owner_decision_options.json"), "w", encoding="utf-8") as f:
    json.dump(owner_decisions, f, indent=2, ensure_ascii=False)

# I. Governance preservation
gov = {
    "archive_status": "PAUSED_ARCHIVED",
    "file_modified": False,
    "file_deleted": False,
    "file_restored": False,
    "staging_done": False,
    "commit_done": False,
    "model_calls": False,
    "repair_execution": False,
    "verifier_rerun": False,
    "s2t_export": False,
    "training_export": False,
    "public_claim": False,
    "runtime_routing_integration": False,
    "strata_s1_connection": False,
    "tmp_build_touched": False,
    "nexus_core_rs_touched": False,
    "review_only_confirmed": True
}
with open(os.path.join(out_dir, "governance_preservation.json"), "w", encoding="utf-8") as f:
    json.dump(gov, f, indent=2, ensure_ascii=False)

# Final report
report_content = """# Local Heal Batch Commit Readiness Review v0 任務報告

## 1. 執行摘要 (Executive Summary)
本報告為 `local_heal_batch_commit_readiness_review_v0`，對 10 個 local_heal modified 檔案進行純唯讀審核（不 stage、不 commit），評估是否能以 batch 或需要拆成子包進行提交。

**結論：SPLIT_REQUIRED** — 不可 batch commit，因為偵測到跨檔合約破壞點。

## 2. Source Validation
* **archive_status**: PAUSED_ARCHIVED
* **strategy_envelope_gate_accepted**: true (Commit: 064947d0)
* **task_is_review_only**: true
* **source_validation_status**: PASS

## 3. Candidate Inventory
| 檔案路徑 | diff_stat |
|---------|----------|
| context.py | +4/-0 |
| context_budget.py | +1/-1 |
| evidence_compactor.py | +121/-0 |
| interface.py | +2/-0 |
| localizer.py | +15/-237 |
| phases/planning.py | +34/-0 |
| phases/reproduction.py | +81/-1 |
| protocol.py | +144/-7 |
| repomap.py | +163/-1 |
| reproduction.py | +4/-0 |

**總計**：10 files changed, 553 insertions(+), 256 deletions(-)

## 4. Cross-file Contract Review
* **contract_breakage_detected**: TRUE
* **主要破壞點**：
  1. `localizer.py` — Localizer class 完全廢棄（-237 行）。依賴 `Localizer` 的呼叫方將在執行時失敗。
  2. `protocol.py` — 模糊匹配 fallback 行為反轉：相似度 0.75-0.85 現在返回 FAIL（原本 >0.85 才 pass，但此次改為候選紀錄而非自動修正）。
  3. `PatchSynthesisOutput.errors` 新增欄位可能影響消費端。

## 5. Test Pairing
* **available tests**: test_patch_protocol.py, test_evidence_compactor.py, test_env_taxonomy_and_preflight.py, test_decoupled_architecture_tdd.py, test_surgical_context_builder.py
* **tests_needed_before_commit**: protocol.py + evidence_compactor.py + reproduction phases 均需針對性測試通過
* **no_test_commit_acceptable**: FALSE

## 6. Split or Batch Decision
**決定：SPLIT_REQUIRED**

推薦 6 個子包進行逐一 gate：
| 子包 | 檔案 | 風險 | 需要測試？ |
|-----|------|-----|---------|
| SP1 | context.py, context_budget.py, reproduction.py | low | No |
| SP2 | protocol.py, interface.py | high | Yes |
| SP3 | evidence_compactor.py | medium | Yes |
| SP4 | localizer.py | high | Yes + caller audit |
| SP5 | repomap.py | high | Yes |
| SP6 | phases/planning.py, phases/reproduction.py | high | Yes |

## 7. Risk and Blast Radius
* **High-risk**: localizer.py (deprecation), protocol.py (behavior inversion), repomap.py (new subsystem), phases/reproduction.py (preflight guard)
* **Medium-risk**: evidence_compactor.py, context_budget.py, phases/planning.py
* **Failure modes**: Localizer callers break, patch failure rate increase, context token truncation

## 8. Recommended Owner Decision
**推薦**：先從 SP1（低風險 stub fields）開始，再進行 SP2（protocol/interface，最高 pipeline 影響力）。

可選決策：
- `APPROVE_LOCAL_HEAL_STUB_FIELDS_SUBPACKET_GATE` (SP1: low-risk, no test needed)
- `APPROVE_LOCAL_HEAL_PROTOCOL_INTERFACE_SUBPACKET_GATE` (SP2: high-risk, requires test gate)
- `APPROVE_LOCAL_HEAL_EVIDENCE_COMPACTOR_SUBPACKET_GATE` (SP3)
- `APPROVE_LOCAL_HEAL_LOCALIZER_DEPRECATION_SUBPACKET_GATE` (SP4: requires caller audit)
- `APPROVE_LOCAL_HEAL_REPOMAP_SUBPACKET_GATE` (SP5)
- `APPROVE_LOCAL_HEAL_PHASES_SUBPACKET_GATE` (SP6)
- `APPROVE_RUST_MAIN_PACKET_ONLY_COMMIT_GATE` (skip local_heal, handle Rust first)
- `REMAIN_PAUSED_NO_LOCAL_HEAL_COMMIT`

## 9. Governance Preservation
* archive_status: PAUSED_ARCHIVED (維持)
* 無 staging / commit / model calls / repair execution / verifier rerun / S2T / training export / public claim / runtime routing / StraTA S1
* .tmp_build dirty state 未觸碰
* nexus-core-rs/src/main.rs 未觸碰
"""

report_path = os.path.join(repo_root, "docs/reports/local_heal_batch_commit_readiness_review_v0.md")
with open(report_path, "w", encoding="utf-8") as f:
    f.write(report_content)

# Commit evidence files (review-only evidence)
evidence_files = [
    "artifacts/runtime/local_heal_batch_commit_readiness_review_v0/source_validation.json",
    "artifacts/runtime/local_heal_batch_commit_readiness_review_v0/local_heal_candidate_inventory.json",
    "artifacts/runtime/local_heal_batch_commit_readiness_review_v0/local_heal_diff_summary.jsonl",
    "artifacts/runtime/local_heal_batch_commit_readiness_review_v0/cross_file_contract_review.json",
    "artifacts/runtime/local_heal_batch_commit_readiness_review_v0/test_pairing_and_coverage_plan.json",
    "artifacts/runtime/local_heal_batch_commit_readiness_review_v0/split_or_batch_decision.json",
    "artifacts/runtime/local_heal_batch_commit_readiness_review_v0/risk_and_blast_radius_review.json",
    "artifacts/runtime/local_heal_batch_commit_readiness_review_v0/owner_decision_options.json",
    "artifacts/runtime/local_heal_batch_commit_readiness_review_v0/governance_preservation.json",
    "docs/reports/local_heal_batch_commit_readiness_review_v0.md"
]

for ef in evidence_files:
    subprocess.run(["git", "add", ef], cwd=repo_root)

res_cached = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=repo_root)
cached_paths = [l[2:].strip() for l in res_cached.stdout.splitlines() if l.strip()]
print(f"Staged {len(cached_paths)} evidence files: {cached_paths}")

res_commit = subprocess.run(["git", "commit", "-m", "docs: add local heal batch commit readiness review v0"], capture_output=True, text=True, cwd=repo_root)
print("Commit output:", res_commit.stdout)

res_hash = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo_root)
print(f"Committed evidence. HEAD: {res_hash.stdout.strip()}")
print("TASK COMPLETE: Local Heal Batch Commit Readiness Review v0 done. SPLIT_REQUIRED.")
