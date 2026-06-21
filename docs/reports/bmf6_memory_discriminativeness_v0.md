# BMF6-DIS — Memory Discriminativeness Validation

**Status**: `BMF6_DIS_MEMORY_NEUTRAL_CONFIRMED`
**Date**: 2026-06-21
**Commit**: Pending

---

## Executive Summary

15 tasks tested including hard, ambiguous, and memory-relevant tasks. Memory is neutral across all tasks. Even on hard/ambiguous/memory-relevant tasks, memory does not change verifier outcomes. Issue is memory relevance quality, not task difficulty.

---

## Task Profile

| Category | Count |
|----------|-------|
| Total tasks | 15 |
| Memory-relevant | 6 |
| Hard/ambiguous | 4 |
| Anchor-ambiguous | 5 |
| Evidence-gap | 1 |
| Prior memory | 2 |

---

## Attribution Results

| Metric | Value |
|--------|-------|
| Helped | 0 |
| Harmed | 0 |
| Neutral | 15 |
| Enabled pass rate | 100% |
| Disabled pass rate | 100% |
| Verifier delta | 0% |
| Anchor delta | 0% |
| Memory in evidence | 73% |
| Memory in prompt | 60% |

---

## Key Finding

**Memory is neutral even on hard/ambiguous/memory-relevant tasks.**

This confirms BMF5 finding on a larger, harder pack. The issue is not task difficulty — it's memory relevance quality. Current memory retrieval adds context but does not discriminate between helpful and unhelpful lessons.

---

## Recommendation

**Do not implement helped/harmed writeback yet.** Instead, improve memory relevance/ranking:
- Better semantic matching
- Failure-class-specific retrieval
- Recency weighting
- Provenance-based trust scoring

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
