# Policy Lane Model v1 — Post-Freeze 分級治理架構

**Date**: 2026-06-15
**Base**: policy-baseline-manifest.v1 (frozen 2026-06-15)
**Principle**: Lane-based governance, not monolithic lock-down

---

## 1. Three-Lane Architecture

### Hard Lane
**Scope**: Public claim, primary cutover, 3B promotion, evidence verifier, delivery/claim authority
**Rules**:
- Fail-closed:缺 evidence / drill / held-out / feature flag →直接 block
- Rollback drill required before any change
- Held-out validation required
- Feature flag + fallback mandatory
- Human approval required for cutover
- No manual override possible

**Applies to**:
| Policy ID | Module | Reason |
|-----------|--------|--------|
| P-CLAIM-02 | hallucination_guard | Public claim scoring |
| P-CLAIM-03 | capability_receipt_policy | Public claim safety |
| P-DELIVERY-01 | delivery_gate | Delivery authority |
| P-DELIVERY-02 | delivery_contract | Delivery contracts |
| P-GATE-03 | receipt_verifier | Evidence verification |
| P-FLOW-01 | flow_machine | State transition authority |
| P-S2T-01 | s2t_strict | Routing authority |
| P-S2T-03 | s2t_3b_advisor | 3B promotion boundary |

### Soft Lane
**Scope**: Internal policy wording, low-risk parameters, reports, non-critical governance
**Rules**:
- Versioned changes allowed with manifest version bump
- Reason code required
- Basic test required
- Rollback note required
- Override allowed with receipt (who/why/scope/expiry/rollback)
- No authority change

**Applies to**:
| Policy ID | Module | Reason |
|-----------|--------|--------|
| P-ROUTE-01~04 | autonomic_router | Routing parameters |
| P-BUDGET-01 | budget_governor | Budget thresholds |
| P-PLAN-01~02 | capability_planner | Planning weights |
| P-COST-01 | cost_hook | Cost model tuning |
| P-GATE-01 | capability_gate | Tool whitelists |
| P-CLAIM-01 | critique_engine | Internal review wording |
| P-LEARN-01~02 | policy_drift / drift_stop_gate | Learning parameters |
| P-BELIEF-01 | belief_engine | Confidence blending |
| P-CTX-01 | context_hub | Context assembly tuning |
| P-SETTLE-01 | attempt_settlement | Settlement parameters |

### Shadow Lane
**Scope**: Observation-only, 3B shadow advisor, Rust shadow dual-run, policy experiments
**Rules**:
- No authority change
- No public claim expansion
- Fallback preserved
- Experiment results logged but not promoted
- Must not affect production routing

**Applies to**:
| Policy ID | Module | Reason |
|-----------|--------|--------|
| P-GATE-02 | evaluation_gate | Shadow verification |
| P-AUTO-01 | autonomy_observation | Shadow observation |

> **Note**: P-CONTAM-01 (contamination_guard) is in **hard lane**, not shadow. Research contamination blocking is a fail-closed core gate, not observation-only.

---

## 2. Lane Gate Enforcement

### Hard Lane Gate
```
IF lane == "hard":
    IF NOT evidence_bundle_complete:
        BLOCK "EVIDENCE_INCOMPLETE"
    IF NOT rollback_drill_passed:
        BLOCK "ROLLBACK_DRILL_MISSING"
    IF NOT held_out_validation:
        BLOCK "HELD_OUT_MISSING"
    IF NOT feature_flag_configured:
        BLOCK "FEATURE_FLAG_MISSING"
    ALLOW only with human approval receipt
```

### Soft Lane Gate
```
IF lane == "soft":
    IF NOT manifest_version_bumped:
        BLOCK "VERSION_NOT_BUMPED"
    IF NOT reason_code_provided:
        BLOCK "REASON_CODE_MISSING"
    IF NOT basic_test_passed:
        BLOCK "TEST_MISSING"
    IF override_active:
        CHECK override_receipt (who/why/scope/expiry/rollback)
        IF override_expired:
            REVERT to previous version
    ALLOW with manifest record
```

### Shadow Lane Gate
```
IF lane == "shadow":
    IF changes_authority:
        BLOCK "SHADOW_CANNOT_CHANGE_AUTHORITY"
    IF expands_public_claim:
        BLOCK "SHADOW_CANNOT_EXPAND_CLAIM"
    IF NOT fallback_preserved:
        BLOCK "FALLBACK_NOT_PRESERVED"
    ALLOW for observation/experiment only
```

