---
task_id: 00-agy-account-pool-runtime-integration
campaign_id: agy-account-pool-runtime
authority: current
status: COMPLETED
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
allowed_files:
  - nexus/services/agy_account_pool.py
  - nexus/executors/worker_registry.py
  - nexus/executors/worker_contract.py
  - tests/services/test_agy_account_pool.py
  - tests/nexus/executors/test_worker_contract.py
  - tests/nexus/orchestrator/test_self_hosted_task_service.py
  - tasks/agy-account-pool-runtime/INDEX.md
  - tasks/agy-account-pool-runtime/00-agy-account-pool-runtime-integration.md
forbidden_scope:
  - nexus/orchestrator/unified_runtime.py
  - /private/tmp/nexus-agy-governance-targets/agy-account-pool-runtime-integration-a1
---

# Task Card: Governed AGY Account-Pool Runtime Integration

## Objective
Implement governed AGY account-pool integration directly into `AgyWorkerAdapter` with deterministic activation, account failover (auth/quota only), isolated HOME environment with API keys absent, wall_time aggregation, and backward-compatible receipt fields, without modifying `UnifiedRuntime`.

## Verification Commands
- `python3 -m pytest -q tests/services/test_agy_account_pool.py tests/nexus/executors/test_worker_contract.py tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `git diff --check`

## Exit Criteria
- All tests in verifier command suite pass clean.
- Target A1 recorded as RETAINED_SUPERSEDED_BY_A2.
- Zero changes to `UnifiedRuntime`.
- `git diff --check` yields zero whitespace issues.
