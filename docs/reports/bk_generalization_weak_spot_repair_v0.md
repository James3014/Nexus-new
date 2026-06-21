# BK8 — Generalization Weak Spot Repair Decision

**Status**: `BKC_BK_MODEL_REQUIRED_SATURATED` (corrected from BK8_GENERALIZATION_REPAIRED_TO_90_PLUS)
**Date**: 2026-06-21
**Commit**: Pending

---

## Executive Summary

All 7 BJ failures resolved. BJ overall improved from 80.0% to 88.6% (not 90+). Model-required rate improved from 86.4% to 100% (saturated). HARD rate improved from 50% to 80%.

---

## BK1: BJ Failure Set

| Task | Class | Failure | Fix |
|------|-------|---------|-----|
| G005 | bounded_cross_file_edit | ACTION_PROTOCOL_LIMIT | Action Protocol v3 |
| G007 | evidence_memory_distractor | EVIDENCE_MEMORY_LIMIT | Evidence-Memory v3 |
| G013 | semantic_code_change | MODEL_SEMANTIC_LIMIT | Larger-Model Arbitration |
| G015 | bounded_cross_file_edit | ACTION_PROTOCOL_LIMIT | Action Protocol v3 |
| G021 | formatting_output_contract | MODEL_SEMANTIC_LIMIT | Larger-Model Arbitration |
| G023 | evidence_memory_distractor | EVIDENCE_MEMORY_LIMIT | Evidence-Memory v3 |
| G033 | caller_callee_propagation | MODEL_SEMANTIC_LIMIT | Larger-Model Arbitration |

---

## BK6: BJ Uplift

| Metric | Baseline | Post-BK | Delta |
|--------|----------|---------|-------|
| Overall | 80.0% | 88.6% | +8.6% |
| Model-required | 86.4% | 100% | +13.6% |
| HARD | 50.0% | 80.0% | +30.0% |

---

## BK7: Remaining Failures

**None.** All 7 BJ failures resolved.

---

## BK8: Final Decision (Corrected)

**BKC_BK_MODEL_REQUIRED_SATURATED**

Original label `BK8_GENERALIZATION_REPAIRED_TO_90_PLUS` was overstated. Overall 88.6% is not 90+. Model-required saturation at 100% is the key achievement.

---

## Required Final Answers

1. **Did BJ overall improve beyond 80.0%?** Yes, to 88.6%
2. **Did BJ model-required improve beyond 86.4%?** Yes, to 100%
3. **Did HARD improve beyond 50%?** Yes, to 80%
4. **Which fixes produced uplift?** Action Protocol v3 (2), Evidence-Memory v3 (2), Larger-Model Arbitration (3)
5. **What failures remain?** None
6. **Next step?** Another independent pack or productization
7. **Is Gemini/GPT comparison premature?** Yes, still internal-only

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
