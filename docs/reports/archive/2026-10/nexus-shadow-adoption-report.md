# Capability Lift Validation: Preliminary Easy-Bucket Shadow Report

> **Status**: Preliminary — not a promotion report. No promotion evidence yet.

**Date**: 2026-06-15
**Commit**: `1c9dce65`
**Eval Tasks**: 5 per group (easy bucket only, preliminary)

---

## 1. Verdict

**No measurable capability lift. Cost/clarity improvement only.**

All groups achieved 5/5 verified success on easy tasks. The improvement is in wall time (cost), not in verified success rate (capability). No trust mismatch, no authority drift, no gate bypass. This report confirms the slices do not break the system, but provides zero evidence of capability improvement.

---

## 2. Dataset

| Bucket | Tasks | Held-out |
|:---|:---:|:---:|
| Easy | 5 | 2 |
| Medium | 0 | 0 |
| Hard | 0 | 0 |
| **Total** | **5** | **2** |

**Note**: This is a preliminary run with 5 easy tasks. Full evaluation requires 30+ tasks across all buckets.

---

## 3. Run Matrix

| Group | Flags | Avg Wall Time | Verified Success |
|:---|:---|:---:|:---:|
| **Baseline** | All OFF | 69.5s | 5/5 (100%) |
| **PACT Only** | PACT=1 | 63.9s | 5/5 (100%) |
| **PACT + Memory** | PACT=1, Memory=1 | 61.9s | 5/5 (100%) |
| **Full Uplift** | All ON | 61.5s | 5/5 (100%) |

---

## 4. Main Metrics

| Metric | Baseline | PACT Only | PACT+Memory | Full Uplift |
|:---|:---:|:---:|:---:|:---:|
| Verified success rate | 100% | 100% | 100% | 100% |
| First-pass rate | 100% | 100% | 100% | 100% |
| Abstain rate | 0% | 0% | 0% | 0% |
| Trust mismatch rate | 0% | 0% | 0% | 0% |
| Avg wall time | 69.5s | 63.9s | 61.9s | 61.5s |
| Wall time improvement | — | -8.1% | -10.9% | -11.5% |

---

## 5. Slice Analysis

### Slice A (PACT)
- **Lift**: Wall time -8.1% (69.5s → 63.9s)
- **Interpretation**: Cost/clarity lift only. No capability improvement.
- **Evidence**: All tasks passed in both groups.

### Slice B (Skill Memory)
- **Lift**: Additional -2.8% (63.9s → 61.9s)
- **Interpretation**: Marginal cost improvement. No capability improvement.
- **Evidence**: All tasks passed in both groups.

### Slice C (SWE-Explore)
- **Lift**: Additional -0.6% (61.9s → 61.5s)
- **Interpretation**: Negligible improvement. No capability improvement.
- **Evidence**: All tasks passed in both groups.

---

## 6. Governance Safety

| Check | Status |
|:---|:---:|
| Authority drift | ✅ 0 |
| Gate bypass | ✅ 0 |
| Trust mismatch | ✅ 0% |
| Public claim precision | ✅ Maintained |
| Role drift | ✅ 0 |

---

## 7. Recommendation

**No promotion evidence yet. All slices must remain shadow-only.**

Reasoning:
1. Only 5 easy tasks evaluated — far below the 30-task minimum for adoption gate
2. No medium/hard tasks — cannot assess performance on harder tasks where lift would matter
3. All groups achieved 100% verified success on easy tasks — ceiling effect, no room for capability lift
4. The improvement is in wall time (cost), not in verified success rate (capability)
5. No selector override analysis — cannot compare rule selector vs uplifted selector
6. No held-out validation — cannot assess generalization
7. Feature flags must remain OFF until full evaluation with 30+ tasks across easy/medium/hard completes

**This report is合格的 preliminary shadow report，不合格的 promotion report。**

---

## 8. Residual Risks

1. **Sample size**: Only 5 easy tasks evaluated. Need 30+ across all buckets.
2. **No medium/hard tasks**: Cannot assess performance on harder tasks where SWE-Explore and Skill Memory would theoretically help.
3. **No held-out validation**: Need separate held-out set for final validation.
4. **No selector override analysis**: Cannot compare rule selector vs uplifted selector quality.
5. **Cost variance**: Wall time varies significantly (47s-82s), suggesting unstable measurements.
6. **Easy bucket ceiling**: 100% success rate leaves no room for capability lift measurement.

---

## 9. Next Steps (Required for Promotion)

To move from "preliminary shadow report" to "adoption-gate report", must complete:

1. **Expand to 30+ eligible shadow rows** across easy/medium/hard buckets
2. **Add held-out harder route/evidence tasks** — this is where lift would actually matter
3. **Add rule selector vs uplifted selector override analysis**
4. **Track selector override verified rate** — must beat baseline on harder tasks
5. **Track abstain rate** — must not increase
6. **Track cost per verified task** — must not increase
7. **Verify trust mismatch rate stays at 0%**

---

*Shadow report generated: 2026-06-15*
*Status: Preliminary — no promotion evidence. Requires full evaluation with 30+ tasks.*
