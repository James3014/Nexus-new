# C10: Integrated Capability Decision

## Status: C10_CONSTRAINED_ACTION_STABLE_ON_EASY_MEDIUM_CURVE

## Executive Summary

The constrained action pipeline is stable on the easy/medium capability curve with 8/8 tasks passing. C9 found no additional real repair tasks in well-tested sympy/astropy libraries. D1 hard_cross_function bucket remains untested. R1 Rust shadow deferred. Pipeline is proven for internal-only use.

## Current Capability Classification

**C10_CONSTRAINED_ACTION_STABLE_ON_EASY_MEDIUM_CURVE**

- ✅ 8/8 tasks pass (100%)
- ✅ 2/2 repair regression anchors pass
- ✅ 6/6 verification tasks pass
- ✅ Buckets: easy_localized, medium_semantic, output_formatting, constructor_normalization
- ✅ Repos: sympy, astropy
- ✅ Regression guard: PASS
- ❌ hard_cross_function: 0 tasks
- ❌ New repair tasks: 0 found (well-tested libraries)

## C8 Baseline Recap

| Metric | Value |
|--------|-------|
| Total tasks | 8 |
| Verifier pass | 8/8 (100%) |
| Repair pass | 2/2 |
| Verification pass | 6/6 |
| Buckets covered | 4/5 |
| Repos covered | 2/2 |
| Regression guard | PASS |

## C9 Real Repair Task Results

- **Tasks discovered**: 0 new real repair tasks
- **Reason**: sympy and astropy are well-tested libraries with extensive test suites
- **Finding**: Edge cases (Permutation size, cycle conversion, symbolic distance, matrix determinant) all work correctly
- **Conclusion**: Well-tested libraries don't have easy-to-find repair tasks

## D1 Hard Cross-Function Coverage

- **Status**: Not tested
- **Reason**: No suitable hard_cross_function tasks found
- **Finding**: Hard tasks require broader codebase understanding than current task pool provides
- **Conclusion**: hard_cross_function bucket needs different task sources

## R1 Rust Shadow Result

- **Status**: Deferred
- **Reason**: No performance bottleneck identified yet
- **Finding**: Python deterministic applier works correctly for current task volume
- **Conclusion**: Rust migration not needed until task volume or performance demands it

## Regression Guard

| Task | Status |
|------|--------|
| C_12481 | ✅ PASS |
| C_13453 | ✅ PASS |

## Failure Taxonomy

| Category | Count | Notes |
|----------|-------|-------|
| Action DSL gaps | 0 | All action types sufficient |
| Evidence gaps | 0 | Evidence pipeline works |
| Model action selection failures | 0 | Model identifies correct mechanisms |
| Env/verifier blocked | 0 | All envs working |
| Repair task supply limited | 1 | Well-tested libraries have few bugs |

## Public Claim

**public_claim_allowed=false**
**production_ready=false**
**training_export_allowed=false**
**internal_only=true**

## Next Roadmap

1. **Internal demo**: Package constrained action pipeline for internal demonstration
2. **Task supply expansion**: Find repair tasks in less-tested libraries
3. **R-track**: Rust shadow when performance demands it
4. **H4**: Stronger model comparison on harder tasks
5. **Stop and stabilize**: Current pipeline is proven stable on easy/medium curve
