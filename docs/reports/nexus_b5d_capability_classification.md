# B5-D: Updated Capability Classification

## Status: B5C_PATCH_APPLIED_VERIFIER_FAILED

## B5-C Results

| Action | Type | Apply | Syntax | Verifier |
|--------|------|-------|--------|----------|
| 1 | INSERT_GUARD | Failed | Syntax error | N/A |
| 2 | CALL_EXISTING_HELPER | ✅ Applied | ✅ Passed | ❌ FAIL |

## Key Findings

1. **Action 2 applied successfully**: `self.data._set_col_formats(cols)` was inserted into the source.
2. **Syntax passed**: The insertion didn't break Python syntax.
3. **Verifier failed**: "formats ignored" — the fix is incomplete.
4. **Insert point was wrong**: Action 2 inserted at L4 (before `write` method body), but should be after `_set_fill_values(cols)` at L356.

## Analysis

- **B3 conclusion refined**: 12B CAN identify correct mechanism under constrained action
- **B5 shows**: Action application works mechanically, but insert point selection needs improvement
- **Verifier failure**: `_set_col_formats(cols)` was inserted but in wrong location, so it doesn't affect the actual format application

## Updated Classification

**B5_CONSTRAINED_ACTION_IMPROVES_BUT_INSERT_POINT_NEEDS_FIX**

- ✅ Schema normalization works (CALL_EXISTENT_HELPER → CALL_EXISTING_HELPER)
- ✅ Action application works mechanically
- ✅ Syntax check passes
- ❌ Insert point selection is wrong (too early in method)
- ❌ Verifier fails because fix is in wrong location

## Conclusion

The constrained action pipeline is almost working:
1. Model identifies correct mechanism ✅
2. Schema normalization works ✅
3. Action application works ✅
4. Insert point needs improvement ❌
5. Verifier fails due to wrong location ❌

This is a **mechanical improvement path**, not a semantic limitation.

## Next Step

Fix insert point selection to place `_set_col_formats(cols)` AFTER `_set_fill_values(cols)`, then re-run.
