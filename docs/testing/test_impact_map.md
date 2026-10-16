# 測試影響映射 (Impact Map)
| 程式碼路徑 | 測試集合 (Directories/Files) | 狀態 | 風險 | 風險原因 |
| :--- | :--- | :--- | :--- | :--- |
| uv.lock | tests/product/test_python_runner.py, tests/product/test_http_e2e.py | active | high | frozen_python_oci_lockfile_contract |
| pyproject.toml | tests/product/test_python_runner.py, tests/product/test_http_e2e.py | active | high | frozen_python_oci_dependency_contract |
| product/execution/python_runner.py | tests/product/test_python_runner.py, tests/product/test_http_e2e.py | active | high | frozen_python_oci_runner_http_consumer_contract |
| product | tests/product/test_changeset_certification_adapter.py, tests/product/test_evidence_receipt_hardening.py, tests/product/test_false_completion_benchmark.py, tests/product/test_github_adapter.py, tests/product/test_kernel.py, tests/product/test_robustness.py, tests/product/test_semantic_matrix.py | active | high | product_contract |
| product/kernel/__init__.py | tests/product/test_kernel.py | active | high | product_kernel_contract |
| product/adapters/github.py | tests/product/test_github_adapter.py | active | high | product_github_adapter_contract |
| product/benchmark/__init__.py | tests/product/test_false_completion_benchmark.py | active | high | product_benchmark_contract |
| nexus/contracts/changeset_certification.py | tests/contracts/test_changeset_certification.py, tests/product/test_changeset_certification_adapter.py | active | high | changeset_certification_contract |
| nexus/evidence/tool_exposure_trust.py | tests/evidence/test_tool_exposure_trust.py, tests/nexus/orchestrator/test_canonical_core_transport_tool_exposure.py | active | high | tool_exposure_core_evidence_trust_contract |
| tasks/github-issue-526-host-authority-and-canary-20260823/02-host-effect-authority-receipt.json | tests/contracts/test_gateway_deployment_contract.py, tests/ops/test_mcp_gateway_durable.py | active | high | gateway_host_authority_bundle_contract |
| tasks/github-issue-526-host-authority-and-canary-20260823/10-durable-recovery-authority-receipt.json | tests/contracts/test_gateway_deployment_contract.py, tests/ops/test_mcp_gateway_durable.py | active | high | issue526_r1_recovery_authority_receipt_contract |
| tasks/github-issue-526-host-authority-and-canary-20260823/10-r1-source-acceptance-evidence.json | tests/contracts/test_gateway_deployment_contract.py, tests/ops/test_mcp_gateway_durable.py | active | high | issue526_r1_source_acceptance_evidence_contract |
| tasks/github-issue-526-g20-r1-source-contract-delta-20260903/02-r1-complete-deployment-recovery-authority-receipt.json | tests/contracts/test_gateway_deployment_contract.py, tests/ops/test_mcp_gateway_durable.py | active | high | issue526_clm_runtime_recovery_authority_contract |
| tasks/clm-candidate-evidence-runtime-20260928/01-source-acceptance-evidence.json | tests/contracts/test_gateway_deployment_contract.py, tests/ops/test_mcp_gateway_durable.py | active | high | clm_candidate_evidence_source_acceptance_contract |
| tasks/clm-candidate-evidence-runtime-20260928/02-derived-recovery-request.json | tests/contracts/test_gateway_deployment_contract.py, tests/ops/test_mcp_gateway_durable.py | active | high | clm_candidate_evidence_recovery_request_contract |
| tasks/trajectory-verifier-wave0-runtime-20260930/01-source-acceptance-evidence.json | tests/contracts/test_gateway_deployment_contract.py, tests/ops/test_mcp_gateway_durable.py | active | high | trajectory_verifier_wave0_source_acceptance_contract |
| tasks/trajectory-verifier-wave0-runtime-20260930/02-derived-recovery-request.json | tests/contracts/test_gateway_deployment_contract.py, tests/ops/test_mcp_gateway_durable.py | active | high | trajectory_verifier_wave0_recovery_request_contract |
| tasks/trajectory-verifier-wave1-runtime-20260930/01-source-acceptance-evidence.json | tests/contracts/test_gateway_deployment_contract.py, tests/ops/test_mcp_gateway_durable.py | active | high | trajectory_verifier_wave1_source_acceptance_contract |
| tasks/trajectory-verifier-wave1-runtime-20260930/02-derived-recovery-request.json | tests/contracts/test_gateway_deployment_contract.py, tests/ops/test_mcp_gateway_durable.py | active | high | trajectory_verifier_wave1_recovery_request_contract |
| .gitmodules | tests/ops/test_gitmodules_declares_gitlinks.py | active | high | checkout_gitlink_metadata_contract |
| SWE-bench | tests/ops/test_gitmodules_declares_gitlinks.py | active | low | governed_deletion_retired_path |
| nexus-mempalace | tests/ops/test_gitmodules_declares_gitlinks.py | active | low | governed_deletion_retired_path |
| nexus-rust-v16 | tests/ops/test_gitmodules_declares_gitlinks.py | active | low | governed_deletion_retired_path |
| notebooklm-py-audit | tests/ops/test_gitmodules_declares_gitlinks.py | active | low | governed_deletion_retired_path |
| nexus-evolve | tests/ops/test_gitmodules_declares_gitlinks.py | active | low | governed_deletion_retired_path |
| scripts/Jaden_Storybook.html | tests/ops/test_gitmodules_declares_gitlinks.py | active | low | governed_deletion_retired_path |
| scripts/Jaden_Storybook_v1.md | tests/ops/test_gitmodules_declares_gitlinks.py | active | low | governed_deletion_retired_path |
| scripts/dashboard.html | tests/ops/test_gitmodules_declares_gitlinks.py | active | low | governed_deletion_retired_path |
| configs/federated_dna.yaml | tests/ops/test_gitmodules_declares_gitlinks.py | active | low | governed_deletion_retired_path |
| tenants | tests/ops/test_gitmodules_declares_gitlinks.py | active | low | governed_deletion_retired_path |
| .nexus-core/deletions | tests/ops/test_gitmodules_declares_gitlinks.py | active | low | governed_deletion_retired_path |
| Cargo.toml | tests/ops/test_nightly_quarantine_items_layout.py, tests/ops/test_nightly_quarantine.py | active | low | governed_deletion_retired_path |
| Cargo.lock | tests/ops/test_nightly_quarantine_items_layout.py, tests/ops/test_nightly_quarantine.py | active | low | governed_deletion_retired_path |
| .cargo | tests/ops/test_nightly_quarantine_items_layout.py, tests/ops/test_nightly_quarantine.py | active | low | governed_deletion_retired_path |
| src/lib.rs | tests/ops/test_nightly_quarantine_items_layout.py, tests/ops/test_nightly_quarantine.py | active | low | governed_deletion_retired_path |
| src/fast_matcher.rs | tests/ops/test_nightly_quarantine_items_layout.py, tests/ops/test_nightly_quarantine.py | active | low | governed_deletion_retired_path |
| src/governance | tests/ops/test_nightly_quarantine_items_layout.py, tests/ops/test_nightly_quarantine.py | active | low | governed_deletion_retired_path |
| src/experimental | tests/ops/test_nightly_quarantine_items_layout.py, tests/ops/test_nightly_quarantine.py | active | low | governed_deletion_retired_path |
| nexus-core | tests/ops/test_nightly_quarantine_items_layout.py, tests/ops/test_nightly_quarantine.py | active | low | governed_deletion_retired_path |
| scratch/final_parity_check.py | tests/ops/test_nightly_quarantine_items_layout.py, tests/ops/test_nightly_quarantine.py | active | low | governed_deletion_retired_path |
| scripts/test_l6_mechanical_gate.py | tests/ops/test_nightly_quarantine_items_layout.py, tests/ops/test_nightly_quarantine.py | active | low | governed_deletion_retired_path |
| nexus/delivery/suggestions.py | tests/delivery/test_suggestions.py, tests/test_cli_thinning.py | active | medium | verification_command_suggestion_contract |
| nexus/bridge | tests/integration/test_capability_existence_155.py, tests/integration/test_rust_wave3_cutover.py, tests/core/test_l1_l4_realization.py | active | low | rust_bridge_python_scan_contract |
| .claude | tests/ops/test_claude_handoff_hooks.py | active | medium | claude_handoff_hook_contract |
| HANDOFF.md | tests/ops/test_claude_handoff_hooks.py | active | medium | claude_handoff_hook_contract |
| tests/ops/test_claude_handoff_hooks.py | tests/ops/test_claude_handoff_hooks.py | active | medium | test_contract |
| .claude/hooks/core-precheck-on-stop.sh | tests/ops/test_nexus_core_precheck.py, tests/ops/test_claude_handoff_hooks.py | active | medium | core_precheck_stop_hook_contract |
| .claude/settings.json | tests/ops/test_nexus_core_precheck.py, tests/ops/test_claude_handoff_hooks.py | active | medium | claude_stop_hook_registration_contract |
| scripts/ops/nexus-core-precheck | tests/ops/test_nexus_core_precheck.py | active | medium | core_precheck_dispatch_status_contract |
| tests/ops/test_nexus_core_precheck.py | tests/ops/test_nexus_core_precheck.py | active | medium | test_contract |
| .gitignore | tests/ops/test_repository_secret_hygiene.py, tests/ops/test_select_tests.py | active | high | repository_secret_hygiene_contract |
| .nexus-core/config.toml | tests/ops/test_select_tests.py, tests/ops/test_pr_impact_gate.py | active | high | nexus_core_completion_config_contract |
| .agents/skills | tests/ops/test_skill_file_contract.py, tests/learning/test_skill_catalog.py, tests/learning/test_skill_schema.py, tests/ops/test_ci_gate_report_trust_audit.py | active | high | skill_artifact_contract_and_catalog_governance |
| .github/actions | tests/product/test_client_conformance.py | active | high | action_contract |
| nexus/events | tests/events, tests/core/test_event_bus.py, tests/architecture/test_boundaries_v4.py | active | high | event_store_and_transport_contract |
| nexus/feedback | tests/events, tests/unit/evaluation/test_policy_delta.py, tests/unit/committee/test_data_flow_v267.py, tests/architecture/test_boundaries_v3.py, tests/architecture/test_boundaries_v4.py | active | high | developer_feedback_contract |
| nexus/committee/controller.py | tests/unit/committee/test_data_flow_v267.py, tests/research/test_candidate_evidence_committee_integration.py | active | high | candidate_evidence_committee_sidecar_contract |
| nexus/committee/oracle_touch_guard.py | tests/unit/committee/test_oracle_touch_guard.py, tests/unit/committee/test_data_flow_v267.py | active | high | committee_test_oracle_touch_guard_contract |
| tests/unit/committee/test_oracle_touch_guard.py | tests/unit/committee/test_oracle_touch_guard.py | active | high | test_contract |
| nexus/committee/execution_verifier.py | tests/unit/committee/test_execution_verifier_sandbox.py, tests/services/test_capability_wiring_fixes_groupc.py, tests/unit/committee/test_data_flow_v267.py | active | high | committee_patch_execution_verifier_contract |
| nexus/engine/sandboxed_lane.py | tests/unit/committee/test_execution_verifier_sandbox.py, tests/engine/test_swarm_run_sandbox.py, tests/engine/test_ultra_review_service.py, tests/services/test_capability_wiring_fixes_groupc.py | active | high | untrusted_code_sandbox_contract |
| tests/unit/committee/test_execution_verifier_sandbox.py | tests/unit/committee/test_execution_verifier_sandbox.py | active | high | test_contract |
| nexus/engine/swarm_run.py | tests/engine/test_swarm_run_sandbox.py, tests/services/test_capability_wiring_fixes_groupc.py | active | high | swarm_verify_sandbox_contract |
| tests/engine/test_swarm_run_sandbox.py | tests/engine/test_swarm_run_sandbox.py | active | high | test_contract |
| nexus/committee/diversity_sampler.py | tests/unit/committee/test_data_flow_v267.py, tests/architecture/test_boundaries_v4.py | active | high | issue51_proven_orphan_cleanup_contract |
| nexus/env/diff_report.py | tests/architecture/test_boundaries_v3.py, tests/architecture/test_boundaries_v4.py | active | high | issue51_proven_orphan_cleanup_contract |
| nexus/env/snapshot.py | tests/architecture/test_boundaries_v3.py, tests/architecture/test_boundaries_v4.py | active | high | issue51_proven_orphan_cleanup_contract |
| nexus/policy/compatibility.py | tests/services/test_policy_gate.py, tests/architecture/test_boundaries_v3.py, tests/architecture/test_boundaries_v4.py | active | high | issue51_proven_orphan_cleanup_contract |
| nexus/core | tests/core, tests/test_core_*.py | active | high | core_contract |
| nexus/__init__.py | tests/core/test_layer_ports.py, tests/test_layer_boundaries.py | active | high | core_layer_port_binding_contract |
| nexus/core/layer_ports.py | tests/core/test_layer_ports.py, tests/test_layer_boundaries.py | active | high | core_layer_port_binding_contract |
| nexus/engine/core_ports.py | tests/core/test_layer_ports.py, tests/test_layer_boundaries.py | active | high | core_layer_port_binding_contract |
| nexus/app/core_ports.py | tests/core/test_layer_ports.py, tests/test_layer_boundaries.py | active | high | core_layer_port_binding_contract |
| nexus/core/belief_v02.py | tests/core/test_belief_v02.py | active | high | belief_v02_jsonl_contract |
| nexus/memory | tests/unit/memory, tests/integration/test_v28_contract_sealing.py, tests/test_lab_only_deprecations.py | active | medium | lab_only_module_contract |
| nexus/federation/fleet_manager.py | tests/federation, tests/test_lab_only_deprecations.py | active | medium | lab_only_module_contract |
| nexus/search/sampler.py | tests/unit/committee/search/test_adaptive_resampler.py, tests/unit/committee/test_data_flow_v267.py | active | medium | committee_adaptive_resampler_contract |
| tests/test_lab_only_deprecations.py | tests/test_lab_only_deprecations.py | active | medium | test_contract |
| tests/unit/committee/search/test_adaptive_resampler.py | tests/unit/committee/search/test_adaptive_resampler.py | active | medium | test_contract |
| tests/unit/committee/test_data_flow_v267.py | tests/unit/committee/test_data_flow_v267.py | active | high | test_contract |
| nexus/infrastructure/state_json_store.py | tests/infrastructure/test_state_json_store.py, tests/core, tests/services/test_policy_gate.py, tests/gates/test_s2t_memory_sidecar_fixtures.py, tests/ops/test_select_tests.py, tests/ops/test_pr_impact_gate.py, tests/architecture/test_boundaries.py, tests/architecture/test_boundaries_v2.py, tests/architecture/test_boundaries_v3.py, tests/architecture/test_boundaries_v4.py | active | high | state_json_atomic_cas_contract |
| nexus/core/context_hub.py | tests/core/test_context_hub_strict_deps.py, tests/core/test_context_budget_sources.py, tests/core/test_context_text_store.py | active | high | context_hub_split_contract |
| nexus/core/context_budget_sources.py | tests/core/test_context_budget_sources.py, tests/core/test_context_hub_strict_deps.py::test_context_hub_uses_split_context_budget_source_builder | active | high | context_hub_split_contract |
| nexus/core/context_text_store.py | tests/core/test_context_text_store.py, tests/core/test_context_hub_strict_deps.py::test_context_hub_uses_split_context_text_store | active | high | context_hub_split_contract |
| nexus/core/memory_manager.py | tests/core/test_memory_manager_sqlite_retry.py, tests/core/test_memory_manager_write_guard.py, tests/infrastructure/test_sqlite_retry.py | active | high | project_memory_sqlite_retry_contract |
| nexus/learning | tests/learning | active | high | learning_contract |
| nexus/learning/skill_registry.py | tests/test_skill_sharing.py::test_skill_registry_upsert_retries_sqlite_busy_then_success, tests/test_skill_sharing.py::test_skill_registry_upsert_keeps_non_busy_errors_fail_fast, tests/test_skill_sharing.py, tests/infrastructure/test_sqlite_retry.py | active | high | skill_registry_sqlite_retry_contract |
| nexus/learning/skill_fit_status.py | tests/learning/test_skill_fit_data_shape_pregate.py, tests/learning/test_skill_fit_ablation.py::test_skill_fit_status_rollup_finds_skill_but_blocks_benchmark_until_threshold_clean, tests/learning/test_skill_fit_ablation.py::test_skill_fit_status_rollup_uses_threshold_alternate_candidate_even_if_policy_needs_more_data | active | high | skill_fit_data_shape_pregate_contract |
| nexus/learning/skill_fit_ablation_core.py | tests/learning/test_skill_fit_ablation.py::test_skill_fit_plan_characterizes_public_candidate_selection_contract, tests/learning/test_skill_fit_ablation.py::test_execution_matrix_characterizes_public_row_shape_for_all_arm_types, tests/learning/test_skill_fit_ablation.py::test_execution_matrix_expands_tasks_by_arms_without_claiming_value, tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_index_groups_rows_by_capability_and_skill_id, tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_requires_receipt_backed_effective_rows, tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_groups_verdicts_by_capability_and_skill_id, tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_returns_when_matrix_incomplete | active | high | skill_fit_candidate_catalog_and_execution_matrix_contract |
| nexus/learning/skill_fit_candidate_index.py | tests/learning/test_skill_fit_ablation.py::test_skill_fit_candidate_index_preserves_plan_selection_contract, tests/learning/test_skill_fit_ablation.py::test_skill_fit_plan_characterizes_public_candidate_selection_contract, tests/learning/test_skill_fit_ablation.py::test_plan_dedupes_gstack_prefixed_skill_aliases | active | high | skill_fit_candidate_index_contract |
| nexus/learning/sf2_bounded_probe.py | tests/learning/test_skill_route_taxonomy.py::test_sf2_probe_verdict_catalog_characterizes_multicapability_fail_closed_shape, tests/learning/test_skill_route_taxonomy.py::test_sf2_bounded_probe_static_receipts_keep_runtime_and_benchmark_blocked, tests/learning/test_skill_route_taxonomy.py::test_sf2_completion_gate_closes_only_after_receipts_and_dispositions | active | high | sf2_bounded_probe_fail_closed_contract |
| runtimes/open_swe | tests/services/test_external_intelligence_service.py, tests/services/test_open_swe_external_intelligence.py, tests/services/test_open_swe_worker_transport.py | active | high | external_open_swe_runtime_protocol_security_recovery_contract |
| requirements/canonical-runtime.txt | tests/test_planner_selected_capability_materialization.py, tests/services/test_online_planner_context_input.py, tests/services/test_unified_runtime.py, tests/services/test_unified_runtime_workforce_admission.py, tests/nexus/orchestrator/test_self_hosted_task_service.py, tests/nexus/orchestrator/test_worker_planner_context_input.py | active | high | canonical_runtime_dependency_contract |
| nexus/services/unified_runtime.py | tests/test_planner_selected_capability_materialization.py, tests/services/test_online_planner_context_input.py, tests/services/test_unified_runtime.py, tests/services/test_unified_runtime_workforce_admission.py, tests/nexus/orchestrator/test_worker_planner_context_input.py, tests/services, tests/test_services_*.py | active | high | planner_selected_context_materialization_contract |
| nexus/orchestrator/self_hosted_task_service.py | tests/nexus/orchestrator/test_self_hosted_task_service.py, tests/nexus/orchestrator/test_worker_planner_context_input.py | active | high | self_hosted_worker_planner_context_contract |
| nexus/orchestrator/ambient_core.py | tests/nexus/orchestrator/test_evidence_coverage_live_path.py, tests/nexus/orchestrator/test_self_hosted_task_service.py, tests/nexus/orchestrator/test_managed_local_agent.py | active | high | evidence_coverage_core_verdict_contract |
| nexus/orchestrator/canonical_core_transport.py | tests/nexus/orchestrator/test_evidence_coverage_live_path.py, tests/nexus/orchestrator/test_canonical_core_transport.py, tests/nexus/orchestrator/test_canonical_core_transport_tool_exposure.py, tests/nexus/orchestrator/test_evidence_coverage_reuse_v1.py, tests/nexus/orchestrator/test_wave_d_canaries.py | active | high | canonical_core_transport_contract |
| tests/nexus/orchestrator/_evidence_coverage_live_driver.py | tests/nexus/orchestrator/test_evidence_coverage_live_path.py | active | medium | evidence_coverage_live_driver |
| nexus/orchestrator/bootstrap_agent_authority.py | tests/nexus/orchestrator/test_bootstrap_agent_authority.py, tests/nexus/orchestrator/test_gateway_controller_root.py, tests/nexus/orchestrator/test_owner_confirmation_elicitation.py, tests/nexus/orchestrator/test_task_card_create_expected_evidence.py | active | high | bootstrap_agent_task_card_authority_contract |
| tests/nexus/orchestrator/test_bootstrap_agent_authority.py | tests/nexus/orchestrator/test_bootstrap_agent_authority.py | active | high | test_contract |
| docs/runbooks/declaring_expected_evidence_universe.md | tests/nexus/orchestrator/test_task_card_create_expected_evidence.py, tests/nexus/orchestrator/test_evidence_coverage_live_path.py | active | medium | task_card_expected_evidence_declaration |
| docs/runbooks/gateway_r1_lost_ledger_runbook.md | tests/ops/test_mcp_gateway_durable.py | active | medium | gateway_r1_lost_ledger_runbook |
| nexus/orchestrator/candidate_verifier.py | tests/nexus/orchestrator/test_candidate_verifier.py, tests/nexus/orchestrator/test_self_hosted_task_service.py | active | high | verifier_static_contract_and_retry_recovery |
| nexus/orchestrator/code_integrity_verifier.py | tests/nexus/orchestrator/test_code_integrity_verifier.py, tests/nexus/orchestrator/test_candidate_verifier.py | active | high | code_integrity_candidate_evidence_contract |
| nexus/orchestrator/managed_local_agent.py | tests/nexus/orchestrator/test_managed_local_agent.py, tests/nexus/orchestrator/test_self_hosted_task_service.py | active | high | managed_local_agent_effect_binding_contract |
| nexus/orchestrator/worktree_manager.py | tests/nexus/orchestrator/test_worktree_manager.py, tests/nexus/orchestrator/test_self_hosted_task_service.py | active | high | target_ownership_release_contract |
| nexus/services/external_intelligence_fanout.py | tests/services/test_external_intelligence_fanout.py, tests/services/test_open_swe_worker_transport.py | active | high | external_intelligence_fanout_contract |
| nexus/services/open_swe_external_intelligence.py | tests/services/test_open_swe_external_intelligence.py, tests/services/test_open_swe_worker_transport.py | active | high | open_swe_external_intelligence_effect_projection_contract |
| nexus/services/external_intelligence_core_binding.py | tests/services/test_external_intelligence_core_binding.py, tests/services/test_external_intelligence_fanout.py, tests/services/test_open_swe_worker_transport.py, tests/services/test_external_intelligence_closure.py | active | high | external_intelligence_core_mutation_binding_contract |
| nexus/services | tests/services, tests/test_services_*.py | active | medium | service_contract |
| nexus/cli | tests/services/test_archived_capabilities_2026_10_13.py | active | medium | archived_cli_commands_2026_10_13 |
| nexus/evaluation/eval_harness.py | tests/services/test_archived_legacy_engine_2026_10_13.py | active | medium | archived_legacy_engine_2026_10_13 |
| nexus/config/model_workforce.yaml | tests/contracts/test_model_workforce_policy.py, tests/services/test_model_workforce_policy_loader.py | active | medium | workforce_policy_contract |
| nexus/config/model_three_arm_matrix.yaml | tests/contracts/test_model_workforce_policy.py, tests/calibration/provider_adoption/test_three_arm_wiring.py | active | medium | three_arm_benchmark_matrix |
| nexus/calibration/provider_adoption | tests/calibration/provider_adoption/test_*.py, tests/bench/test_model_calibration_plan.py | active | high | provider_adoption_calibration_evidence_contract |
| nexus/config/model_capability_lineage.yaml | tests/services/test_model_capability_lineage.py, tests/bench/test_model_calibration_plan.py, tests/nexus/orchestrator/test_unified_mcp_gateway.py | active | medium | model_capability_lineage_calibration_contract |
| nexus/engine/capability_planner.py | tests/engine/test_capability_planner.py::test_capability_planner_emits_planned_skill_mount_contract_for_curated_skill | active | high | skill_mount_planner_contract |
| nexus/evidence/claim_boundary.py | tests/architecture/test_planner_alias.py, tests/services/test_mainchain_false_green_gates.py | active | high | runtime_owned_planner_alias_contract |
| nexus/evidence/receipt_base.py | tests/architecture/test_planner_alias.py, tests/services/test_unified_runtime.py | active | high | runtime_owned_planner_alias_contract |
| nexus/engine | tests/engine, tests/test_engine_*.py | active | high | governance |
| nexus/engine/sandbox_runner.py | tests/engine/test_sandbox_actions.py | active | high | sandbox_physical_runner_contract |
| nexus/executors/agy_dispatch_boundary.py | tests/services/test_agy_dispatch_write_boundary.py, tests/services/test_agy_dispatch.py | active | high | agy_dispatch_write_boundary_contract |
| nexus/executors/agy_write_admission.py | tests/nexus/executors/test_agy_write_admission.py, tests/services/test_agy_dispatch_write_boundary.py | active | high | agy_write_admission_run_home_seatbelt_contract |
| nexus/engine/confined_test_runner.py | tests/services/test_post_candidate_seam.py, tests/research/test_post_candidate_seam_wiring.py | active | high | post_candidate_confined_sandbox_hidden_test_forbidden_contract |
| tests/services/test_executor_resolution_observable.py | tests/services/test_executor_resolution_observable.py | active | high | test_contract |
| nexus/services/executor_self_check.py | tests/services/test_executor_resolution_observable.py, tests/services/test_runtime_compat.py | active | high | executor_resolution_observable_self_check_contract |
| nexus/services/post_candidate_seam.py | tests/services/test_post_candidate_seam.py, tests/research/test_post_candidate_seam_wiring.py, tests/services/test_escalate_planner_signal_triggers.py | active | high | post_candidate_seam_sandbox_ultra_review_file_lock_contract |
| nexus/executors/cli_worker.py | tests/nexus/executors/test_cli_worker.py | active | high | cli_worker_executor_contract |
| nexus/executors/exec_policy.py | tests/nexus/executors/test_exec_policy.py, tests/nexus/executors/test_cli_worker.py, tests/nexus/orchestrator/test_candidate_verifier.py, tests/engine/test_cli_pregate.py | active | high | worker_exec_policy_contract |
| nexus/executors/codex_executor.py | tests/nexus/executors/test_codex_executor.py, tests/nexus/executors/test_worker_contract.py, tests/nexus/executors/test_cli_worker.py, tests/nexus/orchestrator/test_worker_planner_context_input.py | active | high | codex_receipt_attempt_count_and_worker_context_contract |
| nexus/executors/worker_registry.py | tests/nexus/executors/test_worker_contract.py, tests/services/test_agy_account_pool.py | active | high | worker_registry_contract |
| nexus/governance/capability_gate.py | tests/engine/test_engine_bootstrap.py, tests/health/test_commander_health_loop.py, tests/services/test_policy_gate.py | active | high | legacy_capability_gate_authority_boundary |
| nexus/engine/asi_constraints.py | tests/engine/test_asi_constraints.py::test_asi_constraint_extractor_orders_families_and_preserves_evidence_refs, tests/engine/test_asi_constraints.py | active | medium | asi_constraint_ordering_contract |
| nexus/contracts/s2t_export.py | tests/contracts/test_s2t_contracts.py::test_s2t_agent_lightning_export_emits_preference_pairs, tests/contracts/test_s2t_contracts.py::test_s2t_export_selects_highest_scored_failed_rejected_candidate_stably | active | medium | s2t_export_ordering_contract |
| nexus/contracts/hybrid_retrieval.py | tests/contracts/test_hybrid_retrieval.py | active | high | hybrid_retrieval_rrf_contract |
| nexus/contracts/planner_snapshot_binding.py | tests/integration/test_local_heal_planner_snapshot_binding.py, tests/integration/test_abc_local_heal_shadow_seam.py, tests/integration/test_n31_fail_closed_local_heal_adapter.py | active | high | planner_snapshot_route_context_binding_contract |
| nexus/engine/capability_executor_controls.py | tests/integration/test_local_heal_planner_snapshot_binding.py, tests/integration/test_abc_local_heal_shadow_seam.py, tests/engine/test_capability_routing_contracts.py | active | high | planner_snapshot_route_context_task_binding_contract |
| nexus/engine/route_decision_adapter.py | tests/engine/test_capability_routing_contracts.py, tests/integration/test_local_heal_planner_snapshot_binding.py | active | high | route_decision_execution_plan_task_binding_contract |
| nexus/services/local_heal/capability_adapter.py | tests/integration/test_local_heal_planner_snapshot_binding.py, tests/integration/test_n31_fail_closed_local_heal_adapter.py, tests/unit/local_heal/test_capability_adapter.py | active | high | local_heal_adapter_route_context_task_binding_contract |
| tests/contracts/test_hybrid_retrieval.py | tests/contracts/test_hybrid_retrieval.py | active | medium | test_contract |
| tests/nexus/executors/test_worker_effect_projection.py | tests/nexus/executors/test_worker_effect_projection.py | active | medium | test_contract |
| tests/nexus/governance/test_capability_gate_authority_boundary.py | tests/nexus/governance/test_capability_gate_authority_boundary.py | active | medium | test_contract |
| tests/nexus/orchestrator/test_candidate_verifier.py | tests/nexus/orchestrator/test_candidate_verifier.py | active | medium | test_contract |
| tests/nexus/orchestrator/test_code_integrity_verifier.py | tests/nexus/orchestrator/test_code_integrity_verifier.py | active | medium | test_contract |
| tests/nexus/orchestrator/test_managed_local_agent.py | tests/nexus/orchestrator/test_managed_local_agent.py | active | medium | test_contract |
| tests/nexus/orchestrator/test_self_hosted_task_service.py | tests/nexus/orchestrator/test_self_hosted_task_service.py | active | medium | test_contract |
| tests/services/test_open_swe_worker_transport.py | tests/services/test_open_swe_worker_transport.py | active | medium | test_contract |
| nexus/app/research_flow_service.py | tests/app/test_research_flow_service.py::test_codeintel_evidence_facade_delegates_to_leaf_module, tests/app/test_research_flow_service.py::test_runtime_skill_mount_contract_requires_confirmed_capability_receipt, tests/app/test_research_flow_service.py::test_runtime_skill_mount_contract_blocks_unconfirmed_planned_mount, tests/app/test_research_flow_service.py::test_forced_hyper_skips_baseline_probe, tests/app/test_research_flow_service.py::test_hyper_guard_fallback_preserves_gateway_token_source, tests/app/test_research_flow_service.py::test_cross_module_hyper_failure_can_rescue_with_original_artifact_verification, tests/research/test_post_candidate_seam_wiring.py | active | high | skill_mount_runtime_auto_flow_and_codeintel_facade_contract |
| nexus/app/research_s2t_runtime.py | tests/app/test_research_s2t_runtime.py, tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries | active | high | research_s2t_runtime_trace_contract |
| nexus/app | tests/app | active | medium | app_flow |
| scripts/nightshift.py | tests/services/test_nightshift_queue_consumer.py, tests/app/test_nightshift_runner_service.py | active | high | issue111_nightshift_entrypoint_queue_contract |
| nexus/research/bench_treatment_lane.py | tests/benchmark/test_ab_treatment_lane.py, tests/app/test_research_flow_treatment_lane.py | active | high | ab_treatment_lane_product_contract |
| nexus/research | tests/research | active | medium | research_loop |
| nexus/experiments/msa_routing/msa_indexer.py | tests/experiments/test_msa_routing.py | active | medium | msa_routing_contract |
| nexus/research/flow/codeintel_context.py | tests/app/test_research_flow_service.py::test_codeintel_evidence_facade_delegates_to_leaf_module, tests/app/test_research_flow_service.py::test_codeintel_context_is_injected_into_task_text, tests/app/test_research_flow_service.py::test_codeintel_context_compact_mode_keeps_evidence_but_trims_payload, tests/app/test_research_flow_service.py::test_codeintel_dci_runs_only_for_evidence_heavy_lane, tests/app/test_research_flow_service.py::test_build_codeintel_evidence_reuses_run_cache_graph | active | high | research_codeintel_context_contract |
| nexus/research/flow/auto_flow_executor.py | tests/research/test_auto_flow_executor.py, tests/app/test_research_flow_service.py::test_forced_hyper_skips_baseline_probe, tests/app/test_research_flow_service.py::test_hyper_guard_fallback_preserves_gateway_token_source, tests/app/test_research_flow_service.py::test_cross_module_hyper_failure_can_rescue_with_original_artifact_verification | active | high | auto_flow_executor_accounting_contract |
| nexus/research/flow/unified_capability_projection.py | tests/research/test_unified_capability_projection.py, tests/research/test_auto_flow_executor.py, tests/research/test_auto_flow_baseline_report.py | active | high | unified_runtime_capability_receipt_binding_contract |
| nexus/research/gate_inputs.py | tests/research/test_gate_inputs_wiring.py, tests/research/test_sprint_runtime_verifier_proof.py, tests/research/test_post_candidate_seam_wiring.py | active | high | sprint_gate_inputs_wiring_contract |
| nexus/research/flow/auto_flow_payload.py | tests/research/test_auto_flow_payload.py, tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries | active | high | auto_flow_payload_contract |
| nexus/research/flow/runtime_state.py | tests/research/test_flow_leaf_modules.py, tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries | active | medium | research_runtime_state_contract |
| nexus/research/flow/runtime_decision.py | tests/research/test_flow_leaf_modules.py, tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries | active | high | research_runtime_decision_contract |
| nexus/research/flow/report_io.py | tests/research/test_flow_leaf_modules.py, tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries | active | medium | research_report_io_contract |
| nexus/research/flow/task_classifier.py | tests/research/test_flow_leaf_modules.py | active | medium | research_task_classifier_contract |
| nexus/research/flow/governance_packets.py | tests/research/test_flow_leaf_modules.py, tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries | active | high | research_governance_packet_contract |
| nexus/research/flow/capability_evidence.py | tests/research/test_flow_leaf_modules.py, tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries | active | high | research_capability_evidence_contract |
| nexus/research/flow/capability_planning.py | tests/research/test_flow_leaf_modules.py, tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries | active | high | research_capability_planning_contract |
| nexus/research/flow/meta_opt_preset.py | tests/research/test_meta_opt_preset.py, tests/engine/test_research_actions.py | active | medium | research_meta_opt_preset_contract |
| nexus/research/flow/model_training_export.py | tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries | active | high | research_model_training_export_contract |
| nexus/benchmark | tests/benchmark | active | medium | benchmark_contract |
| nexus/connectors | tests/connectors | active | medium | connector_contract |
| nexus/security | tests/security | active | high | security |
| nexus/pilot_cli | tests/pilot_cli | active | medium | cli_runtime |
| nexus/health | tests/health | active | medium | health_signal |
| nexus_dag_workflow.py | tests/test_async_dag_workflow.py | active | medium | workflow_contract |
| scripts/engine/nexus_cli.py | tests/test_cli_learn_mode.py, tests/test_cli_commands.py, tests/engine/test_cli_semantic_contract_audit.py, tests/engine/test_cli_artifact_gate_audit.py, tests/engine/test_bench_actions.py, tests/engine/test_code_actions.py, tests/engine/test_multi_agent_actions.py, tests/engine/test_learn_actions.py, tests/engine/test_research_actions.py, tests/engine/test_sandbox_actions.py, tests/engine/test_registry_actions.py | active | high | governance |
| tests/engine/test_run_delivery_closeout.py | tests/engine/test_run_delivery_closeout.py | active | medium | test_contract |
| nexus/delivery/status_report.py | tests/ops/test_nexus_status_honesty.py | active | high | delivery_contract |
| nexus/delivery/receipt.py | tests/delivery/test_receipt.py, tests/engine/test_run_delivery_closeout.py, tests/ops/test_delivery_gate_contract.py | active | high | delivery_contract |
| tests/test_cli_output_contract.py | tests/test_cli_output_contract.py | active | medium | test_contract |
| scripts/engine/commands/bench_actions.py | tests/engine/test_bench_actions.py | active | medium | bench_cli_action_contract |
| scripts/engine/commands/self_hosted_actions.py | tests/engine/test_self_hosted_cli.py | active | medium | self_hosted_cli_action_contract |
| scripts/engine/commands/code_actions.py | tests/engine/test_code_actions.py | active | medium | code_cli_action_contract |
| scripts/engine/commands/learn_actions.py | tests/engine/test_learn_actions.py | active | medium | learn_cli_action_contract |
| scripts/engine/commands/multi_agent_actions.py | tests/engine/test_multi_agent_actions.py | active | medium | multi_agent_cli_action_contract |
| scripts/engine/commands/registry_actions.py | tests/engine/test_registry_actions.py | active | medium | registry_cli_action_contract |
| scripts/eval | tests/eval/test_memory_ab_v1.py | active | medium | memory_ab_eval_harness_contract |
| scripts/engine/commands/research_actions.py | tests/engine/test_research_actions.py | active | medium | research_cli_action_contract |
| scripts/engine/commands/sandbox_actions.py | tests/engine/test_sandbox_actions.py | active | medium | sandbox_cli_action_and_physical_runner_contract |
| scripts/engine/commands/stress_test.py | tests/engine/test_simulated_evaluation_honesty.py | active | medium | simulated_evaluation_honesty_contract |
| scripts/local_heal/run_june_regression_pack.py | tests/unit/local_heal/test_june_regression_pack_env_scope.py, tests/integration/test_real_model_probe.py, tests/integration/test_june_regression_pack.py | active | medium | june_regression_pack_env_scope_contract |
| scripts/engine/commands/swarm.py | tests/services/test_distill_swarm_honesty.py, tests/test_swarm_command_delivery.py | active | medium | swarm_tag_opt_in_contract |
| tests/test_metabolism.py | tests/test_metabolism.py | active | medium | test_contract |
| scripts/ui-validator.py | tests/engine/test_simulated_evaluation_honesty.py | active | medium | simulated_evaluation_honesty_contract |
| tests/engine/test_simulated_evaluation_honesty.py | tests/engine/test_simulated_evaluation_honesty.py | active | medium | test_contract |
| tests/engine/test_mainchain_gate_selection.py | tests/engine/test_mainchain_gate_selection.py | active | medium | test_contract |
| scripts/ops/ci_gate.py | tests/ops/test_ci_gate_report_trust_audit.py, tests/ops/test_ci_gate_closeout_contract.py, tests/ops/test_ci_gate_wiki_sync_block.py | active | high | governance |
| scripts/ops/_nexus_enforced_briefing.sh | tests/ops/test_nexus_enforced_briefing.py | active | high | enforced_agent_briefing_contract |
| scripts/ops/run_gemini_nexus_round.sh | tests/ops/test_nexus_enforced_briefing.py | active | high | enforced_agent_briefing_contract |
| .nexus/reports/enforced_agent_briefing.md | tests/ops/test_nexus_enforced_briefing.py | active | high | enforced_agent_briefing_contract |
| docs/AGENT_MANDATORY_PROTOCOL.md | tests/ops/test_nexus_enforced_briefing.py, tests/services/test_continuous_learning.py | active | high | mandatory_agent_protocol_contract |
| scripts/ops/check_skill_catalog_policy.py | tests/learning/test_skill_catalog.py, tests/ops/test_ci_gate_report_trust_audit.py | active | high | skill_catalog_governance |
| scripts/ops/capability_invocation_matrix.py | tests/ops/test_capability_invocation_matrix.py::test_capability_invocation_arm_index_preserves_jsonl_diagnostics, tests/ops/test_capability_invocation_matrix.py::test_invocation_matrix_fails_closed_on_missing_model_receipt, tests/ops/test_capability_invocation_matrix.py::test_invocation_matrix_marks_invoked_without_evidence_as_heatmap_red, tests/ops/test_capability_invocation_matrix.py::test_invocation_matrix_exposes_runtime_backed_executor_claim_scope | active | medium | capability_invocation_matrix_contract |
| scripts/ops/capability_invocation_index.py | tests/ops/test_capability_invocation_matrix.py::test_capability_invocation_arm_index_preserves_jsonl_diagnostics, tests/ops/test_capability_invocation_matrix.py::test_invocation_matrix_fails_closed_on_missing_model_receipt | active | medium | capability_invocation_matrix_contract |
| scripts/ops/ultra_gate.py | tests/ops/test_ultra_gate.py | active | high | governance |
| scripts/ops/trusted_deletion_anchor.py | tests/ops/test_trusted_deletion_anchor.py, tests/ops/test_trusted_deletion_anchor_pr960.py, tests/ops/test_trusted_deletion_anchor_tempdir_cleanup.py, tests/ops/test_trusted_dependency_contract.py | active | high | trusted_deletion_anchor_verifier_contract |
| scripts/ops/trusted_impact_gate.py | tests/ops/test_trusted_impact_gate.py, tests/ops/test_pr_impact_gate.py | active | high | trusted_impact_gate_verifier_contract |
| scripts/ops/trusted_dependency_contract.py | tests/ops/test_trusted_dependency_contract.py, tests/ops/test_trusted_deletion_anchor.py | active | high | trusted_dependency_contract_check |
| tests/ops/test_trusted_dependency_contract.py | tests/ops/test_trusted_dependency_contract.py | active | high | test_contract |
| tests/ops/test_trusted_deletion_anchor_tempdir_cleanup.py | tests/ops/test_trusted_deletion_anchor_tempdir_cleanup.py | active | high | test_contract |
| nexus/config/governance_manifest.json | tests/governance/test_audit_gate_honesty.py, tests/test_iron_gate_governance.py | active | high | governance_seal_manifest |
| nexus/delivery/replay_runner.py | tests/governance/test_audit_gate_honesty.py, tests/governance/test_replay_runner_allowlist.py, tests/test_iron_gate_governance.py | active | high | replay_runner_allowlist |
| nexus/governance/learning_gate.py | tests/governance/test_audit_gate_honesty.py, tests/health | active | high | learning_gate_unverified_contract |
| nexus/infrastructure/storage_implementations.py | tests/governance/test_audit_gate_honesty.py, tests/core/test_mempalace_belief_writer_path.py | active | medium | belief_store_read_status |
| nexus/services/belief_constraint_producer.py | tests/core/test_mempalace_belief_writer_path.py | active | medium | belief_constraint_producer_contract |
| tests/engine/test_ultra_review_service.py | tests/engine/test_ultra_review_service.py | active | medium | test_contract |
| tests/ops/test_ultra_gate.py | tests/ops/test_ultra_gate.py | active | medium | test_contract |
| scripts/ops/__init__.py | tests/ops/test_anti_drift_gate.py, tests/ops/test_soul_artifact_vault.py | active | medium | compatibility |
| scripts/ops/select_tests.py | tests/ops/test_select_tests.py | active | high | jit_selector |
| scripts/ops/jit_promotion.py | tests/ops/test_jit_promotion.py | active | medium | jit_promotion |
| scripts/ops/build_test_impact_index.py | tests/ops/test_build_test_impact_index.py | active | medium | jit_index |
| scripts/ops/test_changed.sh | tests/ops/test_select_tests.py | active | medium | jit_entrypoint |
| scripts/ops | tests/ops | active | medium | ops_tooling |
| docs/reports/policy-manifest.v2.json | tests/ops/test_policy_manifest_schema.py, tests/ops/test_policy_lane_gate.py, tests/integration/test_policy_lane_integration.py, tests/ops/test_update_manifest_drills.py | active | high | policy_manifest_contract |
| scripts/ops/check_policy_lane_gate.py | tests/ops/test_policy_manifest_schema.py, tests/ops/test_policy_lane_gate.py, tests/integration/test_policy_lane_integration.py | active | high | policy_lane_gate_contract |
| scripts/ops/update_manifest_drills.py | tests/ops/test_update_manifest_drills.py, tests/ops/test_policy_manifest_schema.py | active | medium | policy_manifest_updater_contract |
| scripts/ci/nexus-core-verify.sh | tests/ops/test_select_tests.py, tests/ops/test_pr_impact_gate.py | active | high | nexus_core_completion_ci_entrypoint_contract |
| scripts/ci/nexus_core_trusted_pin_policy.py | tests/ops/test_nexus_core_trusted_pin_policy.py, tests/ops/test_select_tests.py, tests/ops/test_pr_impact_gate.py | active | high | nexus_core_trusted_pin_maintenance_contract |
| scripts/bench/capability_ab_runner.py | tests/benchmark/test_capability_ab_runner.py::test_run_with_nexus_subprocess_preserves_executor_receipts_without_llm, tests/benchmark/test_capability_ab_runner.py::test_skill_mount_evidence_contract_accepts_causal_runtime_mount, tests/benchmark/test_capability_ab_runner.py::test_skill_mount_evidence_contract_rejects_quarantined_mount, tests/benchmark/test_ab_hidden_test_staging.py | active | high | benchmark_contract |
| tests/benchmark/data/online_ab_hard_v1_prompt_data.json | tests/benchmark/test_ab_no_answer_hints.py | active | medium | ab_prompt_symmetry_contract |
| scripts/bench/agy_prompt_capture.py | tests/benchmark/test_ab_prompt_symmetry_audit.py, tests/benchmark/test_ab_treatment_lane.py | active | high | ab_prompt_symmetry_contract |
| scripts/bench/prompt_symmetry_schema.json | tests/benchmark/test_ab_prompt_symmetry_audit.py, tests/benchmark/test_ab_treatment_lane.py | active | high | ab_prompt_symmetry_contract |
| scripts/bench/prompt_symmetry_audit.py | tests/benchmark/test_ab_prompt_symmetry_audit.py, tests/benchmark/test_ab_treatment_lane.py | active | high | ab_prompt_symmetry_contract |
| scripts/bench/hidden_test_staging.py | tests/benchmark/test_ab_hidden_test_staging.py, tests/benchmark/test_ab_prompt_symmetry_audit.py | active | high | ab_hidden_test_staging_contract |
| scripts/bench/fixture_materialization.py | tests/benchmark/test_fixture_materialization.py | active | high | external_fixture_materialization_contract |
| scripts/bench/public_lane_contract.py | tests/benchmark/test_capability_ab_runner.py::test_skill_mount_evidence_contract_accepts_causal_runtime_mount, tests/benchmark/test_capability_ab_runner.py::test_skill_mount_evidence_contract_rejects_quarantined_mount | active | high | benchmark_contract |
| scripts/bench/treatment_lane.py | tests/benchmark/test_ab_treatment_lane.py, tests/benchmark/test_ab_prompt_symmetry_audit.py | active | high | ab_treatment_lane_fairness_contract |
| scripts/bench/run_lane.py | tests/benchmark/test_ab_treatment_lane.py | active | medium | ab_treatment_lane_command_contract |
| scripts/bench/treatment_replay_proof.py | tests/benchmark/test_ab_treatment_lane.py | active | medium | ab_treatment_lane_proof_contract |
| scripts/bench/analyze_run.py | tests/benchmark/test_ab_treatment_lane.py | active | medium | ab_treatment_lane_report_contract |
| scripts/bench | tests/benchmark | active | medium | benchmark_contract |
| scripts/local_heal/run_controlled_local_solve_fixture.py | tests/integration/test_controlled_local_solve_fixture_runner.py | active | high | local_heal_controlled_solve_fixture_contract |
| nexus/learning/skill_catalog.py | tests/learning/test_skill_catalog.py, tests/ops/test_ci_gate_report_trust_audit.py | active | high | skill_catalog_governance |
| nexus/learning/skill_fit_followup.py | tests/learning/test_skill_fit_ablation.py::test_skill_fit_row_index_groups_baselines_catalog_and_skill_rows_for_rca_and_cost, tests/learning/test_skill_fit_ablation.py::test_skill_fit_row_level_rca_recommends_targeted_replay_for_promising_governance_skill, tests/learning/test_skill_fit_ablation.py::test_skill_fit_cost_phase_contract_separates_cost_from_delivery_claims | active | high | skill_fit_row_index_contract |
| tests/ops/test_ci_gate_report_trust_audit.py | tests/ops/test_ci_gate_report_trust_audit.py | active | medium | test_contract |
| tests/governance/test_audit_gate_honesty.py | tests/governance/test_audit_gate_honesty.py | active | medium | test_contract |
| tests/governance/test_replay_runner_allowlist.py | tests/governance/test_replay_runner_allowlist.py | active | medium | test_contract |
| tests/ops/test_stage_b_replay.py | tests/ops/test_stage_b_replay.py | active | medium | test_contract |
| tests/test_iron_gate_governance.py | tests/test_iron_gate_governance.py | active | medium | test_contract |
| tests/ops/test_repository_secret_hygiene.py | tests/ops/test_repository_secret_hygiene.py, tests/ops/test_select_tests.py | active | high | repository_secret_hygiene_contract |
| tests/ops/test_select_tests.py | tests/ops/test_select_tests.py | active | medium | test_contract |
| tests/ops/test_nexus_enforced_briefing.py | tests/ops/test_nexus_enforced_briefing.py | active | high | enforced_agent_briefing_contract |
| tests/ops/test_capability_invocation_matrix.py | tests/ops/test_capability_invocation_matrix.py | active | medium | test_contract |
| tests/engine/test_cli_artifact_gate_audit.py | tests/engine/test_cli_artifact_gate_audit.py | active | medium | test_contract |
| tests/engine/test_cli_semantic_contract_audit.py | tests/engine/test_cli_semantic_contract_audit.py | active | medium | test_contract |
| tests/engine/test_bench_actions.py | tests/engine/test_bench_actions.py | active | medium | test_contract |
| tests/engine/test_code_actions.py | tests/engine/test_code_actions.py | active | medium | test_contract |
| tests/research/test_auto_flow_executor.py | tests/research/test_auto_flow_executor.py, tests/app/test_research_flow_service.py::test_forced_hyper_skips_baseline_probe, tests/app/test_research_flow_service.py::test_hyper_guard_fallback_preserves_gateway_token_source, tests/app/test_research_flow_service.py::test_cross_module_hyper_failure_can_rescue_with_original_artifact_verification | active | high | auto_flow_executor_accounting_contract |
| tests/engine/test_learn_actions.py | tests/engine/test_learn_actions.py | active | medium | test_contract |
| tests/engine/test_multi_agent_actions.py | tests/engine/test_multi_agent_actions.py | active | medium | test_contract |
| tests/engine/test_cli_failure_exit_codes.py | tests/engine/test_cli_failure_exit_codes.py | active | medium | test_contract |
| tests/engine/test_delegate_completion_contract.py | tests/engine/test_delegate_completion_contract.py | active | medium | test_contract |
| tests/engine/test_registry_actions.py | tests/engine/test_registry_actions.py | active | medium | test_contract |
| tests/engine/test_research_actions.py | tests/engine/test_research_actions.py | active | medium | test_contract |
| tests/research/test_meta_opt_preset.py | tests/research/test_meta_opt_preset.py | active | medium | test_contract |
| tests/learning/test_skill_fit_data_shape_pregate.py | tests/learning/test_skill_fit_data_shape_pregate.py | active | medium | test_contract |
| tests/learning/test_skill_fit_ablation.py | tests/learning/test_skill_fit_ablation.py::test_skill_fit_candidate_index_preserves_plan_selection_contract, tests/learning/test_skill_fit_ablation.py::test_skill_fit_plan_characterizes_public_candidate_selection_contract, tests/learning/test_skill_fit_ablation.py::test_execution_matrix_characterizes_public_row_shape_for_all_arm_types, tests/learning/test_skill_fit_ablation.py::test_execution_matrix_expands_tasks_by_arms_without_claiming_value, tests/learning/test_skill_fit_ablation.py::test_skill_fit_catalog_index_groups_rows_by_capability_and_skill_id, tests/learning/test_skill_fit_ablation.py::test_skill_fit_row_index_groups_baselines_catalog_and_skill_rows_for_rca_and_cost, tests/learning/test_skill_fit_ablation.py::test_skill_fit_row_level_rca_recommends_targeted_replay_for_promising_governance_skill, tests/learning/test_skill_fit_ablation.py::test_skill_fit_cost_phase_contract_separates_cost_from_delivery_claims | active | high | skill_fit_candidate_execution_matrix_and_row_index_contract |
| tests/learning/test_skill_route_taxonomy.py | tests/learning/test_skill_route_taxonomy.py::test_sf2_probe_verdict_catalog_characterizes_multicapability_fail_closed_shape, tests/learning/test_skill_route_taxonomy.py::test_sf2_bounded_probe_static_receipts_keep_runtime_and_benchmark_blocked, tests/learning/test_skill_route_taxonomy.py::test_sf2_completion_gate_closes_only_after_receipts_and_dispositions | active | medium | test_contract |
| tests/test_skill_sharing.py | tests/test_skill_sharing.py | active | medium | test_contract |
| tests/core/test_belief_v02.py | tests/core/test_belief_v02.py | active | medium | test_contract |
| tests/core/test_context_hub_strict_deps.py | tests/core/test_context_hub_strict_deps.py | active | medium | test_contract |
| tests/core/test_mission_control.py | tests/core/test_mission_control.py | active | medium | test_contract |
| tests/core/test_mission_transitions.py | tests/core/test_mission_transitions.py | active | medium | test_contract |
| tests/core/test_drone_hud_and_run.py | tests/core/test_drone_hud_and_run.py | active | medium | test_contract |
| tests/contracts/test_s2t_contracts.py | tests/contracts/test_s2t_contracts.py | active | medium | test_contract |
| tests/engine/test_sandbox_actions.py | tests/engine/test_sandbox_actions.py | active | medium | test_contract |
| tests/app/test_research_s2t_runtime.py | tests/app/test_research_s2t_runtime.py | active | medium | test_contract |
| tests/app/test_research_flow_service.py | tests/app/test_research_flow_service.py::test_codeintel_evidence_facade_delegates_to_leaf_module, tests/app/test_research_flow_service.py::test_forced_hyper_skips_baseline_probe, tests/app/test_research_flow_service.py::test_hyper_guard_fallback_preserves_gateway_token_source, tests/app/test_research_flow_service.py::test_cross_module_hyper_failure_can_rescue_with_original_artifact_verification, tests/app/test_research_flow_service.py::test_run_auto_flow_populates_autoreason_from_candidate_summaries, tests/app/test_research_flow_service.py::test_runtime_skill_mount_contract_requires_confirmed_capability_receipt, tests/app/test_research_flow_service.py::test_runtime_skill_mount_contract_blocks_unconfirmed_planned_mount | active | high | research_flow_service_test_contract |
| tests/research/test_auto_flow_payload.py | tests/research/test_auto_flow_payload.py | active | medium | test_contract |
| tests/research/test_flow_leaf_modules.py | tests/research/test_flow_leaf_modules.py | active | medium | test_contract |
| nexus/research/flow/auto_flow_decision.py | tests/research/test_auto_flow_decision.py | active | high | auto_flow_decision_engine_contract |
| tests/research/test_auto_flow_decision.py | tests/research/test_auto_flow_decision.py | active | medium | test_contract |
| nexus/research/flow/evidence_packer.py | tests/research/test_auto_nightshift_on_hyper_failure.py | active | high | auto_nightshift_on_hyper_failure_contract |
| tests/research/test_auto_nightshift_on_hyper_failure.py | tests/research/test_auto_nightshift_on_hyper_failure.py | active | medium | test_contract |
| tests/engine/test_asi_constraints.py | tests/engine/test_asi_constraints.py | active | medium | test_contract |
| tests/benchmark/test_fixture_materialization.py | tests/benchmark/test_fixture_materialization.py | active | medium | test_contract |
| docs/testing/test_impact_map.md | tests/ops/test_select_tests.py, tests/ops/test_ci_gate_report_trust_audit.py::test_run_changed_only_check_uses_selector_targets | active | high | jit_selector_contract |
| docs/plans/NEXUS_CLEAN_CODE_LINUS_REFACTOR_PLAN_2026-05-22.md | tests/ops/test_select_tests.py, tests/ops/test_ci_gate_report_trust_audit.py::test_run_changed_only_check_uses_selector_targets | active | medium | plan_contract |
| docs/reports/NEXUS_REFACTOR_REMAINING_START_EVIDENCE_2026-05-23.md | tests/ops/test_select_tests.py, tests/ops/test_ci_gate_report_trust_audit.py::test_run_changed_only_check_uses_selector_targets | active | medium | refactor_start_evidence_contract |
| nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md | tests/ops/test_select_tests.py, tests/ops/test_ci_gate_report_trust_audit.py::test_run_changed_only_check_uses_selector_targets | active | medium | lesson_writeback_contract |
| nexus_wiki_vault/06_Ops/Ops - Governance Changelog.md | tests/ops/test_select_tests.py, tests/ops/test_ci_gate_report_trust_audit.py::test_run_changed_only_check_uses_selector_targets | active | medium | governance_changelog_contract |
| scripts/brain_de_entropy.py | tests/core/test_context_hub_strict_deps.py, tests/core/test_context_budget_sources.py, tests/core/test_context_text_store.py | active | high | context_hub_behavioral_contract |
| scripts/core/migration_validator.py | tests/core/test_migration_validator_contract.py | active | high | migration_validator_contract |
| scripts/core/drclaw_diagnosis.py | tests/benchmark/test_drclaw_diagnosis_contract.py | active | high | drclaw_diagnosis_contract |
| muse_nexus.egg-info/SOURCES.txt | tests/ops/test_source_inventory_integrity.py | active | high | source_inventory_integrity_contract |
| scripts/legacy/git_manager.py | tests/services/test_git_service.py | active | high | issue52_archived_adapter_cleanup_contract |
| scripts/legacy/linter.py | tests/services/test_linter.py | active | high | issue52_archived_adapter_cleanup_contract |
| scripts/legacy/llm_client.py | tests/test_battlesuit_gateway.py, tests/test_llm_token_regex.py | active | high | issue52_archived_adapter_cleanup_contract |
| scripts/legacy/patcher.py | tests/services/test_patcher.py | active | high | issue52_archived_adapter_cleanup_contract |
| scripts/legacy/reporter.py | tests/test_reporter.py | active | high | issue52_archived_adapter_cleanup_contract |
| scripts/legacy/workspace_manager.py | tests/services/test_workspace_manager.py, tests/benchmark/test_workspace.py | active | high | issue52_archived_adapter_cleanup_contract |
| scripts/brain_b_indexer.py | tests/ops/test_source_inventory_integrity.py | active | high | issue55_abandoned_experiment_cleanup_contract |
| scripts/core/brain_b_indexer.py | tests/ops/test_source_inventory_integrity.py | active | high | issue55_abandoned_experiment_cleanup_contract |
| scripts/brain_b_reality_check.py | tests/ops/test_source_inventory_integrity.py | active | high | issue55_abandoned_experiment_cleanup_contract |
| scripts/core/brain_b_reality_check.py | tests/ops/test_source_inventory_integrity.py | active | high | issue55_abandoned_experiment_cleanup_contract |
| scripts/reality_check_v2.py | tests/ops/test_source_inventory_integrity.py | active | high | issue55_abandoned_experiment_cleanup_contract |
| scripts/core/reality_check_v2.py | tests/ops/test_source_inventory_integrity.py | active | high | issue55_abandoned_experiment_cleanup_contract |
| scripts/trigger_test.py | tests/ops/test_source_inventory_integrity.py | active | high | issue55_abandoned_experiment_cleanup_contract |
| scripts/core/trigger_test.py | tests/ops/test_source_inventory_integrity.py | active | high | issue55_abandoned_experiment_cleanup_contract |
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
| tests/services/test_findings_embedding.py | tests/services/test_findings_embedding.py | active | medium | test_contract |
| tests/services/test_memory_repository_schema.py | tests/services/test_memory_repository_schema.py | active | medium | test_contract |
| tests/services/test_lancedb_roots.py | tests/services/test_lancedb_roots.py | active | medium | test_contract |
| tests/services/test_lancedb_roots_guard.py | tests/services/test_lancedb_roots_guard.py | active | medium | test_contract |
| nexus_swarm | tests/ops/test_swarm_deploy_path.py | active | medium | swarm_deploy_path_contract |
| nexus-swarm-v22-prod | tests/ops/test_swarm_deploy_path.py | active | medium | swarm_archived_fork_contract |
| tests/ops/test_swarm_deploy_path.py | tests/ops/test_swarm_deploy_path.py | active | medium | test_contract |
| scripts/test_local_swarm.sh | tests/ops/test_swarm_deploy_path.py | active | medium | swarm_deploy_path_contract |
| nexus-belief-artifact-v0.2-spec.md | tests/core/test_belief_v02.py | active | medium | belief_v02_spec_contract |
| tests/core/test_constraints_source_propagation.py | tests/core/test_constraints_source_propagation.py | active | medium | test_contract |
| tests/core/test_selector_constraints_source_trace.py | tests/core/test_selector_constraints_source_trace.py | active | medium | test_contract |
| tests/services/test_forecast_gate_mainchain_e2e.py | tests/services/test_forecast_gate_mainchain_e2e.py | active | medium | test_contract |
| tests/core/test_mempalace_belief_writer_path.py | tests/core/test_mempalace_belief_writer_path.py | active | medium | test_contract |
| tests/ops/test_nexus_status_honesty.py | tests/ops/test_nexus_status_honesty.py | active | medium | test_contract |
| scripts/ops/closeout_guard.py | tests/ops/test_closeout_guard.py, tests/ops/test_contract_snapshot_attestation.py | active | high | governance |
| tests/ops/test_contract_snapshot_attestation.py | tests/ops/test_contract_snapshot_attestation.py | active | medium | test_contract |
| tests/services/test_distill_swarm_honesty.py | tests/services/test_distill_swarm_honesty.py | active | medium | test_contract |
| tests/engine/test_metrics_and_belief_score.py | tests/engine/test_metrics_and_belief_score.py | active | medium | test_contract |
| nexus/orchestrator/metrics.py | tests/engine/test_metrics_and_belief_score.py, tests/engine/test_multi_agent_actions.py | active | medium | multi_agent_metrics_contract |
| scripts/ops/evidence_verifier.py | tests/ops/test_evidence_verifier_replay_required.py, tests/ops/test_stage_b_replay.py, tests/governance/test_replay_runner_allowlist.py | active | high | replay_runner_allowlist |
| nexus/delivery/evidence_verifier.py | tests/ops/test_evidence_verifier_replay_required.py, tests/test_iron_gate_governance.py | active | high | replay_runner_allowlist |
| tests/ops/test_evidence_verifier_replay_required.py | tests/ops/test_evidence_verifier_replay_required.py | active | medium | test_contract |
| compliance/sla/metrics/stability_poc_v22.json | tests/ops/test_nexus_status_honesty.py | active | medium | compliance_artifact |
| nexus_wiki_vault/07_Compliance/Current_Compliance_Status.md | tests/ops/test_nexus_status_honesty.py | active | medium | compliance_artifact |
| nexus_wiki_vault/99_Schema/generated/ | tests/ops/test_build_wiki_agent_index.py, tests/ops/test_wiki_committed_reproducibility.py, tests/ops/test_classify_wiki_unresolved_links.py | active | medium | wiki_generated_artifacts |
| tests/ops/test_stage_f_flow.py | tests/ops/test_stage_f_flow.py | active | medium | test_contract |
| AGENTS.md | tests/ops/test_bootstrap_authority_files.py, tests/ops/test_bootstrap_context_budget.py, tests/ops/test_codex_task_context_index.py, tests/ops/test_fast_start_consumer_contract.py | active | medium | authority_text_context_budget_contract |
| MUSE_PROTO.md | tests/ops/test_bootstrap_authority_files.py, tests/ops/test_bootstrap_context_budget.py, tests/ops/test_codex_task_context_index.py, tests/ops/test_fast_start_consumer_contract.py | active | medium | authority_text_context_budget_contract |
| CLAUDE.md | tests/ops/test_bootstrap_authority_files.py, tests/ops/test_bootstrap_context_budget.py, tests/ops/test_codex_task_context_index.py, tests/ops/test_fast_start_consumer_contract.py | active | medium | authority_text_context_budget_contract |
| GEMINI.md | tests/ops/test_bootstrap_authority_files.py, tests/ops/test_bootstrap_context_budget.py, tests/ops/test_codex_task_context_index.py, tests/ops/test_fast_start_consumer_contract.py | active | medium | authority_text_context_budget_contract |
| SOUL.md | tests/ops/test_bootstrap_authority_files.py, tests/ops/test_bootstrap_context_budget.py, tests/ops/test_codex_task_context_index.py, tests/ops/test_fast_start_consumer_contract.py | active | medium | authority_text_context_budget_contract |
| docs/agents | tests/ops/test_bootstrap_authority_files.py, tests/ops/test_bootstrap_context_budget.py, tests/ops/test_codex_task_context_index.py, tests/ops/test_fast_start_consumer_contract.py | active | medium | authority_text_context_budget_contract |
| scripts/ops/deletion_guard.py | tests/ops/test_deletion_guard.py | active | high | deletion_guard_owner_approval_contract |
| scripts/ops/review_record_check.py | tests/ops/test_review_record_check.py | active | high | review_record_advisory_check_contract |
| .github/workflows/review-record-present.yml | tests/ops/test_review_record_check.py, tests/ops/test_pr_workflow_concurrency.py | active | high | review_record_workflow_contract |
| tests/nightly_quarantine_items | tests/ops/test_nightly_quarantine.py, tests/ops/test_nightly_quarantine_items_layout.py | active | medium | nightly_quarantine_items_per_entry_package |
| tests/ops/test_nightly_quarantine_items_layout.py | tests/ops/test_nightly_quarantine_items_layout.py | active | medium | test_contract |
| tests/nightly_quarantine_entries.py | tests/ops/test_nightly_quarantine.py, tests/ops/test_nightly_quarantine_items_layout.py | active | medium | nightly_quarantine_entries_compat_shim |
| nexus/core/policy_drift.py | tests/test_governance_telemetry_closure.py, tests/test_semantic_receipt_gate.py | active | medium | dual_gate_replay_artifact_location_contract |
| scripts/effects | tests/effects, tests/unit/local_heal/test_p4_committee_real_winner_path.py | active | low | effects_shadow_scripts_scope_feature_flags |
| scripts/ops/nexus_gateway_auto_deploy.py | tests/ops/test_nexus_gateway_auto_deploy.py, tests/ops/test_check_gateway_source_drift.py | active | high | gateway_auto_deploy_health_gated_switch_contract |
| scripts/ops/install_nexus_gateway_auto_deploy.sh | tests/ops/test_nexus_gateway_auto_deploy.py | active | medium | gateway_auto_deploy_launchagent_installer |
| scripts/ops/check_gateway_source_drift.py | tests/ops/test_check_gateway_source_drift.py, tests/ops/test_nexus_gateway_auto_deploy.py | active | medium | gateway_source_drift_reads_auto_deploy_receipt |
| tests/ops/test_nexus_gateway_auto_deploy.py | tests/ops/test_nexus_gateway_auto_deploy.py | active | medium | test_contract |
| tests/nexus/orchestrator/test_gateway_controller_root.py | tests/nexus/orchestrator/test_gateway_controller_root.py | active | medium | test_contract |
| tests/ops/test_gateway_routine_deploy_authority.py | tests/ops/test_gateway_routine_deploy_authority.py | active | medium | test_contract |
| scripts/ops/eia_scoreboard.py | tests/ops/test_eia_scoreboard.py | active | medium | eia_scoreboard_report |
| nexus/contracts/self_hosted_state_root.py | tests/nexus/orchestrator/test_self_hosted_task_service.py, tests/research/test_trajectory_continuity.py | active | high | self_hosted_state_root_legacy_guard_contract |
