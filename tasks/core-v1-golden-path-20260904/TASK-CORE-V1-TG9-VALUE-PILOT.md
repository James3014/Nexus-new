# TASK-CORE-V1-TG9-VALUE-PILOT — Paired design-partner usability and value evidence

- **Campaign:** `CAMPAIGN-NEXUS-CORE-V1-GOLDEN-PATH-01`
- **Bounded authority:** Ready Issue `#773`
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
- **Required initial verification:** verify TG-8 accepted receipt and a clean controller-bound integration HEAD/tree containing exact accepted TG-1 through TG-8 ancestry, the human study owner/outreach authority, resolved evidence root, consent/study schemas, fixed synthetic fixtures, privacy controls and preregistration template. Real partner eligibility/consent/observations are required only for final AC-017 acceptance, not Luna tooling dispatch.
- **Freshness rule:** re-read protocol/runtime/package revisions, partner consent/status, paired subjects, oracle, time logs, overhead, and trust outcomes before every report update and final acceptance

## MCP execution profile

- **App/server and action snapshot:** not applicable; `DIRECT_DELEGATED` Luna implementation/analysis under Ready Issue #773, with controller-owned human coordination
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

- Real evidence is controller-owned under resolved `$XDG_STATE_HOME/nexus-core/studies/core-v1-tg9`, falling back to `~/.local/state/nexus-core/studies/core-v1-tg9`, with directories `0700` and files `0600`; `/private/tmp` is synthetic-only. For this campaign host `XDG_STATE_HOME` is unset, so the controller-bound root is `/Users/jameschen/.local/state/nexus-core/studies/core-v1-tg9`; any environment change requires rebind before execution. Exact files are `study-manifest.json`, `partner-eligibility.json`, `consent-receipts.json`, `paired-observations.jsonl`, `trust-comparison.json`, `continuation-paid-signal.json`, `privacy-scan.json`, and `report.json`, each schema-versioned/canonical/hash-bound with independent durable readback.
- The human study owner is the Owner or a specifically designated human operator. Luna and controller automation are forbidden to contact/recruit partners, present consent, negotiate, collect payment, authenticate signals, or impersonate anyone; Luna receives only synthetic/schema fixtures. Human owner handles outreach/consent and supplies sanitized, pseudonymous evidence to the deterministic verifier.
- `partner-eligibility.json` schema `nexus.core-v1.tg9-eligibility.v1` includes every consented/enrolled partner, including zero-observation partners, and preregisters 3–5 narrow-ICP partners, inclusion/exclusion rules, role/organization-size/workflow class, selection timestamp, reserve list and eligibility receipt hash before observations. No post-hoc replacement after first observation except preregistered reserve; every zero-observation, replacement and attrition case is reported.
- `consent-receipts.json` schema `nexus.core-v1.tg9-consent.v1` binds study/partner pseudonym, consent version/scope/time, data classes, retention, withdrawal channel and issuer/authority receipt. Withdrawal stops collection immediately, removes that partner from analysis and deletes linkable raw data according to consent; aggregate/report is regenerated with attrition. A privacy incident, missing consent, or unauthorized outreach stops and invalidates affected evidence.
- Design is preregistered within-subject matched-pair AB/BA with distinct difficulty-matched tasks, blinded authorized oracle and deterministic assignment: sort partner/pair IDs, compute SHA-256 of `study_id|partner_id|pair_id|20260904`, low bit selects AB/BA, and require arm-count difference <=1 per partner. Washout is at least 24 hours between pair arms with no access to the prior task/output. Each pair binds protocol/runtime/package/source revision, task family/difficulty, Acceptance Contract/rubric/oracle, assignment/order, timestamps, attempts and pair hash. Each partner needs >=8 valid pairs; cohort >=24 valid pairs, >=3 valid partners, >=4 complete weeks and <=5 partners/8 weeks.
- Timing uses monotonic nanoseconds converted to integer milliseconds with declared start/stop events. `baseline_human_ms` includes all baseline reading, verification, follow-up, retry and rework; `nexus_human_ms` includes active human review; `nexus_read_followup_ms` includes all Nexus-output reading/follow-up/rework; `total_assisted_ms = nexus_human_ms + nexus_read_followup_ms`. Both arms exclude only preregistered external interruptions and retain failed/retried work. Recorder and observation provenance/hash are mandatory.
- Pair improvement is `(baseline_human_ms - total_assisted_ms) / baseline_human_ms`. Partner statistic is median across all valid preregistered pairs; cohort statistic is equal-weight median of partner medians. Bootstrap 95% percentile interval resamples partners with replacement, 10,000 replicates, deterministic seed `20260904`; report estimate and interval descriptively. Pass requires cohort median >=30%, >=70% valid pairs positive, no partner median <0%, and no post-hoc outlier removal. No significance/market-wide inference is claimed.
- Trust outcomes are `CORRECT`, `FALSE_ACCEPT`, `FALSE_REJECT`, `UNRESOLVED` under a fixed blinded oracle artifact. `oracle-receipt` binds study/task/rubric/oracle result hash, authorized issuer, Ed25519 algorithm/key/signature, issued/expires/revoked state and external verification receipt/hash; missing/unverified oracle is `UNRESOLVED`. Zero-margin noninferiority requires assisted false accepts =0 and `(FALSE_ACCEPT+FALSE_REJECT+UNRESOLVED)/all_assigned_pairs` not exceed baseline under the same denominator; no partner may add high-risk error and oracle/rubric cannot change.
- Analysis is modified intent-to-treat: every consented/enrolled partner, including zero-observation, appears in attrition/accounting; threshold uses only complete valid pairs under preregistered rules with every exclusion hash. Closed exclusions: consent withdrawal, corrupted timing before outcome, protocol/runtime drift before pair, missing blinded oracle, privacy invalidation. Interim peeking, cohort/task/rubric changes, semantic-failure exclusion and cherry-picking are forbidden.
- Pseudonyms are HMAC-SHA256 with an Owner-held random pepper; the lookup/pepper stays in a separate owner-controlled `0700/0600` store and never reaches repo, Luna, study evidence or reports. Evidence permits no names, emails, organization names, account IDs, URLs, free text, raw code/private repositories, secrets, IP/device data, or quasi-identifiers. Retention/deletion follows consent; reidentification outside designated human owner is forbidden.
- Accepted continuation/paid signals are only authorized signed pilot continuation, signed LOI/order, paid invoice/payment-processor receipt, or renewal within the study window. `nexus.core-v1.tg9-signal.v1` binds pseudonymous partner/study, type, issuer/authority, observed/issued/expiry/revocation times, Ed25519 algorithm/key/signature hash, signed payload hash, external verification receipt schema/hash, signal hash and independent verifier receipt. Wrong/stale/revoked/self-attested/verbal/worker-generated signals are invalid; no revenue recognition, market-fit, production or public claim follows.
- Report schema `nexus.core-v1.tg9-report.v1` binds TG-8 receipt, all input hashes, protocol/runtime/package revisions, cohort/partner/pair denominators, assignment balance, timing equations, exclusions/attrition, partner/cohort statistics/interval, trust table/oracle receipts, privacy scan, continuation/paid signal, state/reasons, claim ceiling, generated-at and report hash. Allowed states are `PAIRED_USABILITY_VALUE_EVIDENCE_READY`, `SYNTHETIC_ONLY`, `MISSING_EVIDENCE`, `INVALID_EVIDENCE`, `UNVERIFIABLE`; `SYNTHETIC_ONLY` requires `synthetic=true`, carries no external evidence/value claim and can never satisfy AC-017. Any alternate value-ready, promotion, revenue, market-fit or production field is rejected.
- Stop conditions: trust regression/high-risk false accept, privacy incident, invalid/missing consent, protocol/runtime drift, invalid timing, changed oracle/rubric, unregistered interim peek, attrition below minimum, or missing signal. No threshold can be claimed until the complete 4–8 week window and all denominators are final.

