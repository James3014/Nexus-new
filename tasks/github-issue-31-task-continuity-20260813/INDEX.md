# Issue #31 Task Continuity

- campaign_id: github-issue-31-task-continuity-20260813
- issue: #31
- authority: Owner standing grant, bounded Ready Issue
- baseline_main: a74d838cc6bb14af47ce79207181c12a1aed1d35
- status: active
- current_frontier: 01-task-continuity.md
- AUTO_CHAIN=false
- maximum_files: 8
- allowed_files: nexus/core/task_continuity.py, nexus/events/contracts.py, nexus/orchestrator/self_hosted_task_service.py, tests/core/test_task_continuity.py, tests/core/test_event_bus.py, tests/nexus/orchestrator/test_self_hosted_task_service.py, this card, INDEX.md
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_merge: false
- worker_may_push: true (existing PR branch only)

The implementation consumes the existing post-#7 attempt event seam. It adds
no lifecycle, route, workforce, verifier, approval, or merge authority.
