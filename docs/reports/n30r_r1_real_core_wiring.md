# N30R-R1 Closeout: Real Core Arm Production Wiring

**Status**: N30R_R1_REAL_CORE_WIRING_PASS

## baseline SHA
884c37f227e95e52bf2891f737f5532511635f62

## files changed
- scripts/bench/n30r_contracts.py (modified: new receipt fields + VALID_ARM_IDS)
- scripts/bench/n30r_real_core_bridge.py (created: production path bridge)
- scripts/bench/n30r_arm_adapters.py (unchanged)
- scripts/bench/n30r_runner.py (modified: new arm dispatch)
- tests/bench/test_n30r_real_core_bridge.py (created: 17 tests)
- tests/bench/test_n30r_runner_contract.py (modified: updated arm references)

## exact production call chain
```
N30R runner
→ run_real_core_bridge(task, arm, provider, ...)
  → invoke_capability_planner(task, source_code)
    → CapabilityPlanner.plan(task_desc=..., route=..., budget=...)
    → returns plan.signal_snapshot
  → validate_planner_snapshot(snapshot)
  → provider(model_name, system_prompt, prompt)
  → _run_verifier_in_dir(patched, verifier_command)
  → RealCoreBridgeResult with production path evidence
```

## planner class and method
- Class: `nexus.engine.capability_planner.CapabilityPlanner`
- Method: `plan(task_desc=..., task_type=..., route=..., ...)`

## executor class and method
- Configured via signal_snapshot: `selected_executor=local_model`
- Topology: `localheal_pipeline` (frozen)

## frozen topology
`localheal_pipeline`

## mock boundary
- Tests mock only: the provider function (bottom-seam Ollama call)
- Tests do NOT mock: CapabilityPlanner.plan(), signal_snapshot creation, validation

## route authority evidence
- signal_snapshot produced by CapabilityPlanner.plan()
- planner_version = capability_planner_v1
- selected_executor = local_model
- execution_topology = localheal_pipeline
- ssd_route_map, context_slimming_policy, harness_relevance_policy all present

## legacy adapter evidence
- legacy_adapter_called = false (all paths)
- execution_path_kind = nexus_production_localheal_pipeline (core arm)
- execution_path_kind = bare_direct_provider (bare arm)

## golden leakage check
- golden patch absent from planner request
- golden patch absent from prompt
- golden patch absent from receipt

## test names (17 new)
test_real_core_arm_calls_capability_planner
test_real_core_arm_uses_planner_owned_signal_snapshot
test_real_core_arm_calls_local_model_executor
test_real_core_arm_uses_localheal_pipeline
test_real_core_arm_does_not_call_legacy_capability_adapter
test_real_core_arm_disables_committee
test_real_core_arm_disables_local_cascade
test_real_core_arm_disables_cloud_fallback
test_real_core_arm_disables_cross_task_memory
test_real_core_arm_uses_same_7b_model_as_bare
test_real_core_arm_records_production_receipt_hash
test_real_core_arm_fails_closed_without_planner_version
test_real_core_arm_fails_closed_without_route_truth_source
test_real_core_arm_fails_closed_without_signal_snapshot_hash
test_prompt_variant_arm_is_not_labeled_real_core
test_bare_arm_does_not_call_capability_planner
test_golden_patch_is_absent_from_real_core_request

## test result
48 passed (13 contracts + 18 runner + 17 real core bridge)

## live model calls = 0
## production_ready=false
## public_claim_allowed=false
