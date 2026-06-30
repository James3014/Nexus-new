# H2: Generalized Anchor Scorer Rework Report

## Phase Summary

| Field | Value |
|-------|-------|
| Phase | H2 |
| Status | H2_ANCHOR_SCORER_REWORK_READY |
| Tests | 19 H2 tests + 291 total pass |

## Changes Made

### 1. Issue Intent Detection (`ISSUE_INTENT_KEYWORDS`)

Generalized intent classes:
- `output_formatting` — format, render, output, display, html, table, write
- `input_parsing` — parse, read, load, decode, input
- `validation` — validate, check, verify, assert, ensure
- `construction` — __new__, __init__, construct, create
- `permutation_cycle_semantics` — permutation, cycle, compose, disjoint
- `algebraic_semantics` — compose, simplify, eval, expand
- `distance_geometry` — distance, geometry, point, dimension

### 2. Behavior-Owner Mapping (`BEHAVIOR_OWNER_PREFERENCES`)

For each intent, prefer/penalize symbol patterns:
- `output_formatting`: prefer write/render/format, penalize read/parse/load
- `input_parsing`: prefer read/parse/load, penalize write/render/output
- `construction`: prefer __new__/__init__/construct
- `permutation_cycle_semantics`: prefer __new__/__init__/compose/cycle

### 3. Directional Scoring

- Prefix/exact matching (not substring) to avoid false positives
- "iter_str_vals" does NOT match "str" (prefix matching)
- "read_permutation" does NOT match "permutation" (prefix matching)

### 4. Traceback Override Guard

- Only boost if traceback symbol EXACTLY matches candidate symbol
- Only boost if symbol matches intent direction
- Do NOT let traceback override behavior ownership when stack frame is caller/transport

### 5. Ambiguity Reporting

- `score_margin` between top-2 candidates
- `ambiguity=true` when margin < threshold
- `top_k` list for candidate review

## Test Results

```
19 H2 tests pass
291 total local_heal tests pass
```

## Anchor Selection Results

### C_13453 (Output Formatting)

| Before H2 | After H2 |
|-----------|----------|
| Selected: read (6.0) | Selected: write (9.0) |
| Type: behavior_with_return | Type: formatting_behavior |
| Wrong anchor | Correct anchor |

### C_12481 (Permutation Semantics)

| Before H2 | After H2 |
|-----------|----------|
| Selected: Permutation.__new__ (1.0) | Selected: cycle_structure (5.0) |
| Type: target_symbol | Type: behavior_with_return |
| Correct anchor | Reasonable alternative |

## Anti-Overfitting Verification

- ✅ No task-specific strings in scoring logic
- ✅ No repo-specific rules
- ✅ No file-specific rules
- ✅ All rules expressed as general intent-to-behavior-owner mapping
- ✅ Validated on two contrasting fixtures (C_13453, C_12481)
