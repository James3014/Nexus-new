# LocalHeal Sprint C15-2: Failure Classifier Hardening

**Status**: `LOCAL_MODEL_SPRINT_C15_2_FAILURE_CLASSIFIER_HARDENING_PASS`

**Date**: 2026-07-03

---

## Summary

Added `failure_class` — a deterministic, receipt-level failure classifier derived from existing execution metadata. Replaces avoidable `output_class=UNKNOWN` with 15 mutually exclusive failure classes. Every `output_len > 0` row now has a non-empty `failure_class`.

---

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_executor.py` | Added `compute_failure_class()` function + wired into `local_committee_only` and `localheal_pipeline` topologies |
| `tests/unit/local_heal/test_local_model_executor.py` | Added 13 tests covering all failure classes |
| `scripts/bench/m1_real_local_solve_benchmark.py` | Added `failure_class` and `unknown_reason` to row_data |
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

**Result**: 86 passed in 1.63s

---

## Test Counts

| File | Tests |
|------|-------|
| `test_local_model_executor.py` | 77 (64 existing + 13 new C15-2) |
| `test_m1_real_local_solve_benchmark.py` | 9 (existing) |
| **Total** | **86 passed** |

---

## Failure Class Values Added

| Class | Meaning |
|-------|---------|
| `empty_response` | `output_len == 0` and no provider error |
| `provider_error` | Provider returned an error |
| `no_blocks_found` | Failure reason contains `NO_BLOCKS_FOUND` |
| `search_mismatch` | Failure reason contains `SEARCH_MISMATCH` |
| `replace_syntax_error` | Failure reason contains `REPLACE_SYNTAX_ERROR` or `SYNTAX_ERROR` |
| `fenced_output` | `parse_error_kind` contains `REPLACEMENT_MARKDOWN_FENCE` or `contains_markdown_fence=true` |
| `refusal` | `parse_error_kind` or failure reason contains `REFUSAL` |
| `patch_apply_failed` | `patch_lifecycle_state == isolation_attempted_apply_failed` |
| `hash_mismatch` | `patch_lifecycle_state == isolation_applied_hash_mismatch` |
| `verification_failed` | `patch_lifecycle_state == isolation_applied_hash_match_verifier_failed` |
| `semantic_wrong_patch` | Verifier failed and patch was present |
| `verifier_passed` | Verifier passed and solved=true |
| `unknown_with_reason` | No stronger class applies; `unknown_reason` must be non-empty |

---

## Table: Evidence → `failure_class`

| Evidence | State |
|----------|-------|
| `provider_error` non-empty | `provider_error` |
| `output_len == 0` and no provider error | `empty_response` |
| `failure_reason` contains `NO_BLOCKS_FOUND` | `no_blocks_found` |
| `failure_reason` contains `SEARCH_MISMATCH` | `search_mismatch` |
| `failure_reason` contains `REPLACE_SYNTAX_ERROR` | `replace_syntax_error` |
| `parse_error_kind` contains `REPLACEMENT_MARKDOWN_FENCE` or `contains_markdown_fence=true` | `fenced_output` |
| `parse_error_kind` or `failure_reason` contains `REFUSAL` | `refusal` |
| `patch_lifecycle_state == isolation_attempted_apply_failed` | `patch_apply_failed` |
| `patch_lifecycle_state == isolation_applied_hash_mismatch` | `hash_mismatch` |
| `patch_lifecycle_state == isolation_applied_hash_match_verifier_failed` | `verification_failed` |
| `verifier_result == pass` and `solved == true` | `verifier_passed` |
| `verifier_result == fail` and patch present | `semantic_wrong_patch` |
| None of above and `output_len > 0` | `unknown_with_reason` |

---

## Statements

- **Classification only**: This task adds a receipt-level classifier. It does not change execution behavior.
- **No route changes**: No new RouteMode, Router, Planner, or topology selector added.
- **No prompt changes**: No prompt_builder or prompt template modifications.
- **No parser changes**: No protocol or parser behavior changes.
- **No verifier changes**: No verifier behavior changes.
- **No candidate isolation behavior changes**: No changes to isolated_workspace_apply or candidate_isolation_gate.
- **No patch lifecycle behavior changes**: `patch_lifecycle_state` is read-only input to classifier.
- **No real model calls**: No real model calls were made.
- **No live benchmark**: No live benchmark was run.
- **Not toy-math-solve solved**: This task does not claim toy-math-solve solved.
- **Not local model armor ready**: This task does not claim local model armor ready.
- **production_ready=false**: This failure classifier is not production-ready.
- **public_claim_allowed=false**: No public claims are allowed.
