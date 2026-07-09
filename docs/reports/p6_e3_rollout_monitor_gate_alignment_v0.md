# P6-E3 Rollout Monitor Gate Alignment

## Status: P6_E3_ROLLOUT_MONITOR_GATE_ALIGNMENT_PASS

## Files Changed

| File | Action |
|------|--------|
| `nexus/services/local_heal/p6_rollout_monitor.py` | Updated metric semantics |
| `tests/unit/local_heal/test_p6_rollout_monitor.py` | 7 tests |

## Key Changes

- flag_off_behavior_unchanged_rate uses off-arm rows only
- Required arms checked
- Unknown-as-healthy detection
- Constrained candidate count validation

## Statements

- No runtime behavior changed
- No Agent A files changed
