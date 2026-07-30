# Candidate Commit Git HOME Isolation Recovery

**artifact_authority:** current
**owner:** James Chen
**status:** PENDING
**task_id:** `candidate-commit-git-home-isolation-recovery`
**AUTO_CHAIN:** false
**depends_on:** `candidate-commit-git-home-isolation` retained attempt is inspect-only evidence
**commit_required:** true
**candidate_required:** true
**worker_may_commit:** true
**worker_may_approve:** false
**worker_may_integrate:** false
**worker_may_push:** false

## Objective

Reimplement the Git-only HOME isolation contract from 00c in a fresh Target and produce a governed Candidate. The retained 00c staged diff SHA is recovery evidence only; do not copy from the legacy dirty checkout or mutate the Controller during worker execution.

## Allowed files

- `nexus/orchestrator/candidate_commit.py`
- `tests/nexus/orchestrator/test_candidate_commit.py`

## Forbidden scope

- `AGENTS.md`, `MUSE_PROTO.md`, campaign authority outside this card
- `nexus/services/agy_account_pool.py`
- `nexus/executors/worker_registry.py`
- global or repository Git configuration and hooks
- `--no-verify`, tracked deletion, reset, rebase, push, protected-main merge
- legacy dirty checkout `/Users/jameschen/Workspace/nexus`

## Required behavior

- CandidateCommitter sends a deterministic Git HOME only to the scoped commit subprocess.
- Resolution order: non-empty `NEXUS_GIT_HOME`, POSIX OS-account home resolved independently of current HOME, otherwise fail closed.
- AGY credential HOME, outer HOME, and Git HOME remain distinct.
- `MUSE_RUN_CODEX_LOOP=0` is scoped to the commit subprocess.
- No process-global environment mutation.

## Verification commands

- `/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_AUTHOR_NAME=Nexus\\ Test GIT_AUTHOR_EMAIL=nexus-test@localhost GIT_COMMITTER_NAME=Nexus\\ Test GIT_COMMITTER_EMAIL=nexus-test@localhost PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_candidate_commit.py tests/nexus/orchestrator/test_worktree_manager.py tests/nexus/orchestrator/test_self_hosted_controller.py`
- `git diff --check`

## Evidence and exit criteria

- Fresh Target only; Controller unchanged.
- Exact two-file scope, no deletions, no weakened assertions.
- Candidate commit, durable Candidate ref, verified receipt hash, and promotion packet exist.
- Target cleanup is performed only after Candidate protection.
- Allowed claim: `CANDIDATE_COMMIT_GIT_HOME_ISOLATION_CANDIDATE_READY`.
- Must remain false: `AGY_ACCOUNT_POOL_RUNTIME_COMPLETE`, `PRODUCTION_READY`, `PUBLIC_CLAIM_ALLOWED`.

## Block classification

Missing safe Git HOME, credential boundary, candidate binding, or lifecycle evidence is `RECOVERABLE_BLOCK`; authority contradiction or unsafe secret exposure is `HARD_BLOCK`.
