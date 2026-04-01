# v23 X-Ray Full Analysis Report

## Summary
v23 X-Ray Full Scan complete. Symbols: 18151 | Crossings: 10119

## Symbols (18151)
- swarm.py::NexusSwarmOrchestrator
- swarm.py::FederatedSwarmOrchestrator
- swarm.py::PeerSwarmOrchestrator
- swarm.py::SwarmFactory
- swarm.py::fork_subagent
- swarm.py::_only_json_outcome
- swarm.py::__init__
- swarm.py::run
- swarm.py::_analyze
- swarm.py::_plan
- swarm.py::_repair
- swarm.py::_verify
- swarm.py::__init__
- swarm.py::_select_executor
- swarm.py::_dispatch_remote
- swarm.py::_dispatch_remote
- swarm.py::_repair
- swarm.py::_verify
- swarm.py::__init__
- swarm.py::broadcast_decision
- swarm.py::listen_for_peers
- swarm.py::check_manifest_lock
- swarm.py::_repair
- swarm.py::create_swarm
- memory_coordinator.py::LockTimeoutError
- memory_coordinator.py::LockCycleError
- memory_coordinator.py::MemoryCoordinator
- memory_coordinator.py::__init__
- memory_coordinator.py::lock
- memory_coordinator.py::_lock_path
- memory_coordinator.py::_register_lock_order
- memory_coordinator.py::_release_lock_order
- memory_coordinator.py::_record_wait
- memory_coordinator.py::wait_p95_ms
- skill_outcomes.py::_safe_float
- skill_outcomes.py::OutcomePayload
- skill_outcomes.py::build_outcome_event
- skill_outcomes.py::append_skill_outcome_event
- handoff_bundle.py::HandoffRequest
- handoff_bundle.py::HandoffRetentionPolicy
- handoff_bundle.py::HandoffBundle
- handoff_bundle.py::HandoffBundleWriter
- handoff_bundle.py::__init__
- handoff_bundle.py::create
- handoff_bundle.py::_apply_retention
- handoff_bundle.py::_capture_workspace_diff
- pipeline_metadata.py::PipelineMetadata
- access_control_list.py::AccessControlList
- access_control_list.py::__init__
- access_control_list.py::check_system_integrity
- ... and 18101 more

## Crossings (10119)
- swarm.py -> os
- swarm.py -> logging
- swarm.py -> json
- swarm.py -> socket
- swarm.py -> typing
- swarm.py -> pathlib
- swarm.py -> nexus.services.reviewer
- swarm.py -> nexus.security.tls_provider
- swarm.py -> nexus.security.secure_sync
- swarm.py -> subprocess
- swarm.py -> nexus.learning.skill_registry
- swarm.py -> nexus.federation.node_registry
- memory_coordinator.py -> __future__
- memory_coordinator.py -> fcntl
- memory_coordinator.py -> os
- memory_coordinator.py -> threading
- memory_coordinator.py -> time
- memory_coordinator.py -> contextlib
- memory_coordinator.py -> pathlib
- memory_coordinator.py -> typing
- memory_coordinator.py -> logging
- skill_outcomes.py -> __future__
- skill_outcomes.py -> json
- skill_outcomes.py -> datetime
- skill_outcomes.py -> pathlib
- skill_outcomes.py -> typing
- skill_outcomes.py -> dataclasses
- handoff_bundle.py -> json
- handoff_bundle.py -> logging
- handoff_bundle.py -> subprocess
- handoff_bundle.py -> dataclasses
- handoff_bundle.py -> datetime
- handoff_bundle.py -> pathlib
- handoff_bundle.py -> typing
- handoff_bundle.py -> gzip
- handoff_bundle.py -> shutil
- pipeline_metadata.py -> typing
- access_control_list.py -> logging
- access_control_list.py -> typing
- access_control_list.py -> re
- k8s_swarm_adapter.py -> logging
- k8s_swarm_adapter.py -> asyncio
- k8s_swarm_adapter.py -> typing
- crystal.py -> os
- crystal.py -> json
- crystal.py -> logging
- crystal.py -> pathlib
- crystal.py -> datetime
- crystal.py -> collections
- policy_metabolizer.py -> __future__
- ... and 10069 more

