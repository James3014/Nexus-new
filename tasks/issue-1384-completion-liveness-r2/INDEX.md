# Campaign Index: issue-1384-completion-liveness-r2

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Complete Issue #1384 on current main without weakening governance: independently verify the already-merged completion-liveness implementation, reproduce and resolve the stable-main repeated BASE_MOVED same-generation retry edge if it is a real contract defect, preserve relative integration-generation budgeting default=5 and hard ceiling=5 plus all fail-closed boundaries, and prepare the exact subject/evidence needed for the mandatory live high-concurrency criterion 11. Worker may modify only the completion-loop source and focused test if the defect is confirmed; otherwise return a no-op Candidate-ready result with proof. No direct merge, push, release, task-card authority rewrite, or downgrade from GOVERNED.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `issue-1384-main-drift-liveness-r2` | `00-issue-1384-main-drift-liveness-r2.md` | ACTIVE | Owner confirmation |
