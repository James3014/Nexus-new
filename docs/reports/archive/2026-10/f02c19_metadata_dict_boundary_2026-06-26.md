# F-02C19 Policy / Learning Metadata Dict Boundary

**Status:** `F02C19_METADATA_DICT_BOUNDARY_FIXED`

**Date:** 2026-06-26

## Summary

Fixed type mismatches where `PipelineMetadata` was passed to functions expecting `dict[Unknown, Unknown]` by changing parameter types to `MutableMapping[str, Any]`.

## Files Changed

| File | Change |
|---|---|
| `nexus/core/learning_steward.py` | Added `MutableMapping` import, changed 3 function signatures |
| `nexus/core/learning_scorer.py` | Added `MutableMapping` import, changed 1 function signature |

## Fixes Applied

| File | Function | Before | After |
|---|---|---|---|
| `learning_steward.py` | `_profile_for` | `metadata: dict` | `metadata: MutableMapping[str, Any]` |
| `learning_steward.py` | `_failure_history` | `metadata: dict` | `metadata: Mapping[str, Any]` |
| `learning_steward.py` | `_evaluate_canary` | `metadata: dict` | `metadata: MutableMapping[str, Any]` |
| `learning_scorer.py` | `_update_success_window` | `metadata: dict` | `metadata: MutableMapping[str, Any]` |

## Commands Run

```bash
python3 -m py_compile nexus/core/learning_steward.py nexus/core/learning_scorer.py
uv run pyright nexus/core
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 75 | 74 | -1 |

## Scope Statement

- Only type annotations changed
- No learning scoring behavior changed
- No policy decision semantics changed
