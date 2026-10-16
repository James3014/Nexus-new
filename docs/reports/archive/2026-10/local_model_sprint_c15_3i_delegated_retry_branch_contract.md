# LocalHeal Sprint C15-3I: Delegated Retry Branch Contract

**Status**: `LOCAL_MODEL_SPRINT_C15_3I_DELEGATED_RETRY_BRANCH_CONTRACT_PASS`

**Date**: 2026-07-03

---

## Summary

Added deterministic tests proving the delegated retry branch eligibility contract. The tests verify that delegated retry is eligible only when all conditions are met (verifier-failed, hash-match, evidence-ready), and is NOT eligible when earlier blockers such as patch_apply_failed or hash_mismatch are present.

---

## Files Changed

| File | Change |
|------|--------|
| `tests/unit/local_heal/test_local_model_executor.py` | Added 8 deterministic tests proving delegated retry branch contract |

---

## Commands Run

```bash
python3 -m py_compile \
  nexus/services/local_heal/local_model_executor.py \
  tests/unit/local_heal/test_local_model_executor.py \
  scripts/bench/m1_real_local_solve_benchmark.py \
  tests/benchmark/test_m1_real_local_solve_benchmark.py
```

```bash
uv run pytest \
  tests/unit/local_heal/test_local_model_executor.py \
  tests/benchmark/test_m1_real_local_solve_benchmark.py \
  -q
```

**Result**: 127 passed in 1.66s

---

## Test Counts

| File | Tests |
|------|-------|
| `test_local_model_executor.py` | 118 (110 existing + 8 new C15-3I) |
| `test_m1_real_local_solve_benchmark.py` | 9 (existing) |
| **Total** | **127 passed** |

---

## Eligibility Contract

Delegated retry is eligible ONLY when ALL are true:

| Condition | Required Value |
|-----------|----------------|
| `candidate_isolated` | true |
| `hash_match` | true |
| `patch_lifecycle_state` | `isolation_applied_hash_match_verifier_failed` |
| `failure_class` | `verification_failed` or `semantic_wrong_patch` |
| `verifier_failure_evidence_available` | true |
| `semantic_retry_evidence_ready` | true |
| `verifier_result` | `fail` |
| `solved` | false |

---

## Non-Eligibility Contract

Delegated retry is NOT eligible when ANY of these are true:

| Condition | Non-Eligible Value |
|-----------|-------------------|
| `patch_lifecycle_state` | `isolation_attempted_apply_failed` |
| `failure_class` | `patch_apply_failed` |
| `candidate_isolated` | false |
| `hash_match` | false |
| `semantic_retry_evidence_ready` | false |

---

## Metadata Fields Asserted

| Field | Description |
|-------|-------------|
| `pipeline_retry_delegated` | bool, true when delegated retry was invoked |
| `retry_not_invoked_reason` | str, reason when retry was not invoked |
| `delegated_retry_failure_reason` | str, failure reason from delegated retry |
| `delegated_retry_final_patch_len` | int, length of patch from delegated retry |
| `delegated_retry_output_class` | str, output class from delegated retry |
| `delegated_retry_parser_error_kind` | str, parser error kind from delegated retry |
| `delegated_retry_status` | str, status from delegated retry |
| `delegated_retry_output_excerpt` | str, bounded output excerpt from delegated retry |

---

## Statements

- **Deterministic branch contract only**: This task adds deterministic tests proving the delegated retry branch eligibility contract. It does not change production behavior.
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
- **No real model calls**: No real model calls were made.
- **No live benchmark**: No live benchmark was run.
- **Not toy-math-solve solved**: This task does not claim toy-math-solve solved.
- **Not local model armor ready**: This task does not claim local model armor ready.
- **production_ready=false**: This branch contract is not production-ready.
- **public_claim_allowed=false**: No public claims are allowed.
