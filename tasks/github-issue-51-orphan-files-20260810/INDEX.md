---
artifact_authority: current
owner: James Chen
status: active
campaign_id: github-issue-51-orphan-files-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/51
baseline_main: bdcc427f6249406079c85f9725b3af6cd62ab1f1
ordered_cards:
  - 01-delete-proven-orphans.md
current_frontier: 01-delete-proven-orphans.md
completed_cards: []
blocked_cards: []
AUTO_CHAIN: false
---

# Issue 51 Proven Orphan Deletion

Delete only the thirteen exact orphan paths admitted by the fresh Issue #51
reconciliation, remove the one stale Wiki inventory row for the duplicate root
transaction module, and preserve `legacy/logmemory.py` byte-for-byte.

Prerequisite chain `#75 -> #104 -> #105 -> #106` is physically complete.
The candidate must rebind existing PR #71 to this exact current-main baseline,
pass fresh exact-head protected evidence, then use #106 CAS/post-apply controls.

Claim ceiling: `ISSUE_51_ORPHAN_CLEANUP_CANDIDATE`.
