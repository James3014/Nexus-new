# Local Model Output Contract Examples

**Date**: 2026-06-30

## Valid Output Examples

### VALID_SEARCH_REPLACE

```
FILE: src/utils.py
<<<<<<< SEARCH
    return os.path.join(a, b)
=======
    return os.path.join(a, b) if a and b else ''
>>>>>>> REPLACE
```

**Why valid:**
- Contains exact SEARCH/REPLACE markers
- SEARCH matches source code
- REPLACE has functional change
- No markdown fences
- No prose before/after
- No unified diff format

## Invalid Output Examples

### FENCED_SEARCH_REPLACE

````
```
FILE: src/utils.py
<<<<<<< SEARCH
    return os.path.join(a, b)
=======
    return os.path.join(a, b) if a and b else ''
>>>>>>> REPLACE
```
````

**Why invalid:** Wrapped in markdown code fences. Parser rejects.

### UNIFIED_DIFF

```
--- a/src/utils.py
+++ b/src/utils.py
@@ -1,3 +1,3 @@
 def join(a, b):
-    return os.path.join(a, b)
+    return os.path.join(a, b) if a and b else ''
```

**Why invalid:** Uses unified diff format, not SEARCH/REPLACE markers.

### NATURAL_LANGUAGE

```
The issue is that os.path.join doesn't handle empty strings.
I need to add a check for empty arguments before joining.
Here's the fix: add an if statement to check if a and b are non-empty.
```

**Why invalid:** Natural language explanation, no code blocks.

### MALFORMED_SEARCH_REPLACE

```
<<<<<<< SEARCH
    return os.path.join(a, b)
```

**Why invalid:** Has SEARCH marker but missing REPLACE marker.

### REFUSAL

```
I'm sorry, but I can't help with that. This seems to be
outside my capabilities. You might want to consult the
documentation for os.path.join.
```

**Why invalid:** Model refused to provide fix.

## Failure Taxonomy

| output_class | parse_error_kind | pipeline_final_patch_len | Next blocker |
|-------------|-----------------|------------------------|--------------|
| VALID_SEARCH_REPLACE | none | > 0 | candidate isolation / verifier |
| FENCED_SEARCH_REPLACE | REPLACEMENT_MARKDOWN_FENCE | 0 | prompt contract |
| UNIFIED_DIFF | none | 0 | prompt contract |
| NATURAL_LANGUAGE | none | 0 | prompt contract |
| MALFORMED_SEARCH_REPLACE | none | 0 | prompt contract |
| REFUSAL | REFUSAL_DETECTED | 0 | prompt contract / model selection |
| EMPTY | none | 0 | provider / model selection |
| UNKNOWN | none | 0 | telemetry projection |

## M1 Diagnostic Branching

```
if pipeline_final_patch_len = 0:
    → next issue is output/prompt/protocol contract
    → check output_class, parse_error_kind
    → check pipeline_failure_reason

if pipeline_final_patch_len > 0:
    → verify candidate hash, isolated apply, verifier, receipt

if output_class = null AND output_len > 0:
    → telemetry projection regression (C7 fields not flowing to JSONL)
```
