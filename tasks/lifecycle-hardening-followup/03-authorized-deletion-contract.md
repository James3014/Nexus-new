# Task Card 03: Authorized Deletion Contract

## Identity

- task_id: `authorized-deletion-contract`
- campaign_id: `lifecycle-hardening-followup`
- artifact_authority: current
- status: PLANNED
- owner: James Chen
- depends_on: `verify-task-target-integrity` integrated
- read_only: false
- audit_only: false
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Define an explicit, current-base `authorized_deletions` contract for lifecycle verification and cleanup. A deletion is valid only when it is declared by the Task Card/contract, remains within allowed scope, and is independently evidenced; undeclared deletion must continue to fail closed.

## Allowed files

- `nexus/orchestrator/task_contract.py`
- `nexus/orchestrator/candidate_verifier.py`
- `nexus/orchestrator/candidate_commit.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `scripts/engine/commands/self_hosted_actions.py`
- `tests/nexus/orchestrator/test_candidate_verifier.py`
- `tests/nexus/orchestrator/test_candidate_commit.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

## Forbidden scope

No direct JSON editing, cleanup apply, worktree removal, branch/ref deletion, approval, integration, push, canonical-root mutation, or GitNexus instructions. Do not merge the stale salvage commit from the old task.

## Required behavior

1. Contract and MCP/service mapping carry `authorized_deletions` explicitly.
2. Scope verification accepts only exact authorized deletions and rejects undeclared or out-of-scope deletions.
3. Receipts record the authorized deletion set and source hash.
4. Existing no-deletion and protected-file gates remain fail-closed.
5. Focused tests cover declared, undeclared, out-of-scope, and tampered authorization cases.

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/nexus/orchestrator/test_candidate_verifier.py tests/nexus/orchestrator/test_candidate_commit.py tests/nexus/orchestrator/test_self_hosted_task_service.py
git diff --check
```

## Evidence required

- Current-base contract/schema diff.
- RED→GREEN tests for all authorization boundaries.
- Exact scoped commit, candidate binding, and no approval/integration claim.

## Exit criteria

The current lifecycle contract can represent and verify authorized deletions without widening cleanup authority, and a scoped commit is created.

## Residual debt

Workspace cleanup apply and P6 canonical-root cutover require separate owner-authorized cards bound to fresh inventory/plan hashes.

## Block classification

- `RECOVERABLE_BLOCK`: isolated test/runtime dependency failure.
- `HARD_BLOCK`: exact deletion authority cannot be represented without broadening cleanup or bypassing Task Card governance.
