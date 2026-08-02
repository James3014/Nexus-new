# Campaign Index: lifecycle-concurrency-dispatch-corrective

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Fix three lifecycle regressions as one governed TDD packet: allow ISOLATED_TARGET creation from committed canonical HEAD while canonical has unrelated dirty state and bind a dirty snapshot to the lease; guarantee nexus_task_retry preserves task_id but creates a fresh attempt/action/idempotency identity; and prevent DIRECT_CANONICAL primary/codex requests from entering Assisted provider resolution or returning ASSIST_PROVIDER_NOT_REGISTERED. Preserve Direct dirty blocking, integration dirty blocking, human-only approval/integration, one serial Target budget, existing dirty files, and AUTO_CHAIN=false.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `lifecycle-concurrency-dispatch-corrective` | `00-lifecycle-concurrency-dispatch-corrective.md` | ACTIVE | Owner confirmation |
