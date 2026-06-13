# S2T 3B Core Monitoring Baseline (Phase B0)

Date: 2026-06-14
Monitoring Period: [YYYY-MM-DD] to [YYYY-MM-DD]
Status: INITIALIZING

## Executive Dashboard (Templates)
| Metric | Current Value | Target | Status |
|--------|---------------|--------|--------|
| Advisor Usage Rate | 10% | 10% (Fixed) | OK |
| Assisted Decision Rate | TBD | < 20% | PENDING |
| Semantic Rejection Rate | TBD | < 5% | PENDING |
| Fallback-to-Baseline | TBD | - | PENDING |
| Trust Mismatch Rate | 0% | 0% | OK |
| Delivery Regression | 0 | 0 | OK |

## Latency Profile (p95)
- **Baseline Selector**: ~1ms
- **3B Advisor (MPS)**: ~350ms
- **3B Advisor (CPU)**: ~2500ms

## Rollout Control State
```env
NEXUS_S2T_3B_ADVISOR_ENABLED=1
NEXUS_S2T_3B_ASSISTED_MODE=low_risk
NEXUS_S2T_3B_CANARY_RATE=10
NEXUS_S2T_3B_ALLOWED_RISK=low
```

## Observations
- [Observation 1: Initial load impact]
- [Observation 2: Distribution of low-risk tasks]

## Conclusion
Production monitoring is active. Initial telemetry fields are confirmed compliant with the Phase B0 specification.
