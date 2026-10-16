# U3-4 Committee Candidate Isolation Gate Report

**日期**: 2026-06-22
**狀態**: `U3_4_COMMITTEE_CANDIDATE_ISOLATION_GATE_PASS`
**Commit**: pending
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Commands Run

```text
python3 -m py_compile nexus/services/local_heal/committee_orchestrator.py nexus/services/local_heal/receipt.py tests/unit/local_heal/test_committee_route_trace.py
→ OK

pytest tests/unit/local_heal/test_committee_route_trace.py -v
→ 16 passed

pytest tests/unit/local_heal/test_native_route_adapter.py tests/unit/local_heal/test_role_contract.py -q
→ 21 passed
```

## Test Counts

| Suite | Count |
|-------|-------|
| test_committee_route_trace.py | 16 passed |
| test_native_route_adapter.py | 3 passed |
| test_role_contract.py | 18 passed |
| **Total** | **37 passed** |

## Gate Test

`test_committee_candidate_isolation_gate_covers_identity_reapply_hash_and_receipt` — single focused gate covering all 8 contracts.

## Covered Contracts

| # | Contract | Status |
|---|----------|--------|
| 1 | Candidate identity (candidate_id deterministic, candidate_key legacy) | PASS |
| 2 | Candidate isolation (isolation_status, isolated_patch_sha256/length, isolation_store) | PASS |
| 3 | Candidate 1 selected (non-last re-apply, selected/applied/worktree_applied, reapply_mode, hash_match) | PASS |
| 4 | Candidate 2 selected (last existing path, selected/applied/worktree_applied, reapply_mode, hash_match) | PASS |
| 5 | Missing mapping (fail-closed, reapply_mode, all candidates false) | PASS |
| 6 | Missing artifact (fail-closed, reapply_mode, hash_match false) | PASS |
| 7 | Hash mismatch (fail-closed, reapply_mode, hash_match false) | PASS |
| 8 | Receipt persistence (all fields preserved through build_repair_receipt) | PASS |

## Statements

```text
This is a focused unit gate, not a real model smoke.
This is not H5.
This is not local-first / local-only.
public_claim_allowed=false remains unchanged.
production_ready=false remains unchanged.
```
