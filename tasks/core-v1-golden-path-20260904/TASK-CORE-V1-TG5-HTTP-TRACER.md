# TASK-CORE-V1-TG5-HTTP-TRACER — Canonical local HTTP real-PR tracer

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#769`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `9ef4b46838251ce86d20d6469901e1f8f02f66ed468655bb446e170ebe90f170`
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
- **Execution lane:** `NON_MCP`
- **Minimum MCP profile:** `not applicable`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** none

## Goal

Expose the four-endpoint loopback bearer-authenticated HTTP contract and complete the controlled `James3014/Nexus-new#635` PR through acquisition, runner, trust, completion, ledger, and inspectable receipt.

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
- **Required initial verification:** verify TG-1 through TG-4 accepted receipts and a clean controller-bound integration HEAD/tree containing exactly their accepted Candidate commits with recorded conflict-free composition, then verify loopback port availability, token-file permissions, Docker/runner availability, and controlled PR #635 read access
- **Freshness rule:** re-read all upstream contracts, source revision, and local HTTP permission/auth state before each E2E run

## MCP execution profile

- **App/server and action snapshot:** not applicable; `DIRECT_DELEGATED` Luna execution under Ready Issue #769
- **Exact required actions:** not applicable
- **Confirmation-required actions:** none
- **Idempotency and attempt rule:** canonical request hash plus idempotency key; exact replay returns same run/receipt, drift reconciles and fails closed
- **Reconnect reconciliation:** status/reconcile same request attempt before retry
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner/Campaign controller and CapabilityPlanner
- **Execution authority:** approved Luna worker through the non-Nexus `DIRECT_DELEGATED` control plane
- **Verification authority:** independent controller live local E2E; worker PASS is not acceptance
- **Receipt authority:** Evidence Trust, Completion Core, and carrying ledger
- **Approval/integration authority:** external Owner-designated authority only

## Allowed scope

- **Read:** product/acquisition;product/adapters/github.py;product/execution;product/evidence/ingestion.py;product/certification/receipt.py;product/ledger.py;tests/product
- **Edit:** none
- **Create:** product/runtime/__init__.py;product/runtime/schemas.py;product/runtime/auth.py;product/runtime/http.py;product/runtime/service.py;tests/product/test_http_runtime.py;tests/product/test_http_e2e.py
- **Delete:** none
- **Maximum touched production files:** 5
- **Maximum touched test files:** 2

## Unknown scan

- **Known facts:** current execution exports pure ports and no canonical HTTP runtime.
- **Assumptions requiring verification:** endpoint schemas/statuses, loopback binding, bearer token source, request limits/timeouts, lifecycle behavior, durable CAS/reconciliation, and live GitHub credentials.
- **Architecture risks:** runtime could duplicate trust/completion logic.
- **Evidence risks:** simulated HTTP or caller-supplied snapshots are insufficient.
- **Missing owner decision:** none

## Canonical HTTP contract

- **Bind:** `127.0.0.1:8767` by default; wildcard, `0.0.0.0`, IPv6-any, and non-loopback binds are rejected before listening.
- **Authentication:** per-install bearer token is read only from `$XDG_CONFIG_HOME/nexus-core/token`, falling back to `~/.config/nexus-core/token`; the file must be regular, mode `0600`, non-empty, and never enters a receipt. Missing, overlong, malformed, or mismatched tokens return the same unauthorised error without invoking a core.
- **Endpoints:** `POST /v1/certifications`, `GET /v1/certifications/{request_id}`, `GET /v1/certifications/{request_id}/receipt`, and `POST /v1/receipts/verify`.
- **Request/response:** schemas must explicitly carry protocol version and implementation schema as separate axes, repository/PR/base/head/tree/diff identities, Acceptance Contract and Verification Plan hashes, `python-oci-pytest-v1`, idempotency key, and the separated acquisition/execution/evidence/verification/disposition/receipt/claim-ceiling sections. Unknown fields, oversized bodies, invalid IDs, unsupported methods, and malformed JSON fail with a documented error envelope and never create durable state.
- **Limits/timeouts:** request-body and path limits, connect/read/worker timeouts, and bounded result size are fixed in the schema module and asserted by tests; timeout/unknown-effect is `UNVERIFIABLE` and reconciles before retry.
- **Durability:** exact `(idempotency_key, canonical_request_hash)` replay returns the original run/receipt; same key with changed request, stale generation/source, or changed subject fails closed through SQLite generation CAS and reconciliation.
- **Receipt verification:** `/verify` returns `ENVELOPE_ONLY` unless stored original inputs allow full recomputation; it cannot elevate the claim ceiling.

## Exact upstream identity tuple

TG5 may run only after accepted TG1–TG4 receipts bind this exact tuple: `(repository_owner, repository_name, pr_number, base_sha, head_sha, tree_sha, diff_hash, changed_paths, contract_hash, plan_hash, environment_hash, source_revision, source_tree, attempt_id, generation)`. Missing, duplicate, or cross-bound tuple members are a hard fail.

## Controlled real-PR fixture

Use the pre-existing read-only fixture `James3014/Nexus-new#635`; immediately before the run, record and independently re-read its full base/head/tree/diff/check identities. The Candidate PR under implementation must not be used as its own fixture unless the controller records a separate Owner-approved fixture decision.

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
| TG5-01 | TARGET_ROOT | `uv run pytest -qq tests/product/test_http_runtime.py tests/product/test_http_e2e.py` | runtime, auth, schema, replay, and tracer regression | all tests pass |
| TG5-02 | TARGET_ROOT | `NEXUS_CORE_HTTP_PORT=8767 uv run pytest -qq tests/product/test_http_e2e.py -m live --run-live` | authenticated `James3014/Nexus-new#635` acquisition-to-receipt E2E and negative controls | live E2E and all hostile cases pass |
| TG5-03 | TARGET_ROOT | `git diff --check` | patch integrity | exit 0 |

## Physical evidence

Capture loopback/auth configuration (including token path/mode without token contents), canonical request, exact TG1–TG4 tuple and receipt hashes, idempotency/run/acquisition/evidence/result/response/receipt hashes, live #635 E2E, interruption/replay outcomes, Candidate commit, and final state.

## Independent review

Fresh reviewer validates endpoint contract, auth/loopback, core delegation, exact real-PR subject, durable reconciliation, negative controls, tests, and claim ceiling.

## Exit conditions

- **PASS:** live local E2E for the bound #635 fixture supports `REAL_PR_TRACER_BULLET_VERIFIED`.
- **BLOCK:** missing live acquisition, missing TG1–TG4 tuple member, bypassed core, duplicate truth, auth/loopback drift, schema/limit ambiguity, or unknown effect.
- **Residual debt:** clients/package and cross-repo value remain.
- **Next gate:** after controller acceptance, TG-6 and TG-7 are parallel-ready; neither auto-activates.
