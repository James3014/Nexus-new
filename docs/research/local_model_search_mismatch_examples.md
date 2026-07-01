# Local Model SEARCH_MISMATCH Examples

**Date**: 2026-06-30

## What is SEARCH_MISMATCH

SEARCH_MISMATCH occurs when the model's SEARCH block does not match the current
source code. The parser extracts SEARCH/REPLACE blocks, but the validator rejects
them because SEARCH is not found in the source file.

## Example: Paraphrased SEARCH (Invalid)

Model output:
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

Source file:
```python
def double( x ):
    return x * 2
```

**Why invalid**: SEARCH has different whitespace (`x:` vs `x :`). The model
"cleaned up" the source code in SEARCH.

## Example: Stale SEARCH (Invalid)

Model output:
```
FILE: toy/math_util.py
<<<<<<< SEARCH
def double(x):
    result = x * 2
    return result
=======
def double(x):
    return x + x
>>>>>>> REPLACE
```

Source file:
```python
def double(x):
    return x * 2
```

**Why invalid**: SEARCH includes a `result` variable that no longer exists in
the source. The model used an older version of the code.

## Example: Exact SEARCH (Valid)

Model output:
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

Source file:
```python
def double(x):
    return x * 2
```

**Why valid**: SEARCH matches source character-for-character. Only REPLACE
differs.

## Example: SEARCH with extra context (Invalid)

Model output:
```
FILE: toy/math_util.py
<<<<<<< SEARCH
# Math utilities
def double(x):
    return x * 2
=======
# Math utilities
def double(x):
    return x + x
>>>>>>> REPLACE
```

Source file:
```python
def double(x):
    return x * 2
```

**Why invalid**: SEARCH includes a comment that is not in the source file.
The model added extra context.

## Failure Taxonomy for SEARCH_MISMATCH

| Root cause | output_class | search_mismatch | Next action |
|-----------|-------------|----------------|-------------|
| Paraphrased SEARCH | SEARCH_REPLACE_SEARCH_MISMATCH | true | Improve source copying |
| Stale source | SEARCH_REPLACE_SEARCH_MISMATCH | true | Refresh source context |
| Extra context | SEARCH_REPLACE_SEARCH_MISMATCH | true | Trim SEARCH to exact match |
| Whitespace diff | SEARCH_REPLACE_SEARCH_MISMATCH | true | Preserve whitespace exactly |
| Hallucinated source | SEARCH_REPLACE_SEARCH_MISMATCH | true | Copy from provided source |
