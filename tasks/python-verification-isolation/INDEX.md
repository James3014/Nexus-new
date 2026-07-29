# Python Verification Isolation and Tracked Bytecode Cleanup

**artifact_authority:** current
**owner:** James Chen
**status:** active, governed and sequential
**source_decision:** user-authorized remediation after AGY Controller contamination finding
**controller_base_revision:** `06bd067d814e7667cbdcb40fe31e9fcfcd1d330a`
**AUTO_CHAIN:** false

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `python-verification-isolation-guard` | `00-python-verification-isolation-guard.md` | PENDING | campaign bootstrap integrated |
| 1 | `tracked-bytecode-cleanup-core` | `01-tracked-bytecode-cleanup-core.md` | PENDING | guard integrated |
| 2 | `tracked-bytecode-cleanup-verifier-base` | `02-tracked-bytecode-cleanup-verifier-base.md` | PENDING | core cleanup integrated |
| 3 | `tracked-bytecode-cleanup-concurrency` | `03-tracked-bytecode-cleanup-concurrency.md` | PENDING | verifier-base cleanup integrated |
| 4 | `tracked-bytecode-cleanup-django-tests` | `04-tracked-bytecode-cleanup-django-tests.md` | PENDING | concurrency cleanup integrated |

## Current frontier

`python-verification-isolation-guard` is the only current frontier after this campaign bootstrap is independently approved and integrated. No cleanup card may start until the guard Candidate is integrated. No card may self-chain after completion, failure, Candidate formation, or BLOCK.

## Completion condition

The campaign is complete only when:

- the Worker environment forces `PYTHONDONTWRITEBYTECODE=1`;
- Candidate verification fails closed on verifier-created repository mutations;
- all 30 listed tracked `__pycache__/*.pyc` artifacts are absent from `git ls-files`;
- focused tests pass after every batch;
- the canonical Controller remains clean;
- no source, test, receipt, learning ledger, or unrelated generated artifact is deleted.

## Completed cards

None.

## Blocked or superseded cards

None.
