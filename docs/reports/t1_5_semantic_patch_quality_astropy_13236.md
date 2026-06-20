# T1.5 Semantic Patch Quality — Report

**[阶段]** T1.5 Verification-Guided Semantic Patch Retry
**[日期]** 2026-06-17

---

## Claim Boundary

| 字段 | 值 |
|---|---|
| simulated | false |
| receipt_present | true |
| claim_eligible | false |
| public_claim_allowed | false |
| claim_block_reason | focused_internal_rerun |
| run_group | T1_5_SEMANTIC |

---

## T1.5 Verdict: 🟢 Green

**理由：**
1. astropy-13236 从 LOGIC_REGRESSION:VERIFICATION_FAILED 推进为 **SOLVED**。
2. Verification passed: `Column type of structured array in Table: <class 'astropy.table.column.Column'>`
3. Receipt coverage = 1.0 (all required telemetry present).
4. Canonical SEARCH span was locked from T1.4; only REPLACE was rewritten.
5. No SEARCH_MISMATCH regression.

---

## Telemetry (Required Fields)

| Field | Value |
|---|---|
| expected_behavior | Column type should be numpy.void or Column, not NdarrayMixin |
| observed_behavior | BUG PRESENT: Structured ndarray column was auto-transformed into NdarrayMixin |
| verification_failure_text | [FAIL] reproduce_bug.py — BUG PRESENT |
| patch_diff_summary | Removed lines 1242-1247 (NdarrayMixin auto-transform block) |
| target_symbol | NdarrayMixin |
| patched_symbol | Column (block removed) |
| root_cause_hypothesis | Lines 1242-1247 auto-transform structured ndarray into NdarrayMixin; fix removes entire block |
| behavior_delta_claim | Removing auto-transform preserves original numpy dtype for structured array columns |
| behavior_delta_verified | ✅ true |
| semantic_retry_count | 1 |
| same_span_retry | true |
| span_changed_reason | Span locked from T1.4 canonical injection |
| verifier_result_after_retry | PASS |
| receipt_coverage | 1.0 |

---

## Before/After Comparison

### Before (T1.4)
- failure_reason: `LOGIC_REGRESSION:VERIFICATION_FAILED`
- failure_class: `semantic_wrong`
- verification: `[FAIL] BUG PRESENT: Structured ndarray column was auto-transformed into NdarrayMixin`
- Column type: `<class 'astropy.table.ndarray_mixin.NdarrayMixin'>`

### After (T1.5)
- failure_reason: (none — SOLVED)
- failure_class: `SOLVED`
- verification: `[PASS] SUCCESS: Structured ndarray column was NOT auto-transformed into NdarrayMixin`
- Column type: `<class 'astropy.table.column.Column'>`

---

## Receipt Excerpt

```json
{
  "schema": "nexus.local_heal.semantic_retry_receipt.v1",
  "instance_id": "astropy__astropy-13236",
  "run_group": "T1_5_SEMANTIC",
  "verification_passed": true,
  "telemetry": {
    "behavior_delta_verified": true,
    "semantic_retry_count": 1,
    "same_span_retry": true,
    "verifier_result_after_retry": "PASS",
    "receipt_coverage": 1.0
  }
}
```

---

## Verification Excerpt

```
Column type of structured array in Table: <class 'astropy.table.column.Column'>
SUCCESS: Structured ndarray column was NOT auto-transformed into NdarrayMixin.
```

---

## Patch Diff Summary

The fix removes the entire NdarrayMixin auto-transform block (lines 1242-1247) from `astropy/table/table.py`:

```diff
--- a/astropy/table/table.py
+++ b/astropy/table/table.py
@@ -1242,7 +1242,0 @@
-        # Structured ndarray gets viewed as a mixin unless already a valid
-        # mixin class
-        if (not isinstance(data, Column) and not data_is_mixin
-                and isinstance(data, np.ndarray) and len(data.dtype) > 1):
-            data = data.view(NdarrayMixin)
-            data_is_mixin = True
-
```

---

## Tests Run

| Test Suite | Result |
|---|---|
| test_local_heal_decoupled.py | 4/4 ✅ |
| test_local_heal_receipt.py | 4/4 ✅ |
| test_local_heal_validator.py | 3/3 ✅ |
| test_local_heal_corrector.py | 4/4 ✅ |
| test_local_heal_preflight.py | 2/2 ✅ |
| test_local_heal_context_v2.py | 2/2 ✅ |
| **Total** | **19/19 ✅** |

---

## Files Changed

| File | Change |
|---|---|
| `nexus/services/local_heal/prompt_builder.py` | Added `build_verification_guided_retry_prompt()` static method |
| `scripts/bench/t1_5_semantic_retry_astropy_13236.py` | New: T1.5 semantic retry script |
| `.nexus/workspaces/astropy/reproduce_bug.py` | New: verification script for astropy-13236 |

---

## Next Blocker

1. **P0.1 abort receipt guarantee** (from T1.4): Runner must produce abort receipt when pipeline fails before receipt writer.
2. **Generalize semantic retry**: The `build_verification_guided_retry_prompt()` can be integrated into the orchestrator for automatic verification-guided retries on LOGIC_REGRESSION.
3. **astropy-12907**: Still blocked on workspace provisioning.
