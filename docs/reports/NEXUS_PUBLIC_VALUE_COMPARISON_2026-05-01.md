# Nexus Public Value Comparison

## Main Evidence

| Model | Scope | Gate | Bare verified | Nexus verified | Lift | Claim status |
| :--- | :--- | :--- | ---: | ---: | ---: | :--- |
| Gemini 3 Flash | 12x1 | markdown PASS; bundle PASS; nexus_public_benchmark_evidence_bundle_v2 | 8/12, 66.7% | 12/12, 100.0% | 33.3% | public candidate |
| Gemini 3.1 Pro | 12x2 | markdown PASS; nexus_public_benchmark_evidence_bundle_v1 | 5/24, 20.8% | 24/24, 100.0% | 79.2% | historical observation |
| GPT-5.5 | 8x2 | markdown PASS; bundle PASS; nexus_public_benchmark_evidence_bundle_v2 | 8/16, 50.0% | 16/16, 100.0% | 50.0% | performance candidate |

## Cost

| Model | Wall time | Model calls | Tokens |
| :--- | :--- | :--- | :--- |
| Gemini 3 Flash | 32.57s -> 49.16s | 1.00 -> 1.08 | 27432 -> 30813 |
| Gemini 3.1 Pro | 17.98s -> 48.49s | 1.00 -> 1.79 | 21162 -> 39663 |
| GPT-5.5 | 9.28s -> 65.50s | 1.00 -> 1.00 | 12699 -> 8540 |

## Claim Boundaries

- Gemini 3 Flash: none
- Gemini 3.1 Pro: none
- GPT-5.5: none

## Final Report Gate

- Final gate: FAIL
- Final gate failures: Gemini 3.1 Pro:bundle_schema_not_v2, Gemini 3.1 Pro:public_gate_not_pass, manifest_hash_mismatch, scope_mismatch
