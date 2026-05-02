# Nexus Public Value Comparison

## Main Evidence

| Model | Scope | Gate | Bare verified | Nexus verified | Lift | Claim status |
| :--- | :--- | :--- | ---: | ---: | ---: | :--- |
| Gemini 3 Flash | 12x2 | markdown PASS; bundle PASS; nexus_public_benchmark_evidence_bundle_v2 | 13/24, 54.2% | 24/24, 100.0% | 45.8% | final |
| Gemini 3.1 Pro | 12x2 | markdown PASS; bundle PASS; nexus_public_benchmark_evidence_bundle_v2 | 10/24, 41.7% | 24/24, 100.0% | 58.3% | final |
| GPT-5.5 | 12x2 | markdown PASS; bundle PASS; nexus_public_benchmark_evidence_bundle_v2 | 13/24, 54.2% | 24/24, 100.0% | 45.8% | final |

## Cost

| Model | Wall time | Model calls | Tokens |
| :--- | :--- | :--- | :--- |
| Gemini 3 Flash | 34.12s -> 59.05s | 1.00 -> 1.17 | 27128 -> 33329 |
| Gemini 3.1 Pro | 20.76s -> 38.14s | 1.00 -> 1.04 | 22253 -> 23530 |
| GPT-5.5 | 12.63s -> 17.41s | 1.00 -> 1.00 | 6618 -> 13579 |

## Route Cost Ledger

Scope: measured benchmark telemetry, not provider billing cost.

| Model | Ledger | Route decision | Recommended flow | Chosen flow | Capability stack |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Gemini 3 Flash | nexus_route_cost_ledger_v1 | 1.00 | 1.00 | 1.00 | selected 18.33, required 5.00, conditional 13.33 |
| Gemini 3.1 Pro | nexus_route_cost_ledger_v1 | 1.00 | 1.00 | 1.00 | selected 18.33, required 5.00, conditional 13.33 |
| GPT-5.5 | nexus_route_cost_ledger_v1 | 1.00 | 1.00 | 1.00 | selected 17.42, required 5.00, conditional 12.42 |

## Claim Boundaries

- Gemini 3 Flash: none
- Gemini 3.1 Pro: none
- GPT-5.5: none

## Final Report Gate

- Final gate: PASS
- Final gate failures: none
