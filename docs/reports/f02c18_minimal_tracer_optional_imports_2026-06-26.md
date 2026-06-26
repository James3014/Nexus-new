# F-02C18 Minimal Tracer Optional Import Cleanup

**Status:** `F02C18_MINIMAL_TRACER_OPTIONAL_IMPORTS_FIXED`

**Date:** 2026-06-26

## Summary

Fixed 5 `reportPossiblyUnboundVariable` errors in `minimal_tracer.py` by pre-declaring OTel imports with `None` defaults.

## File Changed

| File | Change |
|---|---|
| `nexus/core/minimal_tracer.py` | Pre-declared OTel imports as module-level variables with `None` defaults |

## Approach

The original code imported OTel symbols inside a `try/except` block, but Pyright couldn't guarantee they were bound when used later. Fixed by:
1. Declaring `_trace`, `_TracerProvider`, `_SimpleSpanProcessor`, `_InMemorySpanExporter` as module-level `Any` variables initialized to `None`
2. Importing into these variables inside the `try` block
3. Adding `is not None` guards before use

## Commands Run

```bash
python3 -m py_compile nexus/core/minimal_tracer.py
uv run pyright nexus/core
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 80 | 75 | -5 |
| minimal_tracer.py errors | 5 | 0 | -5 |

## Scope Statement

- Only import structure changed
- No tracing behavior changed
- JSONL fallback preserved
- No-op tracing when OTel unavailable preserved
