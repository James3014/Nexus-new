# Task Card 07: Workspace Retry and Permission Gate

## Identity

- task_id: `workspace-retry-and-permission-gate`
- campaign_id: `bootstrap-authority-convergence`
- artifact_authority: current
- status: INTEGRATED_WITH_OWNER_REVIEW
- owner: James Chen
- depends_on: `briefing-overlay-reduction` integrated
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Stop lifecycle retries from requiring a new task/workspace and make read-only workspace inventory resilient to a permission-preserving hooks directory. A retry must reuse the exact task ID, archived state, Task Card binding, and governed target rules; it must never duplicate an active Target or bypass retained-review blockers.

## Allowed files

- `nexus/orchestrator/worktree_manager.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `scripts/engine/commands/self_hosted_actions.py`
- `scripts/engine/nexus_cli.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/engine/test_self_hosted_cli.py`

## Forbidden scope

No canonical-root mutation; no deletion or rewriting of historical receipts; no automatic disposal of dirty/retained Targets; no bypass of Task Card, approval, candidate, integration, or cleanup authority; no P6 cutover.

## Required behavior

1. `get_canonical_git_hooks_dir` validates an already-correct directory without requiring a write; a failed chmod is recoverable only when mode/owner are already safe, otherwise it remains fail-closed.
2. Read-only workspace inventory/plan/status can report a structured permission blocker instead of crashing the task surface.
3. `self-hosted retry --task-id` reuses the durable request only for a terminal task whose previous Target disposition is removed/cleaned; active, pending, dirty, or retained tasks return an explicit no-duplicate/block decision.
4. Retry increments attempt history, preserves prior candidate/receipt history, and binds the new attempt to the same Task Card and lifecycle revision.
5. Focused tests prove idempotency, retained-review protection, and permission-safe inventory behavior.

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py tests/engine/test_self_hosted_cli.py
git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
```

## Exit criteria

Same-task retry and permission-safe read-only inventory are implemented, tested, and committed; no duplicate Target is created and retained evidence remains protected.

## Integrated evidence

- commit: `86c197690`
- verification: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py tests/engine/test_self_hosted_cli.py` (`88 + 30 passed`)
- focused proof: retry/permission subset `27 passed`; live `self-hosted retry` on retained task returned `BLOCKED_RETAINED_REVIEW` without acquiring the canonical state lock
- live workspace proof: inventory completed and classified controller, protected root, dirty/unmapped Targets, and retained task Target without PermissionError

## Residual debt

Automatic orphan scanning and owner-authorized bulk cleanup remain separate from retry and must not be inferred from this card.

## Block classification

- `RECOVERABLE_BLOCK`: permission/test environment failure with state preserved.
- `HARD_BLOCK`: retry would require changing Task Card identity, reusing dirty evidence, or bypassing human disposition.
