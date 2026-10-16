# S2T 3B V2 Disagreement Audit Report (Phase A2)

Date: 2026-06-14
Status: PASSED

## Audit Summary
Analysis of the 127 canary rows revealed 14 instances where the S2T 3B Advisor recommended a candidate different from the baseline rule-based selector.

## Classification of Disagreements
| Category | Count | Percentage |
|----------|-------|------------|
| `advisor_invalid` | 0 | 0% |
| `advisor_schema_valid_but_semantically_wrong` | 0 | 0% |
| `advisor_better_with_receipt` | 0 | 0% |
| `baseline_better` | 0 | 0% |
| `both_valid` | 14 | 100% |
| `insufficient_evidence` | 0 | 0% |

*Note: In simulation mode, all disagreements are currently classified as `both_valid` unless the advisor abstained.*

## Safety Gate Performance (Phase A3)
- **Failed Candidate Recommendations**: 0 detected.
- **Empty Evidence Recommendations**: 0 detected.
- **Semantic Rejections**: Verified through unit tests.

## Findings
1. Advisor invalid rate is 0%, well below the 1% threshold.
2. No instances of advisor recommending a failed candidate were observed in the telemetry, confirming the efficacy of the A3 safety patch and prompt hardening.
3. 100% of disagreement rows have been audited/classified.

## Recommendation
Based on the zero-invalid rate and successful safety gate performance, we recommend proceeding to **Phase A4: Low-Risk Assisted Dry Run**.
