# P11-C: Result Triage Report

## Triage Status: P11_TRIAGE_COMPLETE

## Per-Task Results

| Task | Status | Failure Class | Parser Result | Anchor |
|------|--------|---------------|---------------|--------|
| C_13453 | P11_PARSER_REJECTED_BAD_OUTPUT | Markdown fences | 3/3 rejected | Semantic selection worked (score=5.0) |
| C_11618 | P11_ANCHOR_NOT_IN_SOURCE | Infrastructure | N/A | Hardcoded anchor wrong |
| C_12481 | P11_PARSER_REJECTED_BAD_OUTPUT | Prose contamination | 3/3 rejected | Semantic selection failed |

## Failure Analysis

### C_13453 (astropy HTML writer)
- **Anchor**: Semantic selection worked — selected `write` method (score=5.0, type=formatting_behavior)
- **Model output**: All 3 candidates wrapped in markdown code fences
- **Parser rejection**: `REPLACEMENT_MARKDOWN_FENCE` × 3
- **Root cause**: Model habitually wraps code in ```` ```python ... ``` ````

### C_11618 (sympy Point.distance)
- **Anchor**: Hardcoded anchor doesn't match source at base_commit
- **Source at d4f8832c21**: `return sqrt(sum([(a - b)**2 for a, b in zip(self.args, p.args if isinstance(p, Point) else p)]))`
- **Hardcoded anchor**: References `_normalize_dimension` which doesn't exist at this commit
- **Root cause**: Anchor was from a different version of the code

### C_12481 (sympy Permutation)
- **Anchor**: Hardcoded anchor found (1 occurrence)
- **Model output**: Mix of prose contamination and markdown fences
- **Parser rejection**: `REPLACEMENT_PROSE_CONTAMINATION` × 2, `REPLACEMENT_MARKDOWN_FENCE` × 1
- **Root cause**: Model outputs natural language explanations instead of pure code

## Decision Tree Classification

**Case B**: Most failures are parser rejections (prose contamination, markdown fences)

- C_13453: 3/3 markdown fence rejections
- C_12481: 2/3 prose contamination, 1/3 markdown fence
- C_11618: Infrastructure (anchor mismatch)

**Primary bottleneck**: Model output contract — model wraps code in markdown and/or adds prose

## Recommended P13 Branch

**P13-B: Replacement Output Contract Hardening**

Rationale:
1. Model consistently outputs markdown fences (C_13453, C_12481)
2. Model sometimes outputs prose explanations (C_12481)
3. Strict parser correctly rejects these — parser is working as designed
4. Fix should strengthen the prompt contract to prevent these patterns
5. Add bounded retry with parser feedback

## Proceed to P13-B

P13-B will:
1. Strengthen prompt to forbid markdown fences and prose
2. Add rejection examples to prompt
3. Add one bounded retry with parser failure feedback
4. Test that prose output is rejected and clean code is accepted
