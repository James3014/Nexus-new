# Task Card: OWNER-INLINE-CONTRACT-BINDING-REPAIR-02

artifact_authority: current
task_id: `OWNER-INLINE-CONTRACT-BINDING-REPAIR-02`
owner: James Chen
status: ACTIVE
supersedes: `OWNER-INLINE-CONTRACT-BINDING-REPAIR-01`
rejected_candidate: `30c01b759ea5f6b466abd8d7330fd77a4ab8e3ea`
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Complete the OWNER_INLINE approval identity repair that Card 01 only partially
implemented. Use one shared, fail-closed identity resolver and add explicit
regression tests before the Candidate is eligible for primary review.

## Required implementation

The resolver accepts persisted state plus expected task/head and returns:

- `OWNER_INLINE`: validated nested `owner_inline_contract`, its exact canonical
  `contract_hash`, and `task_card_hash=None`;
- `TRACKED_TASK_CARD`: the existing Task Card hash/contract behavior unchanged.

Use the resolver at all six seams:

1. Gateway `_candidate_approve`;
2. Gateway `_candidate_bind_integration`;
3. Gateway `_candidate_integrate`;
4. service `approve_promotion` before any mutation;
5. service `bind_candidate_integration_closure` for approval, immutable closure,
   runtime identity, replay, and concurrency checks;
6. service `integrate_approved` for persisted approval revalidation.

Do not merely rewrite caller-provided runtime identity. Validate exact equality
between the resolved identity, typed approval, and runtime identity; mismatch
must fail before state mutation or integration invocation.

## Required regression evidence

- Add production-focused tests to both allowed test files; a production-only
  diff is ineligible.
- Deliberately set top-level service `contract_hash` different from the valid
  nested Owner Inline hash.
- Prove Gateway approve/bind/integrate each use the nested hash.
- Prove direct service `approve_promotion`, closure bind, and integration accept
  the nested-bound grant and reject a top-level-bound grant before mutation.
- Tamper nested hash, task id, expected head, runtime identity, and approval hash;
  assert byte-stable state and zero integration/provider calls.
- Prove tracked Task Card identity remains unchanged.

## Allowed files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_target_integration_authority_closure.py`

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

No durable JSON edits, route/planner/workforce/provider changes, public schema,
contracts module changes, launcher/OAuth, OpenWiki, learning closure, approval,
integration, reload, cleanup, push, release, or successor auto-chain.

## Exit criteria

One scoped Candidate commit touching source and regression tests, exact tests
green, no deletions, independent primary review, and stop at
`PENDING_HUMAN_APPROVAL`.

## Block classification

- `RECOVERABLE_BLOCK`: environmental verifier/provider issue.
- `HARD_BLOCK`: a correct repair requires weakening approval validation or
  changing public schema, route authority, or lifecycle action vocabulary.
