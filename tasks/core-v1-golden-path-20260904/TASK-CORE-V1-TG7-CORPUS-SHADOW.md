# TASK-CORE-V1-TG7-CORPUS-SHADOW — Representative corpus and second-repository shadow

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#771`
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
- **Commit required:** `true`
- **Candidate required:** `true`
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
| REQ-014 | benchmark requirement | representative corpus and second-repo shadow precede protocol maturity |
| AC-010 | benchmark witness | revision-bound gates, zero high-risk false certification, and exact eligible-case denominator |

## Owner decisions

DEC-005; DEC-013; DER-003. The controller selects and binds the second repository before dispatch; the worker does not select or change it. Human pilot/value work belongs only to TG-9.

## Source and start state

- **Workspace/root:** `REVERIFY_AFTER_DEPENDENCY`
- **Branch:** `REVERIFY_AFTER_DEPENDENCY`
- **Starting HEAD:** `REVERIFY_AFTER_DEPENDENCY`
- **Dirty baseline:** `REVERIFY_AFTER_DEPENDENCY`
- **Required initial verification:** verify TG-5 accepted receipt and exact accepted Candidate source in a clean controller-bound integration HEAD/tree; the controller must bind the privacy-safe immutable second-repository selection in `selection.json` before worker dispatch; this card's `Parallel safe: false` forbids auto-start but the separate Owner/controller contract permits concurrent TG-6/TG-7 dispatch as distinct Ready Issues
- **Freshness rule:** re-read selection, external revision, corpus manifest, and TG-5 receipt before each run

## MCP execution profile

- **App/server and action snapshot:** not applicable; `DIRECT_DELEGATED` Luna execution under Ready Issue #771
- **Exact required actions:** not applicable
- **Confirmation-required actions:** none
- **Idempotency and attempt rule:** each corpus/shadow run binds task set, repo revision, and TG-5 receipt
- **Reconnect reconciliation:** reconcile the same attempt before retry
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner/Campaign controller for the second repository; CapabilityPlanner remains route authority
- **Execution authority:** approved Luna worker through the non-Nexus `DIRECT_DELEGATED` control plane
- **Verification authority:** independent controller benchmark/shadow review; worker PASS is not acceptance
- **Receipt authority:** benchmark and Core receipts without maturity elevation
- **Approval/integration authority:** Owner-designated authority only

## Allowed scope

- **Read:** product/benchmark;product/protocol;product/runtime;product/execution;product/evidence;tests/product/test_false_completion_benchmark.py;README.md;TG5 receipt;selected public repository at its bound revision
- **Edit:** none
- **Create:** product/benchmark/tg7_shadow.py;tests/benchmark/test_core_v1_tg7_manifest.py
- **Delete:** none
- **Maximum touched production files:** 1
- **Maximum touched test files:** 1

## Unknown scan

- **Known facts:** current fixed corpus is not representative external proof.
- **Assumptions requiring verification:** public repository license/privacy eligibility, immutable external identity, corpus representativeness, comparability, adequate oracle, and exact denominator.
- **Architecture risks:** internal tests overclaimed as Stable.
- **Evidence risks:** missing oracle, eligible-case denominator, external subject/revision, hostile-family coverage, or gate artifact.
- **Missing owner decision:** none

## Selection, corpus, and report contract

