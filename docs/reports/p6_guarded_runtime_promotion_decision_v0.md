# P6 Guarded Runtime Promotion Decision

## Decision: A — P6_GUARDED_RUNTIME_CONTINUE_ENV_GUARDED

## Evidence Summary

| Metric | Value | Gate |
|--------|-------|------|
| P6-B5 total rows | 8 | >= 24 ⚠️ (insufficient) |
| unsafe_action_count | 0 | = 0 ✅ |
| memory_or_belief_quota_override_count | 0 | = 0 ✅ |
| unknown_quota_never_healthy | true | ✅ |
| verifier_required_rate | 100% | = 100% ✅ |
| claim_gate_required_rate | 100% | = 100% ✅ |
| public_claim_allowed_count | 0 | = 0 ✅ |
| receipt_complete_rate | 100% | = 100% ✅ |
| flag_off_behavior_unchanged | true | ✅ |
| constrained_candidate_count >= 2 | true | ✅ |
| exhausted/local_available → local_only | true | ✅ |
| exhausted/local_unavailable → fail_closed | true | ✅ |
| unknown → fail_closed | true | ✅ |

## Gate Results

### ✅ Passed
- unsafe_action_count = 0
- memory/belief cannot change quota action
- verifier_required always true
- claim_gate_required always true
- public_claim_allowed always false
- receipt_complete always true
- flag-off behavior unchanged
- constrained quota reduces candidate count
- exhausted/local maps to local_only
- exhausted/no_local maps to fail_closed
- unknown maps to fail_closed (never healthy)

### ⚠️ Partial
- P6-B5 total rows = 8 (spec requires >= 24)

## Decision Rationale

P6 guarded runtime is **safe** — all safety gates pass, no unsafe actions, memory/belief cannot override quota. However, promotion to rollout candidate requires >= 24 A/B rows per spec. Current 8 rows are insufficient for full statistical confidence.

**Decision A (CONTINUE_ENV_GUARDED)** is appropriate because:
1. Safety is proven but data volume is insufficient
2. No reason to block continued env-guarded usage
3. More data needed before broader rollout

## P5 Status

P5 remains env-guarded only:
- selection_changed_rate = 0/20 on real candidate pools
- No observed selection benefit
- Safety gates pass but no promotion signal

## Next Steps

1. Continue P6 env-guarded runtime in production
2. Collect more A/B rows (target: 24+)
3. Re-evaluate promotion after sufficient data
4. P5-S3 diagnostic: investigate why selection_changed_rate = 0
