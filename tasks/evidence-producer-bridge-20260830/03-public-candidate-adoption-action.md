# TASK-EPB-003 — Public Typed External Candidate Adoption Action

- **Campaign:** `CAMPAIGN-EVIDENCE-PRODUCER-BRIDGE-01`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-EPB-EXTERNAL-CANDIDATE-ADOPTION-EXEC-001`
- **Source spec SHA-256:** `9e841f43d63ffc10704f00b4d21b88f9fbf78f3a473839a1409f278a951251a1`
- **Source groups:** Public typed adoption action
- **Requirements:** `REQ-001; REQ-007`
- **Acceptance:** `AC-001; AC-004`
- **Auto-chain:** `false`
- **Maximum claim:** Adoption capability independently verified; no EPB approval, integration, remote merge, release, production, Task4, or public-stability claim.
- **Depends on:** `TASK-EPB-002`
- **Dependency unlock evidence:** `Exact accepted/integrated core service Candidate SHA, tree, service API, verified receipt, and fresh base HEAD`
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `medium`
- **Execution lane:** `NEXUS_LIFECYCLE_V2`
- **Minimum MCP profile:** `CANDIDATE`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** none

## Goal

Expose the accepted core adoption service through one closed `nexus_candidate_adopt_external` Gateway action and compatible self-hosted CLI action, preserving fresh one-shot Owner binding and unchanged downstream approval/integration gates.

## Observable outcome

Typed fail-closed public external Candidate adoption reaches pending approval only

The real Gateway/CLI surface accepts only the exact typed adoption request, delegates evidence derivation to the accepted core service, returns its durable adoption receipt/status, and rejects downstream authority fields and effects.

## Non-goals

- No new verification, receipt, approval, integration, push, release, activation, Product, Task4, trust-root, or signing authority.
- No arbitrary shell or public trust-this-SHA action.
- No modification of the original EPB Candidate.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| `DEC-001` | immutable subject authority | Preserve the exact original EPB Candidate |
| `DEC-002` | lifecycle separation | Adoption ends at pending approval |
| `DEC-003` | scope ceiling | No Task4, trust-root, release, production, or public-stability expansion |
| `CUR-003` | reproduced public-surface gap | Current Gateway/CLI lacks adoption action |
| `CON-001` | Candidate binding contract | Forward exact service-derived Candidate state and receipt bindings |
| `CON-002` | authority contract | Do not hand-edit state or collapse downstream gates |
| `REQ-001` | implementation requirement | Distinct typed adoption authority |
| `REQ-007` | implementation requirement | Unchanged downstream gates |
| `AC-001` | acceptance witness | Typed authority binding |
| `AC-004` | acceptance witness | Downstream separation |

## Owner decisions

- Owner master authorization SHA-256 `1adad9c3cc0356c6bd7d7babf41bf980664c3ed38253909642b78e4992572133` authorizes same-mission implementation after `TASK-EPB-002` is independently accepted and integrated.
- The public action must remain typed, closed, one-shot, host-bound, and pending-approval-only.

## Source and start state

- **Workspace/root:** REVERIFY_AFTER_DEPENDENCY
- **Branch:** REVERIFY_AFTER_DEPENDENCY
- **Starting HEAD:** REVERIFY_AFTER_DEPENDENCY
- **Dirty baseline:** REVERIFY_AFTER_DEPENDENCY
- **Required initial verification:** bind exact integrated `TASK-EPB-002` Candidate/receipt/service API, Task Card hash, Gateway manifest/schema/permission identity, branch/HEAD/tree, and clean Target
- **Freshness rule:** re-read after dependency integration, any reconnect/reload, HEAD/dirty movement, or Gateway definition change

## MCP execution profile

- **App/server and action snapshot:** refresh after `TASK-EPB-002` integration; implementation uses current governed Candidate actions
- **Exact required actions:** `nexus_task_run; nexus_task_wait; nexus_task_status; nexus_task_reconcile; nexus_task_finish`
- **Confirmation-required actions:** implementation Candidate creation only
- **Idempotency and attempt rule:** stable task ID with fresh attempt/action/idempotency identities; reconcile timeout before retry
- **Reconnect reconciliation:** re-read task state, Candidate, request hash, action/attempt/idempotency identities, Gateway definition, and physical Git state
- **Transport blocker:** none

## Authority map

- **Selection authority:** CapabilityPlanner plus current Workforce Admission
- **Execution authority:** Owner-authorized Primary Controller dispatching one eligible bounded worker after dependency unlock
- **Verification authority:** real Gateway/CLI action tests plus independent controller and reviewer evidence
- **Receipt authority:** accepted core service and existing lifecycle state service
- **Approval/integration authority:** unchanged Primary Controller gates; worker has none

## Allowed scope

- **Read:** `AGENTS.md; tasks/evidence-producer-bridge-20260830/INDEX.md; tasks/evidence-producer-bridge-20260830/03-public-candidate-adoption-action.md; docs/specs/SPEC-EPB-EXTERNAL-CANDIDATE-ADOPTION-EXEC-001.md; nexus/contracts/lifecycle_action.py; nexus/orchestrator/self_hosted_task_service.py; nexus/orchestrator/unified_mcp_gateway.py; scripts/engine/nexus_cli.py`
- **Edit:** `nexus/orchestrator/unified_mcp_gateway.py; scripts/engine/nexus_cli.py; tests/nexus/orchestrator/test_unified_mcp_gateway.py; tests/engine/test_self_hosted_cli.py`
- **Create:** `none`
- **Delete:** `none`
- **Maximum touched production files:** 2
- **Maximum touched test files:** 2

## Unknown scan

- **Known facts:** public surface is absent; core service is the sole evidence/state derivation authority after dependency acceptance.
- **Assumptions requiring verification:** current Gateway schema and CLI adapters can expose the action without broad shell or duplicate semantics.
- **Architecture risks:** public arbitrary SHA import, duplicate validation logic, acceptance/approval collapse, stale runtime identity, downstream side effects.
- **Evidence risks:** mock-only success, handler bypass of service, schema accepting extra authority fields.
- **Missing owner decision:** none

## Mandatory source audit

- Rebind accepted/integrated core service API and receipt schema.
- Inspect complete Gateway tool manifest/handler, action guards, CLI command registry, and current tests.
- Audit all public action names and forbid shadow aliases or generic shell fallback.
- Preserve one-direction dependency into the core service.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Behavioral RED must prove the public Gateway/CLI action is absent, extra fields are rejected, missing one-shot authority cannot invoke the service, and no public caller can supply state/verified receipt/downstream actions as truth.

## Implementation constraints

- Gateway/CLI parse and validate only the closed request envelope, then call the accepted core service.
- Do not duplicate CandidateVerifier, CandidateCommitter, artifact, or state derivation logic.
- Bind current server instance, lifecycle revision, manifest, schema, permission policy, task/card, attempt, Candidate, and evidence identities.
- Return pending-approval state/receipt only; reject or omit approval/integration/push/release/activation behavior.

## GREEN and regression gates

- `AC-001`: exact fresh one-shot adoption authority reaches only the core service for the exact bound Candidate.
- `AC-004`: downstream fields and effects are schema-rejected; resulting state is pending approval only.
- Existing Gateway manifest/freshness, lifecycle approval/integration, CLI registry, and unknown-field tests remain green.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| `CMD-001` | TARGET_ROOT | `uv run pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/engine/test_self_hosted_cli.py` | Public action and regression verification | PASS |
| `CMD-002` | TARGET_ROOT | `uv run ruff check nexus/orchestrator/unified_mcp_gateway.py scripts/engine/nexus_cli.py tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/engine/test_self_hosted_cli.py` | Static lint | PASS |
| `CMD-003` | TARGET_ROOT | `uv run pyright nexus/orchestrator/unified_mcp_gateway.py scripts/engine/nexus_cli.py` | Type verification | 0 errors |
| `CMD-004` | TARGET_ROOT | `git diff --check` | Patch integrity | PASS |

## Physical evidence

- Fresh dependency Candidate/receipt/API identity, Task Card/hash, worktree/head/tree, dispatch/admission/attempt identities.
- Real Gateway and CLI positive witness, closed-schema hostile substitutions, downstream-effect audit, and exact service call binding.
- Full diff/path/deletion/mode audit, Candidate commit/tree/state/verified-receipt hashes, and independent acceptance receipt.

## Independent review

A reviewer distinct from the implementer must inspect dependency identity, full diff, public schema and handler, CLI compatibility, real positive witness, unknown/extra-field rejection, absence of duplicated verification/authority, pending-only state, and no downstream effect. Required disposition: `ACCEPT_CANDIDATE` or exact bounded rejection evidence.

## Exit conditions

- **PASS:** Exact public-action Candidate is committed, all commands/hostile controls pass, dependency remains bound, and independent reviewer returns `ACCEPT_CANDIDATE`.
- **BLOCK:** Dependency drift, generic import, duplicate trust/verification authority, schema widening, downstream effect, forbidden path, or unresolved independent rejection.
- **Residual debt:** Activate the accepted public-action Candidate, then use the canonical action to adopt/approve/integrate the original EPB Candidate.
- **Next gate:** Primary Controller integrates/activates the accepted public action and performs the exact original EPB adoption.
