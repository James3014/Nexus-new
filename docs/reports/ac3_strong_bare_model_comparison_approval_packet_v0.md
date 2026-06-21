# AC3 — Strong Bare Model Comparison Approval Packet

**Status**: `AC3_STRONG_COMPARISON_APPROVAL_REQUIRED`
**Date**: 2026-06-21
**Owner Decision**: REQUIRED

---

## 1. Why Comparison Is Needed

The AB2 benchmark shows the full Nexus capability route solves 13/14 tasks (92.9%). The single remaining failure (`django__django-13455`) is classified as `ABSTAIN_BOUNDARY_EDIT`. To determine whether this failure is:
- A model semantic ceiling (stronger model would solve it)
- A governance boundary (any model would abstain)
- An evidence/action substrate gap

A strong bare model comparison is needed.

---

## 2. Current Local Full Route Result

| Metric | Value |
|--------|-------|
| Pass Rate | 13/14 (92.9%) |
| Avg Proposer Calls | 1.8 |
| Avg Latency | 35.0 sec |
| Ablation: Without Memory | +33% proposer calls |
| Ablation: Without Reasoning | +67% proposer calls |
| Ablation: Without Sandbox | -14% pass rate |

---

## 3. Remaining Failures

| Task ID | Classification | Evidence Gap | Reasoning Gap | Action Protocol Gap |
|---------|---------------|--------------|---------------|---------------------|
| django__django-13455 | OWNER_GATED_BOUNDARY | NONE | NONE | NONE |

---

## 4. What Strong Comparison Will Answer

1. Is django__django-13455 solvable by a stronger model without Nexus evidence?
2. Does Nexus evidence help a strong model solve it?
3. Does constrained action protocol help a strong model solve it?
4. Is the failure a true semantic ceiling or a governance boundary?

---

## 5. Exact Tasks

| Task ID | Difficulty | Reason for Inclusion |
|---------|------------|---------------------|
| django__django-13455 | HARD | MODEL_SEMANTIC_LIMIT candidate |
| C_12481 | MEDIUM | Regression sanity |
| C_13453 | EASY | Regression sanity |
| sympy__sympy-13031 | EASY | Medium task control |

---

## 6. Exact Prompts / Evidence Conditions

### Arm C: Strong Bare Model Direct Repair
- Prompt: Full problem statement + file context
- Evidence: None (bare model)
- Action: Free-form (no constrained protocol)

### Arm D: Strong Bare Model with Nexus Evidence
- Prompt: Full problem statement + file context + Nexus evidence graph
- Evidence: Complete evidence graph from AB2
- Action: Free-form (no constrained protocol)

### Arm E: Strong Bare Model with Constrained Action
- Prompt: Full problem statement + file context + Nexus evidence graph
- Evidence: Complete evidence graph from AB2
- Action: Constrained SEARCH/REPLACE protocol

---

## 7. Cost and Privacy Boundary

| Metric | Value |
|--------|-------|
| Cloud API Usage | NONE (local execution only) |
| Privacy Boundary | MAINTAINED |
| Token Cost | Internal only |
| Data Export | NONE |

---

## 8. No Production/Public Claim

This comparison is for **internal calibration only**. No public claims, no marketing, no production use.

---

## 9. No Training Export

No training data will be exported from this comparison.

---

## 10. Success Criteria

| Criterion | Required |
|-----------|----------|
| All 4 tasks evaluated | YES |
| Regression tasks (C_12481, C_13453) remain passing | YES |
| Control task (sympy__sympy-13031) remains passing | YES |
| django__django-13455 classified correctly | YES |
| No cloud API calls | YES |
| No data export | YES |

---

## 11. Abort Criteria

| Criterion | Action |
|-----------|--------|
| Any regression task fails | ABORT immediately |
| Cloud API call detected | ABORT immediately |
| Data export detected | ABORT immediately |
| Owner revokes approval | STOP execution |

---

## Approval Required

**Owner must explicitly approve** before any strong model execution.

If approval is present:
- Run minimal comparison
- Write results to `artifacts/runtime/ac3_strong_bare_model_comparison_v0/`
- Report final status

If approval is not present:
- Stop after this packet
- Final status: `AC3_STRONG_COMPARISON_APPROVAL_REQUIRED`
