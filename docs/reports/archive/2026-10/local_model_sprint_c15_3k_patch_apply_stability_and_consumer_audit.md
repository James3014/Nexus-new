# LocalHeal Sprint C15-3K: Patch Apply Stability and Eligible Branch Consumer Audit

**Status**: `LOCAL_MODEL_SPRINT_C15_3K_PATCH_APPLY_STABILITY_AND_CONSUMER_AUDIT_PASS`

**Date**: 2026-07-03

---

## Summary

Added diagnostic fields for patch-apply failure and retry eligibility audit. The system now clearly reports:
1. Why isolated apply fails (stage, reason, error excerpt, patch hash)
2. Whether the verifier-failed branch is eligible for delegated retry
3. Why eligible branch was not delegated (or that it was delegated)

---

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_executor.py` | Added apply failure diagnostics + retry eligibility diagnostics |
| `scripts/bench/m1_real_local_solve_benchmark.py` | Added 11 diagnostic fields to row_data |
| `tests/unit/local_heal/test_local_model_executor.py` | Added 10 tests proving diagnostic fields |

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

**Result**: 137 passed in 1.59s

---

## Test Counts

| File | Tests |
|------|-------|
| `test_local_model_executor.py` | 128 (118 existing + 10 new C15-3K) |
| `test_m1_real_local_solve_benchmark.py` | 9 (existing) |
| **Total** | **137 passed** |

---

## Apply Failure Fields Added

| Field | Description |
|-------|-------------|
| `apply_failure_stage` | `none`, `projection`, `isolated_apply`, `hash_check`, `unknown` |
| `apply_failure_reason` | Human-readable reason for apply failure |
| `apply_failure_error_excerpt` | Bounded error excerpt (max 500 chars) |
| `apply_failure_patch_len` | Length of patch that failed to apply |
| `apply_failure_patch_hash` | Hash of patch that failed to apply |
| `apply_failure_projected` | Whether projection was attempted |
| `apply_failure_selected_candidate_hash` | Selected candidate hash |
| `apply_failure_target_file` | Target file path |

---

## Retry Eligibility Fields Added

| Field | Description |
|-------|-------------|
| `retry_eligibility_checked` | bool, always true when checked |
| `retry_eligible` | bool, true when delegated retry is eligible |
| `retry_not_invoked_reason` | str, reason when retry was not invoked |

---

## Apply Failure Classification Rules

| `patch_lifecycle_state` | `apply_failure_stage` | `apply_failure_reason` |
|------------------------|----------------------|----------------------|
| `isolation_attempted_apply_failed` | `isolated_apply` | `isolated_apply_error` or `patch_apply_failed` |
| `patch_present_not_projected` | `projection` | `patch_present_not_projected` |
| `patch_projected_not_isolated` | `isolated_apply` | `candidate_isolation_not_attempted` |
| Other | `none` | (empty) |

---

## Retry Eligibility Rules

| Condition | `retry_eligible` | `retry_not_invoked_reason` |
|-----------|-----------------|--------------------------|
| `solved=true` | false | `already_solved` |
| `provider=None` | false | `delegated_consumer_unavailable` |
| `patch_lifecycle_state=isolation_attempted_apply_failed` | false | `patch_apply_failed` |
| `patch_lifecycle_state=isolation_applied_hash_mismatch` | false | `hash_mismatch` |
| `semantic_retry_evidence_ready=false` | false | `semantic_retry_evidence_not_ready` |
| `failure_class not in (verification_failed, semantic_wrong_patch)` | false | `failure_class_not_retryable` |
| `candidate_isolated=false` | false | `candidate_not_isolated` |
| All conditions met | true | `none` |

---

## Statements

- **Deterministic diagnostics and eligibility audit only**: This task adds diagnostic fields and eligibility audit. It does not change execution behavior.
- **No new route**: No new RouteMode, Router, or topology selector added.
- **No new topology**: No new execution_topology added.
- **No new retry loop**: No new retry loop created.
- **No route changes**: No route logic modified.
- **No prompt changes**: No prompt builder or retry prompt modifications.
- **No parser changes**: No protocol or parser behavior changes.
- **No verifier behavior changes**: Verifier results are read-only input. No verifier invocation is changed.
- **No candidate isolation behavior changes**: No changes to isolated_workspace_apply or candidate_isolation_gate.
- **No patch lifecycle behavior changes**: `patch_lifecycle_state` is read-only input.
- **No full benchmark**: Only toy-math-solve was run, not the full 6-task benchmark.
- **No live benchmark**: No live benchmark was run.
- **Not toy-math-solve solved**: This task does not claim toy-math-solve solved.
- **Not local model armor ready**: This task does not claim local model armor ready.
- **production_ready=false**: This diagnostic audit is not production-ready.
- **public_claim_allowed=false**: No public claims are allowed.
