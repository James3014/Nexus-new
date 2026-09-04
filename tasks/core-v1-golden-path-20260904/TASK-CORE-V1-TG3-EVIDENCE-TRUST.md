# TASK-CORE-V1-TG3-EVIDENCE-TRUST — Evidence Trust Core extraction

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#763`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `1afae6f51f91563d8476a25c220446eab8b06391b8edd99fb95ea0881828d7ed`
- **Source groups:** TG-3 Evidence Trust extraction
- **Requirements:** REQ-008
- **Acceptance:** AC-005
- **Auto-chain:** `false`
- **Maximum claim:** `EVIDENCE_TRUST_BOUNDARY_VERIFIED`
- **Depends on:** TASK-CORE-V1-TG0-FREEZE-RECONCILE;TASK-CORE-V1-TG1-GITHUB-ACQUISITION;TASK-CORE-V1-TG2-PYTHON-PROFILE
- **Dependency unlock evidence:** TG-0 interfaces;TG-1 receipt;TG-2 receipt
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

Make Evidence Trust Core the sole canonical consumer of acquisition and runner evidence, validating identity, provenance, freshness, replay, issuer, and prerequisite separation.

## Observable outcome

canonical trust owner consumes TG-1/TG-2

## Non-goals

No completion reducer duplication, runtime transport, approval, signing authority, merge, or production claim.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-008 | trust behavior | producer/issuer, subject, hashes, freshness, replay, and external prerequisites validate |
| AC-005 | hostile witness | tamper, duplicate, expiry, revoke, reorder, and cross-bind fail closed |

## Owner decisions

DEC-001; DEC-002; DER-001. Evidence Trust is one permanent owner and does not become Completion Core.

## Source and start state

- **Workspace/root:** `REVERIFY_AFTER_DEPENDENCY`
- **Branch:** `REVERIFY_AFTER_DEPENDENCY`
- **Starting HEAD:** `REVERIFY_AFTER_DEPENDENCY`
- **Dirty baseline:** `REVERIFY_AFTER_DEPENDENCY`
- **Required initial verification:** verify TG-0 through TG-2 accepted receipts and clean isolated source
- **Freshness rule:** re-read all upstream receipt identities before run and acceptance

## MCP execution profile

- **App/server and action snapshot:** Nexus lifecycle MCP snapshot required at execution
- **Exact required actions:** nexus_task_run;nexus_task_status;nexus_task_wait;nexus_task_reconcile;nexus_task_finish
- **Confirmation-required actions:** nexus_task_run;nexus_task_finish
- **Idempotency and attempt rule:** stable task with distinct retry attempts; duplicate evidence does not create a second trust result
- **Reconnect reconciliation:** reconcile same attempt before retry
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner/Campaign controller and CapabilityPlanner
- **Execution authority:** approved Luna worker
- **Verification authority:** independent controller hostile ingestion matrix
- **Receipt authority:** Evidence Trust and Completion Core
- **Approval/integration authority:** external Owner-designated authority only

## Allowed scope

- **Read:** product/evidence/ingestion.py;product/adapters/trusted.py;product/evidence/__init__.py;tests/product/test_trusted_evidence_ingestion.py;tests/product/test_trusted_certification_adapter.py
- **Edit:** product/evidence/ingestion.py;product/adapters/trusted.py
- **Create:** none
- **Delete:** none
- **Maximum touched production files:** 2
- **Maximum touched test files:** 0

## Unknown scan

- **Known facts:** donor trust ingestion exists but final owner/external live receipts are incomplete.
- **Assumptions requiring verification:** issuer/auth receipt model and exact upstream contract fields.
- **Architecture risks:** donor adapter becoming a second owner.
- **Evidence risks:** static hashes without authenticated producer/issuer are insufficient.
- **Missing owner decision:** none

## Mandatory source audit

Audit trust ingestion, trusted adapter, source/runner receipt fields, current hostile tests, and all duplicate/replay paths.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Run hostile matrix for tamper, duplicate, expired, revoked, reordered, cross-bound, unauthenticated, stale, and replayed evidence; no harness-only failure counts.

## Implementation constraints

Preserve one Evidence Trust owner, explicit external prerequisites, and Completion Core boundary; never self-assert issuer or elevate claims.

## GREEN and regression gates

AC-005 passes with all hostile classes rejected and valid TG-1/TG-2 evidence accepted with exact provenance.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG3-01 | TARGET_ROOT | `uv run pytest -qq tests/product/test_trusted_evidence_ingestion.py tests/product/test_trusted_certification_adapter.py` | trust hostile regression | all tests pass |
| TG3-02 | TARGET_ROOT | `git diff --check` | patch integrity | exit 0 |

## Physical evidence

Capture upstream receipt hashes, context/profile/bundle/ingestion/external prerequisite hashes, attempt, Candidate commit, hostile matrix, and final trust receipt.

## Independent review

Fresh reviewer verifies sole ownership, provenance, freshness, replay/tamper rejection, upstream bindings, diff, tests, and claim ceiling.

## Exit conditions

- **PASS:** independent receipt supports `EVIDENCE_TRUST_BOUNDARY_VERIFIED`.
- **BLOCK:** missing issuer/prerequisite, cross-bound evidence, or duplicate owner.
- **Residual debt:** durable ledger and HTTP remain downstream.
- **Next gate:** TG-4 may implement ledger/reconciliation after identities freeze.
