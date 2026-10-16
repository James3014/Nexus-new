# U3-5 Tiny Local Committee Smoke Report

**日期**: 2026-06-22
**狀態**: `U3_5_TINY_LOCAL_COMMITTEE_SMOKE_PASS`
**Commit**: pending
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Commands Run

```text
python3 -m py_compile tests/unit/local_heal/test_committee_route_trace.py
→ OK

pytest tests/unit/local_heal/test_committee_route_trace.py -v
→ 17 passed

pytest tests/unit/local_heal/test_native_route_adapter.py tests/unit/local_heal/test_role_contract.py -q
→ 21 passed
```

## Test Counts

| Suite | Count |
|-------|-------|
| test_committee_route_trace.py | 17 passed |
| test_native_route_adapter.py | 3 passed |
| test_role_contract.py | 18 passed |
| **Total** | **38 passed** |

## Smoke Approach

**Stubs, not real model calls.** Uses `_CommitteeControllerStub` and `_PatchPhase` to drive `CommitteeOrchestrator.run()` with `NEXUS_USE_COMMITTEE=1`, then calls `build_repair_receipt(ctx)`.

## Smoke Assertions Verified

| # | Assertion | Result |
|---|-----------|--------|
| 1 | NEXUS_USE_COMMITTEE=1 set | PASS |
| 2 | Committee route invoked (receipt has telemetries.committee) | PASS |
| 3 | committee.schema == "nexus.local_heal.committee_trace.v1" | PASS |
| 4 | committee.enabled == true | PASS |
| 5 | candidate_count >= 1 | PASS |
| 6 | Each candidate has candidate_id, isolation_status, isolated_patch_sha256, isolated_patch_length | PASS |
| 7 | Each candidate has selected, applied, worktree_applied | PASS |
| 8 | judge_selection.selected_candidate_id exists | PASS |
| 9 | committee_receipt.selected_candidate_id exists | PASS |
| 10 | selected_candidate_apply_supported is true | PASS |
| 11 | selected_candidate_applied is true | PASS |
| 12 | selected_candidate_patch_sha256 exists | PASS |
| 13 | applied_patch_sha256 exists | PASS |
| 14 | selected_candidate_apply_hash_match is true | PASS |
| 15 | selected_candidate_reapply_mode is valid | PASS |
| 16 | public_claim_allowed=false, production_ready=false | PASS |

## Statements

```text
No Gemini/Codex calls.
No full benchmark.
This is not H5.
This is not local-first / local-only.
public_claim_allowed=false.
production_ready=false.
```

## Remaining Requirement Before H5

```text
Define H5 route semantics and fallback gates.
```
