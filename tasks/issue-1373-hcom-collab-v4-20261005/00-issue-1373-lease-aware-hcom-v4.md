# Task Card: issue-1373-lease-aware-hcom-v4

artifact_authority: current
task_id: `issue-1373-lease-aware-hcom-v4`
campaign_id: `issue-1373-hcom-collab-v4-20261005`
owner: James Chen (James3014)
status: ACTIVE
execution_lane: GOVERNED
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false
base_commit: `3ff423ecf11dd956eeb95430de79407c602b525e`

## Objective

Implement Issue #1373 against canonical Gateway/main source 3ff423ecf11dd956eeb95430de79407c602b525e. Make hcom collaborative Agy sessions lease-aware through the existing CrossProcessLeaseCoordinator and existing durable operation/process evidence. Preserve nexus-agy-dispatch as the sole routing/admission authority and hcom as transport/session only. The exact leased account snapshot HOME must be passed to hcom-agy-safe rather than re-selecting manager current. Hold the same per-account collision authority for the complete foreground hcom/Agy lifetime, preserving provider_pid/provider_process_state/first_effect truth. Parent crash or registry loss must not permit concurrent reuse while the live child still owns the lease; after abnormal/lost-ack termination, a lock-free but unreconciled receipt must fail closed until exact reconciliation rather than being overwritten. Clean positively observed exit may release. Resume must reacquire/rebind through canonical admission. Reuse existing operation journal/process-truth stores; create no second router, lease registry, journal, scheduler, verifier, acceptance authority, merge authority, or hcom-owned admission. Expose non-secret collaborative lease/session/reconcile state through workflow doctor and prove bidirectional dispatcher/collaborative mutual exclusion, distinct-account parallelism, crash/orphan/registry-loss behavior, clean cleanup, and OUTCOME_UNKNOWN != retry permission.

## Allowed files

- `tasks/issue-1373-hcom-collab-v4-20261005/00-issue-1373-lease-aware-hcom-v4.md`
- `tasks/issue-1373-hcom-collab-v4-20261005/INDEX.md`
- `scripts/ops/nexus-hcom-agy-safe`
- `scripts/ops/nexus-agy-dispatch`
- `nexus/services/agy_account_pool.py`
- `nexus/services/workflow_doctor.py`
- `tests/ops/test_nexus_hcom_agy_safe.py`
- `tests/services/test_account_concurrency.py`
- `tests/services/test_agy_dispatch.py`
- `tests/services/test_workflow_doctor.py`

## Verification commands

```bash
python3 -m pytest -q tests/ops/test_nexus_hcom_agy_safe.py tests/services/test_account_concurrency.py tests/services/test_agy_dispatch.py tests/services/test_workflow_doctor.py
python3 -m ruff check scripts/ops/nexus-hcom-agy-safe scripts/ops/nexus-agy-dispatch nexus/services/agy_account_pool.py nexus/services/workflow_doctor.py tests/ops/test_nexus_hcom_agy_safe.py tests/services/test_account_concurrency.py tests/services/test_agy_dispatch.py tests/services/test_workflow_doctor.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
