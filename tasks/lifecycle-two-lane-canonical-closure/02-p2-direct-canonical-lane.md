# Task Card 02: P2 Direct Canonical Lane

## Identity

- task_id: `lifecycle-two-lane-p2-direct-canonical-lane`
- campaign_id: `lifecycle-two-lane-canonical-closure`
- artifact_authority: current
- status: IN_PROGRESS
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

Add an explicit `DIRECT_CANONICAL` decision surface for small primary-agent work. Eligible direct work must be bound to `/Users/jameschen/Workspace/nexus` on `nexus/integration/main`, clean, non-deleting, non-authority-sensitive, and no more than four allowed files. Ineligible requests fail closed to `ISOLATED_TARGET` and must not invoke `prepare_task`.

## Allowed files

- `tasks/lifecycle-two-lane-canonical-closure/02-p2-direct-canonical-lane.md`
- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

## Verification

```bash
git diff --check
uv run pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py -k 'direct_canonical or execution_lane'
```

## Exit criteria

The service exposes a fail-closed lane decision; eligible direct requests return a direct-work handoff without creating lifecycle state or a Target; risky/dirty/delegated requests resolve to isolated execution; and focused tests pass with a scoped commit.

## Block classification

Any direct request that can create a Target, bypass the canonical branch/cleanliness checks, or be selected for delegated worker execution is a `HARD_BLOCK`.
