# Nexus Local-Model Research State — Current

Status date: **2026-09-29**

This document is the current research-state index for bounded local-model investigation in Nexus. It records settled research conclusions and reopen conditions. It is **not** routing, CapabilityPlanner, Workforce Admission, model-admission, release, or production authority.

## Current frontier

### Apple Foundation Models (`/usr/bin/fm`)

- **Triage verdict:** `WATCH`
- **Allowed research role:** `EXPERIMENT_ONLY`
- **Active Apple FM experiment:** `NONE`
- **Mainline research state:** `STOPPED_PENDING_REOPEN_TRIGGER`
- **Routing/admission status:** `NOT_AUTHORIZED`
- **Current research question:** no active question; prior adoption hypotheses are settled negative for the tested roles.

### What is settled

1. **Physical execution is viable on the tested host.**
   - Tested host: Apple M5 Pro / 64 GB.
   - Tested runtime: `/usr/bin/fm`.
   - Network-deny execution was physically verified in the bounded experiments.
   - The experiments establish runtime viability only; they do not establish Nexus admission.

2. **Local-first call avoidance has material upside, but the tested acceptance mechanism is unsafe.**
   - In `APPLE_FM_NEXUS_VALUE_AB_V2`, both FM x2 and FM x4 reduced online calls from 120 to 41: **65.83% reduction**.
   - The same arms produced **14 false local passes**, local-accept precision **82.28%**, and final system accuracy **80.00%** versus **87.50%** for the no-FM arm.
   - The quality regression remains after separating online transport failures from completed-call semantic quality.
   - Result: `REJECT_FOR_ROUTING`.

3. **FM x4 did not add semantic value over FM x2 in the tested cascade.**
   - A2 and A4 had identical local acceptance sets and identical FM correctness.
   - FM-only latency was worse for x4 in the value experiment.
   - Current bounded operating conclusion: if Apple FM is ever reopened for experimentation, x2 is the default physical test point; x4 requires a new burst-specific hypothesis.

4. **Evidence filtering failed the safety prerequisite.**
   - In `APPLE_FM_EVIDENCE_FILTER_AB_V1`, holdout critical-evidence recall was **0%** for Apple FM x2.
   - All **223/223** critical spans in the holdout were dropped.
   - Downstream completed-call semantic accuracy fell to **34.78%**.
   - The deterministic baseline preserved **100%** critical evidence and **100%** completed-call semantic accuracy while reducing prompt characters by **10.10%**.
   - Result: `REJECT_EVIDENCE_FILTER`.

5. **The successor local-completion experiment is intentionally not active.**
   - `APPLE_FM_VERIFIABLE_LOCAL_TASK_V1` is `SKIPPED_BY_PREREQUISITE_GATE`.
   - The prerequisite evidence-filter safety gate failed, so widening Apple FM responsibility would contradict the frozen experiment sequence.

## Current Nexus decision

Apple Foundation Models do **not** currently justify additional Nexus runtime complexity for any tested mainline role.

Do not promote Apple FM into:

- CapabilityPlanner routing;
- Workforce Admission or model admission;
- a default local worker;
- local semantic completion;
- evidence filtering / evidence-preservation compression;
- production or release configuration.

Do not reopen Apple FM merely for:

- higher tokens/sec;
- more worker-count scaling;
- prompt tuning;
- self-confidence thresholds;
- another heuristic acceptance rule.

The present evidence supports **focus preservation**: keep Apple FM available as a watched external/local capability, but spend no additional mainline research budget until a reopen trigger occurs.

## Reopen triggers

Re-evaluate Apple FM only if at least one of these conditions becomes true:

1. **Material model/runtime generation change**
   - Apple changes the on-device model/runtime in a way that could plausibly change semantic reliability, context handling, structured generation, or bounded reasoning quality.
   - Requalification must bind the exact OS, model/runtime identity, hardware, and executable identity.

2. **New independently verifiable semantic task family**
   - A real Nexus task appears where deterministic code is not already the better solution;
   - the task genuinely requires semantic interpretation;
   - source-backed ground truth exists; and
   - correctness can be independently verified without using Apple FM self-confidence as the verifier.

3. **New same-harness evidence showing a material decision delta**
   - The candidate must beat the deterministic incumbent on a bounded role;
   - preserve zero or near-zero material false-safe behavior under the predeclared gate;
   - preserve downstream correctness; and
   - produce a material cost, call, token, latency, or capacity benefit.

Until one of these triggers exists, the Apple FM research frontier remains closed.

## Measurement gaps that do not reopen the line by themselves

- Exact online token / quota savings remain `UNKNOWN` because the tested Agy wrapper did not expose token usage.
- Online Agy account-pool tail latency is a separate transport/reliability issue and must not be treated as Apple FM semantic evidence.
- These gaps should be addressed only when they materially affect another active experiment; they are not reasons to rerun Apple FM adoption tests.

## Durable evidence

### Value A/B

Branch: `exp/apple-fm-value-ab-v1`

- Evidence commit: `8eb37956e397fe551c6e53e13362d37248f1989e`
- Frozen V2 subject: `fafa1a6fa909175bb776b6f1f3b3ed57e4b84b2f`
- Report: `artifacts/experiments/apple_fm_value_ab_v2/REPORT.md`
- Cohort SHA-256: `23db354e2bed5d17c493cddbd3096c7dde22ea3f467d1ab84816fd895fba0112`
- Result SHA-256: `fa852e37ac78ef5848f69b53f081daa29357d72f2a84fd7b69750858c611512b`

### Evidence-filter A/B

Branch: `exp/apple-fm-evidence-filter-v1`

- Frozen subject: `af24e653d27573a325c65bd692c01082c6e9d6f7`
- Result-seal commit: `015f953e0e0c1c86fb740a26bc85e11d38cef666`
- Closeout commit: `f5f7d2c8cb5f2186dac22aa7b89ee92cd3efbd43`
- Report: `artifacts/experiments/apple_fm_evidence_filter_ab_v1/REPORT.md`
- Successor gate: `artifacts/experiments/apple_fm_verifiable_local_task_v1_gate.json`
- Cohort SHA-256: `16a636d8e8eeec69c0586cd6893b555488ea84ce6eeea01ef254ec09a8c29b4f`
- Result SHA-256: `d60e6b662ecb11a46326ecad6381b5a26754c1cd38ce3cd2f662cca8d9d99515`

## Research-state semantics

- `WATCH` means the candidate remains worth noticing if a reopen trigger occurs; it is not an active pilot.
- `EXPERIMENT_ONLY` means no experiment result grants routing, admission, acceptance, merge, release, or production authority.
- Historical experiment branches remain evidence. They are not current runtime configuration.
- New evidence may supersede this state only through a newly bound experiment or an explicit Owner decision with appropriate evidence.

## Next gate

`NO_ACTIVE_APPLE_FM_GATE`

The next Apple FM action is not another benchmark. The next gate exists only when a listed reopen trigger is satisfied.
