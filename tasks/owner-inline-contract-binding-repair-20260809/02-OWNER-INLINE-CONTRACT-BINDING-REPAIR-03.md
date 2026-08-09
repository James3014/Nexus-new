# Task Card: OWNER-INLINE-CONTRACT-BINDING-REPAIR-03

artifact_authority: current
task_id: `OWNER-INLINE-CONTRACT-BINDING-REPAIR-03`
owner: James Chen
status: ACTIVE
supersedes: `OWNER-INLINE-CONTRACT-BINDING-REPAIR-02`
rejected_candidate: `f5104f5a8b42be7850c3c6ca4d1adb5b22c497ce`
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Finish the six-seam OWNER_INLINE approval identity repair without regressing
legacy TRACKED_TASK_CARD architecture approvals. Bind typed Owner Inline
approval and integration to the validated nested Owner Inline contract hash,
while keeping the top-level service contract hash as separate service evidence.

## Required implementation

Start from the reviewed Card 02 Candidate design, then correct and prove it:

1. Use one shared fail-closed resolver for Gateway approve/bind/integrate and
   service approve/bind/integrate.
2. For `OWNER_INLINE`, validate the nested contract against task id and expected
   head and use its canonical hash with `task_card_hash=None`.
3. For `TRACKED_TASK_CARD`, preserve existing Task Card behavior byte-for-byte.
4. In `approve_promotion`, require full typed validation for every Owner Inline
   approval and for complete public `nexus.approval.v2` grants. Do not interpret
   a legacy partial tracked/architecture approval as a complete public grant
   merely because it contains `approved_by`, `bound_task_id`, or one runtime
   field.
5. All mismatches must fail before state mutation, provider invocation, or
   integration invocation. Do not rewrite caller runtime identity.

## Required regression evidence

- Deliberately use different top-level service and nested Owner Inline hashes.
- Exercise actual Gateway approve, bind, and integrate paths; each must forward
  the nested hash and reject the top-level hash.
- Exercise actual service approve, bind, and integrate paths; each must accept
  nested-bound evidence and reject top-level-bound or tampered evidence with a
  byte-stable state and zero integration calls.
- Cover nested hash/task/head/runtime identity/approval hash tampering.
- Prove legacy partial tracked architecture approval behavior and complete
  public TRACKED_TASK_CARD approval behavior remain green.
- Run the exact card suite plus the full self-hosted task service suite.

## Allowed files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_target_integration_authority_closure.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/nexus/orchestrator/test_unified_mcp_gateway.py \
  tests/nexus/orchestrator/test_target_integration_authority_closure.py \
  tests/nexus/orchestrator/test_self_hosted_task_service.py
git diff --check
git diff --name-status
git diff --stat
git diff --cached --name-status
git diff --cached --stat
```

## Forbidden scope

No durable JSON edits, route/planner/workforce/provider changes, public schema,
contracts module changes, launcher/OAuth, OpenWiki, learning closure, approval,
integration, reload, cleanup, push, release, or successor auto-chain.

## Exit criteria

One scoped Candidate commit, exact tests green, no deletions, independent
primary review, and stop at `PENDING_HUMAN_APPROVAL`.

## Block classification

- `RECOVERABLE_BLOCK`: environmental verifier/provider issue.
- `HARD_BLOCK`: a correct repair requires weakening Owner Inline validation,
  changing public schema, or changing route/lifecycle vocabulary.
