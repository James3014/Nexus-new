# 測試影響映射 (Impact Map)
| 程式碼路徑 | 測試集合 (Directories/Files) | 狀態 | 風險 | 風險原因 |
| :--- | :--- | :--- | :--- | :--- |
| nexus/core | tests/core, tests/test_core_*.py | active | high | core_contract |
| nexus/core/memory_manager.py | tests/core/test_memory_manager_sqlite_retry.py, tests/core/test_memory_manager_write_guard.py, tests/infrastructure/test_sqlite_retry.py | active | high | project_memory_sqlite_retry_contract |
| nexus/learning/skill_registry.py | tests/test_skill_sharing.py::test_skill_registry_upsert_retries_sqlite_busy_then_success, tests/test_skill_sharing.py::test_skill_registry_upsert_keeps_non_busy_errors_fail_fast, tests/test_skill_sharing.py, tests/infrastructure/test_sqlite_retry.py | active | high | skill_registry_sqlite_retry_contract |
| nexus/services | tests/services, tests/test_services_*.py | active | medium | service_contract |
| nexus/engine/capability_planner.py | tests/engine/test_capability_planner.py::test_capability_planner_emits_planned_skill_mount_contract_for_curated_skill | active | high | skill_mount_planner_contract |
| nexus/engine | tests/engine, tests/test_engine_*.py | active | high | governance |
| nexus/app/research_flow_service.py | tests/app/test_research_flow_service.py::test_runtime_skill_mount_contract_requires_confirmed_capability_receipt, tests/app/test_research_flow_service.py::test_runtime_skill_mount_contract_blocks_unconfirmed_planned_mount | active | high | skill_mount_runtime_contract |
| nexus/app | tests/app | active | medium | app_flow |
| nexus/research | tests/research | active | medium | research_loop |
| nexus/benchmark | tests/benchmark | active | medium | benchmark_contract |
| nexus/connectors | tests/connectors | active | medium | connector_contract |
| nexus/security | tests/security | active | high | security |
| nexus/pilot_cli | tests/pilot_cli | active | medium | cli_runtime |
| nexus/health | tests/health | active | medium | health_signal |
| nexus_dag_workflow.py | tests/test_async_dag_workflow.py | active | medium | workflow_contract |
| scripts/engine/nexus_cli.py | tests/test_cli_learn_mode.py, tests/test_cli_commands.py, tests/engine/test_sandbox_actions.py | active | high | governance |
| scripts/engine/commands/sandbox_actions.py | tests/engine/test_sandbox_actions.py | active | medium | sandbox_cli_action_contract |
| scripts/ops/ci_gate.py | tests/ops/test_ci_gate_report_trust_audit.py, tests/ops/test_ci_gate_closeout_contract.py, tests/ops/test_ci_gate_wiki_sync_block.py | active | high | governance |
| scripts/ops/check_skill_catalog_policy.py | tests/learning/test_skill_catalog.py, tests/ops/test_ci_gate_report_trust_audit.py | active | high | skill_catalog_governance |
| scripts/ops/ultra_gate.py | tests/ops/test_ultra_gate.py | active | high | governance |
| scripts/ops/__init__.py | tests/ops/test_anti_drift_gate.py, tests/ops/test_soul_artifact_vault.py | active | medium | compatibility |
| scripts/ops/select_tests.py | tests/ops/test_select_tests.py | active | high | jit_selector |
| scripts/ops/jit_promotion.py | tests/ops/test_jit_promotion.py | active | medium | jit_promotion |
| scripts/ops/build_test_impact_index.py | tests/ops/test_build_test_impact_index.py | active | medium | jit_index |
| scripts/ops/test_changed.sh | tests/ops/test_select_tests.py | active | medium | jit_entrypoint |
| scripts/ops | tests/ops | active | medium | ops_tooling |
| scripts/bench/capability_ab_runner.py | tests/benchmark/test_capability_ab_runner.py::test_run_with_nexus_subprocess_preserves_executor_receipts_without_llm, tests/benchmark/test_capability_ab_runner.py::test_skill_mount_evidence_contract_accepts_causal_runtime_mount, tests/benchmark/test_capability_ab_runner.py::test_skill_mount_evidence_contract_rejects_quarantined_mount | active | high | benchmark_contract |
| scripts/bench/fixture_materialization.py | tests/benchmark/test_fixture_materialization.py | active | high | external_fixture_materialization_contract |
| scripts/bench/public_lane_contract.py | tests/benchmark/test_capability_ab_runner.py::test_skill_mount_evidence_contract_accepts_causal_runtime_mount, tests/benchmark/test_capability_ab_runner.py::test_skill_mount_evidence_contract_rejects_quarantined_mount | active | high | benchmark_contract |
| scripts/bench | tests/benchmark | active | medium | benchmark_contract |
| nexus/learning/skill_catalog.py | tests/learning/test_skill_catalog.py, tests/ops/test_ci_gate_report_trust_audit.py | active | high | skill_catalog_governance |
| tests/ops/test_ci_gate_report_trust_audit.py | tests/ops/test_ci_gate_report_trust_audit.py | active | medium | test_contract |
| tests/ops/test_select_tests.py | tests/ops/test_select_tests.py | active | medium | test_contract |
| tests/test_skill_sharing.py | tests/test_skill_sharing.py | active | medium | test_contract |
| tests/engine/test_sandbox_actions.py | tests/engine/test_sandbox_actions.py | active | medium | test_contract |
| tests/benchmark/test_fixture_materialization.py | tests/benchmark/test_fixture_materialization.py | active | medium | test_contract |
| docs/testing/test_impact_map.md | tests/ops/test_select_tests.py, tests/ops/test_ci_gate_report_trust_audit.py::test_run_changed_only_check_uses_selector_targets | active | high | jit_selector_contract |
| docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md | tests/ops/test_select_tests.py, tests/ops/test_ci_gate_report_trust_audit.py::test_run_changed_only_check_uses_selector_targets | active | medium | plan_contract |
| docs/reports/NEXUS_REFACTOR_REMAINING_START_EVIDENCE_2026-05-23.md | tests/ops/test_select_tests.py, tests/ops/test_ci_gate_report_trust_audit.py::test_run_changed_only_check_uses_selector_targets | active | medium | refactor_start_evidence_contract |
| nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md | tests/ops/test_select_tests.py, tests/ops/test_ci_gate_report_trust_audit.py::test_run_changed_only_check_uses_selector_targets | active | medium | lesson_writeback_contract |
## Candidate Legacy Tests
| 檔案 | 理由 |
| :--- | :--- |
| tests/test_task_runner_phase_task.py | No direct import of core/services/engine found |
| tests/test_gate_ladder_contract.py | No direct import of core/services/engine found |
| tests/test_report_export_schema.py | No direct import of core/services/engine found |
| tests/test_nightshift_local_convergence.py | No direct import of core/services/engine found |
| tests/test_disk_janitor.py | No direct import of core/services/engine found |
| tests/test_script_entrypoints.py | No direct import of core/services/engine found |
| tests/test_skill_sharing.py | No direct import of core/services/engine found |
| tests/test_skills_builtin_inventory.py | No direct import of core/services/engine found |
| tests/test_otel_integration.py | No direct import of core/services/engine found |
| tests/test_migration_safety_validator.py | No direct import of core/services/engine found |
| tests/test_nexus_v1_5_2_external.py | No direct import of core/services/engine found |
| tests/test_ci_gate_phantom_guard.py | No direct import of core/services/engine found |
| tests/test_skills_health.py | No direct import of core/services/engine found |
| tests/test_task_runner_completion_gate.py | No direct import of core/services/engine found |
| tests/test_cross_platform.py | No direct import of core/services/engine found |
| tests/test_webarena_sota.py | No direct import of core/services/engine found |
| tests/test_config_hardening.py | No direct import of core/services/engine found |
| tests/test_blackzone_fixes.py | No direct import of core/services/engine found |
| tests/test_feynman_bridge.py | No direct import of core/services/engine found |
| tests/test_cli_dispatch.py | No direct import of core/services/engine found |
| tests/test_skills_optimization_runner.py | No direct import of core/services/engine found |
| tests/test_magic_strings.py | No direct import of core/services/engine found |
| tests/test_guard_allowlist.py | No direct import of core/services/engine found |
| tests/test_skills_autotune.py | No direct import of core/services/engine found |
| tests/test_critique.py | No direct import of core/services/engine found |
| tests/test_task_runner_heartbeat.py | No direct import of core/services/engine found |
| tests/test_cli_health_commands.py | No direct import of core/services/engine found |
| tests/test_nexus_v1_5_2_internal.py | No direct import of core/services/engine found |
| tests/test_swarm_command_delivery.py | No direct import of core/services/engine found |
| tests/test_ab_eval_schema.py | No direct import of core/services/engine found |
| tests/test_cli_commands.py | No direct import of core/services/engine found |
| tests/test_replay_case_delivery.py | No direct import of core/services/engine found |
| tests/test_v18_legacy_delivery.py | No direct import of core/services/engine found |
| tests/test_llm_token_regex.py | No direct import of core/services/engine found |
