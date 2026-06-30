# U3-0 Preflight Audit Report

**日期**: 2026-06-22
**狀態**: `U3_0_PREFLIGHT_AUDIT_COMPLETE`
**治理**: `public_claim_allowed=false`, `production_ready=false`

---

## Scope

Read-only inspection of candidate identity, isolation, judge selection, and selected-candidate re-apply in the current U3 committee route. No code changes.

## Compile & Test

```
python3 -m py_compile nexus/services/local_heal/committee_orchestrator.py nexus/services/local_heal/receipt.py tests/unit/local_heal/test_committee_route_trace.py
→ OK

pytest tests/unit/local_heal/test_committee_route_trace.py tests/unit/local_heal/test_native_route_adapter.py tests/unit/local_heal/test_role_contract.py -q
→ 24 passed
```

## 7 Questions Answered

### Q1: candidate_key format

`{instance_id}#proposer-{N}` (N=1-indexed). Source: `committee_orchestrator.py:84`.

### Q2: winner_id format

`{task_id}-{model}-{attempt}-{hash_suffix}`. Source: test stub `test_committee_route_trace.py:58`.

### Q3: Judge selection → candidate mapping

Iterates `candidate_snapshots`, checks `winner_id.startswith(f"{instance_id}-{model}-{attempt}-")`. Fragile — depends on `CommitteeControllerV263` generating `winner_id` in expected format.

### Q4: Selected candidate re-apply

**Partial — only works if last candidate wins.** Non-last winner → fail-closed with `COMMITTEE_SELECTED_NON_APPLIED_CANDIDATE_UNSUPPORTED`. No worktree restore mechanism.

### Q5: selected_candidate_hash == applied_patch_hash

**No.** Neither hash is computed or compared. `patch_sha256` is stored in trace only.

### Q6: Mismatch handling

Existing fail-closed: "winner is not last candidate" → reject. **Missing**: hash mismatch detection (`COMMITTEE_SELECTED_CANDIDATE_APPLY_HASH_MISMATCH` does not exist).

### Q7: Files needing changes

| File | Change | Priority |
|------|--------|----------|
| `committee_orchestrator.py` | Isolation store, hash computation, hash comparison, non-last re-apply | P0 |
| `receipt.py` | Add hash fields to committee trace | P1 |
| `test_committee_route_trace.py` | New tests for isolation, both judge directions, hash mismatch | P0 |

## Gap Summary

| Requirement | Current | Gap |
|-------------|---------|-----|
| Stable candidate_id | `candidate_key` exists but unused | Not connected to judge |
| Candidate isolation | In-place mutation | No isolation store |
| Hash comparison | Not implemented | **Missing** |
| Non-last re-apply | Fail-closed reject | No worktree restore |

## Full Audit

`docs/reports/u3_candidate_isolation_preflight_audit_v0.md`
