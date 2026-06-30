# Preflight Shadow Evaluation Report (Final)

**Status**: PASS — No capability lift, no regression
**Date**: 2026-06-15
**Commit**: `79fb4ad1`
**Tasks**: 10 per group (easy/medium/hard), warmed state

---

## 1. Verdict

**No measurable capability lift. Cost/clarity improvement only.**

All 4 groups achieve 10/10 verified success with similar wall times (50-53s). The slices do not break the system and show marginal cost improvement, but no capability lift is demonstrated.

---

## 2. Run Matrix

| Group | Flags | Verified | Avg Time | Easy | Med | Hard |
|:---|:---|:---:|:---:|:---:|:---:|:---:|
| Baseline | All OFF | 10/10 | 53.3s | 3/3 | 3/3 | 4/4 |
| PACT Only | PACT=1 | 10/10 | 52.6s | 3/3 | 3/3 | 4/4 |
| PACT+Memory | PACT=1,Mem=1 | 10/10 | 50.0s | 3/3 | 3/3 | 4/4 |
| Full Uplift | All ON | 10/10 | 50.1s | 3/3 | 3/3 | 4/4 |

---

## 3. Analysis

### 3.1 Baseline vs Uplift
- **Wall time**: 53.3s → 50.1s (-6.0%)
- **Verified success**: 100% → 100% (no change)
- **Conclusion**: Marginal cost improvement, no capability lift

### 3.2 Slice Analysis
- **PACT**: -1.3% wall time (53.3s → 52.6s)
- **Skill Memory**: -4.9% wall time (52.6s → 50.0s)
- **SWE-Explore**: +0.2% wall time (50.0s → 50.1s) — negligible

### 3.3 Cold Start Issue
- First run with PACT+Memory: 221s (cold start)
- Subsequent runs: 50s (warm state)
- **Lesson**: Always warm models before evaluation

---

## 4. Governance Safety

| Check | Status |
|:---|:---:|
| Trust mismatch | 0 ✅ |
| Authority drift | 0 ✅ |
| Gate bypass | 0 ✅ |
| Role drift | 0 ✅ |
| Public claim precision | Maintained ✅ |

---

## 5. Recommendation

**No promotion evidence yet. All slices must remain shadow-only.**

Reasoning:
1. All groups achieve 100% verified success — ceiling effect
2. The improvement is in wall time (cost), not capability
3. Need 30+ tasks across easy/medium/hard before any promotion decision
4. Feature flags should remain OFF until full evaluation completes

---

## 6. Next Steps

1. Expand to 30+ tasks with held-out harder tasks
2. Add selector override analysis
3. Track abstain rate and trust mismatch
4. Generate complete per-row evidence records

---

*Report generated: 2026-06-15*
*Status: Preliminary — no promotion evidence. Requires full evaluation with 30+ tasks.*