- Evidence paths are fixed outside source: `/private/tmp/nexus-core-v1-evidence/tg7/tg5-receipt.json`, `selection.json`, `corpus.json`, `shadow-receipt.json`, and `report.json`. Before dispatch the controller copies the independently accepted TG-5 receipt to that exact path, verifies its canonical schema/receipt hash against Issue #769 acceptance, records the file SHA-256, and makes it read-only; missing/mismatched/stale receipt blocks execution.
- Before worker dispatch, the controller selects and materializes one public Python repository read-only at `/private/tmp/nexus-core-v1-evidence/tg7/repository`; the worker has no network and may validate but not choose/change/fetch it. `selection.json` schema `nexus.core-v1.tg7-selection.v1` has exact keys `canonical_url`, `owner`, `name`, `commit`, `tree`, `snapshot_path`, `snapshot_tree_hash`, `observed_at`, `license_spdx`, `license_evidence_hash`, `privacy_class`, `read_only_evidence_hash`, `task_set_id`, `not_nexus_reason`, `selection_hash`. Allowed licenses: `MIT`, `BSD-2-Clause`, `BSD-3-Clause`, `Apache-2.0`, `ISC`; private/protected data, credentials, secrets, personal data, generated state, or Nexus-new are ineligible. Controller verifies commit/tree twice and permissions before dispatch.
- `corpus.json` schema `nexus.core-v1.tg7-corpus.v1` uses canonical SHA-256, unique sorted case IDs, and at least 50 **eligible** revision-bound cases. Each case binds repository commit/tree, hostile family, canonical request/input hash, operation, oracle kind/source/hash, expected factual status/disposition/reason, TG-5 protocol/schema/profile/task-set identities, and case hash. Each of eight families—authentication/issuer, provenance/hash tamper, stale revision/generation, duplicate/replay, malformed protocol/schema, missing/inadequate oracle, path/scope escape, crash/unknown effect—has at least five eligible cases. Oracle kinds are closed to accepted TG-2 JUnit receipts or deterministic protocol-guard expectations and require controller review; worker prose is never an oracle.
- Shadow execution uses exact TG-5 protocol, implementation schema, `python-oci-pytest-v1`, request canonicalization, outcome mapping, and claim ceiling. Every eligible case produces a real read-only attempt receipt; zero silent skips. Changed external commit/tree, TG-5 receipt, task set, profile, or oracle makes the run `UNVERIFIABLE`.
- `shadow-receipt.json` schema `nexus.core-v1.tg7-shadow-receipt.v1` binds run ID, TG-5 receipt, selection/corpus/task-set hashes, external repository/commit/tree, ordered per-case attempt/oracle/result hashes, eligible/infra-invalid counts and receipt hash. `report.json` schema `nexus.core-v1.tg7-report.v1` binds it plus family counts, denominator, false-certification case IDs/count, trust mismatches, compatibility, claim ceiling, generated-at and report hash.
- High-risk false certification means an eligible case whose trusted expected outcome is rejection, `FAILED_VERIFICATION`, or `UNVERIFIABLE`, but observed Completion is `VERIFIED` with certifiable disposition. Report recomputes this from case/attempt/oracle receipts; caller counts are untrusted. Pass: count `0`, denominator >=50, each family >=5, exact arithmetic accounting.
- Infra-invalid reasons are closed to `MATERIALIZATION_MISSING`, `RUNNER_UNAVAILABLE_BEFORE_EXECUTION`, `DEPENDENCY_ARTIFACT_MISSING`, `TIMEOUT_BEFORE_EXECUTION`, `CORRUPT_FIXTURE`. Every exclusion retains case/attempt/reason hashes and is separate; semantic failures, trust mismatches, post-execution timeouts, or hostile outcomes cannot be excluded. Eligible denominator after exclusions remains >=50. No human-time/value claim is made.
- `Parallel safe: false` prevents auto-start under `AUTO_CHAIN=false`; the separate Owner/controller contract still permits concurrent TG-6/TG-7 distinct Ready Issues after TG-5 in disjoint isolated worktrees.

## Mandatory source audit

Audit TG-5 receipt, corpus manifest, selected external repo/revision, read-only permission, oracle, compatibility, denominator, and report hashes. Human-time logs are out of scope.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Remove the oracle, eligible-case denominator, external subject/revision, hostile-family coverage, or gate artifact; the incomplete benchmark must remain non-claimable.

## Implementation constraints

Read-only proof spike; no selection or mutation; preserve exact revisions and claim ceiling.

## GREEN and regression gates

AC-010 passes only with selected representative corpus, second-repo receipt, and independent benchmark review.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG7-01 | TARGET_ROOT | `uv run pytest -qq tests/product/test_false_completion_benchmark.py tests/benchmark/test_core_v1_tg7_manifest.py` | schemas and hostile guard | all tests pass, including forged selection/license/tree/oracle/denominator/infra/report/TG5 negatives |
| TG7-02 | TARGET_ROOT | `uv run pytest --collect-only -q tests/benchmark/test_core_v1_tg7_manifest.py` | prove TG7 negative tests discovered | intended cases listed |
| TG7-03 | TARGET_ROOT | `uv run python -m product.benchmark.tg7_shadow --selection /private/tmp/nexus-core-v1-evidence/tg7/selection.json --repository /private/tmp/nexus-core-v1-evidence/tg7/repository --manifest /private/tmp/nexus-core-v1-evidence/tg7/corpus.json --tg5-receipt /private/tmp/nexus-core-v1-evidence/tg7/tg5-receipt.json --shadow-receipt /private/tmp/nexus-core-v1-evidence/tg7/shadow-receipt.json --report /private/tmp/nexus-core-v1-evidence/tg7/report.json` | read-only second-repo shadow | zero skips; >=50 eligible, >=5 per family, exact accounting, false certification 0, hash-valid receipt/report |
| TG7-04 | TARGET_ROOT | `git diff --check` | integrity | exit 0 |

## Physical evidence

Capture selection, corpus/task-set, external repo/revision/tree, read-only permission, per-case oracle, TG5 receipt, shadow attempts, compatibility, and report hashes. Human-time/value logs are explicitly out of scope.

## Independent review

Fresh reviewer verifies representativeness, external identity, denominator, false-certification result, and ceiling.

## Exit conditions

- **PASS:** shadow evidence supports `CROSS_REPO_TRUST_SHADOW_VERIFIED`.
- **BLOCK:** selection/permission or external identity is absent, license/privacy boundary is unresolved, corpus has fewer than 50 cases or fewer than 8 hostile families, oracle/denominator is inadequate, or high-risk false certification is non-zero.
- **Residual debt:** TG-8 maturity/value gate.
- **Next gate:** TG-8 may start only from a clean controller-bound integration HEAD/tree containing the exact accepted TG-6 and TG-7 Candidates plus their TG-5 ancestry.
