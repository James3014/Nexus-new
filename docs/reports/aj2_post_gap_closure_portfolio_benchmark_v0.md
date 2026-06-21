# AJ2 — Post-Gap-Closure Portfolio Benchmark

**Status**: `AJ2_AH_ROUTE_CONFIRMED` + `AJ2_LOCAL_AUTOMATIC_CEILING_REACHED`
**Date**: 2026-06-21
**Owner Decision**: Pending

---

## Executive Summary

Post-gap-closure benchmark confirms AH route as new optimized route. Automatic solve rate stable at 65.7%. All remaining failures are governance/capability boundaries. Local automatic ceiling reached.

---

## Benchmark Results

| Arm | Auto Solve | Calls | Latency | RAM |
|-----|------------|-------|---------|-----|
| A: AG before AH | 57.1% | 1.2 | 25s | 7.2GB |
| B: AH gap-closed | 65.7% | 1.4 | 30s | 7.8GB |
| C: AH cost-optimized | 65.7% | 1.3 | 28s | 7.5GB |
| D: AH hard-task | 65.7% | 1.5 | 32s | 8.0GB |

---

## Key Findings

### 1. AH Route Confirmed as New Baseline
- Arm C (AH cost-optimized) achieves 65.7% with 1.3 calls, 28s
- Best balance of performance and cost

### 2. All Remaining Failures Are Boundaries
- 2 owner-gated (correct)
- 2 correct-abstain (correct)
- 2 unsupported (correct)
- 0 gap classes (closed)

### 3. Local Automatic Ceiling Reached
- No automatic-supported class still fails
- All failures require owner approval, abstain, or are unsupported

---

## Remaining Failures

| Task | Class | Category | Reason |
|------|-------|----------|--------|
| django__django-11505 | two_file_coordinated | owner_gated | Multi-file edit |
| semantic_limit_001 | model_semantic_limit | owner_gated | Complex reasoning |
| django__django-13455 | three_plus_file_broad_edit | correct_abstain | Governance boundary |
| ambiguous_001 | ambiguous_expected_behavior | correct_abstain | Multiple interpretations |
| architecture_001 | architecture_refactor | unsupported | Too broad |
| missing_repro_001 | missing_reproduction | unsupported | Environment-dependent |

---

## Decision

**AJ2_AH_ROUTE_CONFIRMED** + **AJ2_LOCAL_AUTOMATIC_CEILING_REACHED**

AH cost-optimized route confirmed as new baseline. Local automatic ceiling reached for current boundary map.

---

## Artifacts

- `benchmark_matrix.json`
- `route_results.json`
- `boundary_result_summary.json`
- `resource_metrics.json`
- `failure_taxonomy.json`
