# H5-29 Final Patch Replacement Shadow Contract + Output Mutation Guard Report

**日期**: 2026-06-23
**狀態**: `H5_29_FINAL_PATCH_REPLACEMENT_SHADOW_CONTRACT_OUTPUT_GUARD_PASS`
**Commit**: pending
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +2 pure helpers (final_patch shadow contract, output mutation guard), +2 attachments in `_finalize_with_nexus_row`, +9 summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +9 H5-29 tests |

## Commands Run

```text
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
→ OK

pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5" -q
→ 139 passed

pytest tests/benchmark/test_h5_local_committee_e2e_smoke.py -q
→ 38 passed

pytest tests/benchmark/test_h5_cloud_fallback_e2e_smoke.py -q
→ 18 passed

NEXUS_H5_ENABLE_CONTROLLED_EXECUTION=1 NEXUS_H5_ALLOW_LOCAL_FINALIZATION=1 \
  NEXUS_H5_ALLOW_FINAL_SOURCE_CHANGE=1 NEXUS_H5_ALLOW_FINAL_PATCH_REPLACEMENT=1 \
  pytest tests/benchmark/test_capability_ab_runner.py -k "h5_29" -q
→ 9 passed
```

## Test Counts

| Suite | Count |
|-------|-------|
| H5 selector | 139 |
| Local smoke | 38 |
| Cloud smoke | 18 |
| H5-29 all-flags controlled trial | 9 |
| **Total** | **204** |

## Schemas

### Final Patch Replacement Shadow Contract

```json
{
  "schema": "nexus.hybrid_h5_final_patch_replacement_shadow_contract.v1",
  "evaluated": true,
  "shadow_patch_candidate": false,
  "shadow_patch_status": "blocked",
  "shadow_patch_reasons": [],
  "selected_candidate_id": "",
  "selected_candidate_patch_sha256": "",
  "selected_candidate_patch_length": 0,
  "selected_candidate_hash_verified": false,
  "actual_final_patch_present_before": false,
  "actual_final_patch_present_after": false,
  "actual_final_patch_replaced": false,
  "shadow_final_patch_replacement_would_occur": false,
  "final_patch_replacement_allowed": false,
  "promotion_allowed": false,
  "shadow_final_source_after_promotion": "none",
  "actual_final_source_after": "none",
  "rollback_available": false,
  "rollback_required": false,
  "public_claim_allowed": false,
  "production_ready": false
}
```

### Output Mutation Guard

```json
{
  "schema": "nexus.hybrid_h5_output_mutation_guard.v1",
  "evaluated": true,
  "output_mutation_candidate": false,
  "output_mutation_status": "blocked",
  "output_mutation_reasons": [],
  "shadow_patch_candidate": false,
  "shadow_final_patch_replacement_would_occur": false,
  "actual_output_mutated": false,
  "output_mutation_allowed": false,
  "actual_final_source_changed": false,
  "actual_final_patch_replaced": false,
  "model_calls_incremented": false,
  "safe_to_continue": true,
  "rollback_required": false,
  "public_claim_allowed": false,
  "production_ready": false
}
```

## Shadow Patch Candidate Rules

1. `shadow_patch_candidate=true` only when:
   - Shadow final_source promotion candidate exists (`shadow_promotion_candidate=true`)
   - `shadow_final_source_after_promotion == "local_candidate_shadow_promoted"`
   - `selected_candidate_patch_sha256` is present
   - `selected_candidate_patch_length > 0`
   - `selected_candidate_hash_verified=true`
   - `rollback_available=true`
2. If `shadow_patch_candidate=true`:
   - `shadow_final_patch_replacement_would_occur=true`
   - `shadow_patch_status="shadow_ready_blocked"`
3. Even if `shadow_patch_candidate=true`:
   - `actual_final_patch_present_after == actual_final_patch_present_before`
   - `actual_final_patch_replaced=false`
   - `final_patch_replacement_allowed=false`

## Output Mutation Guard Rules

1. `actual_output_mutated=false` always in H5-29 normal rows.
2. `output_mutation_allowed=false` always.
3. `output_mutation_candidate=true` only if:
   - Final patch replacement shadow contract has `shadow_patch_candidate=true`
   - `shadow_final_patch_replacement_would_occur=true`
4. If unexpected mutation detected (`actual_output_mutated`, `actual_final_source_changed`, `actual_final_patch_replaced`, or `model_calls_incremented`):
   - `safe_to_continue=false`
   - `rollback_required=true`

## All-Four-Flags Controlled Trial

| Field | Result |
|-------|--------|
| `final_source` (row-level) | "none" |
| `behavior_changed` | false |
| `actual_final_source_changed` | false |
| `actual_final_patch_replaced` | false |
| `final_patch_replacement_allowed` | false |
| `actual_output_mutated` | false |
| `output_mutation_allowed` | false |
| `h5_local_candidate_promotion_dry_run.promotion_allowed` | false |

## Proofs

- **actual final_source remains none**: Row-level `final_source="none"` unchanged. `actual_final_source_changed=false` in normal rows.
- **actual final_patch is not replaced**: `actual_final_patch_replaced=false` always. `final_patch_replacement_allowed=false` always. `actual_final_patch_present_after == actual_final_patch_present_before`.
- **shadow_final_patch_replacement_would_occur can be true only as metadata**: When `shadow_patch_candidate=true`, `shadow_final_patch_replacement_would_occur=true` records what WOULD happen. Actual final_patch is unchanged.
- **output is not mutated**: `actual_output_mutated=false` always. `output_mutation_allowed=false` always.
- **model_calls is not incremented**: `model_calls_incremented=false` always. `model_calls_increment_would_occur=false`.

## Summary Counters

```text
h5_final_patch_replacement_shadow_contract_count
h5_final_patch_shadow_candidate_count
h5_final_patch_replacement_allowed_count
h5_actual_final_patch_replaced_count
h5_output_mutation_guard_count
h5_output_mutation_candidate_count
h5_output_mutation_allowed_count
h5_actual_output_mutated_count
h5_output_mutation_rollback_required_count
```

Expected:
- `h5_final_patch_replacement_allowed_count == 0`
- `h5_actual_final_patch_replaced_count == 0`
- `h5_output_mutation_allowed_count == 0`
- `h5_actual_output_mutated_count == 0`
- `h5_output_mutation_rollback_required_count == 0`
- `h5_execution_allowed_count == 0`
- `h5_behavior_changed_count == 0`
- `h5_cloud_fallback_invoked_count == 0`

## Statements

```text
Final patch replacement shadow contract only.
Output mutation guard only.
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
