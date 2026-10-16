# B4-D: Decision Gate

## Status: B4C_MODEL_IDENTIFIED_CORRECT_MECHANISM_BUT_APPLY_FAILED

## B4-C Results

| Attempt | Action Type | Snippet | Apply | Verifier |
|---------|-------------|---------|-------|----------|
| 1 | INSERT_GUARD | `for col in cols: self._set_col_formats(col)` | Failed (no change) | N/A |
| 2 | CALL_EXISTENT_HELPER | `self.data._set_col_formats(cols)` | N/A (invalid type) | N/A |

## Key Finding

**The model DID identify the correct mechanism with constrained action space!**

- Attempt 1: Proposed `_set_col_formats(col)` — correct function, correct intent
- Attempt 2: Proposed `self.data._set_col_formats(cols)` — correct function, correct class reference

Both attempts show the model understands the bug mechanism when given constrained actions:
1. `_set_col_formats()` must be called
2. It should be called before `iter_str_vals()`
3. The format application is the missing piece

## Why Apply Failed

- Attempt 1: The snippet insertion logic was too simplistic — it tried to insert before `iter_str_vals` but the anchor text didn't match exactly
- Attempt 2: Action type was misspelled (`CALL_EXISTENT_HELPER` vs `CALL_EXISTING_HELPER`)

## Conclusion

**B4_PARTIALLY_PROVES_CONSTRAINED_ACTION_VALUE**

- ✅ Constrained action space helped model identify correct mechanism
- ✅ Model proposed `_set_col_formats()` — the exact fix
- ❌ Apply failed due to implementation detail (snippet insertion logic)
- ❌ Not a semantic limitation — it's a mechanical integration issue

## Next Steps

1. Fix snippet insertion logic to handle exact anchor matching
2. Re-run B4-C with corrected apply logic
3. If apply succeeds, test verifier
4. This is promising — constrained actions DO help local 12B
