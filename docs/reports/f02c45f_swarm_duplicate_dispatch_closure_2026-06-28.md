# F-02C45F Swarm Duplicate Dispatch Closure

**Status:** `F02C45F_SWARM_DUPLICATE_DISPATCH_CLOSED`

**Date:** 2026-06-28

## Summary

Removed duplicate `_dispatch_remote` definition in `FederatedSwarmOrchestrator`.

## File Changed

| File | Change |
|---|---|
| `nexus/core/swarm.py` | Removed duplicate `_dispatch_remote` method (line 233-258) |

## Fix Applied

Removed the first `_dispatch_remote` method that lacked the federation security boundary check. The second method (line 267) with `_ALLOWED_REMOTE_PHASES` enforcement is now the only definition.

## Commands Run

```bash
python3 -m py_compile nexus/core/swarm.py
uv run pyright nexus/core
uv run bandit -r nexus/core -ll -ii
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 5 | 4 | -1 |
| swarm.py errors | 1 | 0 | -1 |
| Bandit medium/high | 0 | 0 | 0 |

## Scope Statement

- Only duplicate method removed
- Federation security boundary preserved
- mTLS dispatch behavior preserved
- Bandit still passes
