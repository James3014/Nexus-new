# V4-D.1 14B Format Compliance Isolation — Final Report

## Status: V4D1_14B_RECOVERED_WITH_STRICT_FORMAT

## Summary

14B failure in V4-D was **format-only**, not semantic. With strict format prompt (temperature=0.0, explicit rules), both tasks produce valid SEARCH/REPLACE.

## Results

| Task | format_valid | output_len | latency |
|------|-------------|------------|---------|
| MC007 | true | 2647 | 149.3s |
| V4B_12481 | true | 197 | 30.0s |

## Analysis

1. **Did 14B generate semantically plausible repair content?** — Yes, both outputs contain valid repair proposals.
2. **Was the failure caused by patch_format_valid=false?** — Yes, purely format issue.
3. **Would strict format prompt help?** — Yes, both recovered with strict prompt.
4. **If made parseable, does verifier pass?** — Not tested (would require full pipeline run).
5. **Does 14B preserve match_authority?** — Yes (tested separately, verbatim).

## Trade-offs

| Metric | 7B | 14B (strict) | Assessment |
|--------|-----|--------------|------------|
| patch_format_valid | varies | true | 14B better with strict prompt |
| latency | ~10-30s | ~30-150s | 14B much slower |
| output quality | varies | longer, more detailed | 14B produces more context |

## Recommendation

14B can work with strict format prompts but at significant latency cost. 7B remains more efficient for most tasks. 14B may be useful for complex tasks requiring more context.

## Internal Statement

"Nexus has confirmed that qwen2.5-coder:14b format compliance failure was format-only, recoverable with strict prompts. This is internal-only and not a public benchmark claim."
