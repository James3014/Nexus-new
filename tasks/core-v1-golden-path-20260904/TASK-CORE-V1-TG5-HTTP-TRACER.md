# TASK-CORE-V1-TG5-HTTP-TRACER — Canonical local HTTP real-PR tracer

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#763`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `1afae6f51f91563d8476a25c220446eab8b06391b8edd99fb95ea0881828d7ed`
- **Source groups:** TG-0 Boundary/version/crosswalk freeze;TG-1 Live GitHub acquisition;TG-2 Python profile;TG-3 Evidence Trust extraction;TG-4 Durable ledger/reconciliation;TG-5 HTTP tracer bullet
- **Requirements:** REQ-003;REQ-004;REQ-007;REQ-008;REQ-009;REQ-010;REQ-011;REQ-012
- **Acceptance:** AC-002;AC-004;AC-005;AC-006;AC-007;AC-008;AC-009;AC-014
- **Auto-chain:** `false`
- **Maximum claim:** `REAL_PR_TRACER_BULLET_VERIFIED`
- **Depends on:** TASK-CORE-V1-TG1-GITHUB-ACQUISITION;TASK-CORE-V1-TG2-PYTHON-PROFILE;TASK-CORE-V1-TG3-EVIDENCE-TRUST;TASK-CORE-V1-TG4-LEDGER-RECONCILIATION
- **Dependency unlock evidence:** TG-1 receipt;TG-2 receipt;TG-3 receipt;TG-4 receipt
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

Expose the four-endpoint loopback bearer-authenticated HTTP contract and complete one real PR through acquisition, runner, trust, completion, ledger, and inspectable receipt.

## Observable outcome

real PR to inspectable receipt

## Non-goals

No remote control plane, mutation, client duplication, approval, merge, deployment, release, production, or Stable claim.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-003 | product journey | exactly real PR through inspectable receipt, read-only |
| REQ-004 | acquisition seam | authenticated immutable PR snapshot remains exact |
| REQ-007 | runner seam | only adequate deterministic oracle can certify |
| REQ-008 | trust seam | only authenticated, provenance-bound evidence is consumed |
| REQ-009 | completion boundary | factual tri-state and bounded disposition |
| REQ-010 | retry seam | idempotency/CAS/reconciliation survive interruption |
| REQ-011 | ledger seam | receipt history recovers without claim elevation |
| REQ-012 | transport owner | HTTP canonical; clients remain thin |
| AC-002 | acquisition seam | exact live subject survives end-to-end |
| AC-004 | runner seam | oracle truth remains bound |
| AC-005 | trust seam | hostile evidence cannot certify |
| AC-006 | claim seam | caller cannot mint higher truth |
| AC-007 | retry seam | idempotency/CAS/reconciliation survive interruption |
| AC-008 | ledger seam | receipt history recovers |
| AC-009 | tracer seam | four endpoints expose canonical semantics |
| AC-014 | journey witness | one real PR traverses all stages without mutation |

## Owner decisions

DEC-002; DEC-004; DEC-007; DEC-009.

## Source and start state

- **Workspace/root:** `REVERIFY_AFTER_DEPENDENCY`
- **Branch:** `REVERIFY_AFTER_DEPENDENCY`
- **Starting HEAD:** `REVERIFY_AFTER_DEPENDENCY`
- **Dirty baseline:** `REVERIFY_AFTER_DEPENDENCY`
- **Required initial verification:** verify TG-1 through TG-4 acceptance receipts and clean isolated source
- **Freshness rule:** re-read all upstream contracts, source revision, and local HTTP permission/auth state before each E2E run

## MCP execution profile

- **App/server and action snapshot:** Nexus lifecycle MCP snapshot required at execution
- **Exact required actions:** nexus_task_run;nexus_task_status;nexus_task_wait;nexus_task_reconcile;nexus_task_finish
- **Confirmation-required actions:** nexus_task_run;nexus_task_finish
- **Idempotency and attempt rule:** canonical request hash plus idempotency key; exact replay returns same run/receipt, drift reconciles and fails closed
- **Reconnect reconciliation:** status/reconcile same request attempt before retry
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner/Campaign controller and CapabilityPlanner
- **Execution authority:** approved Luna worker
- **Verification authority:** independent controller live local E2E
- **Receipt authority:** Evidence Trust, Completion Core, and carrying ledger
- **Approval/integration authority:** external Owner-designated authority only

## Allowed scope

- **Read:** product/adapters/github.py;product/execution/__init__.py;product/evidence/ingestion.py;product/certification/receipt.py;tests/product
- **Edit:** product/adapters/github.py;product/execution/__init__.py;product/evidence/ingestion.py;product/certification/receipt.py
- **Create:** product/runtime.py
- **Delete:** none
- **Maximum touched production files:** 5
- **Maximum touched test files:** 0

## Unknown scan

- **Known facts:** current execution exports pure ports and no canonical HTTP runtime.
- **Assumptions requiring verification:** loopback binding, bearer token source, endpoint schemas, lifecycle behavior, and live GitHub credentials.
- **Architecture risks:** runtime could duplicate trust/completion logic.
- **Evidence risks:** simulated HTTP or caller-supplied snapshots are insufficient.
- **Missing owner decision:** none

## Mandatory source audit

Audit upstream contracts and receipts, protocol/schema axes, auth/loopback policy, ledger identity, all client boundaries, and real-PR E2E test seams.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Negative E2E cases cover idempotency/request/version drift, interrupted request, direct caller result, stale source, inadequate oracle, and unknown effect.

## Implementation constraints

Bind only to 127.0.0.1 with per-install bearer token; retain four endpoints; delegate truth to the two cores; persist/reconcile durable state; never mutate PR.

## GREEN and regression gates

AC-002 and AC-004 through AC-009 pass only on a live local E2E from authenticated real PR to receipt and all negative controls.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG5-01 | TARGET_ROOT | `uv run pytest -qq tests/product` | product and tracer regression | all tests pass |
| TG5-02 | TARGET_ROOT | `git diff --check` | patch integrity | exit 0 |

## Physical evidence

Capture loopback/auth configuration, canonical request, idempotency/run/acquisition/evidence/result/response/receipt hashes, live E2E, interruption/replay outcomes, Candidate commit, and final state.

## Independent review

Fresh reviewer validates endpoint contract, auth/loopback, core delegation, exact real-PR subject, durable reconciliation, negative controls, tests, and claim ceiling.

## Exit conditions

- **PASS:** live local E2E supports `REAL_PR_TRACER_BULLET_VERIFIED`.
- **BLOCK:** missing live acquisition, bypassed core, duplicate truth, auth drift, or unknown effect.
- **Residual debt:** clients/package and cross-repo value remain.
- **Next gate:** TG-6 and TG-7 may become parallel-ready; neither auto-activates.
