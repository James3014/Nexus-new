# E1/E2/E3: Environment and Task Supply Expansion

## Status: E2_5_TASK_POOL_READY

## E1: Environment Matrix

| Repo | Python | Modules Working | Status |
|------|--------|-----------------|--------|
| sympy | 3.9.24 | 8/8 (combinatorics, geometry, matrix, core, calculus, solvers) | ✅ READY |
| astropy | 3.9.24 | html module | ✅ READY |

## E2: Real Task Pool

| Task | Bucket | Module | Status |
|------|--------|--------|--------|
| C_12481_REGRESSION | constructor_normalization | combinatorics | ✅ VERIFIED |
| C_13453_REGRESSION | output_formatting | astropy.html | ✅ VERIFIED |
| perm_identity | easy_localized | combinatorics | ✅ VERIFIED |
| perm_inverse | medium_semantic | combinatorics | ✅ VERIFIED |
| perm_multiply | medium_semantic | combinatorics | ✅ VERIFIED |
| geo_distance | easy_localized | geometry | ✅ VERIFIED |
| matrix_det | easy_localized | matrix | ✅ VERIFIED |
| core_simplify | medium_semantic | core | ✅ VERIFIED |

## Bucket Coverage

| Bucket | Tasks | Status |
|--------|-------|--------|
| easy_localized | 3 (geo_distance, matrix_det, perm_identity) | ✅ |
| medium_semantic | 3 (perm_inverse, perm_multiply, core_simplify) | ✅ |
| output_formatting | 1 (C_13453) | ✅ |
| constructor_normalization | 1 (C_12481) | ✅ |
| hard_cross_function | 0 | ⏳ |

## Metrics

| Metric | Value |
|--------|-------|
| Tasks discovered | 8 |
| Eligible tasks | 8 |
| Buckets covered | 4/5 |
| Repos covered | 2/2 |
| Verifier pass | 8/8 (100%) |

## Conclusion

**E2_5_TASK_POOL_READY**

- 8 verified tasks across 4 buckets
- 2 repos working (sympy, astropy)
- All tasks have working verifiers
- Ready for C6 capability curve expansion

## Next Step

Run C6 with the expanded 8-task pool to test constrained action stability across more buckets.
