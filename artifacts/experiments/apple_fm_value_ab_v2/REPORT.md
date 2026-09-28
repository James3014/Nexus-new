# Apple FM Nexus Value A/B V2 — Experiment Report

Status: **COMPLETE / REJECT_FOR_ROUTING**

Claim ceiling: `EXPERIMENT_ONLY_NO_ROUTING_AUTHORITY`

## Frozen subject

- Nexus base: `be6690bd3609e09314118c362fb062b46caf7c82`
- V2 experiment subject: `fafa1a6fa909175bb776b6f1f3b3ed57e4b84b2f`
- V2 subject tree: `a04a60a7961ec82abfbc67ff29fe74c3341b09d9`
- V2 cohort: 120 cases, SHA-256 `23db354e2bed5d17c493cddbd3096c7dde22ea3f467d1ab84816fd895fba0112`
- V2 result SHA-256: `fa852e37ac78ef5848f69b53f081daa29357d72f2a84fd7b69750858c611512b`
- Policy calibration cohort SHA-256: `46819db2b69568fd7dbef5eaa8deb78004a1d7dbc42778f3bff6865a678bc2f1`

V2 used 100 literal-extraction cases from Nexus JSON source paths not used by V1 plus 20 mandatory-escalation controls. Literal source-path overlap with V1 was zero.

## Physical identity

- Host: `JamesdeMac-mini.home`
- Hardware: Apple M5 Pro, 64 GB
- OS/kernel: Darwin 27.0.0
- Runtime: `/usr/bin/fm`
- Runtime SHA-256: `f429257df40311ba075484be92c273ab4e882e5694f970c621a4d606b3a956d0`
- FM identity digest: `52acf12b150e00b2b17168233dbd24ab992631bd178d024ad26da2cdb96fc0a2`
- Network-deny control: PASS

Online baseline used `~/.local/bin/nexus-agy-dispatch`, Gemini 3.8 Flash, effort low, four-way parallelism. Token usage is UNKNOWN because the wrapper does not expose it.

## Arm results

| Metric | A0: no FM | A2: FM x2 | A4: FM x4 |
| --- | ---: | ---: | ---: |
| Tasks | 120 | 120 | 120 |
| Online calls | 120 | 41 | 41 |
| Online-call reduction | 0% | 65.83% | 65.83% |
| Final system accuracy | 87.50% | 80.00% | 80.00% |
| p50 end-to-end latency | 7,303 ms | 948 ms | 1,840 ms |
| p95 end-to-end latency | 125,288 ms | 12,492 ms | 126,070 ms |
| Local accepts | 0 | 79 | 79 |
| False local passes | 0 | 14 | 14 |
| Local accept precision | — | 82.28% | 82.28% |
| Online infra errors | 12 | 6 | 7 |

Paired online-call reduction 95% CI for A2 and A4: **57.5% to 74.17%**.

Paired accuracy delta versus A0 for both A2 and A4: **-7.5 percentage points**, bootstrap 95% CI **[-15.83 pp, +0.83 pp]**.

## Reliability-separated view

A0 completed-online semantic accuracy was 105/108 = **97.22%**. Twelve A0 cases were infrastructure errors, mostly ~120 second Agy timeouts.

Excluding online infrastructure failures from each arm:
- A0: 105/108 = **97.22%**
- A2: 96/114 = **84.21%**
- A4: 96/113 = **84.96%**

Therefore the quality regression is not explained by online timeouts alone.

## Apple FM semantic evidence

Across all 100 V2 literal-extraction cases:
- FM raw semantic accuracy: **86/100 = 86%**
- FM output-contract validity: **100%**
- Oracle-safe local ceiling for this cohort: **86/120 = 71.67% of all tasks**, if a perfect verifier existed.
- Current frozen policy accepted 79 local cases, but only 65 were correct.
- All 21 cases whose observed FM output was longer than 32 characters were correct.
- Among the 79 observed outputs at or below 32 characters, only 65 were correct.

This falsifies the V1-derived heuristic that short observed FM output is a safe acceptance signal.

## FM x2 versus FM x4

Local semantic decisions were identical:
- acceptance-set difference: 0 cases
- FM-correctness difference: 0 cases

FM-only latency:
- x2: p50 **785.5 ms**, p95 **2,269 ms**, mean **967.35 ms**
- x4: p50 **1,503 ms**, p95 **3,197 ms**, mean **1,704.39 ms**

The end-to-end A4 p95 is additionally contaminated by online-route timeout allocation. This run provides no evidence that x4 improves the cascade over x2.

## Safety controls

Mandatory-escalation local accepts:
- A2: **0**
- A4: **0**

So the explicit authority-sensitive bypass worked. The failure was semantic local acceptance inside the permitted bounded task family, not an authority-boundary violation.

## Gate result

Passed:
- online calls reduced by at least 30%

Failed:
- zero false local passes
- quality non-inferiority within 1 percentage point
- A0 completed semantic accuracy >=98% (observed 97.22%)

Final verdict: **REJECT**.

## Interpretation

Apple FM can materially reduce online model calls on this tested workload, but the current local acceptance mechanism cannot tell correct from incorrect FM outputs reliably enough. A 65.8% call reduction is not acceptable when local-accept precision is only 82.3% and final quality drops 7.5 points.

The experiment therefore does **not** support adding Apple FM to formal Nexus routing.

It also does not prove Apple FM has no useful Nexus role. It proves that:
1. concurrency is physically viable;
2. x2 remains the better default than x4 for this workload;
3. call avoidance is potentially large;
4. a trustworthy independent acceptance/verifier signal is still missing.

Literal extraction is also a weak long-term FM target because many such cases are better solved deterministically in code. Any successor experiment should target a genuinely semantic bounded task family with source-backed ground truth, >=95% calibration accuracy, and an independent verifier that is not FM self-confidence.

No production routing, CapabilityPlanner, Workforce Admission, merge, release, or production authority changed.
