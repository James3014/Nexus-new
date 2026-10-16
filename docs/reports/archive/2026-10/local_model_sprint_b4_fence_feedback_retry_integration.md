# Local Model Sprint B4: Connect Fence Feedback into Existing Retry Loop

**Status:** LOCAL_MODEL_SPRINT_B4_FENCE_FEEDBACK_RETRY_INTEGRATION_PASS
**Date:** 2026-07-01

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/failure_analyzer.py` | Added `REPLACEMENT_MARKDOWN_FENCE` classification |
| `nexus/services/local_heal/orchestrator.py` | Set `last_failure_class` for patch failures |
| `tests/unit/local_heal/test_committee_to_repair_seam_audit.py` | Added 3 B4 tests |

## Commands Run

```bash
uv run pytest tests/unit/local_heal/test_committee_to_repair_seam_audit.py tests/unit/local_heal/test_failure_feedback_builder.py -q
# 18 passed
```

## What Changed

| Before B4 | After B4 |
|-----------|----------|
| `classify_patch_failure` returns `NO_BLOCKS_FOUND` for fence | Returns `REPLACEMENT_MARKDOWN_FENCE` |
| `last_failure_class` only set for verification failures | Also set for patch failures |
| Retry feedback uses generic "VERIFIER_FAIL" | Uses actual failure class from patch synthesis |
| `should_retry` returns True for fence | Returns True (unchanged) |

## How Retry Works Now

1. Patch synthesis fails with `REPLACEMENT_MARKDOWN_FENCE`
2. `_handle_patch_failure` classifies it as `REPLACEMENT_MARKDOWN_FENCE`
3. Sets `ctx.op.last_failure_class = "REPLACEMENT_MARKDOWN_FENCE"`
4. `should_retry` returns True
5. `_handle_retry` increments attempt
6. On next attempt, `build_failure_feedback` receives `failure_class="REPLACEMENT_MARKDOWN_FENCE"`
7. Feedback says "Do NOT use markdown fences" — model gets precise instruction

## Explicit Statements

- No new retry framework created.
- Existing orchestrator retry loop used.
- No parser/sanitizer change.
- No fence stripping/accepting.
- Existing strict guard unchanged.
