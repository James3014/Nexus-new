# Candidate Commit Subprocess Env Isolation

**artifact_authority:** current
**owner:** James Chen
**status:** COMPLETED
**task_id:** `candidate-commit-subprocess-env-isolation`
**AUTO_CHAIN:** false
**controller_base_revision:** `bf6afeddf921128b061a6bc65f6228650f22627d`
**depends_on:** `python-verification-isolation-runtime-guard` integrated
**commit_required:** true
**candidate_required:** true
**worker_may_commit:** true
**worker_may_approve:** false
**worker_may_integrate:** false
**worker_may_push:** false

## Objective

Replace CandidateCommitter process-global environment mutation (`MUSE_RUN_CODEX_LOOP`) with subprocess-specific Git environment isolation in `_run_git`.

## Required behavior

- `WorktreeManager._run_git` accepts an optional `env` mapping parameter passed directly to `subprocess.run`.
- Existing callers of `_run_git` without `env` argument retain standard process environment inheritance behavior.
- `CandidateCommitter.create_candidate_commit` creates `commit_env` from `os.environ`, sets `MUSE_RUN_CODEX_LOOP=0` in that dict, and passes `env=commit_env` to `_run_git`.
- `CandidateCommitter` never mutates `os.environ`.
- Unit tests verify subprocess hook receives `0` when outer process has `1`, outer process remains `1`, absent outer variable remains absent, concurrent thread never observes temporary global mutation, and `WorktreeManager` default calls are unchanged.

## Allowed files

- `tasks/python-verification-isolation/INDEX.md`
- `tasks/python-verification-isolation/00b-candidate-commit-subprocess-env-isolation.md`
- `tasks/python-verification-isolation/01-tracked-bytecode-cleanup-core.md`
- `nexus/orchestrator/worktree_manager.py`
- `nexus/orchestrator/candidate_commit.py`
- `tests/nexus/orchestrator/test_worktree_manager.py`
- `tests/nexus/orchestrator/test_candidate_commit.py`

## Forbidden scope

- No modification to `AGENTS.md`.
- No deletion of tracked bytecode.
- No process-global `os.environ` mutation during candidate commit.

## Verification commands

```bash
python3 -m pytest -q tests/nexus/orchestrator/test_candidate_commit.py tests/nexus/orchestrator/test_worktree_manager.py tests/nexus/orchestrator/test_self_hosted_controller.py
git diff --check
```

## Evidence and exit criteria

- `_run_git` accepts optional `env` argument.
- `CandidateCommitter` uses subprocess `env` without touching `os.environ`.
- Unit tests pass proving subprocess isolation and thread safety against environment leakage.
- All verification commands pass.

## Completion evidence

- Candidate: `ff4c421b32c917fb47894cdaafbd27e0bcab5fcf`
- Integrated Controller: `06e211496e05be3d42a7d079ef6f215977774f95`
- Independent verification: 43 focused tests passed with no working-tree mutation.
- Residual follow-up: AGY account isolation changes `HOME`, so governed Git commits require a separate Git HOME selection contract before cleanup tasks may start.
