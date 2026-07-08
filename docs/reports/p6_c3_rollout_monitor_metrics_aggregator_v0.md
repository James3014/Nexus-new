# P6-C3 Rollout Monitor / Metrics Aggregator

## Status: P6_C3_ROLLOUT_MONITOR_METRICS_AGGREGATOR_PASS

## Files Changed

| File | Action |
|------|--------|
| `nexus/services/local_heal/p6_rollout_monitor.py` | P6RolloutMetrics + compute_rollout_metrics() |
| `tests/unit/local_heal/test_p6_rollout_monitor.py` | 7 tests |

## Metrics Fields

- total_rows, rows_per_arm, rows_per_arm_min
- unsafe_action_count, memory_or_belief_quota_override_count
- unknown_quota_as_healthy_count, verifier_required_rate
- claim_gate_required_rate, public_claim_allowed_count
- receipt_complete_rate, flag_off_behavior_unchanged_rate
- constrained_candidate_count_min, rollout_candidate_gate_passed
- blocked_reasons

## Statements

- No runtime behavior changed
- No live monitoring
- No production rollout
- public_claim_allowed=false
