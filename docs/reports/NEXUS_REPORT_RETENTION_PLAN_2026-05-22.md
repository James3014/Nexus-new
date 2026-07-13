# Nexus Report Retention Plan - 2026-05-22

## Scope
- Plan-only report retention inventory.
- Excludes active `ZERO_TRUST_V2` artifacts.
- No files are moved, deleted, staged, or archived by this artifact.

## Summary
- Reports scanned: `2081`
- Active Zero Trust V2 reports excluded: `49`
- Retention class counts: `{'archive_candidate': 26, 'bounded_handoff': 8, 'experiment_evidence': 20, 'generated_evidence': 19, 'historical_preserved': 670, 'keep_current_entrypoint': 26, 'keep_human_entrypoint': 13, 'keep_review': 71, 'supporting_asset': 11, 'unknown_hold': 1217}`
- Topic counts: `{'ENGINEERING_HYGIENE': 12, 'HEEP': 37, 'LEGACY': 4, 'OPTIMIZATION': 9, 'PUBLIC_CLAIM': 16, 'SF': 649, 'UNKNOWN_HOLD': 1354}`
- Report area counts: `{'archive': 670, 'asset': 11, 'experiment': 20, 'generated': 19, 'handoff': 8, 'root': 1326, 'unknown': 27}`

## Keep Rules
- Keep current decision, runtime apply, post-apply smoke, and human-readable summary/index files at `docs/reports` root.
- Keep files referenced by `NEXUS_SF_WORKSPACE_RETENTION_CURRENT_MANIFEST_2026-05-20.json`.
- Treat raw matrices, task manifests, queues, catalogs, and rollups as archive candidates only after owner review.

