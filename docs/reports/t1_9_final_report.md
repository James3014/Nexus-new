# T1.9 Two-Task Focused Regression — Final Report

**日期**: 2026-06-17
**Run Group**: T1_9_FOCUSED_REGRESSION

---

## T1.9 Verdict: 🟢 Green

---

## Result Summary

| Task | Solved | Verification | canonical_span_source | model_calls | model_patch_reward | deterministic_fallback_reward | Receipt |
|------|--------|--------------|----------------------|-------------|-------------------|------------------------------|---------|
| astropy__astropy-13236 | ✅ | PASS | unified_diff | 0 | 0.0 | REMOVE_BLOCK | ✅ |
| astropy__astropy-12907 | ✅ | PASS | ast_boundary | 0 | 0.0 | AST_BOUNDARY_EXTRACT | ✅ |

---

## astropy-13236 result

```
instance_id:            astropy__astropy-13236
solved:                 true
verification_result:    PASS
canonical_span_source:  unified_diff
canonical_span_confidence: 0.9
model_calls:            0
model_patch_reward:     0.0
deterministic_fallback_reward: REMOVE_BLOCK
receipt_present:        true
receipt_coverage:       1.0
match_gate_passed:      true
syntax_gate_passed:     true
failure_class:          SOLVED
search_locked:          true
same_span_retry:        true
semantic_retry_count:   1
semantic_retry_mode:    verification_guided
verifier_result_after_retry: PASS
behavior_delta_verified: true
llm_replace_success:    false
deterministic_fallback_used: true
```

---

## astropy-12907 result

```
instance_id:            astropy__astropy-12907
solved:                 true
verification_result:    PASS
canonical_span_source:  ast_boundary
canonical_span_confidence: 0.8
model_calls:            0
model_patch_reward:     0.0
ast_fallback_reward:    AST_BOUNDARY_EXTRACT
receipt_present:        true
receipt_coverage:       1.0
match_gate_passed:      true
syntax_gate_passed:     true
failure_class:          SOLVED
target_symbol:          _cstack
target_symbol_source:   ast_boundary
target_symbol_confidence: 0.8
ast_symbol_found:       true
ast_symbol_span_start:  219
ast_symbol_span_end:    247
fallback_used:          true
fallback_reason:        SEARCH_MISMATCH from LLM — using AST boundary fallback
```

---

## Receipt coverage

| Task | receipt_present | receipt_coverage |
|------|-----------------|------------------|
| astropy-13236 | true | 1.0 |
| astropy-12907 | true | 1.0 |

---

## canonical_span_source per task

- astropy-13236: `unified_diff`
- astropy-12907: `ast_boundary`

---

## Attribution per task

| Task | model_calls | model_patch_reward | deterministic_fallback_reward |
|------|-------------|-------------------|------------------------------|
| astropy-13236 | 0 | 0.0 | REMOVE_BLOCK |
| astropy-12907 | 0 | 0.0 | AST_BOUNDARY_EXTRACT |

---

## Any SEARCH_MISMATCH regression? NO

## Any model_calls=0 counted as model success? NO

---

## Changed files

- `nexus/services/local_heal/canonical_span.py`
- `nexus/services/local_heal/orchestrator.py`
- `nexus/services/local_heal/prompt_builder.py`
- `nexus/services/local_heal/context.py`
- `nexus/services/local_heal/receipt.py`
- `tests/unit/test_canonical_span.py`
- `scripts/bench/t1_9_two_task_regression.py`
- `docs/reports/t1_9_two_task_focused_regression.md`

---

## Tests run

- local_heal tests: 38/38 ✅
- canonical_span tests: 9/9 ✅
- reproduce_bug.py (13236): PASS ✅
- reproduce_bug.py (12907): PASS ✅

---

## Next blocker

1. Attribution-safe expansion beyond two focused tasks.
2. Verify hybrid canonical recovery on additional SEARCH_MISMATCH cases.
3. Separate deterministic/canonical recovery rows from model patch success rows in S2T/export.
4. Optional: improve LLM prompt for block removal, but do not treat it as current blocker.
