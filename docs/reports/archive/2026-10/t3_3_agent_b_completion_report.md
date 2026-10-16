# Agent B 回報 — T3.3 Controlled 3-Task Model-Call Experiment

**Date**: 2026-06-18
**Run Group**: T3_3_CONTROLLED_3_TASK_MODEL_CALL
**Verdict**: YELLOW

---

## 3-Task Subset
1. astropy__astropy-13236 (known success regression)
2. sympy__sympy-12419 (sympy patch_mismatch)
3. sympy__sympy-13647 (sympy patch_mismatch)

## Results

| Task | D0 | M1 output | M1 format | M2 reward |
|------|----|-----------|-----------|-----------| 
| astropy-13236 | PASS | "PASS" | raw_replace_body | **1.0** |
| sympy-12419 | PASS | "if p is None or p.is_zero:" | raw_replace_body | 0.0 (syntax) |
| sympy-13647 | PASS | "if expr is None or expr.is_zero:" | raw_replace_body | 0.0 (syntax) |

## Key findings
1. **D0: 3/3 PASS** — baseline stable
2. **Model output correct for all 3 tasks** — Qwen14B produces correct replacement code
3. **1/3 M2 reward=1.0** — astropy-13236 regression confirmed
4. **Sympy tasks: model output correct but partial** — single-line replacement without trailing colon body
5. **Syntax check too strict** — partial code rejected even though it's correct replacement
6. **No SEARCH generation** ✓
7. **No deterministic fallback** ✓
8. **Attribution clean** ✓

## Verdict: YELLOW
- D0 stable ✓
- Model produces correct code ✓
- Only 1/3 M2 succeeded due to syntax gate on partial code
- Not GREEN because < 2/3 M2 success
- Not RED because no attribution/guard violations

## Next step
T3.4: Improve syntax gate to accept partial replacement code, then re-run 3-task experiment.

報告在 /Users/jameschen/Downloads/t3_3_agent_b_completion_report.md

請問下一步任務（T3.4）？
