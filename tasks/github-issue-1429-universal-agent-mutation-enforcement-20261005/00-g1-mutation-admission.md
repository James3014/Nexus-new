# Task Card: Issue #1429 universal agent mutation enforcement — G1 admission

artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: issue-1429-universal-agent-mutation-enforcement-g1
attempt_id: attempt-1429-g1-admission
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
- Architecture parent: `James3014/Nexus-new#1349`
- Owner request: enforce Nexus mutation admission plus Core completion across all canonical repositories without restoring universal Core mutation sessions.

## Objective

Implement the Nexus-owned, transport-neutral mutation admission and its trusted
integration validator for the canonical repository set.

This card owns the **G1 source contract only**. It does not itself enable
repository rulesets, deploy the Gateway, grant merge/release authority, or claim
that OS-level raw filesystem mutation is impossible.

## Architecture boundary

- Nexus MCP / Nexus-new owns admission, lane/authority identity and integration policy.
- `nexus-core` remains Evidence Trust + Completion only.
- DevSpace, RDC, CLI, GitHub and delegated agents remain execution transports.
- `DIRECT_CANONICAL` and `DIRECT_DELEGATED` stay transport-neutral and do not require a Core mutation session.
- Do not create a second Router, operation database, Candidate authority or verifier.

## Allowed files

- `nexus/orchestrator/mutation_admission.py`
- `nexus/orchestrator/unified_mcp_gateway.py`
- `scripts/ops/nexus_mutation_integration_gate.py`
- `tests/nexus/orchestrator/test_mutation_admission.py`
- `docs/testing/test_impact_map.md`
- `AGENTS.md`

## Required behavior

1. Admission is durable under the existing canonical self-hosted state root.
2. Admission binds exact repository, current default-branch base SHA, operation identity, lane, authority and allowed paths.
3. Direct admission requires explicit Owner-inline authority; governed admission requires a tracked Task Card.
4. Reusing an operation identity with widened/different scope fails closed.
5. Gateway re-observes the repository default-branch head before issuing admission; caller-supplied stale base fails closed.
6. The admission receipt is transport-neutral and exposes no route, execution, verification, acceptance, merge, release, deploy or production authority.
7. A trusted integration validator binds exact admission hash to exact PR base/head and changed paths, and blocks scope escape.
8. Core completion remains a separate required evidence contract.

## Verification

```bash
uv run pytest -q tests/nexus/orchestrator/test_mutation_admission.py tests/nexus/orchestrator/test_unified_mcp_gateway.py
uv run ruff check nexus/orchestrator/mutation_admission.py nexus/orchestrator/unified_mcp_gateway.py scripts/ops/nexus_mutation_integration_gate.py tests/nexus/orchestrator/test_mutation_admission.py
uv run pyright nexus/orchestrator/mutation_admission.py nexus/orchestrator/unified_mcp_gateway.py scripts/ops/nexus_mutation_integration_gate.py
git diff --check
```

## Negative controls

- stale base SHA -> BLOCK;
- non-canonical repository -> BLOCK;
- same operation id with different scope -> BLOCK;
- governed admission without Task Card -> BLOCK;
- tampered receipt hash -> BLOCK;
- PR changed paths outside admitted scope -> BLOCK;
- admission alone never proves Core completion or merge readiness.

## Claim ceiling

`NEXUS_MUTATION_ADMISSION_G1_SOURCE_VERIFIED`

No deployment, ruleset enforcement, universal bypass prevention, release or production claim is permitted by this card.
