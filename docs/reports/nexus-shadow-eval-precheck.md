# Shadow Evaluation Precheck Report

> **Status**: Pilot pass — preflight only, not adoption-ready
> **Date**: 2026-06-15
> **Commit**: `79fb4ad1`
> **Tasks**: 10 per group (easy/medium/hard), warmed state

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

**All slices remain shadow-only. No runtime default change is allowed yet.**

Reasoning:
1. All groups achieve 100% verified success — ceiling effect
2. The improvement is in wall time (cost), not capability
3. Only 10 tasks per group — need 30+ for full evaluation
4. Missing: selector override analysis, per-row evidence records, abstain rate
5. Feature flags must remain OFF until full evaluation completes
6. **Promotion review remains blocked** until 30+ eligible rows, held-out harder tasks, selector override metrics, abstain rate, and full per-row evidence records are available

---

## 6. Next Steps

1. Expand to 30+ eligible shadow rows with held-out harder tasks
2. Add selector override analysis (rule selector vs uplifted selector)
3. Track abstain rate and trust mismatch per-row
4. Generate complete per-row evidence records
5. Only after all above: consider promotion review

---

## 7. What This Report Does NOT Support

- ❌ Promotion to limited runtime adoption
- ❌ Capability lift claims
- ❌ Runtime default changes
- ❌ Any claim beyond "shadow-only, no regression"

---

*Report generated: 2026-06-15*
*Status: Pilot pass — preflight only. Promotion blocked until 30+ eligible rows with full evidence.*
