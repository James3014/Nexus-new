# P6 Guarded Rollout Operator Runbook

## Purpose

P6 guarded quota-aware degradation only. Not production default. Not public claim. Not solve-rate claim.

## Preconditions

- P6-D1 readiness report accepted
- P6-D2 boundary accepted
- P6-D3 heldout plan exists
- P6-D4 validator passes
- P5 remains env-guarded only
- P4 verifier/claim gate required

## Enablement

- Env guard required: `NEXUS_ENABLE_P6_QUOTA_DEGRADATION=1`
- Default runtime remains off unless explicitly approved
- No public claim

## Observation

- Monitor metrics: unsafe_action_count, unknown_quota_as_healthy_count, memory_override_count
- Canary states: continue_env_guarded, allow_rollout_candidate, pause_canary, block_canary, rollback_required
- Receipt fields: p6_rollout_state, p6_degradation_action, p6_budget_class

## Pause / Block / Rollback Triggers

- unsafe_action_count > 0 → **rollback_required**
- public_claim_allowed_count > 0 → **rollback_required**
- verifier_required_rate < 100% → **rollback_required**
- claim_gate_required_rate < 100% → **rollback_required**
- unknown_quota_as_healthy_count > 0 → **rollback_required**
- memory/belief quota override > 0 → **rollback_required**
- runtime mutation without env guard → **rollback_required**

## Operator Checklist

### Before Enable
- [ ] P6-D1 readiness report accepted
- [ ] P6-D2 boundary accepted
- [ ] P6-D3 heldout plan exists
- [ ] P6-D4 validator passes
- [ ] P5 remains env-guarded
- [ ] P4 verifier/claim gate required

### During Canary
- [ ] Monitor unsafe_action_count
- [ ] Monitor unknown_quota_as_healthy_count
- [ ] Check canary decision state
- [ ] Inspect receipt fields

### After Canary
- [ ] Verify public_claim_allowed=false
- [ ] Verify production_ready=false
- [ ] Verify default_runtime_allowed=false

### Rollback
- [ ] Set `NEXUS_ENABLE_P6_QUOTA_DEGRADATION=0`
- [ ] Verify runtime behavior unchanged
- [ ] Record rollback reason
