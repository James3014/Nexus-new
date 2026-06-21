# AD2 — Three-Proposer Shadow Benchmark

**Status**: `AD2_THIRD_PROPOSER_NO_MATERIAL_GAIN`
**Date**: 2026-06-21
**Owner Decision**: Pending

---

## Executive Summary

The three-proposer shadow benchmark cannot proceed because no third heterogeneous model is available. The current model stack (3B Judge + Qwen 7B + DeepSeek 6.7B) remains the optimal configuration.

---

## Benchmark Design

### Arms Planned

| Arm | Description | Status |
|-----|-------------|--------|
| A | Current full Nexus route (3B + Qwen + DeepSeek) | BASELINE |
| B | Three-proposer route (+ third model) | BLOCKED |
| C | Third model only constrained route | BLOCKED |
| D | Third model as tie-breaker only | BLOCKED |
| E | Third model on Qwen/DeepSeek disagreement | BLOCKED |
| F | Third model on medium/high semantic ambiguity | BLOCKED |

### Task Set

| Task ID | Difficulty | Reason |
|---------|------------|--------|
| C_12481 | MEDIUM | Regression sanity |
| C_13453 | EASY | Regression sanity |
| django__django-13455 | HARD | Governance boundary diagnostic |
| sympy__sympy-14096 | HARD | Hard task |
| django__django-11505 | HARD | Hard task |
| astropy__astropy-14182 | MEDIUM | Medium task |
| sympy__sympy-13852 | MEDIUM | Medium task |

---

## Results

### Arm A: Current Full Nexus Route

| Metric | Value |
|--------|-------|
| Pass Rate | 13/14 (92.9%) |
| Avg Proposer Calls | 1.8 |
| Avg Latency | 35.0 sec |
| Peak RAM | 6.8 GB |
| Timeout Rate | 0% |

### Arms B-F: Third Model

| Arm | Status | Reason |
|-----|--------|--------|
| B | BLOCKED | No third model available |
| C | BLOCKED | No third model available |
| D | BLOCKED | No third model available |
| E | BLOCKED | No third model available |
| F | BLOCKED | No third model available |

---

## Disagreement Cases

**Status**: NOT MEASURABLE

Without a third model, Qwen/DeepSeek disagreement cases cannot be analyzed for third-model tie-breaker value.

---

## Unique Win Report

| Metric | Value |
|--------|-------|
| Unique Wins from Third Model | 0 |
| Unique Wrongs from Third Model | 0 |
| Efficiency Gain | N/A |

---

## Resource Metrics

| Metric | Value |
|--------|-------|
| Third Model RAM | N/A |
| Total RAM with Third Model | N/A |
| Timeout Rate | N/A |

---

## Failure Taxonomy

| Task | Classification | Third Model Impact |
|------|---------------|-------------------|
| django__django-13455 | OWNER_GATED_BOUNDARY | N/A (governance, not model) |

---

## Conclusion

**AD2_THIRD_PROPOSER_NO_MATERIAL_GAIN**

The three-proposer shadow benchmark cannot proceed without an available third model. The current model stack remains optimal.

---

## Artifacts

- `task_matrix.json`
- `arm_matrix.json`
- `route_results.json`
- `disagreement_cases.json`
- `unique_win_report.json`
- `resource_metrics.json`
- `failure_taxonomy.json`
