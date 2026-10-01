# Task Card: issue-1209-grok-host-affinity-r5

artifact_authority: current
task_id: `issue-1209-grok-host-affinity`
attempt_id: `ISSUE1209-HOST-AFFINITY-R5-20261001`
owner: James Chen
status: SUPERSEDED
superseded_by: `02-issue-1209-grok-host-affinity-r6.md`
supersedes: `00-issue-1209-grok-host-affinity.md`
supersession_reason_r6: `FINAL_PR_SCOPE_PROJECTION_RECONCILIATION`
supersession_reason: `CI_CALLER_FIXTURE_REQUIRES_SCOPE_WIDENING`
execution_lane: GOVERNED
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Complete Issue #1209 without weakening host-affinity semantics. Preserve the existing
production implementation and repair the pre-existing external-worker caller fixture
so its synthetic non-empty Grok pool is explicitly bound to the current host before
provider execution. Exact-base CI proved the caller fixture still encoded the
pre-#1209 unbound-pool assumption.

## Scope delta from R4

R4 correctly requires legacy/non-empty unbound pools to fail closed. R5 MUST NOT add
implicit or automatic host binding to production behavior merely to satisfy the
regression test.
The only new mutable path is:

- `tests/services/test_external_worker_dispatch.py`

The caller fixture must use the public host-binding API with explicit confirmation
before the background Grok operation begins.

## Allowed files

- `nexus/services/grok_account_pool.py`
- `scripts/ops/nexus-grok-accounts`
- `tests/services/test_grok_account_pool.py`
- `tests/ops/test_nexus_grok_accounts.py`
- `tests/services/test_external_worker_dispatch.py`
- `docs/integrations/CHATGPT_DIRECT_CONTROL_PROFILE.md`

## Verification commands

```bash
python3 -m pytest -q tests/services/test_grok_account_pool.py tests/ops/test_nexus_grok_accounts.py
python3 -m pytest -q tests/services/test_external_worker_dispatch.py
uv run ruff check nexus/services/grok_account_pool.py scripts/ops/nexus-grok-accounts tests/services/test_grok_account_pool.py tests/ops/test_nexus_grok_accounts.py tests/services/test_external_worker_dispatch.py
git diff --check
```
## Safety invariant

The fix must preserve all of the following:

- non-empty legacy pools without `host_binding` remain fail-closed until explicit confirmation;
- copied pools bound to another host remain fail-closed before provider execution;
- no second router, scheduler, account selector, or distributed lease authority is introduced;
- no production auto-bind/test-mode bypass is permitted;
- no OAuth/session/profile bytes are copied or persisted by this change.

## Exit criteria

Produce one exact R5 commit within this scope, run every verification command above,
obtain independent exact-subject acceptance, update the PR merge-lane binding to the
R5 card/hash/head, and stop before protected merge authority.

## Block classification

Any required mutation outside these six files, any weakening of explicit host
binding, or any verifier failure is a HARD_BLOCK.
