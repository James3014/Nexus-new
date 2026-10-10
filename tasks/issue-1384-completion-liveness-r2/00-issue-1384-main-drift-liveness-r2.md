# Task Card: issue-1384-main-drift-liveness-r2

artifact_authority: current
task_id: `issue-1384-main-drift-liveness-r2`
owner: James Chen
status: ACTIVE
execution_lane: GOVERNED
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Complete Issue #1384 on current main without weakening governance: independently verify the already-merged completion-liveness implementation, reproduce and resolve the stable-main repeated BASE_MOVED same-generation retry edge if it is a real contract defect, preserve relative integration-generation budgeting default=5 and hard ceiling=5 plus all fail-closed boundaries, and prepare the exact subject/evidence needed for the mandatory live high-concurrency criterion 11. Worker may modify only the completion-loop source and focused test if the defect is confirmed; otherwise return a no-op Candidate-ready result with proof. No direct merge, push, release, task-card authority rewrite, or downgrade from GOVERNED.

## Allowed files

- `nexus/orchestrator/github_completion_loop.py`
- `tests/nexus/orchestrator/test_github_completion_loop.py`

## Verification commands

```bash
uv run --frozen --group trusted-anchor pytest -q tests/nexus/orchestrator/test_github_completion_loop.py
uv run --frozen ruff check nexus/orchestrator/github_completion_loop.py tests/nexus/orchestrator/test_github_completion_loop.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
