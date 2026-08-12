---
artifact_authority: current
owner: James Chen
status: active
campaign_id: github-issue-153-event-feedback-impact-map-20260811
source_issue: https://github.com/James3014/Nexus-new/issues/153
baseline_main: 9dddd018ad2761face3d2f3ce29dff8d8feae72d
implementation_commit: 4ffbd1fa7e4b88c932615daf3dfa3dec9e8ecd7b
rebind_lineage_commit: 88a6c616fdf145738e582aa625c94abbf90daf66
current_frontier: 01-event-feedback-impact-map.md
frontier_status: ACTIVE
AUTO_CHAIN: false
ordered_cards:
  - 01-event-feedback-impact-map.md
completed_cards: []
blocked_cards: []
---

# GitHub Issue 153 — event and feedback impact mapping

This card governs the bounded selector impact-map addition that unblocks PR
#151's exact-base impact selection. It does not modify PR #151 or selector
implementation semantics.

The final exact PR head is bound externally by the PR, protected checks, and
merge receipt; this card does not recursively claim a mutable candidate head.
