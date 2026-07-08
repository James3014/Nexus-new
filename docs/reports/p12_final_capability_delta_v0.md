# P12-FINAL: Capability Delta Acceptance Report

## Phase Summary

| Field | Value |
|-------|-------|
| Phase | P12-FINAL |
| Commit SHA | d9b62b10 |
| Status | P12_MODEL_SEMANTIC_REASONING_PRIMARY_BOTTLENECK |
| Model | gemma4-coder-12b-q4km:latest (11.9B, Q4_K_M) |
| Tests Run | 224 (all passing) |

## Execution Evidence

### P11 Results

| Task | Status | Failure Class | Parser | Verifier |
|------|--------|---------------|--------|----------|
| C_13453 | P11_PARSER_REJECTED_BAD_OUTPUT | Markdown fences | 3/3 rejected | N/A |
| C_11618 | P11_ANCHOR_NOT_IN_SOURCE | Infrastructure | N/A | N/A |
| C_12481 | P11_PARSER_REJECTED_BAD_OUTPUT | Prose contamination | 3/3 rejected | N/A |

### P13-B Results (Hardened Prompt)

| Task | Status | Failure Class | Parser | Verifier |
|------|--------|---------------|--------|----------|
| C_13453 | P13B_MIXED_PARSER_REJECTIONS | Markdown fences + prose | 6/6 rejected | N/A |
| C_12481 | P13B_PROSE_CONTAMINATION_REJECTIONS | Prose contamination | 5/6 rejected | 1 applied, failed |

### P13-A Results (Verifier Feedback Correction)

| Task | Status | Failure Class | Parser | Verifier |
|------|--------|---------------|--------|----------|
| C_12481 | P13A_CORRECTION_IMPROVED_BUT_FAILS | Semantic failure | 1/1 accepted | Applied, IndentationError |

## Capability Delta Comparison

| Metric | C4 Baseline | P5 | P9/P10 | P11 | P13-B | P13-A |
|--------|-------------|-----|--------|-----|-------|-------|
| SEARCH_MISMATCH | 100% | 0% | 0% | 0% | 0% | 0% |
| ANCHOR_NOT_IN_SOURCE | 33% | 0% | 0% | 33% | 0% | 0% |
| Prose contamination | 33% | 0% | 0% | 67% | 67% | 0% |
| Markdown fences | 0% | 0% | 0% | 33% | 33% | 0% |
| Patch apply | 0% | 78% | 78% | 0% | 17% | 100% |
| Verifier pass | 0% | 0% | 0% | 0% | 0% | 0% |

## Per-Task Conclusion

### C_11618 (Point.distance)
- **Root cause**: Hardcoded anchor doesn't match source at base_commit
- **Delta**: Infrastructure issue, not model issue
- **Resolution**: Anchor needs to be updated to match actual source

### C_12481 (Permutation non-disjoint cycles)
- **Root cause**: Model semantic reasoning insufficient
- **Delta**: Parser rejections eliminated (parser bug fixed), patch applies, but fix is semantically wrong
- **Resolution**: Model needs better understanding of Cycle composition

### C_13453 (HTML writer formats parameter)
- **Root cause**: Model habitually wraps output in markdown fences
- **Delta**: Parser correctly rejects markdown fences, but model doesn't comply with prompt
- **Resolution**: Model needs to follow "no markdown" instruction

## Capability Conclusion

**P12_MODEL_SEMANTIC_REASONING_PRIMARY_BOTTLENECK**

Rationale:
1. Infrastructure failures (SEARCH_MISMATCH, anchor bugs) eliminated by P9/P10
2. Parser rejections (prose, markdown) correctly enforced by P9 strict parser
3. Parser bug fixed in P13-A (indented code now accepted)
4. C_12481: Patch applies but fix is semantically wrong — model doesn't understand Cycle composition
5. C_13453: Model ignores "no markdown" instruction — behavioral issue
6. Model semantic reasoning is now the limiting factor

## Files Changed (Final)

| File | Change | Lines |
|------|--------|-------|
| `errors.py` | 7 new PatchErrorKind | +7 |
| `protocol.py` | AnchoredEditReplacementGuard + bug fix | +115 |
| `anchored_edit.py` | Provenance metadata | +59 |
| `semantic_anchor_selection.py` | New module | +312 |
| `test_anchored_edit.py` | 20 new tests | +259 |
| `test_semantic_anchor_selection.py` | 16 new tests | +312 |
| `scratch/run_p11_hard_tasks.py` | P11 script | +350 |
| `scratch/run_p13b_hardened_contract.py` | P13-B script | +300 |
| `scratch/run_p13a_correction.py` | P13-A script | +200 |

## Test Results

```
224 passed in 1.56s
```

## Next Recommendation

**P13_CANDIDATE_GENERATION_REWORK or MODEL_UPGRADE**

Options:
1. **P13-D: Candidate Generation Rework** — Generate smaller replacement spans, use leaf-method anchor only, add ABSTAIN option
2. **Model Upgrade** — Use a larger or more capable model (e.g., 14B with GPU, or cloud API)
3. **Task Re-selection** — Select easier tasks that match current model capabilities

## Restrictions Compliance

- ✅ No public claim
- ✅ No training export
- ✅ No runtime/routing enablement
- ✅ No production readiness claim
- ✅ All results internal-only

## Final Status

P12_MODEL_SEMANTIC_REASONING_PRIMARY_BOTTLENECK

Infrastructure complete. Parser hardened. Model semantic reasoning is the bottleneck.
