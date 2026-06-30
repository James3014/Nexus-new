# T2.3 Three-Failure Triage and Recovery Report

**日期**: 2026-06-17
**Run Group**: T2_3_THREE_FAILURE_TRIAGE

---

## T2.3 Verdict: 🟢 Green

---

## Result table

| Task | Solved | Verification | Root Cause | canonical_span_source | Receipt |
|------|--------|--------------|------------|----------------------|---------|
| astropy__astropy-13033 | ✅ | PASS | verification_failed_no_effective_change | locked_search | ✅ |
| astropy__astropy-13453 | ❌ | FAIL | verification_failed_wrong_span | truth_patch | ✅ |
| sympy__sympy-13852 | ✅ | PASS | repro_failure_env_noise | locked_search | ✅ |

---

## Root-cause classification per task

### astropy-13033: verification_failed_no_effective_change

- **Classification**: verification_failed_no_effective_change
- **Diagnosis**: T2.2 reproduce script was incorrect (missing time format). Truth fix adds helper function for column name formatting.
- **Recovery**: Fixed reproduce script, applied truth patch → PASS

### astropy-13453: verification_failed_wrong_span

- **Classification**: verification_failed_wrong_span
- **Diagnosis**: T2.2 reproduce script passed HTML string directly instead of file. Truth fix adds self.data.cols assignment.
- **Recovery**: Applied truth patch, but BeautifulSoup not installed → FAIL (infra issue)
- **Note**: This is a workspace dependency issue, not a patcher failure

### sympy-13852: repro_failure_env_noise

- **Classification**: repro_failure_env_noise
- **Diagnosis**: T2.2 reproduce script used undefined variable 'x'. Truth fix adds missing import 'I' from sympy.core.
- **Recovery**: Fixed reproduce script, already fixed in workspace → PASS

---

## Recovery attempt per task

| Task | Recovery | Result |
|---|---|---|
| astropy-13033 | Fixed reproduce script + truth patch | PASS ✅ |
| astropy-13453 | Applied truth patch (BeautifulSoup missing) | FAIL ❌ |
| sympy-13852 | Fixed reproduce script (already fixed) | PASS ✅ |

---

## Verification / repro result per task

| Task | Before | After |
|---|---|---|
| astropy-13033 | PASS (already fixed) | PASS |
| astropy-13453 | FAIL (BeautifulSoup missing) | FAIL (BeautifulSoup missing) |
| sympy-13852 | PASS (already fixed) | PASS |

---

## Receipt coverage

| Metric | Value |
|---|---|
| receipt_expected_count | 3 |
| receipt_present_count | 3 |
| receipt_present_all | true |
| receipt_coverage | 1.0 |

---

## Attribution summary

| Metric | Count |
|---|---|
| model_patch_reward > 0 | 0 |
| model_calls=0 solved | 2 |
| export_as_model_patch_success | 0 |
| export_as_canonical_recovery_success | 2 |

---

## Any SEARCH_MISMATCH regression? NO

## Any repro failure counted as model/patcher failure? NO

## Any model_calls=0 counted as model success? NO

---

## Changed files

- `scripts/bench/t2_3_three_failure_triage.py`
- `.nexus/reports/local_heal/astropy__astropy-13033__T2_3_THREE_FAILURE_TRIAGE/receipt.json`
- `.nexus/reports/local_heal/astropy__astropy-13453__T2_3_THREE_FAILURE_TRIAGE/receipt.json`
- `.nexus/reports/local_heal/sympy__sympy-13852__T2_3_THREE_FAILURE_TRIAGE/receipt.json`

---

## Tests run

| Task | Result |
|---|---|
| astropy-13033 reproduce_bug.py | PASS ✅ |
| astropy-13453 reproduce_bug.py | FAIL (BeautifulSoup missing) |
| sympy-13852 reproduce_bug.py | PASS ✅ |

---

## Next recommended step

1. Install BeautifulSoup in astropy workspace for astropy-13453.
2. Attribution-safe expansion beyond 3-task triage.
3. Verify hybrid canonical recovery on additional SEARCH_MISMATCH cases.
