# Local Model Sprint A4: REPLACEMENT_MARKDOWN_FENCE Feedback

**Status:** LOCAL_MODEL_SPRINT_A4_FENCE_FEEDBACK_PASS
**Date:** 2026-07-01

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/failure_feedback_builder.py` | Added REPLACEMENT_MARKDOWN_FENCE specific feedback |
| `tests/unit/local_heal/test_failure_feedback_builder.py` | Added 4 fence feedback tests |

## Commands Run

```bash
uv run pytest tests/unit/local_heal/test_failure_feedback_builder.py -q
# 5 passed
```

## Test Counts

- `test_failure_feedback_builder.py`: 5 passed (1 existing + 4 new)

## New Feedback Behavior

For `failure_class == "REPLACEMENT_MARKDOWN_FENCE"`:
- Explicitly tells model NOT to use markdown fences
- Explicitly tells model NOT to output ```python or ```diff
- Instructs model to output ONLY replacement code inside REPLACE block
- No prose, no explanation
- Shows exact REPLACE block format

For other failure classes: unchanged.

## Explicit Statements

- No parser/sanitizer change.
- Guard remains strict (anchored_edit rejection unchanged).
- Feedback is wording only, does not accept fenced output.
