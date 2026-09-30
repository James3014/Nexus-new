# Task Card: issue-1209-grok-host-affinity-r6

artifact_authority: current
task_id: `issue-1209-grok-host-affinity`
attempt_id: `ISSUE1209-HOST-AFFINITY-R6-20261001`
owner: James Chen
status: SUPERSEDED
superseded_by: `03-issue-1209-grok-host-affinity-r7.md`
supersedes: `01-issue-1209-grok-host-affinity-r5.md`
supersession_reason_r7: `PUBLISH_BASE_STABLE_FINAL_INTEGRATION_CONTRACT`
supersession_reason: `FINAL_PR_SCOPE_PROJECTION_RECONCILIATION`
execution_lane: GOVERNED
commit_required: true
candidate_required: true
allowed_file_count: 10
allow_deletions: false
claim_ceiling: CANDIDATE_READY_FOR_GOVERNED_GITHUB_MERGE_EVIDENCE_ONLY
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

worker_execution_card: `01-issue-1209-grok-host-affinity-r5.md`
worker_execution_card_sha256: `9b7d0e192378b549cc727fa3eff531575e9bcd9f0530873e7c47671666ba08fc`
worker_commit: `d3fca07a349ed693e6ba1cf93a199193275ce38a`

## Objective

Reconcile the final GitHub Candidate scope without changing #1209 product semantics
or granting another implementation attempt. R5 remains the immutable worker execution
contract. R6 binds the exact complete PR path set required by governed merge evidence,
including coordinator-owned Task Card and INDEX metadata.

allowed_files:
  - docs/integrations/CHATGPT_DIRECT_CONTROL_PROFILE.md
  - nexus/services/grok_account_pool.py
  - scripts/ops/nexus-grok-accounts
  - tasks/github-issue-1209-grok-host-affinity-20260930/00-issue-1209-grok-host-affinity.md
  - tasks/github-issue-1209-grok-host-affinity-20260930/01-issue-1209-grok-host-affinity-r5.md
  - tasks/github-issue-1209-grok-host-affinity-20260930/02-issue-1209-grok-host-affinity-r6.md
  - tasks/github-issue-1209-grok-host-affinity-20260930/INDEX.md
  - tests/ops/test_nexus_grok_accounts.py
  - tests/services/test_external_worker_dispatch.py
  - tests/services/test_grok_account_pool.py

## Implementation lineage

The production implementation and its original tests/docs were already present in the
R4 Candidate. Exact-base CI then exposed one pre-existing caller fixture that encoded
the obsolete unbound-pool assumption. Under R5, Agy changed only
`tests/services/test_external_worker_dispatch.py`, explicitly binding the synthetic
non-empty pool via the public `bind_host(confirm_existing_pool=True)` API.

R6 introduces no production/test behavior change. Its only new repository mutation is
coordinator-owned governance metadata needed to make final PR scope machine-exact.
## Verification commands

- `python3 -m pytest -q tests/services/test_grok_account_pool.py tests/ops/test_nexus_grok_accounts.py`
- `python3 -m pytest -q tests/services/test_external_worker_dispatch.py`
- `uv run ruff check nexus/services/grok_account_pool.py scripts/ops/nexus-grok-accounts tests/services/test_grok_account_pool.py tests/ops/test_nexus_grok_accounts.py tests/services/test_external_worker_dispatch.py`
- `git diff --check`

## Safety invariant

- non-empty legacy pools without `host_binding` remain fail-closed until explicit confirmation;
- copied pools bound to another host remain fail-closed before provider execution;
- no automatic production host binding or test-mode bypass;
- no second router, scheduler, account selector, distributed lease authority, approval authority, or merge authority;
- no OAuth/session/profile bytes are copied or persisted by this change.

## Acceptance boundary

Independent review must bind the final exact Candidate commit/tree, this R6 Card hash,
the base commit used by trusted CI, and the full diff. R5 worker PASS is implementation
evidence only and is not independent acceptance.

## Exit criteria

Exact-head required CI gates pass, independent exact-subject acceptance is recorded,
the governed merge projection is machine-valid, and the workflow reaches its protected
exact-head merge gate. R6 itself grants no push, approval, merge, release, or production
authority.
