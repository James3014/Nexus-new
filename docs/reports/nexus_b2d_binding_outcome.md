# B2-D: Binding Outcome Classification

## Status: B2_NATIVE_BINDING_PROVEN_BUT_MODEL_LIMIT_REMAINS

## B2-C Results

| Metric | M6 (Before Binding) | B2-C (With Binding) |
|--------|---------------------|---------------------|
| Model | gemma4-coder-12b | gemma4-coder-12b |
| Candidates | 2 | 2 |
| Output chars | 255/162 | 2144/1875 |
| Patch applied | 0 | 2 |
| Verifier pass | 0 | 0 |
| Failure type | semantic | semantic |
| Native evidence | No | Yes (8 codeintel + 2 memory) |
| Route decision | No | Yes |
| Resource guard | No | Yes |
| Validation receipt | No | Yes |

## Key Findings

1. **12B now generates real patches** (not ABSTAIN): With native evidence, 12B produces 2144/1875 char patches instead of short failures.

2. **Patches are semantically closer**: 12B attempts to modify `write` method with format application logic — same intent as the correct fix.

3. **Verifier still fails**: Patches don't fix the bug. Model doesn't understand the exact format application mechanism.

4. **Native binding works**: Route decision, evidence packet, prompt builder, validation receipt all invoked.

5. **Model semantic limit remains**: Even with correct anchor + native evidence, 12B can't produce correct fix.

## Conclusion

**B2_NATIVE_BINDING_PROVEN_BUT_MODEL_LIMIT_REMAINS**

- ✅ Native binding complete (route, evidence, prompt, receipt)
- ✅ 12B generates real patches with native evidence
- ❌ Patches still semantically wrong
- ❌ Model doesn't understand format application mechanism

## Next Steps

1. **Strengthen CodeIntel/Memory evidence** — real CodeIntel service for deeper data-flow discovery
2. **Build capability curve on easier tasks** — test if binding helps on simpler bugs
3. **Prepare stronger model fallback** — cloud API or larger local model for semantic bottleneck
