# Nexus Universal Local Assist Productization Campaign Status

## Current milestone

`M4-A_PROVIDER_NEUTRAL_CLOUD_AGENT_CONTRACT`

## Completed milestones

- `M2_STATUS_CONVERGED_AND_SEALED` — `cdad37e9c`
- `PLANNER_LOCAL_ASSIST_RECOMMENDATION_CONTRACT_PROVEN` — `dca1c56f4`
- `PLANNER_LOCAL_ASSIST_RECOMMENDATION_SHADOW_PROVEN` — `53bc1d39d`
- `PLANNER_LOCAL_ASSIST_RECOMMENDATION_CALIBRATED` — `8b5280f89`
- `PLANNER_AUTOMATIC_ADVISOR_CANARY_PROVEN` — `8b198c94a`
- `PLANNER_AUTOMATIC_CANDIDATE_CANARY_PROVEN` — `bce01fd0b`
- `PLANNER_AUTOMATIC_VERIFIED_SUBTASK_CANARY_PROVEN` — `cfa1693cc`
- `PLANNER_DRIVEN_LOCAL_ASSIST_PROVEN` — `111eab2e0`

## Current commit

`111eab2e0` — `feat(local-assist): prove planner-driven bounded dispatch`

## Evidence

- `tests/engine/test_local_assist_recommendation.py` → `9 passed in 0.18s`.
- `tests/engine/test_local_assist_shadow_runtime.py` → `3 passed in 0.17s`.
- Shadow dataset → `12` tasks, `3` per action (`skip`, `advisor`, `candidate`, `verified-subtask`); coverage `1.0`; exact agreement `1.0`; unsafe recommendation rate `0.0`; Local Assist invocations `0`.
- Calibration → `CALIBRATED`; unsafe recommendation rate `0.0`; false-positive rate `0.0`; exact agreement `1.0`; unexplained disagreements `0`; route authority unchanged; automatic dispatch disabled.
- Advisor canary tests → `8 passed`; provider unavailable, malformed output, timeout, incomplete receipt, mismatched task identity, stale revision, absent recommendation, high risk, and formal mutation all fail closed; successful canary is read-only advisor only.
- Candidate canary tests → `4 passed`; candidate isolation, source revision, verifier precondition, formal mutation guard, candidate hash match, and Agent adoption receipt are enforced; formal workspace remains unchanged.
- Verified-subtask canary tests → `4 passed`; isolated apply, deterministic verifier pass/fail, rollback reference, Agent review, and terminal verifier failure are enforced; fallback remains disabled.
- Bounded dispatch tests → `6 passed`; skip/advisor/candidate/verified-subtask dispatch share recommendation receipt, task identity, workspace revision, and Agent authority; no formal workspace mutation.
- Planner regression and Local Assist focused suites → `144 passed`; two pre-existing failures remain in `tests/engine/test_capability_routing_contracts.py` because the worktree already contains unrelated changes in `nexus/services/local_heal/receipt.py`.
- Recommendation is embedded as `signal_snapshot["local_assist_recommendation"]` and is deterministic, shadow-only, non-mutating, and route-authority preserving.
- Machine-readable receipt writer: `write_local_assist_recommendation_receipt`.

## Claim boundary

`selected`, `invoked`, `output_delivered`, and `output_consumed` remain proven only for accepted M1/M2 evidence. `outcome_contributed`, `value_measured`, automatic planner dispatch, real cloud-local runtime, and provider-neutral productization remain not proven. `production_ready=false`, `public_claim_allowed=false`, and `internal_only=true` remain in force.

## Current blockers

- Existing dirty-tree regression failures in `test_capability_routing_contracts.py`; not caused by the M3-A files and intentionally left untouched.

## Next automatic action

Implement M4-A provider-neutral cloud Agent contract: define request/response/adapter boundaries, preserve candidate isolation and route authority, and keep fake providers out of real-cloud claims.
