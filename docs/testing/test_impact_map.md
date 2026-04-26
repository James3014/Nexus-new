# 測試影響映射 (Impact Map)
| 程式碼路徑 | 測試集合 (Directories/Files) | 狀態 |
| :--- | :--- | :--- |
| nexus/core | tests/core, tests/test_core_*.py | active |
| nexus/services | tests/services, tests/test_services_*.py | active |
| nexus/engine | tests/engine, tests/test_engine_*.py | active |
| nexus/app | tests/app | active |
| nexus/research | tests/research | active |
| nexus/benchmark | tests/benchmark | active |
| nexus/connectors | tests/connectors | active |
| nexus/security | tests/security | active |
| nexus/pilot_cli | tests/pilot_cli | active |
| nexus/health | tests/health | active |
| nexus_dag_workflow.py | tests/test_async_dag_workflow.py | active |
| scripts/ops/ci_gate.py | tests/ops/test_ci_gate_report_trust_audit.py, tests/ops/test_ci_gate_closeout_contract.py, tests/ops/test_ci_gate_wiki_sync_block.py | active |
| scripts/ops/__init__.py | tests/ops/test_anti_drift_gate.py, tests/ops/test_soul_artifact_vault.py | active |
| scripts/ops/select_tests.py | tests/ops/test_select_tests.py | active |
| scripts/ops/build_test_impact_index.py | tests/ops/test_build_test_impact_index.py | active |
| scripts/ops/test_changed.sh | tests/ops/test_select_tests.py | active |
| scripts/ops | tests/ops | active |
| scripts/bench | tests/benchmark | active |
| tests/ops/test_ci_gate_report_trust_audit.py | tests/ops/test_ci_gate_report_trust_audit.py | active |
| tests/ops/test_select_tests.py | tests/ops/test_select_tests.py | active |
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
