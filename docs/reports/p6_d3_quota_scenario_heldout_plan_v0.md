# P6-D3 Quota Scenario Heldout Plan

## Status: P6_D3_QUOTA_SCENARIO_HELDOUT_PLAN_PASS

## Fixture

`artifacts/effect_fixtures/p6_quota_scenario_heldout_plan_v0.json` — 36 cases

## Distribution

| Difficulty | Count |
|------------|-------|
| easy | 12 |
| medium | 12 |
| hard | 12 |

| Quota State | Count |
|-------------|-------|
| healthy | 12 |
| constrained | 6 |
| exhausted_local_available | 6 |
| exhausted_local_unavailable | 6 |
| unknown | 6 |

## Expected Action Matrix

| Quota → Difficulty | easy | medium | hard |
|--------------------|------|--------|------|
| healthy | keep_full_committee | keep_full_committee | keep_full_committee |
| constrained | reduce_candidate_count | reduce_candidate_count | reduce_candidate_count |
| exhausted_local_available | local_only | local_only | local_only |
| exhausted_local_unavailable | fail_closed | fail_closed | fail_closed |
| unknown | fail_closed | fail_closed | fail_closed |

## Safety Invariants

- public_claim_allowed=false (all cases)
- production_ready=false (all cases)
- default_runtime_allowed=false (all cases)
- verifier_required=true (all cases)
- claim_gate_required=true (all cases)

## Statements

- This is a plan, not execution
- No runtime behavior changed
- No Agent A files changed
