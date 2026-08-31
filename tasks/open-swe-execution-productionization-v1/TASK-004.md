# TASK-004 — Activation evidence portfolio and artifact-aware attribution

- **Campaign:** `CAMPAIGN-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Status:** `BLOCKED`
- **Source spec:** `SPEC-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Source spec SHA-256:** `17e2b27e2ad57d02cd33fd37d0c7d97a29a1ff14e182d7661b141baf9f925d74`
- **Source groups:** `G4 Activation evidence portfolio`
- **Requirements:** `REQ-007; REQ-008`
- **Acceptance:** `AC-009; AC-010`
- **Auto-chain:** `false`
- **Maximum claim:** Evidence is sufficient for a separate Owner activation decision; this card itself does not switch defaults, retire OpenCLI, merge, release, or claim production readiness.
- **Depends on:** `TASK-002; TASK-003`
- **Dependency unlock evidence:** Portable sandbox qualification from TASK-002; independently accepted diagnosis/repair Candidate path from TASK-003.
- **Task type:** `INTEGRATION_VERIFY`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `medium`
- **Execution lane:** `NEXUS_LIFECYCLE_V2`
- **Minimum MCP profile:** `VERIFY`
- **Commit required:** `false`
- **Candidate required:** `false`
- **Parallel safe:** `false`
- **Supersedes:** `none`

## Goal

Run and independently adjudicate the minimum production-shaped evidence portfolio required before any default-switch decision: semantic-only, CI diagnosis+repair, and ambiguous-outcome/recovery canaries, including artifact-aware attribution when a target new failure is repaired while unrelated baseline failures remain.

## Observable outcome

Three exact-identity canaries produce immutable evidence with no unauthorized authority escalation. The portfolio distinguishes target repair success from unrelated aggregate red checks and yields either `ACTIVATION_EVIDENCE_READY` or a bounded blocking verdict.

## Non-goals

No config/default switch; no OpenCLI retirement; no production rollout; no auto-merge/release/deploy; no statistical claim that Open SWE reviewer quality is superior to OpenCLI.

## Source lineage

`REQ-007`, `REQ-008`, `AC-009`, `AC-010`, accepted TASK-002/TASK-003 evidence, and PR #664 only as historical design evidence.

## Owner decisions

No new Owner decision is required to run evidence canaries. A later default switch remains a separate Owner/production authority boundary.

## Source and start state

- **Workspace/root:** exact accepted current-main revision after TASK-002/TASK-003 prerequisites
- **Branch:** disposable canary branches/workspaces only
- **Starting HEAD:** rebind fresh per canary
- **Dirty baseline:** clean/disposable
- **Required initial verification:** re-read accepted adapter/backend/repair contracts and current CI/RI evidence interfaces
- **Freshness rule:** every canary binds repository, base, head, RI content hash, adapter/backend/model identity, task/attempt identity, and relevant CI artifact/run IDs

## MCP execution profile

- **App/server and action snapshot:** current Nexus/GitHub actions at execution
- **Exact required actions:** read-only RI/GitHub status plus governed canary/Candidate actions as authorized by then-current card; exact names rebound before execution
- **Confirmation-required actions:** protected merge/release/default activation are forbidden in this card
- **Idempotency and attempt rule:** each canary has unique identity; uncertain dispatch reconciles before any retry
- **Reconnect reconciliation:** provider/task/GitHub physical state first; no blind replay
- **Transport blocker:** missing accepted TASK-002 or TASK-003 evidence, or inability to observe exact CI artifacts/identity

## Authority map

- **Selection authority:** source-spec portfolio only; no route-policy mutation
- **Execution authority:** bounded canary Task Cards/fixtures under current Nexus governance
- **Verification authority:** independent acceptance/audit
- **Receipt authority:** immutable canary reports bound to physical Git/CI/model identities
- **Approval/integration authority:** none; later Owner activation decision only

## Allowed scope

This blocked verification card grants no current production-file mutation. Exact disposable canary fixtures/branches are frozen only after prerequisites pass.

- **Read:** accepted TASK-002/TASK-003 evidence; current RI/CI artifacts; canary source and workflow evidence
- **Edit:** `none while BLOCKED`
- **Create:** disposable canary artifacts only after unblocking
- **Delete:** disposable canary cleanup only under separately authorized controller action
- **Maximum touched production files:** `0`
- **Maximum touched test files:** `0 in canonical source`

## Unknown scan

- **Known facts:** one historical PR #664 canary repaired its target new failure while an unrelated baseline architecture failure kept aggregate impact red.
- **Assumptions requiring verification:** accepted TASK-003 exposes enough artifact/run identity to classify target repair independently from unrelated baseline failures.
- **Architecture risks:** using coarse aggregate CFI as sole success oracle; canary evidence accidentally changing default route.
- **Evidence risks:** all-happy-path canaries would not prove recovery/reconciliation.
- **Missing owner decision:** `none until an actual activation switch is proposed`

## Mandatory source audit

Before unblocking, bind current GitHub/CI artifact APIs, RI report identities, canary workflow semantics, recovery/failure injection seam, and proof that canaries cannot auto-merge or change production defaults.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Historical PR #664 demonstrates the exact false-green/false-red problem: target new failure can be repaired while aggregate job remains red. This card must prove the productionized path handles that distinction physically rather than via report prose.

## Implementation constraints

At least three distinct canaries are required: (1) semantic-only, (2) CI diagnosis+repair, (3) ambiguous-outcome/recovery. At least one must exercise a negative/stale/recovery path. Target repair attribution must use artifact/run/head identity, not aggregate check color alone.

## GREEN and regression gates

- `AC-009`: all three production-shaped canaries pass their exact positive and negative controls.
- `AC-010`: a target repaired failure is recognized as resolved even when an unrelated baseline failure remains, without claiming aggregate green.
- OpenCLI remains available and default throughout.

## Mandatory command manifest

`BLOCKED/UNVERIFIED` until TASK-002/TASK-003 establish exact runtime/backend/controller interfaces. Do not invent canary commands now.

## Physical evidence

Per-canary exact repository/base/head/RI hashes, model/backend/dependency identities, run/attempt IDs, CI check/job/artifact IDs, Candidate SHA/tree where applicable, recovery/reconcile evidence, target failure attribution, control-arm/default-route state, and proof PRs remain unmerged unless separately authorized.

## Independent review

A fresh reviewer adjudicates each canary independently and then the portfolio as a whole, with special attention to stale identity, ambiguous outcomes, artifact attribution, authority conservation, and control-arm preservation.

## Exit conditions

- **PASS:** AC-009 and AC-010 are independently satisfied, yielding `ACTIVATION_EVIDENCE_READY` only.
- **BLOCK:** fewer than three qualifying canaries, portable sandbox/repair prerequisite drift, recovery path duplicates effects, artifact attribution remains ambiguous, or any authority/default-switch leakage occurs.
- **Residual debt:** production rollout/monitoring and any future OpenCLI retirement require separate Owner-approved work.
- **Next gate:** separate Owner activation decision; no auto-chain.
