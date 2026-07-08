# P6-B3 DegradationPolicy Receipt Integration

## Status: P6_B3_RECEIPT_INTEGRATION_PASS

## Files Changed

| File | Action |
|------|--------|
| `nexus/services/local_heal/p6_receipt.py` | P6Receipt dataclass + builder |
| `nexus/services/local_heal/quota_state.py` | QuotaState runtime contract |
| `nexus/services/local_heal/degradation_policy.py` | DegradationPolicy runtime decision |
| `tests/unit/local_heal/test_p6_quota_state.py` | 7 tests |
| `tests/unit/local_heal/test_p6_degradation_policy.py` | 9 tests |
| `tests/unit/local_heal/test_p6_receipt.py` | 10 tests |

## Commands Run

```bash
python3 -m py_compile \
  nexus/services/local_heal/quota_state.py \
  nexus/services/local_heal/degradation_policy.py \
  nexus/services/local_heal/p6_receipt.py \
  tests/unit/local_heal/test_p6_quota_state.py \
  tests/unit/local_heal/test_p6_degradation_policy.py \
  tests/unit/local_heal/test_p6_receipt.py

python3 -m pytest \
  tests/unit/local_heal/test_p6_quota_state.py \
  tests/unit/local_heal/test_p6_degradation_policy.py \
  tests/unit/local_heal/test_p6_receipt.py \
  -q

python3 -m pytest tests/effects/test_p6_quota_policy_simulation.py -q
```

## Test Counts

- `test_p6_quota_state.py`: 7/7 passed
- `test_p6_degradation_policy.py`: 9/9 passed
- `test_p6_receipt.py`: 10/10 passed
- `test_p6_quota_policy_simulation.py`: 7/7 passed
- **Total: 33/33 passed**

## P6 Receipt Field List (20 fields)

```
p6_enabled
p6_runtime_mode
p6_quota_state_known
p6_budget_class
p6_quota_source
p6_quota_confidence
p6_degradation_action
p6_degradation_reason
p6_candidate_count_limit
p6_cloud_allowed
p6_local_allowed
p6_committee_allowed
p6_p5_allowed
p6_memory_signal_used_for_quota
p6_belief_signal_used_for_quota
p6_verifier_required
p6_claim_gate_required
p6_runtime_route_mutation_allowed
p6_env_guard_required
p6_public_claim_allowed
```

## Sample Receipt: Healthy

```json
{
  "p6_enabled": true,
  "p6_runtime_mode": "env_guarded",
  "p6_quota_state_known": true,
  "p6_budget_class": "healthy",
  "p6_quota_source": "env",
  "p6_quota_confidence": 1.0,
  "p6_degradation_action": "keep_full_committee",
  "p6_degradation_reason": "quota_healthy",
  "p6_candidate_count_limit": null,
  "p6_cloud_allowed": true,
  "p6_local_allowed": true,
  "p6_committee_allowed": true,
  "p6_p5_allowed": true,
  "p6_memory_signal_used_for_quota": false,
  "p6_belief_signal_used_for_quota": false,
  "p6_verifier_required": true,
  "p6_claim_gate_required": true,
  "p6_runtime_route_mutation_allowed": false,
  "p6_env_guard_required": true,
  "p6_public_claim_allowed": false
}
```

## Sample Receipt: Unknown

```json
{
  "p6_enabled": true,
  "p6_runtime_mode": "env_guarded",
  "p6_quota_state_known": false,
  "p6_budget_class": "unknown",
  "p6_quota_source": "env",
  "p6_quota_confidence": 0.0,
  "p6_degradation_action": "fail_closed",
  "p6_degradation_reason": "quota_unknown_conservative",
  "p6_candidate_count_limit": 0,
  "p6_cloud_allowed": false,
  "p6_local_allowed": true,
  "p6_committee_allowed": false,
  "p6_p5_allowed": false,
  "p6_memory_signal_used_for_quota": false,
  "p6_belief_signal_used_for_quota": false,
  "p6_verifier_required": true,
  "p6_claim_gate_required": true,
  "p6_runtime_route_mutation_allowed": false,
  "p6_env_guard_required": true,
  "p6_public_claim_allowed": false
}
```

## Proof: Memory/Belief Cannot Alter Quota Action

- `p6_memory_signal_used_for_quota` is hardcoded `false` in `build_p6_receipt()`
- `p6_belief_signal_used_for_quota` is hardcoded `false` in `build_p6_receipt()`
- `evaluate_degradation_policy()` does not accept memory or belief inputs
- `DegradationDecision.memory_signal_used_for_quota` is hardcoded `false`

## Proof: Verifier/Claim Gate Remain Required

- `p6_verifier_required` is hardcoded `true` in `P6Receipt`
- `p6_claim_gate_required` is hardcoded `true` in `P6Receipt`
- `evaluate_degradation_policy()` returns `verifier_required=True` always
- `evaluate_degradation_policy()` returns `claim_gate_required=True` always

## Statements

- No runtime route changed
- P6-B4 not implemented
- P5 remains env-guarded only
- public_claim_allowed=false
- production_ready=false
