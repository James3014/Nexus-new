# H6-4: Local Adapter Execution Plan Dry Run

**Status**: H6_4_LOCAL_ADAPTER_EXECUTION_PLAN_DRY_RUN_PASS

## Summary

H6-4 converts H6-3 shadow adapter routing receipt into a local adapter execution plan, kept non-executable and dry-run only. This phase ensures Nexus can represent a local adapter execution plan without calling real models.

## Files Changed

- `tests/benchmark/test_capability_ab_runner.py` — Added 23 H6-4 tests
- `scripts/bench/capability_ab_runner.py` — Added `_build_h6_local_adapter_execution_plan_dry_run` helper
- `docs/reports/h6_4_local_adapter_execution_plan_dry_run_v0.md` — This report

## Test Counts

- H6-4 collect-only: 23 selected
- H6-4 default env: 23 passed
- H6-4 flagged env: 23 passed
- H6-3/H6-4 targeted: 65 passed

## Key Properties

- `dry_run_only`: True
- `executable`: False
- `production_ready`: False
- `public_claim_allowed`: False
