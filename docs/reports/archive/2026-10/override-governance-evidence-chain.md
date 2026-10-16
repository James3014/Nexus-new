# Override Governance Verification Evidence Chain

**Date**: 2026-06-15
**Status**: VERIFIED — soft override可用, hard override仍 fail-closed, rollback正常

---

## 1. Evidence Artifacts

| Step | Command | Receipt/Artifact | Verified |
|------|---------|------------------|----------|
| 1. Create soft override | `python scripts/ops/policy_override_lifecycle.py create --policy-id P-COST-01 --who agent --why "Cost model tuning" --scope "COST_MODEL.read_file" --expiry "2026-06-16T00:00:00Z" --rollback-target "P-COST-01.1.0.0"` | `.nexus/policy_overrides/OVR-2026-06-15-012340-09838df2.json` | ✅ |
| 2. Check override active | `python scripts/ops/policy_override_lifecycle.py check --override-id OVR-2026-06-15-012340-09838df2` | stdout: `{status: "active", remaining_hours: 22.6}` | ✅ |
| 3. Block hard override | `python scripts/ops/policy_override_lifecycle.py create --policy-id P-GATE-03 ...` | stdout: `{error: "HARD_LANE_OVERRIDE_BLOCKED"}`, exit code 1 | ✅ |
| 4. Rollback | `python scripts/ops/policy_override_lifecycle.py rollback --override-id OVR-2026-06-15-012340-09838df2` | stdout: `{status: "rolled_back", rollback_to: "P-COST-01.1.0.0"}` | ✅ |
| 5. List overrides | `python scripts/ops/policy_override_lifecycle.py list` | stdout: `{overrides: [...], total: 1}` | ✅ |
| 6. Friction report | `python scripts/ops/policy_lane_friction_report.py` | `docs/reports/friction-report-2026-06-15.json` | ✅ |

## 2. Policy Family Cross-Reference

| Family | Lane | Override Behavior | Evidence |
|--------|------|-------------------|----------|
| S2T (P-S2T-01~03) | hard | BLOCKED | Manifest + gate test |
| Evidence (P-GATE-03) | hard | BLOCKED | CLI output + test |
| Claim (P-CLAIM-02~03) | hard | BLOCKED | Manifest + gate test |
| Delivery (P-DELIVERY-01~02) | hard | BLOCKED | Manifest + gate test |
| Flow (P-FLOW-01) | hard | BLOCKED | Manifest + gate test |
| Contamination (P-CONTAM-01) | hard | BLOCKED | Manifest + gate test |
| Route (P-ROUTE-01~04) | soft | ALLOWED with receipt | Override lifecycle |
| Budget (P-BUDGET-01) | soft | ALLOWED with receipt | Override lifecycle |
| Cost (P-COST-01) | soft | ALLOWED with receipt | Override lifecycle tested |
| Plan (P-PLAN-01~02) | soft | ALLOWED with receipt | Manifest |
| Shadow (P-GATE-02, P-AUTO-01) | shadow | ALLOWED, no authority | Manifest + test |

## 3. Friction Calibration

| Sample | hard_ratio | override_rate | net_friction | Assessment |
|--------|-----------|---------------|--------------|------------|
| 2026-06-15 (baseline) | 0.37 | 0.10 | 0.333 | MEDIUM |
| Stable threshold | 0.37 | — | 0.20-0.40 | acceptable |

**Note**: Single-sample baseline. Time-series tracking recommended for calibration.

## 4. Conclusion

- **Override create**: PASS ✅
- **Hard-lane protection**: PASS ✅
- **Override TTL / active check**: PASS ✅
- **Rollback integrity**: PASS ✅
- **Friction**: currently acceptable (MEDIUM), but only as local snapshot

**This is a successful override governance verification.** It supports the internal conclusion "soft override可用, hard override仍 fail-closed, rollback正常" but does not support broader capability narratives or policy tuning completion claims.

---

*Evidence chain generated 2026-06-15. All artifacts are reproducible via listed commands.*
