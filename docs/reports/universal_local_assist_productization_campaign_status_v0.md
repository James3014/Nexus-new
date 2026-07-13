# Nexus Universal Local Assist Productization Campaign Status

## Current milestone

`M3-D_ADVISOR_CANARY_AUTOMATION`

## Completed milestones

- `M2_STATUS_CONVERGED_AND_SEALED` — `cdad37e9c`
- `PLANNER_LOCAL_ASSIST_RECOMMENDATION_CONTRACT_PROVEN` — `dca1c56f4`
- `PLANNER_LOCAL_ASSIST_RECOMMENDATION_SHADOW_PROVEN` — `53bc1d39d`
- `PLANNER_LOCAL_ASSIST_RECOMMENDATION_CALIBRATED` — `8b5280f89`

## Current commit

`8b5280f89` — `fix(local-assist): calibrate shadow recommendation policy`

## Evidence

- `tests/engine/test_local_assist_recommendation.py` → `9 passed in 0.18s`.
- `tests/engine/test_local_assist_shadow_runtime.py` → `3 passed in 0.17s`.
- Shadow dataset → `12` tasks, `3` per action (`skip`, `advisor`, `candidate`, `verified-subtask`); coverage `1.0`; exact agreement `1.0`; unsafe recommendation rate `0.0`; Local Assist invocations `0`.
- Calibration → `CALIBRATED`; unsafe recommendation rate `0.0`; false-positive rate `0.0`; exact agreement `1.0`; unexplained disagreements `0`; route authority unchanged; automatic dispatch disabled.
- Planner regression and Local Assist focused suites → `144 passed`; two pre-existing failures remain in `tests/engine/test_capability_routing_contracts.py` because the worktree already contains unrelated changes in `nexus/services/local_heal/receipt.py`.
- Recommendation is embedded as `signal_snapshot["local_assist_recommendation"]` and is deterministic, shadow-only, non-mutating, and route-authority preserving.
- Machine-readable receipt writer: `write_local_assist_recommendation_receipt`.

## Claim boundary

`selected`, `invoked`, `output_delivered`, and `output_consumed` remain proven only for accepted M1/M2 evidence. `outcome_contributed`, `value_measured`, automatic planner dispatch, real cloud-local runtime, and provider-neutral productization remain not proven. `production_ready=false`, `public_claim_allowed=false`, and `internal_only=true` remain in force.

## Current blockers

- Existing dirty-tree regression failures in `test_capability_routing_contracts.py`; not caused by the M3-A files and intentionally left untouched.

## Next automatic action

Implement M3-D advisor canary: allow only narrowly gated read-only advisor automation with fail-closed provider and receipt handling; candidate and formal workspace mutation remain disabled.
