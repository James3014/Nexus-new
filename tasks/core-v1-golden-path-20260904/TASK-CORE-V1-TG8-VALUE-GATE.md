# TASK-CORE-V1-TG8-VALUE-GATE — Protocol RC/Stable maturity gate

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#772`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `9ef4b46838251ce86d20d6469901e1f8f02f66ed468655bb446e170ebe90f170`
- **Source groups:** TG-8 Protocol maturity
- **Requirements:** REQ-014
- **Acceptance:** AC-016
- **Auto-chain:** `false`
- **Maximum claim:** bounded protocol-maturity claim
- **Depends on:** TASK-CORE-V1-TG6-CLIENTS-PACKAGE;TASK-CORE-V1-TG7-CORPUS-SHADOW
- **Dependency unlock evidence:** TG-6 accepted receipt;TG-7 accepted report
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

Evaluate protocol compatibility and upgrade/rollback evidence after corpus and second-repository shadow evidence, and classify evidence readiness for RC versus Stable without promoting either.

## Observable outcome

evidence-gated RC/Stable readiness

## Non-goals

No automatic RC/Stable promotion, human-value/pilot claim, public/commercial claim, release, production declaration, or off-scope source mutation. TG-9 already exists in the validated bundle but remains dependency-gated and is not started or authorized by TG-8.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-014 | maturity boundary | protocol maturity requires the real vertical, cross-repository trust, conformance, compatibility, upgrade, and rollback gates |
| AC-010 | accepted dependency | external shadow and representative corpus are revision-bound before this gate starts |
| AC-016 | maturity witness | protocol compatibility, conformance, rollback, and explicit RC/Stable evidence thresholds are included; human value is separate |

## Owner decisions

DEC-005; DEC-013; DER-003. Protocol evidence readiness is adjudicated by the controller; any RC/Stable promotion, release, public claim, or production decision remains external Owner authority. TG-9 value work is already separately specified but remains dependency-gated.

## Source and start state

- **Workspace/root:** `REVERIFY_AFTER_DEPENDENCY`
- **Branch:** `REVERIFY_AFTER_DEPENDENCY`
- **Starting HEAD:** `REVERIFY_AFTER_DEPENDENCY`
- **Dirty baseline:** `REVERIFY_AFTER_DEPENDENCY`
- **Required initial verification:** verify TG-5, TG-6, and TG-7 accepted receipts/reports and a clean controller-bound integration HEAD/tree containing the exact accepted TG-6/TG-7 Candidate commits and their TG-5 ancestry
- **Freshness rule:** re-read protocol candidate, repositories, receipts, conformance, compatibility, upgrade, and rollback before adjudication

## MCP execution profile

- **App/server and action snapshot:** not applicable; `DIRECT_DELEGATED` Luna execution under Ready Issue #772
- **Exact required actions:** not applicable
- **Confirmation-required actions:** none
- **Idempotency and attempt rule:** gate adjudication binds exact evidence set and candidate; replay cannot promote twice
- **Reconnect reconciliation:** reconcile the same attempt before retry
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner/Campaign controller; CapabilityPlanner remains route authority
- **Execution authority:** approved Luna worker through the non-Nexus `DIRECT_DELEGATED` control plane
- **Verification authority:** independent controller adjudication; worker PASS is not acceptance
- **Receipt authority:** bounded protocol-maturity receipt only
- **Approval/integration authority:** Owner-designated release/public authority only

## Allowed scope

- **Read:** README.md;pyproject.toml;product/protocol;product/benchmark;product/ledger.py;product/clients;tests/product/test_false_completion_benchmark.py;TG4/TG5/TG6/TG7 receipts and reports
- **Edit:** none
- **Create:** product/protocol/compatibility_gate.py;tests/benchmark/test_core_v1_tg8_protocol_gate.py
- **Delete:** none
- **Maximum touched production files:** 1
- **Maximum touched test files:** 1

## Unknown scan

- **Known facts:** current source does not support Stable, release, production, or commercial value.
- **Assumptions requiring verification:** external shadow, protocol/schema compatibility, client conformance, upgrade/rollback, and exact TG7 gate report.
- **Architecture risks:** internal evidence promoted to public maturity.
- **Evidence risks:** missing gate artifact, ambiguous RC/Stable threshold, or inferred release authority.
- **Missing owner decision:** none

