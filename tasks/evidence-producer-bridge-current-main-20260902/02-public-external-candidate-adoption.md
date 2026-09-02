# TASK-EPB-003-R1 — Current-main Public External Candidate Adoption

task_id: `TASK-EPB-003-R1`

- Campaign: `CAMPAIGN-EVIDENCE-PRODUCER-BRIDGE-01`
- Mission: `CORE-EVIDENCE-TRUST-CANONICALIZATION-20260902`
- Status: `ACTIVE`
- Source spec: `SPEC-EPB-EXTERNAL-CANDIDATE-ADOPTION-EXEC-001`
- Source spec SHA-256: `9e841f43d63ffc10704f00b4d21b88f9fbf78f3a473839a1409f278a951251a1`
- Requirements: `REQ-001; REQ-007`
- Acceptance: `AC-001; AC-004`
- Exact base/core merge: `1c4f9384a67c61f80d1f11215e9c1ab225b21809`
- Exact base/core tree: `ea8cbcfb051e58f202e825bb29e32d25773b8318`
- Core predecessor: `CORE_EXTERNAL_CANDIDATE_ADOPTION_INTEGRATED_SOURCE_VERIFIED`
- Historical public donor: PR #668 path projection after core commit `913a90900b906f31d18e35efdd853863aad92400`; reference only.
- Execution lane: `GOVERNED`
- Commit/Candidate required: `true`
- Parallel safe: `false`

## Goal

Expose one closed, runtime-bound public `CANDIDATE_ADOPT_EXTERNAL` Gateway/CLI
action that delegates exactly once to the integrated core service and returns
pending-only evidence. It must not duplicate physical verification/state
formation or consume downstream approval/integration authority.

## Required invariants

1. Fresh one-shot Owner effect authority is bound to exact action, runtime,
   root/branch/controller, task/attempt/card, Candidate, base, evidence, and
   request identity.
2. Gateway re-reads controller/root/HEAD after authority resolution and rejects
   drift before delegation.
3. Closed schemas reject missing/extra/unknown or downstream-effect fields.
4. The handler delegates exactly once to the core adoption service; it does not
   verify, commit, form state, or call a worker itself.
5. Output validates exact pending status/receipt and rejects approval,
   integration, push, merge, release, reload, runtime activation, production,
   or public-claim fields/effects.
6. CLI is a thin typed forwarder to the same service contract.

## Allowed paths

- `nexus/contracts/autonomy_goal.py`
- `nexus/contracts/lifecycle_action.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/unified_mcp_gateway.py`
- `scripts/engine/commands/self_hosted_actions.py`
- `scripts/engine/nexus_cli.py`
- `tests/contracts/test_lifecycle_action.py`
- `tests/engine/test_self_hosted_cli.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_standing_grant_store.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`

Maximum changed paths: `11`; deletions: `0`.

## Forbidden scope

- CandidateVerifier/Committer/WorktreeManager or duplicate core verification,
  state, receipt, Planner, Workforce, Product/Evidence, provider/worker logic.
- Candidate rewrite, approval, integration, push, merge, release, reload,
  runtime activation, production, Task4, signing, trust root, public stability.

## Required RED and hostile witnesses

- Current core exposes no public adoption tool/CLI; new positive tests fail for
  the missing closed action, not fixture/import errors.
- expired/replayed/wrong action/runtime/card/Candidate authority;
- root/branch/controller/head drift after authority;
- extra/missing/downstream fields and authority-token result injection;
- multiple/zero core service calls;
- non-pending result or any downstream effect.

## Verification

- `uv run pytest -q tests/contracts/test_lifecycle_action.py tests/engine/test_self_hosted_cli.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/orchestrator/test_standing_grant_store.py tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `uv run ruff check nexus/contracts/autonomy_goal.py nexus/contracts/lifecycle_action.py nexus/orchestrator/self_hosted_task_service.py nexus/orchestrator/unified_mcp_gateway.py scripts/engine/commands/self_hosted_actions.py scripts/engine/nexus_cli.py tests/contracts/test_lifecycle_action.py tests/engine/test_self_hosted_cli.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/orchestrator/test_standing_grant_store.py tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `uv run pyright nexus/contracts/autonomy_goal.py nexus/contracts/lifecycle_action.py nexus/orchestrator/self_hosted_task_service.py nexus/orchestrator/unified_mcp_gateway.py scripts/engine/commands/self_hosted_actions.py scripts/engine/nexus_cli.py`
- `git diff --check`

## Exit and claim ceiling

Independent acceptance must bind exact core dependency/API, base/head/tree/card
hash, full public diff, real Gateway/CLI positive witness, closed-schema hostile
controls, exact service-call cardinality, pending-only output, and no downstream
effect.

Maximum claim:

`PUBLIC_EXTERNAL_CANDIDATE_ADOPTION_CANDIDATE_VERIFIED`

No approval, integration, merge, release, runtime activation, production,
Task4, or public-stability claim.

`AUTO_CHAIN=false`
