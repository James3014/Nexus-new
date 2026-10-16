# F-02C34 Orchestrator Contract Inventory

**Status:** `F02C34_ORCHESTRATOR_CONTRACT_INVENTORY`

**Date:** 2026-06-26

## Summary

Inventory of `orchestrator.py` 6 errors — analyzing contract mismatches between `BeliefGate` protocol and actual usage.

## Errors

| Line | Error | Root Cause |
|---|---|---|
| 117 | `process_audit_outcome` not known attribute of `None` | `self.belief_engine` could be `None` |
| 119 | `update_belief` not known attribute of `BeliefGate` | `BeliefGate` protocol missing `update_belief` |
| 119 | `update_belief` not known attribute of `None` | `self.belief_engine` could be `None` |
| 131 | `audit_action` not known attribute of `None` | `self.palace` could be `None` |
| 139 | `assess_confidence` not known attribute of `BeliefGate` | `BeliefGate` protocol missing `assess_confidence` |
| 139 | `assess_confidence` not known attribute of `None` | `self.belief_engine` could be `None` |

## BeliefGate Protocol Definition

**File:** `nexus/core/belief_contracts.py:20`

```python
class BeliefGate(Protocol):
    def process_audit_outcome(self, outcome: AuditOutcome) -> dict[str, Any]: ...
```

**Missing methods:**
- `update_belief(task_id, assumption, confidence, evidence_id)`
- `assess_confidence(task_id, assumption) -> float`

## BeliefEngine Implementation

**File:** `nexus/core/belief_engine.py`

Has all 3 methods:
- `process_audit_outcome` ✓
- `update_belief` ✓
- `assess_confidence` ✓

## Diagnosis

1. **`BeliefGate` protocol is incomplete** — only declares `process_audit_outcome`, missing `update_belief` and `assess_confidence`
2. **`self.belief_engine` type is `BeliefGate | Any | None`** — could be `None`
3. **`self.palace` type is `Any | None`** — could be `None`

## Recommendation

**Safe fix (Agent B can do):**
- Add `update_belief` and `assess_confidence` to `BeliefGate` protocol
- Add `None` guards before calling methods

**Requires main agent judgment:**
- Whether `BeliefGate` should be expanded or a new protocol created
- Whether `_NullBeliefGate` should implement all methods

## Commands Run

```bash
uv run pyright nexus/core
```

## Scope Statement

- Inventory only, no code changed
- Identified root cause: incomplete protocol definition
