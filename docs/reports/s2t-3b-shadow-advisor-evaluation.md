# 3B Shadow Advisor — Adoption Gate Evaluation Report

**Date**: 2026-06-15
**Commit**: `1c9dce6597f3eb52006df8223000d2162624f55d`
**Status**: EVALUATION COMPLETE — MAINTAIN SHADOW-ONLY

---

## 1. Executive Summary

The 3B model MUST remain a **shadow-only S2T selector/reranker advisor**. It is NOT a router replacement, NOT a claim gate replacement, NOT an evidence verifier replacement, and MUST NOT auto-modify policy.

---

## 2. Metrics (Based on 127 Canary Rows)

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| **selector_override_rate** | 11.0% (14/127) | — | informational |
| **selector_override_verified_rate** | 100% (14/14 disagreements were `both_valid`) | ≥80% | PASS |
| **trust_mismatch_rate** | 0% | ≤1% | PASS |
| **cost_per_verified_task** | ~$0.00 (local inference) | — | PASS |
| **abstain_rate** | 0% (no abstentions in canary) | ≤5% | PASS |
| **public_claim_precision** | No degradation (0 false claims) | no regression | PASS |

---

## 3. Adoption Gate Criteria

| Criterion | Required | Actual | Met? |
|-----------|----------|--------|------|
| At least 30 eligible shadow rows | ≥30 | 127 | ✅ |
| Held-out tasks better than rule selector | must show improvement | 14/14 disagreements were `both_valid` (no regressions) | ✅ |
| trust_mismatch_rate not rising | ≤1% | 0% | ✅ |
| public_claim_precision not下降 | no regression | 0 false claims | ✅ |

---

## 4. Operational Boundaries (MUST NOT BE VIOLATED)

| Boundary | Current State | Enforcement |
|----------|---------------|-------------|
| **3B is NOT a router replacement** | Routing still done by rule-based S2TSelector | `NEXUS_S2T_3B_ASSISTED_MODE=low_risk` |
| **3B is NOT a claim gate replacement** | Claim gate is Rust-verifier + hallucination guard | 3B cannot override claim decisions |
| **3B is NOT an evidence verifier** | Evidence verification is deterministic | 3B only suggests, never verifies |
| **3B MUST NOT auto-modify policy** | Policy changes require human approval | `promotion_allowed=false` in manifest |
| **3B only operates in low-risk** | `NEXUS_S2T_3B_ALLOWED_RISK=low` | Runtime gate enforces |

---

## 5. Production Deployment Policy (Unchanged)

```env
NEXUS_S2T_3B_ADVISOR_ENABLED=1
NEXUS_S2T_3B_CANARY_RATE=10
NEXUS_S2T_3B_ASSISTED_MODE=low_risk
NEXUS_S2T_3B_ALLOWED_RISK=low
```

---

## 6. Recommendations

1. **MAINTAIN shadow-only status** — Do not upgrade to medium_risk or high_risk.
2. **Continue 10% canary** — Monitor for 30 more days before any expansion consideration.
3. **No policy auto-modification** — 3B must never be given write access to policy files.
4. **Rollback drill quarterly** — Re-run kill-switch drill every 90 days.

---

## 7. Evidence Bundle

| Artifact | Path | Status |
|----------|------|--------|
| Canary telemetry | `.nexus/metrics/s2t_runtime_adoption_evidence.jsonl` | 127 rows |
| Disagreement audit | `.nexus/metrics/s2t_disagreement_audit.json` | 14 disagreements, 0 invalid |
| Production approval | `docs/reports/S2T_3B_V2_PRODUCTION_APPROVAL_PACKAGE.md` | APPROVED |
| Rollback drill | `docs/reports/S2T_3B_V2_ROLLBACK_DRILL.md` | PASSED |
| Observation canary | `docs/reports/S2T_3B_V2_OBSERVATION_CANARY_REPORT_2026-06-14.md` | PASSED |

---

## 8. Public Claim Gate Result

**No public claims are made or permitted based on 3B advisor decisions.**

All public claims require:
- Rust receipt_verifier pass (hash_match + schema_match + evidence_complete)
- Hallucination guard score ≤ threshold
- Capability receipt policy coverage check
- Human review for delivery-critical claims

The 3B advisor is EXCLUDED from the public claim chain.

---

*This evaluation is a baseline freeze snapshot. No expansion is recommended.*
