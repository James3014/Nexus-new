# Full Rerun: Local Qwen Repair Capability Evidence Rebuild — Result

**Date**: 2026-06-19
**Task**: RECOVERY-MAINLINE-02
**Verdict**: 🟡 YELLOW

---

## Summary

16 runs completed across 4 tasks × 4 arms. 0 solved. Real disk-backed evidence produced.

---

## Upstream Abandonment

- M3: MISSING
- S6.7: MISSING
- S6.x: MISSING_DEFERRED
- S6.8: NOT_RECOVERABLE
- Recovery mode: full_rerun

---

## Task Set

| Task | Family | Active |
|------|--------|--------|
| astropy-13236 | stable_local_edit | YES |
| sympy-13852 | stable_local_edit | YES |
| astropy-12907 | retry_sensitive | YES |
| astropy-14182 | stable_local_edit | YES |

Active tasks: 4 (minimum met)

---

## Comparison Arms

| Arm | Model | Nexus | Completed |
|-----|-------|-------|-----------|
| bare_7b | qwen2.5-coder:7b | NO | YES |
| nexus_7b | qwen2.5-coder:7b | YES | YES |
| bare_14b | qwen2.5-coder:14b-instruct-q3_K_M | NO | YES |
| nexus_14b | qwen2.5-coder:14b-instruct-q3_K_M | YES | YES |

All 4 arms completed.

---

## Results

| Arm | Runs | Solved | Syntax | SEARCH | Avg Latency |
|-----|------|--------|--------|--------|-------------|
| bare_7b | 4 | 0 | 0 | 2 | 9749ms |
| nexus_7b | 4 | 0 | 1 | 2 | 4106ms |
| bare_14b | 4 | 0 | 1 | 4 | 15832ms |
| nexus_14b | 4 | 0 | 2 | 4 | 11658ms |

**Total: 16 runs, 0 solved, 4 syntax pass, 12 SEARCH detected**

---

## Nexus Lift Analysis

- **Nexus lift detected**: NO (0/16 solved)
- **Strongest component**: REPLACE_only protocol (SEARCH/REPLACE format compliance)
- **Weakest component**: Actual patch correctness
- **Observation**: Nexus improves format compliance but not repair correctness

---

## Governance

- S5 checkpoint: NO ✅
- Checkpoint adoption: NO ✅
- Production routing: NO ✅
- Public claim: NO ✅
- Source-stale: NO ✅
- Fabricated evidence: NO ✅

---

## Decision

```
Full Rerun Verdict: YELLOW
proceed_to_local_qwen_m4_reentry: NO
reason: 0/16 solved — models produce SEARCH/REPLACE but content doesn't match actual buggy code
recommended_next_step: Improve source anchoring and context quality
```

---

## Files Created

1. artifacts/runtime/full_rerun_upstream_chain_abandonment.json
2. artifacts/runtime/full_rerun_task_set.json
3. artifacts/runtime/full_rerun_comparison_arms.json
4. artifacts/runtime/full_rerun_record_schema.json
5. scripts/run_full_rerun_local_qwen.py
6. artifacts/runtime/full_rerun_local_qwen_repair_records.jsonl
7. artifacts/runtime/full_rerun_nexus_lift_analysis.json
8. artifacts/runtime/full_rerun_attribution_governance_guard.json
9. /Users/jameschen/Downloads/full_rerun_result_20260619.md (this file)
