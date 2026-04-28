# 測試影響映射 (Impact Map)
| 程式碼路徑 | 測試集合 (Directories/Files) | 狀態 | 風險 | 風險原因 |
| :--- | :--- | :--- | :--- | :--- |
| nexus/core | tests/core, tests/test_core_*.py | active | high | core_contract |
| nexus/services | tests/services, tests/test_services_*.py | active | medium | service_contract |
| nexus/engine | tests/engine, tests/test_engine_*.py | active | high | governance |
| nexus/app | tests/app | active | medium | app_flow |
| nexus/research | tests/research | active | medium | research_loop |
| nexus/benchmark | tests/benchmark | active | medium | benchmark_contract |
| nexus/connectors | tests/connectors | active | medium | connector_contract |
| nexus/security | tests/security | active | high | security |
| nexus/pilot_cli | tests/pilot_cli | active | medium | cli_runtime |
| nexus/health | tests/health | active | medium | health_signal |
| nexus_dag_workflow.py | tests/test_async_dag_workflow.py | active | medium | workflow_contract |
| scripts/engine/nexus_cli.py | tests/test_cli_learn_mode.py, tests/test_cli_commands.py | active | high | governance |
| scripts/ops/ci_gate.py | tests/ops/test_ci_gate_report_trust_audit.py, tests/ops/test_ci_gate_closeout_contract.py, tests/ops/test_ci_gate_wiki_sync_block.py | active | high | governance |
| scripts/ops/ultra_gate.py | tests/ops/test_ultra_gate.py | active | high | governance |
| scripts/ops/__init__.py | tests/ops/test_anti_drift_gate.py, tests/ops/test_soul_artifact_vault.py | active | medium | compatibility |
| scripts/ops/select_tests.py | tests/ops/test_select_tests.py | active | high | jit_selector |
| scripts/ops/jit_promotion.py | tests/ops/test_jit_promotion.py | active | medium | jit_promotion |
| scripts/ops/build_test_impact_index.py | tests/ops/test_build_test_impact_index.py | active | medium | jit_index |
| scripts/ops/test_changed.sh | tests/ops/test_select_tests.py | active | medium | jit_entrypoint |
| scripts/ops | tests/ops | active | medium | ops_tooling |
| scripts/bench | tests/benchmark | active | medium | benchmark_contract |
| tests/ops/test_ci_gate_report_trust_audit.py | tests/ops/test_ci_gate_report_trust_audit.py | active | medium | test_contract |
| tests/ops/test_select_tests.py | tests/ops/test_select_tests.py | active | medium | test_contract |
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
