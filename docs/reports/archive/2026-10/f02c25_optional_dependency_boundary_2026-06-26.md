# F-02C25 Optional Dependency Boundary Cleanup

**Status:** `F02C25_OPTIONAL_DEPENDENCY_BOUNDARY_CLEANED`

**Date:** 2026-06-26

## Summary

Improved optional dependency handling in `eternal_memory.py` and `web_action_executor.py`.

## Files Changed

| File | Change |
|---|---|
| `nexus/core/eternal_memory.py` | Added `None` guard before `cipher.encrypt()` |
| `nexus/core/web_action_executor.py` | Used `TYPE_CHECKING` + `Any` for optional `playwright` import |

## Fixes Applied

### eternal_memory.py

| Line | Before | After |
|---|---|---|
| 89 | `self.cipher.encrypt(...)` | Guard with `if self.cipher is None: return None` |

### web_action_executor.py

| Line | Before | After |
|---|---|---|
| 5-8 | `from playwright.async_api import Page` | `TYPE_CHECKING` guard + `Any` fallback |
| 16 | `page: Page` | `page: Any` |

## Commands Run

```bash
python3 -m py_compile nexus/core/eternal_memory.py nexus/core/web_action_executor.py
uv run pyright nexus/core
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 55 | 54 | -1 |

## Remaining (Accepted Residual)

| File | Error | Reason |
|---|---|---|
| `eternal_memory.py:9` | Missing import `cryptography.fernet` | Optional dependency not installed |
| `eternal_memory.py:14` | Missing import `arweave` | Optional dependency not installed |
| `web_action_executor.py:6` | Missing import `playwright.async_api` | Optional dependency not installed |

These are expected when packages are not installed. Documented as accepted residual.

## Scope Statement

- Only type fixes and guards added
- No new dependencies added
- Fail-closed behavior preserved