---

## 3. Policy Versioning

### Version Format
`{policy_id}.{major}.{minor}.{patch}`

- **Major**: Authority change (requires hard lane process)
- **Minor**: Parameter adjustment (soft lane)
- **Patch**: Documentation / typo (soft lane, no test required)

### Version Record
```json
{
  "version": "P-CLAIM-02.1.3.0",
  "previous_version": "P-CLAIM-02.1.2.0",
  "diff_summary": "Adjusted hallucination threshold from 5 to 6",
  "lane": "soft",
  "reason_code": "THRESHOLD_TUNING",
  "author": "agent",
  "timestamp": "2026-06-15T00:00:00Z",
  "rollback_target": "P-CLAIM-02.1.2.0",
  "test_result": "PASS"
}
```

### Rollback Support
- Each version record stores `rollback_target`
- Rollback = restore previous version + record rollback event
- Historical evidence CANNOT be modified, only new versions added

---

## 4. Override Mechanism

### Override Receipt
```json
{
  "override_id": "OVR-2026-06-15-001",
  "policy_id": "P-COST-01",
  "lane": "soft",
  "who": "agent",
  "why": "Cost model tuning for benchmark",
  "scope": "COST_MODEL.read_file adjustment",
  "expiry": "2026-06-16T00:00:00Z",
  "rollback_plan": "Revert to P-COST-01.1.0.0",
  "created_at": "2026-06-15T00:00:00Z"
}
```

### Override Rules
- **Hard lane**: NO override allowed (manual bypass blocked)
- **Soft lane**: Override allowed with receipt
- **Shadow lane**: Override allowed (no authority impact)
- **Expiry**: Auto-revert when override expires
- **Renewal**: Must create new override receipt to extend

---

## 5. Lane Assignment Matrix

| Policy ID | Lane | Risk Tier | Authority Impact | Claim Impact | Cutover Impact |
|-----------|------|-----------|------------------|--------------|----------------|
| P-ROUTE-01~04 | soft | low | none | none | none |
| P-BUDGET-01 | soft | low | none | none | none |
| P-PLAN-01~02 | soft | medium | none | none | none |
| P-S2T-01~02 | hard | high | routing authority | none | cutover-gated |
| P-S2T-03 | hard | high | 3B promotion | none | cutover-gated |
| P-COST-01 | soft | low | none | none | none |
| P-GATE-01 | soft | medium | tool authority | none | none |
| P-GATE-02 | shadow | low | none | none | none |
| P-GATE-03 | hard | critical | evidence authority | claim-gated | cutover-gated |
| P-CLAIM-01 | soft | medium | none | internal | none |
| P-CLAIM-02 | hard | critical | none | claim-gated | cutover-gated |
| P-CLAIM-03 | hard | critical | none | claim-gated | cutover-gated |
| P-DELIVERY-01 | hard | critical | delivery authority | claim-gated | cutover-gated |
| P-DELIVERY-02 | hard | critical | delivery authority | claim-gated | cutover-gated |
| P-LEARN-01~02 | soft | medium | none | none | none |
| P-AUTO-01 | shadow | low | none | none | none |
| P-BELIEF-01 | soft | low | none | none | none |
| P-CTX-01 | soft | medium | none | none | none |
| P-SETTLE-01 | soft | medium | none | none | none |
| P-FLOW-01 | hard | critical | transition authority | none | cutover-gated |
| P-CONTAM-01 | shadow | low | none | none | none |

---

## 6. Test Cases

### Hard Lane — PASS
- Input: Policy change with complete evidence bundle, rollback drill passed, held-out validation passed, feature flag configured
- Expected: ALLOW

### Hard Lane — BLOCK
- Input: Policy change without rollback drill
- Expected: BLOCK "ROLLBACK_DRILL_MISSING"

### Soft Lane — PASS
- Input: Policy change with version bump, reason code, basic test passed
- Expected: ALLOW with manifest record

### Soft Lane — BLOCK
- Input: Policy change without version bump
- Expected: BLOCK "VERSION_NOT_BUMPED"

### Shadow Lane — PASS
- Input: Observation-only change, no authority impact, fallback preserved
- Expected: ALLOW

### Shadow Lane — BLOCK
- Input: Shadow change that attempts to modify public claim scope
- Expected: BLOCK "SHADOW_CANNOT_EXPAND_CLAIM"

---

*This lane model is a post-freeze governance framework. Hard lane changes require full cutover-grade evidence.*
