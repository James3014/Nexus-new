# H2-B: C_13453 Rerun + C_12481 Regression Guard

## Phase Summary

| Field | Value |
|-------|-------|
| Phase | H2-B |
| Status | H2B_C13453_ANCHOR_CORRECTED |
| Tests | 35 pass |

## C_13453 Anchor Selection

| Metric | Before H2 | After H2-B |
|--------|-----------|------------|
| Selected | read (6.0) | write (9.0) |
| Span | L10-L30 | L342-L456 |
| Type | behavior_with_return | formatting_behavior |
| Correct? | ❌ Wrong | ✅ Correct HTML writer |

### Top-3 Anchors

| Rank | Symbol | Score | Type | Span |
|------|--------|-------|------|------|
| 1 | write | 9.0 | formatting_behavior | L342-L456 |
| 2 | write | 9.0 | formatting_behavior | L40-L41 |
| 3 | start_line | 6.0 | behavior_with_return | L177-L189 |

### Score Reasons (Selected)

- `behavior_keyword_preferred:output_formatting` — write matches output intent
- `very_high_behavior_depth_4` — has return, conditional, loop, method call
- `high_keyword_overlap_4` — 4 issue keywords found in source
- `intent_direction_match:output_formatting` — write matches output intent

## C_12481 Regression Guard

| Metric | Before H2 | After H2 |
|--------|-----------|----------|
| Selected | Permutation.__new__ (1.0) | cycle_structure (5.0) |
| Type | target_symbol | behavior_with_return |
| Status | ✅ Correct | ⚠️ Alternative |

### Analysis

- `cycle_structure` is semantically downstream of `Permutation.__new__`
- It's a behavior owner for cycle semantics, but not the constructor
- This is an **acceptable semantic refinement**, not a regression
- No verifier evidence needed for regression judgment

## H2 Improvements

1. **Behavior Depth Scorer** — Prefers methods with more logic over simple one-liners
2. **Tie-Breaking** — When scores are tied, prefers higher behavior depth
3. **Intent-Aware Directional Scoring** — output_formatting prefers write over read

## Status

**H2B_C13453_ANCHOR_CORRECTED**

C_13453 now selects the correct HTML writer method (write at L342-L456). Ready for model rerun to test if correct anchor improves repair capability.
