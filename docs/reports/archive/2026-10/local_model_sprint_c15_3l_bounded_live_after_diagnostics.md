# LocalHeal Sprint C15-3L: Bounded Live Branch Coverage After Diagnostics

**Status**: `LOCAL_MODEL_SPRINT_C15_3L_LIVE_AFTER_DIAGNOSTICS_PASS`

**Date**: 2026-07-03

---

## Commands Run

```bash
python3 -m py_compile scripts/bench/m1_real_local_solve_benchmark.py
```

```bash
uv run pytest tests/unit/local_heal/test_local_model_executor.py tests/benchmark/test_m1_real_local_solve_benchmark.py -q
```

**Deterministic test count**: 137 passed

```bash
timeout 180 /Users/jameschen/.local/bin/uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-solve
```

**Live attempts**: 3 completed

---

## Live Attempt Table

| Attempt | `patch_lifecycle_state` | `failure_class` | `apply_failure_stage` | `apply_failure_reason` | `retry_eligible` | `retry_not_invoked_reason` | Branch Classification |
|---------|------------------------|-----------------|----------------------|----------------------|-----------------|--------------------------|----------------------|
| 1 | `isolation_attempted_apply_failed` | `patch_apply_failed` | `isolated_apply` | `error: patch failed: toy/math_util.py:1` | false | `patch_apply_failed` | `patch_apply_failed_with_reason` |
| 2 | `isolation_attempted_apply_failed` | `patch_apply_failed` | `isolated_apply` | `error: patch failed: toy/math_util.py:1` | false | `patch_apply_failed` | `patch_apply_failed_with_reason` |
| 3 | `isolation_attempted_apply_failed` | `patch_apply_failed` | `isolated_apply` | `error: patch failed: toy/math_util.py:1` | false | `patch_apply_failed` | `patch_apply_failed_with_reason` |

---

## Branch Classification Count

| Branch | Count |
|--------|-------|
| `patch_apply_failed_with_reason` | 3 |

---

## Diagnostic Field Verification

| Field | Attempt 1 | Attempt 2 | Attempt 3 | Status |
|-------|-----------|-----------|-----------|--------|
| `apply_failure_stage` | `isolated_apply` | `isolated_apply` | `isolated_apply` | ✅ Present |
| `apply_failure_reason` | Non-empty | Non-empty | Non-empty | ✅ Present |
| `retry_eligibility_checked` | true | true | true | ✅ Present |
| `retry_eligible` | false | false | false | ✅ Correct |
| `retry_not_invoked_reason` | `patch_apply_failed` | `patch_apply_failed` | `patch_apply_failed` | ✅ Correct |

---

## Decision Gate

**Result: D**

Most attempts (3/3) are `patch_apply_failed_with_reason`. The next phase should be:

**`C15-3M Patch Apply Failure Root Cause Fix`**

Focus on why the live model output produces patches that fail to apply. The `apply_failure_reason` consistently shows:
- `error: patch failed: toy/math_util.py:1`
- `error: toy/math_util.py: patch does not apply`

This indicates the model's SEARCH block doesn't match the current source file content, causing the patch to fail at the isolated apply stage.

---

## Next Recommended Phase

**C15-3M Patch Apply Failure Root Cause Fix**

This phase should investigate:
1. Why the model's SEARCH block doesn't match the source file
2. Whether the locked search span is being used correctly
3. Whether the model is producing SEARCH/REPLACE format correctly
4. Whether the source file content changes between patch generation and apply

---

## Statements

- **No code changes**: This task only ran live validation and created a report.
- **No route changes**: No route logic was modified.
- **No topology changes**: No topology logic was modified.
- **No prompt changes**: No prompt builder was modified.
- **No parser changes**: No parser behavior was modified.
- **No verifier behavior changes**: No verifier logic was modified.
- **No candidate isolation behavior changes**: No isolation logic was modified.
- **No full benchmark**: Only toy-math-solve was run, not the full 6-task benchmark.
- **Bounded toy live attempts only**: Exactly 3 `--task-id toy-math-solve` runs were executed.
- **Not local model armor ready**: This validation did not prove local model armor readiness.
- **production_ready=false**: This validation is not production-ready.
- **public_claim_allowed=false**: No public claims are allowed.
