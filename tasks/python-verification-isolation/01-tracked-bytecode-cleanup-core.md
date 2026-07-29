# Tracked Bytecode Cleanup — Core Domains

**artifact_authority:** current
**owner:** James Chen
**status:** PENDING
**task_id:** `tracked-bytecode-cleanup-core`
**AUTO_CHAIN:** false
**controller_base_revision:** `bf6afeddf921128b061a6bc65f6228650f22627d`
**depends_on:** `candidate-commit-subprocess-env-isolation` integrated
**commit_required:** true
**candidate_required:** true
**worker_may_commit:** true
**worker_may_approve:** false
**worker_may_integrate:** false
**worker_may_push:** false

## Objective

Remove the first seven tracked Python bytecode artifacts after the isolation guard is integrated. This is a deletion-only mechanical task.

## Allowed deletions

- `nexus/experimental/__pycache__/__init__.cpython-314.pyc`
- `nexus/experimental/__pycache__/sandboxed_adapter.cpython-314.pyc`
- `nexus/research/domain/__pycache__/__init__.cpython-314.pyc`
- `nexus/research/domain/__pycache__/route_planner.cpython-314.pyc`
- `nexus/research/domain/__pycache__/routing_receipt.cpython-314.pyc`
- `nexus/rollout/__pycache__/__init__.cpython-314.pyc`
- `nexus/rollout/__pycache__/canary_guard.cpython-314.pyc`

No other path may change.

## Verification commands

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q \
  tests/unit/experimental \
  tests/unit/research \
  tests/unit/rollout

git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
git ls-files | rg '(^|/)__pycache__/.*\.pyc$'
```

## Evidence and exit criteria

- Exactly seven deletions are present and match the list above.
- No source or test file is modified.
- Focused tests pass.
- Remaining tracked bytecode count is exactly 23.
- Candidate is committed, protected, and left pending independent approval.
- The next cleanup card is not activated automatically.

## Block and claim boundary

Unexpected deletion, source modification, or a bytecode path outside the exact list is an evidence-integrity conflict. Temporary tool or environment issues must be recovered and retried on the same card.

Allowed claim: `TRACKED_BYTECODE_CORE_BATCH_CANDIDATE_READY`.

Must remain false: `ALL_TRACKED_BYTECODE_REMOVED`, `PRODUCTION_READY`, `PUBLIC_CLAIM_ALLOWED`.
