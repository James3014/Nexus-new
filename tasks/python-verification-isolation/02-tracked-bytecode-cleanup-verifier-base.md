# Tracked Bytecode Cleanup — Verifier Base Domains

**artifact_authority:** current
**owner:** James Chen
**status:** PENDING
**task_id:** `tracked-bytecode-cleanup-verifier-base`
**AUTO_CHAIN:** false
**controller_base_revision:** `06bd067d814e7667cbdcb40fe31e9fcfcd1d330a`
**depends_on:** `tracked-bytecode-cleanup-core` integrated
**commit_required:** true
**candidate_required:** true
**worker_may_commit:** true
**worker_may_approve:** false
**worker_may_integrate:** false
**worker_may_push:** false

## Objective

Remove six tracked bytecode artifacts from the astropy and common-core verifier domains. This is a deletion-only mechanical task.

## Allowed deletions

- `nexus/verifiers/domain/astropy/__pycache__/__init__.cpython-314.pyc`
- `nexus/verifiers/domain/astropy/__pycache__/astrophysics_guard.cpython-314.pyc`
- `nexus/verifiers/domain/astropy/__pycache__/fits_reader.cpython-314.pyc`
- `nexus/verifiers/domain/common_core/__pycache__/__init__.cpython-314.pyc`
- `nexus/verifiers/domain/common_core/__pycache__/lock_helpers.cpython-314.pyc`
- `nexus/verifiers/domain/common_core/__pycache__/state_guards.cpython-314.pyc`

No other path may change.

## Verification commands

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q \
  tests/unit/verifiers/astropy \
  tests/unit/verifiers/common_core

git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
git ls-files | rg '(^|/)__pycache__/.*\.pyc$'
```

## Evidence and exit criteria

- Exactly six deletions are present and match the list above.
- No source or test file is modified.
- Focused tests pass.
- Remaining tracked bytecode count is exactly 17.
- Candidate is committed, protected, and left pending independent approval.
- The next cleanup card is not activated automatically.

## Block and claim boundary

Unexpected deletion, source modification, or a bytecode path outside the exact list is an evidence-integrity conflict. Temporary tool or environment issues must be recovered and retried on the same card.

Allowed claim: `TRACKED_BYTECODE_VERIFIER_BASE_BATCH_CANDIDATE_READY`.

Must remain false: `ALL_TRACKED_BYTECODE_REMOVED`, `PRODUCTION_READY`, `PUBLIC_CLAIM_ALLOWED`.
