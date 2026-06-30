# T2.1 Five-Task Recovery Regression Report

**日期**: 2026-06-17
**Run Group**: T2_1_FIVE_TASK_WORKSPACE_RECOVERY

---

## Claim Boundary

| Field | Value |
|---|---|
| simulated | false |
| claim_eligible | false |
| public_claim_allowed | false |
| claim_block_reason | focused_internal_regression |
| receipt_expected_count | 5 |
| receipt_present_count | 5 |
| receipt_present_all | true |
| receipt_coverage | 1.0 |
| workspace_expected_count | 5 |
| workspace_configured_count | 5 |
| workspace_coverage | 1.0 |
| raw_task_count | 5 |
| deduped_task_count | 5 |

---

## T2.1 Verdict: 🟢 Green (Strong Green: 5/5 PASS)

---

## Five-task result table

| Task | Solved | Verification | canonical_span_source | model_calls | model_patch_reward | deterministic_fallback_reward | Receipt |
|------|--------|--------------|----------------------|-------------|-------------------|------------------------------|---------|
| astropy__astropy-12907 | ✅ | PASS | ast_boundary | 0 | 0.0 | AST_SYMBOL_FIX | ✅ |
| astropy__astropy-13236 | ✅ | PASS | unified_diff | 0 | 0.0 | REMOVE_BLOCK | ✅ |
| astropy__astropy-13579 | ✅ | PASS | locked_search | 0 | 0.0 | — | ✅ |
| astropy__astropy-14182 | ✅ | PASS | locked_search | 0 | 0.0 | — | ✅ |
| sympy__sympy-12481 | ✅ | PASS | locked_search | 0 | 0.0 | — | ✅ |

---

## Receipt coverage

| Metric | Value |
|---|---|
| receipt_expected_count | 5 |
| receipt_present_count | 5 |
| receipt_present_all | true |
| receipt_coverage | 1.0 |

---

## Workspace coverage

| Workspace | Configured | Python | Import |
|---|---|---|---|
| astropy | ✅ | 3.10 (.venv_astropy) | ✅ |
| sympy | ✅ | 3.9 (.venv39) | ✅ |

---

## Gate progression

| Gate | Passed | Total |
|---|---|---|
| match_gate_passed | 5 | 5 |
| syntax_gate_passed | 5 | 5 |
| verification_passed | 5 | 5 |
| solved | 5 | 5 |

---

## canonical_span_source distribution

| Source | Count |
|---|---|
| locked_search | 3 |
| unified_diff | 1 |
| ast_boundary | 1 |

---

## Attribution distribution

| Metric | Count |
|---|---|
| model_patch_reward > 0 | 0 |
| deterministic_fallback_reward | 2 |
| ast_fallback_reward | 0 |
| model_calls=0 solved | 5 |

---

## Workspace failure classification

| Task | failure_class | count_as_patcher_failure | count_as_model_failure |
|---|---|---|---|
| astropy-12907 | SOLVED | false | false |
| astropy-13236 | SOLVED | false | false |
| astropy-13579 | SOLVED | false | false |
| astropy-14182 | SOLVED | false | false |
| sympy-12481 | SOLVED | false | false |

---

## model_calls=0 solved section

All 5 tasks solved with model_calls=0. None exported as model patch success.

| Task | model_calls | model_patch_reward | export_as_model_patch_success |
|---|---|---|---|
| astropy-12907 | 0 | 0.0 | false |
| astropy-13236 | 0 | 0.0 | false |
| astropy-13579 | 0 | 0.0 | false |
| astropy-14182 | 0 | 0.0 | false |
| sympy-12481 | 0 | 0.0 | false |

---

## Export eligibility section

| Task | export_as_model_patch_success | export_as_canonical_recovery_success | export_as_internal_infra_failure | export_as_public_claim |
|---|---|---|---|---|
| astropy-12907 | false | true | false | false |
| astropy-13236 | false | true | false | false |
| astropy-13579 | false | true | false | false |
| astropy-14182 | false | true | false | false |
| sympy-12481 | false | true | false | false |

---

## No-public-claim statement

**This is a focused internal regression. No public benchmark claims are made or allowed.**

- claim_eligible=false for all tasks
- public_claim_allowed=false for all tasks
- claim_block_reason=focused_internal_regression

---

## Regression from T2.0 check

| Check | Result |
|---|---|
| astropy-12907 regressed? | NO |
| astropy-13236 regressed? | NO |
| astropy-13579 regressed? | NO |
| astropy-14182 regressed? | NO |
| sympy-12481 regressed? | NO (was workspace_not_configured, now solved) |
| SEARCH_MISMATCH regression? | NO |

---

## Tests run

| Task | Result |
|---|---|
| astropy-12907 reproduce_bug.py | PASS ✅ |
| astropy-13236 reproduce_bug.py | PASS ✅ |
| astropy-13579 reproduce_bug.py | PASS ✅ |
| astropy-14182 reproduce_bug.py | PASS ✅ |
| sympy-12481 reproduce_bug.py | PASS ✅ |

---

## Next recommended step

1. Attribution-safe expansion beyond 5-task set.
2. Verify hybrid canonical recovery on additional SEARCH_MISMATCH cases.
3. Separate deterministic/canonical recovery rows from model patch success rows in S2T/export.
