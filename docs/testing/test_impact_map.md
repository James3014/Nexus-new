# 測試影響映射 (Impact Map)
| 程式碼路徑 | 測試集合 (Directories/Files) | 狀態 | 風險 | 風險原因 |
| :--- | :--- | :--- | :--- | :--- |
| nexus/core | tests/core, tests/test_core_*.py | active | high | core_contract |
| nexus/core/context_hub.py | tests/core/test_context_hub_strict_deps.py, tests/core/test_context_budget_sources.py, tests/core/test_context_text_store.py | active | high | context_hub_split_contract |
| nexus/core/context_budget_sources.py | tests/core/test_context_budget_sources.py, tests/core/test_context_hub_strict_deps.py::test_context_hub_uses_split_context_budget_source_builder | active | high | context_hub_split_contract |
| nexus/core/context_text_store.py | tests/core/test_context_text_store.py, tests/core/test_context_hub_strict_deps.py::test_context_hub_uses_split_context_text_store | active | high | context_hub_split_contract |
| nexus/core/memory_manager.py | tests/core/test_memory_manager_sqlite_retry.py, tests/core/test_memory_manager_write_guard.py, tests/infrastructure/test_sqlite_retry.py | active | high | project_memory_sqlite_retry_contract |
| nexus/learning/skill_registry.py | tests/test_skill_sharing.py::test_skill_registry_upsert_retries_sqlite_busy_then_success, tests/test_skill_sharing.py::test_skill_registry_upsert_keeps_non_busy_errors_fail_fast, tests/test_skill_sharing.py, tests/infrastructure/test_sqlite_retry.py | active | high | skill_registry_sqlite_retry_contract |
| nexus/learning/skill_fit_status.py | tests/learning/test_skill_fit_data_shape_pregate.py, tests/learning/test_skill_fit_ablation.py::test_skill_fit_status_rollup_finds_skill_but_blocks_benchmark_until_threshold_clean, tests/learning/test_skill_fit_ablation.py::test_skill_fit_status_rollup_uses_threshold_alternate_candidate_even_if_policy_needs_more_data | active | high | skill_fit_data_shape_pregate_contract |
| nexus/learning/skill_fit_ablation_core.py | tests/learning/test_skill_fit_ablation.py::test_skill_fit_plan_characterizes_public_candidate_selection_contract, tests/learning/test_skill_fit_ablation.py::test_execution_matrix_characterizes_public_row_shape_for_all_arm_types, tests/learning/test_skill_fit_ablation.py::test_execution_matrix_expands_tasks_by_arms_without_claiming_value, tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_index_groups_rows_by_capability_and_skill_id, tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_requires_receipt_backed_effective_rows, tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_groups_verdicts_by_capability_and_skill_id, tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_returns_when_matrix_incomplete | active | high | skill_fit_candidate_catalog_and_execution_matrix_contract |
| nexus/learning/skill_fit_candidate_index.py | tests/learning/test_skill_fit_ablation.py::test_skill_fit_candidate_index_preserves_plan_selection_contract, tests/learning/test_skill_fit_ablation.py::test_skill_fit_plan_characterizes_public_candidate_selection_contract, tests/learning/test_skill_fit_ablation.py::test_plan_dedupes_gstack_prefixed_skill_aliases | active | high | skill_fit_candidate_index_contract |
| nexus/learning/sf2_bounded_probe.py | tests/learning/test_skill_route_taxonomy.py::test_sf2_probe_verdict_catalog_characterizes_multicapability_fail_closed_shape, tests/learning/test_skill_route_taxonomy.py::test_sf2_bounded_probe_static_receipts_keep_runtime_and_benchmark_blocked, tests/learning/test_skill_route_taxonomy.py::test_sf2_completion_gate_closes_only_after_receipts_and_dispositions | active | high | sf2_bounded_probe_fail_closed_contract |
| nexus/services | tests/services, tests/test_services_*.py | active | medium | service_contract |
| nexus/engine/capability_planner.py | tests/engine/test_capability_planner.py::test_capability_planner_emits_planned_skill_mount_contract_for_curated_skill | active | high | skill_mount_planner_contract |
| nexus/engine | tests/engine, tests/test_engine_*.py | active | high | governance |
| nexus/engine/sandbox_runner.py | tests/engine/test_sandbox_actions.py | active | high | sandbox_physical_runner_contract |
| nexus/engine/asi_constraints.py | tests/engine/test_asi_constraints.py::test_asi_constraint_extractor_orders_families_and_preserves_evidence_refs, tests/engine/test_asi_constraints.py | active | medium | asi_constraint_ordering_contract |
| nexus/contracts/s2t_export.py | tests/contracts/test_s2t_contracts.py::test_s2t_agent_lightning_export_emits_preference_pairs, tests/contracts/test_s2t_contracts.py::test_s2t_export_selects_highest_scored_failed_rejected_candidate_stably | active | medium | s2t_export_ordering_contract |
| nexus/app/research_flow_service.py | tests/app/test_research_flow_service.py::test_runtime_skill_mount_contract_requires_confirmed_capability_receipt, tests/app/test_research_flow_service.py::test_runtime_skill_mount_contract_blocks_unconfirmed_planned_mount, tests/app/test_research_flow_service.py::test_forced_hyper_skips_baseline_probe, tests/app/test_research_flow_service.py::test_hyper_guard_fallback_preserves_gateway_token_source, tests/app/test_research_flow_service.py::test_cross_module_hyper_failure_can_rescue_with_original_artifact_verification | active | high | skill_mount_runtime_and_auto_flow_executor_accounting_contract |
| nexus/app/research_s2t_runtime.py | tests/app/test_research_s2t_runtime.py, tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries | active | high | research_s2t_runtime_trace_contract |
| nexus/app | tests/app | active | medium | app_flow |
| nexus/research | tests/research | active | medium | research_loop |
| nexus/research/flow/auto_flow_executor.py | tests/research/test_auto_flow_executor.py, tests/app/test_research_flow_service.py::test_forced_hyper_skips_baseline_probe, tests/app/test_research_flow_service.py::test_hyper_guard_fallback_preserves_gateway_token_source, tests/app/test_research_flow_service.py::test_cross_module_hyper_failure_can_rescue_with_original_artifact_verification | active | high | auto_flow_executor_accounting_contract |
| nexus/research/flow/auto_flow_payload.py | tests/research/test_auto_flow_payload.py, tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries | active | high | auto_flow_payload_contract |
| nexus/research/flow/runtime_state.py | tests/research/test_flow_leaf_modules.py, tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries | active | medium | research_runtime_state_contract |
| nexus/research/flow/runtime_decision.py | tests/research/test_flow_leaf_modules.py, tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries | active | high | research_runtime_decision_contract |
| nexus/research/flow/report_io.py | tests/research/test_flow_leaf_modules.py, tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries | active | medium | research_report_io_contract |
| nexus/research/flow/task_classifier.py | tests/research/test_flow_leaf_modules.py | active | medium | research_task_classifier_contract |
| nexus/research/flow/governance_packets.py | tests/research/test_flow_leaf_modules.py, tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries | active | high | research_governance_packet_contract |
| nexus/research/flow/capability_evidence.py | tests/research/test_flow_leaf_modules.py, tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries | active | high | research_capability_evidence_contract |
| nexus/research/flow/capability_planning.py | tests/research/test_flow_leaf_modules.py, tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries | active | high | research_capability_planning_contract |
| nexus/research/flow/model_training_export.py | tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries | active | high | research_model_training_export_contract |
| nexus/benchmark | tests/benchmark | active | medium | benchmark_contract |
| nexus/connectors | tests/connectors | active | medium | connector_contract |
| nexus/security | tests/security | active | high | security |
| nexus/pilot_cli | tests/pilot_cli | active | medium | cli_runtime |
| nexus/health | tests/health | active | medium | health_signal |
| nexus_dag_workflow.py | tests/test_async_dag_workflow.py | active | medium | workflow_contract |
| scripts/engine/nexus_cli.py | tests/test_cli_learn_mode.py, tests/test_cli_commands.py, tests/engine/test_cli_semantic_contract_audit.py, tests/engine/test_cli_artifact_gate_audit.py, tests/engine/test_bench_actions.py, tests/engine/test_code_actions.py, tests/engine/test_multi_agent_actions.py, tests/engine/test_learn_actions.py, tests/engine/test_research_actions.py, tests/engine/test_sandbox_actions.py, tests/engine/test_registry_actions.py | active | high | governance |
| scripts/engine/commands/bench_actions.py | tests/engine/test_bench_actions.py | active | medium | bench_cli_action_contract |
| scripts/engine/commands/code_actions.py | tests/engine/test_code_actions.py | active | medium | code_cli_action_contract |
| scripts/engine/commands/learn_actions.py | tests/engine/test_learn_actions.py | active | medium | learn_cli_action_contract |
| scripts/engine/commands/multi_agent_actions.py | tests/engine/test_multi_agent_actions.py | active | medium | multi_agent_cli_action_contract |
| scripts/engine/commands/registry_actions.py | tests/engine/test_registry_actions.py | active | medium | registry_cli_action_contract |
| scripts/engine/commands/research_actions.py | tests/engine/test_research_actions.py | active | medium | research_cli_action_contract |
| scripts/engine/commands/sandbox_actions.py | tests/engine/test_sandbox_actions.py | active | medium | sandbox_cli_action_and_physical_runner_contract |
| scripts/ops/ci_gate.py | tests/ops/test_ci_gate_report_trust_audit.py, tests/ops/test_ci_gate_closeout_contract.py, tests/ops/test_ci_gate_wiki_sync_block.py | active | high | governance |
| scripts/ops/check_skill_catalog_policy.py | tests/learning/test_skill_catalog.py, tests/ops/test_ci_gate_report_trust_audit.py | active | high | skill_catalog_governance |
| scripts/ops/capability_invocation_matrix.py | tests/ops/test_capability_invocation_matrix.py::test_capability_invocation_arm_index_preserves_jsonl_diagnostics, tests/ops/test_capability_invocation_matrix.py::test_invocation_matrix_fails_closed_on_missing_model_receipt, tests/ops/test_capability_invocation_matrix.py::test_invocation_matrix_marks_invoked_without_evidence_as_heatmap_red, tests/ops/test_capability_invocation_matrix.py::test_invocation_matrix_exposes_runtime_backed_executor_claim_scope | active | medium | capability_invocation_matrix_contract |
| scripts/ops/capability_invocation_index.py | tests/ops/test_capability_invocation_matrix.py::test_capability_invocation_arm_index_preserves_jsonl_diagnostics, tests/ops/test_capability_invocation_matrix.py::test_invocation_matrix_fails_closed_on_missing_model_receipt | active | medium | capability_invocation_matrix_contract |
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
| nexus/learning/skill_fit_followup.py | tests/learning/test_skill_fit_ablation.py::test_skill_fit_row_index_groups_baselines_catalog_and_skill_rows_for_rca_and_cost, tests/learning/test_skill_fit_ablation.py::test_skill_fit_row_level_rca_recommends_targeted_replay_for_promising_governance_skill, tests/learning/test_skill_fit_ablation.py::test_skill_fit_cost_phase_contract_separates_cost_from_delivery_claims | active | high | skill_fit_row_index_contract |
| tests/ops/test_ci_gate_report_trust_audit.py | tests/ops/test_ci_gate_report_trust_audit.py | active | medium | test_contract |
| tests/ops/test_select_tests.py | tests/ops/test_select_tests.py | active | medium | test_contract |
| tests/ops/test_capability_invocation_matrix.py | tests/ops/test_capability_invocation_matrix.py | active | medium | test_contract |
| tests/engine/test_cli_artifact_gate_audit.py | tests/engine/test_cli_artifact_gate_audit.py | active | medium | test_contract |
| tests/engine/test_cli_semantic_contract_audit.py | tests/engine/test_cli_semantic_contract_audit.py | active | medium | test_contract |
| tests/engine/test_bench_actions.py | tests/engine/test_bench_actions.py | active | medium | test_contract |
| tests/engine/test_code_actions.py | tests/engine/test_code_actions.py | active | medium | test_contract |
| tests/research/test_auto_flow_executor.py | tests/research/test_auto_flow_executor.py, tests/app/test_research_flow_service.py::test_forced_hyper_skips_baseline_probe, tests/app/test_research_flow_service.py::test_hyper_guard_fallback_preserves_gateway_token_source, tests/app/test_research_flow_service.py::test_cross_module_hyper_failure_can_rescue_with_original_artifact_verification | active | high | auto_flow_executor_accounting_contract |
| tests/engine/test_learn_actions.py | tests/engine/test_learn_actions.py | active | medium | test_contract |
| tests/engine/test_multi_agent_actions.py | tests/engine/test_multi_agent_actions.py | active | medium | test_contract |
| tests/engine/test_registry_actions.py | tests/engine/test_registry_actions.py | active | medium | test_contract |
| tests/engine/test_research_actions.py | tests/engine/test_research_actions.py | active | medium | test_contract |
| tests/learning/test_skill_fit_data_shape_pregate.py | tests/learning/test_skill_fit_data_shape_pregate.py | active | medium | test_contract |
| tests/learning/test_skill_fit_ablation.py | tests/learning/test_skill_fit_ablation.py::test_skill_fit_candidate_index_preserves_plan_selection_contract, tests/learning/test_skill_fit_ablation.py::test_skill_fit_plan_characterizes_public_candidate_selection_contract, tests/learning/test_skill_fit_ablation.py::test_execution_matrix_characterizes_public_row_shape_for_all_arm_types, tests/learning/test_skill_fit_ablation.py::test_execution_matrix_expands_tasks_by_arms_without_claiming_value, tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_index_groups_rows_by_capability_and_skill_id, tests/learning/test_skill_fit_ablation.py::test_skill_fit_row_index_groups_baselines_catalog_and_skill_rows_for_rca_and_cost, tests/learning/test_skill_fit_ablation.py::test_skill_fit_row_level_rca_recommends_targeted_replay_for_promising_governance_skill, tests/learning/test_skill_fit_ablation.py::test_skill_fit_cost_phase_contract_separates_cost_from_delivery_claims | active | high | skill_fit_candidate_execution_matrix_and_row_index_contract |
| tests/learning/test_skill_route_taxonomy.py | tests/learning/test_skill_route_taxonomy.py::test_sf2_probe_verdict_catalog_characterizes_multicapability_fail_closed_shape, tests/learning/test_skill_route_taxonomy.py::test_sf2_bounded_probe_static_receipts_keep_runtime_and_benchmark_blocked, tests/learning/test_skill_route_taxonomy.py::test_sf2_completion_gate_closes_only_after_receipts_and_dispositions | active | medium | test_contract |
| tests/test_skill_sharing.py | tests/test_skill_sharing.py | active | medium | test_contract |
| tests/core/test_context_hub_strict_deps.py | tests/core/test_context_hub_strict_deps.py | active | medium | test_contract |
| tests/contracts/test_s2t_contracts.py | tests/contracts/test_s2t_contracts.py | active | medium | test_contract |
| tests/engine/test_sandbox_actions.py | tests/engine/test_sandbox_actions.py | active | medium | test_contract |
| tests/app/test_research_s2t_runtime.py | tests/app/test_research_s2t_runtime.py | active | medium | test_contract |
| tests/app/test_research_flow_service.py | tests/app/test_research_flow_service.py::test_forced_hyper_skips_baseline_probe, tests/app/test_research_flow_service.py::test_hyper_guard_fallback_preserves_gateway_token_source, tests/app/test_research_flow_service.py::test_cross_module_hyper_failure_can_rescue_with_original_artifact_verification, tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries, tests/app/test_research_flow_service.py::test_runtime_skill_mount_contract_requires_confirmed_capability_receipt, tests/app/test_research_flow_service.py::test_runtime_skill_mount_contract_blocks_unconfirmed_planned_mount | active | high | research_flow_service_test_contract |
| tests/research/test_auto_flow_payload.py | tests/research/test_auto_flow_payload.py | active | medium | test_contract |
| tests/research/test_flow_leaf_modules.py | tests/research/test_flow_leaf_modules.py | active | medium | test_contract |
| tests/engine/test_asi_constraints.py | tests/engine/test_asi_constraints.py | active | medium | test_contract |
| tests/benchmark/test_fixture_materialization.py | tests/benchmark/test_fixture_materialization.py | active | medium | test_contract |
| docs/testing/test_impact_map.md | tests/ops/test_select_tests.py, tests/ops/test_ci_gate_report_trust_audit.py::test_run_changed_only_check_uses_selector_targets | active | high | jit_selector_contract |
| docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md | tests/ops/test_select_tests.py, tests/ops/test_ci_gate_report_trust_audit.py::test_run_changed_only_check_uses_selector_targets | active | medium | plan_contract |
| docs/reports/NEXUS_REFACTOR_REMAINING_START_EVIDENCE_2026-05-23.md | tests/ops/test_select_tests.py, tests/ops/test_ci_gate_report_trust_audit.py::test_run_changed_only_check_uses_selector_targets | active | medium | refactor_start_evidence_contract |
| nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md | tests/ops/test_select_tests.py, tests/ops/test_ci_gate_report_trust_audit.py::test_run_changed_only_check_uses_selector_targets | active | medium | lesson_writeback_contract |
| nexus_wiki_vault/06_Ops/Ops - Governance Changelog.md | tests/ops/test_select_tests.py, tests/ops/test_ci_gate_report_trust_audit.py::test_run_changed_only_check_uses_selector_targets | active | medium | governance_changelog_contract |
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
