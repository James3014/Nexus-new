# F-02C20 Router / PLoop / Plan Narrowing

**Status:** `F02C20_ROUTER_PLAN_NARROWING_FIXED`

**Date:** 2026-06-26

## Summary

Fixed 7 type errors in `router.py` by adding `Optional` type hints, using `getattr` for dynamic attribute access, and narrowing `plan` type.

## File Changed

| File | Change |
|---|---|
| `nexus/core/router.py` | Fixed `Optional` params, `getattr` for PLoopManager, narrowed plan access |

## Fixes Applied

| Line | Before | After |
|---|---|---|
| 27 | `run_dir: str = None` | `run_dir: Optional[str] = None` |
| 43 | `code_payload: str = None` | `code_payload: Optional[str] = None` |
| 127-131 | Direct attribute access on `PLoopManager` | `getattr` with fallback |
| 300-301 | `plan.plan_id` / `plan.task_id` | `getattr` with dict fallback |

## Commands Run

```bash
python3 -m py_compile nexus/core/router.py
uv run pyright nexus/core
uv run bandit -r nexus/core -ll -ii
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 74 | 67 | -7 |
| Bandit medium/high | 0 | 0 | 0 |

## Scope Statement

- Only type narrowing applied
- No routing decisions changed
- No capability selection changed
- Bandit still passes
