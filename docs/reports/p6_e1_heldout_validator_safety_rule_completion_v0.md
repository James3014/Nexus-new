# P6-E1 Heldout Validator Safety Rule Completion

## Status: P6_E1_HELDOUT_VALIDATOR_SAFETY_RULE_COMPLETION_PASS

## Files Changed

| File | Action |
|------|--------|
| `nexus/services/local_heal/p6_heldout_validator.py` | Added 4 safety rules + new violation fields |
| `tests/unit/local_heal/test_p6_heldout_validator.py` | 11 tests |
| `artifacts/effect_fixtures/p6_quota_scenario_heldout_plan_v0.json` | Fixed unknown/exhausted cases |

## New Safety Rules

1. unknown quota must not be keep_full_committee or cloud_allowed
2. constrained reduce_candidate_count requires min >= 2
3. exhausted_local_unavailable must be fail_closed or diagnosis_only
4. action/permission consistency checks

## Statements

- No runtime behavior changed
- No Agent A files changed
