# TASK-CORE-V1-TG4-LEDGER-RECONCILIATION — Durable ledger and replay fencing

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#768`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `9ef4b46838251ce86d20d6469901e1f8f02f66ed468655bb446e170ebe90f170`
- **Source groups:** TG-4 Durable ledger/reconciliation
- **Requirements:** REQ-010;REQ-011
- **Acceptance:** AC-007;AC-008
- **Auto-chain:** `false`
- **Maximum claim:** `LOCAL_LEDGER_RECONCILIATION_VERIFIED`
- **Depends on:** TASK-CORE-V1-TG3-EVIDENCE-TRUST
- **Dependency unlock evidence:** TG-3 accepted identity receipt
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

Implement append-only SQLite WAL/full-sync receipt history with idempotency, generation CAS, crash recovery, hash links, corruption fail-closed inspection, and optional identity-only signing over the TG-3 canonical identity envelope and exact Completion receipt.

## Observable outcome

idempotent crash-safe receipt history

## Non-goals

No claim elevation from signatures, no approval/integration, no remote ledger, and no replacement of factual Completion Core.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-010 | durable runtime | ambiguous effects reconcile before retry; stale/replay/generation/CAS fail closed |
| REQ-011 | ledger boundary | receipt history survives restart; signing attests identity only |
| AC-007 | restart witness | duplicate/drift/crash requests create no duplicate truth |
| AC-008 | recovery witness | corruption/truncation/reorder/key mismatch blocks safely |

## Owner decisions

DEC-007; DEC-009. SQLite WAL/full-sync and external private-key custody are binding.

## Source and start state

- **Workspace/root:** `REVERIFY_AFTER_DEPENDENCY`
- **Branch:** `REVERIFY_AFTER_DEPENDENCY`
- **Starting HEAD:** `REVERIFY_AFTER_DEPENDENCY`
- **Dirty baseline:** `REVERIFY_AFTER_DEPENDENCY`
- **Required initial verification:** verify TG-3 accepted identity contract and a clean controller-bound integration HEAD/tree containing the exact accepted TG-3 Candidate and its TG-1/TG-2 ancestry
- **Freshness rule:** re-read TG-3 receipt and ledger schema before retry or acceptance

## MCP execution profile

- **App/server and action snapshot:** not applicable; `DIRECT_DELEGATED` Luna execution under Ready Issue #768
- **Exact required actions:** not applicable
- **Confirmation-required actions:** none
- **Idempotency and attempt rule:** key plus canonical request hash and generation CAS; changed request never reuses entry
- **Reconnect reconciliation:** controller re-reads the same worker/session, filesystem, Git, provider, and durable ledger state before retry after any unknown effect
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner/Campaign controller and CapabilityPlanner
- **Execution authority:** approved Luna worker through the non-Nexus `DIRECT_DELEGATED` control plane
- **Verification authority:** independent controller restart/tamper/CAS probes; worker PASS is not acceptance
- **Receipt authority:** ledger carries exact Completion receipts; it cannot change claim ceiling
- **Approval/integration authority:** external Owner-designated authority only

## Allowed scope

- **Read:** product/certification/receipt.py;product/evidence/ingestion.py;tests/product/test_evidence_receipt_hardening.py
- **Edit:** none
- **Create:** product/ledger.py;tests/product/test_ledger.py
- **Delete:** none
- **Maximum touched production files:** 1
- **Maximum touched test files:** 1

## Unknown scan

- **Known facts:** no product-level durable ledger/reconciliation seam is verified; current receipt and trust objects are process-local.
- **Assumptions requiring verification:** SQLite schema, XDG path, full-sync semantics, key metadata, crash boundaries, recovery API, and external signed-head anchor availability.
- **Architecture risks:** ledger becoming a truth owner rather than a carrier; persisting a hash without a reloadable canonical payload.
- **Evidence risks:** in-memory idempotency, clean shutdown, or arbitrary rollback to an earlier valid state cannot support AC-007/AC-008.
- **Missing owner decision:** none; the bounded persistence/signing contract below is required before implementation.

## Mandatory source audit

Audit receipt identity, TG-3 envelope/generation fields, existing hardening tests, durable boundary ordering, corruption/recovery semantics, multiprocess locking, and signature custody boundary. Confirm the ledger carries trust/completion outputs but never derives a new factual disposition.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Crash at every durable boundary, duplicate key, request drift, stale generation, torn tail, reorder, replacement, multiprocess lock contention, and key metadata mismatch must fail closed or reconcile. A fully valid historical rollback is not detectable without an external signed head anchor; without one, the reader must return `ANCHOR_UNAVAILABLE`/`UNVERIFIABLE`, never claim rollback detection.

## Implementation constraints

Default path is `~/.local/state/nexus-core/ledger.sqlite3` (explicit XDG state override permitted). Configure SQLite `journal_mode=WAL`, `synchronous=FULL`, foreign keys, and `BEGIN IMMEDIATE` for append/CAS. Persist unique idempotency key, canonical request hash, attempt/generation, source snapshot hash, result/receipt hash, sequence, previous-entry hash, entry hash, signer key ID/algorithm/signature, and durable head metadata. Add failpoints before write, after write/before commit, and after commit/before response. External signer receives only canonical digest and returns public key metadata plus signature; private keys never enter Nexus. Signatures attest identity only and never elevate the claim ceiling.

## GREEN and regression gates

AC-007 and AC-008 pass only with restart/replay/tamper/CAS evidence, exact receipt identity preservation, multiprocess contention evidence, and explicit anchor behavior (`VERIFIED` only when an external signed head anchor validates; otherwise `ANCHOR_UNAVAILABLE`/`UNVERIFIABLE`).

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG4-01 | TARGET_ROOT | `uv run pytest -qq tests/product/test_ledger.py tests/product/test_evidence_receipt_hardening.py` | SQLite WAL/restart/CAS/corruption/signing regression plus upstream receipt compatibility | all tests pass |
| TG4-02 | TARGET_ROOT | `git diff --check` | patch integrity | exit 0 |

## Physical evidence

Capture XDG ledger path, schema/PRAGMA values, generation/entry/head hashes, crash/restart observations, idempotency/CAS and multiprocess outcomes, corruption/torn-tail and anchor result, signer/key metadata (never private key), attempt, Candidate commit, and recovery receipt.

## Independent review

Fresh reviewer inspects transaction boundaries, WAL/full-sync/CAS behavior, multiprocess locking, chain/anchor corruption behavior, signing scope and key custody, reloadable receipt identity, exact tests, and authority ceiling.

## Exit conditions

- **PASS:** restart/tamper/CAS receipt supports `LOCAL_LEDGER_RECONCILIATION_VERIFIED`, with anchor availability or explicit `ANCHOR_UNAVAILABLE`/`UNVERIFIABLE` handling.
- **BLOCK:** ambiguous recovery, corruption accepted, duplicate truth, missing chain/head binding, arbitrary rollback treated as detected without an anchor, private-key material crossing the port, or signature claim elevation.
- **Residual debt:** HTTP integration remains downstream.
- **Next gate:** TG-5 may start only from a clean controller-bound integration HEAD/tree containing the exact accepted TG-1 through TG-4 Candidate commits and recorded conflict-free composition.
