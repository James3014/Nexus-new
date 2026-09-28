# Apple FM Evidence Filter A/B V1

Status: **COMPLETE / REJECT_EVIDENCE_FILTER**

Claim ceiling: `EXPERIMENT_ONLY_NO_ROUTING_AUTHORITY`

## Frozen subject

- Canonical base: `4ca491f07b98054be65f6fd8d87c6d167cb59849`
- Frozen experiment subject: `af24e653d27573a325c65bd692c01082c6e9d6f7`
- Subject tree: `f90d2508216906f2da5588b8e6c6a1be8b5758da`
- Cohort SHA-256: `16a636d8e8eeec69c0586cd6893b555488ea84ce6eeea01ef254ec09a8c29b4f`
- Cohort: 34 real MAT-B comparisons, 10 calibration / 24 holdout
- Ground-truth oracle: repository implementation `scripts/ops/build_heep_mat_b_live_report.py::_decision`
- Source report: `docs/reports/NEXUS_HEEP_MAT_B_LIVE_REPORT_2026-05-20.json`

The benchmark uses mixed outcomes and does not permit constant-label guessing.

## Arms

- A0: all 20 raw evidence spans -> Gemini 3.8 Flash low.
- A1: deterministic static field filter -> Gemini 3.8 Flash low.
- A2: Apple FM x2 counterfactual KEEP/DROP filter; invalid FM output fails closed to KEEP -> Gemini 3.8 Flash low.

Apple FM classification: 680 physical `/usr/bin/fm respond` calls, network denied, 100% syntactically valid KEEP/DROP outputs.

## Holdout results

| Metric | A0 full evidence | A1 deterministic | A2 Apple FM x2 |
| --- | ---: | ---: | ---: |
| Cases | 24 | 24 | 24 |
| Critical evidence recall | 100% | 100% | **0%** |
| Cases retaining all critical evidence | 24/24 | 24/24 | **0/24** |
| Mean selected spans | 20.0 | 15.0 | **0.0417** |
| Mean prompt chars | 2032.0 | 1826.7 | 1289.3 |
| Prompt-char reduction vs A0 | — | **10.10%** | **36.55%** |
| Completed-call semantic accuracy | 100% | **100%** | **34.78%** |
| System accuracy | 95.83% | **100%** | **33.33%** |
| Infra errors | 1 | 0 | 1 |
| p50 latency | 6.210 s | 6.164 s | 6.028 s |
| p95 latency | 10.335 s | 10.022 s | 12.861 s |

## FM filter behavior

On the 24-case holdout:
- critical spans: 223 KEEP/DROP decisions -> **223 DROP, 0 KEEP**
- noncritical spans: 257 decisions -> **256 DROP, 1 KEEP**
- FM output syntax validity: 100%

So this is not an output-contract problem. The model consistently misunderstood the evidence-preservation objective despite a frozen counterfactual prompt.

A2 downstream semantic errors on completed calls: 15. A0: 0. A1: 0.

## Gates

- A2 critical evidence recall = 100%: **FAIL**
- A2 completed accuracy non-inferior within 1 pp: **FAIL**
- A2 prompt chars reduced >=30%: PASS
- A2 infra errors <= A0: PASS

Final verdict: **REJECT_EVIDENCE_FILTER**.

## Interpretation

Apple FM achieved the desired compression magnitude only by deleting decision-critical evidence. It therefore has no safe evidence-filter utility under this tested contract.

The deterministic A1 baseline is superior for this decision family: it preserves all critical evidence and downstream correctness with a modest 10.1% prompt-character reduction. That reduction comes without introducing a model-dependent evidence-loss failure mode.

This experiment does not authorize routing, CapabilityPlanner, Workforce Admission, merge, release, or production changes.
