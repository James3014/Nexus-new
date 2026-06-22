# H5-3 Cloud Fallback Eligibility Trace Report

**日期**: 2026-06-22
**狀態**: `H5_3_CLOUD_FALLBACK_ELIGIBILITY_TRACE_PASS`
**Commit**: pending
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +H5-3 eligibility logic in H5 block, +3 new summary counters, fixed failure_reason propagation |
| `tests/benchmark/test_capability_ab_runner.py` | +7 H5-3 tests |

## Commands Run

```text
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
→ OK

pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5" -q
→ 21 passed, 346 deselected
```

## Fallback Eligibility Rules Implemented

| # | Trigger | cloud_fallback_eligible | fail_closed_reason |
|---|---------|------------------------|-------------------|
| 1 | Local success | false | "" |
| 2 | Verifier rejected | true (if cloud ok) | "" |
| 3 | Local infra unavailable | true (if cloud ok) | "" |
| 4 | Local timeout | true (if cloud ok) | "" |
| 5 | Missing candidate mapping | false | local_missing_candidate_mapping |
| 6 | Missing artifact | false | local_missing_artifact |
| 7 | Hash mismatch | false | local_hash_mismatch |
| 8 | Local trace missing | false | local_trace_missing |
| 9 | Cloud provider unavailable | false | cloud_provider_unavailable |

## New Env Flag

```text
NEXUS_HYBRID_H5_FALLBACK_ELIGIBILITY_TRACE=1
```

## New Summary Counters

```text
h5_cloud_fallback_eligible_count
h5_fallback_eligibility_trace_count
h5_would_fail_closed_count
```

## Statements

```text
Eligibility trace only.
No cloud fallback execution.
No final delivery source change.
No route order change.
No real model calls.
No benchmark.
Not H5 ready.
Not local-first ready.
Not local-only ready.
public_claim_allowed=false.
production_ready=false.
```
