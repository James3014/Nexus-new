# Task Card: issue-982-target-admission-bare-common-dir-repair-20260920

artifact_authority: current
task_id: `issue-982-target-admission-bare-common-dir-repair-20260920`
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

Repair the target-admission reservation lock so a controller checkout whose `git rev-parse --git-common-dir` resolves to a valid bare/common Git directory such as `repository.git` is accepted. Remove the basename==`.git` assumption while preserving fail-closed controller toplevel identity, existence/directory validation, Git-owned common-dir provenance, flock serialization, and all existing target/lease boundaries. Add regression tests that reproduce the gateway-direct deployment shape and negative controls for invalid/non-directory common-dir evidence. No route, Workforce, Task Card, provider, merge, release, or canary semantics change.

## Allowed files

- `nexus/orchestrator/worktree_manager.py`
- `tests/nexus/orchestrator/test_worktree_manager.py`

## Verification commands

```bash
python -m pytest tests/nexus/orchestrator/test_worktree_manager.py
python -m py_compile nexus/orchestrator/worktree_manager.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
