# Nexus BMF5-HHA Memory Helped/Harmed Attribution — Final Report

**Date**: 2026-06-21
**Status**: COMPLETE
**Decision**: BMF5_HHA_NEUTRAL_OR_INCONCLUSIVE
**Commit**: `5a615da1`

---

## Executive Summary

10 tasks tested across memory_enabled / memory_disabled arms. Memory is present in 80% of tasks, influences anchor scoring for 60%, but does not change verifier outcomes. **Memory is NEUTRAL for all tasks.**

---

## Test Results

| Suite | Result |
|-------|--------|
| BMF3 integration | 12/12 PASS |
| H2 anchor tests | 2/2 PASS |
| Receipt tests | 17/19 (2 pre-existing) |
| Full local_heal | 373/376 (3 pre-existing) |

---

## Attribution Summary

| Metric | Value |
|--------|-------|
| Tasks tested | 10 |
| Arms run | 2 (enabled / disabled) |
| Helped | 0 |
| Harmed | 0 |
| Neutral | 10 |
| Memory retrieval rate | 100% |
| Memory prompt inclusion | 80% |
| Memory anchor influence | 60% |
| Verifier pass delta | **0%** |

---

## Interpretation

**Memory is safe (no harm).** Current memory retrieval adds context but does not materially change repair outcomes.

| Finding | Implication |
|---------|-------------|
| No HELPED signal | Memory not yet discriminating enough to improve outcomes |
| No HARMED signal | Memory safe to keep enabled |
| 80% prompt inclusion | Memory enters context but model doesn't act on it |
| 60% anchor influence | Memory affects scoring but not final decision |

**Recommendation**: Future work should focus on making memory more discriminating (better ranking, relevance filtering) rather than adding more memory volume.

---

## Required Final Answers

1. **Tasks run?** 10
2. **Arms run?** 2 (enabled, disabled)
3. **Memory helped?** No (0 tasks)
4. **Memory harmed?** No (0 tasks)
5. **Neutral?** 10
6. **Inconclusive?** 0
7. **Memory in evidence packet?** Yes (80%)
8. **Memory in prompt?** Yes (80%)
9. **Memory influenced anchor?** Yes (60%)
10. **Verifier pass delta?** 0% (flat)
11. **selected_ids reconstructible?** Yes
12. **Stale trace leakage?** No
13. **Production source changed?** No
14. **Tests pass?** 373/376 (3 pre-existing)
15. **Safe for helped/harmed writeback?** No (memory is neutral, writeback would be inaccurate)

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
