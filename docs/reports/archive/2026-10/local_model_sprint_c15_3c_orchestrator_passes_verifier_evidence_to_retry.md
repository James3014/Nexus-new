# LocalHeal Sprint C15-3C: Orchestrator Verifier Evidence Pass-Through

**Status**: `LOCAL_MODEL_SPRINT_C15_3C_ORCHESTRATOR_PASSES_VERIFIER_EVIDENCE_TO_RETRY_PASS`

**Date**: 2026-07-03

---

## Summary

Wired the existing orchestrator retry path to pass bounded verifier failure evidence into the existing `build_verification_guided_retry_prompt` function. When `semantic_retry_evidence_ready == true` and `verifier_failure_evidence_available == true`, the orchestrator now passes verifier evidence to the retry prompt. This phase only connects existing evidence to the existing retry prompt — it does not create a new retry path.

---

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/orchestrator.py` | Added verifier evidence pass-through logic in `_attempt_semantic_retry` + metadata recording |
| `nexus/services/local_heal/local_model_executor.py` | No changes needed (evidence fields already exist) |
| `tests/unit/local_heal/test_local_model_executor.py` | Added 8 tests covering orchestrator evidence pass-through |
| `scripts/bench/m1_real_local_solve_benchmark.py` | Added 3 orchestrator metadata fields to row_data |
| `tests/benchmark/test_m1_real_local_solve_benchmark.py` | No changes needed (existing tests pass) |

---

## Commands Run

```bash
python3 -m py_compile \
  nexus/services/local_heal/orchestrator.py \
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

**Result**: 106 passed in 1.65s

---

## Test Counts

| File | Tests |
|------|-------|
| `test_local_model_executor.py` | 97 (89 existing + 8 new C15-3C) |
| `test_m1_real_local_solve_benchmark.py` | 9 (existing) |
| **Total** | **106 passed** |

---

## Evidence Fields Passed

| Field | Source |
|-------|--------|
| `verifier_failure_kind` | C15-3A |
| `verifier_stdout_excerpt` | C15-3A |
| `verifier_stderr_excerpt` | C15-3A |
| `verifier_exit_code` | C15-3A |
| `verifier_command_hash` | C15-3A |

---

## Metadata Fields Added

| Field | Description |
|-------|-------------|
| `orchestrator_verifier_evidence_passed_to_retry` | bool, true when evidence was passed to retry prompt |
| `orchestrator_verifier_evidence_fields` | str, comma-separated list of passed fields |
| `orchestrator_retry_prompt_evidence_hash` | str, 16-char SHA256 hash of passed evidence |

---

## Statements

- **Existing orchestrator retry path only**: This task connects existing evidence to the existing retry prompt. It does not create a new retry path.
- **No new route**: No new RouteMode, Router, or topology selector added.
- **No new topology**: No new execution_topology added.
- **No new retry loop**: No new retry loop created. Evidence is passed only when existing retry path is invoked.
- **No route changes**: No route logic modified.
- **No prompt builder changes**: No prompt_builder.py modifications (only orchestrator.py reads evidence and passes to existing prompt builder).
- **No parser changes**: No protocol or parser behavior changes.
- **No verifier behavior changes**: Verifier results are read-only input. No verifier invocation is changed.
- **No candidate isolation behavior changes**: No changes to isolated_workspace_apply or candidate_isolation_gate.
- **No patch lifecycle behavior changes**: `patch_lifecycle_state` is read-only input.
- **No failure classifier behavior changes**: `failure_class` is read-only input.
- **No real model calls**: No real model calls were made.
- **No live benchmark**: No live benchmark was run.
- **Not toy-math-solve solved**: This task does not claim toy-math-solve solved.
- **Not local model armor ready**: This task does not claim local model armor ready.
- **production_ready=false**: This evidence pass-through is not production-ready.
- **public_claim_allowed=false**: No public claims are allowed.
