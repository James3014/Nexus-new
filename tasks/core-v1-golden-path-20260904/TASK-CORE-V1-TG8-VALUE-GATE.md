# TASK-CORE-V1-TG8-VALUE-GATE — Protocol maturity and paired value gate

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#763`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `1afae6f51f91563d8476a25c220446eab8b06391b8edd99fb95ea0881828d7ed`
- **Source groups:** TG-7 Corpus/second repo;TG-8 Protocol/value gate
- **Requirements:** REQ-014
- **Acceptance:** AC-010;AC-016
- **Auto-chain:** `false`
- **Maximum claim:** bounded maturity/value claim
- **Depends on:** TASK-CORE-V1-TG6-CLIENTS-PACKAGE;TASK-CORE-V1-TG7-CORPUS-SHADOW
- **Dependency unlock evidence:** TG-6 receipt;TG-7 receipt and pilot selection
- **Task type:** `INTEGRATION_VERIFY`
- **Slicing strategy:** `EXPAND_CONTRACT`
- **Scope class:** `medium`
- **Execution lane:** `NEXUS_LIFECYCLE_V2`
- **Minimum MCP profile:** `VERIFY`
- **Commit required:** `false`
- **Candidate required:** `false`
- **Parallel safe:** `false`
- **Supersedes:** none

## Goal

Evaluate protocol compatibility, upgrade/rollback evidence, and paired human-time value after corpus and second-repository shadow evidence.

## Observable outcome

evidence-gated RC/Stable and paired value data

## Non-goals

No automatic RC/Stable promotion, public/commercial claim, release, production declaration, or source mutation.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-014 | maturity/value boundary | maturity and value require all evidence gates |
| AC-010 | corpus witness | external shadow and representative corpus are revision-bound |
| AC-016 | final witness | compatibility, rollback, paired denominator, and Nexus overhead are included |

## Owner decisions

DEC-005; DER-003. Pilot and maturity decisions remain Owner-controlled.

## Source and start state

- **Workspace/root:** `REVERIFY_AFTER_DEPENDENCY`
- **Branch:** `REVERIFY_AFTER_DEPENDENCY`
- **Starting HEAD:** `REVERIFY_AFTER_DEPENDENCY`
- **Dirty baseline:** `REVERIFY_AFTER_DEPENDENCY`
- **Required initial verification:** verify TG-6 and TG-7 accepted receipts plus explicit pilot selection
- **Freshness rule:** re-read protocol candidate, repos, receipts, compatibility, rollback, and time logs before adjudication

## MCP execution profile

- **App/server and action snapshot:** Nexus lifecycle MCP snapshot required at execution
- **Exact required actions:** nexus_task_run;nexus_task_status;nexus_task_wait;nexus_task_reconcile;nexus_task_finish
- **Confirmation-required actions:** nexus_task_run;nexus_task_finish
- **Idempotency and attempt rule:** gate adjudication binds exact evidence set and candidate; replay cannot promote twice
- **Reconnect reconciliation:** reconcile the same attempt before retry
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner for pilot/maturity; CapabilityPlanner for route
- **Execution authority:** approved Luna worker
- **Verification authority:** independent controller adjudication
- **Receipt authority:** bounded maturity/value receipt only
- **Approval/integration authority:** Owner-designated release/public authority only

## Allowed scope

- **Read:** README.md;pyproject.toml;product/benchmark;tests/product/test_false_completion_benchmark.py
- **Edit:** none
- **Create:** none
- **Delete:** none
- **Maximum touched production files:** 0
- **Maximum touched test files:** 0

## Unknown scan

- **Known facts:** current source does not support Stable, release, production, or commercial value.
- **Assumptions requiring verification:** external shadow, protocol compatibility, rollback, paired time, and denominator.
- **Architecture risks:** internal evidence promoted to public maturity.
- **Evidence risks:** missing gate artifact or overhead measurement.
- **Missing owner decision:** none

## Mandatory source audit

Audit TG-6 install/rollback, TG-7 corpus/shadow, protocol/schema axes, compatibility, paired human-time logs, and all maturity gates.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Remove any oracle, denominator, paired subject, compatibility, or rollback artifact; adjudication remains blocked and never infers Stable/value.

## Implementation constraints

Proof-only verification; preserve protocol/schema separation and claim ceiling; no Owner decision is inferred.

## GREEN and regression gates

AC-010 and AC-016 pass only when every gate is revision-bound, false certification is zero, and paired overhead evidence is independently accepted.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG8-01 | TARGET_ROOT | `uv run pytest -qq tests/product/test_false_completion_benchmark.py` | benchmark guard | all tests pass |
| TG8-02 | TARGET_ROOT | `git diff --check` | integrity | exit 0 |

## Physical evidence

Capture pilot decision, protocol candidate, corpus/shadow, paired attempts, oracle, time log, compatibility, upgrade/rollback, hashes, reviewer attempt, and bounded adjudication.

## Independent review

Fresh reviewer verifies AC-010/AC-016 gates, denominator, external identity, claim ceiling, and no promotion authority.

## Exit conditions

- **PASS:** evidence supports only the bounded maturity/value claim.
- **BLOCK:** any gate artifact or Owner selection is missing.
- **Residual debt:** public/release/production authority remains external.
- **Next gate:** Owner decides whether separate release/public process may begin.
