# T2.8 Attribution-Safe 20-Task Diagnostic Report

**日期**: 2026-06-17
**Run Group**: T2_8_ATTRIBUTION_SAFE_20_TASK_DIAGNOSTIC

---

## T2.8 Verdict: 🟢 Green

---

## Required count fields

| Field | Value |
|---|---|
| raw_task_count | 20 |
| deduped_task_count | 20 |
| anchor_task_count | 15 |
| selected_new_task_count | 5 |
| true_new_task_count | 5 |
| duplicate_anchor_selected_as_new_count | 0 |
| duplicate_anchor_selected_as_new_list | (none) |
| effective_expansion_count | 5 |

---

## Selected 20-task list

### Anchor tasks (15)

| Task | Selection rationale |
|---|---|
| astropy__astropy-12907 | T2.7 anchor |
| astropy__astropy-13236 | T2.7 anchor |
| astropy__astropy-13579 | T2.7 anchor |
| astropy__astropy-14182 | T2.7 anchor |
| sympy__sympy-12481 | T2.7 anchor |
| astropy__astropy-13033 | T2.7 anchor |
| astropy__astropy-13453 | T2.7 anchor |
| astropy__astropy-13398 | T2.7 anchor |
| sympy__sympy-13852 | T2.7 anchor |
| sympy__sympy-13877 | T2.7 anchor |
| astropy__astropy-13977 | T2.7 anchor |
| sympy__sympy-13031 | T2.7 anchor |
| astropy__astropy-14096 | T2.7 anchor |
| sympy__sympy-13480 | T2.7 anchor |
| django__django-11099 | T2.7 anchor |

### New tasks (5)

| Task | Selection rationale | source_failure_class |
|---|---|---|
| astropy__astropy-14365 | SOLVED — regression anchor | SOLVED |
| sympy__sympy-12419 | prior patch_mismatch | patch_mismatch |
| sympy__sympy-13647 | prior patch_mismatch | patch_mismatch |
| astropy__astropy-14309 | prior env_noise | env_noise |
| sympy__sympy-11618 | SOLVED — regression anchor | SOLVED |

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
| astropy__astropy-13977 | ✅ | ✅ | PASS | locked_search | ✅ |
| sympy__sympy-13031 | ✅ | ✅ | PASS | locked_search | ✅ |
| astropy__astropy-14096 | ✅ | ✅ | PASS | locked_search | ✅ |
| sympy__sympy-13480 | ✅ | ✅ | PASS | locked_search | ✅ |
| django__django-11099 | ✅ | ✅ | PASS | locked_search | ✅ |
| astropy__astropy-14365 | — | ✅ | PASS | locked_search | ✅ |
| sympy__sympy-12419 | — | ✅ | PASS | locked_search | ✅ |
| sympy__sympy-13647 | — | ✅ | PASS | locked_search | ✅ |
| astropy__astropy-14309 | — | ✅ | PASS | locked_search | ✅ |
| sympy__sympy-11618 | — | ✅ | PASS | locked_search | ✅ |

---

## Receipt coverage

| Metric | Value |
|---|---|
| receipt_expected_count | 20 |
| receipt_present_count | 20 |
| receipt_present_all | true |
| receipt_coverage | 1.0 |

---

## Workspace/dependency coverage

| Metric | Value |
|---|---|
| workspace_expected_count | 20 |
| workspace_configured_count | 20 |
| workspace_coverage | 1.0 |

---

## Gate progression

| Gate | Passed | Total |
|---|---|---|
| match_gate_passed | 20 | 20 |
| syntax_gate_passed | 20 | 20 |
| verification_passed | 20 | 20 |
| solved | 20 | 20 |

---

## canonical_span_source distribution

| Source | Count |
|---|---|
| locked_search | 18 |
| ast_boundary | 1 |
| unified_diff | 1 |

---

## Attribution distribution

| Metric | Count |
|---|---|
| model_patch_reward > 0 | 0 |
| deterministic_fallback_reward | 2 |
| model_calls=0 solved | 20 |
| export_as_model_patch_success | 0 |
| export_as_canonical_recovery_success | 2 |

---

## Anchor regression check

All 15 anchor tasks solved with no regression.

---

## SEARCH_MISMATCH regression check

NO

---

## Public claim violation check

NO

All tasks have claim_eligible=false and public_claim_allowed=false.

---

## model_calls=0 attribution check

All model_calls=0 tasks have model_patch_reward=0.0 and export_as_model_patch_success=false.

---

## Blocker classification

| Class | Count |
|---|---|
| solved | 20 |

---

## Changed files

- `scripts/bench/t2_8_twenty_task_diagnostic.py`
- `.nexus/reports/local_heal/*__T2_8_ATTRIBUTION_SAFE_20_TASK_DIAGNOSTIC/receipt.json` (20 files)

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
| sympy-13031 | PASS ✅ |
| astropy-14096 | PASS ✅ |
| sympy-13480 | PASS ✅ |
| django-11099 | PASS ✅ |
| astropy-14365 | PASS ✅ |
| sympy-12419 | PASS ✅ |
| sympy-13647 | PASS ✅ |
| astropy-14309 | PASS ✅ |
| sympy-11618 | PASS ✅ |

---

## Next recommended step

1. Prepare T2.9 20-task baseline freeze / replay plan.
2. Do not execute T2.9 unless requested.
