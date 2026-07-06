# C4 Committee Combination Coverage Audit Report

**status**: C4_COMMITTEE_COMBINATION_COVERAGE_AUDIT_PASS
**date**: 2026-07-06

## Commands Run

```bash
rg -n "dual|triple|four-model|committee_no_winner|selected_candidate" docs/reports tests/unit/local_heal nexus/services/local_heal
```

## Coverage Matrix

| Combination | Contract Truth | Live Execution | Solve Success |
|---|---|---|---|
| Dual model (qwen+deepseek) | ✅ `test_committee_route_trace.py` (19 tests) | ⚠️ Historical only | ❌ Not current |
| Triple model | ⚠️ No dedicated tests | ❌ Not tested | ❌ Not tested |
| Four-model | ⚠️ No dedicated tests | ❌ Not tested | ❌ Not tested |
| Single model (no committee) | ✅ `test_candidate_decision_adapter.py` | ✅ Standard path | ⚠️ Depends on model |
| committee_no_winner | ✅ `test_committee_no_winner_classifier.py` (10 tests) | ⚠️ Historical only | N/A |
| selected/applied/verifier truth | ✅ `test_committee_route_trace.py` (19 tests) | ⚠️ Stub-based | N/A |

## Evidence Levels

| Level | Definition | Combinations |
|---|---|---|
| **Contract truth** | Unit tests prove field presence and consistency | Dual, committee_no_winner, selected/applied/verifier |
| **Live execution** | Real model runs with production artifacts | Single model only |
| **Solve success** | End-to-end repair with passing verifier | None current-proof |

## Gaps

1. **Triple/four-model**: No dedicated contract truth tests. Only dual model tested.
2. **Live execution**: Dual model tests are stub-based, not live model runs.
3. **Solve success**: No current-proof solve success for any combination.

## Statements

- **Coverage audit only**: This report documents coverage, does not fix gaps.
- **Contract truth ≠ solve truth**: Unit green does not mean solve restored.
- **No model policy changed**: Only coverage documented.
- **No solve improvement claimed**.
