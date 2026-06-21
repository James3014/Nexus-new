# AO2 — Live Regression Entrypoints Implementation

**Status**: `AO2_LIVE_REGRESSION_ENTRYPOINTS_IMPLEMENTED`
**Date**: 2026-06-21

---

## Implementation Evidence

| Evidence | Status |
|----------|--------|
| Python scripts added | 2 (run_c12481_regression.py, run_c13453_regression.py) |
| Tests added | 8 (all passing) |
| Scripts executable | YES |
| Dry-run mode works | YES |
| Result schema correct | YES |
| No hardcoded patches | VERIFIED |
| All flags correct | VERIFIED |

---

## Files Added

| File | Type |
|------|------|
| `scripts/bench/run_c12481_regression.py` | ADDED |
| `scripts/bench/run_c13453_regression.py` | ADDED |
| `tests/unit/local_heal/test_live_regression_entrypoints.py` | ADDED |
| `artifacts/runtime/ao2_live_regression_entrypoints_v0/c12481_regression_result.json` | GENERATED |
| `artifacts/runtime/ao2_live_regression_entrypoints_v0/c13453_regression_result.json` | GENERATED |
| `artifacts/runtime/ao2_live_regression_entrypoints_v0/entrypoint_schema_check.json` | GENERATED |
| `artifacts/runtime/ao2_live_regression_entrypoints_v0/test_results.json` | GENERATED |

---

## Entrypoint Results

### C_12481

| Field | Value |
|-------|-------|
| task_id | C_12481 |
| fixture_status | FIXTURE_LOADED |
| verifier_status | FAIL (no matching tests) |
| hardcoded_patch_used | false |
| All flags | correct |

### C_13453

| Field | Value |
|-------|-------|
| task_id | C_13453 |
| fixture_status | FIXTURE_LOADED |
| verifier_status | PASS (1 test passed) |
| hardcoded_patch_used | false |
| All flags | correct |

---

## Test Results

| Suite | Passed | Failed |
|-------|--------|--------|
| entrypoint tests | 8 | 0 |
| local_heal full | 336 | 0 |

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |

---

## Decision

**AO2_LIVE_REGRESSION_ENTRYPOINTS_IMPLEMENTED**

Live regression entrypoints implemented and verified. C_12481 fixture loads but verifier finds no matching tests (expected). C_13453 fixture loads and verifier passes.

---

## Artifacts

- `c12481_regression_result.json`
- `c13453_regression_result.json`
- `entrypoint_schema_check.json`
- `test_results.json`
