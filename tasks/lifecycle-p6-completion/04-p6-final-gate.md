# Task Card 04: P6 Final Gate

## Identity

- task_id: `lifecycle-p6-final-gate`
- campaign_id: `lifecycle-p6-completion`
- artifact_authority: current
- status: PENDING
- owner: James Chen
- depends_on: `lifecycle-p3-allocator-p6-operator-surfaces`, `orphan-workspace-reconciliation`, `lifecycle-p5-cutover-rehearsal`
- read_only: true
- audit_only: true
- commit_required: false
- candidate_required: false
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false

## Objective

Perform the final P6 operator, timeout, lock, cleanup-dry-run, and bounded performance checks on the isolated Candidate stack, then return a fail-closed verdict with residual owner-only gates.

## Forbidden scope

No lifecycle JSON edits, live cleanup, branch/ref deletion, approval, integration, push, or canonical-root mutation.

## Exit criteria

P6 command probes and regression tests pass; any semantic failure (including missing durable Candidate binding) is reported as a fail-closed lifecycle result with `next_action`, not hidden or converted into success.
