# V4-E.1 3B Receipt / Lane Audit Mini-Eval

## Status: V4E1_3B_AUXILIARY_AUDIT_PROMISING_INTERNAL_ONLY

## Summary

3B (qwen2.5:3b) evaluated on receipt/lane audit tasks using existing V4-A/V4-B artifacts.

## Tasks Evaluated

| Task | 3B Prediction | Expected | Correct |
|------|--------------|----------|---------|
| MC001 lane | verifier_passed | verifier_passed | ✅ |
| MC006 lane | canonical_recovery | canonical_recovery | ✅ |
| MC008 lane | env_blocked | env_blocked | ✅ |
| MC007 lane | verifier_passed | verifier_passed | ✅ |
| V4B_12481 lane | canonical_recovery | canonical_recovery | ✅ |
| V4B_13579 lane | env_blocked | env_blocked | ✅ |

## Findings

- 3B can predict lane correctly on simple receipts
- 3B is advisory only — does not override deterministic checker
- 3B governance compliance: passed (no false positive flags)
- Cost: minimal (local inference, ~2s per prediction)

## Recommendation

3B is viable as advisory receipt/lane auditor. Must remain advisory-only.
