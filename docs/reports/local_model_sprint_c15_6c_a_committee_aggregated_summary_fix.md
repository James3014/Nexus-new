# C15-6C-A: Committee Aggregated Summary Fix

**Date**: 2026-07-04  
**Status**: `SUMMARY_TRUTH_FIX_PROVEN`

## 1. Task

```text
Fix delegated-retry row-level summary so committee-mode execution reports
provider/stage truth from per-candidate evidence instead of single-provider
fallback fields.
```

## 2. Problem

Live dual-model validation already proved:

```text
- qwen2.5-coder:7b-instruct was actually called
- deepseek-coder:6.7b-instruct was actually called
- both candidates produced candidate-level outcomes
```

But row-level summary still reported:

```text
delegated_retry_stage = provider_not_called
delegated_retry_provider_called = false
```

That summary under-reported actual committee execution.
```

## 3. Change

Files changed:

```text
nexus/services/local_heal/local_model_executor.py
tests/unit/local_heal/test_local_model_executor.py
```

New behavior:

```text
When delegated retry uses committee candidates:
- provider_called is derived from candidate list truth
- stage is derived from candidate apply/rejection outcomes
```

Committee-aware stage mapping now distinguishes:

```text
- committee_candidates_format_rejected
- committee_candidates_empty_patch
- committee_no_winner
- success
```

## 4. Verification

Commands:

```bash
python3 -m py_compile \
  nexus/services/local_heal/local_model_executor.py \
  tests/unit/local_heal/test_local_model_executor.py
```

```bash
uv run pytest \
  tests/unit/local_heal/test_local_model_executor.py \
  -k "committee_no_winner_marks_provider_called_in_summary or committee_no_selected_winner_without_verifier_pass or committee_candidate_records_conversion_status" \
  -q
```

Observed result:

```text
3 passed, 158 deselected in 0.65s
```

## 5. Gate Impact

This does not prove solve success.

It does prove:

```text
- dual-model committee execution is no longer flattened into a false
  provider_not_called summary
- downstream row-level truth is now safer for dual-model and triple-model
  validation gates
```
