# LocalHeal Sprint C15-3E: Verifier Receipt Stdout/Stderr Capture Fix

**Status**: `LOCAL_MODEL_SPRINT_C15_3E_VERIFIER_RECEIPT_STDOUT_STDERR_CAPTURE_FIX_PASS`

**Date**: 2026-07-03

---

## Summary

Fixed the verifier receipt plumbing so that `stdout_tail`, `stderr_tail`, `exit_code`, and `error` from `IsolatedVerifierReceipt` are preserved in downstream metadata. Both `local_committee_only` and `localheal_pipeline` topologies now capture verifier receipt evidence and pass it to `compute_verifier_failure_evidence()`. Added presence fields for tracking.

---

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_executor.py` | Captured `stdout_tail`, `stderr_tail`, `exit_code` from verifier receipt in both topologies + added presence fields |
| `scripts/bench/m1_real_local_solve_benchmark.py` | Added 4 verifier receipt presence fields to row_data |
| `tests/unit/local_heal/test_local_model_executor.py` | Added 9 tests covering verifier receipt evidence capture |

---

## Commands Run

```bash
python3 -m py_compile \
  nexus/services/local_heal/local_model_executor.py \
  nexus/services/local_heal/isolated_local_solve_loop.py \
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

**Result**: 115 passed in 1.63s

---

## Test Counts

| File | Tests |
|------|-------|
| `test_local_model_executor.py` | 106 (97 existing + 9 new C15-3E) |
| `test_m1_real_local_solve_benchmark.py` | 9 (existing) |
| **Total** | **115 passed** |

---

## Receipt Fields Preserved

| Field | Source |
|-------|--------|
| `verifier_stdout_tail` | `IsolatedVerifierReceipt.stdout_tail` |
| `verifier_stderr_tail` | `IsolatedVerifierReceipt.stderr_tail` |
| `verifier_exit_code` | `IsolatedVerifierReceipt.exit_code` |
| `verifier_error` | `IsolatedVerifierReceipt.verifier_error` |

---

## Evidence Fields Affected

| Field | Before | After |
|-------|--------|-------|
| `verifier_stdout_excerpt` | Always empty | Real stdout when available |
| `verifier_stderr_excerpt` | Always empty | Real stderr when available |
| `verifier_exit_code` | Always empty | Real exit code when available |
| `verifier_failure_evidence_available` | Always false when no error | True when stdout/stderr/error present |

---

## Statements

- **Verifier receipt plumbing only**: This task fixes the plumbing to pass verifier receipt evidence to downstream metadata. It does not change verifier behavior.
- **No new route**: No new RouteMode, Router, or topology selector added.
- **No new topology**: No new execution_topology added.
- **No new retry loop**: No new retry loop created.
- **No route changes**: No route logic modified.
- **No prompt changes**: No prompt builder or retry prompt modifications.
- **No parser changes**: No protocol or parser behavior changes.
- **No verifier behavior changes**: Verifier results are read-only input. No verifier invocation is changed.
- **No candidate isolation behavior changes**: No changes to isolated_workspace_apply or candidate_isolation_gate.
- **No patch lifecycle behavior changes**: `patch_lifecycle_state` is read-only input.
- **No failure classifier behavior changes**: `failure_class` is read-only input.
- **No semantic retry prompt changes**: No prompt_builder.py modifications.
- **No real model calls**: No real model calls were made.
- **No live benchmark**: No live benchmark was run.
- **Not toy-math-solve solved**: This task does not claim toy-math-solve solved.
- **Not local model armor ready**: This task does not claim local model armor ready.
- **production_ready=false**: This receipt plumbing fix is not production-ready.
- **public_claim_allowed=false**: No public claims are allowed.
