# Nexus AO2 Live Regression Entrypoints — Final Report

**Date**: 2026-06-21
**Status**: COMPLETE
**Commit**: `f323dc03`

---

## Implementation Summary

| Metric | Value |
|--------|-------|
| Scripts added | 2 |
| Tests added | 8 |
| Tests passing | 8/8 |
| local_heal suite | 336/336 |
| Entrypoints executable | YES |
| No hardcoded patches | VERIFIED |

---

## Files Added

| File | Purpose |
|------|---------|
| `scripts/bench/run_c12481_regression.py` | C_12481 entrypoint |
| `scripts/bench/run_c13453_regression.py` | C_13453 entrypoint |
| `tests/unit/local_heal/test_live_regression_entrypoints.py` | 8 tests |

---

## Entrypoint Results

### C_12481

```json
{
  "task_id": "C_12481",
  "fixture_status": "FIXTURE_LOADED",
  "verifier_status": "FAIL",
  "verifier_detail": "No tests matched keyword"
}
```

### C_13453

```json
{
  "task_id": "C_13453",
  "fixture_status": "FIXTURE_LOADED",
  "verifier_status": "PASS",
  "verifier_detail": "1 test passed"
}
```

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |

---

## Reports

- `/Users/jameschen/Downloads/nexus_ao2_live_regression_final_report.md`
- `docs/reports/ao2_live_regression_entrypoints_v0.md` (in repo)
