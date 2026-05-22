# Nexus Report Retention Plan - 2026-05-22

## Scope
- Plan-only report retention inventory.
- Excludes active `ZERO_TRUST_V2` artifacts.
- No files are moved, deleted, staged, or archived by this artifact.

## Summary
- Reports scanned: `202`
- Active Zero Trust V2 reports excluded: `47`
- Retention class counts: `{'archive_candidate': 26, 'keep_current_entrypoint': 26, 'keep_human_entrypoint': 9, 'keep_review': 68, 'unknown_hold': 73}`
- Topic counts: `{'ENGINEERING_HYGIENE': 11, 'HEEP': 37, 'LEGACY': 4, 'OPTIMIZATION': 5, 'PUBLIC_CLAIM': 16, 'SF': 49, 'UNKNOWN_HOLD': 80}`

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
- `docs/reports/NEXUS_HEEP_PROVIDER_RECEIPT_BLOCKER_RCA_2026-05-20.json` (HEEP, keep_review)
- ... plus `63` more keep/review rows in the JSON inventory.

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
- `docs/reports/NEXUS_SKILL_FIT_CATALOG_REPAIR_AND_CODING_2026-05-15.json` (SF, 2719 bytes)

## Unknown Hold
- `docs/reports/NEXUS_CAPABILITY_INVOCATION_COST_P30_2026-05-10.md` (5872 bytes)
- `docs/reports/NEXUS_CAPABILITY_ROUTE_P44_CLOSURE_2026-05-12.md` (4080 bytes)
- `docs/reports/NEXUS_CAPABILITY_ROUTE_WIRING_P24_2026-05-10.md` (2925 bytes)
- `docs/reports/NEXUS_CBO_IO_MEASUREMENT_2026-05-20.json` (732 bytes)
- `docs/reports/NEXUS_CBO_REPAIR_SPLIT_DECISION_2026-05-20.json` (2999 bytes)
- `docs/reports/NEXUS_CODE_REALITY_P180_2026-05-05.md` (3993 bytes)
- `docs/reports/NEXUS_COMMERCIAL_LANES_GEMINI3FLASH_REPORT_2026-05-02.md` (6137 bytes)
- `docs/reports/NEXUS_COMMERCIAL_ROUTE_COST_TUNING_2026-05-02.md` (7552 bytes)
- `docs/reports/NEXUS_CONTEXTPLUS_LEARNING_GUIDE_V1_2026-05-13.md` (4795 bytes)
- `docs/reports/NEXUS_DCI_RTIMING_ROUTE_COST_P21_2026-05-09.md` (2984 bytes)
- `docs/reports/NEXUS_DOCS_AUTH_EXECUTOR_SEAM_P84_2026-05-13.md` (4763 bytes)
- `docs/reports/NEXUS_DOCS_RECEIPT_RUBRIC_P86_2026-05-13.md` (3800 bytes)
- `docs/reports/NEXUS_EMAS_SAFE_CANDIDATE_INTAKE_2026-05-20.json` (16509 bytes)
- `docs/reports/NEXUS_FEATURE_REFLEX_P68_FLASH_3TASK_2026-05-13.md` (5718 bytes)
- `docs/reports/NEXUS_FEATURE_REFLEX_P74_FLASH_3TASK_3TRIAL_2026-05-13.md` (6214 bytes)
- `docs/reports/NEXUS_FEATURE_REFLEX_P80B_FLASH_3TASK_3TRIAL_2026-05-13.md` (4866 bytes)
- `docs/reports/NEXUS_FLASH_PRO_GOVERNANCE_DECISION_2026-05-03.md` (2160 bytes)
- `docs/reports/NEXUS_FLASH_RHYPER_P10_CLOSURE_2026-05-12.md` (3888 bytes)
- `docs/reports/NEXUS_GEMINI3FLASH_AUTO_SMOKE_2026-05-02.md` (1102 bytes)
- `docs/reports/NEXUS_GPT55_TEACHER_DISTANCE_P231_P360_2026-05-08.md` (3176 bytes)
- `docs/reports/NEXUS_HIDDEN_LITE_PRE_RESCUE_P51_2026-05-13.md` (4145 bytes)
- `docs/reports/NEXUS_HIDDEN_RETRY_MINIMAL_LANE_P35_2026-05-13.md` (5019 bytes)
- `docs/reports/NEXUS_HIDDEN_RETRY_TELEMETRY_P34_2026-05-13.md` (6356 bytes)
- `docs/reports/NEXUS_LEARNING_LOOP_CLOSED_LOOP_REPORT_2026-04-03.md` (7355 bytes)
- `docs/reports/NEXUS_LLM_AUDIT_REPORT.md` (2696 bytes)
- `docs/reports/NEXUS_MODEL_REQUIRED_UPLIFT_GATE_2026-05-13.md` (4490 bytes)
- `docs/reports/NEXUS_OUTCOME_MEMORY_RETENTION_2026-05-20.json` (1075 bytes)
- `docs/reports/NEXUS_P10_ROUTE_COST_EXECUTION_2026-05-09.md` (6864 bytes)
- `docs/reports/NEXUS_P110_LAUNCH_CANDIDATE_GATE_2026-05-10.md` (4431 bytes)
- `docs/reports/NEXUS_P120_LAUNCH_READY_CLOSURE_2026-05-10.md` (4921 bytes)
- `docs/reports/NEXUS_P12_GOAL_CAPABILITY_HEATMAP_2026-05-12.md` (992 bytes)
- `docs/reports/NEXUS_P12_GOAL_CLOSURE_2026-05-12.md` (6295 bytes)
- `docs/reports/NEXUS_P130_GOAL_CLOSURE_2026-05-10.md` (4174 bytes)
- `docs/reports/NEXUS_P23_CAPABILITY_HEATMAP_2026-05-12.md` (992 bytes)
- `docs/reports/NEXUS_P23_GOAL_CLOSURE_2026-05-12.md` (6662 bytes)
- `docs/reports/NEXUS_P28_NEXT_ROUND_MAIN_AXIS_EXECUTION_BOARD_2026-05-13.md` (6023 bytes)
- `docs/reports/NEXUS_RESEARCH_STACK_P30_FLASH_2026-05-05.md` (6196 bytes)
- `docs/reports/NEXUS_ROOT_TEST_ASSET_ARCHIVE_LOG_2026-05-13.md` (1300 bytes)
- `docs/reports/NEXUS_ROUTE_CAPABILITY_CLOSURE_P30_2026-05-10.md` (5494 bytes)
- `docs/reports/NEXUS_ROUTE_CAPABILITY_P90_THREE_ARM_CLOSURE_2026-05-10.md` (6493 bytes)
- ... plus `33` more unknown rows in the JSON inventory.

## Execution Gates
- Do not move Zero Trust V2 files while that agent is active.
- Do not use `git mv` for report retention cleanup.
- Move at most 10 files per later cleanup slice.
- Re-run `git status --short` and reference checks after each later move slice.

## Claim Boundary
- This inventory does not move, delete, stage, or archive files.
- ZERO_TRUST_V2 artifacts are excluded because another agent is actively writing that workstream.
- Archive candidates require a separate owner-approved filesystem move plan before any action.
