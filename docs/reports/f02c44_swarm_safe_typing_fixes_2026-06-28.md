# F-02C44 Swarm Safe Typing Fixes

**Status:** `F02C44_SWARM_SAFE_TYPING_FIXES`

**Date:** 2026-06-28

## Summary

Fixed 9 type errors in `swarm.py` with safe, targeted fixes.

## File Changed

| File | Change |
|---|---|
| `nexus/core/swarm.py` | Fixed dict conversion, optional model, client context guard |

## Fixes Applied

| Line | Before | After |
|---|---|---|
| 99 | `dict(result) if result else {...}` | `if isinstance(result, dict): return result` |
| 106 | `dict(result) if result else {...}` | `if isinstance(result, dict): return result` |
| 200 | `model: str = None` | `model: Optional[str] = None` |
| 231 | `self.tls_provider.get_client_context()` | Guard with `if not self.tls_provider: return None` |
| 347 | `model=None` | `model: Optional[str] = None` |

## Commands Run

```bash
python3 -m py_compile nexus/core/swarm.py
uv run pyright nexus/core
uv run bandit -r nexus/core -ll -ii
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 17 | 8 | -9 |
| swarm.py errors | 13 | 4 | -9 |
| Bandit medium/high | 0 | 0 | 0 |

## Remaining swarm.py Errors (4)

| Line | Error | Category |
|---|---|---|
| 229 | `_dispatch_remote` obscured by same name | Duplicate method |
| 270 | Cannot access `_dispatch_remote` for `object` | Remote dispatch |
| 276 | Cannot access `_repair` for `object` | Remote dispatch |
| 335 | Cannot access `history` for `PeerSwarmOrchestrator` | Peer history |

## Scope Statement

- Only type fixes applied
- No swarm behavior changed
- No remote dispatch architecture changed
- Bandit still passes
