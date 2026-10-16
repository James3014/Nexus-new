# T2.2 Attribution-Safe 10-Task Recovery Diagnostic Report

**日期**: 2026-06-17
**Run Group**: T2_2_ATTRIBUTION_SAFE_10_TASK_DIAGNOSTIC

---

## T2.2 Verdict: 🟢 Green

---

## Selected task list

### Anchor tasks (5)

| Task | Selection rationale |
|---|---|
| astropy__astropy-12907 | T2.1 anchor — ast_boundary recovery |
| astropy__astropy-13236 | T2.1 anchor — unified_diff + deterministic REMOVE_BLOCK |
| astropy__astropy-13579 | T2.1 anchor — locked_search |
| astropy__astropy-14182 | T2.1 anchor — locked_search |
| sympy__sympy-12481 | T2.1 anchor — locked_search (workspace fixed) |

### New tasks (5)

| Task | Selection rationale |
|---|---|
| astropy__astropy-13033 | patch_mismatch: NO_EFFECTIVE_CHANGE — tests semantic fix capability |
| astropy__astropy-13453 | semantic_wrong: VERIFICATION_FAILED — tests verification-guided retry |
| astropy__astropy-13398 | semantic_wrong: VERIFICATION_FAILED — tests single-line semantic fix |
| sympy__sympy-13852 | env_noise: REPRO_NOT_REPRODUCED — tests workspace reproducibility |
| sympy__sympy-13877 | env_noise: REPRO_ENVIRONMENT_FAILURE — tests sympy import stability |

---

## Result table

| Task | Anchor | Solved | Verification | canonical_span_source | model_calls | model_patch_reward | Receipt |
|------|--------|--------|--------------|----------------------|-------------|-------------------|---------|
| astropy__astropy-12907 | ✅ | ✅ | PASS | ast_boundary | 0 | 0.0 | ✅ |
| astropy__astropy-13236 | ✅ | ✅ | PASS | unified_diff | 0 | 0.0 | ✅ |
| astropy__astropy-13579 | ✅ | ✅ | PASS | locked_search | 0 | 0.0 | ✅ |
| astropy__astropy-14182 | ✅ | ✅ | PASS | locked_search | 0 | 0.0 | ✅ |
| sympy__sympy-12481 | ✅ | ✅ | PASS | locked_search | 0 | 0.0 | ✅ |
| astropy__astropy-13033 | — | ❌ | FAIL | none | 0 | 0.0 | ✅ |
| astropy__astropy-13453 | — | ❌ | FAIL | ast_boundary | 0 | 0.0 | ✅ |
| astropy__astropy-13398 | — | ✅ | PASS | locked_search | 0 | 0.0 | ✅ |
| sympy__sympy-13852 | — | ❌ | FAIL | ast_boundary | 0 | 0.0 | ✅ |
| sympy__sympy-13877 | — | ✅ | PASS | locked_search | 0 | 0.0 | ✅ |

---

## Receipt coverage

| Metric | Value |
|---|---|
| receipt_expected_count | 10 |
| receipt_present_count | 10 |
| receipt_present_all | true |
| receipt_coverage | 1.0 |

---

## Workspace coverage

| Metric | Value |
|---|---|
| workspace_expected_count | 10 |
| workspace_configured_count | 10 |
| workspace_coverage | 1.0 |
| workspace_failure_count | 0 |

---

## Gate progression

| Gate | Passed | Total |
|---|---|---|
| match_gate_passed | 10 | 10 |
| syntax_gate_passed | 10 | 10 |
| verification_passed | 7 | 10 |
| solved | 7 | 10 |

---

## canonical_span_source distribution

| Source | Count |
|---|---|
| locked_search | 5 |
| ast_boundary | 3 |
| unified_diff | 1 |
| none | 1 |

---

## Attribution distribution

| Metric | Count |
|---|---|
| model_patch_reward > 0 | 0 |
| deterministic_fallback_reward | 4 |
| ast_fallback_reward | 0 |
| model_calls=0 solved | 7 |
| model_calls>0 solved | 0 |
| export_as_model_patch_success | 0 |
| export_as_canonical_recovery_success | 7 |

---

## T2.1 anchor regression? NO

All 5 anchor tasks solved with no regression.

---

## Any SEARCH_MISMATCH regression? NO

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
| solved | 7 | 12907, 13236, 13579, 14182, 12481, 13398, 13877 |
| verification_failed | 2 | 13033, 13453 |
| repro_failure | 1 | 13852 |

---

## Changed files

- `scripts/bench/t2_2_ten_task_diagnostic.py`
- `.nexus/reports/local_heal/*__T2_2_ATTRIBUTION_SAFE_10_TASK_DIAGNOSTIC/receipt.json` (10 files)

---

## Tests run

| Task | Result |
|---|---|
| astropy-12907 reproduce_bug.py | PASS ✅ |
| astropy-13236 reproduce_bug.py | PASS ✅ |
| astropy-13579 reproduce_bug.py | PASS ✅ |
| astropy-14182 reproduce_bug.py | PASS ✅ |
| sympy-12481 reproduce_bug.py | PASS ✅ |
| astropy-13033 reproduce_bug.py | FAIL (verification_failed) |
| astropy-13453 reproduce_bug.py | FAIL (verification_failed) |
| astropy-13398 reproduce_bug.py | PASS ✅ |
| sympy-13852 reproduce_bug.py | FAIL (repro_failure) |
| sympy-13877 reproduce_bug.py | PASS ✅ |

---

## Next recommended step

1. Investigate astropy-13033 and astropy-13453 verification failures.
2. Investigate sympy-13852 repro failure.
3. Attribution-safe expansion beyond 10-task set.
