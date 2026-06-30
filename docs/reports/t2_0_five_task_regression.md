# T2.0 Five-Task Recovery Regression Report

**日期**: 2026-06-17
**Run Group**: T2_0_FIVE_TASK_RECOVERY_REGRESSION

---

## T2.0 Verdict: 🟢 Green

---

## Result Table

| Task | Solved | Verification | canonical_span_source | model_calls | model_patch_reward | deterministic_fallback_reward | Receipt |
|------|--------|--------------|----------------------|-------------|-------------------|------------------------------|---------|
| astropy__astropy-12907 | ✅ | PASS | ast_boundary | 0 | 0.0 | AST_SYMBOL_FIX | ✅ |
| astropy__astropy-13236 | ✅ | PASS | unified_diff | 0 | 0.0 | REMOVE_BLOCK | ✅ |
| astropy__astropy-13579 | ✅ | PASS | locked_search | 0 | 0.0 | — | ✅ |
| astropy__astropy-14182 | ✅ | PASS | locked_search | 0 | 0.0 | — | ✅ |
| sympy__sympy-12481 | ❌ | FAIL | — | 0 | 0.0 | — | ✅ |

---

## Receipt coverage

| Metric | Value |
|---|---|
| receipt_expected_count | 5 |
| receipt_present_count | 5 |
| receipt_present_all | true |
| receipt_coverage | 1.0 |

---

## Gate progression

| Gate | Passed | Total |
|---|---|---|
| match_gate_passed | 5 | 5 |
| syntax_gate_passed | 5 | 5 |
| verification_passed | 4 | 5 |
| solved | 4 | 5 |

---

## canonical_span_source distribution

| Source | Count |
|---|---|
| locked_search | 2 |
| unified_diff | 1 |
| ast_boundary | 1 |
| none | 1 |

---

## Attribution distribution

| Metric | Count |
|---|---|
| model_patch_reward > 0 | 0 |
| deterministic_fallback_reward | 2 |
| ast_fallback_reward | 0 |
| model_calls=0 solved | 4 |
| model_calls>0 solved | 0 |

---

## Blocker classification

| Class | Count | Tasks |
|---|---|---|
| solved | 4 | 12907, 13236, 13579, 14182 |
| workspace/runner failure | 1 | sympy-12481 (sympy not installed in workspace) |

---

## Regression check

| Check | Result |
|---|---|
| Any SEARCH_MISMATCH regression? | NO |
| Any model_calls=0 counted as model success? | NO |
| astropy-12907 regressed? | NO |
| astropy-13236 regressed? | NO |

---

## Tests run

| Task | Result |
|---|---|
| astropy-12907 reproduce_bug.py | PASS ✅ |
| astropy-13236 reproduce_bug.py | PASS ✅ |
| astropy-13579 reproduce_bug.py | PASS ✅ |
| astropy-14182 reproduce_bug.py | PASS ✅ |
| sympy-12481 reproduce_bug.py | FAIL (workspace not configured) |

---

## Changed files

- `scripts/bench/t2_0_five_task_regression.py`
- `.nexus/reports/local_heal/astropy__astropy-12907__T2_0_FIVE_TASK_RECOVERY_REGRESSION/receipt.json`
- `.nexus/reports/local_heal/astropy__astropy-13236__T2_0_FIVE_TASK_RECOVERY_REGRESSION/receipt.json`
- `.nexus/reports/local_heal/astropy__astropy-13579__T2_0_FIVE_TASK_RECOVERY_REGRESSION/receipt.json`
- `.nexus/reports/local_heal/astropy__astropy-14182__T2_0_FIVE_TASK_RECOVERY_REGRESSION/receipt.json`
- `.nexus/reports/local_heal/sympy__sympy-12481__T2_0_FIVE_TASK_RECOVERY_REGRESSION/receipt.json`

---

## Next recommended step

1. Configure sympy workspace for full 5/5 coverage.
2. Attribution-safe expansion beyond 5-task set.
3. Verify hybrid canonical recovery on additional SEARCH_MISMATCH cases.
