# F-02C38 Router Final Low-Risk Narrowing

**Status:** `F02C38_ROUTER_FINAL_NARROWING_FIXED`

**Date:** 2026-06-28

## Summary

Fixed 3 type errors in `router.py` with low-risk, targeted fixes.

## File Changed

| File | Change |
|---|---|
| `nexus/core/router.py` | Fixed `None` handling and narrowed `plan` type |

## Fixes Applied

| Line | Before | After |
|---|---|---|
| 226 | `metadata.get(...)` chain | Separate `None` check for `metadata` |
| 294 | `controller.execute_plan(plan)` | Narrow with `isinstance(plan, dict)` check |

## Commands Run

```bash
python3 -m py_compile nexus/core/router.py
uv run pyright nexus/core
uv run bandit -r nexus/core -ll -ii
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 28 | 25 | -3 |
| router.py errors | 3 | 0 | -3 |
| Bandit medium/high | 0 | 0 | 0 |

## Scope Statement

- Only type narrowing applied
- No route scoring changed
- No capability selection changed
- Bandit still passes
