# ADR: P6 Rollout Candidate Boundary

## Status: ACCEPTED

## Decision

`P6_GUARDED_RUNTIME_ROLLOUT_CANDIDATE` means env-guarded rollout candidate only. It does NOT mean:
- Production default
- Public claim allowed
- P5 promoted
- Solve-rate improved

## Scope

- Applies only to P6 quota-aware degradation
- Applies only under explicit env guard (`NEXUS_ENABLE_P6_QUOTA_DEGRADATION=1`)
- Applies only when P4 verifier and claim gate remain required

## Non-Authorities

- Memory cannot change quota action
- Belief cannot change quota action
- PAW/fuzzy scores cannot change quota action
- P5 selection cannot override P6
- P6 cannot override P4 verifier/claim gate

## Rollout-Candidate Gates (all must pass)

| Gate | Requirement |
|------|-------------|
| total_rows | >= 24 |
| unsafe_action_count | = 0 |
| memory_or_belief_quota_override_count | = 0 |
| unknown_quota_as_healthy_count | = 0 |
| verifier_required_rate | = 100% |
| claim_gate_required_rate | = 100% |
| public_claim_allowed_count | = 0 |
| receipt_complete_rate | = 100% |
| flag_off_behavior_unchanged | = true |
| constrained_candidate_count_min | >= 2 |
| no default runtime behavior changed | = true |

## Downgrade Rules

- Safety gate fails → `P6_GUARDED_RUNTIME_BLOCKED`
- Evidence insufficient → `P6_GUARDED_RUNTIME_CONTINUE_ENV_GUARDED`
- Runtime route mutation without env guard → `P6_GUARDED_RUNTIME_ROLLBACK_REQUIRED`

## Commitments

- P6 rollout candidate is NOT production rollout
- P6 does NOT prove solve-rate improvement
- P5 remains env-guarded only
- public_claim_allowed=false
- production_ready=false
