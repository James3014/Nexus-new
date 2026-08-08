# Task Card: WORKTREE-DISPOSITION-HARDENING-01

artifact_authority: current
task_id: `WORKTREE-DISPOSITION-HARDENING-01`
owner: James Chen
status: ACTIVE
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Harden existing `WorktreeManager` and Direct completion semantics so registered
worktrees are judged by physical risk rather than by count. Clean, inactive,
reachable, redundant worktrees must not block Direct completion merely because
they are registered. Dirty, active, locked, durable-owned, overlapping, current
review, or uniquely unprotected worktrees remain fail-closed.

Expose a deterministic disposition receipt with enough evidence to decide:

- `RELEASABLE_REDUNDANT_CLEAN`
- `ACTIVE_RETAIN`
- `FORENSIC_RETAIN`
- `OWNER_DECISION_REQUIRED`
- `BLOCKED_UNPROTECTED_UNIQUE_COMMIT`

No cleanup occurs in this implementation Candidate.

## Baseline and dependencies

- Canonical baseline at authority creation:
  `230f7c4ed9c48f7431dba9d50d41f22e0c3f5e5b`.
- Re-anchor to fresh canonical before implementation.
- Do not overlap the externally owned `DEEPSEEK-WORKER-READINESS-FIX-01`
  Candidate; if its changes touch an allowed file, base this Candidate after
  that exact integration or stop with `RECOVERABLE_BLOCK`.

## Allowed files

- `nexus/orchestrator/worktree_manager.py`
- `nexus/orchestrator/self_hosted_task_service.py` only for the existing Direct
  completion gate and receipt projection
- `tests/nexus/orchestrator/test_worktree_manager.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py` only for Direct
  completion/disposition tests

## Required controls

- inventory records path, HEAD, branch/detached state, dirty/untracked state,
  canonical reachability, unique commits, branch/ref protection, lifecycle
  ownership, active process/lock evidence, and current-review status;
- the same frozen inventory produces the same plan hash;
- Direct completion permits additional registered worktrees only when every
  non-canonical entry is proven clean, inactive, unlocked, non-overlapping,
  redundant/reachable, and not durable-owned/current-review;
- dirty, unknown, active, locked, overlapping, or unique-unprotected entries
  block with typed evidence;
- no worktree removal, prune, ref deletion, reset, stash, or cleanup is invoked;
- existing OPENWIKI worktrees remain untouched and classify conservatively.

## RED -> GREEN

1. RED: clean redundant registered worktree blocks Direct completion solely by
   count. GREEN: it passes evidence-based disposition.
2. RED: process/lock/ref/reachability/unique-commit evidence is absent or
   ignored. GREEN: every signal is surfaced and gates deterministically.
3. Dirty/untracked, durable-owned, current-review, overlapping, or unique
   unprotected worktrees remain blocked with zero cleanup.
4. Inventory/plan ordering and SHA-256 are deterministic.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/nexus/orchestrator/test_worktree_manager.py \
  tests/nexus/orchestrator/test_self_hosted_task_service.py
git diff --check
git diff --name-status
git diff --stat
git diff --cached --name-status
git diff --cached --stat
```

## Forbidden scope

No Gateway/MCP, durable/OAuth, route/planner/workforce, provider, OpenWiki,
lifecycle JSON, actual cleanup, ref deletion, integration, push, or production
claim. Do not modify another agent's Target.

## Exit criteria

One clean scoped Candidate commit, exact tests green, no deletions, deterministic
receipt evidence, and independent review. Worker stops before cleanup,
approval, integration, or push.

## Block classification

- `RECOVERABLE_BLOCK`: active overlapping Candidate or test/environment issue.
- `HARD_BLOCK`: destructive ambiguity, unique unprotected data requiring
  deletion, authority expansion, or need to touch another task's Target.
