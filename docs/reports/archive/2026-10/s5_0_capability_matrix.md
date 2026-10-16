# S5.0 Capability Matrix

**Date**: 2026-06-18
**Status**: FROZEN

---

## A. Strategy Layer

| Capability | Status | First Proven |
|------------|--------|-------------|
| StrategyEnvelope trace-only | ✓ Implemented | S0 |
| Strategy-conditioned prompt | ✓ Shadow mode | S1 |
| Limited active strategy prompt | ✓ 4-task adoption | S1.2 |
| Diverse strategy tournament | ✓ 3 candidates/task | S2 |
| Strategy-specific probes | ✓ Differentiated scoring | S2.2 |
| Winner-only execution | ✓ All rollouts | S2+ |
| Source guard preflight | ✓ buggy_line check | S4.1 |

## B. Patch Shape Layer

| Shape | Status | First Verified |
|-------|--------|---------------|
| single_line_replacement | ✓ Stable | T3.2 |
| small_local_replacement | ✓ Stable | T3.5 |
| indentation_normalized_replacement | ✓ Stable | T4.8 |
| multi_line_block_replacement | ⚠ Stored-output only | S4.6 |
| function_body_insertion | ⚠ Stored-output only | S4.6 |
| parent_boundary_preservation | ✓ Implemented | S4.5 |
| indentation_aware_line_insertion | ✓ Fresh M0 verified | S4.9 |
| unsupported_complex_shape | ✗ Blocked | S4.3 |

## C. Execution Layer

| Mode | Status | Notes |
|------|--------|-------|
| D0 deterministic baseline | ✓ Stable | All candidates |
| R0 stored-output replay | ✓ Stable | Historical evidence |
| M0 fresh Qwen replay | ✓ Partial | 5 fresh verified, 2 stored-output |
| M0 deterministic (pinned) | ✓ Partial | astropy-13579 stable |

## D. Guard Layer

| Guard | Status | Notes |
|-------|--------|-------|
| REPLACE-only contract | ✓ | All M0 |
| Context-aware syntax gate | ✓ | T3.5+ |
| Effective-change guard | ✓ | No-op detection |
| Parent-boundary validation | ✓ | S4.5+ |
| Indentation-aware insertion | ✓ | S4.6+ |
| Source stale guard | ✓ | S4.1+ |
| No-op detection | ✓ | T3.8+ |
| Public claim block | ✓ | All phases |

## E. Evidence Tiers

| Tier | Count | Candidates |
|------|-------|------------|
| stable_fresh_m0_verified | 5 | astropy-13236, sympy-13852, astropy-12907, astropy-14182, astropy-13453 |
| fresh_m0_verified | 1 | astropy-13579 |
| stored_output_replayable | 3 | sympy-13031, astropy-13579 (historical), + 1 |
| historical_clean_excluded | 4 | sympy-12419, sympy-13647, astropy-14365, astropy-14309 |
| negative_control | 1 | sympy-11618 |

## F. Non-Claims

This is NOT:
- A public benchmark
- A Qwen solve rate
- Comparable to official SWE-bench
- Production-ready autonomous patcher

This IS:
- Internal controlled model-candidate evidence
- CI-validated fixture-backed replay path
- Strategy-conditioned patch generation
- Indentation-aware insertion capability
