# Issue #31 Task Continuity

- campaign_id: github-issue-31-task-continuity-20260813
- issue: #31
- authority: Owner standing grant, bounded Ready Issue
- baseline_main: a74d838cc6bb14af47ce79207181c12a1aed1d35
- reconciled_main: cdf2570ede5ae218f36f886b696c8da45458043a
- status: ACTIVE
- frontier_status: ACCEPTED_CANDIDATE_PENDING_OWNER_MERGE_SLOT
- current_frontier: 01
- terminal_marker: none (physical merge and post-merge readback required)
- AUTO_CHAIN=false
- claim_ceiling: ISSUE_31_REPAIR_CANDIDATE_ACCEPTED_PENDING_OWNER_MERGE_SLOT
- maximum_files: 8
- allowed_files: nexus/core/task_continuity.py, nexus/events/contracts.py, nexus/orchestrator/self_hosted_task_service.py, tests/core/test_task_continuity.py, tests/core/test_event_bus.py, tests/nexus/orchestrator/test_self_hosted_task_service.py, this card, INDEX.md
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_merge: false
- worker_may_push: true (existing PR branch only)

The implementation consumes the existing post-#7 attempt event seam. It adds
no lifecycle, route, workforce, verifier, approval, or merge authority.

Owner KEEP_OPEN repair gate: the prior metadata acceptance is superseded for
this repair. Continuity producer/event/replay fields preserve the exact event
type and protected continuity fields. Independent DeepSeek hostile
re-acceptance passed at governance-bound head
`bec5dff16d5e424231a45ff29e6dbb9c436eb521`; the repair remains non-terminal
until physical merge and post-merge readback.

Prior repair candidate `41351277b0c22a1bf890f0f9cf67e9a683cc2668`
is retained as rejected history. The current semantic repair candidate is
`7e14303927be3235ad05493574a46e975bb759c9` (parent
`ee673dc93a6de9505414f23d498637293b306827`; code and hostile tests only).
Rejected lifecycle state maps/fails closed to `ATTEMPT_REJECTED`, canonical
`failure_reason` persists independently from observation through replay, and
malformed, scalar, or over-limit continuity collections fail closed at the
shared 64-item ceiling. A fresh admitted `gpt-5.6-luna` producer canary created
the current-code artifact with SHA-256
`1af901590d92337db153a679207dd8343efd9a54e2e9974e846c0ebc8709fa2f`; a
separate fresh Luna consumer used only that artifact, selected `strategy-b`,
and did not repeat rejected `strategy-a`. Candidate acceptance is complete;
the Owner merge slot remains pending and no terminal marker is authorized.

Terminal reconciliation records PR #226 head `49cba7ccf36daf39bafa6f5100436eac4103106a`
and merge `a787e8e7` on the reconciled main above. Its exact bounded receipt is
8 files, zero deletions, with 313 focused tests/checks. The G5 cross-agent
continuity finding (#117) remains explicitly excluded; this terminal metadata
does not assert runtime, route, Workforce, provider, approval, integration,
merge, release, or production truth.
