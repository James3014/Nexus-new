---
task_id: github-issue-129-atomic-work-claim
issue: 129
repository: James3014/Nexus-new
baseline_revision: 80370ab3c5e3c3714cf378de1dba90412d1a2a7f
status: ACTIVE
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
claim_ceiling: CLAIM_PROTOCOL_CANDIDATE_PR_ONLY
---

# Atomic Ready-Issue work claim

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

