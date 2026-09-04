# TASK-CORE-V1-TG7-CORPUS-SHADOW — Representative corpus and second-repository shadow

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#763`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `9ef4b46838251ce86d20d6469901e1f8f02f66ed468655bb446e170ebe90f170`
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
- **Execution lane:** `NON_MCP`
- **Minimum MCP profile:** `not applicable`
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

- **App/server and action snapshot:** not applicable; `DIRECT_DELEGATED` Luna execution under Ready Issue #763
- **Exact required actions:** not applicable
- **Confirmation-required actions:** none
- **Idempotency and attempt rule:** each corpus/shadow run binds task set, repo revision, and TG-5 receipt
- **Reconnect reconciliation:** reconcile the same attempt before retry
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner for repo/pilot; CapabilityPlanner for route
- **Execution authority:** approved Luna worker through the non-Nexus `DIRECT_DELEGATED` control plane
- **Verification authority:** independent controller benchmark/shadow review; worker PASS is not acceptance
- **Receipt authority:** benchmark and Core receipts without maturity elevation
- **Approval/integration authority:** Owner-designated authority only

## Allowed scope

- **Read:** product/benchmark;tests/product/test_false_completion_benchmark.py;README.md;TG5 receipt;selected public repository at its bound revision
- **Edit:** none
- **Create:** product/benchmark/tg7_shadow.py;tests/benchmark/test_core_v1_tg7_manifest.py
- **Delete:** none
- **Maximum touched production files:** 1
- **Maximum touched test files:** 1

## Unknown scan

- **Known facts:** current fixed corpus is not representative external proof.
- **Assumptions requiring verification:** public repository license/privacy eligibility, immutable external identity, corpus representativeness, comparability, adequate oracle, and exact denominator.
- **Architecture risks:** internal tests overclaimed as Stable.
- **Evidence risks:** missing oracle, denominator, paired subject, or gate artifact.
- **Missing owner decision:** none

## Selection, corpus, and report contract

- Evidence paths are fixed outside the source diff: `/private/tmp/nexus-core-v1-evidence/tg7/selection.json`, `/private/tmp/nexus-core-v1-evidence/tg7/corpus.json`, `/private/tmp/nexus-core-v1-evidence/tg7/shadow-receipt.json`, and `/private/tmp/nexus-core-v1-evidence/tg7/report.json`.
- During the task, the worker may propose a public Python repository, but the controller must bind the selection before execution. `selection.json` records canonical URL, owner/name, immutable commit/tree, observation time, license, privacy boundary, read-only permission, task-set identity, and why the repository is not Nexus-new. No repository mutation or external outreach is allowed.
- `corpus.json` contains at least 50 revision-bound cases spanning at least these eight hostile families: authentication/issuer, provenance/hash tamper, stale revision/generation, duplicate/replay, malformed protocol/schema, missing/inadequate oracle, path/scope escape, and crash/unknown effect. Each case has an adequate oracle and expected disposition.
- `report.json` records eligible/infra-invalid counts, family coverage, high-risk false-certification count, trust mismatches, task-set/repository/TG5 receipt hashes, and denominator. The observed high-risk false-certification count must be exactly `0`; missing oracle, denominator, subject, or gate artifact is non-claimable.
- The denominator is `eligible cases after infra exclusions`; infra-invalid cases are reported separately and never silently removed. No human-time/value claim is made in TG7.

## Mandatory source audit

Audit TG-5 receipt, corpus manifest, selected external repo/revision, read-only permission, oracle, compatibility, denominator, and report hashes. Human-time logs are out of scope.

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
| TG7-01 | TARGET_ROOT | `uv run pytest -qq tests/product/test_false_completion_benchmark.py tests/benchmark/test_core_v1_tg7_manifest.py` | fixed benchmark and manifest guard | all tests pass |
| TG7-02 | TARGET_ROOT | `uv run python -m product.benchmark.tg7_shadow --manifest /private/tmp/nexus-core-v1-evidence/tg7/corpus.json --shadow-repo /private/tmp/nexus-core-v1-evidence/tg7/selection.json --tg5-receipt /private/tmp/nexus-core-v1-evidence/tg7/tg5-receipt.json --report /private/tmp/nexus-core-v1-evidence/tg7/report.json` | representative corpus and read-only second-repo shadow | report is hash-valid, has >=50 cases across >=8 families, and high-risk false certification is 0 |
| TG7-03 | TARGET_ROOT | `git diff --check` | integrity | exit 0 |

## Physical evidence

Capture selection, corpus/task-set, external repo/revision/tree, read-only permission, per-case oracle, TG5 receipt, shadow attempts, compatibility, and report hashes. Human-time/value logs are explicitly out of scope.

## Independent review

Fresh reviewer verifies representativeness, external identity, denominator, false-certification result, and ceiling.

## Exit conditions

- **PASS:** shadow evidence supports `CROSS_REPO_TRUST_SHADOW_VERIFIED`.
- **BLOCK:** selection/permission or external identity is absent, license/privacy boundary is unresolved, corpus has fewer than 50 cases or fewer than 8 hostile families, oracle/denominator is inadequate, or high-risk false certification is non-zero.
- **Residual debt:** TG-8 maturity/value gate.
- **Next gate:** TG-8 after TG-6 and TG-7 acceptance; TG-6 and TG-7 may run in parallel after TG-5 acceptance.
