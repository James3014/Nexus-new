# H5-34 Controlled Actual Final Source Apply Gate Report

**日期**: 2026-06-23
**狀態**: `H5_34_CONTROLLED_ACTUAL_FINAL_SOURCE_APPLY_GATE_PASS`
**Commit**: pending
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +2 pure helpers (decision + apply), +1 integration in `_finalize_with_nexus_row`, +8 summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +10 H5-34 tests |

## Commands Run

```text
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
→ OK

pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5" -q
→ 184 passed

pytest tests/benchmark/test_h5_local_committee_e2e_smoke.py tests/benchmark/test_h5_cloud_fallback_e2e_smoke.py -q
→ 56 passed

pytest tests/benchmark/test_capability_ab_runner.py -k "h5_34" -v
→ 10 passed (default env)

NEXUS_H5_ENABLE_CONTROLLED_EXECUTION=1 NEXUS_H5_ALLOW_LOCAL_FINALIZATION=1 \
  NEXUS_H5_ALLOW_FINAL_SOURCE_CHANGE=1 NEXUS_H5_ALLOW_FINAL_PATCH_REPLACEMENT=1 \
  NEXUS_H5_ALLOW_OUTPUT_MUTATION=1 NEXUS_H5_ALLOW_FINAL_SOURCE_APPLY_PREFLIGHT=1 \
  NEXUS_H5_ALLOW_ACTUAL_FINAL_SOURCE_APPLY=1 \
  pytest tests/benchmark/test_capability_ab_runner.py -k "h5_34" -v
→ 10 passed (all-seven-flags)
```

## Test Counts

| Suite | Count |
|-------|-------|
| H5 selector | 184 |
| Local smoke | 38 |
| Cloud smoke | 18 |
| H5-34 default env | 10 |
| H5-34 all-seven-flags | 10 |
| **Total** | **260** |

## Schemas

### Apply Decision

```json
{
  "schema": "nexus.hybrid_h5_actual_final_source_apply_decision.v1",
  "evaluated": true,
  "apply_decision": "blocked",
  "apply_reasons": [],
  "actual_apply_allowed": false,
  "apply_target_final_source": "local_candidate_shadow_promoted",
  "actual_final_source_before": "none",
  "would_change_final_source_to": "none",
  "all_seven_flags_enabled": false,
  "preflight_pass_shadow_only": false,
  "isolated_simulation_pass": false,
  "rollback_available": false,
  "rollback_required": false,
  "safe_to_continue": true,
  "final_patch_replacement_allowed": false,
  "output_mutation_allowed": false,
  "model_calls_increment_allowed": false,
  "public_claim_allowed": false,
  "production_ready": false
}
```

### Apply Receipt

```json
{
  "schema": "nexus.hybrid_h5_actual_final_source_apply_receipt.v1",
  "evaluated": true,
  "actual_apply_executed": false,
  "actual_final_source_before": "none",
  "actual_final_source_after": "none",
  "actual_final_source_changed": false,
  "apply_decision": "blocked",
  "apply_target_final_source": "local_candidate_shadow_promoted",
  "final_patch_replaced": false,
  "output_mutated": false,
  "model_calls_incremented": false,
  "cloud_invoked": false,
  "behavior_changed": false,
  "rollback_available": false,
  "rollback_required": false,
  "safe_to_continue": true,
  "public_claim_allowed": false,
  "production_ready": false
}
```

## All Seven Flags

| # | Flag | Env Variable |
|---|------|-------------|
| 1 | Controlled execution | `NEXUS_H5_ENABLE_CONTROLLED_EXECUTION` |
| 2 | Local finalization | `NEXUS_H5_ALLOW_LOCAL_FINALIZATION` |
| 3 | Final source change | `NEXUS_H5_ALLOW_FINAL_SOURCE_CHANGE` |
| 4 | Final patch replacement | `NEXUS_H5_ALLOW_FINAL_PATCH_REPLACEMENT` |
| 5 | Output mutation | `NEXUS_H5_ALLOW_OUTPUT_MUTATION` |
| 6 | Final source apply preflight | `NEXUS_H5_ALLOW_FINAL_SOURCE_APPLY_PREFLIGHT` |
| 7 | Actual final source apply | `NEXUS_H5_ALLOW_ACTUAL_FINAL_SOURCE_APPLY` |

All seven flags must be exactly "1" plus all preflight/simulation/rollback conditions satisfied for `actual_apply_allowed=true`.

## Default-Env Result

- `actual_apply_allowed=false`
- `final_source` remains `"none"`
- All safety fields unchanged

## All-Seven-Flags Trial Result

When all seven flags are enabled and all prior receipts pass:
- `actual_apply_allowed=true`
- `apply_decision="apply_final_source_only"`
- `final_source` may become `"local_candidate_shadow_promoted"`
- `final_patch` unchanged
- `output` unchanged
- `model_calls` not incremented
- `behavior_changed=false`
- `cloud_fallback_invoked=false`

## Proofs

- **default env final_source remains none**: Without all seven flags, `actual_apply_allowed=false`, `final_source` stays `"none"`.
- **all-seven-flags may set final_source**: `actual_apply_allowed=true` → `final_source="local_candidate_shadow_promoted"` via `_apply_h5_actual_final_source_if_allowed` shallow copy. Original row not mutated.
- **final_patch is not replaced**: `final_patch_replaced=false` always.
- **output is not mutated**: `output_mutated=false` always.
- **model_calls is not incremented**: `model_calls_incremented=false` always.
- **behavior_changed remains false**: Always false.
- **cloud_fallback_invoked remains false**: Always false.

## Summary Counters

```text
h5_actual_final_source_apply_decision_count
h5_actual_final_source_apply_allowed_count
h5_actual_final_source_apply_blocked_count
h5_actual_final_source_apply_executed_count
h5_actual_final_source_apply_final_source_changed_count
h5_actual_final_source_apply_all_flags_enabled_count
h5_actual_final_source_apply_rollback_required_count
h5_actual_final_source_apply_safe_count
```

## Statements

```text
Controlled actual final_source apply gate only.
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
