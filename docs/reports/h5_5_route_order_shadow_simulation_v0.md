# H5-5 Route-order Shadow Simulation Report

**日期**: 2026-06-22
**狀態**: `H5_5_ROUTE_ORDER_SHADOW_SIMULATION_PASS`
**Commit**: pending
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +H5-5 shadow simulation logic after H5-4, +5 new summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +6 H5-5 tests, +shared `_h5_all_flags_set` helper |

## Commands Run

```text
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
→ OK

pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5" -q
→ 33 passed, 346 deselected
```

## Shadow States Implemented

| State | Sequence | Terminal |
|-------|----------|----------|
| Local success | `["local_committee"]` | `would_use_local_candidate` |
| Cloud fallback eligible | `["local_committee", "cloud_fallback"]` | `would_use_cloud_fallback` |
| Would fail closed | `["local_committee"]` | `would_fail_closed` |
| Skip cloud fallback | `["local_committee"]` | `would_use_local_candidate` |
| Missing local trace | `[]` | `not_evaluated` |
| No decision available | `[]` | `not_evaluated` |

## New Env Flag

```text
NEXUS_HYBRID_H5_ROUTE_ORDER_SHADOW=1
```

## New h5_route Fields

```text
route_order_shadow_enabled
route_order_shadow_sequence
route_order_shadow_terminal_state
route_order_shadow_reason
route_order_shadow_policy_version
route_order_shadow_behavior_changed
```

## New Summary Counters

```text
h5_route_order_shadow_count
h5_shadow_would_use_local_candidate_count
h5_shadow_would_use_cloud_fallback_count
h5_shadow_would_fail_closed_count
h5_shadow_behavior_changed_count
```

## Statements

```text
Route-order shadow simulation only.
No actual route order change.
No cloud fallback execution.
No local committee invocation by benchmark runner.
No final delivery source change.
No output mutation.
No real model calls.
No benchmark.
Not H5 ready.
Not local-first ready.
Not local-only ready.
public_claim_allowed=false.
production_ready=false.
```
