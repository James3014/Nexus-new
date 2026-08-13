# Issue #31 Task Continuity

- campaign_id: github-issue-31-task-continuity-20260813
- issue: #31
- authority: Owner standing grant, bounded Ready Issue
- baseline_main: a74d838cc6bb14af47ce79207181c12a1aed1d35
- reconciled_main: eb668fb76f0c30d8f025db42cdb8e320d556c037
- status: COMPLETE
- frontier_status: TERMINAL
- current_frontier: none
- terminal_marker: CANONICAL_TASK_CONTINUITY_CONTRACT_VERIFIED_SOURCE_AND_HOSTILE_TESTS_ONLY
- AUTO_CHAIN=false
- claim_ceiling: ISSUE_31_TERMINAL_METADATA_ACCEPTED_SOURCE_AND_HOSTILE_TESTS_ONLY
- maximum_files: 8
- allowed_files: nexus/core/task_continuity.py, nexus/events/contracts.py, nexus/orchestrator/self_hosted_task_service.py, tests/core/test_task_continuity.py, tests/core/test_event_bus.py, tests/nexus/orchestrator/test_self_hosted_task_service.py, this card, INDEX.md
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_merge: false
- worker_may_push: true (existing PR branch only)

The implementation consumes the existing post-#7 attempt event seam. It adds
no lifecycle, route, workforce, verifier, approval, or merge authority.

Terminal reconciliation records PR #226 head `49cba7ccf36daf39bafa6f5100436eac4103106a`
and merge `a787e8e7` on the reconciled main above. Its exact bounded receipt is
8 files, zero deletions, with 313 focused tests/checks. The G5 cross-agent
continuity finding (#117) remains explicitly excluded; this terminal metadata
does not assert runtime, route, Workforce, provider, approval, integration,
merge, release, or production truth.