## Current Entrypoints
- `docs/reports/FLASH_NEXUS_PUBLIC_CANDIDATE_REPORT_2026-05-04.md` (PUBLIC_CLAIM, keep_review)
- `docs/reports/FLASH_NEXUS_PUBLIC_REPORT_2026-05-04.md` (PUBLIC_CLAIM, keep_review)
- `docs/reports/GEMINI31PRO_NEXUS_VALUE_REPORT_2026-05-01.md` (PUBLIC_CLAIM, keep_review)
- `docs/reports/GEMINI3FLASH_NEXUS_VALUE_REPORT_2026-04-28.md` (PUBLIC_CLAIM, keep_review)
- `docs/reports/GEMINI3FLASH_NEXUS_VALUE_REPORT_2026-05-01.md` (PUBLIC_CLAIM, keep_review)
- `docs/reports/GEMINI_FLASH_NEXUS_P16_P17_2026-05-05.md` (LEGACY, keep_review)
- `docs/reports/GEMINI_FLASH_NEXUS_P378_2026-05-06.md` (LEGACY, keep_review)
- `docs/reports/GPT55_NEXUS_VALUE_REPORT_2026-05-01.md` (PUBLIC_CLAIM, keep_review)
- `docs/reports/IMPLEMENTATION_TRACKING_RFC_OPT_001.md` (OPTIMIZATION, keep_review)
- `docs/reports/IRON_NEXUS_PHASE_A_TO_G_STATUS_2026-05-05.md` (LEGACY, keep_review)
- `docs/reports/MAIN_HARDENED_SYNC_REPORT_2026-05-04.md` (LEGACY, keep_review)
- `docs/reports/NEXUS_CAPABILITY_PLAN_DDTREE_AUTOREASON_ULTRA_ROUTE_2026-04-28.md` (UNKNOWN_HOLD, keep_human_entrypoint)
- `docs/reports/NEXUS_CLAIM_TRAINING_POSTURE_P86_5_2026-05-13.md` (PUBLIC_CLAIM, keep_review)
- `docs/reports/NEXUS_CLEAN_CODE_ROOT_CLEANUP_SAFETY_REVIEW_2026-05-20.md` (ENGINEERING_HYGIENE, keep_review)
- `docs/reports/NEXUS_CLEAN_CODE_ROOT_RETENTION_INVENTORY_2026-05-20.json` (ENGINEERING_HYGIENE, keep_review)
- `docs/reports/NEXUS_CODEBASE_OPTIMIZATION_PREFLIGHT_2026-05-20.json` (OPTIMIZATION, keep_review)
- `docs/reports/NEXUS_COMMERCIAL_LANES_BENCHMARK_PLAN_2026-05-02.md` (UNKNOWN_HOLD, keep_human_entrypoint)
- `docs/reports/NEXUS_CORE_REFACTOR_P72_2026-05-05.md` (ENGINEERING_HYGIENE, keep_review)
- `docs/reports/NEXUS_ENGINEERING_HYGIENE_INDEX_2026-05-18.md` (ENGINEERING_HYGIENE, keep_human_entrypoint)
- `docs/reports/NEXUS_FLASH_COST_OPT_P6_2026-05-03.md` (OPTIMIZATION, keep_review)
- `docs/reports/NEXUS_FLASH_PRO_PUBLIC_REPORT_2026-05-03.md` (PUBLIC_CLAIM, keep_review)
- `docs/reports/NEXUS_GEMINI31PRO_VALUE_BENCHMARK_2026-04-28.md` (PUBLIC_CLAIM, keep_review)
- `docs/reports/NEXUS_GEMINI3FLASH_VALUE_BENCHMARK_2026-04-28.md` (PUBLIC_CLAIM, keep_review)
- `docs/reports/NEXUS_HEEP_EMAS_CONTRACT_2026-05-20.json` (HEEP, keep_review)
- `docs/reports/NEXUS_HEEP_EXECUTOR_RECEIPT_ROUTE_SMOKE_2026-05-20.json` (HEEP, keep_review)
- `docs/reports/NEXUS_HEEP_EXECUTOR_TRIO_NEXT_STEP_PACKET_2026-05-20.json` (HEEP, keep_review)
- `docs/reports/NEXUS_HEEP_EXECUTOR_TRIO_PROVIDER_CLEAN_REPLAY_STATUS_2026-05-20.json` (HEEP, keep_review)
- `docs/reports/NEXUS_HEEP_GOLD_CASE_MANIFEST_2026-05-20.json` (HEEP, keep_review)
- `docs/reports/NEXUS_HEEP_LIVE_MAP_UPDATE_GATE_2026-05-20.json` (HEEP, keep_review)
- `docs/reports/NEXUS_HEEP_LIVE_MODE_DECISION_2026-05-20.json` (HEEP, keep_review)
- `docs/reports/NEXUS_HEEP_LIVE_PILOT_CONTRACT_2026-05-20.json` (HEEP, keep_review)
- `docs/reports/NEXUS_HEEP_LIVE_PILOT_RUN_2026-05-20.json` (HEEP, keep_review)
- `docs/reports/NEXUS_HEEP_MAT_B_BLOCKED_MODE_RESOLUTION_2026-05-20.json` (HEEP, keep_review)
- `docs/reports/NEXUS_HEEP_MAT_B_EXECUTOR_TRIO_REPLAY_STATUS_2026-05-20.json` (HEEP, keep_review)
- `docs/reports/NEXUS_HEEP_MAT_B_FINAL_SKILL_DECISIONS_2026-05-20.json` (HEEP, keep_current_entrypoint)
- `docs/reports/NEXUS_HEEP_MAT_B_HOLD_CLEAN_REPLAY_REPORT_2026-05-20.json` (HEEP, keep_review)
- `docs/reports/NEXUS_HEEP_MAT_B_LIVE_REPORT_2026-05-20.json` (HEEP, keep_review)
- `docs/reports/NEXUS_HEEP_MAT_B_NEXT_REPLAY_STATUS_2026-05-20.json` (HEEP, keep_review)
- `docs/reports/NEXUS_HEEP_MODE_MAP_UPDATE_GATE_V2_2026-05-20.json` (HEEP, keep_review)
- `docs/reports/NEXUS_HEEP_PROVIDER_CLEAN_REPLAY_RCA_2026-05-20.json` (HEEP, keep_review)
- ... plus `70` more keep/review rows in the JSON inventory.

