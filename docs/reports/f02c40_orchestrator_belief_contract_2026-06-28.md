# F-02C40 Orchestrator Belief Contract Narrowing

**Status:** `F02C40_ORCHESTRATOR_BELIEF_CONTRACT_FIXED`

**Date:** 2026-06-28

## Summary

Fixed 4 type errors in `orchestrator.py` by adding `None` guards before attribute access.

## File Changed

| File | Change |
|---|---|
| `nexus/core/orchestrator.py` | Added `None` guards for `belief_engine` and `palace` |

## Fixes Applied

| Line | Before | After |
|---|---|---|
| 116-124 | `hasattr(self.belief_engine, ...)` then call | Added `and self.belief_engine is not None` |
| 129-134 | `hasattr(self.palace, ...)` then call | Added `and self.palace is not None` |
| 136-139 | `hasattr(self.belief_engine, ...)` check | Added `or self.belief_engine is None` |

## Root Cause

`BeliefGate` protocol only declares `process_audit_outcome`, but code also calls `update_belief` and `assess_confidence`. These exist in `BeliefEngine` but not in the protocol. Added `None` guards to satisfy Pyright.

## Commands Run

```bash
python3 -m py_compile nexus/core/orchestrator.py
uv run pyright nexus/core
uv run bandit -r nexus/core -ll -ii
```

## Results

| Metric | Before | After | Delta |
|---|---|---|---|
| Pyright total errors | 23 | 19 | -4 |
| orchestrator.py errors | 6 | 2 | -4 |
| Bandit medium/high | 0 | 0 | 0 |

## Remaining orchestrator.py Errors

2 errors remain — `update_belief` and `assess_confidence` not in `BeliefGate` protocol. These are protocol-level issues that require main agent judgment.

## Scope Statement

- Only `None` guards added
- No belief scoring semantics changed
- No palace/audit routing changed
- Bandit still passes
