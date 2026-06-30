# U3-2 Candidate Isolation Store Report

**日期**: 2026-06-22
**狀態**: `U3_2_CANDIDATE_ISOLATION_STORE_PASS`
**Commit**: `9b7cb53f local-heal: store isolated committee candidates`
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Scope

U3-2 only. Record and preserve candidate patches by candidate_id as isolated candidate records.

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/committee_orchestrator.py` | +isolation fields on candidate_snapshot |
| `tests/unit/local_heal/test_committee_route_trace.py` | +5 new tests for isolation |

## Candidate Schema (U3-2 additions)

```json
{
  "candidate_id": "C_12481#candidate-1",
  "isolation_status": "stored",
  "isolated_patch_sha256": "...",
  "isolated_patch_length": 123,
  "isolation_store": "committee_trace",
  "worktree_applied": false
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

## Tests

| Test | What it verifies |
|------|-----------------|
| `test_committee_candidates_are_isolated` | isolation_status="stored", isolated_patch_sha256==patch_sha256, isolated_patch_length==patch_length |
| `test_committee_non_selected_candidate_remains_unapplied` | non-selected candidate: applied=false, worktree_applied=false |
| `test_committee_isolation_preserved_in_non_last_fail_closed` | isolation fields present even in COMMITTEE_SELECTED_NON_APPLIED_CANDIDATE_UNSUPPORTED |
| `test_committee_isolation_preserved_in_missing_mapping` | isolation fields present even in COMMITTEE_WINNER_CANDIDATE_MAPPING_MISSING |
| `test_committee_isolation_fields_persisted_in_receipt` | isolation fields survive through build_repair_receipt |

## What U3-2 Does NOT Do

```text
No selected-candidate re-apply (U3-3)
No hash comparison (U3-3)
No worktree modification for non-selected candidates
No H5 / local-first / local-only
No production_ready / public_claim_allowed
```
