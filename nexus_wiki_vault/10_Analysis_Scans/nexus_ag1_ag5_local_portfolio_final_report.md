# Nexus AG1-AG5 Local Portfolio Optimization — Final Report

**Date**: 2026-06-21
**Status**: COMPLETE
**Decision**: AG5_OPTIMIZED_3B_DUAL_7B_ROUTE_CONFIRMED

---

## Executive Summary

Local portfolio optimization complete. The optimized stack achieves 57.1% automatic solve rate with lowest calls (1.2) and lowest latency (25s).

---

## Optimized Stack

| Component | Configuration |
|-----------|---------------|
| 3B Judge | Combined role: gate + critic + evidence judge |
| Qwen 7B | Bucket-specific primary proposer |
| DeepSeek 6.7B | Disagreement-triggered second proposer |
| Nexus Armor | Cost-optimized route (default) / Hard-task route (complex) |

---

## AG1: 3B Role Optimization

**Status**: `AG1_3B_GATE_CONFIRMED` + `AG1_3B_CRITIC_USEFUL`

| Role | Result |
|------|--------|
| Gate | Saves 20% calls |
| Critic | 100% boundary detection |
| Evidence Judge | Improves routing |
| Combined | OPTIMAL |

---

## AG2: Dual 7B Collaboration

**Status**: `AG2_BUCKET_SPECIFIC_ROUTING_READY` + `AG2_CONDITIONAL_SECOND_PROPOSER_READY`

| Mode | Result |
|------|--------|
| Bucket-specific | 1.2 calls, 25s latency |
| Disagreement-triggered | 1.4 calls, 32s latency |
| Critic mode | 0 duplicated wrongs |

---

## AG3: Nexus Armor Optimization

**Status**: `AG3_COST_OPTIMIZED_ROUTE_READY` + `AG3_HARD_TASK_ROUTE_READY`

| Arm | Result |
|-----|--------|
| Cost-optimized | 1.2 calls, 25s, 0.88 score |
| Hard-task | 1.9 calls, 40s, 0.89 score |

---

## AG4: 14B Fallback

**Status**: `AG4_14B_NOT_NEEDED_YET`

No unresolved tasks require 14B fallback. All remaining failures are governance/capability boundaries.

---

## AG5: Final Decision

**Status**: `AG5_OPTIMIZED_3B_DUAL_7B_ROUTE_CONFIRMED`

### Performance

| Metric | Value |
|--------|-------|
| Automatic Solve Rate | 57.1% |
| Model Calls/Success | 1.2 |
| Latency | 25s |
| Boundary Detection | 100% |

### Unresolved Classes

| Class | Next Action |
|-------|-------------|
| evidence_graph_gap | Build evidence graph |
| action_protocol_gap | Extend action protocol |
| verifier_unavailable | Build verifier |

---

## What Remains Forbidden

- Public claim: **FORBIDDEN**
- Production release: **FORBIDDEN**
- Training export: **FORBIDDEN**
- Cloud/API execution: **FORBIDDEN**
- Unrestricted multi-file edit: **FORBIDDEN**

---

## 30-Day Research Plan

### Week 1-2: Capability Extension
- Build evidence graph for gap tasks
- Extend action protocol for unsupported types
- Build verifiers for new domains

### Week 3-4: Validation
- Run expanded benchmark with optimized route
- Validate boundary map accuracy
- Collect user feedback

### Month 2: Productization
- Design internal API
- Deploy to internal staging
- Run 7-day canary

---

## Artifacts

| Path | Description |
|------|-------------|
| `artifacts/runtime/ag1_3b_role_optimization_v0/` | AG1 3B role analysis |
| `artifacts/runtime/ag2_dual_7b_collaboration_optimization_v0/` | AG2 dual 7B analysis |
| `artifacts/runtime/ag3_nexus_armor_local_portfolio_optimization_v0/` | AG3 armor optimization |
| `docs/reports/ag1_3b_role_optimization_v0.md` | AG1 report |
| `docs/reports/ag2_dual_7b_collaboration_optimization_v0.md` | AG2 report |
| `docs/reports/ag3_nexus_armor_local_portfolio_optimization_v0.md` | AG3 report |
| `docs/reports/ag4_targeted_14b_fallback_decision_v0.md` | AG4 report |
| `docs/reports/ag5_local_portfolio_optimization_decision_v0.md` | AG5 report |

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
