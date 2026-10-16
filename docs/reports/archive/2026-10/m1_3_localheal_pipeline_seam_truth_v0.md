# M1.3 LocalHeal Pipeline Seam Truth Report

**Status**: `M1_3_LOCALHEAL_PIPELINE_SEAM_TRUTH_PASS`

## Executive Summary

The `localheal_pipeline` execution topology invokes the **bridge** (`LocalHealPipelineCapabilityExecutor`), NOT the full `HealPipeline` or `Orchestrator`. This is a confirmed seam: the bridge checks module availability and performs lightweight operations (instantiation, protocol parse), but does NOT execute the full repair loop, verification loop, or semantic retry.

## Key Findings

### Was HealPipeline actually invoked?
**NO.** The bridge instantiates `HealPipeline(ollama_generate_fn=_noop_generate)` (line 328 of `local_model_capability_executors.py`) but never calls `.run()`. The `HealPipeline.run()` method (which contains the full phase orchestration) is never executed.

### Was Orchestrator actually invoked?
**NO.** The bridge checks `CommitteeOrchestrator` import availability but never instantiates or calls `HealOrchestrator.run()`. The orchestrator's repair loop, verification loop, and semantic retry are all bypassed.

### Does telemetry say availability-only?
**PARTIALLY.** When modules are importable:
- `localheal_pipeline_invoked = True` (bridge was called)
- `localheal_pipeline_actual_execution = True` (bridge did real work: instantiated modules, parsed protocol)
- `localheal_pipeline_availability_only = False` (modules are importable)

This means the bridge performs "real work" at the module level (instantiation, protocol parse), but this is NOT equivalent to full pipeline execution.

### Is solved outcome blocked when actual execution is false?
**YES.** When provider returns empty output, `candidate_hash` is empty hash and no solved state is produced. The bridge's `actual_execution` flag alone does not produce solved outcomes — actual patch application through the provider is required.

## Test Results

| Test | Status |
|------|--------|
| `test_localheal_pipeline_topology_reports_bridge_invocation` | PASS |
| `test_localheal_pipeline_topology_does_not_call_heal_pipeline_run` | PASS |
| `test_localheal_pipeline_topology_does_not_call_orchestrator_run` | PASS |
| `test_localheal_pipeline_topology_exposes_actual_execution_flag` | PASS |
| `test_localheal_pipeline_topology_does_not_mark_solved_from_availability_only` | PASS |
| `test_single_local_model_topology_does_not_use_bridge` | PASS |
| `test_model_call_goes_through_provider_not_pipeline` | PASS |

**Total: 7 passed, 0 failed**

## Execution Path Analysis

### What happens in `localheal_pipeline` topology:

1. `LocalModelExecutor.run()` resolves topology via `_resolve_execution_topology()`
2. Builds provider via `build_local_model_provider_from_signal_snapshot()`
3. Builds `LocalModelCapabilityContext`
4. Enters `localheal_pipeline` branch (line 427 of `local_model_executor.py`)
5. Calls `LocalHealPipelineCapabilityExecutor().execute(cap_ctx)` — **the bridge**
6. Bridge imports and checks: HealPipeline, CommitteeOrchestrator, SolidSearchReplaceProtocol, GranularMethodLocalizer, FailureFeedbackBuilder, EvaluationGate
7. Bridge instantiates `HealPipeline(ollama_generate_fn=_noop_generate)` — **but does NOT call .run()**
8. Bridge calls `SolidSearchReplaceProtocol().parse()` — lightweight protocol check
9. Model call goes through `provider.generate()` directly — **NOT through pipeline**
10. Returns `LocalModelExecutorResponse` with bridge telemetry

### What does NOT happen:
- ❌ `HealPipeline.run()` — no phase orchestration
- ❌ `HealOrchestrator.run()` — no repair loop, no verification loop
- ❌ Semantic retry — not available in bridge path
- ❌ Failure feedback loop — not wired through bridge
- ❌ Evaluation gate execution — only availability check

## Next Seam Recommendation

M1 must route through full `HealPipeline` or explicitly add retry/repair capabilities to the bridge path. The current bridge is an availability checker, not an execution path. To achieve actual solve capability:
1. Either wire `LocalModelExecutor.run()` → `HealPipeline.run()` (full pipeline)
2. Or add retry loop, verification, and semantic retry to the bridge path

## Files

- `tests/unit/local_heal/test_localheal_pipeline_seam_truth.py` — seam truth tests
- `docs/reports/m1_3_localheal_pipeline_seam_truth_v0.md` — this report
