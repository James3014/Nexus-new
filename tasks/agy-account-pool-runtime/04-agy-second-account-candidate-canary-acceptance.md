---
artifact_authority: current
owner: James Chen
status: READY
task_id: agy-second-account-candidate-canary-acceptance
campaign_id: agy-account-pool-runtime
triggered_by:
  - agy-card01-live-dispatch-acceptance
depends_on_evidence:
  - 6170fb9951c5587a08f8d64812cba687b19f18ea
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# Task Card: AGY Second-Account Candidate Canary Acceptance

## Objective

Use the switched second AGY account in an isolated Target to repair the existing
safe fixture, produce a non-empty Candidate diff, and pass the existing
self-hosted lifecycle. This card is the next and only gate for the current AGY
two-account switch-and-dispatch closure.

The deferred structured-result capability is future Research Ledger/Reviewer
work and is not a prerequisite for this card.

## Existing Account A evidence

Account A evidence supports only the first-account provider invocation:

```yaml
account_a:
  alias_hash: f13b48bb5924
  provider_started: true
  exit_code: 0
  provider_calls: 1
  canonical_unchanged: true
  cleanup: REMOVED
```

It does not by itself complete Card 03.

## Account B acceptance contract

The current switched account is expected to have alias hash
`fd84db4038d7`. If `ensure-active` changes the active account before provider
execution, the final provider receipt alias is authoritative; it must differ
from Account A.

```yaml
execution_lane: ISOLATED_TARGET
worker: agy
model: gemini-3.6-flash-high
maximum_provider_calls: 1
rotation: forbidden
apply_to_canonical: false
merge: false
push: false
```

Only this source file may be changed:

```text
tests/fixtures/n30r_w0/target.py
```

Task:

```text
Repair add_one so add_one(4) == 5.
Modify only the allowed file; do not modify the verifier.
```

Required verifiers:

```bash
python3 tests/fixtures/n30r_w0/verify_target.py
git diff --check
```

Forbidden:

```text
tests/fixtures/n30r_w0/verify_target.py
production code
Task Contract runtime
Gateway
worker adapter
account manager
canonical checkout
```

Do not use `rotate-after-failure`. Do not manually switch a third account.

## Required preflight

Before dispatch:

1. Verify canonical HEAD is `314311276d7aff62562f06fab379a0e37e0fe123` and the
   working tree is clean.
2. Invoke the production `ensure-active` seam using the explicit manager path
   and runtime root.
3. Record only the final manager alias hash and actual isolated HOME hash.
4. Verify the AGY executable identity matches Account A.
5. Verify the Task Card identity and current controller revision.

The provider receipt alias must match the final `ensure-active` alias.

## Pass conditions

```yaml
account_b:
  manager_preflight_alias: fd84db4038d7
  provider_receipt_alias_matches: true
  provider_exit_code: 0
  candidate_diff_non_empty: true
  changed_files:
    - tests/fixtures/n30r_w0/target.py
  verifier_pass: true
  canonical_unchanged: true
  target_cleanup_complete: true

switch_proof:
  account_a_alias: f13b48bb5924
  account_b_alias: fd84db4038d7
  aliases_distinct: true
  same_agy_executable: true
  manager_switch_verified: true
```

The final provider receipt is the source of truth if `ensure-active` changes
the selected account. It must still differ from Account A and remain bound to
the manager preflight alias.

## Privacy and mutation boundary

Never persist or output raw account names, credentials, HOME paths, environment
dumps, raw provider streams, Git history, or unrelated files. Receipts may
contain only anonymized alias/HOME hashes, executable hashes, result hashes,
provider timing/exit evidence, verifier evidence, and cleanup evidence.

No canonical file, HEAD, or working tree mutation is permitted. No merge, push,
or production-readiness claim is permitted.

## Claim ceiling

If all pass conditions hold, the acceptance may report:

```text
AGY_TWO_ACCOUNT_SWITCH_AND_DISPATCH_LIVE_PASS
REAL_MANAGER_ACCOUNT_SELECTION_VERIFIED
AGY_SECOND_ACCOUNT_CANDIDATE_CANARY_PASS
CANONICAL_NO_MUTATION_VERIFIED
```

It must not report:

```text
AGY_ALL_ACCOUNTS_HEALTHY
AGY_ENTIRE_POOL_QUALIFIED
REAL_QUOTA_ROTATION_PHYSICALLY_VERIFIED
STRUCTURED_RESULT_RUNTIME_IMPLEMENTED
PRODUCTION_READY
```

## Completion receipt

```yaml
verdict:
starting_head:
ending_head:
working_tree:
task_card:
  path: tasks/agy-account-pool-runtime/04-agy-second-account-candidate-canary-acceptance.md
  hash:
account_a:
  alias_hash: f13b48bb5924
  provider_exit_code: 0
  provider_calls: 1
  canonical_unchanged: true
  cleanup_complete: true
account_b:
  manager_preflight_alias:
  provider_receipt_alias:
  isolated_home_hash:
  provider_exit_code:
  candidate_diff_non_empty:
  changed_files:
  verifier_pass:
  canonical_unchanged:
  cleanup_complete:
switch_proof:
  aliases_distinct:
  same_agy_executable:
  manager_switch_verified:
safety:
  credentials_exposed: false
  canonical_mutated: false
  merge_performed: false
  push_performed: false
claim_ceiling:
NEXT_GATE: AGY_TWO_ACCOUNT_SWITCH_AND_DISPATCH_LIVE_PASS
```
