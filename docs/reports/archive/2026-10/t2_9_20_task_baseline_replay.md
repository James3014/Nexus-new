# T2.9 20-Task Baseline Replay Report

**Run Group**: T2_9_20_TASK_BASELINE_REPLAY
**Date**: 2026-06-18
**Verdict**: GREEN (20/20 PASS)

## Replay Script

- **Path**: `scripts/bench/t2_9_replay_20_task_baseline.py`
- **Mode**: Clean replay from frozen T2.8 20-task baseline
- **Model calls**: 0 (deterministic replay only)

## Result Summary

| Metric | Value |
|--------|-------|
| Total tasks | 20 |
| Solved | 20/20 |
| Receipt coverage | 20/20 |
| match_gate_passed | 20/20 |
| syntax_gate_passed | 20/20 |
| verification_passed | 20/20 |
| export_as_model_patch_success | 0 |
| export_as_canonical_recovery_success | 2 |
| export_as_public_claim | 0 |
| Guard violations | 0 |

## Task Results

| Task | Role | Solved | Source | Rule |
|------|------|--------|--------|------|
| astropy__astropy-12907 | t2_7_anchor | Y | ast_boundary | AST_SYMBOL_FIX |
| astropy__astropy-13236 | t2_7_anchor | Y | unified_diff | REMOVE_BLOCK |
| astropy__astropy-13579 | t2_7_anchor | Y | locked_search | locked_search_reuse |
| astropy__astropy-14182 | t2_7_anchor | Y | locked_search | locked_search_reuse |
| sympy__sympy-12481 | t2_7_anchor | Y | locked_search | locked_search_reuse |
| astropy__astropy-13033 | t2_7_anchor | Y | locked_search | repro_script_fix |
| astropy__astropy-13453 | t2_7_anchor | Y | locked_search | astropy_html_dependency_fix |
| astropy__astropy-13398 | t2_7_anchor | Y | locked_search | repro_env_noise |
| sympy__sympy-13852 | t2_7_anchor | Y | locked_search | repro_env_noise |
| sympy__sympy-13877 | t2_7_anchor | Y | locked_search | repro_env_noise |
| astropy__astropy-13977 | t2_7_anchor | Y | locked_search | repro_env_noise |
| sympy__sympy-13031 | t2_7_anchor | Y | locked_search | repro_script_fix |
| astropy__astropy-14096 | t2_7_anchor | Y | locked_search | repro_env_noise |
| sympy__sympy-13480 | t2_7_anchor | Y | locked_search | repro_env_noise |
| django__django-11099 | t2_7_anchor | Y | locked_search | django_workspace_validation |
| astropy__astropy-14365 | t2_8_new | Y | locked_search | t2_8_regression_anchor_reuse |
| sympy__sympy-12419 | t2_8_new | Y | locked_search | canonical_locked_search_replay |
| sympy__sympy-13647 | t2_8_new | Y | locked_search | canonical_locked_search_replay |
| astropy__astropy-14309 | t2_8_new | Y | locked_search | repro_env_noise |
| sympy__sympy-11618 | t2_8_new | Y | locked_search | t2_8_regression_anchor_reuse |

## Non-Claims

This is NOT a public benchmark, NOT Qwen solve rate, NOT model patch synthesis success. This is an internal deterministic/canonical/recovery baseline clean replay.
