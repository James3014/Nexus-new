# Preflight Shadow Evaluation Report

**Status**: BLOCKED — PACT+Memory has severe regression
**Date**: 2026-06-15
**Commit**: `79fb4ad1`

---

## 1. Verdict

**BLOCKED — PACT+Memory has severe regression**

All groups achieve 10/10 verified success, but PACT+Memory shows extreme wall time regression (221s avg vs 50s baseline). This indicates the skill memory query layer is adding severe overhead that must be investigated before any promotion.

---

## 2. Run Matrix (10 tasks per group)

| Group | Verified | Avg Time | Easy | Med | Hard |
|:---|:---:|:---:|:---:|:---:|:---:|
| Baseline | 10/10 | 49.8s | 3/3 | 3/3 | 4/4 |
| PACT Only | 10/10 | 47.5s | 3/3 | 3/3 | 4/4 |
| PACT+Memory | 10/10 | 221.2s | 3/3 | 3/3 | 4/4 |
| Full Uplift | timeout | — | — | — | — |

---

## 3. Analysis

### 3.1 Baseline vs PACT Only
- **No significant difference**: 49.8s vs 47.5s (-4.6%)
- Both achieve 10/10 verified success
- Conclusion: PACT adds no measurable benefit on easy/medium tasks

### 3.2 PACT+Memory Regression
- **Severe regression**: 221.2s vs 49.8s (+344%)
- Root cause: skill memory query adds massive overhead
- easy-002: 1091s (should be ~60s)
- easy-003: 733s (should be ~60s)
- This is a blocking issue that must be investigated

### 3.3 Full Uplift
- Timed out during execution
- Cannot evaluate until PACT+Memory regression is fixed

---

## 4. Next Steps

1. **Investigate PACT+Memory regression**: Skill memory query is adding ~1000s overhead
2. **Fix the regression**: Either optimize the query or disable it for simple tasks
3. **Re-run Full Uplift**: Once PACT+Memory is fixed
4. **Generate complete shadow report**: With all 4 groups working correctly

---

*Report generated: 2026-06-15*
*Status: BLOCKED — PACT+Memory regression must be fixed first*