## Risks Detected (122)
⚠️ session_persistence.py: Potential subprocess execution detected.
⚠️ truth_validator.py: Potential subprocess execution detected.
⚠️ truth_validator.py: Potential subprocess execution detected.
⚠️ truth_validator.py: Potential subprocess execution detected.
⚠️ notifier.py: Potential subprocess execution detected.
⚠️ preflight_check.py: Potential subprocess execution detected.
⚠️ preflight_check.py: Potential subprocess execution detected.
⚠️ workspace_manager.py: Potential subprocess execution detected.
⚠️ workspace_manager.py: Potential subprocess execution detected.
⚠️ workspace_manager.py: Potential subprocess execution detected.
⚠️ commander.py: Potential subprocess execution detected.
⚠️ jinja/venv/lib/python3.14/site-packages/pip/_internal/network/auth.py: Potential subprocess execution detected.
⚠️ jinja/venv/lib/python3.14/site-packages/pip/_internal/network/auth.py: Potential subprocess execution detected.
⚠️ jinja/venv/lib/python3.14/site-packages/pip/_internal/utils/subprocess.py: Potential subprocess execution detected.
⚠️ jinja/venv/lib/python3.14/site-packages/pip/_internal/cli/main_parser.py: Potential subprocess execution detected.
⚠️ jinja/venv/lib/python3.14/site-packages/pip/_vendor/packaging/tags.py: Potential subprocess execution detected.
⚠️ jinja/venv/lib/python3.14/site-packages/pip/_vendor/packaging/_musllinux.py: Potential subprocess execution detected.
⚠️ jinja/venv/lib/python3.14/site-packages/pip/_vendor/distlib/util.py: Potential subprocess execution detected.
⚠️ click/tests/test_imports.py: Potential subprocess execution detected.
⚠️ click/src/click/shell_completion.py: Potential subprocess execution detected.
⚠️ click/src/click/_termui_impl.py: Potential subprocess execution detected.
⚠️ click/src/click/_termui_impl.py: Potential subprocess execution detected.
⚠️ click/src/click/_termui_impl.py: Potential subprocess execution detected.
⚠️ click/src/click/_termui_impl.py: Potential subprocess execution detected.
⚠️ click/src/click/_termui_impl.py: Potential subprocess execution detected.
⚠️ click/src/click/_termui_impl.py: Potential subprocess execution detected.
⚠️ click/src/click/_termui_impl.py: Potential subprocess execution detected.
⚠️ japan-ski-radar/scripts/radar.py: Potential subprocess execution detected.
⚠️ git-manager/scripts/parallel_fix.py: Potential subprocess execution detected.
⚠️ git-manager/scripts/parallel_fix.py: Potential subprocess execution detected.
⚠️ git-manager/scripts/parallel_fix.py: Potential subprocess execution detected.
⚠️ inspiration-curator/scripts/curate.py: Potential subprocess execution detected.
⚠️ idea-generator/scripts/daily_innovation.py: Potential subprocess execution detected.
⚠️ ski-diagnostician/scripts/search_ski.py: Scan failed: unterminated f-string literal (detected at line 20) (<unknown>, line 20)
⚠️ healthcheck/scripts/monitor_gateway.py: Potential subprocess execution detected.
⚠️ healthcheck/scripts/monitor_gateway.py: Potential subprocess execution detected.
⚠️ healthcheck/scripts/monitor_gateway.py: Potential subprocess execution detected.
⚠️ .bak/skill-reviewer/scripts/skill_reviewer.py: Potential subprocess execution detected.
⚠️ .bak/self-healer/scripts/self_healer.py: Potential subprocess execution detected.
⚠️ .bak/self-healer/scripts/self_healer.py: Potential subprocess execution detected.
⚠️ notebooklm-skill/scripts/run.py: Potential subprocess execution detected.
⚠️ notebooklm-skill/scripts/run.py: Potential subprocess execution detected.
⚠️ notebooklm-skill/scripts/setup_environment.py: Potential subprocess execution detected.
⚠️ notebooklm-skill/scripts/setup_environment.py: Potential subprocess execution detected.
⚠️ notebooklm-skill/scripts/setup_environment.py: Potential subprocess execution detected.
⚠️ notebooklm-skill/scripts/setup_environment.py: Potential subprocess execution detected.
⚠️ notebooklm-skill/scripts/__init__.py: Potential subprocess execution detected.
⚠️ notebooklm-skill/scripts/__init__.py: Potential subprocess execution detected.
⚠️ notebooklm-skill/venv/lib/python3.14/site-packages/patchright/__main__.py: Potential subprocess execution detected.
⚠️ notebooklm-skill/venv/lib/python3.14/site-packages/pip/_internal/network/auth.py: Potential subprocess execution detected.
⚠️ notebooklm-skill/venv/lib/python3.14/site-packages/pip/_internal/network/auth.py: Potential subprocess execution detected.
⚠️ notebooklm-skill/venv/lib/python3.14/site-packages/pip/_internal/utils/subprocess.py: Potential subprocess execution detected.
⚠️ notebooklm-skill/venv/lib/python3.14/site-packages/pip/_internal/cli/main_parser.py: Potential subprocess execution detected.
⚠️ notebooklm-skill/venv/lib/python3.14/site-packages/pip/_vendor/packaging/tags.py: Potential subprocess execution detected.
⚠️ notebooklm-skill/venv/lib/python3.14/site-packages/pip/_vendor/packaging/_musllinux.py: Potential subprocess execution detected.
⚠️ notebooklm-skill/venv/lib/python3.14/site-packages/pip/_vendor/distlib/util.py: Potential subprocess execution detected.
⚠️ notebooklm-skill/venv/lib/python3.14/site-packages/greenlet/tests/test_interpreter_shutdown.py: Potential subprocess execution detected.
⚠️ link-smelter/scripts/smelt.py: Potential subprocess execution detected.
⚠️ Archives/content-agent/scripts/content_agent.py: Potential subprocess execution detected.
⚠️ Archives/skill-creator/eval-viewer/generate_review.py: Potential subprocess execution detected.
⚠️ Archives/skill-creator/scripts/run_eval.py: Potential subprocess execution detected.
⚠️ Archives/skill-creator/scripts/improve_description.py: Potential subprocess execution detected.
⚠️ apple-reminders/scripts/get_reminders.py: Potential subprocess execution detected.
⚠️ scheduler-manager/scripts/scheduler_manager.py: Potential subprocess execution detected.
⚠️ scheduler-manager/scripts/scheduler_manager.py: Potential subprocess execution detected.
⚠️ skill-creator-advanced/scripts/run_eval.py: Potential subprocess execution detected.
⚠️ skill-creator-advanced/scripts/improve_description.py: Potential subprocess execution detected.
⚠️ .system/skill-installer/scripts/install-skill-from-github.py: Potential subprocess execution detected.
⚠️ video-tool/scripts/vid2img.py: Potential subprocess execution detected.
⚠️ apple-notes/scripts/get_notes.py: Potential subprocess execution detected.
⚠️ apple-notes/scripts/ingest_notes.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/cli.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/channels/douyin.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/channels/douyin.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/channels/exa_search.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/channels/weibo.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/channels/weibo.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/channels/twitter.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/channels/twitter.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/channels/twitter.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/channels/linkedin.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/channels/xiaohongshu.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/channels/xiaohongshu.py: Potential subprocess execution detected.
⚠️ agent-reach/agent_reach/channels/github.py: Potential subprocess execution detected.
⚠️ food-scout/scripts/dynamic_locator.py: Potential subprocess execution detected.
⚠️ food-scout/scripts/env_sensor.py: Potential subprocess execution detected.
⚠️ food-scout/scripts/infra_manager.py: Potential subprocess execution detected.
⚠️ food-scout/scripts/infra_manager.py: Potential subprocess execution detected.
⚠️ food-scout/scripts/loc_provider.py: Potential subprocess execution detected.
⚠️ food-scout/scripts/loc_provider.py: Potential subprocess execution detected.
⚠️ food-scout/scripts/loc_provider.py: Potential subprocess execution detected.
⚠️ reflection/scripts/reflection.py: Potential subprocess execution detected.
