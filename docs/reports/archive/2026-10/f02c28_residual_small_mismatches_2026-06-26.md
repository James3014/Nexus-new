# F-02C28 Residual Small Mismatches

**Status:** `F02C28_RESIDUAL_SMALL_MISMATCHES_FIXED`

**Date:** 2026-06-26

## Summary

Fixed 3 type errors in 3 files with targeted fixes.

## Files Changed

| File | Change |
|---|---|
| `nexus/core/critique_engine.py` | Changed `dict = None` to `Optional[dict] = None` |
| `nexus/core/xray_observer.py` | Added `Path` import, fixed `FindingsMemoryStore` and `confidence` types |
| `nexus/core/unified_registry.py` | Added `SkillFrontmatter` conversion before return |

## Fixes Applied

| File | Line | Before | After |
|---|---|---|---|
| `critique_engine.py:69` | `evidence_bundle: dict = None` | `evidence_bundle: Optional[dict] = None` |
| `xray_observer.py:63` | `FindingsMemoryStore(".")` | `FindingsMemoryStore(Path("."))` |
| `xray_observer.py:72` | `confidence=1.0` | `confidence="1.0"` |
| `unified_registry.py:79` | `return self.registry.get_by_task_id(...)` | Convert to `SkillFrontmatter` before return |

## Commands Run

```bash
python3 -m py_compile nexus/core/critique_engine.py nexus/core/xray_observer.py nexus/core/unified_registry.py
uv run pyright nexus/core
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 50 | 47 | -3 |

## Scope Statement

- Only type fixes applied
- No registry semantics changed
- No data format changed
