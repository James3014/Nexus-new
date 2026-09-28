# Apple FM Verifiable Local Task V1

Status: **COMPLETE / DETERMINISTIC_DOMINATES**

Claim ceiling: `EXPERIMENT_ONLY_NO_ROUTING_AUTHORITY`

## Goal

Test whether Apple FM adds practical value for a source-backed, independently verifiable local task: real Agy execution outcome triage.

The experiment does not ask FM to make routing, retry, account-rotation, Workforce, or production decisions.

## Frozen subject

- Nexus base: `4ca491f07b98054be65f6fd8d87c6d167cb59849`
- R1 freeze: `e64f588815b5f3e029813aab25390cf5d2688923`
- R2 timeout-contract correction: `4a9569c20d0d167aaf2796ae3256e12cf2bcfc22`
- R2 tree: `8b85bcd5a7b78471790d2ae27f2d44c77b6addc0`
- Cohort SHA-256: `063ff493a3f90c99fbd79ae7209fd1398326fa370d2815f27abe51f0b8fb0151`
- Harness SHA-256: `77e3f626195bd3b5af06007d0121d795a489bf5a498c62a756464c84aa225b83`
- Result SHA-256: `6c4098ccc67fe1b1589a40921fad8e418ccec2971e09fdc33b1f6694b647c627`

## Corpus

50 unique physical Agy observations from the prior Apple FM value A/B:
- 25 SUCCESS
- 25 TIMEOUT

Each observation is bound to `arm:case_id`.
Account/lease hashes are redacted.
No email addresses are included.
The structured `failure_kind` answer field is removed from model-visible text.

The available real corpus did not contain enough independent examples of quota/auth/rate-limit/etc. outcomes for a credible multi-class semantic benchmark. Those classes were not synthesized.

## Deterministic baseline

The baseline uses the same model-visible event text and existing execution contract:
- structured `status=completed` -> SUCCESS
- explicit timeout text -> TIMEOUT
- failed receipt with wall time >= the frozen 120s timeout contract -> TIMEOUT
- otherwise UNKNOWN

This is consistent with the existing Nexus external-worker/Agy timeout semantics and tests.

Result:
- Accuracy: **50/50 = 100%**
- Mean classification latency: **0.173 microseconds**

## Apple FM x2

Physical runtime:
- `/usr/bin/fm`
- runtime SHA-256: `f429257df40311ba075484be92c273ab4e882e5694f970c621a4d606b3a956d0`
- workers: 2
- network-deny sandbox: enabled

Result:
- Accuracy: **50/50 = 100%**
- Output-contract validity: **100%**
- False classifications: **0**
- Mean latency: **477.9 ms**
- p50 latency: **440 ms**
- p95 latency: **513 ms**
- Batch wall time: **12.053 s**

## Gate result

Passed:
- deterministic accuracy = 100%
- Apple FM accuracy >=95%
- Apple FM false classifications = 0
- deterministic path faster than Apple FM

Final verdict: **DETERMINISTIC_DOMINATES**.

## Interpretation

Apple FM can correctly classify this bounded real task, but it adds no useful capability. The same observable execution evidence is already classified exactly by deterministic runtime logic at negligible cost and latency.

Therefore provider/Agy SUCCESS-vs-TIMEOUT triage is not a useful Apple FM integration target.

The broader multi-class failure-triage hypothesis remains unproven because current real historical evidence is too sparse outside SUCCESS/TIMEOUT. The experiment intentionally did not manufacture synthetic quota/auth/rate-limit events to make the benchmark look broader.

No CapabilityPlanner, Workforce Admission, routing, retry authority, account-rotation authority, runtime default, release, or production behavior changed.
