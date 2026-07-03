# LocalHeal Sprint C15-3A: Verifier Failure Evidence Capture

**Status**: `LOCAL_MODEL_SPRINT_C15_3A_VERIFIER_FAILURE_EVIDENCE_CAPTURE_PASS`

**Date**: 2026-07-03

---

## Summary

Added bounded verifier failure evidence fields to downstream metadata and benchmark row_data. When verifier fails, evidence is captured in a stable receipt field for a later semantic retry phase. This phase only captures evidence — it does not change execution behavior, trigger retry, or alter verifier results.

---

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_executor.py` | Added `compute_verifier_failure_evidence()` function + wired into `local_committee_only` and `localheal_pipeline` topologies |
| `tests/unit/local_heal/test_local_model_executor.py` | Added 12 tests covering verifier failure evidence capture |
| `scripts/bench/m1_real_local_solve_benchmark.py` | Added 7 verifier failure evidence fields to row_data |
| `tests/benchmark/test_m1_real_local_solve_benchmark.py` | No changes needed (existing tests pass) |

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

**Result**: 98 passed in 1.61s

---

## Test Counts

| File | Tests |
|------|-------|
| `test_local_model_executor.py` | 89 (77 existing + 12 new C15-3A) |
| `test_m1_real_local_solve_benchmark.py` | 9 (existing) |
| **Total** | **98 passed** |

---

## Fields Added

| Field | Type | Description |
|-------|------|-------------|
| `verifier_failure_evidence_available` | bool | True only when verifier_result=fail and at least one evidence field is non-empty |
| `verifier_failure_kind` | str | Classification of verifier failure type |
| `verifier_stdout_excerpt` | str | Bounded to max 1000 characters |
| `verifier_stderr_excerpt` | str | Bounded to max 1000 characters |
| `verifier_exit_code` | int/str | Raw exit code from verifier |
| `verifier_command_hash` | str | 16-char SHA256 hash of verifier command (not raw command) |
| `semantic_retry_evidence_ready` | bool | True when failure_class and lifecycle state indicate retry-ready evidence |

---

## Table: Verifier Evidence → `verifier_failure_kind`

| Evidence | Kind |
|----------|------|
| `verifier_error` contains "timeout" | `timeout` |
| exit_code != 0, stdout/stderr contains "assert" | `assertion_failure` |
| exit_code != 0, stdout/stderr contains "traceback"/"exception" | `exception` |
| exit_code != 0, other | `nonzero_exit` |
| No verifier command | `missing_verifier_command` |
| Fallback | `unknown_verifier_failure` |

---

## Statements

- **Evidence capture only**: This task captures bounded verifier failure evidence. It does not change execution behavior.
- **No semantic retry implemented**: No retry is triggered. Evidence is captured for a future phase.
- **No retry prompt changes**: No prompt_builder or retry prompt modifications.
- **No route changes**: No new RouteMode, Router, Planner, or topology selector added.
- **No prompt changes**: No prompt_builder or prompt template modifications.
- **No parser changes**: No protocol or parser behavior changes.
- **No verifier behavior changes**: Verifier results are read-only input. No verifier invocation is changed.
- **No candidate isolation behavior changes**: No changes to isolated_workspace_apply or candidate_isolation_gate.
- **No patch lifecycle behavior changes**: `patch_lifecycle_state` is read-only input.
- **No failure classifier behavior changes**: `failure_class` is read-only input.
- **No real model calls**: No real model calls were made.
- **No live benchmark**: No live benchmark was run.
- **Not toy-math-solve solved**: This task does not claim toy-math-solve solved.
- **Not local model armor ready**: This task does not claim local model armor ready.
- **production_ready=false**: This evidence capture is not production-ready.
- **public_claim_allowed=false**: No public claims are allowed.