## Mandatory source audit

Audit TG-8 acceptance, study rubric, partner eligibility/consent, privacy boundary, pair identity, timing method, overhead capture, trust oracle, exclusions, denominator, aggregation, and continuation/paid evidence before implementation or reporting.

## Start-state classification

`REVERIFY_AFTER_DEPENDENCY`

## RED or existing-guard proof

Remove or alter the pair identity, denominator, consent/authority, overhead, trust oracle, cohort size, duration, threshold, or continuation/paid signal; the verifier must refuse a value-ready result.

## Implementation constraints

Measurement/report tooling is deterministic and claim-bounded. Luna may create only the two listed source/test files and may not edit package metadata, `product/benchmark/__init__.py`, docs, fixtures, or evidence. Luna uses synthetic inputs only. The controller/human study owner alone stages sanitized real evidence and runs final verification. No personal data, pepper/lookup, secrets, raw partner evidence, or outreach enters worker context. Protocol truth, Completion truth, human authority, signal authority and value evidence remain separate.

## GREEN and regression gates

AC-017 passes only when the exact manifest and all paired observations independently recompute to at least 30% improvement including overhead, no trust regression, complete 3–5 partner/4–8 week coverage, and an authenticated continuation or paid signal.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| TG9-01 | TARGET_ROOT | `uv run pytest -qq tests/benchmark/test_core_v1_tg9_value_manifest.py` | eligibility/consent/pairing/timing/trust/privacy/signal/report hostile guard with synthetic fixtures | all tests pass |
| TG9-02 | TARGET_ROOT | `uv run pytest --collect-only -q tests/benchmark/test_core_v1_tg9_value_manifest.py` | prove negative contract discovery | intended cases listed |
| TG9-03 | TARGET_ROOT | `uv run python -m product.benchmark.tg9_value --synthetic-self-test` | worker-safe deterministic preflight | emits only `SYNTHETIC_ONLY` with `synthetic=true` while exercising positive/negative schema paths; cannot emit value-ready |
| TG9-04 | TARGET_ROOT | `uv run python -m product.benchmark.tg9_value --privacy-scan /Users/jameschen/.local/state/nexus-core/studies/core-v1-tg9 --report /Users/jameschen/.local/state/nexus-core/studies/core-v1-tg9/privacy-scan.json` | controller-only privacy/reidentification scan before analysis | zero forbidden fields/data classes; hash-valid scan |
| TG9-05 | TARGET_ROOT | `uv run python -m product.benchmark.tg9_value --manifest /Users/jameschen/.local/state/nexus-core/studies/core-v1-tg9/study-manifest.json --eligibility /Users/jameschen/.local/state/nexus-core/studies/core-v1-tg9/partner-eligibility.json --consent /Users/jameschen/.local/state/nexus-core/studies/core-v1-tg9/consent-receipts.json --observations /Users/jameschen/.local/state/nexus-core/studies/core-v1-tg9/paired-observations.jsonl --trust /Users/jameschen/.local/state/nexus-core/studies/core-v1-tg9/trust-comparison.json --signal /Users/jameschen/.local/state/nexus-core/studies/core-v1-tg9/continuation-paid-signal.json --report /Users/jameschen/.local/state/nexus-core/studies/core-v1-tg9/report.json` | controller-only recomputation of bounded real value evidence | allowed state with exact reasons; ready only if every threshold/evidence gate passes |
| TG9-06 | TARGET_ROOT | `git diff --check` | integrity | exit 0 |

## Physical evidence

Capture TG-8 receipt, protocol/runtime/package revisions, study-manifest hash, pseudonymous pair and attempt identities, consent/authority receipt hashes, fixed oracle/rubric, raw time/overhead hashes, trust comparison, cohort/duration, exclusion/denominator decisions, continuation/paid signal receipt, Candidate commit, and final report hash.

## Independent review

Fresh reviewer verifies AC-017, study preregistration, privacy boundary, exact paired recomputation, overhead, trust parity, cohort/duration, continuation/paid evidence, diff/tests, and claim ceiling.

## Exit conditions

- **PASS:** independently accepted evidence supports only `PAIRED_USABILITY_VALUE_EVIDENCE_READY`.
- **BLOCK:** missing/invalid consent, partner eligibility, pair/denominator, overhead, trust oracle, cohort/duration, threshold, continuation/paid signal, or privacy boundary; any Protocol/release/production/market-fit overclaim.
- **Residual debt:** public/commercial claims, release, production, and broader market validation remain separate authorities.
- **Next gate:** Owner-designated public/commercial decision may consider the bounded evidence; no automatic action follows.
