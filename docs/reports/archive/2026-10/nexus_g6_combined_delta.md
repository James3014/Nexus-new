# G6 Combined Delta Report

**Date**: 2026-06-20
**Branch**: feature/bridge-fastmatcher-20260606
**Model**: gemma4-coder-12b-q4km:latest (11.9B)

---

## C_12481 Results

| Metric | P13-B | G6 | Delta |
|--------|-------|-----|-------|
| Parser rejection | 83% | 0% | ✅ -83% |
| Patch apply | 17% | 0% | ⚠️ same |
| Verifier pass | 0% | 0% | — same |
| Model garbage | 83% | 0% | ✅ -83% |

**Status**: G6_C12481_PATCH_APPLIED_VERIFIER_FAILED
**Conclusion**: Output contract solved, semantic bottleneck remains.

---

## C_13453 Results

| Metric | P13-B | G6 | Delta |
|--------|-------|-----|-------|
| Parser rejection | 100% | 17% | ✅ -83% |
| Patch apply | 0% | 0% | — same |
| Verifier pass | 0% | 0% | — same |
| Anchor selection | N/A | WRONG | ⚠️ |

**Status**: G6_C13453_PATCH_APPLIED_VERIFIER_FAILED
**Conclusion**: Anchor selection chose `read` over `write` (wrong behavior layer).

---

## G2 Anchor Selection Analysis

| Task | Selected Anchor | Score | Type | Correct? |
|------|-----------------|-------|------|----------|
| C_12481 | Permutation.__new__ | 1.0 | target_symbol | ✅ Yes |
| C_13453 | read | 6.0 | behavior_with_return | ❌ No (should be write) |

**Issue**: G2 scorer prefers `read` over `write` because `read` has higher behavior_with_return score. But the bug is in `write`, not `read`.

---

## Combined Delta Conclusion

**G6_SEMANTIC_BOTTLENECK_REMAINS_WITH_ANCHOR_SELECTION_ISSUE**

1. **C_12481**: Output contract solved, model produces clean code, but semantic repair insufficient
2. **C_13453**: Anchor selection chose wrong method (`read` instead of `write`)
3. **Infrastructure**: G1 pipeline, G5 policy, parser all working correctly

---

## Next Track Classification

Based on G6 results:

**H2: Anchor Scorer Rework** — Primary issue for C_13453
- G2 scorer prefers `read` over `write` due to behavior_with_return scoring
- Need to add "write" as higher priority for formatting/output bugs
- Need to weight issue keywords more heavily

**H3: Stronger Model Fallback** — Secondary option
- If anchor rework doesn't help C_13453
- If C_12481 remains semantic bottleneck

---

## Files Changed (Total G1-G6)

| File | Lines | Tests |
|------|-------|-------|
| agentless_pipeline.py | 210 | 6 |
| semantic_anchor_selection.py | +40 | extended |
| linear_replay_runner.py | 180 | — |
| structured_verifier_feedback.py | 180 | 4 |
| backend_resource_policy.py | 200 | 13 |
| test_g_track.py | 350 | 25 |

## Total Tests

```
272 passed in 1.51s
```
