# F-02C16 Commander + State Contract Fixes

**Status:** `F02C16_COMMANDER_STATE_CONTRACT_FIXED`

**Date:** 2026-06-26

## Summary

Fixed 5 type errors in `commander.py` by adding `task_id` parameter to `NexusState()` calls, converting `Path` to `str` for `PolicyManager`, and adding missing keys to `PipelineMetadata`.

## Files Changed

| File | Change |
|---|---|
| `nexus/core/commander.py` | Added `task_id="unknown"` to `NexusState()` calls, used `str(self.project_root)` |
| `nexus/core/pipeline_metadata.py` | Added `v7_triggered` and `command` keys |

## Fixes Applied

| File | Line | Before | After |
|---|---|---|---|
| `commander.py:46` | `NexusState()` | `NexusState(task_id="unknown")` |
| `commander.py:56` | `PolicyManager(self.project_root)` | `PolicyManager(str(self.project_root))` |
| `commander.py:66` | `PolicyManager(self.project_root)` | `PolicyManager(str(self.project_root))` |
| `commander.py:163` | `NexusState()` | `NexusState(task_id=args.get("task", "unknown"))` |
| `pipeline_metadata.py` | Missing keys | Added `v7_triggered: bool`, `command: str` |

## Commands Run

```bash
python3 -m py_compile nexus/core/commander.py nexus/core/pipeline_metadata.py
uv run pyright nexus/core
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 88 | 83 | -5 |

## Scope Statement

- Only type fixes applied
- No runtime behavior changed
- No state serialization changed
