# LocalHeal Sprint C15-3B: Semantic Retry Prompt Uses Verifier Evidence

**Status**: `LOCAL_MODEL_SPRINT_C15_3B_SEMANTIC_RETRY_PROMPT_USES_VERIFIER_EVIDENCE_PASS`

**Date**: 2026-07-03

---

## Summary

Added bounded verifier failure evidence injection to the existing `build_verification_guided_retry_prompt` function. When verifier fails and evidence is available, the retry prompt now includes bounded verifier evidence for root-cause analysis. This phase only injects evidence — it does not create a new retry path, trigger retry, or alter verifier authority.

---

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/failure_feedback_builder.py` | Added `build_verifier_evidence_section()` and `compute_verifier_evidence_hash()` functions |
| `nexus/services/local_heal/prompt_builder.py` | Modified `build_verification_guided_retry_prompt()` to accept verifier evidence parameters and inject evidence section |
| `nexus/services/local_heal/local_model_executor.py` | Added metadata fields for evidence injection tracking |
| `tests/unit/local_heal/test_failure_feedback_builder.py` | Added 10 tests covering verifier evidence prompt injection |
| `scripts/bench/m1_real_local_solve_benchmark.py` | Added 3 semantic retry metadata fields to row_data |
| `tests/benchmark/test_m1_real_local_solve_benchmark.py` | No changes needed (existing tests pass) |

---

## Commands Run

```bash
python3 -m py_compile \
  nexus/services/local_heal/failure_feedback_builder.py \
  nexus/services/local_heal/prompt_builder.py \
  nexus/services/local_heal/local_model_executor.py \
  scripts/bench/m1_real_local_solve_benchmark.py \
  tests/unit/local_heal/test_failure_feedback_builder.py \
  tests/unit/local_heal/test_local_model_executor.py \
  tests/benchmark/test_m1_real_local_solve_benchmark.py
```

```bash
uv run pytest \
  tests/unit/local_heal/test_failure_feedback_builder.py \
  tests/unit/local_heal/test_local_model_executor.py \
  tests/benchmark/test_m1_real_local_solve_benchmark.py \
  -q
```

**Result**: 114 passed in 1.55s

---

## Test Counts

| File | Tests |
|------|-------|
| `test_failure_feedback_builder.py` | 17 (7 existing + 10 new C15-3B) |
| `test_local_model_executor.py` | 89 (existing) |
| `test_m1_real_local_solve_benchmark.py` | 9 (existing) |
| **Total** | **114 passed** |

---

## Evidence Fields Consumed

| Field | Source |
|-------|--------|
| `verifier_failure_kind` | C15-3A |
| `verifier_stdout_excerpt` | C15-3A |
| `verifier_stderr_excerpt` | C15-3A |
| `verifier_exit_code` | C15-3A |
| `verifier_command_hash` | C15-3A |

---

## Prompt Section Added

When `semantic_retry_evidence_ready == true`, the retry prompt includes:

```
### VERIFIER FAILURE EVIDENCE (bounded, for root-cause analysis only)
- Failure kind: <verifier_failure_kind>
- Exit code: <verifier_exit_code>
- Command hash: <verifier_command_hash>
- Stdout excerpt (bounded):
```
<verifier_stdout_excerpt[:1000]>
```
- Stderr excerpt (bounded):
```
<verifier_stderr_excerpt[:1000]>
```

ANALYZE the failure evidence above to understand what went wrong.
The verifier remains final authority — your new patch must still pass verification.
Output must remain SEARCH/REPLACE protocol. No prose, no markdown fences.
```

---

## Metadata Fields Added

| Field | Description |
|-------|-------------|
| `semantic_retry_verifier_evidence_injected` | bool, false until orchestrator invokes retry with evidence |
| `semantic_retry_verifier_evidence_fields` | str, comma-separated list of injected fields |
| `semantic_retry_prompt_evidence_hash` | str, 16-char SHA256 hash of injected evidence |

---

## Statements

- **Existing retry prompt evidence injection only**: This task injects bounded verifier evidence into the existing `build_verification_guided_retry_prompt` function. It does not create a new retry path.
- **No new route**: No new RouteMode, Router, or topology selector added.
- **No new topology**: No new execution_topology added.
- **No new retry loop**: No new retry loop created. Evidence is injected only when existing retry path is invoked.
- **No route changes**: No route logic modified.
- **No parser changes**: No protocol or parser behavior changes.
- **No verifier behavior changes**: Verifier results are read-only input. No verifier invocation is changed.
- **No candidate isolation behavior changes**: No changes to isolated_workspace_apply or candidate_isolation_gate.
- **No patch lifecycle behavior changes**: `patch_lifecycle_state` is read-only input.
- **No failure classifier behavior changes**: `failure_class` is read-only input.
- **No real model calls**: No real model calls were made.
- **No live benchmark**: No live benchmark was run.
- **Not toy-math-solve solved**: This task does not claim toy-math-solve solved.
- **Not local model armor ready**: This task does not claim local model armor ready.
- **production_ready=false**: This evidence injection is not production-ready.
- **public_claim_allowed=false**: No public claims are allowed.
