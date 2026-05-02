# Nexus Public Value Comparison

## Main Evidence

| Model | Scope | Gate | Bare verified | Nexus verified | Lift | Claim status |
| :--- | :--- | :--- | ---: | ---: | ---: | :--- |
| Gemini 3 Flash | 3x1 auto-route smoke | markdown PASS; bundle PASS; nexus_public_benchmark_evidence_bundle_v2 | 2/3, 66.7% | 3/3, 100.0% | 33.3% | public smoke candidate |

## Cost

| Model | Wall time | Model calls | Tokens |
| :--- | :--- | :--- | :--- |
| Gemini 3 Flash | 23.81s -> 25.69s | 1.00 -> 1.00 | 26004 -> 24427 |

## Route Cost Ledger

Scope: measured benchmark telemetry, not provider billing cost.

| Model | Ledger | Route decision | Recommended flow | Chosen flow | Capability stack |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Gemini 3 Flash | nexus_route_cost_ledger_v1 | 1.00 | 1.00 | 1.00 | selected 18.67, required 5.00, conditional 13.67 |

## Claim Boundaries

- Gemini 3 Flash: smoke final gate is blocked only by missing public disclosure manifest; evidence bundle public claim gate PASS

## Final Report Gate

- Final gate: FAIL
- Final gate failures: Gemini 3 Flash:disclosure_not_pass
