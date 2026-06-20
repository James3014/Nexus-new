# T2.9 20-Task Evidence Pack

**Baseline**: T2_9_20_TASK_RECOVERY_BASELINE
**Source Run**: T2_8_ATTRIBUTION_SAFE_20_TASK_DIAGNOSTIC
**Replay Run**: T2_9_20_TASK_BASELINE_REPLAY
**Date**: 2026-06-18

---

## 1. Baseline Manifest

- **Path**: `configs/baselines/t2_9_20_task_recovery_baseline.yaml`
- **baseline_id**: T2_9_20_TASK_RECOVERY_BASELINE
- **source_run**: T2_8_ATTRIBUTION_SAFE_20_TASK_DIAGNOSTIC
- **baseline_type**: internal_recovery_baseline
- **raw_task_count**: 20
- **deduped_task_count**: 20
- **anchor_task_count**: 15 (t2_7_anchor)
- **new_task_count**: 5 (t2_8_new)
- **expansion_stage**: T2_to_T3_gate

## 2. Task Inventory

### Anchor tasks (15)

| # | instance_id | project | recovery_rule_id | canonical_span_source |
|---|-------------|---------|-------------------|----------------------|
| 1 | astropy__astropy-12907 | astropy | AST_SYMBOL_FIX | ast_boundary |
| 2 | astropy__astropy-13236 | astropy | REMOVE_BLOCK | unified_diff |
| 3 | astropy__astropy-13579 | astropy | locked_search_reuse | locked_search |
| 4 | astropy__astropy-14182 | astropy | locked_search_reuse | locked_search |
| 5 | sympy__sympy-12481 | sympy | locked_search_reuse | locked_search |
| 6 | astropy__astropy-13033 | astropy | repro_script_fix | locked_search |
| 7 | astropy__astropy-13453 | astropy | astropy_html_dependency_fix | locked_search |
| 8 | astropy__astropy-13398 | astropy | repro_env_noise | locked_search |
| 9 | sympy__sympy-13852 | sympy | repro_env_noise | locked_search |
| 10 | sympy__sympy-13877 | sympy | repro_env_noise | locked_search |
| 11 | astropy__astropy-13977 | astropy | repro_env_noise | locked_search |
| 12 | sympy__sympy-13031 | sympy | repro_script_fix | locked_search |
| 13 | astropy__astropy-14096 | astropy | repro_env_noise | locked_search |
| 14 | sympy__sympy-13480 | sympy | repro_env_noise | locked_search |
| 15 | django__django-11099 | django | django_workspace_validation | locked_search |

### New tasks (5)

| # | instance_id | project | recovery_rule_id | canonical_span_source | source_failure_class |
|---|-------------|---------|-------------------|----------------------|---------------------|
| 16 | astropy__astropy-14365 | astropy | t2_8_regression_anchor_reuse | locked_search | SOLVED |
| 17 | sympy__sympy-12419 | sympy | canonical_locked_search_replay | locked_search | patch_mismatch |
| 18 | sympy__sympy-13647 | sympy | canonical_locked_search_replay | locked_search | patch_mismatch |
| 19 | astropy__astropy-14309 | astropy | repro_env_noise | locked_search | env_noise |
| 20 | sympy__sympy-11618 | sympy | t2_8_regression_anchor_reuse | locked_search | SOLVED |

## 3. Clean Replay Result

| Metric | Result |
|--------|--------|
| **Verdict** | GREEN |
| **Solved** | 20/20 |
| **Receipt coverage** | 20/20 |
| **match_gate_passed** | 20/20 |
| **syntax_gate_passed** | 20/20 |
| **verification_passed** | 20/20 |

## 4. canonical_span_source Distribution

| Source | Count |
|--------|-------|
| locked_search | 18 |
| ast_boundary | 1 |
| unified_diff | 1 |

## 5. Recovery Rule Distribution

| Rule | Count |
|------|-------|
| locked_search_reuse | 5 |
| repro_env_noise | 6 |
| repro_script_fix | 2 |
| AST_SYMBOL_FIX | 1 |
| REMOVE_BLOCK | 1 |
| astropy_html_dependency_fix | 1 |
| django_workspace_validation | 1 |
| t2_8_regression_anchor_reuse | 2 |
| canonical_locked_search_replay | 2 |

## 6. Attribution Distribution

| Metric | Value |
|--------|-------|
| model_calls=0 solved | 20 |
| model_patch_reward > 0 | 0 |
| export_as_model_patch_success | 0 |
| export_as_canonical_recovery_success | 2 |
| deterministic_fallback_reward | 2 (AST_SYMBOL_FIX, REMOVE_BLOCK) |

## 7. Workspace / Dependency Coverage

| Project | Workspace OK | Import OK | .venv Committed | Bootstrap Audit |
|---------|-------------|-----------|-----------------|-----------------|
| astropy | Yes | Yes | No | PASS |
| sympy | Yes | Yes (via sys.path) | No | PASS |
| django | Yes | Yes (via sys.path) | No | PASS |

## 8. Clean Workspace / Base Hash Evidence

All 20 tasks ran with:
- `worktree_clean_before_run`: verified per task
- `base_repo_hash`: recorded per task in receipts
- Workspace reset (`git checkout -- . && git clean -fd`) before each task

## 9. Guard Summary

| Guard | Status |
|-------|--------|
| G01: model_calls=0 | PASS |
| G02: deterministic fallback | PASS |
| G03: ast_boundary + model_calls=0 | PASS |
| G04: locked_search replay | PASS |
| G05: repro/harness failure | PASS |
| G06: dependency/workspace failure | PASS |
| G07: internal baseline | PASS |
| G08: model patch candidate | PASS |

## 10. Registry Freeze

- **Path**: `docs/reports/recovery_rule_registry_v1_1_freeze.md`
- **Rules**: 16 rules covering all T2.8 task recovery paths
- **Gaps**: 0 unhandled gaps

## 11. Export/Claim Guard Freeze

- **Path**: `docs/reports/s2t_export_claim_guard_t2_9_freeze.md`
- **Guards**: 8 guard rules, all pass
- **Public claim leakage**: impossible from internal baseline

---

## Non-Claims

This is NOT:
- A public benchmark
- A Qwen solve rate
- Model patch synthesis success
- Evidence of model_patch_reward > 0
- Comparable to official SWE-bench metrics

This IS:
- An internal deterministic/canonical/recovery baseline
- A clean replay of the T2.8 20-task set from frozen workspace state
- Evidence of Nexus recovery pipeline reliability at 20-task scale

---

## Known Limitations

1. **18/20 tasks use locked_search** — these are deterministic replays of previously verified fixes, not novel patch synthesis
2. **2 tasks use deterministic fallback** (AST_SYMBOL_FIX, REMOVE_BLOCK) — these are line/block replacements, not model-generated patches
3. **model_calls=0 for all 20 tasks** — no model inference was involved in any solve
4. **No .venv hermetic isolation** — sympy and django use sys.path.insert rather than pip install
5. **Deprecation warnings** — sympy 1.0.1.dev produces collections.Mapping warnings on Python 3.9

## T3 Gate Decision

**T2.9 GREEN → T3 is ALLOWED to start**

Recommended T3.0 option: **Option B — Model-Call Reintroduction Experiment**

Rationale:
- Clean replay evidence is strong (20/20, all guards pass)
- Bootstrap is reproducible across all 3 projects
- Current bottleneck is that model_calls=0 means no model patch synthesis
- T3.0 should introduce controlled model_calls>0 on a subset to distinguish model patch reward from deterministic recovery

T3.0 execution is NOT performed in this task. It requires explicit user request.
