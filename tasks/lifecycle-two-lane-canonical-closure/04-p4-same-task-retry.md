# Task Card 04: P4 Same-task Retry and Action Surfaces

## Identity

- task_id: `lifecycle-two-lane-p4-same-task-retry`
- campaign_id: `lifecycle-two-lane-canonical-closure`
- artifact_authority: current
- status: COMPLETED
- owner: James Chen
- audit_only: false
- commit_required: true
- candidate_required: false
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Make failure recovery point to one durable same-`task_id` retry surface. A clean no-Candidate terminal failure recommends `retry_task`; a candidate or merge failure recommends receipt inspection; a second logical task using the same Task Card hash is rejected with an explicit duplicate error.

## Allowed files

- `tasks/lifecycle-two-lane-canonical-closure/04-p4-same-task-retry.md`
- `nexus/orchestrator/self_hosted_task_service.py`
- `scripts/engine/commands/self_hosted_actions.py`
- `scripts/engine/nexus_cli.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

## Verification

```bash
git diff --check
uv run pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py -k 'retry or actionable or duplicate_logical'
```

## Exit criteria

Failure action envelopes identify retry versus receipt inspection; retry preserves the original task ID and increments the durable attempt; duplicate Task Card hashes cannot create a second logical task; a CLI receipt surface exists; and focused tests pass with a scoped commit.

## Block classification

Any retry that creates a new logical task ID, any duplicate card-hash task, or any failure action without a callable next surface is a `HARD_BLOCK`.
