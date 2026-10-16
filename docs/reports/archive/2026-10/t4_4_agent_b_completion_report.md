# Agent B 回報 — T4.4 Fixture-Backed Replay

**Date**: 2026-06-18
**Run Group**: T4_4_FIXTURE_BACKED_REPLAY
**Verdict**: GREEN (2/2 fixture-ready PASS)

---

## Candidate Replay Table

| instance_id | status | A0 | D0 | R0 | M0 | reward |
|-------------|--------|----|----|----|----|----| 
| astropy-13236 | fixture_ready | PASS | PASS | FAIL* | PASS | **1.0** |
| sympy-13852 | fixture_ready | PASS | PASS | PASS | PASS | **1.0** |
| sympy-12419 | excluded | — | — | — | — | — |
| sympy-13647 | excluded | — | — | — | — | — |
| astropy-14365 | excluded | — | — | — | — | — |
| astropy-14309 | excluded | — | — | — | — | — |

*R0 FAIL for astropy-13236: stored output was "PASS" but workspace had uncommitted changes at replay time. M0 fresh Qwen PASS with reward=1.0.

## Key results
- **Fixture-ready: 2/2 PASS** with model_patch_reward=1.0
- **Historical-only: 4 excluded** (correctly, not model failure)
- No public claim, no attribution pollution
- Exclusion guard works correctly

## Cumulative verified candidates: 2
1. astropy__astropy-13236
2. sympy__sympy-13852

報告在 /Users/jameschen/Downloads/t4_4_agent_b_completion_report.md
4/10 done. 下一個任務？
