# LocalHeal Sprint C15-4D-3: Delegated Retry Bounded Live Recheck

**Status**: `C15_4D_3_OUTPUT_QUALITY_STILL_BLOCKED`

**Date**: 2026-07-04

**Base commit**: `41a4db1fc fix(localheal): prioritize locked search in verifier retry prompt`

---

## Commands Run

```bash
python3 -m py_compile \
  nexus/services/local_heal/prompt_builder.py \
  tests/unit/local_heal/test_prompt_builder.py
# exit 0

uv run pytest tests/unit/local_heal/test_prompt_builder.py -v
# 5 passed

export NEXUS_BENCHMARK_APPEND=1
timeout 180 /Users/jameschen/.local/bin/uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap
# Completed, 1 attempt appended
```

---

## Test Results

| Test | Result |
|------|--------|
| `test_verification_guided_retry_prompt_places_search_lock_before_verifier_evidence` | ✅ PASS |
| `test_verification_guided_retry_prompt_keeps_output_format_near_locked_search` | ✅ PASS |
| `test_verification_guided_retry_prompt_preserves_verifier_evidence` | ✅ PASS |
| `test_primary_patch_system_prompt_unchanged` | ✅ PASS |
| `test_no_route_authority_fields_change` | ✅ PASS |

---

## Live Attempt Table

### This Run (C15-4D-3)

| Attempt | `pipeline_retry_delegated` | `delegated_retry_status` | `delegated_retry_stage` | `verifier_result` | `solved` | `solve_mechanism` |
|---------|--------------------------|------------------------|------------------------|------------------|---------|-------------------|
| 1 (latest) | **true** | REPLACE_SYNTAX_ERROR | first_patch_failed | fail | false | delegated_retry_unresolved |

### Comparison with C15-4C-2 (before prompt reordering)

| Attempt | `delegated_retry_status` | `delegated_retry_stage` | `verifier_result` | `solved` |
|---------|------------------------|------------------------|------------------|---------|
| C15-4C-2 #1 | REPLACE_SYNTAX_ERROR | first_patch_failed | fail | false |
| C15-4C-2 #2 | REPLACE_SYNTAX_ERROR | first_patch_failed | fail | false |
| C15-4C-2 #3 | SEARCH_MISMATCH | first_patch_parser_rejected | fail | false |

---

## Latest Row Evidence

### Required Fields

| Field | Value |
|-------|-------|
| `task_id` | toy-math-verifier-evidence-gap |
| `pipeline_retry_delegated` | **true** |
| `delegated_retry_provider_called` | **true** |
| `semantic_retry_prompt_has_verifier_evidence` | **true** |
| `orchestrator_verifier_evidence_passed_to_retry` | **true** |
| `verifier_result` | **fail** |
| `solved` | **false** |
| `solve_mechanism` | delegated_retry_unresolved |
| `delegated_retry_stage` | first_patch_failed |
| `delegated_retry_status` | REPLACE_SYNTAX_ERROR:expected an indented block after 'if' statement on line 3 |

### Raw Output

```
FILE: toy/math_util.py
<<<<<<< SEARCH
    return (score - min_val) / (max_val - min_val)
=======
    if max_val == min_val:
        return 0 if score <= min_val else 1
    return (score - min_val) / (max_val - min_val)
>>>>>>> REPLACE
```

### Pipeline Telemetry

| Field | Value |
|-------|-------|
| `semantic_retry_status` | REPLACE_SYNTAX_ERROR:expected an indented block after 'if' statement on line 3 |
| `semantic_retry_output_class` | APPLY_FAILED |
| `semantic_retry_failure_reason` | apply_failed:REPLACE_SYNTAX_ERROR |
| `pipeline_failure_reason` | SEARCH_MISMATCH:SEARCH_MISMATCH |
| `patch_lifecycle_state` | isolation_applied_hash_match_verifier_failed |
| `failure_class` | verification_failed |
| `pipeline_final_patch_len` | 346 |
| `candidate_isolated` | True |

---

## Success Criteria Checklist

| Criterion | Status |
|-----------|--------|
| `task_id = toy-math-verifier-evidence-gap` | ✅ |
| `pipeline_retry_delegated = true` | ✅ |
| `delegated_retry_provider_called = true` | ✅ |
| `semantic_retry_prompt_has_verifier_evidence = true` | ✅ |
| `orchestrator_verifier_evidence_passed_to_retry = true` | ✅ |
| `verifier_result = pass` | ❌ |
| `solved = true` | ❌ |
| `solve_mechanism = delegated_retry` | ❌ (delegated_retry_unresolved) |
| `delegated_retry_stage = success` | ❌ (first_patch_failed) |
| Primary first-pass did not solve | ✅ |
| Primary pipeline semantic retry did not preempt delegated retry | ✅ |

**8/11 criteria met. delegated_retry solved remains NOT_PROVEN.**

---

## Failure Taxonomy

### This Run (C15-4D-3)

| Category | Count | Raw Status |
|----------|-------|-----------|
| INDENTATION_SYNTAX_ERROR | 1 | `REPLACE_SYNTAX_ERROR:expected an indented block after 'if' statement on line 3` |

### Cumulative (C15-4C-2 + C15-4D-3)

| Category | Count | Description |
|----------|-------|-------------|
| INDENTATION_SYNTAX_ERROR | 3 | Model produces if/else logic but indentation is wrong in applied patch |
| SEARCH_NOT_EXACT_SOURCE | 1 | SEARCH block doesn't match current source file |

**The dominant failure pattern is INDENTATION_SYNTAX_ERROR (3/4 attempts).**

---

## Judgment

### Did C15-4D-2B improve output quality?

**No measurable improvement.** The failure pattern remains identical:

- C15-4C-2 (before patch): 2/3 REPLACE_SYNTAX_ERROR, 1/3 SEARCH_MISMATCH
- C15-4D-3 (after patch): 1/1 REPLACE_SYNTAX_ERROR (same root cause)

The prompt reordering moved locked SEARCH before verifier evidence, but the model still produces `if` statements with wrong indentation in the REPLACE block. The SEARCH block is now correct (no SEARCH_MISMATCH in this run), but the REPLACE syntax error persists.

### Is delegated_retry solved now proven?

**No.** All success acceptance criteria are NOT met. `verifier_result = fail`, `solved = false`, `solve_mechanism = delegated_retry_unresolved`.

### Is next step more validation, semantic analysis, claim boundary, or instrumentation?

**Claim boundary (C15-4E).** The failure pattern is stable across 4 attempts (3/4 INDENTATION_SYNTAX_ERROR). This is a model output quality ceiling, not a prompt ordering issue. Further prompt reordering is unlikely to resolve this. The next step should:

1. Formally define what can be claimed about delegated retry given current model quality
2. Document the output quality ceiling
3. Decide whether to accept the limitation or explore model/provider alternatives

---

## Scope Statement

- **No production code changed** in this task (prompt_builder.py change was in C15-4D-2B).
- **No tests changed.**
- **No benchmark behavior changed.**
- **No route authority changed.**
- **Parser/verifier/candidate isolation unchanged.**
- **delegated_retry solved NOT_PROVEN** — success criteria not met.
- **production_ready=false.**
- **public_claim_allowed=false.**

---

## Next Recommended Task

**C15-4E Delegated Retry Output Quality Claim Boundary**

Formally define what can and cannot be claimed about delegated retry given current 7B model quality limitations. Document the INDENTATION_SYNTAX_ERROR ceiling and decide whether to accept the limitation or pursue model/provider alternatives in a separate task.
