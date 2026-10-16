# U3-3A Selected / Applied Trace Contract Report

**日期**: 2026-06-22
**狀態**: `U3_3A_SELECTED_APPLIED_TRACE_CONTRACT_PASS`
**Commit**: `a08afe14 local-heal: mark selected committee candidate state`
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Scope

U3-3A only. Mark selected/applied/worktree_applied state on candidate snapshots after judge selection.

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/committee_orchestrator.py` | Mark selected/applied/worktree_applied on snapshots, add selected_candidate_applied to receipt |
| `tests/unit/local_heal/test_committee_route_trace.py` | Update 4 existing tests, no new tests needed |

## Behavior

| Path | selected | applied | worktree_applied | failure_reason |
|------|----------|---------|------------------|----------------|
| Last winner wins | true | true | true | (none) |
| Non-last selected | true | false | false | COMMITTEE_SELECTED_NON_APPLIED_CANDIDATE_UNSUPPORTED |
| Missing mapping | false | false | false | COMMITTEE_WINNER_CANDIDATE_MAPPING_MISSING |

## New Receipt Field

```json
"committee_receipt": {
  "selected_candidate_applied": true
}
```

## Compile & Test

```
python3 -m py_compile nexus/services/local_heal/committee_orchestrator.py tests/unit/local_heal/test_committee_route_trace.py
→ OK

pytest tests/unit/local_heal/test_committee_route_trace.py -v
→ 10 passed

pytest tests/unit/local_heal/test_native_route_adapter.py tests/unit/local_heal/test_role_contract.py -q
→ 21 passed
```

## What U3-3A Does NOT Do

```text
No hash comparison (U3-3B)
No selected-candidate re-apply (U3-3C)
No H5 / local-first / local-only
No production_ready / public_claim_allowed
```
