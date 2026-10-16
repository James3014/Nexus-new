# Agent B 回報 — T3.2 REPLACE-Only Format Contract Refinement

**Date**: 2026-06-18
**Run Group**: T3_2_REPLACE_ONLY_FORMAT_REFINEMENT
**Verdict**: GREEN

---

## 完成細節

### T3.1 failure recap
- T3.1: model output diff格式 → syntax gate FAIL
- T3.2 fix: 建立 REPLACE-only prompt contract (T3_REPLACE_ONLY_V1)

### D0: Deterministic baseline
- astropy__astropy-13236: PASS ✓

### M1a: Prompt contract attempt
- Prompt: T3_REPLACE_ONLY_V1 (strict REPLACE-only, no diff/markdown/SEARCH)
- Qwen14B output: **"PASS"** (correct block deletion response)
- Format class: raw_replace_body ✓
- Replace extracted: True ✓
- Syntax OK: True ✓
- Latency: 3.5s
- No M1b needed (M1a succeeded)

### M2: Guarded model candidate
- Applied model patch (block removal)
- Verification: PASS ✓
- **model_patch_reward=1.0** ✓
- llm_replace_success=True ✓
- No deterministic fallback ✓
- No truth patch ✓
- No manual patch ✓
- canonical_search_locked=True ✓

### Key achievements
1. **First clean model_patch_reward=1.0 candidate** in Nexus history
2. Qwen14B correctly follows REPLACE-only contract
3. Model understands block deletion = output "PASS"
4. No SEARCH generation by model ✓
5. Attribution clean ✓

### T3.2 Verdict: GREEN
- D0 baseline stable ✓
- Qwen14B callable ✓
- Output format contract works ✓
- M2 verification PASS with model_patch_reward=1.0 ✓

### Reports
- /Users/jameschen/Downloads/t3_2_agent_b_completion_report.md

請問下一步任務（T3.3）？
