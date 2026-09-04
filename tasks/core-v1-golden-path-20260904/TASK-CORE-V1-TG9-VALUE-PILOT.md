# TASK-CORE-V1-TG9-VALUE-PILOT — Paired design-partner usability and value evidence

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#763`
- **Status:** `PLANNED`
- **Source spec:** `SPEC-NEXUS-CORE-V1-FREEZE-001`
- **Source spec SHA-256:** `9ef4b46838251ce86d20d6469901e1f8f02f66ed468655bb446e170ebe90f170`
- **Source groups:** TG-9 Design-partner value
- **Requirements:** REQ-015
- **Acceptance:** AC-017
- **Auto-chain:** `false`
- **Maximum claim:** bounded usability/value claim
- **Depends on:** TASK-CORE-V1-TG8-VALUE-GATE
- **Dependency unlock evidence:** TG-8 independently accepted protocol-maturity evidence receipt
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

Produce revision-bound paired usability and commercial-value evidence from 3–5 narrow-ICP design partners over 4–8 weeks without lowering trust quality or conflating Protocol Stable with product value.

## Observable outcome

paired usability and continuation/paid evidence

## Non-goals

No automatic outreach under another identity, deceptive recruitment, protocol promotion, release, deployment, production declaration, revenue recognition, market-fit claim, or source-repository mutation.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| REQ-015 | value boundary | paired time, overhead, trust parity, cohort/duration, and continuation/paid signal are all required |
| AC-017 | value witness | anecdotes, unpaired measurements, protocol maturity, or omitted overhead cannot become commercial truth |
| DEC-013 | gate separation | cross-repo trust, Protocol Stable, and value remain separate claims |

## Owner decisions

DEC-013. The cohort is 3–5 narrow-ICP design partners, duration is 4–8 weeks, paired human-verification-time improvement threshold is at least 30% including Nexus overhead, trust may not regress, and a continuation or paid signal is required.

## Source and start state

- **Workspace/root:** `REVERIFY_AFTER_DEPENDENCY`
- **Branch:** `REVERIFY_AFTER_DEPENDENCY`
- **Starting HEAD:** `REVERIFY_AFTER_DEPENDENCY`
- **Dirty baseline:** `REVERIFY_AFTER_DEPENDENCY`
- **Required initial verification:** verify TG-8 accepted receipt, exact protocol/runtime/package identity, approved privacy-safe study materials, and eligible partner evidence
- **Freshness rule:** re-read protocol/runtime/package revisions, partner consent/status, paired subjects, oracle, time logs, overhead, and trust outcomes before every report update and final acceptance

## MCP execution profile

- **App/server and action snapshot:** not applicable; `DIRECT_DELEGATED` Luna implementation/analysis under Ready Issue #763, with controller-owned human coordination
- **Exact required actions:** not applicable
- **Confirmation-required actions:** none
- **Idempotency and attempt rule:** each paired subject has a pseudonymous stable pair ID and unique attempts; duplicates or changed definitions never overwrite prior observations
- **Reconnect reconciliation:** controller re-reads the same worker/session, filesystem, Git, provider, consent, and evidence-report state before retry
- **Transport blocker:** none

## Authority map

- **Selection authority:** Owner/Campaign controller; CapabilityPlanner remains route authority
- **Execution authority:** approved Luna worker may implement bounded measurement/report tooling; controller owns human-facing coordination and never sends secrets or personal data to the worker
- **Verification authority:** independent controller plus authorized human study evidence; worker PASS is not acceptance
- **Receipt authority:** bounded value-study report and hashes only; no Protocol or Completion claim elevation
- **Approval/integration authority:** external Owner-designated public/release/commercial authority only

## Allowed scope

- **Read:** docs/specs/NEXUS_CORE_V1_FINAL_BOUNDARY_AND_GOLDEN_PATH_FREEZE.md;product/protocol;product/benchmark;tests/benchmark;TG8 receipt and public privacy-safe study inputs
- **Edit:** none
- **Create:** product/benchmark/tg9_value.py;tests/benchmark/test_core_v1_tg9_value_manifest.py
- **Delete:** none
- **Maximum touched production files:** 1
- **Maximum touched test files:** 1

## Unknown scan

