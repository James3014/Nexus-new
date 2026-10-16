# U3-3C Selected Candidate Re-apply Report

**日期**: 2026-06-22
**狀態**: `U3_3C_SELECTED_CANDIDATE_REAPPLY_PASS`
**Commit**: pending
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Scope

U3-3C only. Replace non-last fail-closed with deterministic selected-candidate re-apply.

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/committee_orchestrator.py` | Unified apply path for last/non-last, +artifact missing check, +reapply_mode field |
| `tests/unit/local_heal/test_committee_route_trace.py` | Rewrote non-last test to verify success, +4 new tests |

## Key Behavior Change

```text
BEFORE: non-last selected candidate → fail-closed (COMMITTEE_SELECTED_NON_APPLIED_CANDIDATE_UNSUPPORTED)
AFTER:  non-last selected candidate → re-apply from proposals[attempt_idx]["artifacts"][0]
```

## selected_candidate_reapply_mode Values

| Mode | Meaning |
|------|---------|
| `last_candidate_existing_path` | Last candidate selected (unchanged path) |
| `non_last_candidate_reapplied` | Non-last candidate selected, re-applied |
| `missing_artifact` | Selected candidate artifact empty → fail-closed |
| `missing_mapping` | Candidate mapping failed → fail-closed |
| `hash_mismatch` | Hash mismatch after apply → fail-closed |

## Fail-Closed Paths

| Failure | Reason |
|---------|--------|
| Missing mapping | COMMITTEE_WINNER_CANDIDATE_MAPPING_MISSING |
| Empty artifact | COMMITTEE_SELECTED_CANDIDATE_ARTIFACT_MISSING |
| Hash mismatch | COMMITTEE_SELECTED_CANDIDATE_APPLY_HASH_MISMATCH |

## Compile & Test

```
python3 -m py_compile nexus/services/local_heal/committee_orchestrator.py tests/unit/local_heal/test_committee_route_trace.py
→ OK

pytest tests/unit/local_heal/test_committee_route_trace.py -v
→ 15 passed

pytest tests/unit/local_heal/test_native_route_adapter.py tests/unit/local_heal/test_role_contract.py -q
→ 21 passed
```

## Tests

| Test | Verifies |
|------|----------|
| `test_committee_non_last_selected_candidate_reapplies` | candidate 1 selected, re-applied, solve_eligible=true |
| `test_committee_non_selected_candidate_remains_unapplied` | candidate 2 selected, last path, reapply_mode=last_candidate_existing_path |
| `test_committee_isolation_preserved_in_non_last_reapply` | isolation fields preserved in non-last re-apply |
| `test_committee_hash_mismatch_fail_closes` | hash mismatch fail-closed on last candidate |
| `test_committee_hash_mismatch_after_non_last_reapply` | hash mismatch fail-closed on non-last candidate |
| `test_committee_missing_artifact_fail_closes` | empty artifact → fail-closed |
| `test_committee_missing_mapping_includes_reapply_mode` | missing mapping → reapply_mode=missing_mapping |
| `test_committee_receipt_persists_reapply_fields` | all reapply fields persist through receipt |

## Remaining Requirements

```text
U3 still requires focused gate and smoke before H5.
No real model calls.
No benchmark.
```

## What U3-3C Does NOT Do

```text
No H5 / local-first / local-only
No production_ready / public_claim_allowed
```
