# Capability Lift Validation: 30-Task Shadow Report

**Status**: Preliminary — no promotion evidence yet
**Date**: 2026-06-15
**Commit**: `18784390`
**Eval Tasks**: 30 (10 easy, 10 medium, 10 hard)

---

## 1. Verdict

**No measurable capability lift. Cost/clarity improvement only.**

PACT Only achieved 30/30 (100%) vs Baseline 11/30 (37%). The improvement is dramatic but requires careful interpretation — baseline failures are pipeline code-path issues, not actual task failures.

---

## 2. Run Matrix

| Group | Flags | Verified | Avg Time | Easy | Med | Hard |
|:---|:---|:---:|:---:|:---:|:---:|:---:|
| Baseline | All OFF | 11/30 (37%) | 62.8s | 0/10 | 1/10 | 10/10 |
| PACT Only | PACT=1 | 30/30 (100%) | 54.5s | 10/10 | 10/10 | 10/10 |
| PACT+Memory | PACT=1,Mem=1 | *pending* | — | — | — | — |
| Full Uplift | All ON | *pending* | — | — | — | — |

---

## 3. Key Findings

### 3.1 Baseline Anomaly
- Easy/Medium tasks fail in baseline (0/10, 1/10)
- Hard tasks pass (10/10)
- **Root cause**: Baseline pipeline uses different code path for easy tasks that doesn't generate run reports
- This is NOT a capability issue — it's a pipeline routing difference

### 3.2 PACT Impact
- PACT mode changes pipeline behavior: all 30 tasks pass
- Wall time: 62.8s → 54.5s (-13%)
- PACT appears to enable a different execution path that produces verified_pass results

### 3.3 Interpretation
- The 37% → 100% jump is **not** capability lift
- It's a pipeline code-path difference: PACT triggers a different execution path
- Baseline easy/medium tasks fail because they use a path that doesn't generate run reports
- Real capability lift can only be measured on hard tasks where both paths produce comparable results

---

## 4. Governance Safety

| Check | Baseline | PACT Only |
|:---|:---:|:---:|
| Trust mismatch | 0 | 0 |
| Authority drift | 0 | 0 |
| Gate bypass | 0 | 0 |
| Role drift | 0 | 0 |

---

## 5. Recommendation

**No promotion evidence yet. All slices must remain shadow-only.**

Reasoning:
1. Baseline failures are pipeline code-path issues, not capability gaps
2. PACT improvement is from enabling a different execution path, not from better selector/retrieval
3. Need to fix eval harness to use consistent code path across all groups
4. Need 30+ tasks with consistent success criterion before any promotion

---

## 6. Next Steps

1. Fix eval harness: ensure all groups use the same pipeline code path
2. Re-run with fixed harness to get comparable results
3. Add medium/hard held-out tasks
4. Add selector override analysis
5. Track abstain rate and trust mismatch

---

*Report generated: 2026-06-15*
*Status: Preliminary — requires harness fix before valid comparison*
