# Issue #31 Task Continuity

- campaign_id: github-issue-31-task-continuity-20260813
- issue: #31
- authority: Owner standing grant, bounded Ready Issue
- baseline_main: a74d838cc6bb14af47ce79207181c12a1aed1d35
- reconciled_main: cdf2570ede5ae218f36f886b696c8da45458043a
- status: ACTIVE
- frontier_status: IMPLEMENTATION_ACTIVE
- current_frontier: 01
- terminal_marker: none (repair required)
- AUTO_CHAIN=false
- claim_ceiling: ISSUE_31_REPAIR_CANDIDATE_ONLY_PENDING_OWNER_KEEP_OPEN_GATE
- maximum_files: 8
- allowed_files: nexus/core/task_continuity.py, nexus/events/contracts.py, nexus/orchestrator/self_hosted_task_service.py, tests/core/test_task_continuity.py, tests/core/test_event_bus.py, tests/nexus/orchestrator/test_self_hosted_task_service.py, this card, INDEX.md
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_merge: false
- worker_may_push: true (existing PR branch only)

The implementation consumes the existing post-#7 attempt event seam. It adds
no lifecycle, route, workforce, verifier, approval, or merge authority.

Owner KEEP_OPEN repair gate: the prior metadata acceptance is superseded for
this repair. Continuity producer/event/replay fields must preserve the exact
event type and protected continuity fields; no VERIFIED or terminal claim is
authorized until independent re-acceptance of this bounded repair.

Repair candidate head: `41351277b0c22a1bf890f0f9cf67e9a683cc2668` (code and
hostile tests only). Rejected lifecycle state maps/fails closed to
`ATTEMPT_REJECTED`, canonical `failure_reason` persists through replay, and
malformed continuity lists fail closed. KEEP_OPEN remains active; acceptance
is external and pending; no terminal marker is authorized.

Terminal reconciliation records PR #226 head `49cba7ccf36daf39bafa6f5100436eac4103106a`
and merge `a787e8e7` on the reconciled main above. Its exact bounded receipt is
8 files, zero deletions, with 313 focused tests/checks. The G5 cross-agent
continuity finding (#117) remains explicitly excluded; this terminal metadata
does not assert runtime, route, Workforce, provider, approval, integration,
merge, release, or production truth.
