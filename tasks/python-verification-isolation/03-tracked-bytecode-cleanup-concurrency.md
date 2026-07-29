# Tracked Bytecode Cleanup — Concurrency Verifier Domain

**artifact_authority:** current
**owner:** James Chen
**status:** PENDING
**task_id:** `tracked-bytecode-cleanup-concurrency`
**AUTO_CHAIN:** false
**controller_base_revision:** `06bd067d814e7667cbdcb40fe31e9fcfcd1d330a`
**depends_on:** `tracked-bytecode-cleanup-verifier-base` integrated
**commit_required:** true
**candidate_required:** true
**worker_may_commit:** true
**worker_may_approve:** false
**worker_may_integrate:** false
**worker_may_push:** false

## Objective

Remove seven tracked bytecode artifacts from the concurrency verifier domain. This is a deletion-only mechanical task.

## Allowed deletions

- `nexus/verifiers/domain/concurrency/__pycache__/__init__.cpython-314.pyc`
- `nexus/verifiers/domain/concurrency/__pycache__/buggy_targets.cpython-314.pyc`
- `nexus/verifiers/domain/concurrency/__pycache__/buggy_targets_batch_b01.cpython-314.pyc`
- `nexus/verifiers/domain/concurrency/__pycache__/buggy_targets_batch_b02.cpython-314.pyc`
- `nexus/verifiers/domain/concurrency/__pycache__/fixed_targets.cpython-314.pyc`
- `nexus/verifiers/domain/concurrency/__pycache__/fixed_targets_batch_b01.cpython-314.pyc`
- `nexus/verifiers/domain/concurrency/__pycache__/fixed_targets_batch_b02.cpython-314.pyc`

No other path may change.

## Verification commands

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/unit/verifiers/concurrency

git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
git ls-files | rg '(^|/)__pycache__/.*\.pyc$'
```

## Evidence and exit criteria

- Exactly seven deletions are present and match the list above.
- No source or test file is modified.
- Focused tests pass.
- Remaining tracked bytecode count is exactly 10.
- Candidate is committed, protected, and left pending independent approval.
- The next cleanup card is not activated automatically.

## Block and claim boundary

Unexpected deletion, source modification, or a bytecode path outside the exact list is an evidence-integrity conflict. Temporary tool or environment issues must be recovered and retried on the same card.

Allowed claim: `TRACKED_BYTECODE_CONCURRENCY_BATCH_CANDIDATE_READY`.

Must remain false: `ALL_TRACKED_BYTECODE_REMOVED`, `PRODUCTION_READY`, `PUBLIC_CLAIM_ALLOWED`.