## Archive Candidates
- `docs/reports/NEXUS_HEEP_ASSEMBLY_CATALOG_2026-05-20.json` (HEEP, 42804 bytes)
- `docs/reports/NEXUS_HEEP_FLASH_NEXUS_EXECUTION_MATRIX_2026-05-20.json` (HEEP, 276087 bytes)
- `docs/reports/NEXUS_HEEP_FLASH_NEXUS_LIVE_COMPARE_QUEUE_2026-05-20.json` (HEEP, 112581 bytes)
- `docs/reports/NEXUS_HEEP_FLASH_NEXUS_SKILL_STATUS_2026-05-20.json` (HEEP, 18877 bytes)
- `docs/reports/NEXUS_HEEP_FLASH_NEXUS_TASK_MANIFEST_2026-05-20.json` (HEEP, 35301 bytes)
- `docs/reports/NEXUS_HEEP_LOCAL_ABC_ROLLUP_2026-05-20.json` (HEEP, 13685 bytes)
- `docs/reports/NEXUS_HEEP_MAT_B_BLOCKER_RESOLUTION_QUEUE_2026-05-20.json` (HEEP, 18014 bytes)
- `docs/reports/NEXUS_HEEP_MAT_B_ROLLUP_V2_2026-05-20.json` (HEEP, 27429 bytes)
- `docs/reports/NEXUS_HEEP_MODE_CANDIDATE_CATALOG_2026-05-20.json` (HEEP, 20493 bytes)
- `docs/reports/NEXUS_SFV2_ROLE_ABLATION_EDGECASE_EXECUTION_MATRIX_2026-05-21.json` (SF, 122216 bytes)
- `docs/reports/NEXUS_SFV2_ROLE_ABLATION_EDGECASE_LIVE_ROLLUP_2026-05-21.json` (SF, 31849 bytes)
- `docs/reports/NEXUS_SFV2_ROLE_ABLATION_EDGECASE_SKILL_STATUS_2026-05-21.json` (SF, 5876 bytes)
- `docs/reports/NEXUS_SFV2_ROLE_ABLATION_EDGECASE_TASK_MANIFEST_2026-05-21.json` (SF, 23727 bytes)
- `docs/reports/NEXUS_SFV2_ROLE_ABLATION_EXECUTION_MATRIX_2026-05-20.json` (SF, 77210 bytes)
- `docs/reports/NEXUS_SFV2_ROLE_ABLATION_LIVE_CATALOG_2026-05-20.json` (SF, 826 bytes)
- `docs/reports/NEXUS_SFV2_ROLE_ABLATION_LIVE_ROLLUP_2026-05-20.json` (SF, 21703 bytes)
- `docs/reports/NEXUS_SFV2_ROLE_ABLATION_SKILL_STATUS_2026-05-20.json` (SF, 5897 bytes)
- `docs/reports/NEXUS_SFV2_ROLE_ABLATION_TASK_MANIFEST_2026-05-20.json` (SF, 9522 bytes)
- `docs/reports/NEXUS_SF_FINAL_264_CANDIDATE_CLASSIFICATION_2026-05-21.json` (SF, 257851 bytes)
- `docs/reports/NEXUS_SF_FINAL_ALL_CANDIDATE_LIVE_COMPARE_MATRIX_2026-05-21.json` (SF, 501121 bytes)
- `docs/reports/NEXUS_SF_FINAL_ALL_CANDIDATE_LIVE_COMPARE_SKILL_STATUS_2026-05-21.json` (SF, 71263 bytes)
- `docs/reports/NEXUS_SF_FINAL_ALL_CANDIDATE_LIVE_COMPARE_TASKS_2026-05-21.json` (SF, 37250 bytes)
- `docs/reports/NEXUS_SF_FINAL_LIVE_COMPARE_MATRIX_2026-05-21.json` (SF, 14614 bytes)
- `docs/reports/NEXUS_SF_FINAL_LIVE_COMPARE_SKILL_STATUS_2026-05-21.json` (SF, 3357 bytes)
- `docs/reports/NEXUS_SF_FINAL_LIVE_COMPARE_TASKS_2026-05-21.json` (SF, 3810 bytes)
- `docs/reports/NEXUS_SKILL_FIT_CATALOG_REPAIR_AND_CODING_2026-05-15.json` (SF, 884 bytes)

