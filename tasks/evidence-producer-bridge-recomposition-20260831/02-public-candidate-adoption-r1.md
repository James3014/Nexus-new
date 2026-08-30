# TASK-EPB-003-R1 — Public Typed External Candidate Adoption Successor

- **Campaign:** `CAMPAIGN-EVIDENCE-PRODUCER-BRIDGE-01`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-EPB-EXTERNAL-CANDIDATE-ADOPTION-EXEC-001`
- **Source spec SHA-256:** `9e841f43d63ffc10704f00b4d21b88f9fbf78f3a473839a1409f278a951251a1`
- **Source groups:** Public typed adoption action
- **Requirements:** `REQ-001; REQ-007`
- **Acceptance:** `AC-001; AC-004`
- **Auto-chain:** `false`
- **Maximum claim:** Adoption capability independently verified; no EPB approval, integration, remote merge, release, production, Task4, or public-stability claim.
- **Depends on:** `TASK-EPB-002-R1`
- **Dependency unlock evidence:** `Exact accepted core successor SHA, tree, service API, validation receipt, independent acceptance receipt, and fresh base HEAD`
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `medium`
- **Execution lane:** `NEXUS_LIFECYCLE_V2`
- **Minimum MCP profile:** `CANDIDATE`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** `TASK-EPB-003`

## Goal

Recompose the settled closed Gateway/CLI adoption action on the fresh accepted core successor.

## Observable outcome

Typed fail-closed public external Candidate adoption reaches pending approval only

## Non-goals

No duplicate verifier/state authority, approval, integration, push, merge, reload, release, production, Task4, signing, trust root, or Product Candidate modification.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| `REQ-001` | public action | Closed typed one-shot runtime-bound adoption request |
| `REQ-007` | downstream separation | Pending-only result; approval/integration unchanged |
| `AC-001` | witness | Exact authority/runtime/service delegation |
| `AC-004` | witness | Extra/downstream fields and effects rejected |

## Owner decisions

Owner mission authority permits this successor only after exact independent core acceptance. It creates no downstream authority.

## Source and start state

- **Workspace/root:** `REVERIFY_AFTER_DEPENDENCY`
- **Branch:** `REVERIFY_AFTER_DEPENDENCY`
- **Starting HEAD:** `REVERIFY_AFTER_DEPENDENCY`
- **Dirty baseline:** `REVERIFY_AFTER_DEPENDENCY`
- **Required initial verification:** bind exact accepted core SHA/tree/receipt/API and current Task Card hash
- **Freshness rule:** re-read after dependency, HEAD/status/tool/runtime movement

## MCP execution profile

- **App/server and action snapshot:** refresh after core acceptance
- **Exact required actions:** `nexus_task_run; nexus_task_wait; nexus_task_status; nexus_task_reconcile; nexus_task_finish`
- **Confirmation-required actions:** Candidate commit only
- **Idempotency and attempt rule:** fresh successor attempt; reconcile before retry
- **Reconnect reconciliation:** re-read task, Candidate, action/attempt/idempotency, manifest/schema/permission, and Git state
- **Transport blocker:** none

## Authority map

- **Selection authority:** Primary Controller
- **Execution authority:** one bounded Luna implementation worker after dependency unlock
- **Verification authority:** real Gateway/CLI tests and independent reviewer
- **Receipt authority:** accepted core service and existing lifecycle state service
- **Approval/integration authority:** none in this card

## Allowed scope

- **Read:** approved spec; this bundle; accepted core successor; historical `a20712a5..fc402296` public delta
- **Edit:** `nexus/contracts/autonomy_goal.py`; `nexus/contracts/lifecycle_action.py`; `nexus/orchestrator/self_hosted_task_service.py`; `nexus/orchestrator/unified_mcp_gateway.py`; `scripts/engine/commands/self_hosted_actions.py`; `scripts/engine/nexus_cli.py`; `tests/contracts/test_lifecycle_action.py`; `tests/engine/test_self_hosted_cli.py`; `tests/nexus/orchestrator/test_self_hosted_task_service.py`; `tests/nexus/orchestrator/test_standing_grant_store.py`; `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- **Create:** none
- **Delete:** none
- **Maximum touched production files:** 6
- **Maximum touched test files:** 5

