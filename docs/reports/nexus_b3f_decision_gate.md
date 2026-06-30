# B3-F: Decision Gate

## Status: B3_MODEL_LIMIT_CONFIRMED_AFTER_DEEP_EVIDENCE

## B3 Results Summary

| Phase | Result |
|-------|--------|
| B3-A RCA | Missing format application mechanism identified |
| B3-B Deep Evidence | 5 CodeIntel items + format flow diagram built |
| B3-C 3B Advisory | Valid, confidence=65%, recommended try 7B |
| B3-D Rust Probe | Not blocking (deferred) |
| B3-E 12B Rerun | 2 candidates, both apply failed (anchor mismatch + wrong mechanism) |

## Key Findings

1. **Deep evidence identified the exact bug**: `_set_col_formats()` sets `col.info.format` but `iter_str_vals()` ignores it.

2. **12B still can't produce correct fix**: Even with deep evidence showing the exact data flow, 12B produces:
   - Candidate 1: Sets `col.info.values` (wrong attribute)
   - Candidate 2: Full method rewrite that doesn't match anchor

3. **3B advisory was correct**: Said evidence is partially sufficient, confidence=65%.

4. **Root cause confirmed**: Model doesn't understand the interaction between `_set_col_formats` and `iter_str_vals` even when told the data flow.

## Conclusion

**B3_MODEL_LIMIT_CONFIRMED_AFTER_DEEP_EVIDENCE**

Native evidence is now deep enough to explain the bug mechanism. But local 12B still cannot produce correct fix. This confirms the model is the primary bottleneck, not evidence quality.

## Next Steps

1. **Prepare stronger model fallback approval packet** — cloud API or larger local model
2. **Build capability curve on easier tasks** — test if binding helps on simpler bugs
3. **Rust kernel for evidence integrity** — not blocking current bottleneck
