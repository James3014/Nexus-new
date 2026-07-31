# Task Card 04: Retained Clean Target Closure

## Identity

- task_id: `retained-clean-target-closure`
- campaign_id: `lifecycle-hardening-followup`
- artifact_authority: current
- status: READY
- owner: James Chen
- depends_on: `authorized-deletion-contract` integrated
- read_only: false
- audit_only: false
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Make the formal `close_without_candidate` lifecycle path release a retained Target that is physically clean and still at its leased initial HEAD when an independently verified integrated replacement exists, including a replacement retained in the durable archive. A dirty or changed-head Target must continue to require salvage evidence and remain fail-closed.

## Allowed files

- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

## Forbidden scope

No direct JSON editing, live state mutation, live worktree removal, branch/ref deletion, approval, integration, push, canonical-root mutation, P6 cutover, or GitNexus instruction changes. Tests must use temporary repositories and state directories only.

## Required behavior

1. A retained clean Target at `lease.initial_head` may close through the existing cleanup authority after `_require_integrated_replacement` succeeds.
2. A retained dirty Target still requires a durable salvage snapshot before cleanup.
3. A retained clean Target whose HEAD changed without a durable snapshot fails closed.
4. An integrated replacement may be resolved from the verified archived lifecycle state surface; arbitrary strings must not satisfy the replacement gate when a live Target exists.
5. No candidate evidence is created by this close path; cleanup and final disposition remain separately recorded.

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/nexus/orchestrator/test_self_hosted_task_service.py
git diff --check
git diff --name-status --diff-filter=D
```

## Evidence required

- RED proof that a retained clean Target currently cannot close safely.
- GREEN proof for archived integrated replacement and clean Target cleanup.
- Regression proof for dirty salvage and changed-head fail-closed behavior.
- Exact scoped commit and no approval/integration claim.

## Exit criteria

The formal lifecycle close path can dispose of a retained clean Target without requiring a meaningless salvage commit, while all dirty/changed evidence remains fail-closed.

## Residual debt

Live retained evidence requires owner-authorized invocation of the formal close API after this Candidate is integrated; this card does not mutate production state.

## Block classification

- `RECOVERABLE_BLOCK`: isolated test/runtime dependency failure.
- `HARD_BLOCK`: safe closure cannot be expressed through existing cleanup and archive authority without broadening scope.
