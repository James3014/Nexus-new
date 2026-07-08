# P6-C1 Rollout Candidate Policy Contract

## Status: P6_C1_ROLLOUT_CANDIDATE_POLICY_CONTRACT_PASS

## Files Changed

| File | Action |
|------|--------|
| `nexus/services/local_heal/p6_rollout_policy.py` | P6RolloutPolicy + build_rollout_policy() |
| `tests/unit/local_heal/test_p6_rollout_policy.py` | 12 tests |
| `docs/reports/p6_c1_rollout_candidate_policy_contract_v0.md` | Report |

## Policy States

| State | default_runtime_allowed | public_claim_allowed | production_ready |
|-------|------------------------|---------------------|------------------|
| disabled | false | false | false |
| env_guarded | false | false | false |
| rollout_candidate | false | false | false |
| blocked | false | false | false |
| rollback_required | false | false | false |

## Safety Invariants

- memory_signal_allowed_for_quota=false (all states)
- belief_signal_allowed_for_quota=false (all states)
- p5_override_allowed=false (all states)
- verifier_required=true (all states)
- claim_gate_required=true (all states)
- public_claim_allowed=false (all states)
- production_ready=false (all states)

## Statements

- rollout_candidate is NOT production
- public_claim_allowed=false always
- production_ready=false always
- no runtime behavior changed
