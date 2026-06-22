# H5-4 Cloud Fallback Decision Dry-run Report

**日期**: 2026-06-22
**狀態**: `H5_4_CLOUD_FALLBACK_DECISION_DRY_RUN_PASS`
**Commit**: pending
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +H5-4 decision logic after H5-3 eligibility, +4 new summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +6 H5-4 tests, +shared `_h5_flags_set` helper |

## Commands Run

```text
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
→ OK

pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5" -q
→ 27 passed, 346 deselected
```

## Decision Rules Implemented

| # | Condition | cloud_fallback_decision | would_invoke |
|---|-----------|------------------------|-------------|
| 1 | H5-4 flag disabled | not_evaluated (absent) | false |
| 2 | cloud_fallback_eligible=true | would_invoke_cloud_fallback | true |
| 3 | local_success_no_fallback | skip_cloud_fallback | false |
| 4 | fail_closed_reason != "" | would_fail_closed | false |
| 5 | local_trace_missing | would_fail_closed | false |

## New Env Flag

```text
NEXUS_HYBRID_H5_FALLBACK_DECISION_DRY_RUN=1
```

## New h5_route Fields

```text
cloud_fallback_decision
cloud_fallback_decision_reason
cloud_fallback_would_invoke
cloud_fallback_provider
cloud_fallback_execution_mode
fallback_decision_policy_version
```

## New Summary Counters

```text
h5_fallback_decision_trace_count
h5_cloud_fallback_would_invoke_count
h5_would_fail_closed_decision_count
h5_skip_cloud_fallback_decision_count
```

## Statements

```text
Decision dry-run only.
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
