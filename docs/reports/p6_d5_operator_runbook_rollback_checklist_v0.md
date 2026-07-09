# P6-D5 Operator Runbook and Rollback Checklist

## Status: P6_D5_OPERATOR_RUNBOOK_ROLLBACK_CHECKLIST_PASS

## Files Changed

| File | Action |
|------|--------|
| `docs/runbooks/p6_guarded_rollout_operator_runbook_v0.md` | Operator runbook |
| `docs/reports/p6_d5_operator_runbook_rollback_checklist_v0.md` | Report |

## Runbook Path

`docs/runbooks/p6_guarded_rollout_operator_runbook_v0.md`

## Rollback Triggers

- unsafe_action_count > 0
- public_claim_allowed_count > 0
- verifier_required_rate < 100%
- claim_gate_required_rate < 100%
- unknown_quota_as_healthy_count > 0
- memory/belief quota override > 0
- runtime mutation without env guard

## Statements

- Doc-only
- No runtime behavior changed
- No Agent A files changed
