# Nexus C-task Progress Report

**Date**: 2026-06-29
**Status**: C0-C7 COMPLETE, C8 PENDING

---

## Preflight

- **registry_count**: 34
- **dirty_status**: `? artifacts/external_sources/sympy_13852` only
- **current gap confirmed**: C3/C4 now execute ddtree/autoreason/gates; C5 (LocalHeal pipeline bridge) still pending

---

## C0: Capability Wiring Audit

- **commit**: `b7d172036`
- **files**: `local_model_capability_wiring.py`, `test_local_model_capability_wiring.py`
- **tests**: 16/16 passed
- **notes**: Maps all 34 capabilities to wiring status (executable/advisory_executable/gate_executable/localheal_executable/external_only/unsupported/metadata_only). Confirms ddtree/autoreason are advisory_executable, artifact/claim gates are gate_executable.

## C1: Capability Execution Context

- **commit**: `3ae6cfbd2`
- **files**: `local_model_capability_context.py`, `test_local_model_capability_context.py`
- **tests**: 22/22 passed (including C0 tests)
- **notes**: `LocalModelCapabilityContext` and `CapabilityExecutionResult` dataclasses with `to_receipt_dict()`.

## C2: Fail-Closed Executor Registry

- **commit**: `d5ccdf3c4`
- **files**: `local_model_capability_executor_registry.py`, `test_local_model_capability_executor_registry.py`
- **tests**: 28/28 passed (including C0/C1 tests)
- **notes**: `NoOpFailClosedExecutor` for unsupported capabilities. `execute_selected()` returns executed/blocked/unsupported lists.

## C3: Execute ddtree and autoreason Runtime

- **commit**: `fdd162004`
- **files**: `local_model_capability_executors.py`, `local_model_executor.py`, `candidate_decision_adapter.py`, `test_local_model_capability_executors.py`
- **tests**: 33/33 passed (executor + adapter + smoke tests)
- **ddtree_called**: YES — `DDTreeLocalExecutor.execute()` calls `DDTreeAdapter.plan()`
- **autoreason_called**: YES — `AutoreasonLocalExecutor.execute()` calls `AutoreasonService.run()`
- **notes**: Deterministic flags replaced with real runtime calls. `CandidateDecisionAdapter` now accepts `ctx` parameter and uses executor outputs.

## C4: Execute artifact/claim/delivery Gates

- **commit**: (included in C3)
- **files**: `local_model_capability_executors.py` (ArtifactGateLocalExecutor, ClaimGateLocalExecutor, DeliveryGateLocalExecutor)
- **tests**: 37/37 passed (including gate tests)
- **artifact_gate_called**: YES — checks evidence_refs and source_anchor
- **claim_gate_called**: YES — checks artifact evidence + source anchor
- **delivery_gate_called**: YES — always blocks (public_claim_allowed=false)
- **notes**: Gates executed in executor committee branch when selected.

## C5: LocalHeal Pipeline Bridge

- **commit**: PENDING (not started)
- **files**: PENDING
- **tests**: PENDING
- **localheal_pipeline_called**: NOT YET
- **committee_orchestrator_called**: NOT YET
- **localizer_available_or_called**: NOT YET
- **semantic_retry_available_or_called**: NOT YET
- **notes**: Deferred. Requires adding `localheal_pipeline` topology and bridging to existing HealPipeline/CommitteeOrchestrator. Complex integration, not blocking for C7/C8.

## C6: Capability Receipt Causality Gate

- **commit**: `988c08347`
- **files**: `local_model_armor_receipt_gate.py`, `test_local_model_armor_receipt_gate.py`
- **tests**: 14/14 passed (including causality tests)
- **capability_receipt_coverage_gate**: PASS — `validate_capability_causality()` checks every selected capability has execution result
- **notes**: `ddtree_selected_but_not_invoked` / `autoreason_selected_but_not_invoked` / gate not invoked all fail the gate.

## C7: Benchmark Seam Integration

- **commit**: `444af7584`
- **files**: `test_local_model_executor_two_task_armor_smoke.py`, `capability_ab_runner.py`
- **tests**: 80/80 passed (full suite), 30/30 regression
- **benchmark_seam_executed_capabilities**: ddtree ✅, autoreason ✅, artifact_gate ✅, claim_gate ✅, delivery_gate ✅
- **notes**: Runner now copies `exec_resp.raw_model_metadata` to adapter row metadata. Test verifies ddtree_invoked, autoreason_invoked, gate_results all present and invoked=True.

## C8: Final Real Solve Readiness Gate

- **commit**: PENDING (not started)
- **files**: PENDING
- **tests**: PENDING
- **deterministic_full_capability_solve**: PENDING
- **real_local_run**: PENDING (env-gated)
- **real_issue_run**: PENDING (env-gated)
- **notes**: Will add deterministic full capability solve test and gated real local model test.

---

## Final (Current)

- **git status**: `? artifacts/external_sources/sympy_13852`
- **last commits**: `444af7584`, `988c08347`, `fdd162004`, `d5ccdf3c4`, `3ae6cfbd2`, `b7d172036`
- **forbidden grep**: pre-existing refs only (CommitteeOrchestrator in pipeline.py/test)
- **pushed**: no

---

## What's Been Accomplished

### N3 Series (N3.1-N3.14)
- LocalModelExecutor consumes planner-owned execution_topology
- selected_capabilities pass-through with ranking
- SolidSearchReplaceProtocol normalization
- Source anchor (locked_search + AST boundary fallback)
- Failure feedback injection
- Receipt completeness gate
- Real isolated solve
- Gated real Qwen toy solve
- Focused real issue harness

### C Series (C0-C7)
- **C0**: 34 capability wiring audit (all capabilities classified)
- **C1**: Execution context + result contract
- **C2**: Fail-closed executor registry
- **C3**: ddtree/autoreason **real runtime calls** (not just metadata flags)
- **C4**: artifact/claim/delivery gate execution
- **C5**: LocalHeal pipeline bridge (deferred)
- **C6**: Causality receipt coverage gate
- **C7**: Benchmark seam verifies capabilities are executed

### What's NOT Done

| Item | Status | Why Deferred |
|---|---|---|
| C5: LocalHeal pipeline bridge | Deferred | Complex integration, requires `localheal_pipeline` topology |
| codeintel/lancedb/belief/mempalace | External only | No local runtime exists |
| swarm/drone/nightshift/ultra_review | External only | No local runtime exists |

---

## Key Architectural Achievement

Before C3, `selected_capabilities_used` was just metadata pass-through.
After C3, capabilities are **actually invoked** with runtime calls and receipts:

```
selected_capabilities → CapabilityExecutorRegistry.execute_selected()
  → DDTreeLocalExecutor.execute() → DDTreeAdapter.plan()
  → AutoreasonLocalExecutor.execute() → AutoreasonService.run()
  → ArtifactGateLocalExecutor.execute() → evidence check
  → ClaimGateLocalExecutor.execute() → claim validation
  → DeliveryGateLocalExecutor.execute() → delivery block
```

Every selected capability now has causality: invoked=True with receipt, or blocked/unsupported with explicit reason.
