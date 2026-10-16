# C4-F: Capability Curve Stability Decision

## Status: C4_CONSTRAINED_ACTION_STABLE_ON_SMALL_CURVE

## Results

| Task | Bucket | Repo | Status |
|------|--------|------|--------|
| C_12481_REGRESSION | constructor_normalization | sympy | ✅ VERIFIER_PASS |
| C_13453_REGRESSION | output_formatting | astropy | ✅ VERIFIER_PASS |

## Task Pool Analysis

| Metric | Value |
|--------|-------|
| Tasks discovered | 7 |
| Eligible tasks | 2 |
| Buckets covered | 2/5 |
| Repos | sympy, astropy |
| Pass rate | 2/2 (100%) |

## Env Blockers

- Sympy: Python 3.12 compatibility (collections.Mapping)
- Astropy: import issues without build
- Both repos work with dedicated .venv

## Stability Assessment

**C4_CONSTRAINED_ACTION_STABLE_ON_SMALL_CURVE**

- ✅ 2/2 eligible tasks pass consistently
- ✅ Both regression tests stable across C3 and C4
- ✅ No action DSL gaps found
- ✅ No evidence gaps found
- ✅ No model action selection failures

## Limitations

- Only 2 eligible tasks (5 skipped as env-blocked or non-bugs)
- Buckets covered: 2/5
- Need more tasks to confirm general stability
- Need to fix env blockers for additional task coverage

## Conclusion

Constrained action pipeline is stable on the 2-task curve. Both C_12481 and C_13453 pass consistently across multiple runs (C3, C4). This is a minimum viable proof that the pipeline works for:
1. Output formatting (C_13453)
2. Constructor/normalization (C_12481)

## Next Steps

1. Fix env blockers to enable more tasks
2. Expand to 10-task curve with real eligible tasks
3. Test on easy_localized and medium_semantic buckets
4. Do NOT make public claim until at least 5 tasks pass across 3+ buckets
