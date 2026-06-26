# F-02C26 State Contract / State IO Small Batch

**Status:** `F02C26_STATE_CONTRACT_IO_FIXED`

**Date:** 2026-06-26

## Summary

Fixed 3 type errors in `state_contracts.py` and `state_io.py`.

## Files Changed

| File | Change |
|---|---|
| `nexus/core/state_contracts.py` | Fixed `metadata` default factory, guarded `conversation.update()` |
| `nexus/core/state_io.py` | Added `isinstance` check for `failure_count` |

## Fixes Applied

| File | Line | Before | After |
|---|---|---|---|
| `state_contracts.py:219` | `Field(default_factory=dict)` | `Field(default_factory=PipelineMetadata)` |
| `state_contracts.py:250` | `self.metadata["conversation"].update(updates)` | Guard with `if conversation:` |
| `state_io.py:90` | `failure_count >= 3` | `isinstance(failure_count, int) and failure_count >= 3` |

## Commands Run

```bash
python3 -m py_compile nexus/core/state_contracts.py nexus/core/state_io.py
uv run pyright nexus/core
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 54 | 51 | -3 |

## Scope Statement

- Only type fixes applied
- No state serialization changed
- No migration behavior changed
