# Tracked Bytecode Cleanup — Django and Test Package Markers

**artifact_authority:** current
**owner:** James Chen
**status:** PENDING
**task_id:** `tracked-bytecode-cleanup-django-tests`
**AUTO_CHAIN:** false
**controller_base_revision:** `06bd067d814e7667cbdcb40fe31e9fcfcd1d330a`
**depends_on:** `tracked-bytecode-cleanup-concurrency` integrated
**commit_required:** true
**candidate_required:** true
**worker_may_commit:** true
**worker_may_approve:** false
**worker_may_integrate:** false
**worker_may_push:** false

## Objective

Remove the final ten tracked bytecode artifacts from the Django verifier domain and unit-test package markers. This is a deletion-only mechanical task.

## Allowed deletions

- `nexus/verifiers/domain/django/__pycache__/__init__.cpython-314.pyc`
- `nexus/verifiers/domain/django/__pycache__/django_core_logic_guard.cpython-314.pyc`
- `nexus/verifiers/domain/django/__pycache__/django_migration_guard.cpython-314.pyc`
- `tests/unit/experimental/__pycache__/__init__.cpython-314.pyc`
- `tests/unit/research/__pycache__/__init__.cpython-314.pyc`
- `tests/unit/rollout/__pycache__/__init__.cpython-314.pyc`
- `tests/unit/verifiers/astropy/__pycache__/__init__.cpython-314.pyc`
- `tests/unit/verifiers/common_core/__pycache__/__init__.cpython-314.pyc`
- `tests/unit/verifiers/concurrency/__pycache__/__init__.cpython-314.pyc`
- `tests/unit/verifiers/django/__pycache__/__init__.cpython-314.pyc`

No other path may change.

## Verification commands

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q \
  tests/unit/verifiers/django \
  tests/unit/experimental \
  tests/unit/research \
  tests/unit/rollout

git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
! git ls-files | rg '(^|/)__pycache__/.*\.pyc$'
```

## Evidence and exit criteria

- Exactly ten deletions are present and match the list above.
- No source or test file is modified.
- Focused tests pass.
- `git ls-files` returns zero tracked Python bytecode artifacts.
- A second bounded Python test run does not recreate tracked bytecode or dirty the Target.
- Candidate is committed, protected, and left pending independent approval.
- Campaign completion requires governed integration and a clean canonical Controller.

## Block and claim boundary

Unexpected deletion, source modification, or a bytecode path outside the exact list is an evidence-integrity conflict. Temporary tool or environment issues must be recovered and retried on the same card.

Allowed claim after Candidate verification: `ALL_TRACKED_BYTECODE_REMOVAL_CANDIDATE_READY`.

Must remain false until governed integration and Controller re-verification: `ALL_TRACKED_BYTECODE_REMOVED`, `PRODUCTION_READY`, `PUBLIC_CLAIM_ALLOWED`.
