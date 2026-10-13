# Task Card: Issue #1429 universal agent mutation enforcement — G2 managed capability enforcement

artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: issue-1429-universal-agent-mutation-enforcement-g2
attempt_id: attempt-1429-g2-managed-capability-enforcement
execution_lane: `GOVERNED`
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Parent authority

- GitHub Issue: `James3014/Nexus-new#1429`
- G1 merge: `38512dbf4129677674c3fc5fe6aa8d49f55d3f1b`
- DevSpace consumer Issue: `James3014/devspace#364`
- Owner request: complete Wave 2 capability enforcement without changing routing, Core ownership, branch-protection rollout, or Gateway deployment authority.

## Objective

Make supported managed mutation transports consume the Nexus-owned G1 mutation admission before source mutation or publication.

This card owns the Nexus-new side of G2:
- Agy/direct delegated mutation admission consumption;
- shared pointer semantics needed by managed transports;
- negative controls for missing, stale, wrong-repository, wrong-base, and scope-widened admission.

DevSpace implementation is owned by `James3014/devspace#364` and must retain its repository-local source/test/Core-completion evidence.

## Architecture boundary

- Nexus-new remains the sole mutation-admission authority.
- DevSpace/Agy/local agents are consumers only; they must not mint or widen admission.
- `nexus-core` remains Evidence Trust + Completion only.
- `CapabilityPlanner` remains route authority.
- Existing DevSpace `resumableWork`, writer lease, `expectedHead`, `writePaths`, tool/effect projections and Core session semantics remain separate and may only narrow.
- Raw OS/RDC/GitHub mutation that is outside a managed consumer path is not claimed physically impossible in G2; G3 must block integration of unmanaged changes.

## Allowed files

- `scripts/ops/nexus-agy-dispatch`
- `tests/services/test_agy_dispatch.py`
- `tests/services/test_agy_dispatch_fast_failover.py`
- `nexus/orchestrator/mutation_admission.py`
- `tests/nexus/orchestrator/test_mutation_admission.py`
- `tasks/github-issue-1429-universal-agent-mutation-enforcement-20261005/01-g2-managed-capability-enforcement.md`
- `docs/testing/test_impact_map.md`

## Required behavior

1. A write-capable Agy dispatch must consume an exact `admission_id + receipt_hash` from the Nexus-owned durable admission store before provider launch.
2. Consumer validation must re-read canonical persisted admission; caller-provided fields alone are never authority.
3. The consumed admission must bind canonical repository identity, exact admitted base SHA, existing G1 lane/authority, and requested write scope as a subset of admitted `allowed_paths`.
4. `plan` / read-only Agy runs remain usable without mutation admission.
5. Missing store, missing receipt, expired receipt, tampered hash, wrong repository, stale/wrong base, or write-scope widening fails before provider launch.
6. DevSpace #364 must consume the same G1 identity at its managed mutation sinks; no second admission authority/store may be introduced.
7. Admission consumption does not imply Core completion, Candidate acceptance, merge, release, deployment, or production authority.

## Negative controls

- accept-edits without admission -> BLOCK before provider launch;
- forged/nonexistent admission id/hash -> BLOCK;
- admission for another canonical repository -> BLOCK;
- admitted base != dispatch base -> BLOCK;
- requested write path outside admission scope -> BLOCK;
- read-only plan without admission -> PASS;
- exact admitted bounded accept-edits -> PASS;
- no consumer may create or mutate a Nexus admission receipt.

## Verification

```bash
uv run pytest -q tests/services/test_agy_dispatch.py tests/services/test_agy_dispatch_fast_failover.py tests/nexus/orchestrator/test_mutation_admission.py
uv run ruff check scripts/ops/nexus-agy-dispatch nexus/orchestrator/mutation_admission.py tests/services/test_agy_dispatch.py tests/services/test_agy_dispatch_fast_failover.py tests/nexus/orchestrator/test_mutation_admission.py
git diff --check
```

DevSpace #364 must separately run its repository-native tests, type checks, and `nexus-certify issue-check --issue 364` before its completion claim.

## Claim ceiling

`SUPPORTED_MANAGED_MUTATION_PATHS_ADMISSION_FENCED_SOURCE_VERIFIED`

No nine-repository integration hard-gate, Gateway deployment, runtime convergence, or universal bypass-prevention claim is permitted by this card.
