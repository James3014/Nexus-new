# Issue #98 — deployment bare common-dir admission repair

```yaml
task_id: github-issue-98-admission-lock
attempt_id: github-issue-98-admission-lock-r1
campaign_id: github-issue-98-merge-block-controller-throughput-20260818
issue: 98
repository: James3014/Nexus-new
status: READY
contract_kind: TRACKED_TASK_CARD
execution_lane: GOVERNED
auto_chain: false
worker_may_commit: true
worker_may_push: false
worker_may_approve: false
worker_may_integrate: false
claim_ceiling: SOURCE_CANDIDATE_ONLY
```

## Goal

Repair the existing Issue #98 Target admission-lock implementation so Git linked worktrees
whose Git-resolved common directory is a structurally valid bare repository such as
`repository.git` use the same shared reservation lock as ordinary `.git` worktrees.

## Exact defect

`WorktreeManager._reservation_lock()` currently accepts the Git-resolved common directory
only when its basename is literally `.git`. Gateway deployment worktrees use a valid bare
common repository named `repository.git`, so admission fails with
`TARGET_ADMISSION_LOCK_UNRESOLVED` before any reservation lock is acquired.

## Required behavior

- Resolve repository/common-dir identity through Git as before.
- Accept a common directory only when it is a directory with Git structural markers
  `HEAD` (regular file) and `objects/` (directory).
- Preserve the existing `nexus-target-admission.lock` location under the exact common-dir.
- Preserve flock acquisition/release, ownership records, overlap policy, target identity,
  cleanup authority and serial-budget semantics.
- Ordinary linked worktrees using `.git` must remain compatible.
- Arbitrary or structurally invalid common directories must still fail closed.

## Allowed files

- `nexus/orchestrator/worktree_manager.py`
- `tests/nexus/orchestrator/test_merge_block_controller_throughput.py`

No deletions. No other source, test, workflow, Task Card, runtime, or deployment mutation is
part of this Candidate.

## Verification

- `uv run pytest -q tests/nexus/orchestrator/test_merge_block_controller_throughput.py`
- `uv run pytest -q tests/nexus/orchestrator/test_worktree_manager.py`
- `uv run ruff check nexus/orchestrator/worktree_manager.py tests/nexus/orchestrator/test_merge_block_controller_throughput.py`
- `git diff --check`

## Acceptance

A fresh independent reviewer must inspect the exact Candidate. Source acceptance does not
grant merge, runtime, release, production, or #973 runtime-recovery authority.

`AUTO_CHAIN=false`.