## Unknown scan

- **Known facts:** historical public delta is linear and accepted only against rejected core dependency.
- **Assumptions requiring verification:** path-scoped public delta applies without duplicating or weakening fresh core behavior.
- **Architecture risks:** duplicate authority, schema widening, stale runtime identity, downstream effect.
- **Evidence risks:** baseline CLI/static debt misclassified.
- **Missing owner decision:** none

## Mandatory source audit

Rebind exact core API; inspect action enum, Gateway manifest/schema/handler, standing-grant effect binding, CLI adapter/registry, result validation, and hostile tests.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Before applying the public delta, the accepted core successor must expose no public adoption action. Closed-schema/downstream hostile tests must fail for the intended missing behavior, not fixture/import errors.

## Implementation constraints

Apply only the public semantic delta, delegate exactly once to the accepted core service, derive runtime truth inside trusted code, and project pending-only output. Never duplicate verification or state formation.

## GREEN and regression gates

Exact public path scope; real Gateway/CLI positive witness; extra/missing/stale/runtime/downstream fields rejected; no approval/integration/reload/push/release/Task4 effect.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| `CMD-001` | TARGET_ROOT | `/Users/jameschen/Workspace/Nexus-new/.venv/bin/pytest -q tests/contracts/test_lifecycle_action.py tests/engine/test_self_hosted_cli.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/orchestrator/test_standing_grant_store.py tests/nexus/orchestrator/test_unified_mcp_gateway.py` | Public action and hostile regressions | PASS or exact-base-identical baseline only |
| `CMD-002` | TARGET_ROOT | `/Users/jameschen/Workspace/Nexus-new/.venv/bin/ruff check nexus/contracts/autonomy_goal.py nexus/contracts/lifecycle_action.py nexus/orchestrator/self_hosted_task_service.py nexus/orchestrator/unified_mcp_gateway.py scripts/engine/commands/self_hosted_actions.py scripts/engine/nexus_cli.py tests/contracts/test_lifecycle_action.py tests/engine/test_self_hosted_cli.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/orchestrator/test_standing_grant_store.py tests/nexus/orchestrator/test_unified_mcp_gateway.py` | Static lint | Zero introduced/touched-line diagnostics; baseline classified |
| `CMD-003` | TARGET_ROOT | `/Users/jameschen/Workspace/Nexus-new/.venv/bin/pyright nexus/contracts/autonomy_goal.py nexus/contracts/lifecycle_action.py nexus/orchestrator/self_hosted_task_service.py nexus/orchestrator/unified_mcp_gateway.py scripts/engine/commands/self_hosted_actions.py scripts/engine/nexus_cli.py` | Type verification | Zero introduced/touched-line diagnostics; baseline classified |
| `CMD-004` | TARGET_ROOT | `git diff --check` | Patch integrity | PASS |

## Physical evidence

Exact core dependency, Task Card/hash, Candidate commit/tree/diff, runtime manifests, paths/deletions/modes, tests/diagnostics, validation and independent acceptance receipts.

## Independent review

A fresh reviewer must inspect dependency identity, complete public diff, schema/handler/CLI, service-call cardinality, pending-only semantics, hostile controls, and no downstream effect. Required disposition: `ACCEPT_CANDIDATE` or exact rejection.

## Exit conditions

- **PASS:** scoped successor committed; gates pass or are exact-base-only; independent reviewer returns `ACCEPT_CANDIDATE`.
- **BLOCK:** dependency drift, generic import, duplicate authority, schema widening, downstream effect, forbidden path, or unresolved rejection.
- **Residual debt:** Product Candidate adoption/approval, local integration, GitHub merge, post-merge verification.
- **Next gate:** Activate the accepted public successor and adopt exact Product successor `d70cdce975ca8394606d54d1492506cf5e392e4d`.
