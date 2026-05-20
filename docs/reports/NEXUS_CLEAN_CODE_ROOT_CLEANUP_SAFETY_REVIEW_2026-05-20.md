# Nexus Clean Code Root Cleanup Safety Review

Date: `2026-05-20`
Claim class: `INTERNAL_REFACTOR_SAFETY_REVIEW`
Runtime update allowed: `false`
Public benchmark allowed: `false`

## Summary

`CC-8` reviewed the `ops_script_candidate` and `test_candidate` rows from
`docs/reports/NEXUS_CLEAN_CODE_ROOT_RETENTION_INVENTORY_2026-05-20.json`.

No root file move is safe in this slice.

Reason:

- candidate root scripts are referenced by `compliance/readiness/asset_inventory.json`;
- several candidates are referenced by historical reports and DCI evidence;
- `final_verify.py` is directly exercised by
  `tests/health/test_health_reporting_scripts.py`;
- `oracle_test.py` is hard-coded in `nexus/oracle/promote.py` and
  `nexus/app/shadow_bus.py`;
- root script moves would require compatibility wrappers or asset inventory
  migration, which would exceed the `CC-8` safe cleanup boundary.

## Decision

| Field | Value |
| --- | --- |
| status | `PASS_WITH_ZERO_MOVES` |
| root candidates reviewed | `20` |
| safe moves | `0` |
| files moved | `0` |
| files deleted | `0` |
| next action | create a separate compatibility-wrapper migration plan |

## Candidate Classes

### Ops Script Candidates

- `STATUS_DASHBOARD.sh`
- `analyze_metrics.py`
- `compute_truth_scores.py`
- `deploy-v21a.sh`
- `ingest.py`
- `latency_tracker.py`
- `migrate_adrs.py`
- `nexus-proxy.sh`
- `nexus_benchmark_full.py`
- `ppo_controller.py`
- `topology_genome.py`

### Test Candidate Scripts

- `elite_sprint_verify.sh`
- `final_verify.py`
- `live_guardrail_test.py`
- `nexus_belief_mechanics_test.py`
- `nexus_limit_test.py`
- `oracle_test.py`
- `physical_verify.py`
- `run_1_simulator.py`
- `verify_v9_hardening.py`

## Required Follow-Up Before Any Move

1. Add wrappers or deprecation shims for moved root entrypoints.
2. Update `compliance/readiness/asset_inventory.json` intentionally.
3. Update tests that resolve root paths, especially health-reporting tests.
4. Split oracle fixture files from root-level executable examples before moving
   `oracle_test.py`.
5. Run full `uv run scripts/ops/ci_gate.py` after the compatibility migration.

## Lesson

Root cleanup must prove reference safety before moving files. A retention
classification is not enough; root scripts may be part of readiness inventory,
historical evidence, or explicit runtime fixtures.
