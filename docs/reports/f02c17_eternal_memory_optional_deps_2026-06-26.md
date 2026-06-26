# F-02C17 Eternal Memory Optional Dependency Boundary

**Status:** `F02C17_ETERNAL_MEMORY_OPTIONAL_DEPS_FIXED`

**Date:** 2026-06-26

## Summary

Added fail-closed guards for optional `cryptography.fernet` and `arweave` dependencies in `eternal_memory.py`.

## File Changed

| File | Change |
|---|---|
| `nexus/core/eternal_memory.py` | Added guards for `Fernet` and `arweave` before use |

## Guards Applied

| Line | Guard | Failure Behavior |
|---|---|---|
| 38 | `elif arweave is None:` | Sets `self.wallet = None`, logs error |
| 44 | `if Fernet is None:` | Sets `self.key = b""`, `self.cipher = None`, logs error |
| 92 | `if self.wallet and arweave is not None:` | Returns `None` |

## Commands Run

```bash
python3 -m py_compile nexus/core/eternal_memory.py
uv run pyright nexus/core
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 83 | 80 | -3 |
| eternal_memory.py errors | 6 | 3 | -3 |

Remaining 3 errors are missing import reports (expected when packages not installed).

## Scope Statement

- Only optional dependency guards added
- No new dependencies added
- Fail-closed behavior preserved
- No storage format changed
