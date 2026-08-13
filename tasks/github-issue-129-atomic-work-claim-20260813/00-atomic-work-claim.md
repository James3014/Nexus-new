---
task_id: github-issue-129-atomic-work-claim
issue: 129
repository: James3014/Nexus-new
baseline_revision: 8e0986b40db56016c79b03eb81ff3d03c85c6f32
rebind_lineage_commit: 7c47118458f320a56f6b209393eb906b3fe878f4
rebind_authorization: direct Owner authorization for persistent claim subrecord/recovery under existing SelfHostedTaskService .state.lock
status: COMPLETED
execution_lane: ISOLATED_TARGET
worker_role: bounded_code_candidate
claim_intent: MANUAL_DISPATCH
claim_enforcement_state: PROJECTION_ONLY
claim_mode: MANUAL_DISPATCH
auto_chain: false
max_files: 4
allowed_files:
  - nexus/orchestrator/self_hosted_task_service.py
  - tests/nexus/orchestrator/test_self_hosted_task_service.py
  - tasks/github-issue-129-atomic-work-claim-20260813/INDEX.md
  - tasks/github-issue-129-atomic-work-claim-20260813/00-atomic-work-claim.md
authorized_deletions: []
reconciled_main: eb668fb76f0c30d8f025db42cdb8e320d556c037
current_main: eb668fb76f0c30d8f025db42cdb8e320d556c037
terminal_marker: ATOMIC_READY_ISSUE_WORK_CLAIM_PROVEN
claim_ceiling: ATOMIC_READY_ISSUE_WORK_CLAIM_PROVEN_EXISTING_SELF_HOSTED_SERVICE_ONLY
shared_file_gate: SATISFIED_BY_PR226_MERGE_A787E8E7
implementation_gate: Owner-authorized bounded implementation active
---

# Atomic Ready-Issue work claim

- task_id: `github-issue-129-atomic-work-claim`
- status: `COMPLETED`

## Objective

Extend the existing `SelfHostedTaskService` canonical machine-shared task
state and its existing `.state.lock` serialization point with one bounded,
hash-bound work-claim subrecord. Do not create a second state root, registry,
lock service, router, scheduler, or lifecycle authority.

The public service seam must support the semantic outcomes `CLAIMED`,
`ALREADY_CLAIMED`, and `BLOCKED`. It must bind the exact repository/Issue,
task/attempt/action, worker/provider/model, role and claim ceiling, base/source,
Task Card, normalized allowed-files or mutation-domain hash, fresh Workforce
Admission receipt identity, optional required provider/realm preflight, claim
id, and monotonic generation/fencing identity.

## Preconditions bound by this card

- Issue #128 is physically settled in `main` and its worker-neutral vocabulary
  remains authoritative.
- Issue #65 / PR #227 is physically settled before this baseline, so the only
  shared service-test overlap is closed.
- The current source owner is `SelfHostedTaskService`; the implementation must
  reuse its canonical state directory, per-task JSON, `.state.lock`, atomic
  replace, task/attempt/action identity, and existing lifecycle authority.
- `CapabilityPlanner` remains the sole route selector. Workforce Admission is
  eligibility evidence only and must be freshly verified, not recomputed into
  routing authority by the claim seam.

## Rebind and frozen contract

This card is freshly bound to exact `nexus-new/main` commit
`8e0986b40db56016c79b03eb81ff3d03c85c6f32`; no force, rebase, or history
rewrite is permitted. The Owner authorizes only the persistent claim subrecord
and recovery protocol within the existing `SelfHostedTaskService` state
directory and `.state.lock`. The implementation must freeze, validate, and
hash-bind the following exact identity tuple before any mutable callback:

`repository`, `issue`, `task_id`, `attempt_id`, `action_id`, `worker_id`,
`provider`, `model`, `role`, `claim_ceiling`, `base_revision`, `source_hash`,
`task_card_path`, normalized `allowed_files`/mutation-domain hash, fresh
Workforce Admission receipt identity, optional required provider/realm
preflight identity, `claim_id`, and monotonic `generation`/`fencing_token`.