## RC/Stable evidence contract

- Evidence paths are fixed outside source: `/private/tmp/nexus-core-v1-evidence/tg8/thresholds.json`, `thresholds.sha256`, `tg4-receipt.json`, `tg5-receipt.json`, `tg6-receipt.json`, `client-conformance.json`, `protocol-compatibility.json`, `upgrade-rollback.json`, `open-issues.json`, exact `stable-run-1.json` through `stable-run-3.json`, TG7 `selection.json`, `corpus.json`, `shadow-receipt.json`, `report.json`, and `gate-report.json`. Controller stages each accepted artifact read-only and records exact SHA-256 before worker reads it; `thresholds.sha256` contains only the 64-hex digest plus newline.
- `thresholds.json` schema `nexus.core-v1.tg8-thresholds.v1` freezes candidates `1.0.0-rc.1` and `1.0.0`, input artifact hashes, classifications below, forbidden output states, and threshold hash. The worker cannot alter thresholds.
- `protocol-compatibility.json` schema `nexus.core-v1.protocol-compatibility.v1` has one row per cross-product transition of public protocol, implementation schema, evidence/envelope/Completion receipt schemas, ledger schema/generation, HTTP schema, CLI/MCP/Action client version and reader version. Each row binds source/target, expected `SUPPORTED` or `REFUSED`, observed outcome, stable reason code, receipt preservation hash and row hash. Unknown axes, axis conflation, missing rows, stale hashes or unexpected coercion are `UNVERIFIABLE`.
- `client-conformance.json` schema `nexus.core-v1.client-conformance.v1` binds the exact TG-6 CLI/MCP/Action artifacts, canonical request/response, endpoint sequence, redaction set, per-client output hashes and parity result. Static YAML or a TG-6 prose receipt alone is insufficient.
- `upgrade-rollback.json` schema `nexus.core-v1.upgrade-rollback.v1` covers exact current public protocol `0.1.0-experimental` -> `1.0.0-rc.1`, RC patch upgrade, RC -> `1.0.0`, incompatible public/schema/ledger transitions, failed-upgrade rollback, and rollback to the exact predecessor reader. Every row binds old/new wheel/runtime/ledger/receipt hashes, expected/observed result, old-receipt byte equality and rollback state; compatible paths preserve receipts and incompatible paths refuse without rewrite.
- `PROTOCOL_RC_EVIDENCE_READY` requires accepted TG4/TG5/TG6/TG7 artifacts, exact complete compatibility/conformance/upgrade matrix, one successful live TG5 tracer, TG7 denominator >=50 with >=5 cases in each of 8 families and zero high-risk false certifications, all required compatible rows supported, all incompatible rows refused, successful failed-upgrade rollback, zero missing/stale/tampered artifacts, and no forbidden claim field.
- `PROTOCOL_STABLE_EVIDENCE_READY` requires every RC condition plus three fresh consecutive controller runs at the exact Stable Candidate commit/tree and distinct run IDs: each reruns live TG5 and full TG7 eligible corpus with zero skips, zero high-risk false certifications and identical factual outcome hashes; aggregated eligible attempts >=150; CLI/MCP/Action parity 100%; every compatible/upgrade/rollback row passes; `open-issues.json` schema `nexus.core-v1.tg8-open-issues.v1` is an Owner/controller snapshot binding repository, observed-at, query/hash and all open trust/runtime severity-high Issue IDs, and its count must be zero. External Owner promotion/release remains separate.
- Machine states are exactly `PROTOCOL_RC_EVIDENCE_READY`, `PROTOCOL_STABLE_EVIDENCE_READY`, `LOWER_MATURITY`, `UNVERIFIABLE`. Output containing combined `PROTOCOL_RC_OR_STABLE_EVIDENCE_READY`, `PROMOTED`, `RELEASED`, `PRODUCTION_READY`, `VALUE_READY`, revenue/market-fit, or higher claim fields is rejected.
- `gate-report.json` schema `nexus.core-v1.tg8-gate-report.v1` binds threshold and every input hash, matrix counts, run identities, denominators, false-certification count/case IDs, compatibility/conformance/rollback summaries, classification, reasons, claim ceiling, generated-at and report hash. It is deterministically recomputed; caller classification/counts are never trusted.
- Human-time measurement, pilot cohort selection, commercial/value claims, and Nexus-overhead experiments are explicitly excluded and require a separately authorized future card.