## Unknown Hold
- `docs/reports/3b_override_verified_rate_analysis.md` (4273 bytes)
- `docs/reports/3b_shadow_advisory_offline_ledger_replay_segment_closure_v0.md` (4096 bytes)
- `docs/reports/3b_shadow_advisory_offline_ledger_replay_v0.md` (3252 bytes)
- `docs/reports/3b_shadow_advisory_offline_ledger_replay_validation_gate_v0.md` (3777 bytes)
- `docs/reports/3b_shadow_advisory_stage2_expansion_approval_packet_v0.md` (4672 bytes)
- `docs/reports/3b_shadow_advisory_stage2_expansion_execution_v0.md` (3794 bytes)
- `docs/reports/3b_shadow_advisory_stage2_expansion_sample_review_v0.md` (4871 bytes)
- `docs/reports/3b_shadow_advisory_stage2_expansion_segment_closure_v0.md` (4362 bytes)
- `docs/reports/3b_shadow_advisory_stage2_expansion_validation_gate_v0.md` (4057 bytes)
- `docs/reports/3b_shadow_advisory_stage3_annotation_materialization_segment_closure_v0.md` (3626 bytes)
- `docs/reports/3b_shadow_advisory_stage3_annotation_materialization_v0.md` (4489 bytes)
- `docs/reports/3b_shadow_advisory_stage3_annotation_materialization_validation_gate_v0.md` (5182 bytes)
- `docs/reports/3b_shadow_advisory_stage3_annotation_plan_review_v0.md` (6422 bytes)
- `docs/reports/3b_shadow_advisory_stage3_archive_receipt_v0.md` (2637 bytes)
- `docs/reports/3b_shadow_advisory_stage3_final_closure_v0.md` (4649 bytes)
- `docs/reports/3b_shadow_advisory_stage3_human_review_annotation_plan_v0.md` (7425 bytes)
- `docs/reports/3b_shadow_advisory_stage3_human_review_annotation_usage_review_v0.md` (4232 bytes)
- `docs/reports/3b_shadow_advisory_stage3_usage_review_segment_closure_v0.md` (4673 bytes)
- `docs/reports/3b_shadow_eval_policy_integration_plan_review_v0.md` (3440 bytes)
- `docs/reports/3b_shadow_eval_policy_integration_plan_v0.md` (5209 bytes)
- `docs/reports/3b_shadow_eval_sample_review_v0.md` (6150 bytes)
- `docs/reports/3b_shadow_eval_schema_tightening_v0.md` (6365 bytes)
- `docs/reports/3b_shadow_eval_tightened_rerun_approval_packet_v0.md` (5364 bytes)
- `docs/reports/3b_shadow_eval_tightened_rerun_execution_v0.md` (4020 bytes)
- `docs/reports/3b_shadow_eval_tightened_rerun_segment_closure_v0.md` (3541 bytes)
- `docs/reports/3b_shadow_eval_tightened_rerun_validation_gate_v0.md` (4751 bytes)
- `docs/reports/3b_shadow_eval_tightened_result_analysis_v0.md` (4512 bytes)
- `docs/reports/3b_shadow_eval_tightened_sample_review_v0.md` (3084 bytes)
- `docs/reports/7R_8R_EVIDENCE_GOVERNANCE_AND_RCA_BIBLE.md` (3801 bytes)
- `docs/reports/7R_8R_governance_status_matrix.md` (2983 bytes)
- `docs/reports/7R_claim_separation_report.md` (907 bytes)
- `docs/reports/7R_pub_bug_004_clean_path_decision.md` (1853 bytes)
- `docs/reports/7R_pub_bug_004_evidence_matrix.md` (2472 bytes)
- `docs/reports/7R_pub_bug_004_exclusion_verdict.md` (2446 bytes)
- `docs/reports/8R_commercial_promotion_manifest.md` (2399 bytes)
- `docs/reports/GPT_task_upstream_gap_closure_20260619.md` (5855 bytes)
- `docs/reports/HYBRID_ROUTE_H4_5_CLOUD_MODEL_E2E_SMOKE_REPORT.md` (4272 bytes)
- `docs/reports/M4_verdict_red_20260619.md` (3927 bytes)
- `docs/reports/NEXUS_ANTIGRAVITY_CLOSURE_LEDGER_2026-05-22.json` (29626 bytes)
- `docs/reports/NEXUS_ANTIGRAVITY_FULL_PREREQUISITE_CLOSEOUT_2026-05-22.json` (2910 bytes)
- ... plus `1177` more unknown rows in the JSON inventory.

## Execution Gates
- Do not move Zero Trust V2 files while that agent is active.
- Do not use `git mv` for report retention cleanup.
- Move at most 10 files per later cleanup slice.
- Re-run `git status --short` and reference checks after each later move slice.

## Claim Boundary
- This inventory does not move, delete, stage, or archive files.
- ZERO_TRUST_V2 artifacts are excluded because another agent is actively writing that workstream.
- Archive candidates require a separate owner-approved filesystem move plan before any action.
