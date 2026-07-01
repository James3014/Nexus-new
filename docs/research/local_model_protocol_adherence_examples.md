# Local Model Protocol Adherence Examples

**Date**: 2026-06-30

## Instability Evidence

toy-math-solve across runs:

| Run | output_len | output_class | contains_search_marker | pipeline_failure_reason |
|-----|-----------|-------------|----------------------|------------------------|
| C11 | 759 | UNKNOWN | false | SEARCH_MISMATCH:SEARCH_MISMATCH |
| C12 | 338 | UNKNOWN | false | NO_BLOCKS_FOUND:MICRO_VERIFY_CONTEXT_MISSING |

Pattern: non-deterministic protocol adherence.

## Failure Classes

### NO_BLOCKS_FOUND
Model output contains no SEARCH/REPLACE markers at all.
- Output may be natural language
- Output may be raw code
- Output may be unified diff

### SEARCH_MISMATCH
Model output contains SEARCH/REPLACE markers but SEARCH doesn't match source.
- SEARCH paraphrased source
- SEARCH used stale source
- SEARCH changed whitespace

### FENCED_SEARCH_REPLACE
Model output contains SEARCH/REPLACE but wrapped in markdown fences.
- Content may be correct
- Format is wrong

### REFUSAL_DETECTED
Model refused to provide fix.
- Apology
- "I can't help"
- "This is outside my capabilities"

## Successful Pattern

```
FILE: toy/math_util.py
<<<<<<< SEARCH
def double(x):
    return x * 2
=======
def double(x):
    return x + x
>>>>>>> REPLACE
```

Key properties:
- SEARCH matches source exactly
- REPLACE makes functional change
- No prose before/after
- No markdown fences
- No unified diff
