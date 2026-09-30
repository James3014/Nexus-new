# Task Card: issue-1209-grok-host-affinity-r7

artifact_authority: current
task_id: `issue-1209-grok-host-affinity`
attempt_id: `ISSUE1209-HOST-AFFINITY-R7-20261001`
owner: James Chen
status: ACTIVE
supersedes: `02-issue-1209-grok-host-affinity-r6.md`
supersession_reason: `PUBLISH_BASE_STABLE_FINAL_INTEGRATION_CONTRACT`
execution_lane: GOVERNED
commit_required: true
candidate_required: true
allowed_file_count: 6
allow_deletions: false
claim_ceiling: CANDIDATE_READY_FOR_GOVERNED_GITHUB_MERGE_EVIDENCE_ONLY
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

implementation_worker_card: `01-issue-1209-grok-host-affinity-r5.md`
implementation_worker_card_sha256: `9b7d0e192378b549cc727fa3eff531575e9bcd9f0530873e7c47671666ba08fc`
implementation_worker_commit: `d3fca07a349ed693e6ba1cf93a199193275ce38a`
r6_independent_review_output_sha256: `bbdaa8d1355b6b9f9535207c8a50385d2f188246824ebec78d124b98e1497741`

## Objective

Provide the base-stable governed integration contract for Issue #1209 after exact-base
CI exposed one caller fixture that still encoded the pre-host-affinity assumption.
This card is published to main before the final integration Candidate is rebound.
It grants no new implementation attempt and does not weaken the R5 safety semantics.

allowed_files:
  - docs/integrations/CHATGPT_DIRECT_CONTROL_PROFILE.md
  - nexus/services/grok_account_pool.py
  - scripts/ops/nexus-grok-accounts
  - tests/ops/test_nexus_grok_accounts.py
  - tests/services/test_external_worker_dispatch.py
  - tests/services/test_grok_account_pool.py

## Required invariants

- A non-empty legacy pool without `host_binding` remains fail-closed until explicit
  owner-host confirmation.
- A copied pool bound to another host fails before lease/account mutation or provider
  execution.
- The external-worker caller fixture binds its synthetic non-empty pool only through
  the public `bind_host(confirm_existing_pool=True)` API.
- No production auto-bind path, test-mode bypass, second router, scheduler, account
  selector, distributed lease authority, approval authority, or merge authority is
  introduced.
- Host sync continues to exclude OAuth/session/profile bytes and mutable lease state.

## Verification

- `python3 -m pytest -q tests/services/test_grok_account_pool.py tests/ops/test_nexus_grok_accounts.py`
- `python3 -m pytest -q tests/services/test_external_worker_dispatch.py`
- `uv run ruff check nexus/services/grok_account_pool.py scripts/ops/nexus-grok-accounts tests/services/test_grok_account_pool.py tests/ops/test_nexus_grok_accounts.py tests/services/test_external_worker_dispatch.py`
- `git diff --check`
- exact-head required GitHub checks
- independent exact-subject Candidate acceptance

## Base-stability requirement

This exact card must exist byte-identically in both the PR base and final integration
head before the trusted governed merge lane is evaluated. The final integration
Candidate must therefore contain exactly the six `allowed_files` paths above; the
campaign metadata is publication evidence on main, not part of that Candidate diff.

## Exit criteria

Rebind the existing #1209 implementation onto a base containing this exact card,
preserve the six-path implementation semantics, obtain exact-head CI and independent
acceptance, and stop at the protected exact-head merge gate. #1209 remains open across
the merge for physical two-host post-merge acceptance.

## Stop boundary

Any product behavior change beyond the settled R5 repair, any seventh implementation
path, any deletion, any weakening of host-affinity fail-closed behavior, or any
authority expansion is a HARD_BLOCK.
