# P6 Guarded Runtime Promotion Decision v2

## Decision: B — P6_GUARDED_RUNTIME_ROLLOUT_CANDIDATE

## Evidence Summary

| Metric | Value | Gate |
|--------|-------|------|
| total_rows | 24 | >= 24 ✅ |
| rows_per_arm | 3 | >= 3 ✅ |
| artifact_semantics_clean | true | ✅ |
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

P6-B8 evidence semantics cleanup confirms:
- Off-arm rows correctly show `runtime_decision_evaluated=false` and `runtime_decision_budget_class="not_evaluated"`
- Quota scenario is preserved separately from runtime decision
- All safety gates pass with clean semantics
- Decision B (rollout candidate) remains valid

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
