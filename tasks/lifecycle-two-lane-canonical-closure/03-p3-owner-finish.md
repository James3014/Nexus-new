# Task Card 03: P3 Owner Finish

## Identity

- task_id: `lifecycle-two-lane-p3-owner-finish`
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

Provide one owner-only `owner_finish` operation that validates the exact Candidate binding, records approval, and immediately integrates to `nexus/integration/main` without push. Keep approval and integration authority out of Worker execution.

## Allowed files

- `tasks/lifecycle-two-lane-canonical-closure/03-p3-owner-finish.md`
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/self_hosted_mcp.py`
- `scripts/engine/commands/self_hosted_actions.py`
- `scripts/engine/nexus_cli.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

## Verification

```bash
git diff --check
uv run pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py -k 'owner_finish'
```

## Exit criteria

Owner finish is exposed through service, MCP, and CLI action surfaces; it performs approval then integration in one call; invalid bindings fail before integration; and focused tests pass with a scoped commit.

## Block classification

Any path that lets a Worker call owner finish, pushes, or integrates without the exact four-field binding is a `HARD_BLOCK`.
