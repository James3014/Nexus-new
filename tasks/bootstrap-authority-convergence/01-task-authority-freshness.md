# Task Card 01: Task Authority Freshness

## Identity

- task_id: `task-authority-freshness`
- campaign_id: `bootstrap-authority-convergence`
- artifact_authority: current
- status: READY
- owner: James Chen
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Add a read-only, machine-readable validator that proves a Git-tracked campaign INDEX and its Task Cards are fresh relative to the current worktree HEAD. It must detect stale current-frontier claims, missing or malformed card references, missing integration commits, integration commits that are not ancestors of HEAD, and lifecycle task-card hash mismatches when state is available.

## Allowed files

- `scripts/ops/task_authority_freshness_check.py`
- `tests/ops/test_task_authority_freshness_check.py`
- `tasks/bootstrap-authority-convergence/INDEX.md`
- `tasks/bootstrap-authority-convergence/01-task-authority-freshness.md`

## Forbidden scope

No canonical-root mutation; no changes to AGENTS/MUSE/GEMINI/CLAUDE/MEMORY/SOUL/Cursor bootstrap files; no startup checker wiring; no protocol contract; no workforce, provider, route, Candidate, approval, integration, push, branch/ref deletion, or receipt mutation.

## Required behavior

1. Default root is the current Git worktree; `--repo-root` permits an explicit worktree for tests and automation.
2. `--index` identifies a Git-tracked campaign INDEX; relative paths resolve under the repo root.
3. Output is JSON on stdout and does not create `.nexus` or lock files.
4. Report worktree root, branch, HEAD, dirty state, index path, index commit, current frontier, completed entries, blocked entries, findings, and a `decision` of `PASS`, `WARN`, or `BLOCK`.
5. A completed entry must contain a 7–40 character lowercase hexadecimal commit and that commit must exist and be an ancestor of HEAD.
6. A current frontier that names a completed task is a blocking stale claim. A named frontier absent from ordered cards is allowed only when it is explicitly listed in Blocked Cards or is a documented readiness gate.
7. Ordered card links must resolve; each card must expose a matching `task_id` and status.
8. If `--state-dir` is supplied, compare nonterminal lifecycle `task_card_path` and `task_card_hash` against the current card; mismatches block. Retained/terminal historical mismatches are reported as warnings.

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/ops/test_task_authority_freshness_check.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/ops/task_authority_freshness_check.py --repo-root . --index tasks/bootstrap-authority-convergence/INDEX.md
PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q scripts/ops/task_authority_freshness_check.py
git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
git diff --stat
git diff --cached --stat
```

## Evidence required

- Unit tests cover fresh pass, stale frontier block, missing card block, non-ancestor commit block, malformed commit block, lifecycle hash mismatch block, and historical retained mismatch warning.
- Live invocation against this campaign returns machine-readable evidence and does not create a lock/report artifact.
- No tracked deletions and only allowed files are committed.

## Exit criteria

`task_authority_freshness_check.py` has a scoped commit, all required tests pass, and the live campaign invocation returns a truthful decision for the current HEAD.

## Residual debt

P0-B bootstrap path cleanup, P0-C machine policy contract, P0-D startup integration, workforce compact query, and briefing overlays remain separate cards. P6 canonical-root cutover remains owner-controlled.

## Block classification

- `RECOVERABLE_BLOCK`: test/runtime dependency failure with files preserved.
- `HARD_BLOCK`: authority conflict, unsafe root mutation, or inability to prove the current INDEX/Card state.
