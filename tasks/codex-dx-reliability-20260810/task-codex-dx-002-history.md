# TASK-CODEX-DX-002-HISTORY — Create truthful Codex and GitHub history coverage receipts

- **Campaign:** `CAMPAIGN-CODEX-DX-RELIABILITY-20260810`
- **Status:** `ACTIVE`
- **Source spec:** `SPEC-CODEX-DX-RELIABILITY-20260810`
- **Source spec SHA-256:** `ed2b76c259ca028cc13e136d58ed7129a970aeb19c7c1901d7a662918054f870`
- **Source groups:** evidence-inventory
- **Requirements:** REQ-001
- **Acceptance:** AC-001
- **Auto-chain:** `false`
- **Maximum claim:** coverage-bounded taxonomy
- **Depends on:** none
- **Dependency unlock evidence:** none
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `small`
- **Execution lane:** `NON_MCP`
- **Minimum MCP profile:** `not applicable`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** `none`

## Goal

Create a versioned read-only history receipt schema and collector contract that records returned items, pagination, per-item reads, taxonomy, snapshot identity, and transport gaps without converting unavailable history into zero failures.

## Observable outcome

versioned history coverage receipt with honest transport gaps

## Non-goals

No GitHub or Codex mutation, no transport retry loop, no invented task counts, no local-heal receipt overloading, and no claim that currently unavailable task history was analyzed.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-001 | binding requirement | Preserve exact source identity, behavior, negative control, and claim ceiling. |
| AC-001 | acceptance witness | Preserve exact source identity, behavior, negative control, and claim ceiling. |

## Owner decisions

DEC-001 defines the full Codex DX product outcome. DEC-003 authorizes continued work with incomplete history explicitly labeled. DEC-004 requires a clean isolated governed Target. No worker approval, integration, push, cleanup, or production authority is granted.

## Source and start state

- **Workspace/root:** /private/tmp/nexus-codex-dx-019fe8e1
- **Branch:** codex/codex-dx-reliability
- **Starting HEAD:** b6601270edd95a756c4eab8c7a623006ee1b32d1
- **Dirty baseline:** clean at Target creation; only the approved source specification and campaign authority bundle may be published before task execution
- **Required initial verification:** Verify root, branch, HEAD, status, worktrees, source spec digest, campaign index, and exact card hash before mutation.
- **Freshness rule:** Re-read after HEAD, index, worktree, transport, source spec, or card hash changes.

## MCP execution profile

- **App/server and action snapshot:** not applicable
- **Exact required actions:** not applicable
- **Confirmation-required actions:** none
- **Idempotency and attempt rule:** not applicable
- **Reconnect reconciliation:** not applicable
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner-approved source specification and campaign frontier.
- **Execution authority:** This exact Git-tracked card in the clean isolated Target through repository-owned local governed execution.
- **Verification authority:** Exact command manifest, source acceptance criteria, and independent reviewer.
- **Receipt authority:** Commit-bound Task Card evidence and benchmark/schema receipts named below.
- **Approval/integration authority:** Owner only; implementer and reviewer cannot approve, integrate, push, merge, release, or clean up.

## Allowed scope

- **Read:** tasks/SPEC-CODEX-DX-RELIABILITY-20260810.md; scripts/bench/evidence_bundle_manifest.py; scripts/bench/evidence_bundle_gates.py; tests/benchmark/test_evidence_bundle_manifest.py; tests/benchmark/test_evidence_bundle_gates.py; docs/benchmark/local_heal_receipt_v1.schema.json
- **Edit:** none
- **Create:** docs/benchmark/codex_dx_history_receipt_v1.schema.json; scripts/bench/codex_dx_history.py; tests/benchmark/test_codex_dx_history.py
- **Delete:** none
- **Maximum touched production files:** 2
- **Maximum touched test files:** 1

## Unknown scan

- **Known facts:** App history currently returns no payload and GitHub transport has been intermittent; prior bounded GitHub audit found 20 PRs.
- **Assumptions requiring verification:** Adapters can expose transport outcome and returned-count metadata without storing secrets or unbounded message contents.
- **Architecture risks:** The collector must remain read-only evidence tooling and cannot become workflow or task authority.
- **Evidence risks:** Partial pagination or hung reads could be mistaken for complete history.
- **Missing owner decision:** none

## Mandatory source audit

Inspect evidence-bundle identity/gate conventions and the adjacent local-heal schema only as a pattern. Define a distinct Codex DX schema with complete, partial, and transport-unavailable states.

## Start-state classification

`DEFECT_REPRODUCED`

## RED or existing-guard proof

Show that no current versioned receipt can distinguish zero returned tasks from an unavailable task transport.

## Implementation constraints

Fail closed on missing cutoff, source identity, pagination state, or per-item outcome. Store bounded evidence references, not secrets or unbounded transcripts.

## GREEN and regression gates

Schema and collector tests cover complete, partial, timeout, unavailable, pagination, duplicate item, redaction, and denominator accounting states.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| C1 | TARGET_ROOT | PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/benchmark/test_codex_dx_history.py tests/benchmark/test_evidence_bundle_manifest.py tests/benchmark/test_evidence_bundle_gates.py | Validate history receipt and adjacent evidence contracts. | All selected tests pass. |
| C2 | TARGET_ROOT | git diff --check | Check scoped patch whitespace. | Exit 0 with no findings. |

## Physical evidence

Bind source spec SHA, Task Card SHA, attempt identity, Target root, starting and final HEAD, complete diff, changed symbols, command outputs, verifier identities, and terminal state. Preserve fixture, canary, benchmark, and source evidence as distinct layers. Missing evidence fails closed.

## Independent review

A fresh reviewer must compare the approved specification, this card, complete scoped diff, RED/GREEN evidence, command outputs, benchmark or schema receipts, unrelated-state audit, and authority boundaries. Review cannot approve or integrate the Candidate.

## Exit conditions

- **PASS:** Receipt schema and collector contract pass negative controls and a scoped Candidate is formed.
- **BLOCK:** Collector requires mutating transport, cannot bound content, leaks credentials, or treats unavailable coverage as complete.
- **Residual debt:** Live task backfill remains required before final goal completion if transport stays unavailable during this card.
- **Next gate:** Independent Candidate acceptance; evidence can later feed TASK-CODEX-DX-008-FEEDBACK and TASK-CODEX-DX-009-AFTER.
