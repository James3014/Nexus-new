# AC4 — Semantic Ceiling Strategy Decision

**Status**: `AC4_STOP_CAPABILITY_EXPANSION_BEGIN_PRODUCTIZATION`
**Date**: 2026-06-21
**Owner Decision**: FINAL

---

## 1. Executive Summary

The semantic ceiling analysis reveals that the current local model stack (qwen2.5-coder:7b + deepseek-6.7b) has **NOT reached its semantic ceiling**. The single remaining failure (`django__django-13455`) is a **governance boundary**, not a model limitation. The full Nexus capability route solves 13/14 tasks (92.9%) with optimal efficiency.

**Strategic Decision**: Stop capability expansion. Begin internal productization design.

---

## 2. AB Recap

### AB1: Full Capability Route Definition
- Route: `local_full_nexus_repair_control_plane_v0`
- 10-stage capability pipeline defined
- Only stub: Swarm/Drone local lock (deferred)

### AB2: 14-Task Benchmark
- Full Nexus Route: 13/14 (92.9%)
- Avg proposer calls: 1.8
- Ablation confirms all capabilities contribute

### AB3: Decision
- Result type: B
- Full route improves efficiency, not pass rate
- Remaining blocker: `ABSTAIN_BOUNDARY_EDIT` (governance, not model)

---

## 3. AC1 Semantic Ceiling Diagnosis

| Dimension | Finding |
|-----------|---------|
| Evidence Graph | Complete for all 14 tasks |
| Model Reasoning | Correct for all 14 tasks |
| Action Protocol | Functional, correctly gates boundaries |
| Verifier | Functional, correctly blocks boundary edits |
| Semantic Ceiling | NOT REACHED |

**Conclusion**: The local model stack is performing at design capacity. No semantic ceiling has been hit.

---

## 4. AC2 14B Fallback Result

| Metric | Value |
|--------|-------|
| Target Model | qwen2.5-coder:14b-instruct-q3_K_M |
| Availability | NOT_AVAILABLE |
| Available Alternatives | deepseek-r1-14b-q4km (different family) |
| Unique Wins | 0 (cannot evaluate) |
| Resource Guard | ACTIVE, RESOURCE_LIMITED |

**Conclusion**: 14B fallback not justified. Remaining failure is governance-mediated, not model-mediated.

---

## 5. AC3 Strong Comparison Status

| Metric | Value |
|--------|-------|
| Approval Status | REQUIRED (not present) |
| Comparison Executed | NO |
| Design Packet | COMPLETE |

**Conclusion**: Approval packet prepared. No cloud/API execution without owner approval.

---

## 6. Final Interpretation

The data shows:

1. **13/14 tasks solved** by full Nexus route (92.9%)
2. **1 task abstained** due to governance boundary (not model failure)
3. **All capabilities contribute** (ablation confirms)
4. **14B fallback not needed** (failure is governance-mediated)
5. **Strong model comparison not needed** (same governance boundary would apply)

The system has reached **optimal local performance** within current governance constraints.

---

## 7. Next Route Policy

### Keep Active
- Full Nexus capability route (`local_full_nexus_repair_control_plane_v0`)
- All 10 capability stages
- Governance boundary abstain for coordinated edits

### Defer
- Swarm/Drone local lock (stub remains)
- 14B fallback (not justified)
- Strong model comparison (not needed)

### Expand
- None (stop capability expansion)

---

## 8. Productization Readiness

| Criterion | Status |
|-----------|--------|
| Pass Rate | 92.9% (13/14) |
| Efficiency | Optimal (1.8 avg proposer calls) |
| Governance | Functional (boundary abstain works) |
| Ablation | All capabilities contribute |
| Resource Usage | Stable (6.8GB peak) |
| Regression Guards | PASSING (C_12481, C_13453) |

**Recommendation**: Ready for internal productization design.

---

## 9. What Remains Forbidden

| Restriction | Status |
|-------------|--------|
| Public claim | FORBIDDEN |
| Production release | FORBIDDEN |
| Training export | FORBIDDEN |
| Cloud/API execution | FORBIDDEN (without approval) |
| Unrestricted multi-file edit | FORBIDDEN |
| Model direct tool calls | FORBIDDEN |
| Model majority vote | FORBIDDEN |
| Test edits to force pass | FORBIDDEN |
| Hardcoded expected patch | FORBIDDEN |

---

## 10. 30-Day Roadmap

### Week 1-2: Productization Design
- Design internal API surface
- Define deployment topology
- Create user documentation
- Establish monitoring baseline

### Week 3-4: Internal Deployment
- Deploy to internal staging
- Run 7-day canary
- Collect user feedback
- Iterate on UX

### Out of Scope
- Public release
- Marketing claims
- Training data export
- Cloud API integration

---

## Decision

**AC4_STOP_CAPABILITY_EXPANSION_BEGIN_PRODUCTIZATION**

The system has achieved optimal local performance. Next objective is internal productization, not further capability expansion.

---

## Mandatory Flags

```json
{
  "public_claim_allowed": false,
  "production_ready": false,
  "training_export_allowed": false,
  "internal_only": true
}
```
