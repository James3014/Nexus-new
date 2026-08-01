# Task Card 05: P5 Target Root and Telemetry

## Identity

- task_id: `lifecycle-two-lane-p5-target-root-and-telemetry`
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

Move governed isolated Targets out of the disabled `/Users/jameschen/Workspace/nexus-worktrees` namespace into `/Users/jameschen/Workspace/nexus-runtime-targets`, preserve lazy creation, and record wall-time/overhead telemetry in durable receipts.

## Allowed files

- `tasks/lifecycle-two-lane-canonical-closure/05-p5-target-root-and-telemetry.md`
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/worktree_manager.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_worktree_manager.py`

## Verification

```bash
git diff --check
uv run pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py -k 'telemetry or target_root or workspace'
uv run pytest -q tests/nexus/orchestrator/test_worktree_manager.py -k 'hooks or workspace_inventory'
```

## Exit criteria

Default production Target roots resolve under `/Users/jameschen/Workspace/nexus-runtime-targets`; the disabled worktree namespace is not used by new lifecycle code; read-only calls remain lazy; terminal checkpoints and receipts expose numeric `wall_time_ms` and `overhead_ms`; and focused tests pass with a scoped commit.

## Block classification

Any new default Target under `nexus-worktrees`, missing telemetry, or eager root creation is a `HARD_BLOCK`.
