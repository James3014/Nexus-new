# TASK-CORE-V1-TG3-EVIDENCE-TRUST — Evidence Trust Core extraction

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#767`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `9ef4b46838251ce86d20d6469901e1f8f02f66ed468655bb446e170ebe90f170`
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
- **Execution lane:** `NON_MCP`
- **Minimum MCP profile:** `not applicable`
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

DEC-001; DEC-002; DER-001. Evidence Trust is one permanent owner and does not become Completion Core. `product/adapters/trusted.py` is compatibility-only and cannot define a second trust owner, reducer, or claim-bearing receipt.

## Source and start state

- **Workspace/root:** `REVERIFY_AFTER_DEPENDENCY`
- **Branch:** `REVERIFY_AFTER_DEPENDENCY`
- **Starting HEAD:** `REVERIFY_AFTER_DEPENDENCY`
- **Dirty baseline:** `REVERIFY_AFTER_DEPENDENCY`
- **Required initial verification:** verify TG-0 through TG-2 accepted receipts and a clean controller-bound integration HEAD/tree containing the exact accepted TG-1 and TG-2 Candidate commits with a recorded conflict-free merge-tree result
- **Freshness rule:** re-read all upstream receipt identities before run and acceptance

## MCP execution profile

- **App/server and action snapshot:** not applicable; `DIRECT_DELEGATED` Luna execution under Ready Issue #767
- **Exact required actions:** not applicable
- **Confirmation-required actions:** none
- **Idempotency and attempt rule:** stable task with distinct retry attempts; duplicate evidence does not create a second trust result
- **Reconnect reconciliation:** controller re-reads the same worker/session, filesystem, Git, provider, and receipt state before retry
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner/Campaign controller and CapabilityPlanner
- **Execution authority:** approved Luna worker through the non-Nexus `DIRECT_DELEGATED` control plane
- **Verification authority:** independent controller hostile ingestion matrix; worker PASS is not acceptance
- **Receipt authority:** Evidence Trust and Completion Core
- **Approval/integration authority:** external Owner-designated authority only

## Allowed scope

- **Read:** product/acquisition/__init__.py;product/acquisition/github.py;product/execution/__init__.py;product/execution/python_runner.py;product/execution/profiles/python-oci-pytest-v1.json;product/execution/profiles/python-oci-pytest-v1.lock;product/evidence/ingestion.py;product/adapters/trusted.py;product/evidence/__init__.py;tests/product/test_github_acquisition.py;tests/product/test_python_runner.py;tests/product/test_trusted_evidence_ingestion.py;tests/product/test_trusted_certification_adapter.py
- **Edit:** product/evidence/ingestion.py;product/adapters/trusted.py;tests/product/test_trusted_evidence_ingestion.py;tests/product/test_trusted_certification_adapter.py
- **Create:** tests/product/test_trusted_evidence_serialization.py (dedicated serializer/loader, external-verifier, and restart-boundary tests)
- **Delete:** none
- **Maximum touched production files:** 2
- **Maximum touched test files:** 3

## Unknown scan

- **Known facts:** donor trust ingestion exists but final owner, durable identity envelope, and externally authenticated issuer receipts are incomplete.
- **Assumptions requiring verification:** exact TG-1/TG-2 receipt fields and the external Ed25519 verifier port contract.
- **Architecture risks:** donor adapter becoming a second owner; weakref-only identities being mistaken for restart-safe receipts.
- **Evidence risks:** static hashes without authenticated producer/issuer, or an envelope that cannot be independently loaded and recomputed, are insufficient.
- **Missing owner decision:** none; verifier-port and envelope fields are implementation contract details bounded below.

## Mandatory source audit

Audit trust ingestion, trusted adapter, source/runner receipt fields, current hostile tests, all duplicate/replay paths, and the exact serializable envelope boundary. Prove `product/evidence/ingestion.py` owns trust decisions and the adapter is compatibility-only.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Run hostile matrix for tamper, duplicate, expired, revoked, reordered, cross-bound, unauthenticated, stale, and replayed evidence; include wrong issuer/key/payload and malformed external-signature cases. Exercise serialize/load/recompute in a fresh process; no harness-only failure counts.

## Implementation constraints

Preserve one Evidence Trust owner, explicit external prerequisites, and Completion Core boundary; never self-assert issuer or elevate claims. Add a canonical identity envelope carrying context/profile/bundle/ingestion/subject/execution/attempt/generation and producer/issuer/external-receipt hashes. Add an injected external Ed25519 verifier port receiving public metadata only; private keys must never enter Nexus.

## GREEN and regression gates

AC-005 passes only when all hostile classes are rejected, valid TG-1/TG-2 evidence is accepted with exact provenance, and the canonical envelope independently reloads/recomputes to the same identity after process restart.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG3-01 | TARGET_ROOT | `uv run pytest -qq tests/product/test_trusted_evidence_ingestion.py tests/product/test_trusted_certification_adapter.py tests/product/test_trusted_evidence_serialization.py` | trust hostile, owner-boundary, external-verifier, and envelope regression | all tests pass |
| TG3-02 | TARGET_ROOT | `git diff --check` | patch integrity | exit 0 |

## Physical evidence

Capture upstream receipt hashes, context/profile/bundle/ingestion/subject/external prerequisite hashes, attempt/generation, verifier/key metadata (never private key material), canonical envelope hash and fresh-process reload result, Candidate commit, hostile matrix, and final trust receipt.

## Independent review

Fresh reviewer verifies sole ownership, provenance, freshness, replay/tamper rejection, external issuer/key/payload verification, serializable envelope reload, upstream bindings, exact diff/test discovery, and claim ceiling.

## Exit conditions

- **PASS:** independent receipt supports `EVIDENCE_TRUST_BOUNDARY_VERIFIED` only with accepted TG-1/TG-2 receipts, a reloadable canonical identity envelope, and an external-verifier result bound to the trust subject.
- **BLOCK:** missing upstream receipt, missing issuer/verifier contract, unverifiable signature, cross-bound evidence, duplicate owner, non-reloadable envelope, or private-key material crossing the port.
- **Residual debt:** durable ledger and HTTP remain downstream.
- **Next gate:** TG-4 may start only from a clean controller-bound integration HEAD/tree containing the exact accepted TG-3 Candidate and its accepted TG-1/TG-2 ancestry.
