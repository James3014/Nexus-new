---
artifact_authority: current
task_id: github-issue-98-merge-block-controller-throughput
campaign_id: github-issue-98-merge-block-controller-throughput-20260818
source_issue: "#98"
owner: James Chen
status: ACTIVE
baseline_revision: 8c2584d6053dd1f04dc87333f807fbea1726545e
historical_baseline_revision: 1ee1c69332514bdbaa5a98f5ed29fad109425c32
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_push: false
worker_may_approve: false
worker_may_integrate: false
AUTO_CHAIN: false
---

# P0: merge-blocked Candidate must not block disjoint execution

## Objective

Prove and enforce `MERGE_BLOCKED != CONTROLLER_BLOCKED`. Replace the two
ordinary global serial gates in self-hosted task admission and physical Target
creation with one fail-closed decision derived from exact task/attempt/lease,
controller/source, mutation mode, and normalized allowed-path identity.

A Candidate that has left mutable execution and is waiting for acceptance,
integration, retry, or an exact Owner merge slot must not block an independent
isolated task whose mutation scope is demonstrably disjoint. Exact, parent/child,
malformed, ambiguous, stale, forged, or cleanup-ownership conflicts continue to
block before provider invocation.

## Authority and dependencies

- GitHub main baseline is the exact rebound revision above. The historical
  baseline is provenance only and grants no stale source authority.
- Issue #163 is physically closed at current main; standing-grant changes are a
  settled predecessor and remain outside this Candidate's scope.
- Issue #96 completed `POST_30_LOCAL_DELTA_FULLY_ACCOUNTED` in comment
  `#5323785365`; the #98 semantic prerequisite is cleared for source mutation.
- Issues #7 and #8 are closed; their historical moving-blocker text is stale.
- PR #409 owns `tests/nexus/orchestrator/test_self_hosted_task_service.py`.
  This Candidate may execute but must not modify that file.
- The running Gateway is observation-only and currently reports
  `reload_required=true`; no live mutation or completion claim may consume it.

## Allowed files

- `tasks/github-issue-98-merge-block-controller-throughput-20260818/INDEX.md`
- `tasks/github-issue-98-merge-block-controller-throughput-20260818/00-merge-block-controller-throughput.md`
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/worktree_manager.py`
- `tests/nexus/orchestrator/test_merge_block_controller_throughput.py`

Maximum: exactly the five paths above. No deletions.

## Required red-first witnesses

1. Candidate A is held in `CANDIDATE_CAPTURED` or `VERIFIED` with
   `allowed_files=["scope/a.txt"]`; independent Task B with
   `allowed_files=["scope/b.txt"]` must reach worker/provider invocation and a
   distinct Target. The pre-fix test must fail on the global serial guard.
2. The same fixture with exact or parent/child overlap must block B before
   provider invocation and keep invocation count at zero.
3. The physical WorktreeManager gate must independently demonstrate the same
   disjoint-allow / overlap-block behavior; changing only the service guard is
   not sufficient.

## Mandatory regression matrix

- merge-waiting A + disjoint B: allow;
- merge-waiting A + exact overlap B: block pre-provider;
- parent/child overlap: block;
- malformed or ambiguous path: block;
- stale task/attempt/lease/controller identity: block;
- cleanup/cancel/reconcile A cannot alter B Target, branch, lease, or evidence;
- retry/idempotent replay A cannot create a second provider call or Target;
- direct-canonical overlapping mutation remains blocked;
- forged competition identity is not a bypass;
- integration expected-HEAD/CAS movement remains fail-closed;
- ordering of two admission attempts is deterministic;
- one merge-blocked Candidate does not reduce throughput for unrelated READY work.

## Forbidden scope

- No global `allow_parallel` switch and no removal of conflict controls.
- No `competition_id` bypass.
- No change to CapabilityPlanner, Workforce Admission, Candidate identity,
  verifier/review/checks, exact-head merge, CAS, or integration safety.
- No edits to PR #409-owned tests, Gateway, provider/runtime configuration,
  protected refs, #143, release, deployment, or production/public claims.

## Verification

```bash
.venv/bin/python -m pytest -q tests/nexus/orchestrator/test_merge_block_controller_throughput.py
.venv/bin/python -m pytest -q tests/nexus/orchestrator/test_worktree_manager.py
.venv/bin/python -m pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py
.venv/bin/python -m pytest -q tests/nexus/orchestrator/test_target_integration_authority_closure.py
.venv/bin/ruff check nexus/orchestrator/self_hosted_task_service.py nexus/orchestrator/worktree_manager.py tests/nexus/orchestrator/test_merge_block_controller_throughput.py
git diff --check
git diff --diff-filter=D --name-status
```

## Exit and claim ceiling

Exit with one scoped issue-branch Candidate commit and primary verification.
Independent exact-head review is required. Physical E2E requires a post-merge,
freshly loaded runtime where Candidate A waits at the merge boundary while
disjoint B reaches Candidate; source tests alone cannot claim
`MERGE_BLOCK_NO_LONGER_GLOBAL_CONTROLLER_BLOCK`.

`HARD_BLOCK` on scope expansion, missing identity, overlap ambiguity, false-green
guard removal, or integration-safety regression. `RECOVERABLE_BLOCK` on a
bounded test/format defect.
