# T2.4 Dependency Closure + Regression Report

**日期**: 2026-06-17
**Run Group**: T2_4_DEPENDENCY_CLOSURE_REGRESSION

---

## T2.4 Verdict: 🟢 Green

---

## BeautifulSoup dependency root cause

- **Problem**: astropy workspace lacked `beautifulsoup4` and `lxml` packages
- **Impact**: astropy-13453 HTML reading tests failed with "BeautifulSoup must be installed"
- **Classification**: workspace dependency issue, not patcher/model failure

---

## Dependency fix

```bash
uv pip install --python .venv_astropy/bin/python beautifulsoup4 lxml
```

Installed:
- beautifulsoup4==4.15.0
- lxml==6.1.1
- soupsieve==2.8.4

---

## Three-task result table

| Task | Solved | Verification | canonical_span_source | dependency_check | Receipt |
|------|--------|--------------|----------------------|------------------|---------|
| astropy__astropy-13033 | ✅ | PASS | locked_search | ✅ | ✅ |
| astropy__astropy-13453 | ✅ | PASS | locked_search | ✅ | ✅ |
| sympy__sympy-13852 | ✅ | PASS | locked_search | ✅ | ✅ |

---

## astropy-13453 result after dependency fix

| Field | Value |
|---|---|
| solved | true |
| verification_result | PASS |
| import_bs4_success | true |
| workspace_dependency_fixed | true |
| bug_reproduced_before_patch | true |
| truth_patch_applied | true |
| canonical_span_source | locked_search |

---

## Receipt coverage

| Metric | Value |
|---|---|
| receipt_expected_count | 3 |
| receipt_present_count | 3 |
| receipt_present_all | true |
| receipt_coverage | 1.0 |

---

## Dependency validation

| Dependency | Status |
|---|---|
| beautifulsoup4 | ✅ installed |
| lxml | ✅ installed |
| import bs4 success | ✅ |
| 13033 dependency_check | ✅ |
| 13453 dependency_check | ✅ |
| 13852 dependency_check | ✅ |

---

## Gate progression

| Gate | Passed | Total |
|---|---|---|
| match_gate_passed | 3 | 3 |
| syntax_gate_passed | 3 | 3 |
| verification_passed | 3 | 3 |
| solved | 3 | 3 |

---

## Any regression from T2.3? NO

- astropy-13033: still PASS ✅
- astropy-13453: PASS (was FAIL due to missing bs4)
- sympy-13852: still PASS ✅

---

## Any dependency failure counted as model/patcher failure? NO

## Any model_calls=0 counted as model success? NO

---

## Attribution summary

| Task | model_calls | model_patch_reward | deterministic_fallback_reward |
|---|---|---|---|
| astropy-13033 | 0 | 0.0 | — |
| astropy-13453 | 0 | 0.0 | — |
| sympy-13852 | 0 | 0.0 | — |

---

## Changed files

- `scripts/bench/t2_4_dependency_closure.py`
- `.nexus/reports/local_heal/astropy__astropy-13033__T2_4_DEPENDENCY_CLOSURE_REGRESSION/receipt.json`
- `.nexus/reports/local_heal/astropy__astropy-13453__T2_4_DEPENDENCY_CLOSURE_REGRESSION/receipt.json`
- `.nexus/reports/local_heal/sympy__sympy-13852__T2_4_DEPENDENCY_CLOSURE_REGRESSION/receipt.json`

---

## Tests run

| Task | Result |
|---|---|
| astropy-13033 reproduce_bug.py | PASS ✅ |
| astropy-13453 reproduce_bug.py | PASS ✅ |
| sympy-13852 reproduce_bug.py | PASS ✅ |

---

## Next recommended step

1. Record dependency setup in workspace runbook/bootstrap script.
2. Attribution-safe expansion beyond 3-task triage.
3. Verify hybrid canonical recovery on additional SEARCH_MISMATCH cases.
