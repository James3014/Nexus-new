# H5-2 Local Attempt Dry-run Trace Report

**日期**: 2026-06-22
**狀態**: `H5_2_LOCAL_ATTEMPT_DRY_RUN_TRACE_PASS`
**Commit**: pending
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | Extended H5 block to read `committee_trace` from row and copy fields into h5_route when dry-run flag enabled |
| `tests/benchmark/test_capability_ab_runner.py` | +5 H5-2 tests |

## Commands Run

```text
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
→ OK

pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5" -q
→ 14 passed, 346 deselected
```

## Fields Copied from Committee Trace

| h5_route field | Source |
|----------------|--------|
| `local_candidate_count` | `committee_trace.candidate_count` |
| `local_selected_candidate_id` | `committee_trace.judge_selection.selected_candidate_id` |
| `local_selected_candidate_applied` | `committee_trace.committee_receipt.selected_candidate_applied` |
| `local_selected_candidate_hash_match` | `committee_trace.committee_receipt.selected_candidate_apply_hash_match` |
| `local_solve_eligible` | `row.local_solve_eligible` |
| `local_failure_reason` | `committee_receipt.failure_reason` or `row.failure_reason` or `"local_trace_missing"` |
| `route_mode` | `"local_first_cloud_fallback_local_attempted"` when trace present |

## Env Flags

```text
NEXUS_HYBRID_H5_LOCAL_FIRST_TRACE=1      — enables base h5_route metadata
NEXUS_HYBRID_H5_LOCAL_DRY_RUN_TRACE=1    — enables copying precomputed committee trace
```

## Statements

```text
Dry-run trace only.
No local committee invocation by benchmark runner.
No cloud fallback execution.
No final delivery source change.
No real model calls.
No benchmark.
Not H5 ready.
Not local-first ready.
Not local-only ready.
public_claim_allowed=false.
production_ready=false.
```
