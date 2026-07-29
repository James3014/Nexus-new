# Candidate Commit Git HOME Isolation

**artifact_authority:** current
**owner:** James Chen
**status:** PENDING
**task_id:** `candidate-commit-git-home-isolation`
**AUTO_CHAIN:** false
**controller_base_revision:** `06e211496e05be3d42a7d079ef6f215977774f95`
**depends_on:** `candidate-commit-subprocess-env-isolation` integrated
**commit_required:** true
**candidate_required:** true
**worker_may_commit:** true
**worker_may_approve:** false
**worker_may_integrate:** false
**worker_may_push:** false

## Objective

Keep AGY provider credentials isolated under the AGY runtime `HOME` while giving the scoped Git commit subprocess a deterministic host Git HOME. This prevents Git from losing the user-level `core.hooksPath` and falling back to the repository-local mandatory full-corpus Drift Audit hook.

## Root cause

The self-hosted AGY Worker runs with `HOME=/Users/jameschen/.nexus/agy-account-pool/live-home`. The Candidate commit subprocess inherited that HOME, so Git could not read the host account's `.gitconfig` and ignored its safe global hooks path. Git then used `/Users/jameschen/Workspace/nexus/.git/hooks/pre-commit`, which always ran an unrelated full Wiki Drift Audit and generated `DRIFT_AUDIT_REPORT.md` despite the Task Card verifiers already passing.

## Required behavior

- `CandidateCommitter` constructs a Git-only environment without mutating `os.environ`.
- The Git-only environment keeps `MUSE_RUN_CODEX_LOOP=0`.
- Git HOME resolution order is:
  1. a non-empty explicit `NEXUS_GIT_HOME`;
  2. the operating-system account home resolved independently of the current `HOME` environment on POSIX;
  3. fail closed if no safe Git HOME can be resolved.
- Only the scoped `git commit` subprocess receives the Git HOME override. AGY execution, account credentials, model process, verifier commands, and the outer Worker retain the isolated AGY HOME.
- The resolved Git HOME must be an absolute existing directory.
- No account email, credential path, token, or raw account identity enters receipts or logs.
- Tests prove that an isolated outer HOME lacking `.gitconfig` does not cause repository-local hook fallback: the commit reads a test host-home `.gitconfig`, uses the configured hooks path, the hook observes `MUSE_RUN_CODEX_LOOP=0`, and the outer HOME remains unchanged.
- Tests prove explicit `NEXUS_GIT_HOME` precedence, invalid explicit paths fail closed, and process-global HOME/MUSE values never change.

## Allowed files

- `nexus/orchestrator/candidate_commit.py`
- `tests/nexus/orchestrator/test_candidate_commit.py`

## Forbidden scope

- No modification to `AGENTS.md` or global Git configuration.
- No modification to AGY account-manager state or credentials.
- No deletion of tracked bytecode.
- No `--no-verify` and no blanket hook bypass.
- No change to route, approval, integration, or claim authority.

## Verification commands

```bash
python3 -m pytest -q tests/nexus/orchestrator/test_candidate_commit.py tests/nexus/orchestrator/test_worktree_manager.py tests/nexus/orchestrator/test_self_hosted_controller.py
git diff --check
```

## Evidence and exit criteria

- Git commit succeeds when outer `HOME` is an AGY runtime home and host Git HOME supplies the safe hooks path.
- The outer `HOME` and `MUSE_RUN_CODEX_LOOP` values are unchanged before and after Candidate formation.
- Repository-local mandatory Drift Audit is not selected solely because AGY changed HOME.
- All exact verifiers pass, Candidate is protected, and independent approval remains required.

Allowed claim: `CANDIDATE_COMMIT_GIT_HOME_ISOLATION_CANDIDATE_READY`.

Must remain false: `TRACKED_BYTECODE_REMOVED`, `AGY_ACCOUNT_POOL_RUNTIME_COMPLETE`, `PRODUCTION_READY`, `PUBLIC_CLAIM_ALLOWED`.
