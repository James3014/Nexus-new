---
artifact_authority: current
owner: James Chen
status: active
campaign_id: github-issue-7-acceptance-repair-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/7
baseline_main: 599227f0efbe1e9a4ca8cd6bff56824f0a6d9965
reconciled_main: 89ed130ac5d3ad58106e7d9ba8f0d3a65066fdc2
current_main: 069596056fff852bad8c826725902d25361aa9c7
rebind_owner_directive: https://github.com/James3014/Nexus-new/issues/7#issuecomment-5250252765
rebind_date: 2026-08-11
ordered_cards:
  - 01-canonical-planner-dispatch-binding.md
  - 02-independent-candidate-acceptance.md
  - 03-bounded-repair-attempts.md
  - 04-ordered-attempt-events-and-e2e.md
current_frontier: 04-ordered-attempt-events-and-e2e.md
frontier_status: ACTIVE
completed_cards:
  - 01-canonical-planner-dispatch-binding.md
  - 02-independent-candidate-acceptance.md
  - 03-bounded-repair-attempts.md
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

M3-B (`02-independent-candidate-acceptance.md`) completed via PR #161. Its
exact Candidate head was `d2a3bfa8b6ed3fd28015565680a84cdf7c826768`, physically
merged as `9121cd2cf83e959db763bbb578a60f861b0855fb`; independent review was
`MERGE_SAFE`, with 255 combined tests and 14 reducer tests. Protected required
checks were terminal PASS; Tier 3 remained skipped.

M3-C (`03-bounded-repair-attempts.md`) was completed via PR #188. Its exact
Candidate head was `0bfb31ebc4dc5862581fe6cf289dea43c8942302`, physically
merged as `892369a93a5c540042f0b4b35d1ee8d81a9de2b2`; the seven-file scope
received independent `ACCEPT`, required checks were terminal PASS, and focused
evidence included 297 combined tests, eight M3-C tests, and 311 primary tests.

The current frontier is M3-D (`04-ordered-attempt-events-and-e2e.md`) with
`ACTIVE` status. On 2026-08-13 the Owner explicitly granted M3-D activation,
bounded implementation, commit, issue-branch push, and pull-request creation
against current main `069596056fff852bad8c826725902d25361aa9c7`. The M3-D
frontier is amended to include the persisted event-log hardening contract in
`nexus/events/log_store.py` and hostile acceptance coverage; this does not
activate #31, #65, #191, or #143.

`AUTO_CHAIN=false`. Approval, integration, merge, release, and production/public
claims remain separate authorities.
