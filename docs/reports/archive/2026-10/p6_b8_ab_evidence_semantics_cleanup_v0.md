# P6-B8 A/B Evidence Semantics Cleanup

## Status: P6_B8_AB_EVIDENCE_SEMANTICS_CLEANUP_PASS

## Files Changed

| File | Action |
|------|--------|
| `tests/effects/test_p6_guarded_runtime_ab.py` | Updated schema + added semantics tests |
| `artifacts/effect_reports/p6_guarded_runtime_ab_v2.jsonl` | New artifact with clean semantics |

## Commands Run

```bash
python3 -m py_compile nexus/services/local_heal/p6_runtime_hook.py tests/effects/test_p6_guarded_runtime_ab.py

python3 -m pytest \
  tests/unit/local_heal/test_p6_quota_state.py \
  tests/unit/local_heal/test_p6_degradation_policy.py \
  tests/unit/local_heal/test_p6_receipt.py \
  tests/unit/local_heal/test_p6_runtime_hook.py \
  tests/effects/test_p6_quota_policy_simulation.py \
  tests/effects/test_p6_guarded_runtime_ab.py \
  -q
```

## Test Counts

- `test_p6_quota_state.py`: 7/7 passed
- `test_p6_degradation_policy.py`: 9/9 passed
- `test_p6_receipt.py`: 10/10 passed
- `test_p6_runtime_hook.py`: 8/8 passed
- `test_p6_quota_policy_simulation.py`: 7/7 passed
- `test_p6_guarded_runtime_ab.py`: 9/9 passed
- **Total: 50/50 passed**

## Artifact

`artifacts/effect_reports/p6_guarded_runtime_ab_v2.jsonl` (24 rows)

## Added Schema Fields

| Field | Type | Description |
|-------|------|-------------|
| `quota_scenario_budget_class` | str | The test scenario being simulated |
| `quota_scenario_known` | bool | Whether quota is known in the scenario |
| `runtime_decision_evaluated` | bool | Whether P6 hook evaluated a decision |
| `runtime_decision_budget_class` | str | Budget class used by runtime decision |
| `runtime_decision_action` | str | Action taken by runtime decision |
| `runtime_decision_reason` | str | Reason for runtime decision |
| `flag_off_default_behavior_preserved` | bool | Whether flag-off preserves default behavior |

## Semantics Explanation

**quota_scenario_budget_class** = the test scenario being simulated (healthy, constrained, exhausted, unknown). This is what we're testing, regardless of whether P6 is enabled.

**runtime_decision_budget_class** = the budget class actually used by the runtime hook decision. For flag-off rows this is "not_evaluated" because the hook never runs.

## Metrics

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
| flag_off_default_behavior_preserved_rate | 100% | = 100% ✅ |

## Statements

- P6 promotion is not P5 promotion
- P5 remains env-guarded only due to selection_changed_rate=0/20
- P6 does not prove solve-rate improvement
- P6 only proves safe quota-aware degradation behavior
- No production claim allowed
- public_claim_allowed=false
- This task does not implement P3 cloud_with_local_assist
- This task does not change default runtime behavior
