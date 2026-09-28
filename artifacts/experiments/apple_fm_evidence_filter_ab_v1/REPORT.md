# Apple FM Evidence Filter A/B V1

Status: **COMPLETE / REJECT_EVIDENCE_FILTER**

Claim ceiling: `EXPERIMENT_ONLY_NO_ROUTING_AUTHORITY`

## Subject
- Base: `4ca491f07b98054be65f6fd8d87c6d167cb59849`
- Frozen experiment commit: `af24e653d27573a325c65bd692c01082c6e9d6f7`
- Tree: `f90d2508216906f2da5588b8e6c6a1be8b5758da`
- Cohort: 34 real MAT-B comparison rows; 10 calibration + 24 holdout
- Cohort SHA-256: `16a636d8e8eeec69c0586cd6893b555488ea84ce6eeea01ef254ec09a8c29b4f`
- Result SHA-256: `d60e6b662ecb11a46326ecad6381b5a26754c1cd38ce3cd2f662cca8d9d99515`
- Oracle: repository `scripts/ops/build_heep_mat_b_live_report.py::_decision`
- Apple FM: `/usr/bin/fm`, SHA-256 `f429257df40311ba075484be92c273ab4e882e5694f970c621a4d606b3a956d0`
- FM workers: 2, network-deny verified
- Online baseline: `~/.local/bin/nexus-agy-dispatch`, Gemini 3.8 Flash, effort low

## Arms
- A0: all 20 raw metric spans.
- A1: deterministic static filter, 15 fields referenced by the canonical decision function.
- A2: Apple FM counterfactual KEEP/DROP per span. Invalid output or timeout would conservatively KEEP.

## Holdout results
| Metric | A0 full | A1 deterministic | A2 Apple FM |
| --- | ---: | ---: | ---: |
| Cases | 24 | 24 | 24 |
| Critical-evidence 100% cases | 24 | 24 | **0** |
| Mean critical recall | 100% | 100% | **0%** |
| Mean selected spans | 20.0 | 15.0 | **0.042** |
| Mean prompt chars | 2032 | 1827 | 1289 |
| Prompt reduction vs A0 | — | 10.1% | **36.6%** |
| Completed Gemini accuracy | 100% | 100% | **34.8%** |
| System accuracy | 95.8% | 100% | **33.3%** |
| Infra errors | 1 | 0 | 1 |

Apple FM performed 680 physical span classifications in 381.8 seconds. All outputs were contract-valid, but the semantic behavior collapsed to:
- `DROP`: 678
- `KEEP`: 2

Thus fail-closed handling for malformed outputs did not help: the failure was valid-but-wrong semantic filtering.

## Gate result
Failed:
- 100% critical-evidence recall
- final completed accuracy non-inferiority within 1 percentage point

Passed:
- prompt character reduction >=30%
- no additional online infrastructure errors relative to A0

Final verdict: **REJECT_EVIDENCE_FILTER**.

## Interpretation
The on-device model can compress context only by dropping information it does not reliably understand as decision-critical. On this source-grounded ordered-policy workload, it removed almost all evidence, including all minimal sufficient critical prefixes in the 24-case holdout.

The deterministic filter was safe and accurate but reduced prompt characters by only ~10%, which is below the experiment's practical-value threshold.

No CapabilityPlanner, Workforce Admission, routing, runtime default, release, or production authority changed.
