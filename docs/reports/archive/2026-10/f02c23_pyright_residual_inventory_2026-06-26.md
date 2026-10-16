# F-02C23 Pyright Residual Inventory

**Status:** `F02C23_PYRIGHT_RESIDUAL_INVENTORY`

**Date:** 2026-06-26

## Summary

Residual Pyright error inventory after T16-T22 batch fixes.

## Current State

- **Total errors:** 60
- **Blocking gate:** NOT eligible (requires 0 errors)

## Errors by File

| File | Count | Category |
|---|---|---|
| `swarm.py` | 13 | Dispatch/encoding/architecture |
| `router.py` | 7 | Route planning/PLoop |
| `orchestrator.py` | 6 | Orchestration/belief |
| `context_hub.py` | 6 | Context/memory |
| `eternal_memory.py` | 3 | Optional dependency (missing import) |
| `dual_loop_orchestrator.py` | 3 | Dual loop/consensus |
| `xray_observer.py` | 2 | Type mismatch |
| `web_action_executor.py` | 2 | Optional dependency (missing import) |
| `telemetry.py` | 2 | Type mismatch |
| `state_io.py` | 2 | TypedDict |
| `state_contracts.py` | 2 | TypedDict |
| `policy_metabolizer.py` | 2 | Type mismatch |
| `policy_manager.py` | 2 | TypedDict/call |
| `learning_steward.py` | 1 | Type mismatch |
| `unified_registry.py` | 1 | Return type |
| `subagent_armor.py` | 1 | Type mismatch |
| `retrieval_memory_adapter.py` | 1 | Type mismatch |
| `learning_scorer.py` | 1 | Type mismatch |
| `critique_engine.py` | 1 | Type mismatch |
| `commander.py` | 1 | Type mismatch |

## Safe to Fix (High Confidence)

| File | Errors | Reason |
|---|---|---|
| `telemetry.py` | 2 | `None` → `Dict[str, Any]` parameter |
| `subagent_armor.py` | 1 | Already guarded |
| `retrieval_memory_adapter.py` | 1 | `None` → `list` parameter |

## Requires Agent Judgment (Runtime Contract)

| File | Errors | Reason |
|---|---|---|
| `swarm.py` | 13 | Dispatch architecture, encoding, remote execution |
| `router.py` | 7 | Route planning, PLoop attributes |
| `orchestrator.py` | 6 | Belief engine, palace integration |
| `context_hub.py` | 6 | Memory injection, context budget |

## Optional Dependency Boundary (Expected)

| File | Errors | Reason |
|---|---|---|
| `eternal_memory.py` | 3 | `cryptography.fernet`, `arweave` not installed |
| `web_action_executor.py` | 2 | `playwright.async_api` not installed |

## Recommendation

- T14 (blocking gate) still blocked at 60 errors
- Next batch should focus on `telemetry.py`, `subagent_armor.py`, `retrieval_memory_adapter.py` (3 easy wins)
- `swarm.py` (13 errors) needs architectural judgment — defer to main agent
- Optional dependency errors are documented and expected

## Commands Run

```bash
uv run pyright nexus/core
```

## Scope Statement

- Inventory only, no code changed
- Pyright remains observation-only
- T14 still blocked
