# F-02C4A Argument Type Mismatches (Small Batch)

**Status:** `F02C4A_ARGUMENT_TYPE_FIXES_APPLIED`

**Date:** 2026-06-26

## Summary

Fixed 3 argument type mismatches in `knowledge_injector.py` and `subagent_armor.py`.

## Files Changed

| File | Change |
|---|---|
| `nexus/core/knowledge_injector.py` | Changed `List[str] = None` to `Optional[List[str]] = None` |
| `nexus/core/subagent_armor.py` | Added guard for `NEXUS_WORKTREE` env var before `Path()` |

## Fixes Applied

| File | Line | Before | After |
|---|---|---|---|
| `knowledge_injector.py:13` | `target_files: List[str] = None` | `target_files: Optional[List[str]] = None` |
| `subagent_armor.py:40` | `Path(os.getenv("NEXUS_WORKTREE"))` | Guard with `if not worktree_str: raise ValueError(...)` |

## Commands Run

```bash
python3 -m py_compile nexus/core/knowledge_injector.py nexus/core/subagent_armor.py
uv run pyright nexus/core
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 94 | 91 | -3 |

## Scope Statement

- Only type annotations and guards fixed
- No API restructured
- No runtime behavior changed
