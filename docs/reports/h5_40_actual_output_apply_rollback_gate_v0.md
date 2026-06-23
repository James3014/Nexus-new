# H5-40 Actual Output Apply + Rollback Gate Report

**日期**: 2026-06-23
**狀態**: `H5_40_ACTUAL_OUTPUT_APPLY_ROLLBACK_GATE_PASS`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +4 pure helpers (apply decision, apply, rollback decision, rollback), +4 attachments, +9 summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +17 H5-40 tests |

## Commands Run

```text
python3 -m py_compile → OK
pytest -k "hybrid_route or local_guard or h5" -q → 258 passed
pytest smoke tests -q → 56 passed
pytest -k "h5_40" -q → 17 passed (default env)
pytest -k "h5_40" -q → 17 passed (all-15-flags)
```

## Test Counts

| Suite | Count |
|-------|-------|
| H5 selector | 258 |
| Smoke | 56 |
| H5-40 | 17 + 17 |
| **Total** | **348** |

## All 15 Flags

13 from H5-39 plus:
- `NEXUS_H5_ALLOW_ACTUAL_OUTPUT_APPLY` (H5-40A)
- `NEXUS_H5_ALLOW_ACTUAL_OUTPUT_ROLLBACK` (H5-40C)

## Default-Env Result

- No output apply, no rollback
- Output unchanged

## All-Flags Trial

- Output may become metadata delivery dict: `{"source": "local_candidate_shadow_promoted", "delivery_kind": "candidate_patch_metadata_only", "patch_sha256": "...", ...}`
- With rollback flag: output may restore to `"none"`
- final_source unchanged by H5-40
- final_patch unchanged by H5-40
- model_calls unchanged
- cloud_fallback_invoked=false
- behavior_changed=false

## Proofs

- **output can apply and rollback under flags**: Apply sets metadata dict, rollback restores to "none"
- **model_calls unchanged**: Always
- **cloud fallback uninvoked**: Always
- **behavior_changed false**: Always
- **final_source/final_patch unchanged by H5-40**: Always

## Summary Counters

```text
h5_actual_output_apply_decision_count
h5_actual_output_apply_allowed_count
h5_actual_output_apply_executed_count
h5_actual_output_mutated_count_h5_40
h5_actual_output_rollback_decision_count
h5_actual_output_rollback_allowed_count
h5_actual_output_rollback_executed_count
h5_actual_output_restored_count
h5_actual_output_safe_count
```

## Statements

```text
Actual output apply/rollback gate only.
Metadata delivery only.
No full H5 execution enabled.
Not H5 ready.
Not local-first ready.
public_claim_allowed=false.
production_ready=false.
```
