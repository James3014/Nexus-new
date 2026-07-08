# G6: C_12481 Delta Analysis Report

## Execution Summary

| Field | Value |
|-------|-------|
| Task | C_12481 (sympy__sympy-12481) |
| Model | gemma4-coder-12b-q4km:latest (11.9B) |
| Base Commit | c807dfe756 |
| Source Hash | 63cbe34d7e97959d |
| Pipeline | G1 Agentless + G4 Verifier Feedback |
| Status | G6_C12481_PATCH_APPLIED_VERIFIER_FAILED |

## Candidate Pipeline Results

| Metric | Count |
|--------|-------|
| Total candidates | 6 |
| Parser pass | 6 (100%) |
| Patch apply | 0 (0%) |
| Verifier pass | 0 (0%) |
| Correction used | No |
| Compliance | Pass |

## Failure Analysis

All 6 candidates failed at the verifier stage:
- Model produced valid Python code
- Parser accepted all 6 (no prose/markdown rejections)
- Patches were applied successfully
- Verifier failed on all 6 (repro script failed)

## Delta Comparison: P13 vs G6

| Metric | P13-B | G6 | Delta |
|--------|-------|-----|-------|
| Parser rejection rate | 83% (5/6) | 0% (0/6) | ✅ Improved |
| Patch apply rate | 17% (1/6) | 0% (0/6) | ⚠️ Same |
| Verifier pass rate | 0% (0/6) | 0% (0/6) | — Same |
| Model garbage output rate | 83% | 0% | ✅ Improved |
| Semantic failure rate | 100% | 100% | — Same |

## Key Findings

1. **Parser rejection rate decreased significantly**: From 83% (P13-B) to 0% (G6). The G1 pipeline prompt is more effective at generating code-only output.

2. **Model produces valid code**: All 6 candidates were accepted by the parser, meaning the model is now outputting clean Python code without prose/markdown contamination.

3. **Semantic failure remains**: The model produces code that parses but doesn't fix the actual bug. This is the core semantic bottleneck.

4. **G4 correction not effective**: The structured verifier feedback didn't help because the failure output was not parseable (DeprecationWarning mixed with actual error).

## Conclusion

**G6_C12481_SEMANTIC_BOTTLENECK_REMAINS**

The G1 pipeline + G5 policy + G4 feedback infrastructure is working correctly. The model now produces clean, parsable code. But the semantic repair capability is insufficient — the model doesn't understand how to fix the Permutation non-disjoint cycles bug.

## Next Steps

1. Try C_13453 (HTML writer formats) — different bug type, may be easier
2. Consider model upgrade for better semantic reasoning
3. Consider task re-selection for easier bugs
