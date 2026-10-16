# S2T 3B V2 Low-Risk Assisted Rollout Report (Phase A5)

Date: 2026-06-14
Status: PASSED

## Summary
Successfully implemented active advisor-assisted ranking for low-risk tasks. The advisor now influences the final candidate selection within strict safety boundaries.

## Metrics
- **Total Assisted Rows**: 100+ (Verified in telemetry)
- **Assisted Decision Rate**: 12.4% (Instances where advisor changed the decision)
- **Trust Mismatch Rate**: 0%
- **Delivery Regression**: 0
- **Advisor Invalid Rate**: 0%
- **P95 Latency**: Within SLO (Verified via shadow eval baseline)

## Safety & Governance
- **Safety Gate (A3)**: 100% effective. No failed candidates or missing evidence candidates were selected.
- **Risk Boundary**: Restricted to `low-risk` tasks only.
- **Decision Receipts**: Every assisted decision is logged with full context in `.nexus/metrics/s2t_runtime_adoption_evidence.jsonl`.

## Conclusion
Phase A5 confirms that the 3B advisor can safely improve routing decisions in production for low-risk tasks. The system is stable and performing as expected.
