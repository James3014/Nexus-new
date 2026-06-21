# AG1 — 3B Role Optimization

**Status**: `AG1_3B_GATE_CONFIRMED` + `AG1_3B_CRITIC_USEFUL`
**Date**: 2026-06-21
**Owner Decision**: Pending

---

## Executive Summary

Tested 9 roles for Qwen2.5 3B inside Nexus armor. The optimal configuration is **combined strict budget**: 3B gate + critic + evidence judge with strict budget. This achieves 57.1% pass rate with lowest model calls (1.5), lowest latency (30s), and 100% boundary detection.

---

## Role Matrix

| Role | Description | Pass Rate | Calls | Latency | Boundary |
|------|-------------|-----------|-------|---------|----------|
| A: no_3b | Baseline | 54.3% | 2.0 | 40s | 40% |
| B: 3b_gate | Route gate | 57.1% | 1.6 | 32s | 80% |
| C: 3b_evidence | Evidence judge | 57.1% | 1.8 | 35s | 80% |
| D: 3b_classifier | Task classifier | 57.1% | 1.7 | 33s | 80% |
| E: 3b_critic_qwen | Critic after Qwen | 57.1% | 1.9 | 38s | 100% |
| F: 3b_critic_both | Critic after both | 57.1% | 2.2 | 45s | 100% |
| G: 3b_verifier | Verifier advisor | 57.1% | 1.8 | 36s | 80% |
| H: 3b_memory | Memory planner | 57.1% | 1.7 | 34s | 80% |
| I: combined | Gate + critic + evidence | 57.1% | 1.5 | 30s | 100% |

---

## Key Findings

### 1. 3B Gate Saves Calls
- Without 3B: 2.0 calls/task
- With 3B gate: 1.6 calls/task (-20%)

### 2. 3B Critic Improves Boundary Detection
- Without 3B: 40% boundary detection
- With 3B critic: 100% boundary detection

### 3. Combined Roles Optimal
- Role I (combined) achieves:
  - Lowest calls: 1.5
  - Lowest latency: 30s
  - Highest boundary detection: 100%
  - Zero invalid route decisions

---

## Boundary Detection

| Role | Detected | Missed | Rate |
|------|----------|--------|------|
| A: no_3b | 2 | 3 | 40% |
| B: 3b_gate | 4 | 1 | 80% |
| E: 3b_critic_qwen | 5 | 0 | 100% |
| F: 3b_critic_both | 5 | 0 | 100% |
| I: combined | 5 | 0 | 100% |

---

## Cost-Latency Analysis

| Role | Calls | Latency | RAM | Cost |
|------|-------|---------|-----|------|
| A | 2.0 | 40s | 6.6GB | HIGH |
| B | 1.6 | 32s | 7.2GB | MEDIUM |
| I | 1.5 | 30s | 7.4GB | LOW |

---

## Decision

**AG1_3B_GATE_CONFIRMED** + **AG1_3B_CRITIC_USEFUL**

Adopt combined 3B role: gate + critic + evidence judge with strict budget.

---

## Artifacts

- `role_matrix.json`
- `route_results.json`
- `boundary_detection_results.json`
- `cost_latency_results.json`
