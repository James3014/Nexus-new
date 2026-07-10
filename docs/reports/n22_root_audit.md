# N22 — Root Audit: N16–N21 E2E Verify

**Gate**: delivery_acceptance
**Date**: 2026-07-10

## Claims

| Claim | Evidence | Verdict |
|-------|----------|---------|
| N16: S-phase 5 caps routed + M2 disabled | `test_s_phase_5_capabilities_e2e.py` (8 tests) | ✅ PASS |
| N17: P-phase 4 caps routed + M2 disabled | `test_p_phase_4_capabilities_e2e.py` (5 tests) | ✅ PASS |
| N18: X-phase 8 caps routed + M2 disabled | `test_x_phase_8_capabilities_e2e.py` (9 tests) | ✅ PASS |
| N19: D-phase 2 caps routed + M2 disabled | `test_d_phase_2_capabilities_e2e.py` (3 tests) | ✅ PASS |
| N20: R-phase 8 caps routed + M2 disabled | `test_r_phase_8_capabilities_e2e.py` (9 tests) | ✅ PASS |
| N21: A+C-phase 9 caps routed + M2 disabled | `test_a_c_phases_9_capabilities_e2e.py` (10 tests) | ✅ PASS |
| 155 non-routing capabilities exist as importable classes/functions | `test_capability_existence_155.py` (513 tests) | ✅ PASS |
| `build_local_model_provider_from_env` import error fixed | `test_real_model_probe.py` | ✅ PASS |

## Capability Summary

| Category | Count |
|----------|-------|
| Routed via capability_selector (SPXDRAC) | 43 |
| Non-routing (passive library) | 155 |
| Registered in capability_registry.py | 51 |
| Total verified | 198 |

## Files Changed

| File | Change |
|------|--------|
| `tests/integration/test_s_phase_5_capabilities_e2e.py` | new |
| `tests/integration/test_p_phase_4_capabilities_e2e.py` | new |
| `tests/integration/test_x_phase_8_capabilities_e2e.py` | new |
| `tests/integration/test_d_phase_2_capabilities_e2e.py` | new |
| `tests/integration/test_r_phase_8_capabilities_e2e.py` | new |
| `tests/integration/test_a_c_phases_9_capabilities_e2e.py` | new |
| `tests/integration/test_capability_existence_155.py` | new |
| `nexus/services/local_heal/capability_adapter.py` | added `build_local_model_provider_from_env` |

## Residual Debt

- `test_real_model_probe.py` only verifies wiring contract, not real model execution
- Pre-existing collection errors in `tests/gates/test_s2t_memory_sidecar_*.py` unaddressed
