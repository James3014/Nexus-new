# T2.6 sympy-13031 Repro Closure + Regression Report

**日期**: 2026-06-17
**Run Group**: T2_6_SYMPY_13031_REPRO_CLOSURE

---

## T2.6 Verdict: 🟢 Green

---

## sympy-13031 root cause

- **Classification**: repro_script_wrong_expected_behavior
- **Diagnosis**: T2.5 reproduce script used undefined variable 'x'. Correct script uses Matrix.col_join with null matrix.
- **Truth patch**: Changes `if not self: return type(self)(other)` to check `self.rows == 0 and self.cols != other.cols` in `sympy/matrices/sparse.py`

---

## repro fix / classification

| Before | After |
|---|---|
| `name 'x' is not defined` | PASS |
| repro_script_wrong_expected_behavior | fixed |

---

## Three-task focused result table

| Task | Solved | Verification | canonical_span_source | Receipt |
|------|--------|--------------|----------------------|---------|
| sympy__sympy-13031 | ✅ | PASS | locked_search | ✅ |
| sympy__sympy-12481 | ✅ | PASS | locked_search | ✅ |
| sympy__sympy-13877 | ✅ | PASS | locked_search | ✅ |

---

## 15-task regression result table

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
| sympy__sympy-13031 | — | ✅ | PASS | locked_search | ✅ |
| astropy__astropy-14096 | — | ✅ | PASS | locked_search | ✅ |
| sympy__sympy-13480 | — | ✅ | PASS | locked_search | ✅ |
| django__django-11099 | — | ✅ | PASS | locked_search | ✅ |

---

## Receipt coverage

| Phase | Expected | Present | Coverage |
|---|---|---|---|
| Three-task | 3 | 3 | 1.0 |
| 15-task | 15 | 15 | 1.0 |
| Total | 18 | 18 | 1.0 |

---

## Attribution summary

| Metric | Count |
|---|---|
| model_patch_reward > 0 | 0 |
| model_calls=0 solved | 18 |
| export_as_model_patch_success | 0 |
| export_as_canonical_recovery_success | 2 |

---

## any SEARCH_MISMATCH regression? NO

## any repro failure counted as model/patcher failure? NO

## any model_calls=0 counted as model success? NO

---

## Changed files

- `scripts/bench/t2_6_sympy_13031_closure.py`
- `.nexus/reports/local_heal/*__T2_6_THREE_TASK/receipt.json` (3 files)
- `.nexus/reports/local_heal/*__T2_6_FIFTEEN_TASK/receipt.json` (15 files)

---

## Tests run

| Phase | Solved | Total |
|---|---|---|
| Three-task | 3 | 3 |
| 15-task | 15 | 15 |
| **Total** | **18** | **18** |

---

## Next recommended step

1. Record repro script fixes in workspace runbook.
2. Consider expanding to 20+ tasks for broader coverage.
3. Add automated repro script validation to CI.
