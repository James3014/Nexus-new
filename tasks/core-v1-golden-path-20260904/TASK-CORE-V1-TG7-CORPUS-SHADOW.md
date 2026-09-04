# TASK-CORE-V1-TG7-CORPUS-SHADOW — Representative corpus and second-repository shadow

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#763`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `1afae6f51f91563d8476a25c220446eab8b06391b8edd99fb95ea0881828d7ed`
- **Source groups:** TG-7 Corpus/second repo
- **Requirements:** REQ-014
- **Acceptance:** AC-010
- **Auto-chain:** `false`
- **Maximum claim:** `CROSS_REPO_TRUST_SHADOW_VERIFIED`
- **Depends on:** TASK-CORE-V1-TG5-HTTP-TRACER
- **Dependency unlock evidence:** TG-5 accepted receipt and DER-003 selection
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

Verify a representative hostile corpus and Owner-selected second-repository shadow against the accepted real-PR tracer.

## Observable outcome

representative corpus and external shadow

## Non-goals

No Stable, commercial, production, release, external outreach, or repository mutation.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-014 | benchmark requirement | representative corpus and second-repo shadow precede maturity/value |
| AC-010 | benchmark witness | revision-bound gates, zero high-risk false certification, and Nexus-overhead denominator |

## Owner decisions

DEC-005; DER-003. Owner selects repository and pilot; worker does not.

## Source and start state

- **Workspace/root:** `REVERIFY_AFTER_DEPENDENCY`
- **Branch:** `REVERIFY_AFTER_DEPENDENCY`
- **Starting HEAD:** `REVERIFY_AFTER_DEPENDENCY`
- **Dirty baseline:** `REVERIFY_AFTER_DEPENDENCY`
- **Required initial verification:** verify TG-5 receipt and explicit DER-003 selection
- **Freshness rule:** re-read selection, external revision, corpus manifest, and TG-5 receipt before each run

## MCP execution profile

- **App/server and action snapshot:** Nexus lifecycle MCP snapshot required at execution
- **Exact required actions:** nexus_task_run;nexus_task_status;nexus_task_wait;nexus_task_reconcile;nexus_task_finish
- **Confirmation-required actions:** nexus_task_run;nexus_task_finish
- **Idempotency and attempt rule:** each corpus/shadow run binds task set, repo revision, and TG-5 receipt
- **Reconnect reconciliation:** reconcile the same attempt before retry
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner for repo/pilot; CapabilityPlanner for route
- **Execution authority:** approved Luna worker
- **Verification authority:** independent controller benchmark/shadow review
- **Receipt authority:** benchmark and Core receipts without maturity elevation
- **Approval/integration authority:** Owner-designated authority only

## Allowed scope

- **Read:** product/benchmark;tests/product/test_false_completion_benchmark.py;README.md
- **Edit:** none
- **Create:** none
- **Delete:** none
- **Maximum touched production files:** 0
- **Maximum touched test files:** 0

## Unknown scan

- **Known facts:** current fixed corpus is not representative external proof.
- **Assumptions requiring verification:** corpus, external identity, comparability, and human-time denominator.
- **Architecture risks:** internal tests overclaimed as Stable.
- **Evidence risks:** missing oracle, denominator, paired subject, or gate artifact.
- **Missing owner decision:** none

## Mandatory source audit

Audit TG-5 receipt, corpus manifest, selected external repo/revision, oracle, compatibility, and paired time logs.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Remove oracle, denominator, paired subject, or gate artifact; incomplete benchmark must remain non-claimable.

## Implementation constraints

Read-only proof spike; no selection or mutation; preserve exact revisions and claim ceiling.

## GREEN and regression gates

AC-010 passes only with selected representative corpus, second-repo receipt, and independent benchmark review.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG7-01 | TARGET_ROOT | `uv run pytest -qq tests/product/test_false_completion_benchmark.py` | benchmark guard | all tests pass |
| TG7-02 | TARGET_ROOT | `git diff --check` | integrity | exit 0 |

## Physical evidence

Capture selection, corpus/task-set, external repo/revision, paired attempts, oracle, time logs, compatibility, and rollback hashes.

## Independent review

Fresh reviewer verifies representativeness, external identity, denominator, false-certification result, and ceiling.

## Exit conditions

- **PASS:** shadow evidence supports `CROSS_REPO_TRUST_SHADOW_VERIFIED`.
- **BLOCK:** selection or external identity is absent, corpus incomplete, or oracle inadequate.
- **Residual debt:** TG-8 maturity/value gate.
- **Next gate:** TG-8 after TG-6 and TG-7 acceptance.
