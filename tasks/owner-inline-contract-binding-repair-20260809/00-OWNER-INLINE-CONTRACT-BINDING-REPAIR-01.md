# Task Card: OWNER-INLINE-CONTRACT-BINDING-REPAIR-01

artifact_authority: current
task_id: `OWNER-INLINE-CONTRACT-BINDING-REPAIR-01`
owner: James Chen
status: ACTIVE
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Make OWNER_INLINE Candidate approval, closure binding, and integration use the
validated nested `nexus.owner_inline_contract.v1` contract hash. The persisted
service task-contract hash remains separate evidence and must not be substituted
for the Owner Inline approval identity. Tracked Task Card behavior must remain
unchanged and every mismatch must fail closed before lifecycle mutation.

## Baseline and reproduced defect

- Canonical baseline at authority creation:
  `f1b6fe3d217b58575d6acd43ec2add1038b8c567`.
- Accepted P4 Candidate:
  `2373deb1666db581932a4f19d6d0d1812cc680f8`.
- Reproduced task:
  `P4-GATEWAY-ASSIST-READONLY-R2-20260809`.
- Persisted service task-contract hash:
  `2b832260d25f4a6bb95fe7a4d41e15087511dc13705760cea2c8d7a96f33231c`.
- Validated nested Owner Inline contract hash:
  `0e97eb9a9ff9858f298b8d4e46c729439c48a1c13970c26daea8cf2e0666a72a`.
- Current typed approval fails with `CONTRACT_HASH_MISMATCH` before mutation.

## Allowed files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_target_integration_authority_closure.py`

## Required controls

- Add or reuse one canonical resolver for approval contract identity.
- For `OWNER_INLINE`, validate the persisted nested contract and use its exact
  `contract_hash`; do not trust the top-level service task-contract hash.
- For `TRACKED_TASK_CARD`, preserve the exact Task Card hash behavior.
- Apply the same resolved identity at Gateway approve/bind/integrate and service
  approve/bind/integrate revalidation seams.
- Reject missing, malformed, task-drifted, HEAD-drifted, or hash-tampered Owner
  Inline contracts before any state mutation or integration call.
- Do not edit durable lifecycle JSON or weaken approval expiry, runtime identity,
  Candidate binding, external acceptance, verifier, or integration gates.

## RED -> GREEN

1. A state whose top-level service contract hash differs from its valid nested
   Owner Inline hash fails under the current implementation and succeeds only
   when the approval is bound to the nested hash.
2. The same state with an approval bound to the top-level hash fails closed with
   zero state mutation and zero integration calls.
3. Gateway approve, closure bind, and integrate forward the resolved nested
   hash consistently.
4. Service approval, closure binding, and integration revalidation use the same
   identity and reject tamper.
5. A tracked Task Card Candidate remains byte-for-byte compatible at the
   approval identity boundary.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/nexus/orchestrator/test_unified_mcp_gateway.py \
  tests/nexus/orchestrator/test_target_integration_authority_closure.py
git diff --check
git diff --name-status
git diff --stat
git diff --cached --name-status
git diff --cached --stat
```

## Forbidden scope

No route/planner/workforce/provider changes, public schema expansion, durable
launcher or OAuth changes, lifecycle JSON edits, OpenWiki or learning-closure
files, direct canonical apply of P4, approval/integration/reload by the worker,
cleanup, push, release, or successor auto-chain.

## Exit criteria

One scoped Candidate commit bound to this card, exact tests green, no deletions,
independent primary review, and worker stop at `PENDING_HUMAN_APPROVAL`.

## Block classification

- `RECOVERABLE_BLOCK`: environmental test or provider failure with source and
  state intact.
- `HARD_BLOCK`: the repair requires weakening validation or changing route,
  lifecycle action vocabulary, public schema, or another subsystem.
