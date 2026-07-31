# Task Card 08: Orphan Workspace Reconciliation

## Identity

- task_id: `orphan-workspace-reconciliation`
- campaign_id: `bootstrap-authority-convergence`
- artifact_authority: current
- status: READY
- owner: James Chen
- depends_on: `workspace-retry-and-permission-gate` integrated
- read_only: true
- audit_only: true
- commit_required: false
- candidate_required: false
- worker_may_commit: false
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Produce a current, read-only reconciliation of all registered worktrees, lifecycle-owned Targets, dirty/unmapped paths, protected refs, and actionable task receipts. Identify exact owner decisions required before any cleanup; do not delete, reset, stash, prune, or cut over during this card.

## Allowed files

- `nexus/orchestrator/worktree_manager.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `scripts/engine/nexus_cli.py`

## Forbidden scope

No filesystem cleanup; no `git worktree remove`, `git clean`, `git reset`, `git stash`, branch/ref deletion, receipt deletion, or canonical-root mutation. No apply phase is authorized by this audit card.

## Required behavior

1. Inventory and actionable-task surfaces must complete without mutating state or requiring a write to an already-safe hooks directory.
2. Every path is classified as controller, protected root, active/retained Target, dirty/unknown, releasable terminal, or blocked unique commit.
3. Every proposed cleanup item includes exact path, task owner (or unbound), dirty state, process state, ref reachability, blocker code, and required human decision.
4. The result must distinguish safe future cleanup from current hard blocks; no “auto-clean all” conclusion is valid.

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/engine/nexus_cli.py self-hosted workspace-inventory --controller-root /Users/jameschen/Workspace/nexus-worktrees/integration-main --state-dir /Users/jameschen/Workspace/nexus-self-hosted-state
PYTHONDONTWRITEBYTECODE=1 python3 scripts/engine/nexus_cli.py self-hosted workspace-plan --controller-root /Users/jameschen/Workspace/nexus-worktrees/integration-main --state-dir /Users/jameschen/Workspace/nexus-self-hosted-state
PYTHONDONTWRITEBYTECODE=1 python3 scripts/engine/nexus_cli.py self-hosted list-actionable --state-dir /Users/jameschen/Workspace/nexus-self-hosted-state
```

## Exit criteria

Read-only inventory, plan, and actionable receipts complete; exact blockers and owner decisions are reported. Any apply/cleanup phase requires a new owner-authorized card bound to the exact plan hash.

## Residual debt

Actual orphan cleanup and P6 canonical-root cutover remain explicitly outside this card.

## Block classification

- `RECOVERABLE_BLOCK`: inventory read/tooling failure with no mutation.
- `HARD_BLOCK`: any request to clean a dirty, protected, unbound, or uniquely committed worktree without explicit owner approval.
