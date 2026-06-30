# M6: Multi-Model Delta Analysis on C_13453

## Phase Summary

| Field | Value |
|-------|-------|
| Phase | M6 |
| Status | M6_C13453_SEMANTIC_FAIL |
| Models | 3B → 7B → 12B (sequential) |

## Results by Model

### M3: 3B Advisory
- **Output**: `output_formatting` intent, confidence 0.95
- **Recommendation**: `should_abstain: true`, `should_try_7b: false`
- **Analysis**: 3B correctly identified the task as difficult

### M4: 7B Candidate Generation
- **Candidates**: 3/3 ABSTAIN
- **Analysis**: 7B refused to generate patches — correct behavior for difficult task

### M5: 12B Semantic Fallback
- **Candidates**: 2 generated, 0 verifier pass
- **Candidate 1**: Tried `self.formats` but replacement incomplete
- **Candidate 2**: Tried `HTML.write(table)` — infinite recursion
- **Analysis**: 12B doesn't understand astropy codebase well enough

## Delta Analysis

| Metric | H2-B Baseline | M6 Multi-Model |
|--------|---------------|----------------|
| Anchor | write (9.0) ✅ | write (9.0) ✅ |
| 3B advisory | N/A | Correct intent, recommended abstain |
| 7B candidates | N/A | 3/3 abstain |
| 12B candidates | N/A | 2 generated, 0 pass |
| Verifier pass | 0 | 0 |
| Status | ANCHOR_CORRECTED | SEMANTIC_FAIL |

## Key Findings

1. **3B advisory is useful**: Correctly identified intent and recommended abstain
2. **7B abstention is correct**: Recognized task difficulty, refused to generate bad patches
3. **12B semantic failure**: Model doesn't understand astropy codebase well enough
4. **Correct anchor doesn't guarantee fix**: Even with correct anchor, model can't produce correct replacement

## Conclusion

**M6_MODEL_SEMANTIC_BOTTLENECK_REMAINS**

The sequential multi-model cascade works correctly:
- 3B classifies intent
- 7B abstains when uncertain
- 12B tries but fails semantically
- Nexus control plane makes final selection

But the core bottleneck remains: **local models don't have enough semantic understanding of the astropy codebase to produce correct fixes**.

## Next Steps

1. Consider H3: Stronger model fallback (cloud API or larger local model)
2. Consider task re-selection for easier bugs
3. Consider context expansion (more code context for the model)
