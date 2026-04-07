# v23 X-Ray Full Analysis Report

## Summary
v23 X-Ray Cross-Repo Scan complete. Symbols: 9532 | Crossings: 5049

## Symbols (9532)
- core::metrics_aggregator.py::MetricsAggregator
- core::metrics_aggregator.py::__init__
- core::metrics_aggregator.py::aggregate_crystallize_payload
- core::shogun.py::ShogunOrchestrator
- core::shogun.py::__init__
- core::shogun.py::shogun_route
- core::shogun.py::_daimyo_decompose
- core::shogun.py::_samurai_execute
- core::swarm.py::NexusSwarmOrchestrator
- core::swarm.py::FederatedSwarmOrchestrator
- core::swarm.py::PeerSwarmOrchestrator
- core::swarm.py::SwarmFactory
- core::swarm.py::fork_subagent
- core::swarm.py::_only_json_outcome
- core::swarm.py::__init__
- core::swarm.py::run
- core::swarm.py::_analyze
- core::swarm.py::_plan
- core::swarm.py::_repair
- core::swarm.py::_verify
- core::swarm.py::__init__
- core::swarm.py::_select_executor
- core::swarm.py::_dispatch_remote
- core::swarm.py::_dispatch_remote
- core::swarm.py::_repair
- core::swarm.py::_verify
- core::swarm.py::__init__
- core::swarm.py::broadcast_decision
- core::swarm.py::listen_for_peers
- core::swarm.py::check_manifest_lock
- core::swarm.py::_repair
- core::swarm.py::create_swarm
- core::memory_coordinator.py::LockTimeoutError
- core::memory_coordinator.py::LockCycleError
- core::memory_coordinator.py::MemoryCoordinator
- core::memory_coordinator.py::__init__
- core::memory_coordinator.py::lock
- core::memory_coordinator.py::_lock_path
- core::memory_coordinator.py::_register_lock_order
- core::memory_coordinator.py::_release_lock_order
- core::memory_coordinator.py::_record_wait
- core::memory_coordinator.py::wait_p95_ms
- core::policy_loader.py::PolicyLoader
- core::policy_loader.py::load
- core::skill_outcomes.py::_safe_float
- core::skill_outcomes.py::OutcomePayload
- core::skill_outcomes.py::build_outcome_event
- core::skill_outcomes.py::append_skill_outcome_event
- core::handoff_bundle.py::HandoffRequest
- core::handoff_bundle.py::HandoffRetentionPolicy
- ... and 9482 more

## Crossings (5049)
- core::metrics_aggregator.py -> typing
- core::metrics_aggregator.py -> time
- core::shogun.py -> typing
- core::shogun.py -> logging
- core::shogun.py -> queue
- core::swarm.py -> pathlib
- core::swarm.py -> typing
- core::swarm.py -> os
- core::swarm.py -> logging
- core::swarm.py -> json
- core::swarm.py -> socket
- core::swarm.py -> nexus.services.reviewer
- core::swarm.py -> nexus.security.tls_provider
- core::swarm.py -> nexus.security.secure_sync
- core::swarm.py -> subprocess
- core::swarm.py -> nexus.learning.skill_registry
- core::swarm.py -> nexus.federation.node_registry
- core::memory_coordinator.py -> __future__
- core::memory_coordinator.py -> pathlib
- core::memory_coordinator.py -> typing
- core::memory_coordinator.py -> fcntl
- core::memory_coordinator.py -> os
- core::memory_coordinator.py -> threading
- core::memory_coordinator.py -> time
- core::memory_coordinator.py -> contextlib
- core::memory_coordinator.py -> logging
- core::policy_loader.py -> pathlib
- core::policy_loader.py -> os
- core::policy_loader.py -> logging
- core::policy_loader.py -> nexus.core.gate_evaluator
- core::policy_loader.py -> yaml
- core::skill_outcomes.py -> __future__
- core::skill_outcomes.py -> pathlib
- core::skill_outcomes.py -> typing
- core::skill_outcomes.py -> json
- core::skill_outcomes.py -> datetime
- core::skill_outcomes.py -> dataclasses
- core::handoff_bundle.py -> pathlib
- core::handoff_bundle.py -> typing
- core::handoff_bundle.py -> json
- core::handoff_bundle.py -> logging
- core::handoff_bundle.py -> subprocess
- core::handoff_bundle.py -> dataclasses
- core::handoff_bundle.py -> datetime
- core::handoff_bundle.py -> gzip
- core::handoff_bundle.py -> shutil
- core::pipeline_metadata.py -> typing
- core::access_control_list.py -> typing
- core::access_control_list.py -> logging
- core::access_control_list.py -> re
- ... and 4999 more

## Risks Detected (27)
⚠️ core::session_persistence.py: Potential subprocess execution detected.
⚠️ core::truth_validator.py: Potential subprocess execution detected.
⚠️ core::truth_validator.py: Potential subprocess execution detected.
⚠️ core::truth_validator.py: Potential subprocess execution detected.
⚠️ core::notifier.py: Potential subprocess execution detected.
⚠️ core::preflight_check.py: Potential subprocess execution detected.
⚠️ core::preflight_check.py: Potential subprocess execution detected.
⚠️ core::workspace_manager.py: Potential subprocess execution detected.
⚠️ core::workspace_manager.py: Potential subprocess execution detected.
⚠️ core::workspace_manager.py: Potential subprocess execution detected.
⚠️ core::commander.py: Potential subprocess execution detected.
⚠️ benchmarks::jinja/venv/lib/python3.14/site-packages/pip/_internal/network/auth.py: Potential subprocess execution detected.
⚠️ benchmarks::jinja/venv/lib/python3.14/site-packages/pip/_internal/network/auth.py: Potential subprocess execution detected.
⚠️ benchmarks::jinja/venv/lib/python3.14/site-packages/pip/_internal/utils/subprocess.py: Potential subprocess execution detected.
⚠️ benchmarks::jinja/venv/lib/python3.14/site-packages/pip/_internal/cli/main_parser.py: Potential subprocess execution detected.
⚠️ benchmarks::jinja/venv/lib/python3.14/site-packages/pip/_vendor/packaging/tags.py: Potential subprocess execution detected.
⚠️ benchmarks::jinja/venv/lib/python3.14/site-packages/pip/_vendor/packaging/_musllinux.py: Potential subprocess execution detected.
⚠️ benchmarks::jinja/venv/lib/python3.14/site-packages/pip/_vendor/distlib/util.py: Potential subprocess execution detected.
⚠️ benchmarks::click/tests/test_imports.py: Potential subprocess execution detected.
⚠️ benchmarks::click/src/click/shell_completion.py: Potential subprocess execution detected.
⚠️ benchmarks::click/src/click/_termui_impl.py: Potential subprocess execution detected.
⚠️ benchmarks::click/src/click/_termui_impl.py: Potential subprocess execution detected.
⚠️ benchmarks::click/src/click/_termui_impl.py: Potential subprocess execution detected.
⚠️ benchmarks::click/src/click/_termui_impl.py: Potential subprocess execution detected.
⚠️ benchmarks::click/src/click/_termui_impl.py: Potential subprocess execution detected.
⚠️ benchmarks::click/src/click/_termui_impl.py: Potential subprocess execution detected.
⚠️ benchmarks::click/src/click/_termui_impl.py: Potential subprocess execution detected.
