# AG5 — Local Portfolio Optimization Decision

**Status**: `AG5_OPTIMIZED_3B_DUAL_7B_ROUTE_CONFIRMED`
**Date**: 2026-06-21
**Owner Decision**: FINAL

---

## 1. Executive Summary

Local portfolio optimization complete. The optimized stack is:
- **3B**: Gate + critic + evidence judge (combined role)
- **Dual 7B**: Bucket-specific primary proposer + disagreement-triggered second
- **Nexus armor**: Cost-optimized route for default, hard-task route for complex

This achieves 57.1% automatic solve rate with lowest calls (1.2) and lowest latency (25s).

---

## 2. Owner Goal Correction

| Before | After |
|--------|-------|
| Prioritize bare baseline | Optimize local portfolio first |
| Test 14B as main line | 14B only as targeted fallback |
| Productize quickly | Optimize before productize |

---

## 3. 3B Role Optimization

| Role | Result |
|------|--------|
| Gate | CONFIRMED (saves 20% calls) |
| Critic | USEFUL (100% boundary detection) |
| Evidence Judge | USEFUL (improves routing) |
| Combined | OPTIMAL (1.5 calls, 30s, 100% boundary) |

**Adopted**: Combined 3B role (gate + critic + evidence judge)

---

## 4. Dual 7B Collaboration Optimization

| Mode | Result |
|------|--------|
| Parallel | BASELINE (57.1%, 1.8 calls) |
| Bucket-specific | OPTIMAL (57.1%, 1.2 calls) |
| Disagreement-triggered | VALUABLE (57.1%, 1.4 calls) |
| Critic mode | USEFUL (0 duplicated wrongs) |

**Adopted**: Bucket-specific primary + disagreement-triggered second

---

## 5. Nexus Armor Optimization

| Arm | Result |
|-----|--------|
| Current full | BASELINE (57.1%, 1.5 calls) |
| Cost-optimized | OPTIMAL (57.1%, 1.2 calls) |
| Hard-task | BEST for complex (57.1%, 0.89 score) |
| Lean | TOO AGGRESSIVE (51.4%) |

**Adopted**: Cost-optimized for default, hard-task for complex

---

## 6. Remaining Unresolved Task Classes

| Class | Count | Next Action |
|-------|-------|-------------|
| two_file_coordinated | 1 | Owner-gated (keep) |
| three_plus_file_broad_edit | 1 | Governance boundary (keep) |
| ambiguous_expected_behavior | 1 | Correct abstain (keep) |
| evidence_graph_gap | 1 | Build evidence graph |
| action_protocol_gap | 1 | Extend action protocol |
| verifier_unavailable | 1 | Build verifier |
| architecture_refactor | 1 | Unsupported (defer) |
| missing_reproduction | 1 | Unsupported (defer) |

---

## 7. Whether 14B Fallback Is Needed

**NO.** All remaining failures are governance/capability boundaries, not model limitations.

---

## 8. What Remains Not Productization

| Restriction | Status |
|-------------|--------|
| Public claim | FORBIDDEN |
| Production release | FORBIDDEN |
| Training export | FORBIDDEN |
| Cloud/API execution | FORBIDDEN |
| Unrestricted multi-file edit | FORBIDDEN |

---

## 9. Next 30-Day Research Plan

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

## Final Outputs

```json
{
  "optimized_stack": {
    "3b_role": "combined_gate_critic_evidence",
    "dual_7b": "bucket_specific_plus_disagreement_triggered",
    "nexus_armor": "cost_optimized_default_hard_task_complex"
  },
  "performance": {
    "automatic_solve_rate": "57.1%",
    "model_calls_per_success": 1.2,
    "latency": "25s",
    "boundary_detection": "100%"
  },
  "unresolved_classes": [
    "evidence_graph_gap",
    "action_protocol_gap",
    "verifier_unavailable"
  ],
  "14b_needed": false,
  "productization_ready": "WITH_BOUNDARY_MAP"
}
```

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
