# U3-3B Selected Candidate Hash Contract Report

**日期**: 2026-06-22
**狀態**: `U3_3B_SELECTED_CANDIDATE_HASH_CONTRACT_PASS`
**Commit**: pending
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Scope

U3-3B only. Add hash verification for the existing last-candidate apply path.

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/committee_orchestrator.py` | +`_compute_patch_hash` helper, +hash verification after final_patch set, +3 new committee_receipt fields |
| `tests/unit/local_heal/test_committee_route_trace.py` | +1 new test (hash mismatch fail-closed), updated existing tests to verify hash fields |

## New committee_receipt Fields

```json
{
  "selected_candidate_patch_sha256": "33df0cf768d9f425",
  "applied_patch_sha256": "33df0cf768d9f425",
  "selected_candidate_apply_hash_match": true
}
```

## Behavior by Path

| Path | selected_candidate_patch_sha256 | applied_patch_sha256 | selected_candidate_apply_hash_match |
|------|------|------|------|
| Last winner, hash matches | candidate isolated hash | sha256(final_patch) | true |
| Last winner, hash mismatch | candidate isolated hash | tampered hash | false → fail-closed |
| Non-last selected | candidate isolated hash | "" | false |
| Missing mapping | "" | "" | false |

## Hash Mismatch Fail-Closed

```text
failure_reason = COMMITTEE_SELECTED_CANDIDATE_APPLY_HASH_MISMATCH
solve_eligible = false
final_patch = ""
verifier NOT executed
```

## Compile & Test

```
python3 -m py_compile nexus/services/local_heal/committee_orchestrator.py tests/unit/local_heal/test_committee_route_trace.py
→ OK

pytest tests/unit/local_heal/test_committee_route_trace.py -v
→ 11 passed

pytest tests/unit/local_heal/test_native_route_adapter.py tests/unit/local_heal/test_role_contract.py -q
→ 21 passed
```

## What U3-3B Does NOT Do

```text
No selected-candidate re-apply (U3-3C)
No H5 / local-first / local-only
No production_ready / public_claim_allowed
```
