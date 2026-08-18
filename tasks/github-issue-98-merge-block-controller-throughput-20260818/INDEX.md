---
artifact_authority: current
owner: James Chen
status: active
source_issue: "#98"
baseline_main: 1ee1c69332514bdbaa5a98f5ed29fad109425c32
current_frontier: 00-merge-block-controller-throughput.md
AUTO_CHAIN: false
---

# Issue #98 P0 merge-block controller throughput

This campaign repairs the existing self-hosted Target admission authority so a
Candidate waiting at the merge/integration boundary does not hold a global
execution lock over independent, disjoint isolated work.

The campaign extends the current task/lease and WorktreeManager authorities. It
does not add another scheduler, Router, Planner, lifecycle, Candidate,
integration, or merge authority.