- **Known facts:** protocol maturity does not prove usability or commercial value; thresholds and study shape are settled.
- **Assumptions requiring verification:** eligible partner consent, paired-task comparability, time-log integrity, human oracle authority, privacy-safe pseudonymization, and continuation/paid evidence.
- **Architecture risks:** value instrumentation could become a third truth owner or leak partner data.
- **Evidence risks:** survivorship bias, unpaired tasks, omitted Nexus overhead, changed rubric, trust regression, or anecdotal signals.
- **Missing owner decision:** none; real partner availability and evidence are execution facts, not decisions to infer.

## Value evidence contract

- Evidence paths are outside the source diff: `/private/tmp/nexus-core-v1-evidence/tg9/study-manifest.json`, `/private/tmp/nexus-core-v1-evidence/tg9/paired-observations.jsonl`, `/private/tmp/nexus-core-v1-evidence/tg9/trust-comparison.json`, `/private/tmp/nexus-core-v1-evidence/tg9/continuation-paid-signal.json`, and `/private/tmp/nexus-core-v1-evidence/tg9/report.json`.
- Study manifest binds protocol/runtime/package revisions, 3–5 pseudonymous partner identities, narrow ICP criteria, consent/authority receipt hashes, 4–8 week observation window, paired tasks, fixed oracle/rubric, measurement method, exclusions, and stop rules.
- Every pair records baseline human verification time, Nexus-assisted verification time, Nexus reading/follow-up overhead, total assisted time, trust outcome, task/revision identity, and observation provenance.
- Pass requires at least 30% paired improvement on the predeclared aggregate, no trust regression under the fixed oracle, the complete cohort/duration, and at least one authenticated continuation or paid signal. Missing evidence lowers only the value claim.
- Raw secrets and personal data are excluded from repository, worker prompts, receipts, logs, and reports; reports use pseudonymous/hash-bound identities.

## Mandatory source audit

Audit TG-8 acceptance, study rubric, partner eligibility/consent, privacy boundary, pair identity, timing method, overhead capture, trust oracle, exclusions, denominator, aggregation, and continuation/paid evidence before implementation or reporting.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Remove or alter the pair identity, denominator, consent/authority, overhead, trust oracle, cohort size, duration, threshold, or continuation/paid signal; the verifier must refuse a value-ready result.

## Implementation constraints

Measurement/report tooling is deterministic and claim-bounded. No personal data or secrets enter source or worker context. Protocol truth, Completion truth, human authority, and value evidence remain separate.

## GREEN and regression gates

AC-017 passes only when the exact manifest and all paired observations independently recompute to at least 30% improvement including overhead, no trust regression, complete 3–5 partner/4–8 week coverage, and an authenticated continuation or paid signal.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG9-01 | TARGET_ROOT | `uv run pytest -qq tests/benchmark/test_core_v1_tg9_value_manifest.py` | value-manifest, privacy, pairing, threshold, and hostile guard | all tests pass |
| TG9-02 | TARGET_ROOT | `uv run python -m product.benchmark.tg9_value --manifest /private/tmp/nexus-core-v1-evidence/tg9/study-manifest.json --observations /private/tmp/nexus-core-v1-evidence/tg9/paired-observations.jsonl --trust /private/tmp/nexus-core-v1-evidence/tg9/trust-comparison.json --signal /private/tmp/nexus-core-v1-evidence/tg9/continuation-paid-signal.json --report /private/tmp/nexus-core-v1-evidence/tg9/report.json` | recompute bounded value evidence | hash-valid report emits only value readiness or exact missing evidence |
| TG9-03 | TARGET_ROOT | `git diff --check` | integrity | exit 0 |

## Physical evidence

Capture TG-8 receipt, protocol/runtime/package revisions, study-manifest hash, pseudonymous pair and attempt identities, consent/authority receipt hashes, fixed oracle/rubric, raw time/overhead hashes, trust comparison, cohort/duration, exclusion/denominator decisions, continuation/paid signal receipt, Candidate commit, and final report hash.

## Independent review

Fresh reviewer verifies AC-017, study preregistration, privacy boundary, exact paired recomputation, overhead, trust parity, cohort/duration, continuation/paid evidence, diff/tests, and claim ceiling.

## Exit conditions

- **PASS:** independently accepted evidence supports only `PAIRED_USABILITY_VALUE_EVIDENCE_READY`.
- **BLOCK:** missing/invalid consent, partner eligibility, pair/denominator, overhead, trust oracle, cohort/duration, threshold, continuation/paid signal, or privacy boundary; any Protocol/release/production/market-fit overclaim.
- **Residual debt:** public/commercial claims, release, production, and broader market validation remain separate authorities.
- **Next gate:** Owner-designated public/commercial decision may consider the bounded evidence; no automatic action follows.
