# Task Card 00: Controller Action Identity Stabilization

## Identity

- task_id: `TASK-CONTROLLER-ACTION-IDENTITY-STABILIZATION`
- campaign_id: `lifecycle-controller-stabilization`
- artifact_authority: current
- status: READY
- owner: James Chen
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Bind every lifecycle action envelope to the exact physical request that the
self-hosted service executes. An action-bearing request must fail closed on any
identity mismatch before durable state write, Target creation, provider
preflight, or worker launch. The Controller remains clean-only, immutable, and
Git-bound.

## Inputs and dependencies

- B0 source anchor: `e93dc3e4b101c4019436f3db5a6082f916ffae8d`
- Runtime base: the B0 governance commit descending directly from that anchor
- Controller: a new clean detached worktree at the runtime base
- Task Card: this Git-tracked file, resolved and hashed from that Controller
- Forensic-only reference: `51b89674132eb0b3deff452b797fe016d1c7f814`
- Dependency: every B0 gate in `INDEX.md` is green

## Required behavior

For action-bearing submissions:

1. Require a mapping-valued `bound_action_request` and recompute its canonical
   request hash; it must equal the envelope `request_hash`.
2. Bind task id, attempt id, action id, idempotency key, expected Controller
   HEAD, allowed paths, task-card path/hash, and contract kind/hash wherever
   those fields are duplicated across the envelope, bound request, and outer
   transport request.
3. Treat outer duplicate fields as untrusted transport copies: they may match
   but may not override the validated envelope or bound payload.
4. Derive operational request values only from the validated bound payload and
   validated envelope identity.
5. Reject every mismatch before any durable state write or external side
   effect, including Target allocation, provider preflight, and worker launch.
6. Reject reuse of one idempotency key with a different validated request hash.
7. Preserve clean-only Controller enforcement. Do not add a dirty-controller
   waiver or use `controller_status_sha256` as dirty-content identity.

Actionless CLI submissions may retain their existing governed behavior. This
card does not create a second router, planner, lifecycle, or execution policy.

## Allowed files

- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_self_hosted_controller.py`
- `tests/nexus/orchestrator/test_worktree_manager.py`
- `tests/nexus/orchestrator/test_candidate_verifier.py`
- `tests/nexus/orchestrator/test_candidate_commit.py`

File-count ceiling: 6. Authorized deletions: none.

## Forbidden scope

- No mutation of `/Users/jameschen/Workspace/nexus` during C1.
- No whole-file copy from the dirty canonical checkout.
- No cherry-pick, merge, rebase, transplant, or base use of `51b89674132eb0b3deff452b797fe016d1c7f814`.
- No dirty Controller authorization or dirty hash waiver.
- No `controller_status_sha256` dirty-content identity.
- No ASSISTED-to-DIRECT mapping.
- No `ISOLATED_TARGET` route authority and no new `execution_lane` policy.
- No Gateway route selection, provider/model authority, second planner, or
  second lifecycle.
- No Phase6 curation, legacy tests, learning logs, reports, task-file edits,
  Gateway reload, approval, integration, merge, push, or cleanup.
- If this allowlist is insufficient, stop with `TASK_CARD_SCOPE_INSUFFICIENT`;
  do not widen it.

## TDD method

Work in small vertical RED-to-GREEN slices. Add one failing identity-boundary
test, confirm its expected failure, make the smallest production change, and
rerun that focused test before continuing. Preserve the existing actionless
path and existing clean-only worktree behavior.

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/jameschen/Workspace/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/contracts/test_lifecycle_action.py tests/nexus/orchestrator/test_lifecycle_guards.py tests/nexus/orchestrator/test_self_hosted_controller.py tests/nexus/orchestrator/test_worktree_manager.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/orchestrator/test_candidate_verifier.py tests/nexus/orchestrator/test_candidate_commit.py
git diff --check <BASE_SHA>...HEAD
git diff --name-status <BASE_SHA>...HEAD
git diff --name-status --diff-filter=D <BASE_SHA>...HEAD
git diff --binary <BASE_SHA>...HEAD | git apply --reverse --check
git status --short --branch
git rev-parse HEAD HEAD^{tree}
git merge-base --is-ancestor <BASE_SHA> HEAD
```

`<BASE_SHA>` is the frozen B0 governance commit and Candidate parent.

## Evidence required

Record exact argv, cwd, relevant environment allowlist, test start/end HEAD and
tree, stdout/stderr digests, exit codes, changed and deleted paths, RED-to-GREEN
evidence, Controller clean checks, Target base and final hashes, ancestry,
reverse-apply result, task-card path/hash, contract kind/hash, Candidate commit,
tree, ref, state, diff hash, verified receipt hash, and any false claim that was
explicitly rejected.

## Exit criteria

- Candidate parent equals the frozen B0 governance commit.
- Candidate changes only the six-file allowlist, deletes nothing, and contains
  no Phase6, dirty-controller authorization, learning-log, report, or task-file
  change.
- Required tests and Git gates pass from the clean isolated Target.
- Formal lifecycle state is `PENDING_HUMAN_APPROVAL` and binds the Candidate,
  Task Card, contract, verifier evidence, and receipt hashes.
- Controller remains at its frozen HEAD/tree and clean.
- Execution stops without approval or integration.

## Block classification

- `RECOVERABLE_BLOCK`: a transient provider or process failure with the same
  frozen Card, Controller, Target, and lifecycle state safely retained.
- `HARD_BLOCK`: identity ambiguity, task-card drift, dirty Controller, scope
  insufficiency, unauthorized file/deletion, unsafe base, side effect before a
  required mismatch rejection, or missing Candidate evidence.
