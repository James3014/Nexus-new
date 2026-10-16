# P6 Guarded Runtime Promotion Decision v1

## Decision: B — P6_GUARDED_RUNTIME_ROLLOUT_CANDIDATE

## Evidence Summary

| Metric | Value | Gate |
|--------|-------|------|
| total_rows | 24 | >= 24 ✅ |
| rows_per_arm | 3 | >= 3 ✅ |
| unsafe_action_count | 0 | = 0 ✅ |
| memory_or_belief_quota_override_count | 0 | = 0 ✅ |
| unknown_quota_as_healthy_count | 0 | = 0 ✅ |
| verifier_required_rate | 100% | = 100% ✅ |
| claim_gate_required_rate | 100% | = 100% ✅ |
| public_claim_allowed_count | 0 | = 0 ✅ |
| receipt_complete_rate | 100% | = 100% ✅ |
| flag_off_behavior_unchanged | true | ✅ |
| constrained_candidate_count_min | 2 | >= 2 ✅ |

## Decision Rationale

All B7 decision gates pass:
- 24 rows across 8 arms (3 variants each)
- Zero unsafe actions
- Zero memory/belief quota overrides
- Zero unknown quota treated as healthy
- 100% verifier/claim gate required
- 100% receipt complete
- Flag-off behavior unchanged
- Constrained quota reduces candidate count but never below 2
- Exhausted/local maps to local_only
- Unknown maps to fail_closed

P6 guarded runtime is safe and ready for rollout candidate status.

## P5 Status

P5 remains env-guarded only:
- selection_changed_rate = 0/20 on real candidate pools
- No observed selection benefit
- Safety gates pass but no promotion signal

## Statements

- P6 promotion is not P5 promotion
- P5 remains env-guarded only due to selection_changed_rate=0/20
- P6 does not prove solve-rate improvement
- P6 only proves safe quota-aware degradation behavior
- No production claim allowed
- public_claim_allowed=false
- This task does not implement P3 cloud_with_local_assist
- This task does not change default runtime behavior

## Next Steps

1. P6 rollout candidate status confirmed
2. P5-S3 diagnostic: investigate why selection_changed_rate = 0
3. Consider P6-A1 runtime integration with broader rollout
