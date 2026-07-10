# N30R-R1B Closeout: Genuine Production Executor Wiring

**Status**: N30R_R1B_GENUINE_EXECUTOR_PASS

## worktree path
/Users/jameschen/Workspace/nexus-n30r-real-core

## baseline SHA
c83c5cf56c2e9dcba2195536b954b36facd9f015

## branch
fix/n30r-genuine-production-executor

## files changed
- scripts/bench/n30r_real_core_bridge.py (rewritten)
- tests/bench/test_n30r_real_core_bridge.py (rewritten: 23 tests)

## exact import path
```python
from nexus.services.local_heal.local_model_executor import (
    LocalModelExecutor,
    LocalModelExecutorRequest,
    LocalModelExecutorResponse,
)
```

## exact executor method
`LocalModelExecutor.run(request, provider=injected_provider)`

## exact request type
`LocalModelExecutorRequest`

## exact response type
`LocalModelExecutorResponse`

## actual runtime call chain
```
run_real_core_bridge()
→ invoke_capability_planner(task, source_code)
  → CapabilityPlanner.plan()
  → returns signal_snapshot (immutable)
→ validate_planner_snapshot(snapshot)
→ assert snapshot == snapshot_copy (immutability proof)
→ build LocalModelExecutorRequest from snapshot
→ wrap provider as InjectedLocalModelProvider
→ LocalModelExecutor.run(request, provider=injected_provider)
  → _resolve_execution_topology(request)
  → Heals pipeline topology resolution
  → candidate generation via provider
  → candidate isolation
  → isolated apply
  → isolated verifier
→ LocalModelExecutorResponse
→ _build_production_receipt_hash(response)
→ RealCoreBridgeResult projection
```

## provider injection boundary
- Benchmark provides `ProviderFn` (model, system_prompt, user_prompt) → str
- Bridge wraps it as `InjectedLocalModelProvider(LocalModelProviderRequest → str)`
- Provider is ONLY passed to `LocalModelExecutor.run()`
- Bridge NEVER calls provider directly
- Source-level test confirms: `test_provider_is_only_reached_inside_local_model_executor`

## planner snapshot immutability evidence
- `snapshot_copy = copy.deepcopy(signal_snapshot)` before executor call
- `assert signal_snapshot == snapshot_copy` after executor call
- Source-level test confirms: `test_real_core_does_not_mutate_planner_signal_snapshot`

## LocalModelExecutor.run invocation count
1 (verified by `test_real_core_calls_local_model_executor_run_exactly_once`)

## localheal_pipeline_run_called evidence
From `response.raw_model_metadata["localheal_pipeline_run_called"]`
Fail-closed if missing or False: `test_real_core_requires_actual_localheal_pipeline_execution`

## localheal_pipeline_actual_execution evidence
From `response.raw_model_metadata["localheal_pipeline_actual_execution"]`
Fail-closed if missing or False: `test_real_core_rejects_executor_response_without_pipeline_execution`

## candidate isolation provenance
From `response.raw_model_metadata["candidate_isolated"]` and `["selected_candidate_hash"]`
Verified by: `test_candidate_isolation_fields_come_from_executor_metadata`

## verifier provenance
From `response.raw_model_metadata["isolated_verifier_status"]`
Verified by: `test_verifier_fields_come_from_executor_metadata`

## production receipt hash construction
```python
_build_production_receipt_hash(response):
  payload = {invoked, local_model_called, candidate_hash, provider,
             model_name, error, timeout, evidence_refs,
             cascade_stages_run, raw_model_metadata}
  canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
  sha256(canonical)
```
Verified by: `test_production_receipt_hash_is_hash_of_canonical_executor_response`

## source-level forbidden-pattern test result
- `test_real_core_bridge_has_no_direct_provider_call`: PASS
- `test_real_core_bridge_has_no_manual_verifier`: PASS
- `test_real_core_bridge_has_no_manual_apply_workspace`: PASS
- `test_real_core_bridge_does_not_mutate_planner_snapshot`: PASS
- `test_real_core_bridge_does_not_hardcode_executor_called`: PASS
- `test_real_core_bridge_does_not_hardcode_production_path_used`: PASS
- `test_real_core_bridge_does_not_hash_snapshot_as_production_receipt`: PASS

## focused test output
54 passed (13 contracts + 18 runner + 23 real core bridge)

## production executor test output
183 passed (test_local_model_executor.py + test_local_model_capability_executors.py)

## live Ollama calls = 0
## R2/R3/R4 not executed
## production_ready=false
## public_claim_allowed=false
