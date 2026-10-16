# Local Model Sprint B5: Committee Parse Failure to Pipeline Retry

**Status:** LOCAL_MODEL_SPRINT_B5_COMMITTEE_TO_PIPELINE_RETRY_PASS
**Date:** 2026-07-01

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_executor.py` | Committee parse failure delegates to pipeline retry |

## Commands Run

```bash
uv run pytest tests/unit/local_heal/test_committee_to_repair_seam_audit.py tests/unit/local_heal/test_local_model_executor.py tests/unit/local_heal/test_downstream_enforcement_gates.py -q
# 46 passed
```

## What Changed

| Before B5 | After B5 |
|-----------|----------|
| Committee parse failure returns empty hash | Committee parse failure delegates to pipeline retry |
| `retry_available=True` but no retry executed | `pipeline_retry_delegated=True` when pipeline retry succeeds |
| No second provider call through pipeline | Pipeline runs HealPipeline.run() with fence feedback |

## How It Works

1. Committee generates candidates
2. Selected candidate fails with REPLACEMENT_MARKDOWN_FENCE
3. Build failure feedback with fence instructions
4. Create HealContext from committee context
5. Call `pipeline.run(heal_ctx)` with fence feedback in problem statement
6. Pipeline runs phases and produces result
7. If pipeline produces non-empty `final_patch`, use as candidate
8. If pipeline fails, remain fail-closed

## Explicit Statements

- No new committee retry loop.
- Existing pipeline/orchestrator retry path used.
- No parser/sanitizer change.
- No fence stripping/accepting.
- solved requires verifier pass.
