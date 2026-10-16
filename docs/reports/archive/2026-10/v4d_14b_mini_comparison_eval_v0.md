# V4-D 14B Mini Comparison Evaluation — Final Report

## Status: V4D_14B_COMPARISON_PASS_INTERNAL_ONLY

## Summary

14B (qwen2.5-coder:14b-instruct-q3_K_M) evaluated on 2 tasks against 7B baseline.

## Results

| Task | Model | Latency | patch_format_valid | match_authority | export_classification |
|------|-------|---------|-------------------|-----------------|----------------------|
| MC007 | 14B | 28.7s | false | verbatim | model_patch_success_candidate |
| V4B_12481 | 14B | 13.5s | false | verbatim | model_patch_success_candidate |

## Comparison to 7B

| Metric | 7B | 14B | Assessment |
|--------|-----|-----|------------|
| patch_format_valid | varies | false | No clear gain |
| match_authority | verbatim | verbatim | Equivalent |
| latency | ~10-20s | ~14-29s | 14B slower |
| governance | preserved | preserved | Equivalent |

## Primary Questions

1. **Does 14B produce valid patches more reliably?** — No clear evidence in this small sample.
2. **Does 14B reduce need for canonical recovery?** — Not tested in this comparison.
3. **Does 14B reduce retry count?** — Both used 0 retries.
4. **Does 14B preserve claim separation?** — Yes.
5. **Does 14B justify higher local compute cost?** — Not in this sample; latency is higher.

## Internal Statement

"Nexus has internally evaluated qwen2.5-coder:14b on a small controlled real-task comparison against the existing 7B evidence baseline. This is internal-only and not a public benchmark claim."

## Recommendation

No clear gain over 7B in this small sample. Continue using 7B as primary model. 14B evaluation can be expanded later if needed.
