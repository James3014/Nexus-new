---
artifact_authority: current
owner: James Chen
status: active
campaign_id: github-issue-7-acceptance-repair-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/7
baseline_main: 599227f0efbe1e9a4ca8cd6bff56824f0a6d9965
ordered_cards:
  - 01-canonical-planner-dispatch-binding.md
  - 02-independent-candidate-acceptance.md
  - 03-bounded-repair-attempts.md
  - 04-ordered-attempt-events-and-e2e.md
current_frontier: 01-canonical-planner-dispatch-binding.md
frontier_status: ACTIVE
completed_cards: []
blocked_cards: []
AUTO_CHAIN: false
---

# GitHub Issue 7 M3 Acceptance and Bounded Repair

Post-#6/#16 reconciliation split M3 into four sequential authority slices.
Each slice must commit only its allowed files, receive independent exact-commit
review, and preserve Candidate, approval, integration, merge, and public-claim
separation.

Issue #29 overlap is forbidden throughout this campaign: do not modify
`nexus/services/unified_runtime.py`, `nexus/services/online_nexus_context.py`,
`nexus/services/local_assist_service.py`,
`nexus/services/verified_assist_contract.py`, or Issue #29 tests/tasks.

M3 emits only auditable structured task/attempt events. Canonical compaction,
resume loading, cross-agent rehydration, hidden chain-of-thought, and #31
continuity metrics are outside this campaign.

Current M3-A card SHA-256:
`71e0835991583469e60d212b618398bbf73dceb6f3b8cc695c3e595855bfa8d4`.
