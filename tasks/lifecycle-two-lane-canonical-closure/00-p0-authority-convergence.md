# Task Card 00: P0 Authority Convergence

## Identity

- task_id: `lifecycle-two-lane-p0-authority-convergence`
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

Make the two-lane campaign the only current lifecycle authority. Freeze stale lifecycle campaign frontiers as historical or superseded without deleting evidence, editing lifecycle JSON, or touching runtime code.

## Allowed files

- `tasks/lifecycle-two-lane-canonical-closure/INDEX.md`
- `tasks/lifecycle-two-lane-canonical-closure/00-p0-authority-convergence.md`
- `tasks/lifecycle-canonical-authority-convergence/INDEX.md`
- `tasks/self-hosted-operator-workflow/INDEX.md`
- `tasks/workspace-control-convergence/INDEX.md`

## Required changes

1. Declare the new campaign current and P0 its current frontier.
2. Mark the old canonical-authority campaign superseded by this campaign while preserving cards and receipts as historical evidence.
3. Freeze the operator-workflow frontier as historical; runtime closeout is revalidated by P1-P4.
4. Update workspace-control authority so only the daily source and registered Nexus worktree is `/Users/jameschen/Workspace/nexus`; the old Controller is evidence-only.
5. Preserve `AUTO_CHAIN=false` and owner-only approval, integration, push, and cleanup boundaries.

## Verification

```bash
git diff --check
git diff --name-status --diff-filter=D
git status --short --branch
rg -n "current_frontier|Controller:|clean Controller|status: active" tasks/lifecycle-canonical-authority-convergence/INDEX.md tasks/self-hosted-operator-workflow/INDEX.md tasks/workspace-control-convergence/INDEX.md
```

## Exit criteria

No named stale campaign claims current lifecycle authority; the new index and card are consistent; there is no tracked deletion, runtime mutation, branch/ref deletion, or external workspace deletion; and a scoped commit exists.

## Block classification

Any inability to form the scoped documentation commit is a `HARD_BLOCK`. Historical evidence remains preserved and no replacement card may start until the authority conflict is resolved.
