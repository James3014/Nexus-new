# Task Card: PREAPPLY-CLOSURE-RECONCILE-RECOVERY-01

artifact_authority: current
task_id: `PREAPPLY-CLOSURE-RECONCILE-RECOVERY-01`
owner: James Chen
status: ACTIVE
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Repair the physical reconciliation gap where an exact
`INTEGRATION_FAILED_PRE_APPLY` task can fall through `reconcile_task()` into
generic lost-worker handling and be rewritten as `FINAL_BLOCK` with
`promotion_status=NOT_CREATED`. Preserve verified Candidate and integration
closure evidence and expose one fail-closed recovery path that requires a fresh
exact `CANDIDATE_INTEGRATE` approval before any apply.

## Baseline and dependency

- Authority baseline: `ac600ffc5c7fba4bdb2868ec8e0af7b8985c4062`.
- Re-anchor to fresh canonical before implementation.
- Do not overlap or cherry-pick around the externally owned
  `DEEPSEEK-WORKER-READINESS-FIX-01` Candidate. Start source work only after its
  disposition/integration is fixed and verify its exact Gateway/service diff.

## Allowed files

- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_target_integration_authority_closure.py`

## Required behavior

- `INTEGRATION_FAILED_PRE_APPLY` is a protected pre-apply closure state during
  reconcile and never enters lost-worker/provider recovery;
- reconcile is idempotent and does not invoke a worker, provider, verifier,
  integrate/apply path, Target cleanup, or approval reuse;
- Candidate commit/tree/state hash, verified receipt hash, attempt/card/contract
  identity, external acceptance, closure history, and integration execution
  evidence remain byte/hash bound;
- the known legacy `FINAL_BLOCK` projection is recoverable only when durable
  evidence proves the same exact Candidate, `merge_performed=false`, physical
  stage `PRE_APPLY`, unchanged canonical branch/head evidence, and the recorded
  lost-worker projection. Unknown or partial `FINAL_BLOCK` remains fail-closed;
- recovery restores only the pre-apply closure/rebind posture. A fresh exact
  `CANDIDATE_INTEGRATE` Owner grant is still mandatory before integration;
- stale/consumed-for-another-action approval, HEAD/branch/runtime drift,
  identity tamper, malformed history, or post-apply evidence fails closed with
  zero durable mutation.

## RED -> GREEN

1. Reconcile an exact `INTEGRATION_FAILED_PRE_APPLY` fixture; RED currently
   projects `FINAL_BLOCK/NOT_CREATED`, GREEN preserves all closure evidence and
   returns the typed retry/rebind action without writes.
2. Reconcile the exact known legacy projection shape; GREEN restores only the
   pre-apply recovery posture and appends auditable projection history.
3. Parameterize task/attempt/Candidate tree/state/receipt/card/contract,
   acceptance, branch/head, stage, merge, error-provenance, and closure-history
   drift; every case fails before mutation.
4. Assert provider calls, worker launches, verifier executions, integration
   applies, cleanup, approval consumption, and canonical Git mutation are zero.
5. Exact duplicate recovery is deterministic and does not append duplicate
   history.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/nexus/orchestrator/test_target_integration_authority_closure.py \
  tests/nexus/orchestrator/test_self_hosted_task_service.py
git diff --check
git diff --name-status
git diff --stat
git diff --cached --name-status
git diff --cached --stat
```

## Forbidden scope

No Gateway/MCP schema, provider/readiness, durable launcher/OAuth, route/planner,
workforce, verifier identity redesign, OpenWiki, lifecycle JSON edits, direct
state-file edits, live recovery, approval, integration, cleanup, reload, push,
or production claim. Do not touch another agent's Target.

## Exit criteria

One clean scoped Candidate commit, exact tests green, no deletions, independent
review, and a recovery receipt proving zero provider/apply side effects. Worker
stops before approval, integration, live state recovery, reload, cleanup, or
push.

## Block classification

- `RECOVERABLE_BLOCK`: active overlapping service Candidate or test/environment
  issue.
- `HARD_BLOCK`: recovery requires weaker identity evidence, post-apply rollback,
  destructive state rewrite, or route/lifecycle authority expansion.
