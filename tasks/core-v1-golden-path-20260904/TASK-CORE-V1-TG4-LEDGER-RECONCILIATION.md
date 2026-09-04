# TASK-CORE-V1-TG4-LEDGER-RECONCILIATION — Durable ledger and replay fencing

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#763`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `1afae6f51f91563d8476a25c220446eab8b06391b8edd99fb95ea0881828d7ed`
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
- **Execution lane:** `NEXUS_LIFECYCLE_V2`
- **Minimum MCP profile:** `CANDIDATE`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** none

## Goal

Implement append-only SQLite WAL/full-sync receipt history with idempotency, generation CAS, crash recovery, hash links, corruption fail-closed inspection, and optional identity-only signing.

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
- **Required initial verification:** verify TG-3 accepted identity contract and clean isolated source
- **Freshness rule:** re-read TG-3 receipt and ledger schema before retry or acceptance

## MCP execution profile

- **App/server and action snapshot:** Nexus lifecycle MCP snapshot required at execution
- **Exact required actions:** nexus_task_run;nexus_task_status;nexus_task_wait;nexus_task_reconcile;nexus_task_finish
- **Confirmation-required actions:** nexus_task_run;nexus_task_finish
- **Idempotency and attempt rule:** key plus canonical request hash and generation CAS; changed request never reuses entry
- **Reconnect reconciliation:** reconcile durable ledger state before retry after any unknown effect
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner/Campaign controller and CapabilityPlanner
- **Execution authority:** approved Luna worker
- **Verification authority:** independent controller restart/tamper/CAS probes
- **Receipt authority:** ledger carries exact Completion receipts; it cannot change claim ceiling
- **Approval/integration authority:** external Owner-designated authority only

## Allowed scope

- **Read:** product/certification/receipt.py;product/evidence/ingestion.py;tests/product/test_evidence_receipt_hardening.py
- **Edit:** product/certification/receipt.py;product/evidence/ingestion.py
- **Create:** product/ledger.py
- **Delete:** none
- **Maximum touched production files:** 3
- **Maximum touched test files:** 0

## Unknown scan

- **Known facts:** no product-level durable ledger/reconciliation seam is verified.
- **Assumptions requiring verification:** SQLite schema, fsync semantics, key metadata, crash boundaries, and recovery API.
- **Architecture risks:** ledger becoming a truth owner rather than carrier.
- **Evidence risks:** in-memory idempotency or clean shutdown is insufficient.
- **Missing owner decision:** none

## Mandatory source audit

Audit receipt identity, evidence generations, existing hardening tests, durable boundary ordering, corruption/recovery semantics, and signature custody boundary.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Crash at every durable boundary, duplicate key, request drift, stale generation, truncation, reorder, replacement, and key metadata mismatch must fail closed or reconcile.

## Implementation constraints

Append-only WAL/full-sync, transactional CAS, hash-linked entries, external private-key custody, and no signature-based claim elevation.

## GREEN and regression gates

AC-007 and AC-008 pass only with restart/replay/tamper/CAS evidence and exact receipt identity preservation.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG4-01 | TARGET_ROOT | `uv run pytest -qq tests/product/test_evidence_receipt_hardening.py` | receipt durability regression | all tests pass |
| TG4-02 | TARGET_ROOT | `git diff --check` | patch integrity | exit 0 |

## Physical evidence

Capture ledger generation/entry hashes, crash/restart observations, idempotency/CAS outcomes, signer/key metadata, attempt, Candidate commit, and recovery receipt.

## Independent review

Fresh reviewer inspects transaction boundaries, corruption behavior, signing scope, receipt identity, tests, and authority ceiling.

## Exit conditions

- **PASS:** restart/tamper/CAS receipt supports `LOCAL_LEDGER_RECONCILIATION_VERIFIED`.
- **BLOCK:** ambiguous recovery, corruption accepted, duplicate truth, or signature claim elevation.
- **Residual debt:** HTTP integration remains downstream.
- **Next gate:** TG-5 integrates the end-to-end local HTTP tracer.
