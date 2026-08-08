# Campaign Index: preapply-closure-reconcile-recovery-20260809

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Preserve and recover exact verified Candidate/closure evidence when a task is in
`INTEGRATION_FAILED_PRE_APPLY`, including the known legacy projection into
`FINAL_BLOCK`, without replaying provider work or reusing stale approval.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `PREAPPLY-CLOSURE-RECONCILE-RECOVERY-01` | `00-PREAPPLY-CLOSURE-RECONCILE-RECOVERY-01.md` | ACTIVE | integrate/re-anchor after externally owned worker-readiness Candidate |

## Governance

- Existing Candidate, closure, approval, and integration identity remain the
  only authority; no second recovery lifecycle is introduced.
- Worker may create one scoped Candidate commit only. Approval, integration,
  live state mutation, reload, cleanup, and push remain primary/Owner actions.
- `AUTO_CHAIN=false`.
