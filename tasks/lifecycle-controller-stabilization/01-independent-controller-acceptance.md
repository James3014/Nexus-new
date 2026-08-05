# Task Card 01: Independent Controller Acceptance

## Identity

- task_id: `TASK-INDEPENDENT-CONTROLLER-ACCEPTANCE`
- campaign_id: `lifecycle-controller-stabilization`
- artifact_authority: planned
- status: BLOCKED_PENDING_OWNER
- owner: James Chen
- commit_required: false
- candidate_required: false
- worker_may_commit: false
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Independently inspect the C1 Candidate's action-identity behavior, fail-closed
ordering, exact scope, and evidence bindings without modifying the Candidate or
granting promotion authority.

## Activation gate

This card is outside the current execution round. It may not be activated by
the C1 worker, lifecycle state, campaign index, Gateway, MCP, or prior Owner
approval. A fresh explicit Owner instruction is required after the C1
Candidate has stopped at `PENDING_HUMAN_APPROVAL`.

## Allowed files

None. This is read-only acceptance work when separately activated.

## Forbidden scope

No edits, commits, approval, integration, merge, push, cleanup, Gateway reload,
Phase6 curation, legacy-test expansion, production claim, or automatic
successor activation.

## Acceptance surface

When separately authorized, independently reproduce the required C1 tests and
Git gates, inspect the complete Candidate diff, verify pre-side-effect mismatch
rejection and idempotency behavior, validate Candidate/Card/contract/receipt
hash bindings, and return an accept-or-fix verdict. Candidate status alone is
not acceptance truth.

## Block classification

`HARD_BLOCK` until a fresh Owner instruction explicitly activates C2.
