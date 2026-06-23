# H5-38 Controlled Actual Final Patch Apply Gate Report

**日期**: 2026-06-23
**狀態**: `H5_38_CONTROLLED_ACTUAL_FINAL_PATCH_APPLY_GATE_PASS`

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +2 pure helpers (decision + apply), +1 integration, +7 summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +10 H5-38 tests |

## Commands Run

```text
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py → OK
pytest -k "hybrid_route or local_guard or h5" -q → 224 passed
pytest test_h5_local_committee_e2e_smoke.py test_h5_cloud_fallback_e2e_smoke.py -q → 56 passed
pytest -k "h5_38" -q → 10 passed (default env)
pytest -k "h5_38" -q → 10 passed (all-ten-flags)
```

## Test Counts

| Suite | Count |
|-------|-------|
| H5 selector | 224 |
| Local smoke | 38 |
| Cloud smoke | 18 |
| H5-38 default | 10 |
| H5-38 all-flags | 10 |
| **Total** | **300** |

## All Ten Flags

Flags 1-8 from H5-34/35 plus:
- `NEXUS_H5_ALLOW_FINAL_PATCH_APPLY_PREFLIGHT` (H5-36)
- `NEXUS_H5_ALLOW_ACTUAL_FINAL_PATCH_APPLY` (H5-38)

## Default-Env Result

- `actual_patch_apply_allowed=false`
- `final_patch` remains unchanged

## All-Ten-Flags Trial

- May set `final_patch` to metadata-only dict: `{"source": "local_candidate_shadow_promoted", "patch_sha256": "...", "content_kind": "candidate_patch_metadata_only"}`
- `output_mutated=false`, `model_calls_incremented=false`, `cloud_invoked=false`, `behavior_changed=false`

## Proofs

- **default env final_patch unchanged**: `actual_patch_apply_allowed=false`, final_patch stays original.
- **all-ten-flags may set metadata-only final_patch**: `actual_patch_apply_allowed=true` → `final_patch = {...metadata dict...}` via shallow copy.
- **output is not mutated**: `output_mutated=false` always.
- **model_calls is not incremented**: `model_calls_incremented=false` always.
- **cloud fallback is not invoked**: `cloud_invoked=false` always.
- **behavior_changed remains false**: Always false.

## Summary Counters

```text
h5_actual_final_patch_apply_decision_count
h5_actual_final_patch_apply_allowed_count
h5_actual_final_patch_apply_blocked_count
h5_actual_final_patch_apply_executed_count
h5_actual_final_patch_apply_replaced_count
h5_actual_final_patch_apply_all_flags_enabled_count
h5_actual_final_patch_apply_safe_count
```

## Statements

```text
Controlled actual final_patch apply gate only.
Metadata-only final_patch promotion.
No output mutation.
No full H5 execution enabled.
Not H5 ready.
Not local-first ready.
public_claim_allowed=false.
production_ready=false.
```
