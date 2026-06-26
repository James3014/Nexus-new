# F-02C31 Router Low-Risk Pass

**Status:** `F02C31_ROUTER_LOW_RISK_PASS_FIXED`

**Date:** 2026-06-26

## Summary

Fixed 4 type errors in `router.py` with low-risk, targeted fixes.

## File Changed

| File | Change |
|---|---|
| `nexus/core/router.py` | Added `Optional` import, fixed `None` handling, added `Optional` type hints |

## Fixes Applied

| Line | Before | After |
|---|---|---|
| 6 | `from typing import Dict, Any, List` | `from typing import Dict, Any, List, Optional` |
| 226 | `str(row.get(...) or ... or "")` | Separate variable with explicit `None` check |
| 452 | `provenance: str = None, row_id: str = None` | `provenance: Optional[str] = None, row_id: Optional[str] = None` |

## Commands Run

```bash
python3 -m py_compile nexus/core/router.py
uv run pyright nexus/core
uv run bandit -r nexus/core -ll -ii
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 43 | 39 | -4 |
| router.py errors | 7 | 3 | -4 |
| Bandit medium/high | 0 | 0 | 0 |

## Scope Statement

- Only type fixes applied
- No route scoring changed
- No capability selection changed
- Bandit still passes
