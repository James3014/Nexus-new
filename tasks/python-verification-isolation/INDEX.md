# Python Verification Isolation and Tracked Bytecode Cleanup

**artifact_authority:** current
**owner:** James Chen
**status:** blocked pending exact authorized deletion contract
**source_decision:** user-authorized remediation after AGY Controller contamination finding
**controller_base_revision:** `06e211496e05be3d42a7d079ef6f215977774f95`
**AUTO_CHAIN:** false

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0a | `python-verification-isolation-runtime-guard` | `00a-python-verification-isolation-runtime-guard.md` | COMPLETED | campaign bootstrap integrated, supersedes 00-python-verification-isolation-guard |
| 0b | `candidate-commit-subprocess-env-isolation` | `00b-candidate-commit-subprocess-env-isolation.md` | COMPLETED | runtime guard integrated |
| 0c | `candidate-commit-git-home-isolation` | `00c-candidate-commit-git-home-isolation.md` | SUPERSEDED | subprocess env isolation integrated; retained attempt has no durable Candidate |
| 0d | `candidate-commit-git-home-isolation-recovery` | `00d-candidate-commit-git-home-isolation-recovery.md` | SUPERSEDED | Task 01 integrated (`self-hosted-lifecycle-core-hardening`) supersedes 00d |
| 1 | `tracked-bytecode-cleanup-core` | `01-tracked-bytecode-cleanup-core.md` | BLOCKED | missing exact-authorized-deletion-contract authority |
| 2 | `tracked-bytecode-cleanup-verifier-base` | `02-tracked-bytecode-cleanup-verifier-base.md` | PENDING | core cleanup integrated |
| 3 | `tracked-bytecode-cleanup-concurrency` | `03-tracked-bytecode-cleanup-concurrency.md` | PENDING | verifier-base cleanup integrated |
| 4 | `tracked-bytecode-cleanup-django-tests` | `04-tracked-bytecode-cleanup-django-tests.md` | PENDING | concurrency cleanup integrated |

## Current frontier

None

## Completion condition

The campaign is complete only when:

- the Worker environment forces `PYTHONDONTWRITEBYTECODE=1`;
- Candidate verification fails closed on verifier-created repository mutations;
- all 30 listed tracked `__pycache__/*.pyc` artifacts are absent from `git ls-files`;
- focused tests pass after every batch;
- the canonical Controller remains clean;
- no source, test, receipt, learning ledger, or unrelated generated artifact is deleted.

## Completed cards

- `python-verification-isolation-runtime-guard` (`00a-python-verification-isolation-runtime-guard.md`) - runtime guard candidate integrated at `bf6afeddf921128b061a6bc65f6228650f22627d`.
- `candidate-commit-subprocess-env-isolation` (`00b-candidate-commit-subprocess-env-isolation.md`) - Candidate `ff4c421b32c917fb47894cdaafbd27e0bcab5fcf` integrated at `06e211496e05be3d42a7d079ef6f215977774f95`; subprocess-only MUSE isolation proven, but Git HOME separation remains the current follow-up.

## Blocked or superseded cards

- `python-verification-isolation-guard` (`00-python-verification-isolation-guard.md`): SUPERSEDED by `python-verification-isolation-runtime-guard` (`00a-python-verification-isolation-runtime-guard.md`) after RepositoryContractGate correctly rejected AGENTS.md policy self-modification.
- `candidate-commit-git-home-isolation` (`00c-candidate-commit-git-home-isolation.md`): SUPERSEDED by `candidate-commit-git-home-isolation-recovery` (`00d-candidate-commit-git-home-isolation-recovery.md`) after the verified Target disappeared before Candidate commit; its staged diff hash remains recovery evidence only.
- `candidate-commit-git-home-isolation-recovery` (`00d-candidate-commit-git-home-isolation-recovery.md`): SUPERSEDED by `self-hosted-lifecycle-core-hardening` (Task 01 integrated at `a99c71d8c0628e1d383adaf3a905cad2c6b1b7f4`).
- `tracked-bytecode-cleanup-core`: reason=missing exact-authorized-deletion-contract authority
