# AC2 — 14B Resource-Gated Fallback Evaluation

**Status**: `AC2_14B_RESOURCE_LIMITED`
**Date**: 2026-06-21
**Owner Decision**: Pending

---

## Executive Summary

The 14B fallback evaluation is **blocked by resource limits**. The target model `qwen2.5-coder:14b-instruct-q3_K_M` is not available in ollama. Available 14B models (`deepseek-r1-14b-q4km`) are different model families and not suitable substitutes for the specific fallback design.

---

## Resource Guard Status

| Metric | Value | Limit | Status |
|--------|-------|-------|--------|
| System RAM | 16.0 GB | — | OK |
| Peak RAM Allowed | 12.0 GB | — | OK |
| Current RAM Usage | 6.8 GB | 12.0 GB | OK |
| Swap Risk | LOW | — | OK |
| CPU-Only Execution | false | — | OK |

---

## Model Availability

| Model | Status | Size | Suitable Fallback |
|-------|--------|------|-------------------|
| qwen2.5-coder:14b-instruct-q3_K_M | NOT_AVAILABLE | — | Target |
| deepseek-r1-14b-q4km | AVAILABLE | 9.0 GB | NO (different family) |
| gemma4-coder-12b-q4km | AVAILABLE | 7.4 GB | NO (12B, different family) |
| qwen2.5-coder:7b | AVAILABLE | 4.7 GB | NO (current baseline) |

---

## Route Results

| Arm | Status | Pass Rate | Notes |
|-----|--------|-----------|-------|
| A: Full Nexus without 14B | COMPLETE | 13/14 (92.9%) | Current baseline |
| B: Full Nexus with 14B fallback | BLOCKED | N/A | Model unavailable |
| C: 14B constrained action only | BLOCKED | N/A | Model unavailable |
| D: 14B free-form diagnostic | BLOCKED | N/A | Model unavailable |

---

## Decision Analysis

### Why 14B Fallback Is Not Justified

1. **Remaining failure is governance-mediated**: `django__django-13455` fails due to `ABSTAIN_BOUNDARY_EDIT`, not model limitation
2. **14B would face same boundary**: A stronger model would still trigger the same governance abstain
3. **Resource cost**: 14B adds ~9GB RAM pressure with no unique win
4. **Model unavailability**: Target model not in ollama registry

### Recommendation

**Do not adopt 14B fallback.** The remaining failure requires owner decision on governance scope, not model upgrade.

---

## Artifacts

- `resource_guard_report.json`
- `model_availability.json`
- `route_results.json`
- `unique_win_report.json`
