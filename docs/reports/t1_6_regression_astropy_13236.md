# T1.6 Regression: astropy-13236 Rerun Report

**日期**：2026-06-17  
**任務**：T1.6 regression check for astropy-13236

---

## Verdict: 🟢 Green

| 指標 | 結果 |
|---|---|
| astropy-13236 | SOLVED (regression check passed) |
| canonical_span_source | unified_diff |
| search_locked | true |
| same_span_retry | true |
| semantic_retry_count | 1 |
| verifier_result_after_retry | PASS |
| behavior_delta_verified | true |
| receipt_present | true |
| receipt_coverage | 1.0 |

---

## Telemetry

| Field | Value |
|---|---|
| instance_id | astropy__astropy-13236 |
| receipt_present | true |
| canonical_span_source | unified_diff |
| search_locked | true |
| same_span_retry | true |
| semantic_retry_count | 1 |
| verifier_result_after_retry | PASS |
| behavior_delta_verified | true |
| semantic_retry_mode | verification_guided |
| llm_replace_success | false (deterministic fallback) |
| deterministic_fallback_used | true |
| deterministic_fallback_reward | REMOVE_BLOCK |
| model_patch_reward | (none) |
| receipt_coverage | 1.0 |

---

## Before/After

### Before (T1.4)
- failure_reason: LOGIC_REGRESSION:VERIFICATION_FAILED
- Column type: NdarrayMixin
- verification: FAIL

### After (T1.6 regression)
- failure_reason: (none — SOLVED)
- Column type: Column
- verification: PASS

---

## Bug Location

**File**: `astropy/table/table.py`  
**Lines**: 1242-1247  
**Bug**: Auto-transform structured ndarray into NdarrayMixin

```python
# Before (buggy)
        # Structured ndarray gets viewed as a mixin unless already a valid
        # mixin class
        if (not isinstance(data, Column) and not data_is_mixin
                and isinstance(data, np.ndarray) and len(data.dtype) > 1):
            data = data.view(NdarrayMixin)
            data_is_mixin = True

# After (fixed)
        # (block removed entirely)
```

---

## Verification Report

### Before
```
Column type of structured array in Table: <class 'astropy.table.ndarray_mixin.NdarrayMixin'>
BUG PRESENT: Structured ndarray column was auto-transformed into NdarrayMixin.
```

### After
```
Column type of structured array in Table: <class 'astropy.table.column.Column'>
SUCCESS: Structured ndarray column was NOT auto-transformed into NdarrayMixin.
```

---

## Canonical Span Extraction

| Strategy | Result |
|---|---|
| locked_search | skipped (no previous canonical) |
| unified_diff | ✅ found |
| ast_boundary | (not needed) |
| traceback_window | (not needed) |

---

## Tests Run

| Test | Result |
|---|---|
| reproduce_bug.py (before) | FAIL (bug present) |
| reproduce_bug.py (after) | PASS ✅ |

---

## Files Changed

| File | Change |
|---|---|
| `scripts/bench/t1_6_regression_astropy_13236.py` | New: T1.6 regression script |
| `.nexus/reports/local_heal/astropy__astropy-13236__T1_6_REGRESSION/receipt.json` | T1.6 regression receipt |
