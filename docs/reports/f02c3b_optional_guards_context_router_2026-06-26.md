# F-02C3B Optional Member Guards (Context / Router / Research)

**Status:** `F02C3B_OPTIONAL_GUARDS_APPLIED`

**Date:** 2026-06-26

## Summary

Added minimal guards for optional member access in `context_hub.py` and `research/gear.py`.

## Files Changed

| File | Change |
|---|---|
| `nexus/core/context_hub.py` | Added ternary guards for `knowledge_injector` calls |
| `nexus/core/research/gear.py` | Added early return guard for `router` |

## Guards Applied

### context_hub.py

| Line | Guard | Failure Behavior |
|---|---|---|
| 223 | `if self.knowledge_injector else []` | Returns empty list |
| 224 | `if self.knowledge_injector else ""` | Returns empty string |
| 536 | `if self.knowledge_injector else []` | Returns empty list |
| 537 | `if self.knowledge_injector else ""` | Returns empty string |

### research/gear.py

| Line | Guard | Failure Behavior |
|---|---|---|
| 30 | `if not self.router:` | Returns error dict |

## Commands Run

```bash
python3 -m py_compile nexus/core/context_hub.py nexus/core/research/gear.py
uv run pyright nexus/core
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 102 | 94 | -8 |

## Scope Statement

- Only optional member access guards added
- No business logic changed
- No routing decisions changed
- Fail-closed behavior preserved
