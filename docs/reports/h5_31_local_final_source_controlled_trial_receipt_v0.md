# H5-31 Local Final Source Controlled Trial Receipt Report

**日期**: 2026-06-23
**狀態**: `H5_31_LOCAL_FINAL_SOURCE_CONTROLLED_TRIAL_RECEIPT_PASS`
**Commit**: pending
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +1 pure helper (`_build_h5_local_final_source_controlled_trial_receipt`), +1 attachment in `_finalize_with_nexus_row`, +7 summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +8 H5-31 tests |

## Commands Run

```text
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
→ OK

pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5" -q
→ 156 passed

pytest tests/benchmark/test_h5_local_committee_e2e_smoke.py tests/benchmark/test_h5_cloud_fallback_e2e_smoke.py -q
→ 56 passed

NEXUS_H5_ENABLE_CONTROLLED_EXECUTION=1 NEXUS_H5_ALLOW_LOCAL_FINALIZATION=1 \
  NEXUS_H5_ALLOW_FINAL_SOURCE_CHANGE=1 NEXUS_H5_ALLOW_FINAL_PATCH_REPLACEMENT=1 \
  NEXUS_H5_ALLOW_OUTPUT_MUTATION=1 \
  pytest tests/benchmark/test_capability_ab_runner.py -k "h5_31" -v
→ 8 passed
```

## Test Counts

| Suite | Count |
|-------|-------|
| H5 selector | 156 |
| Local smoke | 38 |
| Cloud smoke | 18 |
| H5-31 all-flags controlled trial | 8 |
| **Total** | **220** |

## Schema

```json
{
  "schema": "nexus.hybrid_h5_local_final_source_controlled_trial_receipt.v1",
  "evaluated": true,
  "trial_status": "blocked",
  "trial_reasons": [],
  "would_allow_final_source_trial": false,
  "actual_final_source_before": "none",
  "actual_final_source_after": "none",
  "actual_final_source_changed": false,
  "shadow_final_source_after_promotion": "none",
  "trial_final_source_after_promotion": "none",
  "controlled_mutation_gate_present": false,
  "controlled_mutation_gate_blocked": true,
  "all_required_flags_enabled": false,
  "mutation_allowed": false,
  "safe_to_continue": true,
  "rollback_required": false,
  "local_evidence_ready": false,
  "cloud_evidence_ready": false,
  "all_shadow_evidence_present": false,
  "promotion_dry_run_would_promote": false,
  "shadow_final_source_candidate": false,
  "final_patch_replacement_allowed": false,
  "output_mutation_allowed": false,
  "model_calls_increment_allowed": false,
  "public_claim_allowed": false,
  "production_ready": false
}
```

## Trial Readiness Rules

`would_allow_final_source_trial=true` only when ALL conditions hold:

1. Controlled mutation gate exists
2. `all_required_flags_enabled=true`
3. `safe_to_continue=true`
4. `rollback_required=false`
5. Shadow final_source promotion candidate exists
6. `shadow_final_source_after_promotion="local_candidate_shadow_promoted"`
7. Promotion dry-run would promote
8. Local evidence ready
9. Cloud evidence ready
10. All shadow evidence present

Even when `would_allow_final_source_trial=true`:
- `trial_status="trial_ready_blocked"` (never "trial_ready")
- `actual_final_source_after="none"`
- `actual_final_source_changed=false`
- `mutation_allowed=false`

## All-Five-Flags Controlled Trial

| Field | Result |
|-------|--------|
| `would_allow_final_source_trial` | depends on full evidence chain |
| `actual_final_source_after` | "none" |
| `actual_final_source_changed` | false |
| `mutation_allowed` | false |
| `final_patch_replacement_allowed` | false |
| `output_mutation_allowed` | false |
| `model_calls_increment_allowed` | false |

## Proofs

- **actual final_source remains none**: `actual_final_source_before = actual_final_source_after = "none"` in all paths.
- **trial_final_source_after_promotion can be local_candidate_shadow_promoted only as receipt metadata**: Records what WOULD happen in a future controlled execution. Actual final_source stays "none".
- **mutation_allowed remains false**: Always false. Even when trial receipt says `would_allow_final_source_trial=true`, no mutation is allowed.
- **actual final_patch is not replaced**: `final_patch_replacement_allowed=false` always.
- **actual output is not mutated**: `output_mutation_allowed=false` always.
- **model_calls is not incremented**: `model_calls_increment_allowed=false` always.

## Summary Counters

```text
h5_local_final_source_trial_receipt_count
h5_local_final_source_trial_ready_count
h5_local_final_source_trial_blocked_count
h5_local_final_source_trial_actual_change_count
h5_local_final_source_trial_flags_enabled_count
h5_local_final_source_trial_safe_count
h5_local_final_source_trial_rollback_required_count
```

Expected:
- `h5_local_final_source_trial_actual_change_count == 0`
- `h5_local_final_source_trial_rollback_required_count == 0`
- `h5_controlled_mutation_allowed_count == 0`
- `h5_execution_allowed_count == 0`
- `h5_behavior_changed_count == 0`
- `h5_cloud_fallback_invoked_count == 0`
- `h5_actual_final_patch_replaced_count == 0`
- `h5_actual_output_mutated_count == 0`

## Statements

```text
Local final_source controlled trial receipt only.
No H5 execution enabled.
No real local-first execution.
No cloud fallback execution.
No local committee invocation from benchmark runner.
No cloud provider invocation from benchmark runner.
No local candidate finalization.
No actual final_source change.
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
