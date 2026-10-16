# F-02C3A Optional Member Guards (Commander + Orchestrator)

**Status:** `F02C3A_OPTIONAL_GUARDS_APPLIED`

**Date:** 2026-06-26

## Summary

Added minimal `if x is None` guards for optional member access in `commander.py` and `orchestrator.py`.

## Files Changed

| File | Change |
|---|---|
| `nexus/core/commander.py` | Added guards before `state_io.load_global_state()` and `state_io.save_global_state()` calls |
| `nexus/core/orchestrator.py` | Added guard before `llm.ask_with_template()` call |

## Guards Applied

### commander.py

| Line | Guard | Failure Behavior |
|---|---|---|
| 46 | `if self.state_io:` | Falls back to `NexusState()` default |
| 61 | `if self.state_io:` | Skips save |
| 86 | `if self.state_io:` | Skips save |
| 156 | `if self.state_io:` | Skips save |
| 162 | `if self.state_io:` | Falls back to `NexusState()` |
| 169 | `if self.state_io:` | Skips save |

### orchestrator.py

| Line | Guard | Failure Behavior |
|---|---|---|
| 87 | `if not self.llm:` | Returns `False` (fail closed) |

## Commands Run

```bash
python3 -m py_compile nexus/core/commander.py nexus/core/orchestrator.py
uv run pyright nexus/core
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 105 | 102 | -3 |

## Scope Statement

- Only optional member access guards added
- No business logic changed
- No exceptions swallowed
- Fail-closed behavior preserved
