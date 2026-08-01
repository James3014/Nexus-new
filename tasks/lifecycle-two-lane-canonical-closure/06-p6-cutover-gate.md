# Task Card 06: P6 Thirty-task Cutover Gate

## Identity

- task_id: `lifecycle-two-lane-p6-cutover-gate`
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

Run a 30-task cutover matrix proving the two lanes converge on one canonical source: ordinary small primary-agent work creates no Target and no lifecycle state; governed isolated work selects one isolated lane; retries preserve task identity; read-only surfaces remain side-effect free; and the canonical checkout remains clean.

## Allowed files

- `tasks/lifecycle-two-lane-canonical-closure/INDEX.md`
- `tasks/lifecycle-two-lane-canonical-closure/00-p0-authority-convergence.md`
- `tasks/lifecycle-two-lane-canonical-closure/01-p1-read-only-zero-side-effects.md`
- `tasks/lifecycle-two-lane-canonical-closure/02-p2-direct-canonical-lane.md`
- `tasks/lifecycle-two-lane-canonical-closure/03-p3-owner-finish.md`
- `tasks/lifecycle-two-lane-canonical-closure/04-p4-same-task-retry.md`
- `tasks/lifecycle-two-lane-canonical-closure/05-p5-target-root-and-telemetry.md`
- `tasks/lifecycle-two-lane-canonical-closure/06-p6-cutover-gate.md`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

## Verification

```bash
git diff --check
uv run pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py -k 'thirty_task_cutover or canonical_clean'
git status --short --branch
git worktree list --porcelain
```

## Exit criteria

All 30 matrix rows pass; direct rows report `DIRECT_CANONICAL_READY` with `state_created=false` and `target_created=false`; isolated rows report `ISOLATED_TARGET`; no duplicate task IDs or active Target is created; canonical status is clean; and a scoped commit exists.

## Block classification

Any failed row, unexpected Target/state creation, duplicate logical task, stale current campaign, or dirty canonical checkout is a `HARD_BLOCK`; retain evidence and do not claim lifecycle completion.
