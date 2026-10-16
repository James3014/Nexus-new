# P8: Next Paper-Backed Capability Sprint

**Status**: P8_COMPLETE  
**Date**: 2026-06-20  
**Based on**: P7 delta + P5 root cause analysis

---

## Decision: P8 Direction

**Primary**: Fix control-plane engineering gaps before adding model complexity.  
**Rationale**: P7 shows 2/3 remaining failures are fixable with better control plane (anchor correctness + parser guard). Only after fixing these can we measure true semantic gap.

---

## Sprint P8-A: Control Plane Hardening (Priority 1)

### P8-A1: Base-Commit-First Anchor Protocol
- **Change**: `run_anchored_repairs.py` must `git checkout base_commit` **before** reading source for anchor extraction.
- **Evidence**: C_11618 had `ANCHOR_NOT_IN_SOURCE` because script used HEAD version.
- **Implementation**: Move `run_git(checkout base_commit)` before `anchor = t["anchor_text"]` resolution.
- **Expected outcome**: C_11618 now gets model call with correct anchor.

### P8-A2: Parser Prose-Guard
- **Change**: In `anchored_edit` fallback, strip all prose lines before accepting as replacement. Detect: lines not starting with spaces/keywords/operators after stripping markdown.
- **Evidence**: C_12481 cand_1 had SyntaxError because model prepended prose explanation.
- **Implementation**: Add heuristic in `SolidSearchReplaceProtocol.parse()` anchored_edit path: remove leading non-code text blocks.
- **Expected outcome**: C_12481 cand_1 skipped as invalid; cand_2/3 evaluated.

### P8-A3: Targeted Sub-Method Anchor Selection
- **Change**: For complex bug classes (format pipeline, cycle composition), anchor should be at the **leaf method** level, not the caller's iteration block.
- **Evidence**: C_13453 anchor covered `col.info.iter_str_vals()` call site, but fix was needed at `_set_col_formats()` call level.
- **Implementation**: Control-plane anchor selection logic should:
  1. Identify the bugged method from problem_statement.
  2. Anchor to that method's body directly (not caller).

---

## Sprint P8-B: Candidate Diversity (Priority 2)

### P8-B1: N=5 with Temperature Variation
- Increase candidates from 3 to 5 per task.
- Use temperature=[0.0, 0.1, 0.2] across candidates.
- Add system prompt variant that includes the `_set_col_formats` API reference as hint.

### P8-B2: num_predict Increase for Complex Tasks
- Detect tasks with >500-char anchor → use `num_predict=1024`.
- Complex bugs need more tokens to express multi-step fixes.

---

## Sprint P8-C: Validation (After A+B)

- Re-run all 3 tasks with P8-A+B fixes.
- Expected success rate: 1-2/3 (C_11618 most likely, C_12481 if prose-guard works).
- Track: SEARCH_MISMATCH=0 maintained, semantic success rate improved.

---

## Model Policy (Unchanged)

| Model | Role |
|---|---|
| qwen2.5-coder:7b | DEFAULT_EXECUTOR (standard protocol) |
| gemma4-coder-12b-q4km:latest | ANCHORED_EDIT_CANDIDATE (14B proxy) |
| 3B | Advisory only |

**Cloud/14B escalation**: NOT recommended until local 12B achieves ≥1/3 after P8-A fixes.

---

## Governance Constraints (Unchanged)

- `public_claim_allowed=false`
- `training_eligible=false`
- `cloud_api_allowed=false`
- All repair evidence is internal audit only.

---

## P1–P8 Track Summary

| Phase | Outcome |
|---|---|
| P1 Literature Mapping | ✅ Design principles mapped |
| P2 Anchored Edit Interface | ✅ `AnchoredEdit` + protocol.anchored_edit mode |
| P3 Candidate Search | ✅ `CandidatePatchSearcher` with dedup + verifier gate |
| P4 Verifier Feedback | ✅ `BEHAVIOR_COLLAPSE` guard + retry limits |
| P5 Hard Task Re-run | ✅ SEARCH_MISMATCH=0, 0/3 repro (control-plane bugs found) |
| P6 Resource Guard | ✅ 12B policy doc, OS hang prevention |
| P7 Capability Delta | ✅ Bottleneck shifted: infrastructure → semantic |
| P8 Next Sprint Plan | ✅ 3 concrete fixes to control plane |

