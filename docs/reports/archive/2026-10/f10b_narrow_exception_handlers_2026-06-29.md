# F-10B Narrow Exception Handlers

**Status:** `F10B_NARROW_EXCEPTION_HANDLERS`

**Date:** 2026-06-29

## Summary

Narrowed 2 low-risk exception handlers in runtime code.

## Files Changed

| File | Line | Before | After |
|---|---|---|---|
| `nexus/core/drone_engine.py` | 71 | `except:` | `except (json.JSONDecodeError, ValueError):` |
| `nexus/health/service.py` | 253 | `except Exception: pass` | `except (KeyError, TypeError, ValueError): pass` |

## Commands Run

```bash
python3 -m py_compile nexus/core/drone_engine.py nexus/health/service.py
uv run pyright nexus/core
```

## Results

| Metric | Before | After |
|---|---|---|
| Pyright errors | 0 | 0 |

## Scope Statement

- Only 2 exception handlers narrowed
- No control flow changed
- Pyright stays green
