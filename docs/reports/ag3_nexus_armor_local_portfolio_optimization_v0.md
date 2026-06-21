# AG3 — Nexus Armor Optimization for Local Portfolio

**Status**: `AG3_COST_OPTIMIZED_ROUTE_READY` + `AG3_HARD_TASK_ROUTE_READY`
**Date**: 2026-06-21
**Owner Decision**: Pending

---

## Executive Summary

Tested 7 optimization arms for Nexus armor. The optimal configuration is **cost-optimized route** (Arm E) for default tasks and **hard-task route** (Arm F) for complex tasks. This achieves 57.1% pass rate with lowest calls (1.2) and lowest latency (25s).

---

## Optimization Arm Results

| Arm | Pass Rate | Calls | Latency | RAM | Weighted |
|-----|-----------|-------|---------|-----|----------|
| A: current | 57.1% | 1.5 | 30s | 7.4GB | 0.85 |
| B: lean | 51.4% | 1.2 | 22s | 6.8GB | 0.78 |
| C: full_evidence | 57.1% | 1.8 | 38s | 8.2GB | 0.87 |
| D: reasoning_heavy | 57.1% | 1.7 | 35s | 7.8GB | 0.86 |
| E: cost_optimized | 57.1% | 1.2 | 25s | 7.2GB | 0.88 |
| F: hard_task | 57.1% | 1.9 | 40s | 8.5GB | 0.89 |
| G: boundary_safe | 57.1% | 1.6 | 33s | 7.5GB | 0.84 |

---

## Key Findings

### 1. Cost-Optimized Route Optimal for Default
- Arm E: 1.2 calls, 25s latency, 0.88 weighted score
- Uses 3B gate + conditional second proposer

### 2. Hard-Task Route Best for Complex Tasks
- Arm F: 0.89 weighted score (highest)
- Uses larger evidence graph + owner-gated protocol

### 3. Lean Route Too Aggressive
- Arm B: 51.4% pass rate (lowest)
- Loses too much evidence/reasoning

### 4. Boundary-Safe Route Good for Abstain
- Arm G: 4 correct abstains (most)
- Higher false block rate (1)

---

## Cost-Accuracy Frontier

| Position | Arm | Pass Rate | Calls | Latency |
|----------|-----|-----------|-------|---------|
| PARETO_OPTIMAL | E: cost_optimized | 57.1% | 1.2 | 25s |
| BASELINE | A: current | 57.1% | 1.5 | 30s |
| HIGHEST_QUALITY | F: hard_task | 57.1% | 1.9 | 40s |

---

## Route Policy

| Task Type | Recommended Arm |
|-----------|-----------------|
| Default (easy/medium) | E: cost_optimized |
| Hard/semantic tasks | F: hard_task |
| Boundary tasks | G: boundary_safe |

---

## Decision

**AG3_COST_OPTIMIZED_ROUTE_READY** + **AG3_HARD_TASK_ROUTE_READY**

Adopt cost-optimized route for default tasks, hard-task route for complex tasks.

---

## Artifacts

- `optimization_arm_matrix.json`
- `route_results.json`
- `cost_accuracy_frontier.json`
- `threshold_results.json`
- `selector_weight_results.json`
