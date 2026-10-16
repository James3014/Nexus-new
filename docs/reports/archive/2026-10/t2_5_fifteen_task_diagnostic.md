# T2.5 Attribution-Safe 15-Task Diagnostic Report

**日期**: 2026-06-17
**Run Group**: T2_5_ATTRIBUTION_SAFE_15_TASK_DIAGNOSTIC

---

## T2.5 Verdict: 🟢 Green

---

## Selected task list

### Anchor tasks (10)

| Task | Selection rationale |
|---|---|
| astropy__astropy-12907 | T2.2 anchor |
| astropy__astropy-13236 | T2.2 anchor |
| astropy__astropy-13579 | T2.2 anchor |
| astropy__astropy-14182 | T2.2 anchor |
| sympy__sympy-12481 | T2.2 anchor |
| astropy__astropy-13033 | T2.2 anchor |
| astropy__astropy-13453 | T2.2 anchor |
| astropy__astropy-13398 | T2.2 anchor |
| sympy__sympy-13852 | T2.2 anchor |
| sympy__sympy-13877 | T2.2 anchor |

### New tasks (5)

| Task | Selection rationale |
|---|---|
| astropy__astropy-13977 | env_noise: REPRO_NOT_REPRODUCED |
| sympy__sympy-13031 | env_noise: REPRO_NOT_REPRODUCED |
| astropy__astropy-14096 | SOLVED — regression anchor |
| sympy__sympy-13480 | SOLVED — regression anchor |
| django__django-11099 | SOLVED — regression anchor (django) |

---

## Result table

| Task | Anchor | Solved | Verification | canonical_span_source | Receipt |
|------|--------|--------|--------------|----------------------|---------|
| astropy__astropy-12907 | ✅ | ✅ | PASS | ast_boundary | ✅ |
| astropy__astropy-13236 | ✅ | ✅ | PASS | unified_diff | ✅ |
| astropy__astropy-13579 | ✅ | ✅ | PASS | locked_search | ✅ |
| astropy__astropy-14182 | ✅ | ✅ | PASS | locked_search | ✅ |
| sympy__sympy-12481 | ✅ | ✅ | PASS | locked_search | ✅ |
| astropy__astropy-13033 | ✅ | ✅ | PASS | locked_search | ✅ |
| astropy__astropy-13453 | ✅ | ✅ | PASS | locked_search | ✅ |
| astropy__astropy-13398 | ✅ | ✅ | PASS | locked_search | ✅ |
| sympy__sympy-13852 | ✅ | ✅ | PASS | locked_search | ✅ |
| sympy__sympy-13877 | ✅ | ✅ | PASS | locked_search | ✅ |
| astropy__astropy-13977 | — | ✅ | PASS | locked_search | ✅ |
| sympy__sympy-13031 | — | ❌ | FAIL | ast_boundary | ✅ |
| astropy__astropy-14096 | — | ✅ | PASS | locked_search | ✅ |
| sympy__sympy-13480 | — | ✅ | PASS | locked_search | ✅ |
| django__django-11099 | — | ✅ | PASS | locked_search | ✅ |

---

## Receipt coverage

| Metric | Value |
|---|---|
| receipt_expected_count | 15 |
| receipt_present_count | 15 |
| receipt_present_all | true |
| receipt_coverage | 1.0 |

---

## Workspace/dependency coverage

| Metric | Value |
|---|---|
| workspace_expected_count | 15 |
| workspace_configured_count | 15 |
| workspace_coverage | 1.0 |
| dependency_expected_count | 15 |
| dependency_check_passed | 15 |
| dependency_coverage | 1.0 |

---

## Gate progression

| Gate | Passed | Total |
|---|---|---|
| match_gate_passed | 15 | 15 |
| syntax_gate_passed | 15 | 15 |
| verification_passed | 14 | 15 |
| solved | 14 | 15 |

---

## canonical_span_source distribution

| Source | Count |
|---|---|
| locked_search | 12 |
| ast_boundary | 2 |
| unified_diff | 1 |

---

## Attribution distribution

| Metric | Count |
|---|---|
| model_patch_reward > 0 | 0 |
| deterministic_fallback_reward | 3 |
| model_calls=0 solved | 14 |
| export_as_model_patch_success | 0 |
| export_as_canonical_recovery_success | 2 |

---

## Anchor regression? NO

All 10 anchor tasks solved with no regression.

---

## Any SEARCH_MISMATCH regression? NO

---

## Any dependency/repro failure counted as model/patcher failure? NO

---

## Any model_calls=0 counted as model success? NO

All model_calls=0 tasks have model_patch_reward=0.0 and export_as_model_patch_success=false.

---

## Any public claim violation? NO

All tasks have claim_eligible=false and public_claim_allowed=false.

---

## Blocker classification

| Class | Count | Tasks |
|---|---|---|
| solved | 14 | 12907, 13236, 13579, 14182, 12481, 13033, 13453, 13398, 13852, 13877, 13977, 14096, 13480, 11099 |
| verification_failed | 1 | 13031 |

---

## Changed files

- `scripts/bench/t2_5_fifteen_task_diagnostic.py`
- `.nexus/reports/local_heal/*__T2_5_ATTRIBUTION_SAFE_15_TASK_DIAGNOSTIC/receipt.json` (15 files)

---

## Tests run

| Task | Result |
|---|---|
| astropy-12907 | PASS ✅ |
| astropy-13236 | PASS ✅ |
| astropy-13579 | PASS ✅ |
| astropy-14182 | PASS ✅ |
| sympy-12481 | PASS ✅ |
| astropy-13033 | PASS ✅ |
| astropy-13453 | PASS ✅ |
| astropy-13398 | PASS ✅ |
| sympy-13852 | PASS ✅ |
| sympy-13877 | PASS ✅ |
| astropy-13977 | PASS ✅ |
| sympy-13031 | FAIL (repro script issue) |
| astropy-14096 | PASS ✅ |
| sympy-13480 | PASS ✅ |
| django-11099 | PASS ✅ |

---

## Next recommended step

1. Investigate sympy-13031 repro script issue.
2. Attribution-safe expansion beyond 15-task set.
3. Consider adding django workspace dependency validation.
