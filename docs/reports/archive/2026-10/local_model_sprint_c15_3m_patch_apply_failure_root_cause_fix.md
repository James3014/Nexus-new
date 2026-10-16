# LocalHeal Sprint C15-3M: Patch Apply Failure Root Cause Fix

**Status**: `LOCAL_MODEL_SPRINT_C15_3M_APPLY_ROOT_CAUSE_DIAGNOSTICS_PASS`

**Date**: 2026-07-03

---

## Summary

Extended `localheal_pipeline` apply-failure diagnostics so downstream receipts can distinguish patch apply root causes instead of stopping at generic `patch_apply_failed`.

This phase does **not** change route, topology, prompt, parser, verifier behavior, candidate isolation behavior, or retry-loop behavior.

---

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_executor.py` | Added deterministic apply-failure root-cause classification, patch/source excerpts, and target-file hash diagnostics |
| `scripts/bench/m1_real_local_solve_benchmark.py` | Forwarded new apply-failure diagnostic fields into M1 benchmark rows |
| `tests/unit/local_heal/test_local_model_executor.py` | Added focused tests for search mismatch, header mismatch, target-file drift, excerpts, hashes, and restore consistency |
| `tests/benchmark/test_m1_real_local_solve_benchmark.py` | Asserted benchmark rows carry the new apply-failure telemetry fields |

---

## Root-Cause Contract

Added `apply_failure_root_cause` with the following values:

- `search_block_mismatch_current_source`
- `projected_patch_header_mismatch`
- `projected_patch_body_mismatch`
- `target_file_state_drift`
- `patch_format_invalid`
- `workspace_pollution_before_apply`
- `unknown_apply_failure`

Added or forwarded these evidence fields:

- `apply_failure_search_excerpt`
- `apply_failure_current_source_excerpt`
- `apply_failure_projected_patch_excerpt`
- `apply_failure_target_file_hash_before_apply`
- `apply_failure_target_file_hash_after_restore`
- `apply_failure_target_file_hash_at_apply`
- `apply_failure_projection_header`
- `apply_failure_original_header`
- `apply_failure_root_cause`

---

## Commands Run

```bash
python3 -m py_compile \
  nexus/services/local_heal/local_model_executor.py \
  scripts/bench/m1_real_local_solve_benchmark.py \
  tests/unit/local_heal/test_local_model_executor.py \
  tests/benchmark/test_m1_real_local_solve_benchmark.py
```

```bash
uv run pytest \
  tests/unit/local_heal/test_local_model_executor.py \
  tests/benchmark/test_m1_real_local_solve_benchmark.py \
  -q
```

**Result**: `145 passed in 2.00s`

---

## Focused Test Coverage

Added deterministic coverage for:

1. `search_block_mismatch_current_source`
2. `projected_patch_header_mismatch`
3. `target_file_state_drift`
4. search/source/projected patch excerpts
5. target-file hash recording
6. restore hash consistency
7. non-unknown classification when evidence exists and apply reports `patch does not apply`

---

## Evidence Interpretation

- If projected patch headers do not match the target file, receipts now classify `projected_patch_header_mismatch`.
- If the projected patch preimage does not exist in the current source at apply time, receipts now classify `search_block_mismatch_current_source`.
- If the source hash changes between restore and apply observation points, receipts now classify `target_file_state_drift`.
- If the repair loop polluted the target file before apply, the before/after-restore hashes now expose that fact instead of collapsing into generic apply failure.

---

## Statements

- **No live benchmark**: No bounded toy live rerun was executed in this phase.
- **No real model calls**: All coverage is deterministic test-only.
- **No route changes**: No route logic modified.
- **No topology changes**: No new topology or selector added.
- **No prompt changes**: No prompt wording changed.
- **No parser changes**: No parser behavior changed.
- **No verifier behavior changes**: Verifier remained read-only.
- **No candidate isolation behavior changes**: No isolated apply/verifier implementation changed.
- **No retry-loop changes**: Semantic retry eligibility and delegation behavior unchanged.
- **Not toy-math-solve solved**: This phase does not claim a solved result.
- **Not local model armor ready**: This phase only improves diagnostics.
- **production_ready=false**
- **public_claim_allowed=false**
