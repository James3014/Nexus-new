# H5-39 Combined Patch Rollback + Output Preflight + Isolated Output Simulation Report

**日期**: 2026-06-23
**狀態**: `H5_39_PATCH_ROLLBACK_OUTPUT_PREFLIGHT_ISOLATED_OUTPUT_SIMULATION_PASS`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +6 pure helpers (3 decision/helper pairs), +4 attachments in `_finalize_with_nexus_row`, +11 summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +17 H5-39 tests |

## Commands Run

```text
python3 -m py_compile → OK
pytest -k "hybrid_route or local_guard or h5" -q → 241 passed
pytest test_h5_local_committee_e2e_smoke.py test_h5_cloud_fallback_e2e_smoke.py -q → 56 passed
pytest -k "h5_39" -q → 17 passed (default env)
pytest -k "h5_39" -q → 17 passed (all-13-flags)
```

## Test Counts

| Suite | Count |
|-------|-------|
| H5 selector | 241 |
| Smoke | 56 |
| H5-39 | 17 + 17 |
| **Total** | **331** |

## New Env Flags (13 total)

11 previous + `NEXUS_H5_ALLOW_ACTUAL_FINAL_PATCH_ROLLBACK` + `NEXUS_H5_ALLOW_OUTPUT_APPLY_PREFLIGHT` + `NEXUS_H5_ALLOW_ISOLATED_OUTPUT_SIMULATION`

## Part A: Final Patch Rollback

- Applies when: metadata-only patch + clean receipt + rollback flag
- Restores `final_patch` to `"none"` in copied row
- Actual row never mutated

## Part B: Output Apply Preflight

- Requires: final_source cycle proven, final_patch cycle proven, all hashes verified
- `output_preflight_pass_shadow_only` when pass — no actual output mutation

## Part C: Isolated Output Simulation

- When preflight passes: `isolated_output_mutated=true` with sha256/length
- `actual_output_mutated=false` always

## Proofs

- **final_patch rollback works**: metadata patch restored to "none" via shallow copy
- **output preflight is shadow-only**: `output_mutation_allowed=false` always
- **isolated output can mutate only as metadata**: `isolated_output_mutated=true` but `actual_output_mutated=false`
- **actual output remains unchanged**: Always
- **model_calls not incremented**: Always
- **cloud fallback not invoked**: Always
- **behavior_changed remains false**: Always

## Summary Counters

```text
h5_actual_final_patch_rollback_decision_count
h5_actual_final_patch_rollback_allowed_count
h5_actual_final_patch_rollback_executed_count
h5_actual_final_patch_rollback_restored_count
h5_output_apply_preflight_receipt_count
h5_output_apply_preflight_pass_shadow_count
h5_output_apply_preflight_blocked_count
h5_isolated_output_simulation_count
h5_isolated_output_simulation_pass_count
h5_isolated_output_mutated_count
h5_actual_output_mutated_count_h5_39
```

## Statements

```text
Combined acceleration phase only.
No actual output mutation.
No full H5 execution enabled.
Not H5 ready.
Not local-first ready.
public_claim_allowed=false.
production_ready=false.
```