Recovery is a durable subrecord update under the same lock: it records the
reason, advances generation/fencing, and leaves exactly one current owner.
Timeout is not authority transfer. All acquisition, replay, release, cleanup,
recovery, and later authoritative mutation/Candidate handoff paths validate the
claim id plus generation and the full owner/scope tuple. The hostile matrix
below is the acceptance boundary for malformed, stale, competing, tampered,
and wrong-owner requests.

The card preserves #128 worker-neutral semantics and remains separate from
#98 physical Target leases, #130 consumers/polling, #191/#143, route selection,
Workforce policy, lifecycle approval/integration/merge, runtime activation,
release, and production claims.

## Required behavior

1. Acquisition revalidates the current task state and exact bound identity
   while holding the existing state lock, then atomically creates the claim.
2. An exact replay of the same logical request is idempotent and returns
   `ALREADY_CLAIMED`; a changed or competing request returns `BLOCKED` before
   provider or mutation callbacks.
3. Claim generation is monotonic for recovery/supersession. Every later
   authoritative mutation, Candidate handoff, release, or cleanup entry point
   added by this card must validate the current claim id and generation.
4. Timeout alone never transfers authority. Recovery records a durable reason,
   advances generation, and fences the former holder.
5. Release/cleanup is owner-exact. Wrong issue, task, attempt, worker, scope,
   admission, claim id, or generation fails closed.
6. Different Issues remain independently claimable at the ownership layer;
   this makes no #98 physical parallel-Target claim.
7. Claim ownership never implies route/model selection, Candidate acceptance,
   integration, GitHub merge, runtime activation, release, or production truth.

## Hostile verification matrix

- two concurrent claimants for the same Issue/attempt produce exactly one
  `CLAIMED`; the loser is `BLOCKED` and invokes no mutation/provider callback;
- exact replay is `ALREADY_CLAIMED` with no duplicate mutable work;
- stale base/source, controller revision, Task Card, scope, Workforce receipt,
  provider preflight, or worker/model identity blocks;
- stale/superseded generation cannot mutate, publish Candidate, release, or
  clean the current holder;
- wrong owner cannot release another owner; recovery advances the fence and
  preserves one current owner plus a durable reason;
- malformed/tampered persisted claim or hash fails closed;
- two different Issue identities can acquire independent claims without
  asserting simultaneous Target execution;
- no claim result widens scope, reroutes work, promotes a model, self-accepts,
  integrates, or merges.

## Verification

Run at minimum:

```text
python3 -m pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py -k 'work_claim' --disable-warnings --maxfail=1
python3 -m pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py --disable-warnings --maxfail=1
python3 -m compileall -q nexus/orchestrator/self_hosted_task_service.py
git diff --check
```

Ruff must be evaluated exact-base. Existing unrelated debt in the large shared
source/test files may be classified only with base evidence; no new finding or
format delta is allowed in changed hunks.

## Forbidden scope

- no new state root, database, registry, lock daemon, scheduler, or router;
- no changes to `CapabilityPlanner`, Workforce policy/roster, Gateway, unified
  runtime, WorktreeManager/#98 Target leases, approval, integration, merge,
  release, or production surfaces;
- no Issue #130 consumer/polling behavior and no successor activation;
- no #191 or #143 work;
- no self-approval, self-acceptance, protected merge, or main mutation.

## Exit

Stop at an exact four-file Candidate commit/PR with deterministic hostile
tests, scope/deletion audit, exact-base static evidence, and independent review
pending. `AUTO_CHAIN=false`.

## Completion receipt

PR #235 head `3828921cfea8bd924fef7aced016c88f3c56b394` merged at
`eb668fb76f0c30d8f025db42cdb8e320d556c037` from the preserved historical
baseline `8e0986b40db56016c79b03eb81ff3d03c85c6f32`. The exact four-file change
had zero deletions; required checks were successful with Tier3 skipped as
expected. Independent post-merge acceptance passed 26 focused work-claim
tests and all 291 SelfHostedTaskService tests, with no new exact-base Ruff
debt and no hostile behavioral finding.

`ATOMIC_READY_ISSUE_WORK_CLAIM_PROVEN` covers only the canonical atomic claim
subrecord in the existing SelfHostedTaskService state and `.state.lock`. It
does not authorize #130 consumer/polling, #98 Target concurrency, another
store/scheduler/router, route or Workforce selection, approval, integration,
merge, runtime, release, or production truth. `AUTO_CHAIN=false` remains in
force.