## Mandatory source audit

Audit TG-6 install/rollback, TG-7 corpus/shadow, protocol/schema axes, compatibility, explicit RC/Stable thresholds, and all protocol evidence gates. Human-time logs are out of scope.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Remove the real-vertical receipt, cross-repository oracle/denominator, client-conformance, compatibility, upgrade, or rollback artifact; adjudication remains at the lower maturity and never infers Stable/release/production/value.

## Implementation constraints

Proof-only verification; preserve protocol/schema separation and claim ceiling; no Owner decision is inferred.

## GREEN and regression gates

AC-016 passes only when the accepted TG-7 cross-repository gate and every protocol compatibility/conformance/upgrade/rollback gate are revision-bound and independently accepted.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG8-01 | TARGET_ROOT | `uv run pytest -qq tests/benchmark/test_core_v1_tg8_protocol_gate.py` | strict schemas, thresholds and hostile RC/Stable guard | all tests pass, including missing/tampered/stale/axis-confused/incompatible/rollback/promotion negatives |
| TG8-02 | TARGET_ROOT | `uv run pytest --collect-only -q tests/benchmark/test_core_v1_tg8_protocol_gate.py` | prove negative matrix discovery | intended cases listed |
| TG8-03 | TARGET_ROOT | `uv run python -m product.protocol.compatibility_gate --thresholds /private/tmp/nexus-core-v1-evidence/tg8/thresholds.json --expected-thresholds-sha256-file /private/tmp/nexus-core-v1-evidence/tg8/thresholds.sha256 --compatibility /private/tmp/nexus-core-v1-evidence/tg8/protocol-compatibility.json --conformance /private/tmp/nexus-core-v1-evidence/tg8/client-conformance.json --upgrade-rollback /private/tmp/nexus-core-v1-evidence/tg8/upgrade-rollback.json --open-issues /private/tmp/nexus-core-v1-evidence/tg8/open-issues.json --tg4-receipt /private/tmp/nexus-core-v1-evidence/tg8/tg4-receipt.json --tg5-receipt /private/tmp/nexus-core-v1-evidence/tg8/tg5-receipt.json --tg6-receipt /private/tmp/nexus-core-v1-evidence/tg8/tg6-receipt.json --tg7-selection /private/tmp/nexus-core-v1-evidence/tg7/selection.json --tg7-corpus /private/tmp/nexus-core-v1-evidence/tg7/corpus.json --tg7-shadow /private/tmp/nexus-core-v1-evidence/tg7/shadow-receipt.json --tg7-report /private/tmp/nexus-core-v1-evidence/tg7/report.json --stable-run-1 /private/tmp/nexus-core-v1-evidence/tg8/stable-run-1.json --stable-run-2 /private/tmp/nexus-core-v1-evidence/tg8/stable-run-2.json --stable-run-3 /private/tmp/nexus-core-v1-evidence/tg8/stable-run-3.json --report /private/tmp/nexus-core-v1-evidence/tg8/gate-report.json` | bounded RC/Stable adjudication | exact immutable inputs and allowed state only; never promotes |
| TG8-04 | TARGET_ROOT | `git diff --check` | integrity | exit 0 |

## Physical evidence

Capture protocol candidate, corpus/shadow, TG5/TG6/TG7 receipts, compatibility and client-conformance matrices, upgrade/rollback observations, hashes, reviewer attempt, and bounded evidence-readiness adjudication. Do not capture or infer human-time/value data here.

## Independent review

Fresh reviewer verifies the accepted AC-010 dependency plus AC-016 gates, denominator, external identity, claim ceiling, and no promotion authority.

## Exit conditions

- **PASS:** evidence supports exactly `PROTOCOL_RC_EVIDENCE_READY` or `PROTOCOL_STABLE_EVIDENCE_READY`; no promotion is performed.
- **BLOCK:** any compatibility, rollback, TG5/TG6/TG7 receipt, zero-false-certification, or gate artifact is missing; any threshold is ambiguous; or a value/pilot claim is attempted.
- **Residual debt:** public/release/production authority remains external.
- **Next gate:** TG-9 may begin only after this bounded maturity evidence is independently accepted; protocol promotion/release/public actions remain separate.
