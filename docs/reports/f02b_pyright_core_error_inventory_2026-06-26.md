# F-02B Pyright Core Error Inventory

**Status:** `F02B_PYRIGHT_CORE_ERROR_INVENTORY_ONLY`

**Date:** 2026-06-26

## Command

```bash
uv run pyright nexus/core
```

**Exit code:** 1

**Result:** 193 errors, 0 warnings, 0 informations

## Top 5 Error Clusters

### Cluster 1: TypedDict Key Violations (41 errors)

**Files affected:** `learning_governance.py`, `learning_scorer.py`, `learning_steward.py`, `mental_snapshot.py`, `policy_manager.py`, `self_evolve_engine.py`, `state_io.py`, `swarm_orchestrator.py`

**Root cause:** `PipelineMetadata` TypedDict is missing many keys that code assigns to it. The TypedDict definition in `state_contracts.py` is too narrow.

**Proposed batch:** F-02C1 — Expand `PipelineMetadata` TypedDict to include all used keys.

### Cluster 2: reportAttributeAccessIssue on Mixins (40+ errors)

**Files affected:** `state_legacy.py` (30+), `router.py` (5), `swarm.py` (3), `vector_rag.py` (2)

**Root cause:** `NexusStateLegacyMixin` accesses attributes (`tokens`, `observability`, `audit`, `phase_health`, `metadata`) that are defined on `NexusState` but not declared on the mixin. `PLoopManager` and `BeliefGate` similarly have undeclared attributes.

**Proposed batch:** F-02C2 — Add attribute declarations to `NexusStateLegacyMixin` and related protocol classes.

### Cluster 3: reportOptionalMemberAccess (24 errors)

**Files affected:** `commander.py` (5), `context_hub.py` (4), `orchestrator.py` (5), `research/gear.py` (4), `router.py` (4), `swarm.py` (1), `vector_rag.py` (1)

**Root cause:** Calling methods on values that could be `None` without narrowing the type first.

**Proposed batch:** F-02C3 — Add `assert` or `if` guards before optional attribute access.

### Cluster 4: reportArgumentType (32 errors)

**Files affected:** `commander.py`, `context_hub.py`, `drone_engine.py`, `dual_loop_orchestrator.py`, `knowledge_injector.py`, `policy_metabolizer.py`, `retrieval_memory_adapter.py`, `router.py`, `skill_assembler.py`, `state_contracts.py`, `subagent_armor.py`, `swarm.py`, `telemetry.py`, `unified_registry.py`, `vector_rag.py`, `xray_observer.py`

**Root cause:** Mixed `Path`/`str`, `None`/required, `Dict`/TypedDict, `float`/`str` type mismatches.

**Proposed batch:** F-02C4 — Fix type mismatches file-by-file.

### Cluster 5: Undefined/Missing Imports (8 errors)

**Files affected:** `eternal_memory.py` (2 missing imports + 1 undefined), `steward.py` (1 undefined), `truth_validator.py` (1 undefined), `web_action_executor.py` (1 missing import), `policy_loader.py` (1 possibly unbound), `skill_assembler.py` (1 possibly unbound)

**Root cause:** Missing `import` statements or optional dependency imports without fallback.

**Proposed batch:** F-02C5 — Add missing imports and guard optional dependencies.

## Remaining Clusters

| Cluster | Count | Files | Proposed Batch |
|---|---|---|---|
| reportCallIssue | 6 | `context_hub.py`, `dual_loop_orchestrator.py`, `policy_manager.py`, `swarm.py` | F-02C6 |
| reportIncompatibleMethodOverride | 2 | `drone_engine.py` | F-02C7 |
| reportReturnType | 3 | `context_hub.py`, `unified_registry.py`, `workspace_prefetch.py` | F-02C8 |
| reportRedeclaration | 2 | `policy_loader.py`, `swarm.py` | F-02C9 |
| reportOperatorIssue | 2 | `vector_rag.py` | F-02C10 |
| reportGeneralTypeIssues | 2 | `policy_manager.py`, `swarm.py` | F-02C6 (merged) |

## Summary

| Batch | Error Count | Description |
|---|---|---|
| F-02C1 | 41 | TypedDict key expansion |
| F-02C2 | 40+ | Mixin attribute declarations |
| F-02C3 | 24 | Optional member access guards |
| F-02C4 | 32 | Type argument mismatches |
| F-02C5 | 8 | Missing imports |
| F-02C6 | 8 | Call issues + general type issues |
| F-02C7 | 2 | Method override compatibility |
| F-02C8 | 3 | Return type fixes |
| F-02C9 | 2 | Redeclaration cleanup |
| F-02C10 | 2 | Operator fixes |
| **Total** | **~193** | |

## Scope Statement

- No code changed (inventory only)
- Pyright remains observation-only
- F-02 not complete — type errors not fixed
- Proposed batches are suggestions for future remediation
