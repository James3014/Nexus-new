# C8: Final Capability Stability Review

## Status: C8_CONSTRAINED_ACTION_STABLE_ON_EASY_MEDIUM_CURVE

## Executive Summary

The constrained action pipeline passes 8/8 tasks across 4 buckets and 2 repos. Both regression anchors (C_12481, C_13453) pass. Six verification tasks pass. The pipeline is stable on the easy/medium capability curve.

## Results

| Task | Bucket | Type | Status |
|------|--------|------|--------|
| C_12481_REGRESSION | constructor_normalization | Repair | ✅ VERIFIER_PASS |
| C_13453_REGRESSION | output_formatting | Repair | ✅ VERIFIER_PASS |
| perm_identity | easy_localized | Verification | ✅ PASS |
| perm_inverse | medium_semantic | Verification | ✅ PASS |
| perm_multiply | medium_semantic | Verification | ✅ PASS |
| geo_distance | easy_localized | Verification | ✅ PASS |
| matrix_det | easy_localized | Verification | ✅ PASS |
| core_simplify | medium_semantic | Verification | ✅ PASS |

## Metrics

| Metric | Value |
|--------|-------|
| Total tasks | 8 |
| Verifier pass | 8/8 (100%) |
| Repair pass | 2/2 |
| Verification pass | 6/6 |
| Buckets covered | 4/5 |
| Repos covered | 2/2 |
| Regression guard | PASS |

## Bucket Coverage

| Bucket | Tasks | Pass |
|--------|-------|------|
| easy_localized | 3 | 3/3 |
| medium_semantic | 3 | 3/3 |
| output_formatting | 1 | 1/1 |
| constructor_normalization | 1 | 1/1 |
| hard_cross_function | 0 | — |

## Capability Classification

**C8_CONSTRAINED_ACTION_STABLE_ON_EASY_MEDIUM_CURVE**

The constrained action pipeline is stable:
- ✅ 8/8 tasks pass (100%)
- ✅ Both regression anchors stable
- ✅ Easy_localized bucket: 3/3 pass
- ✅ Medium_semantic bucket: 3/3 pass
- ✅ No action DSL gaps
- ✅ No evidence gaps
- ✅ No model action selection failures
- ✅ Regression guard passes

## Limitations

- hard_cross_function bucket not yet tested
- Only 2 repos (sympy, astropy)
- Only verification tasks for new buckets (no repair tasks yet)
- Need repair tasks in easy_localized/medium_semantic to confirm pipeline generalizes

## Public Claim

**public_claim_allowed=false**
**production_ready=false**
**training_export_allowed=false**
**internal_only=true**

## Next Recommended Route

1. **C9**: Expand to 10-task curve with repair tasks in easy_localized/medium_semantic
2. **D1**: Add hard_cross_function task supply
3. **R-track**: Rust deterministic applier/evidence acceleration
4. **H4**: Stronger model comparison on hard tasks
5. **Internal demo**: Package for internal demonstration
