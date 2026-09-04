# TASK-CORE-V1-TG6-CLIENTS-PACKAGE — Thin clients and operator journey

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#763`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `1afae6f51f91563d8476a25c220446eab8b06391b8edd99fb95ea0881828d7ed`
- **Source groups:** TG-6 Thin clients/package
- **Requirements:** REQ-012;REQ-013
- **Acceptance:** AC-011;AC-012
- **Auto-chain:** `false`
- **Maximum claim:** `OPERATOR_JOURNEY_VERIFIED`
- **Depends on:** TASK-CORE-V1-TG5-HTTP-TRACER
- **Dependency unlock evidence:** TG-5 accepted receipt
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `EXPAND_CONTRACT`
- **Scope class:** `medium`
- **Execution lane:** `NEXUS_LIFECYCLE_V2`
- **Minimum MCP profile:** `CANDIDATE`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** none

## Goal

Route CLI, MCP, and GitHub Action through canonical HTTP and provide a reproducible certification-first install, upgrade, and rollback journey.

## Observable outcome

client parity and clean install journey

## Non-goals

No client-local trust/completion logic, legacy deletion, release, deployment, production, Stable, or public value claim.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-012 | client behavior | all clients call HTTP and preserve canonical semantics |
| REQ-013 | packaging | install/quickstart/upgrade/rollback preserve receipts |
| AC-011 | canary witness | no semantic divergence or client-only minting |
| AC-012 | journey witness | clean install and rollback preserve readable history |

## Owner decisions

DEC-004; DEC-007; DEC-010.

## Source and start state

- **Workspace/root:** `REVERIFY_AFTER_DEPENDENCY`
- **Branch:** `REVERIFY_AFTER_DEPENDENCY`
- **Starting HEAD:** `REVERIFY_AFTER_DEPENDENCY`
- **Dirty baseline:** `REVERIFY_AFTER_DEPENDENCY`
- **Required initial verification:** verify TG-5 accepted live HTTP receipt and clean install environment
- **Freshness rule:** re-read TG-5 contract, package metadata, protocol/ledger versions, and client artifacts before each canary

## MCP execution profile

- **App/server and action snapshot:** Nexus lifecycle MCP snapshot required at execution
- **Exact required actions:** nexus_task_run;nexus_task_status;nexus_task_wait;nexus_task_reconcile;nexus_task_finish
- **Confirmation-required actions:** nexus_task_run;nexus_task_finish
- **Idempotency and attempt rule:** each canary run binds canonical request and client artifact; exact replay returns same receipt
- **Reconnect reconciliation:** reconcile same attempt before retry
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner/Campaign controller and CapabilityPlanner
- **Execution authority:** approved Luna worker
- **Verification authority:** independent controller conformance/install/rollback checks
- **Receipt authority:** canonical HTTP/Core/ledger surfaces
- **Approval/integration authority:** external Owner-designated authority only

## Allowed scope

- **Read:** README.md;pyproject.toml;product;tests/product
- **Edit:** README.md;pyproject.toml
- **Create:** product/clients.py;tests/product/test_client_conformance.py
- **Delete:** none
- **Maximum touched production files:** 3
- **Maximum touched test files:** 1

## Unknown scan

- **Known facts:** README/package remain orchestration-first and no client conformance path is verified.
- **Assumptions requiring verification:** package entry point, MCP/Action surfaces, dependency lock, upgrade format, and rollback reader.
- **Architecture risks:** client logic may become parallel semantic owner.
- **Evidence risks:** local unit parity is not install/rollback canary evidence.
- **Missing owner decision:** none

## Mandatory source audit

Audit package metadata, README quickstart, client entry points, canonical HTTP contract, protocol/ledger versions, and legacy compatibility behavior.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Negative canaries replace HTTP response, attempt receipt minting, use incompatible ledger/protocol, and omit prior reader; each must fail closed.

## Implementation constraints

Clients transport only; package remains local-first; upgrade preserves receipt history; rollback restores prior reader/runtime; no legacy deletion.

## GREEN and regression gates

AC-011 and AC-012 pass with all three client paths hitting canonical HTTP and clean install/upgrade/rollback canaries.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG6-01 | TARGET_ROOT | `uv run pytest -qq tests/product` | client/package regression | all tests pass |
| TG6-02 | TARGET_ROOT | `git diff --check` | patch integrity | exit 0 |

## Physical evidence

Capture package/artifact, environment, protocol/ledger, canonical request/response, client parity, install, upgrade, rollback, Candidate, and canary hashes.

## Independent review

Fresh reviewer checks thinness, parity, package reproducibility, compatibility, rollback, receipt readability, tests, and claim ceiling.

## Exit conditions

- **PASS:** canaries support `OPERATOR_JOURNEY_VERIFIED`.
- **BLOCK:** semantic divergence, missing rollback reader, or incompatible history.
- **Residual debt:** representative corpus and value remain.
- **Next gate:** TG-8 may consume TG-6 and TG-7 evidence after external selection.
