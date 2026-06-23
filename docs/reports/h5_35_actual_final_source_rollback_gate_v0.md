# H5-35 Actual Final Source Rollback Gate Report

**日期**: 2026-06-23
**狀態**: `H5_35_ACTUAL_FINAL_SOURCE_ROLLBACK_GATE_PASS`
**Commit**: pending
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +2 pure helpers (rollback decision + rollback apply), +1 integration in `_finalize_with_nexus_row`, +7 summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +10 H5-35 tests |

## Commands Run

```text
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
→ OK

pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5" -q
→ 194 passed

pytest tests/benchmark/test_h5_local_committee_e2e_smoke.py tests/benchmark/test_h5_cloud_fallback_e2e_smoke.py -q
→ 56 passed

pytest tests/benchmark/test_capability_ab_runner.py -k "h5_35" -q
→ 10 passed (default env)

NEXUS_H5_ENABLE_CONTROLLED_EXECUTION=1 ... NEXUS_H5_ALLOW_ACTUAL_FINAL_SOURCE_ROLLBACK=1 \
  pytest tests/benchmark/test_capability_ab_runner.py -k "h5_35" -q
→ 10 passed (all-eight-flags)
```

## Test Counts

| Suite | Count |
|-------|-------|
| H5 selector | 194 |
| Local smoke | 38 |
| Cloud smoke | 18 |
| H5-35 default env | 10 |
| H5-35 all-eight-flags | 10 |
| **Total** | **270** |

## Schemas

### Rollback Decision

```json
{
  "schema": "nexus.hybrid_h5_actual_final_source_rollback_decision.v1",
  "evaluated": true,
  "rollback_decision": "blocked",
  "rollback_reasons": [],
  "rollback_allowed": false,
  "rollback_target_final_source": "none",
  "actual_final_source_before_rollback": "none",
  "would_restore_final_source_to": "none",
  "actual_apply_receipt_present": false,
  "actual_apply_executed": false,
  "rollback_flag_enabled": false,
  "rollback_required": false,
  "rollback_safe": true,
  "final_patch_replaced": false,
  "output_mutated": false,
  "model_calls_incremented": false,
  "cloud_invoked": false,
  "behavior_changed": false,
  "public_claim_allowed": false,
  "production_ready": false
}
```

### Rollback Receipt

```json
{
  "schema": "nexus.hybrid_h5_actual_final_source_rollback_receipt.v1",
  "evaluated": true,
  "rollback_executed": false,
  "actual_final_source_before_rollback": "none",
  "actual_final_source_after_rollback": "none",
  "actual_final_source_restored": false,
  "rollback_decision": "blocked",
  "rollback_target_final_source": "none",
  "final_patch_replaced": false,
  "output_mutated": false,
  "model_calls_incremented": false,
  "cloud_invoked": false,
  "behavior_changed": false,
  "safe_to_continue": true,
  "public_claim_allowed": false,
  "production_ready": false
}
```

## Eight Flags

All seven H5-34 flags plus `NEXUS_H5_ALLOW_ACTUAL_FINAL_SOURCE_ROLLBACK=1`.

## Default-Env Result

- `rollback_allowed=false`
- `rollback_executed=false`
- `final_source` remains `"none"`

## All-Eight-Flags Rollback Trial

When all flags enabled and H5-34 apply executes:
1. H5-34 applies: `final_source` → `"local_candidate_shadow_promoted"`
2. H5-35 rolls back: `final_source` → `"none"`
3. `rollback_executed=true`, `actual_final_source_restored=true`
4. `final_patch` unchanged, `output` unchanged, `model_calls` unchanged, `behavior_changed=false`, `cloud_fallback_invoked=false`

## Proofs

- **default env final_source remains none**: Without rollback flag, `rollback_allowed=false`, no restore occurs.
- **all-eight-flags apply then rollback**: H5-34 sets `final_source="local_candidate_shadow_promoted"`, H5-35 restores to `"none"`. `actual_final_source_restored=true`.
- **final_patch is not replaced**: `final_patch_replaced=false` always.
- **output is not mutated**: `output_mutated=false` always.
- **model_calls is not incremented**: `model_calls_incremented=false` always.
- **behavior_changed remains false**: Always false.
- **cloud_fallback_invoked remains false**: Always false.

## Summary Counters

```text
h5_actual_final_source_rollback_decision_count
h5_actual_final_source_rollback_allowed_count
h5_actual_final_source_rollback_blocked_count
h5_actual_final_source_rollback_executed_count
h5_actual_final_source_rollback_restored_count
h5_actual_final_source_rollback_flag_enabled_count
h5_actual_final_source_rollback_safe_count
```

## Statements

```text
Actual final_source rollback gate only.
No full H5 execution enabled.
No real local-first execution.
No cloud fallback execution.
No local committee invocation from benchmark runner.
No cloud provider invocation from benchmark runner.
No local candidate final_patch finalization.
No actual final_patch replacement.
No model_calls increment.
No output mutation.
No full benchmark.
Not H5 ready.
Not local-first ready.
Not cloud fallback ready.
Not local-only ready.
public_claim_allowed=false.
production_ready=false.
```
