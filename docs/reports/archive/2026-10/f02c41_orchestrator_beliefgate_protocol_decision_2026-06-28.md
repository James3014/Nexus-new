# F-02C41 Orchestrator BeliefGate Protocol Decision

**Status:** `F02C41_ORCHESTRATOR_BELIEFGATE_PROTOCOL_DECISION`

**Date:** 2026-06-28

## Summary

Read-only inventory of `BeliefGate` protocol vs `BeliefEngine` implementation.

## Current State

### BeliefGate Protocol (`belief_contracts.py:20`)

```python
class BeliefGate(Protocol):
    """Minimal interface Orchestrator needs from belief governance."""
    def process_audit_outcome(self, outcome: AuditOutcome) -> dict[str, Any]: ...
```

**Only declares:** `process_audit_outcome`

### BeliefEngine Implementation (`belief_engine.py:16`)

Has 3 public methods:
- `assess_confidence(task_id, assumption) -> float` ✓
- `update_belief(task_id, assumption, confidence, evidence_id)` ✓
- `process_audit_outcome(outcome) -> dict[str, Any]` ✓

### Orchestrator Usage (`orchestrator.py`)

| Line | Method | Has `hasattr` guard? | Pyright Error |
|---|---|---|---|
| 117 | `process_audit_outcome` | Yes | None (in protocol) |
| 119 | `update_belief` | Yes (after first check) | `not known attribute of BeliefGate` |
| 131 | `audit_action` | Yes | None (palace, not belief) |
| 139 | `assess_confidence` | Yes | `not known attribute of BeliefGate` |

## Diagnosis

**Root cause:** `BeliefGate` protocol is incomplete — it only declares `process_audit_outcome`, but orchestrator also calls `update_belief` and `assess_confidence`.

**Is this a stale call?** No — `BeliefEngine` has all 3 methods and they are actively used.

**Is this a missing protocol declaration?** Yes — the protocol should declare all 3 methods that orchestrator needs.

## Safe Fix Options

### Option A: Expand BeliefGate Protocol (Recommended)

Add `update_belief` and `assess_confidence` to `BeliefGate` protocol in `belief_contracts.py`.

**Pros:**
- Minimal change, single file
- Aligns protocol with actual usage
- No runtime behavior change

**Cons:**
- Changes `belief_contracts.py` (not in original allowed files for T40)

### Option B: Keep Runtime Guards Only

The current `hasattr` guards already prevent runtime errors. Pyright errors are type-system only.

**Pros:**
- No code changes needed
- Already safe at runtime

**Cons:**
- Pyright errors remain
- T14 cannot pass with these errors

## Recommendation

**Option A** is the correct fix. The protocol should match the actual interface orchestrator needs.

**Next step:** Expand `BeliefGate` protocol to include `update_belief` and `assess_confidence`.

## Commands Run

```bash
uv run pyright nexus/core
```

## Scope Statement

- Inventory only, no code changed
- Identified root cause: incomplete protocol
- Recommended fix: expand protocol
