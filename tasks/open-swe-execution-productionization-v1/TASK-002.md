# TASK-002 — Portable credential-isolated sandbox qualification

task_id: `TASK-002`

- **Campaign:** `CAMPAIGN-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Status:** `BLOCKED`
- **Source spec:** `SPEC-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Source spec SHA-256:** `17e2b27e2ad57d02cd33fd37d0c7d97a29a1ff14e182d7661b141baf9f925d74`
- **Source groups:** `G2 Portable sandbox qualification`
- **Requirements:** `REQ-005; REQ-007`
- **Acceptance:** `AC-007`
- **Auto-chain:** `false`
- **Maximum claim:** A tested portable sandbox/backend is qualified for bounded Open SWE execution; no activation or default switch.
- **Depends on:** `TASK-001`
- **Dependency unlock evidence:** Independently accepted TASK-001 Candidate with stable adapter/backend contract and exact dependency identities.
- **Task type:** `PROOF`
- **Slicing strategy:** `PROOF_SPIKE`
- **Scope class:** `small`
- **Execution lane:** `NON_MCP`
- **Minimum MCP profile:** `VERIFY`
- **Commit required:** `false`
- **Candidate required:** `false`
- **Parallel safe:** `false`
- **Supersedes:** `none`

## Goal

Qualify one supported non-Seatbelt sandbox/backend for real Open SWE model execution while keeping reusable model/GitHub/controller credential material outside agent-readable execution state.

## Observable outcome

A real model performs bounded repository reading and one bounded disposable execution inside a portable isolated backend; the backend denies out-of-root effects and exposes no reusable controller credential material.

## Non-goals

No production route change, no default switch, no GitHub mutation by the agent, no merge/release/deploy authority, and no Seatbelt-as-portable claim.

## Source lineage

`REQ-005`, `REQ-007`, `AC-007`, `UNK-001`, and accepted TASK-001 contract.

## Owner decisions

No new owner decision required. This card proves an engineering/evidence gate only.

## Source and start state

- **Workspace/root:** disposable proof workspace selected at execution time
- **Branch:** not applicable unless a repository fixture is required
- **Starting HEAD:** accepted TASK-001 integrated/current-main identity must be rebound
- **Dirty baseline:** disposable/clean
- **Required initial verification:** re-read accepted TASK-001 adapter/back-end protocol and current supported sandbox providers
- **Freshness rule:** provider/backend identity, package versions, tool surface, and credential architecture must be bound per run

## MCP execution profile

- **App/server and action snapshot:** not applicable unless DevSpace is used for local fixture execution
- **Exact required actions:** backend-specific read/verify actions determined only after a concrete provider is selected
- **Confirmation-required actions:** none; production credentials/permissions changes are forbidden
- **Idempotency and attempt rule:** each qualification run has one immutable run identity
- **Reconnect reconciliation:** read provider/job state before retry
- **Transport blocker:** no supported portable backend available -> remain BLOCKED

## Authority map

- **Selection authority:** campaign proof gate, not CapabilityPlanner routing
- **Execution authority:** disposable proof environment only
- **Verification authority:** independent coordinator/verifier
- **Receipt authority:** qualification report bound to backend/model/run identity
- **Approval/integration authority:** none

## Allowed scope

- **Read:** accepted TASK-001 adapter contract; current sandbox/backend docs/source; disposable fixture
- **Edit:** `none`
- **Create:** disposable proof artifacts only, outside production source
- **Delete:** disposable proof artifacts only under their own root
- **Maximum touched production files:** `0`
- **Maximum touched test files:** `0`

## Unknown scan

- **Known facts:** Seatbelt qualified only macOS; pilot showed controller-side model call and no GitHub credential inside agent sandbox.
- **Assumptions requiring verification:** at least one portable backend exposes sufficient isolation without placing reusable credentials in agent scope.
- **Architecture risks:** provider proxy may still leak credentials or host authority.
- **Evidence risks:** static docs are insufficient; must run real backend/model.
- **Missing owner decision:** `none`

## Mandatory source audit

Inspect the exact backend credential flow, sandbox process boundary, model invocation ownership, file/network capability policy, and logs/receipts before executing a proof.

## Start-state classification

`PROOF_ONLY_NO_DEFECT_CLAIM`

## RED or existing-guard proof

Current known state is insufficient because only macOS Seatbelt has a physical qualification witness. Portable backend remains unproven.

## Implementation constraints

No production mutation. Do not place reusable credentials in agent-readable environment/filesystem/process arguments. Do not weaken capability isolation to make the proof pass.

## GREEN and regression gates

`AC-007` only: real model execution inside a portable isolated backend with controller-side credentials and denied untrusted capability expansion.

## Mandatory command manifest

Commands/provider actions are intentionally `UNVERIFIED` until a concrete backend is selected. This card remains BLOCKED rather than inventing an execution command.

## Physical evidence

Backend/version, model/provider identity, run ID, sandbox root, executable tool inventory, isolation probes, credential visibility classifications without values, and terminal result.

## Independent review

Fresh reviewer verifies physical isolation and that the evidence does not depend only on provider documentation or model self-report.

## Exit conditions

- **PASS:** one portable backend satisfies AC-007 with real execution and independent review.
- **BLOCK:** no backend available, credentials agent-readable, capability escape possible, or only documentation/static evidence exists.
- **Residual debt:** multi-tenant quota/resource accounting may remain outside this V1 activation gate unless it affects chosen deployment mode.
- **Next gate:** TASK-004 still requires TASK-003 as well; no auto-chain.
