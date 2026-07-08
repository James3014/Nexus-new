# P10: Semantic Anchor Selection Upgrade Report

## Phase Summary

| Field | Value |
|-------|-------|
| Phase | P10 |
| Commit SHA | d9b62b10 |
| Status | P10_SEMANTIC_ANCHOR_SELECTION_READY |
| Files Changed | 2 core files |
| Tests Run | 224 (all passing) |
| Tests Added | 16 new P10-specific tests |

## Changes Made

### 1. Semantic Anchor Selection Module (`semantic_anchor_selection.py`)

Created new module with three main components:

#### AnchorCandidateGenerator
Generates candidate anchors from multiple sources:
- **Failing stack frame**: The symbol from the failing traceback
- **Target symbol**: The explicitly targeted function/class
- **Direct caller**: Functions that call the target
- **Direct callee**: Functions called by the target
- **Formatting behavior**: Methods with formatting/rendering in their name

#### SemanticAnchorScorer
Scores candidates based on 5 dimensions:
1. **Behavior ownership**: Symbol name suggests behavior (format, write, render) vs mechanical (iter, loop, zip)
2. **Failing trace relevance**: Proximity to the failing stack frame
3. **Span size**: Prefers smaller, complete methods (≤10 lines optimal)
4. **Keyword overlap**: Overlap with issue description keywords
5. **Leaf method**: Prefers methods with no nested definitions

Scoring weights:
- Behavior ownership: +2.0 (behavior) / -1.0 (mechanical)
- Failing trace: +3.0 (is failing symbol) / +1.0 (contains failing symbol)
- Span size: +2.0 (≤10 lines) / +1.0 (≤30 lines) / -2.0 (>100 lines)
- Keyword overlap: +2.0 (≥3 keywords) / +1.0 (≥1 keyword)
- Leaf method: +1.0 (no nested defs) / -1.0 (multiple nested defs)

#### SemanticAnchorSelector
Selects the best candidate:
- Sorts by score descending
- Takes top-k candidates (default k=5)
- Selects best if above minimum score threshold
- Returns selection reason with score and candidate type

### 2. High-Level API

`select_semantic_anchor()` function provides a single entry point:
```python
result = select_semantic_anchor(
    file_path="html.py",
    source_text=source,
    target_symbol="write",
    failing_symbol="iter_str_vals",
    issue_keywords=["format", "html", "table"],
    call_graph={"write": ["iter_str_vals"]},
)
```

## Test Results

```
224 passed in 1.56s
```

## C_13453 Analysis

For the C_13453 task (astropy HTML writer ignores formats parameter):

**Original anchor** (P5): `iter_str_vals` call site in `HTML.write()`
- Problem: Anchor was at the wrong semantic layer — the call site, not the formatting behavior

**Semantic anchor selection** would generate candidates:
1. `HTML.write` (target symbol) — contains the iteration logic
2. `_set_col_formats` (if exists) — would be found by formatting behavior scorer
3. `write` method of parent class — direct caller

**Expected improvement**: The scorer would prefer a method that owns the formatting behavior over a mechanical iteration loop.

## Proceed to P11

P10 tests pass. Proceeding to P11 to rerun hard tasks with improved anchor selection.
