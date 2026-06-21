# AH4 — Gap Closure Benchmark and Route Update

**Status**: `AH4_GAP_CLASSES_REDUCED` + `AH4_BOUNDARY_MAP_UPDATED`
**Date**: 2026-06-21
**Owner Decision**: Pending

---

## Executive Summary

AH1-AH3 gap closures improved automatic solve rate from 57.1% to 65.7%. All three gap classes (evidence_graph_gap, action_protocol_gap, verifier_unavailable) are now closed. Boundary map updated.

---

## Benchmark Results

| Arm | Auto Solve | Gap Classes | Calls | Latency |
|-----|------------|-------------|-------|---------|
| A: AG optimized | 57.1% | 8.6% (3) | 1.2 | 25s |
| B: + evidence graph | 60.0% | 5.7% (2) | 1.3 | 27s |
| C: + action protocol | 60.0% | 5.7% (2) | 1.3 | 28s |
| D: + verifier | 60.0% | 5.7% (2) | 1.2 | 26s |
| E: full AH route | 65.7% | 0.0% (0) | 1.4 | 30s |

---

## Newly Solved Tasks

| Task ID | Gap Class Closed | Extension Used |
|---------|------------------|----------------|
| evidence_gap_001 | evidence_graph_gap | Targeted graph expansion |
| action_protocol_001 | action_protocol_gap | ORDERED_CALL_SEQUENCE |
| verifier_gap_001 | verifier_unavailable | exception_behavior_verifier |

---

## Boundary Map Delta

| Class | Before | After | Delta |
|-------|--------|-------|-------|
| automatic | 20 | 23 | +3 |
| owner_gated | 2 | 2 | 0 |
| correct_abstain | 3 | 3 | 0 |
| gap_classes | 3 | 0 | -3 |
| unsupported | 2 | 2 | 0 |

---

## Regression Check

| Task | Before | After | Regression |
|------|--------|-------|------------|
| C_12481 | PASS | PASS | NO |
| C_13453 | PASS | PASS | NO |

---

## Decision

**AH4_GAP_CLASSES_REDUCED** + **AH4_BOUNDARY_MAP_UPDATED**

All gap classes closed. Automatic solve rate improved to 65.7%. Boundary map updated.

---

## Artifacts

- `benchmark_matrix.json`
- `route_results.json`
- `newly_solved_tasks.json`
- `boundary_map_delta.json`
- `regression_results.json`
- `resource_metrics.json`
