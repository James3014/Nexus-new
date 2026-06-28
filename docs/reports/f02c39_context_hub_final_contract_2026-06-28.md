# F-02C39 Context Hub Final Contract Narrowing

**Status:** `F02C39_CONTEXT_HUB_FINAL_CONTRACT_FIXED`

**Date:** 2026-06-28

## Summary

Fixed 2 type errors in `context_hub.py` by correcting stale API calls.

## File Changed

| File | Change |
|---|---|
| `nexus/core/context_hub.py` | Removed stale `to_dict()` call, removed non-existent `aggression` parameter |

## Fixes Applied

| Line | Before | After | Root Cause |
|---|---|---|---|
| 411 | `state.to_dict() if hasattr(...)` | `vars(state)` | Stale call — `NexusState` has no `to_dict()` |
| 424 | `prune_dialogue(history, aggression=nas_aggression)` | `prune_dialogue(history)` | Wrong parameter name — `prune_dialogue` has no `aggression` param |

## Commands Run

```bash
python3 -m py_compile nexus/core/context_hub.py
uv run pyright nexus/core
uv run bandit -r nexus/core -ll -ii
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 25 | 23 | -2 |
| context_hub.py errors | 2 | 0 | -2 |
| Bandit medium/high | 0 | 0 | 0 |

## Scope Statement

- Only stale API call corrections
- No memory injection behavior changed
- No audit-level decision changed
- No context budget policy changed
- Bandit still passes
