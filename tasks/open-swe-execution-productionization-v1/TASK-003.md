# TASK-003 — Governed Open SWE diagnosis and repair adapter

task_id: `TASK-003`

- **Campaign:** `CAMPAIGN-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Status:** `BLOCKED`
- **Source spec:** `SPEC-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Source spec SHA-256:** `17e2b27e2ad57d02cd33fd37d0c7d97a29a1ff14e182d7661b141baf9f925d74`
- **Source groups:** `G3 Diagnosis/repair adapter`
- **Requirements:** `REQ-001; REQ-003; REQ-004; REQ-006`
- **Acceptance:** `AC-008`
- **Auto-chain:** `false`
- **Maximum claim:** A Nexus-governed Open SWE diagnosis/repair Candidate path is qualified; no default activation, OpenCLI retirement, acceptance, merge, release, or production-readiness claim.
- **Depends on:** `TASK-001`
- **Dependency unlock evidence:** Independently accepted TASK-001 Candidate with stable semantic adapter, dependency contract, and physical graph-isolation witness.
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `medium`
- **Execution lane:** `NEXUS_LIFECYCLE_V2`
- **Minimum MCP profile:** `CANDIDATE`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** `none`

## Goal

Adapt the existing Nexus External Intelligence automation/fanout seam so a bounded Open SWE diagnosis graph may run read-only and a separately admitted repair graph may produce a Candidate, while Nexus retains durable queue/replay/reconciliation, repair-cycle limits, verification, acceptance, and GitHub authority.

## Observable outcome

For one bounded failing-CI fixture/canary, RI/CFI/EIA-bound evidence enters the existing Nexus controller, Open SWE diagnoses the failure, a repair is admitted only after `ROOT_CAUSE_SUPPORTED`, one bounded Candidate is produced, independent verification runs, and execution stops before acceptance/merge.

## Non-goals

No default activation; no OpenCLI retirement; no direct GitHub credentials/tools inside Open SWE; no worker self-acceptance; no automatic merge/release/deploy; no `task`/subagent enablement; no second queue/replay controller.

## Source lineage

`REQ-001`, `REQ-003`, `REQ-004`, `REQ-006`, `AC-008`, accepted TASK-001 contract, and pilot PR #664 as historical canary evidence only.

## Owner decisions

`DEC-001`, `DEC-002`, `DEC-003`, `DEC-005` remain binding.

## Source and start state

- **Workspace/root:** current `James3014/Nexus-new` governed Target/worktree
- **Branch:** governed Candidate branch/Target only
- **Starting HEAD:** fresh current main after TASK-001 acceptance/integration
- **Dirty baseline:** clean
- **Required initial verification:** re-read current `ExternalIntelligenceAutomation`, fanout/closure runtime, accepted TASK-001 adapter contract, repair-cycle state, and affected tests before freezing exact mutation paths
- **Freshness rule:** if fanout/closure/replay contracts drift, this blocked card must be superseded with exact paths/commands before activation

## MCP execution profile

- **App/server and action snapshot:** current Nexus Gateway at activation time
- **Exact required actions:** current governed Candidate execution/status/reconcile actions; exact schema must be rebound before activation
- **Confirmation-required actions:** Candidate approval/integration/merge remain outside card
- **Idempotency and attempt rule:** one exact semantic/diagnosis/repair attempt identity; unknown outcomes reconcile before retry; maximum repair cycles remains controller-owned
- **Reconnect reconciliation:** existing Nexus durable state and physical Candidate evidence first
- **Transport blocker:** TASK-001 not accepted or current action schema cannot express bounded diagnosis/repair Candidate flow

## Authority map

- **Selection authority:** CapabilityPlanner only
- **Execution authority:** Nexus lifecycle/Task Card/Workforce Admission
- **Verification authority:** independent Nexus verifier/coordinator
- **Receipt authority:** existing Nexus durable automation/Candidate receipts
- **Approval/integration authority:** separate Owner/Nexus gate

## Allowed scope

Exact production mutation paths are intentionally not frozen until TASK-001 is accepted and current fanout/closure source is rebound. This card is BLOCKED and grants no mutation yet.

- **Read:** accepted TASK-001 implementation; `nexus/services/external_intelligence_automation.py`; `nexus/services/external_intelligence_fanout.py`; `nexus/services/external_intelligence_closure.py`; their focused tests; RI evidence contracts
- **Edit:** `none while BLOCKED`
- **Create:** `none while BLOCKED`
- **Delete:** `none`
- **Maximum touched production files:** `0 while BLOCKED`
- **Maximum touched test files:** `0 while BLOCKED`

## Unknown scan

- **Known facts:** Nexus already owns durable sequencing/fanout/closure; pilot proved real Open SWE diagnosis/repair and Candidate-only boundary.
- **Assumptions requiring verification:** current production fanout/closure interface can accept Open SWE repair execution without duplicating worker-state authority.
- **Architecture risks:** accidental second repair queue, bypass of diagnosis admission, worker self-verification, GitHub credential leakage.
- **Evidence risks:** one PR #664 canary is insufficient to establish crash/replay behavior.
- **Missing owner decision:** `none`

## Mandatory source audit

Before unblocking, bind exact current callers, repair-cycle accounting, ambiguous-outcome handling, Candidate receipt schema, verifier seam, and physical worker mutation boundary. Then supersede this card with exact allowed paths and command manifest if any interface drift exists.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Existing Nexus replay/repair-cycle/Candidate guards are authoritative and must remain green. The missing production behavior is a qualified Open SWE diagnosis/repair execution adapter at those seams.

## Implementation constraints

Diagnosis physically read-only; repair admitted only on supported root cause and exact identity; repair mutation confined to isolated Candidate workspace; no direct GitHub write; no self-acceptance; no blind retry; no more than two automatic repair cycles unless a later approved contract changes it.

## GREEN and regression gates

`AC-008`: real bounded canary reaches independently verified Candidate and stops before acceptance/merge. Negative cases for stale identity, inconclusive diagnosis, unknown outcome, repair-cycle exhaustion, and forbidden authority must block without unauthorized side effect.

## Mandatory command manifest

`BLOCKED/UNVERIFIED` until TASK-001 is accepted and exact current production seams are rebound. Do not invent commands.

## Physical evidence

Exact PR/repository/head/base/RI hashes, task/attempt IDs, diagnosis result, repair admission witness, Candidate SHA/tree/diff, repair-cycle count, verifier evidence, replay/reconcile result, and proof no direct GitHub/merge authority existed in worker graph.

## Independent review

Fresh reviewer must inspect exact Candidate, source contract, controller/worker authority split, negative controls, repair-cycle/replay evidence, and test oracle strength.

## Exit conditions

- **PASS:** AC-008 passes on exact Candidate and real canary with independent verification and preserved Nexus authority.
- **BLOCK:** duplicated controller/queue authority, blind retry, worker GitHub authority, self-acceptance, stale identity mutation, or missing exact verifier evidence.
- **Residual debt:** portable sandbox and activation portfolio remain separate.
- **Next gate:** TASK-004 remains blocked until TASK-002 and TASK-003 both pass; no auto-chain.
