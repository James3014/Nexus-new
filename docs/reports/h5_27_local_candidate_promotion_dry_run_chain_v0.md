# H5-27 Local Candidate Promotion Dry-Run Chain Report

**日期**: 2026-06-22
**狀態**: `H5_27_LOCAL_CANDIDATE_PROMOTION_DRY_RUN_CHAIN_PASS`
**Commit**: pending
**治理**: `public_claim_allowed=false`, `production_ready=false`, `internal_only=true`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +3 pure helpers (promotion dry-run, rollback dry-run, gate matrix), +3 attachments, +11 new summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +9 H5-27 tests |

## Commands Run

```text
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
→ OK

pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5" -q
→ 123 passed

pytest tests/benchmark/test_h5_local_committee_e2e_smoke.py -q
→ 38 passed

pytest tests/benchmark/test_h5_cloud_fallback_e2e_smoke.py -q
→ 18 passed
```

## Schemas

### Promotion Dry-Run

```json
{
  "schema": "nexus.hybrid_h5_local_candidate_promotion_dry_run.v1",
  "would_promote_local_candidate": false,
  "promotion_allowed": false,
  "promotion_status": "blocked",
  "promotion_reasons": [],
  "final_source_after_shadow": "none",
  "final_patch_replacement_would_occur": false,
  "output_mutation_would_occur": false,
  "rollback_required": false
}
```

### Rollback Dry-Run

```json
{
  "schema": "nexus.hybrid_h5_local_candidate_rollback_dry_run.v1",
  "rollback_available": true,
  "rollback_required": false,
  "rollback_status": "not_required",
  "safe_to_continue": true
}
```

### Promotion Gate Matrix

```json
{
  "schema": "nexus.hybrid_h5_local_candidate_promotion_gate_matrix.v1",
  "promotion_gate_status": "blocked",
  "promotion_allowed": false,
  "final_source_change_allowed": false,
  "final_patch_replacement_allowed": false,
  "output_mutation_allowed": false
}
```

## Env Flag Behavior

| Flag | Effect in H5-27 |
|------|----------------|
| `NEXUS_H5_ENABLE_CONTROLLED_EXECUTION=1` | execution_flag_enabled=true, but promotion_allowed=false |
| `NEXUS_H5_ALLOW_LOCAL_FINALIZATION=1` | allow_local_finalization_flag_enabled=true, but promotion_allowed=false |
| `NEXUS_H5_ALLOW_FINAL_SOURCE_CHANGE=1` | allow_final_source_change_flag_enabled=true, but promotion_allowed=false |
| `NEXUS_H5_ALLOW_FINAL_PATCH_REPLACEMENT=1` | allow_final_patch_replacement_flag_enabled=true, but promotion_allowed=false |

All four flags can be "1" simultaneously — `promotion_allowed` remains `false` in H5-27.

## Controlled Trial Results

| Trial | promotion_allowed | final_source | behavior_changed | final_patch |
|-------|-------------------|--------------|------------------|-------------|
| All flags disabled | false | "none" | false | unchanged |
| All flags enabled | false | "none" | false | unchanged |

## Summary Counters

```text
h5_local_promotion_dry_run_count
h5_local_promotion_would_promote_count
h5_local_promotion_allowed_count
h5_local_promotion_blocked_count
h5_local_rollback_dry_run_count
h5_local_rollback_required_count
h5_local_promotion_gate_matrix_count
h5_local_promotion_gate_blocked_count
h5_local_final_source_change_allowed_count
h5_local_final_patch_replacement_allowed_count
```

## Statements

```text
Local candidate promotion dry-run chain only.
No H5 execution enabled.
No real local-first execution.
No cloud fallback execution.
No local committee invocation from benchmark runner.
No cloud provider invocation from benchmark runner.
No local candidate finalization.
No final delivery source change.
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
