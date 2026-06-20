# MatchAuthority Invariant Packet — Phase 1

## Summary

Hardened success attribution boundary in the patch transport path.

## Bugs Fixed

### MULTI_INTENT_AUTHORITY_LOSS

**Root cause**: `authority` was re-initialized to `None` inside the `for intent in intents` loop in `PatchApplier.apply_and_validate()`. This caused cross-file attribution from earlier intents to be lost when later intents were verbatim matches.

**Fix**: Moved `authority` initialization outside the loop. Added `accumulated_authority` with precedence ranking:
- `CROSS_FILE_CORRECTION` (highest) > `CANONICAL_RECOVERY` > `VERBATIM`

## Invariants Enforced

| Invariant | Status | Location |
|-----------|--------|----------|
| `FUZZY_CANDIDATE_ONLY` must never appear on `success=True` | Pre-existing | `patch_applier.py:614-617` |
| `match_authority` must never be `None` on `success=True` | **New** | `patch_applier.py:623-626` |
| `success_attribution` classifies receipt telemetry | **New** | `receipt.py:431` |

## Receipt Field: `success_attribution`

| match_authority | success_attribution | Meaning |
|----------------|---------------------|---------|
| `verbatim` | `model_patch_success` | Model's SEARCH matched exactly |
| `canonical_recovery` | `canonical_recovery_success` | Tool recovered the search span |
| `cross_file_correction` | `cross_file_recovery_success` | Applied to different file |
| empty/None | `unknown` | Authority not set |

## Files Modified

- `nexus/services/local_heal/patch_applier.py` — authority accumulation fix + invariant
- `nexus/services/local_heal/receipt.py` — success_attribution field
- `tests/unit/local_heal/test_patch_applier.py` — 10 new tests

## Test Results

- `test_patch_applier.py`: 17 passed
- `test_receipt_v1_schema.py`: 19 passed
