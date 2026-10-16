# Nexus Session Report — P9-P13, G1-G6, H2, M3-M6, X0

**Date**: 2026-06-20
**Branch**: feature/bridge-fastmatcher-20260606
**Commit SHA**: d9b62b10
**Model**: gemma4-coder-12b-q4km:latest (11.9B, Q4_K_M)

---

## Executive Summary

Completed P9-P13, G1-G6, H2, M3-M6, and X0 tracks. Infrastructure hardened, anchor selection corrected, multi-model cascade tested, existing capabilities audited. Core bottleneck remains: **local models lack semantic understanding of target codebases**.

---

## Track Summary

### P9: Anchor Provenance and Parser Hardening ✅
- 7 new PatchErrorKind values
- AnchoredEditReplacementGuard (prose, markdown, syntax rejection)
- Anchor provenance metadata (extraction_stage, source_hash)
- 20 tests pass

### P10: Semantic Anchor Selection ✅
- CandidateGenerator (target_symbol, caller, callee, formatting_behavior)
- SemanticAnchorScorer (5 dimensions)
- SemanticAnchorSelector (top-k, deterministic)
- 16 tests pass

### P11: Hard-Task Rerun ✅
- 0/3 success (parser rejections)
- C_13453: markdown fences ×3
- C_11618: anchor not in source
- C_12481: prose contamination ×2, markdown ×1

### P13-B: Output Contract Hardening ✅
- Hardened prompt with rejection examples
- Parser bug fix (indented code accepted)
- 0/2 success (semantic failures)

### P13-A: Verifier Feedback ✅
- C_12481: patch applied, verifier failed (IndentationError)
- Parser acceptance improved to 100%

### P12: Capability Delta ✅
- **P12_MODEL_SEMANTIC_REASONING_PRIMARY_BOTTLENECK**
- Infrastructure failures eliminated
- Semantic failures remain

### G1: Agentless Pipeline ✅
- Bounded candidate generation
- 5-stage filter (parser→patch→verifier→compliance→selection)
- 6 tests pass

### G2: Behavior Ownership Anchor Map ✅
- output_generation, validation_behavior, behavior_with_return
- Extended semantic_anchor_selection.py

### G3: Linear Replay Runner ✅
- One candidate = one isolated subprocess
- Fixed base_commit, source_hash, verifier

### G4: Structured Verifier Feedback ✅
- failure_type, assertion_summary, traceback_symbol
- Bounded correction prompt
- 4 tests pass

### G5: Backend Resource Policy ✅
- 3B/7B/12B/14B/cloud policies
- classify_result() separates local vs cloud
- 13 tests pass

### G6: C_12481/C_13453 Rerun ✅
- C_12481: 0% parser rejection, semantic fail
- C_13453: anchor selection chose 'read' over 'write' (wrong)

### H2: Anchor Scorer Rework ✅
- Generalized intent-to-behavior-owner mapping
- Directional scoring (output_formatting→write, input_parsing→read)
- Traceback override guard
- Behavior depth scorer
- Tie-breaking
- 19 tests pass

### H2-B: C_13453 Correct Anchor ✅
- Before: read (6.0) L10-L30 ❌
- After: write (9.0) L342-L456 ✅
- C_12481: cycle_structure (5.0) — acceptable refinement

### M3-M6: Multi-Model Cascade ✅
- 3B: output_formatting, confidence=0.95, recommended abstain
- 7B: 3/3 ABSTAIN (correct behavior)
- 12B: 2 candidates, 0 verifier pass
- Status: M6_MODEL_SEMANTIC_BOTTLENECK_REMAINS

### X0: Existing Capability Binding Audit ✅
- 14 capabilities audited
- All reusable directly
- 0 new modules needed
- CodeIntel/Research/Memory → context_discovery
- Hyper/Sprint → candidate_generation
- Sandbox/Replay → validation
- Autonomic Router → route_decision

---

## Test Results

```
291 tests pass (local_heal suite)
19 H2 tests pass
25 G-track tests pass
```

## Files Changed

| File | Lines | Description |
|------|-------|-------------|
| errors.py | +7 | New PatchErrorKind values |
| protocol.py | +115 | AnchoredEditReplacementGuard |
| anchored_edit.py | +59 | Provenance metadata |
| semantic_anchor_selection.py | +120 | H2 intent-aware scoring |
| candidate_generation.py | +210 | P14 narrow-span |
| agentless_pipeline.py | +210 | G1 pipeline |
| linear_replay_runner.py | +180 | G3 replay |
| structured_verifier_feedback.py | +180 | G4 feedback |
| backend_resource_policy.py | +200 | G5 policy |
| test_anchored_edit.py | +259 | 20 tests |
| test_semantic_anchor_selection.py | +136 | 16 tests |
| test_h2_anchor_scorer.py | +350 | 19 tests |
| test_g_track.py | +350 | 25 tests |
| test_candidate_generation.py | +312 | 23 tests |

## Conclusion

**MODEL_SEMANTIC_BOTTLENECK_REMAINS**

Infrastructure complete. Parser hardened. Anchor selection corrected. Multi-model cascade working. Existing capabilities audited and ready for binding.

Local models (3B/7B/12B) lack enough semantic understanding of target codebases to produce correct fixes. Next steps:
1. H3: Stronger model fallback (cloud API or larger local model)
2. Task re-selection for easier bugs
3. Context expansion via existing CodeIntel/Research/Memory
