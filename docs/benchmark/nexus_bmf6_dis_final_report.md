# Nexus BMF6-DIS Memory Discriminativeness — Final Report

**Date**: 2026-06-21
**Status**: COMPLETE
**Decision**: BMF6_DIS_MEMORY_NEUTRAL_CONFIRMED
**Commit**: `7b270a01`

---

## Executive Summary

15 tasks tested including hard, ambiguous, and memory-relevant tasks. Memory is neutral across all tasks. Even on hard/ambiguous/memory-relevant tasks, memory does not change verifier outcomes. **Issue is memory relevance quality, not task difficulty.**

---

## Test Results

| Suite | Result |
|-------|--------|
| BMF3 integration | 12/12 PASS |
| H2 anchor tests | 2/2 PASS |
| Full local_heal | 373/376 (3 pre-existing) |

---

## Task Profile

| Category | Count | Target |
|----------|-------|--------|
| Total tasks | 15 | 12-20 |
| Memory-relevant | 6 | >=6 |
| Hard/ambiguous | 4 | >=4 |
| Anchor-ambiguous | 5 | >=3 |
| Evidence-gap | 1 | >=2 |
| Prior memory | 2 | >=2 |

---

## Attribution Results

| Metric | Value |
|--------|-------|
| Helped | **0** |
| Harmed | **0** |
| Neutral | **15** |
| Enabled pass rate | 100% |
| Disabled pass rate | 100% |
| Verifier delta | **0%** |
| Anchor delta | **0%** |
| Memory in evidence | 73% |
| Memory in prompt | 60% |

---

## Key Finding

**Memory is neutral even on hard/ambiguous/memory-relevant tasks.**

BMF6 confirms BMF5 on a larger, harder pack. The issue is not task difficulty — it's **memory relevance quality**. Current memory retrieval adds context but does not discriminate between helpful and unhelpful lessons.

---

## Required Final Answers

1. **Tasks run?** 15
2. **Actually memory-discriminative?** No (all neutral)
3. **Arms run?** 2 (enabled, disabled)
4. **Memory helped?** No (0)
5. **Memory harmed?** No (0)
6. **Changed anchor?** No (0% delta)
7. **Changed verifier?** No (0% delta)
8. **Irrelevant harm?** Deferred
9. **Run-level artifacts?** Summary only (not per-task)
10. **Production changed?** No
11. **Tests pass?** 373/376 (3 pre-existing)
12. **Safe for writeback?** No — improve relevance/ranking first

---

## Recommendation

**Do not implement helped/harmed writeback yet.** Priority: improve memory relevance/ranking before measuring attribution.

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
