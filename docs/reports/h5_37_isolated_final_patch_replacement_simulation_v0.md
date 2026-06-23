# H5-37 Isolated Final Patch Replacement Simulation Report

**日期**: 2026-06-23
**狀態**: `H5_37_ISOLATED_FINAL_PATCH_REPLACEMENT_SIMULATION_PASS`
**Commit**: pending

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/bench/capability_ab_runner.py` | +1 pure helper, +1 attachment, +6 summary counters |
| `tests/benchmark/test_capability_ab_runner.py` | +10 H5-37 tests |

## Commands Run

```text
python3 -m py_compile scripts/bench/capability_ab_runner.py tests/benchmark/test_capability_ab_runner.py
→ OK

pytest tests/benchmark/test_capability_ab_runner.py -k "hybrid_route or local_guard or h5" -q
→ 214 passed

pytest tests/benchmark/test_h5_local_committee_e2e_smoke.py tests/benchmark/test_h5_cloud_fallback_e2e_smoke.py -q
→ 56 passed

NEXUS_H5_ALLOW_FINAL_PATCH_APPLY_PREFLIGHT=1 ... \
  pytest tests/benchmark/test_capability_ab_runner.py -k "h5_37" -v
→ 10 passed
```

## Test Counts

| Suite | Count |
|-------|-------|
| H5 selector | 214 |
| Local smoke | 38 |
| Cloud smoke | 18 |
| H5-37 all-flags trial | 10 |
| **Total** | **280** |

## Schema

```json
{
  "schema": "nexus.hybrid_h5_isolated_final_patch_replacement_simulation.v1",
  "evaluated": true,
  "simulation_status": "blocked",
  "simulation_reasons": [],
  "would_simulate_final_patch_replacement": false,
  "actual_final_patch_replaced": false,
  "isolated_final_patch_replaced": false,
  "isolated_final_patch_sha256": "",
  "isolated_final_patch_length": 0,
  "output_mutated": false,
  "model_calls_incremented": false,
  "cloud_invoked": false,
  "behavior_changed": false
}
```

## Simulation Pass Rules

`would_simulate_final_patch_replacement=true` requires ALL:
1. Preflight receipt exists and passes shadow-only
2. Selected candidate patch hash present, length > 0, verified
3. Final source apply cycle proven
4. Final source rollback proven
5. Rollback available, not required, safe
6. Output not mutated

When simulation passes:
- `isolated_final_patch_replaced=true`
- `isolated_final_patch_sha256` = selected hash
- `isolated_final_patch_length` = selected length
- `actual_final_patch_replaced=false` — actual row unchanged

## Proofs

- **isolated final_patch can be replaced as metadata only**: `isolated_final_patch_replaced=true` with sha256/length when simulation passes.
- **actual final_patch remains unchanged**: `actual_final_patch_replaced=false` always.
- **output is not mutated**: `output_mutated=false` always.
- **model_calls is not incremented**: `model_calls_incremented=false` always.
- **cloud fallback is not invoked**: `cloud_invoked=false` always.
- **behavior_changed remains false**: Always false.

## Summary Counters

```text
h5_isolated_final_patch_simulation_count
h5_isolated_final_patch_simulation_pass_count
h5_isolated_final_patch_simulation_blocked_count
h5_isolated_final_patch_replaced_count
h5_actual_final_patch_replaced_count_sim
h5_isolated_final_patch_safe_count
```

## Statements

```text
Isolated final_patch replacement simulation only.
No actual final_patch replacement.
No output mutation.
No full H5 execution enabled.
Not H5 ready.
Not local-first ready.
public_claim_allowed=false.
production_ready=false.
```
