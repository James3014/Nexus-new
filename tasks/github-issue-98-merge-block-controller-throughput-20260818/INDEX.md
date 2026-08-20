---
artifact_authority: current
owner: James Chen
status: active
source_issue: "#98"
baseline_main: f9899121c6b691fd7a66a391a2055a2c78bd387b
rebound_from_main: f9899121c6b691fd7a66a391a2055a2c78bd387b
rebind_head_before_edits: cd4056039915a2517d20815e4003920f021aaf07
historical_rebound_from_main: 8c2584d6053dd1f04dc87333f807fbea1726545e
current_frontier: 00-merge-block-controller-throughput.md
claim_ceiling: SOURCE_CANDIDATE_ONLY
AUTO_CHAIN: false
---

# Issue #98 P0 merge-block controller throughput

This campaign repairs the existing self-hosted Target admission authority so a
Candidate waiting at the merge/integration boundary does not hold a global
execution lock over independent, disjoint isolated work.

The campaign extends the current task/lease and WorktreeManager authorities with
ownership-authority unification:
- Admission and physical cleanup share the same reservation lock;
- Exact ownership records are safely read/validated before removal;
- Records are deleted only after verified registered worktree cleanup;
- Direct service admission consumes physical WorktreeManager decisions and
  caller lifecycle status never releases physical ownership.

The campaign operates on an exact six-file scope:
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/worktree_manager.py`
- `tasks/github-issue-98-merge-block-controller-throughput-20260818/00-merge-block-controller-throughput.md`
- `tasks/github-issue-98-merge-block-controller-throughput-20260818/INDEX.md`
- `tests/nexus/orchestrator/test_merge_block_controller_throughput.py`
- `tests/nexus/orchestrator/test_worktree_manager.py`

It does not add another scheduler, Router, Planner, lifecycle, Candidate,
integration, or merge authority. Post-merge physical E2E remains required.
