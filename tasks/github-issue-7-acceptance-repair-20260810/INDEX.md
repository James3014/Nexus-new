---
artifact_authority: current
owner: James Chen
status: active
campaign_id: github-issue-7-acceptance-repair-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/7
baseline_main: 599227f0efbe1e9a4ca8cd6bff56824f0a6d9965
reconciled_main: 70fd467ab0d29f4373616a5e98d85b014efcd4de
rebind_owner_directive: https://github.com/James3014/Nexus-new/issues/7#issuecomment-5250252765
rebind_date: 2026-08-11
ordered_cards:
  - 01-canonical-planner-dispatch-binding.md
  - 02-independent-candidate-acceptance.md
  - 03-bounded-repair-attempts.md
  - 04-ordered-attempt-events-and-e2e.md
current_frontier: 02-independent-candidate-acceptance.md
frontier_status: BLOCKED_OWNER_GATE
completed_cards:
  - 01-canonical-planner-dispatch-binding.md
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

## Reconciliation (2026-08-11)

Owner directive comment 5250252765 authorizes this governance-only campaign
rebind on branch `codex/issue-7-m3-campaign-rebind`.

M3-A completed on main via PR #81: head
`c68379ea98e090c22847669fbefc50ada6335157`, merged as
`41e5ee06eeecb4abd7df7c15c36af13142a1da56` on 2026-08-11.

Current frontier M3-B (`02-independent-candidate-acceptance.md`) is
`BLOCKED_OWNER_GATE`: implementation starts only after the Owner approves the
M3-B autonomy-conditional acceptance receipt/approval gate
(`M3_B_CAMPAIGN_REBIND_AND_OWNER_GATE`). The block is carried by
`frontier_status`, so M3-B is not moved into `blocked_cards`.

`AUTO_CHAIN=false`; all worker mutation/commit/push/approval/integration
permissions remain false.
