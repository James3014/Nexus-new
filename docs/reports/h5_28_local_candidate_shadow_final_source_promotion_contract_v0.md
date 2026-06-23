# H5-28 Local Candidate Shadow Final Source Promotion Contract Report

**日期**: 2026-06-23
**狀態**: `H5_28_LOCAL_CANDIDATE_SHADOW_FINAL_SOURCE_PROMOTION_CONTRACT_PASS`
**Commit**: pending
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +1 pure helper (`_build_h5_local_candidate_shadow_final_source_promotion`), +1 attachment in `_finalize_with_nexus_row`, +6 summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +7 H5-28 tests |

## Commands Run

```text
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
→ OK

pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5" -q
→ 130 passed

pytest tests/benchmark/test_h5_local_committee_e2e_smoke.py -q
→ 38 passed

pytest tests/benchmark/test_h5_cloud_fallback_e2e_smoke.py -q
→ 18 passed

NEXUS_H5_ENABLE_CONTROLLED_EXECUTION=1 NEXUS_H5_ALLOW_LOCAL_FINALIZATION=1 \
  NEXUS_H5_ALLOW_FINAL_SOURCE_CHANGE=1 NEXUS_H5_ALLOW_FINAL_PATCH_REPLACEMENT=1 \
  pytest tests/benchmark/test_capability_ab_runner.py -k "h5_28" -q
→ 7 passed
```

## Test Counts

| Suite | Count |
|-------|-------|
| H5 selector | 130 |
| Local smoke | 38 |
| Cloud smoke | 18 |
| H5-28 all-flags controlled trial | 7 |
| **Total** | **186** |

## Schema

```json
{
  "schema": "nexus.hybrid_h5_local_candidate_shadow_final_source_promotion.v1",
  "evaluated": true,
  "shadow_promotion_candidate": false,
  "shadow_promotion_status": "blocked",
  "shadow_promotion_reasons": [],
  "actual_final_source_before": "none",
  "actual_final_source_after": "none",
  "shadow_final_source_after_promotion": "none",
  "actual_final_source_changed": false,
  "final_source_change_allowed": false,
  "would_set_final_source_to": "",
  "would_promote_local_candidate": false,
  "promotion_allowed": false,
  "promotion_gate_blocked": true,
  "rollback_available": false,
  "rollback_required": false,
  "selected_candidate_id": "",
  "selected_candidate_patch_sha256": "",
  "selected_candidate_hash_verified": false,
  "final_patch_replacement_allowed": false,
  "final_patch_replacement_would_occur": false,
  "output_mutation_allowed": false,
  "output_mutation_would_occur": false,
  "model_calls_increment_would_occur": false,
  "public_claim_allowed": false,
  "production_ready": false
}
```

## Shadow Promotion Rules

1. `actual_final_source_after` always equals current `final_source` ("none").
2. `actual_final_source_changed` detects unexpected mutations (always false in normal rows).
3. `shadow_promotion_candidate=true` only when:
   - `h5_local_candidate_promotion_dry_run.would_promote_local_candidate=true`
   - Selected candidate metadata exists (local evidence accepted)
   - `h5_local_candidate_rollback_dry_run.safe_to_continue=true`
4. If `shadow_promotion_candidate=true`:
   - `shadow_final_source_after_promotion="local_candidate_shadow_promoted"` (metadata only)
   - `would_set_final_source_to="local_candidate_shadow_promoted"`
5. Even if `shadow_promotion_candidate=true`:
   - `final_source_change_allowed=false`
   - `promotion_allowed=false`
   - `actual_final_source_after="none"`
   - `actual_final_source_changed=false`
6. `shadow_promotion_status`:
   - `"shadow_ready_blocked"` if shadow candidate exists but mutation not allowed
   - `"blocked"` otherwise
7. Required blocked reasons always present:
   - `shadow_only_no_actual_final_source_change`
   - `promotion_gate_blocked`
   - `final_source_change_not_enabled`
   - `real_promotion_not_implemented`

## All-Four-Flags Controlled Trial

| Field | Result |
|-------|--------|
| `actual_final_source_after` | "none" |
| `actual_final_source_changed` | false |
| `final_source` (row-level) | "none" |
| `behavior_changed` | false |
| `final_patch` | unchanged |
| `output` | unchanged |
| `h5_local_candidate_promotion_dry_run.promotion_allowed` | false |
| `h5_local_candidate_shadow_final_source_promotion.promotion_allowed` | false |

## Proofs

- **actual final_source remains none**: `actual_final_source_before = actual_final_source_after = "none"` in all paths. `actual_final_source_changed=false` unless row has unexpected non-"none" final_source.
- **shadow_final_source_after_promotion can be local_candidate_shadow_promoted only as metadata**: When `shadow_promotion_candidate=true`, `shadow_final_source_after_promotion="local_candidate_shadow_promoted"` records what WOULD happen. Actual final_source stays "none".
- **final_patch is not replaced**: `final_patch_replacement_allowed=false`, `final_patch_replacement_would_occur=false` always.
- **output is not mutated**: `output_mutation_allowed=false`, `output_mutation_would_occur=false` always.
- **model_calls is not incremented**: `model_calls_increment_would_occur=false` always.

## Summary Counters

```text
h5_local_shadow_final_source_promotion_count
h5_local_shadow_promotion_candidate_count
h5_local_shadow_promotion_ready_blocked_count
h5_local_actual_final_source_changed_count
h5_local_final_source_change_allowed_count
h5_local_shadow_final_source_promoted_count
```

Expected:
- `h5_local_actual_final_source_changed_count == 0`
- `h5_local_final_source_change_allowed_count == 0` (unless env flag set)
- `h5_local_shadow_final_source_promoted_count >= 1` only as shadow metadata
- `h5_behavior_changed_count == 0`
- `h5_cloud_fallback_invoked_count == 0`
- `h5_execution_allowed_count == 0`

## Statements

```text
Shadow final_source promotion contract only.
No H5 execution enabled.
No real local-first execution.
No cloud fallback execution.
No local committee invocation from benchmark runner.
No cloud provider invocation from benchmark runner.
No local candidate finalization.
No actual final_source change.
No final_patch replacement.
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
