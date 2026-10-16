# Agent B 回報 — T2.9 20-Task Baseline Freeze, Clean Replay, Evidence Pack, T3 Gate

**Date**: 2026-06-18
**Run Group**: T2_9_20_TASK_BASELINE_REPLAY
**Verdict**: GREEN

---

## 完成細節

### 任務 A：T2.9 20-task baseline manifest
- **路徑**: `configs/baselines/t2_9_20_task_recovery_baseline.yaml`
- 20 tasks 全部記錄：15 anchor (t2_7_anchor) + 5 new (t2_8_new)
- 每題包含：instance_id, project, baseline_role, expected_workspace, expected_dependency_profile, expected_verification_result, expected_model_calls, expected_model_patch_reward, expected_export_as_model_patch_success, expected_claim_eligible, expected_public_claim_allowed, expected_canonical_span_source, recovery_rule_id, source_failure_class, source_run
- **Duplicate check**: 0 duplicates (raw=20, deduped=20)

### 任務 B：workspace / dependency bootstrap audit
- **路徑**: `docs/reports/workspace_bootstrap_audit_t2_9.md`
- **astropy**: .venv_astropy/bin/python, import astropy/bs4/lxml OK, .venv not committed
- **sympy**: .venv39/bin/python, import sympy OK (via sys.path), import mpmath OK, .venv not committed
- **django**: /usr/local/bin/python3, import django OK (via sys.path), .venv not committed
- **結果**: PASS — 3/3 projects workspace bootstrap functional

### 任務 C：recovery registry v1.1 freeze
- **路徑**: `docs/reports/recovery_rule_registry_v1_1_freeze.md`
- 16 rules 冻結：AST_SYMBOL_FIX, REMOVE_BLOCK, locked_search_reuse, unified_diff_reuse, verification_guided_retry, repro_env_noise, repro_bug_not_reproduced, repro_script_fix, workspace_config_fix, dependency_missing_fix, parser_dependency_missing_fix, astropy_html_dependency_fix, sympy_python39_workspace_fix, django_workspace_validation, t2_8_regression_anchor_reuse, canonical_locked_search_replay
- 每 rule 含完整 invariants + export guard
- Registry gap audit: 0 unhandled gaps
- **Hard invariants verified**: model_calls=0→model_patch_reward=0.0, deterministic→export_as_model_patch_success=false, internal→public_claim_allowed=false

### 任務 D：export / claim guard freeze
- **路徑**: `docs/reports/s2t_export_claim_guard_t2_9_freeze.md`
- 8 guard rules 冻結並通過測試：G01-G08
- Public claim leakage: impossible from internal baseline
- model_patch_success candidate guard: requires model_calls>0 + llm_replace_success + verification PASS

### 任務 E：T2.9 clean replay
- **路徑**: `scripts/bench/t2_9_replay_20_task_baseline.py`
- **結果**: 20/20 PASS, GREEN
- Receipt coverage: 20/20
- match_gate: 20/20, syntax_gate: 20/20, verification: 20/20
- Guard violations: 0
- canonical_span_source: locked_search=18, ast_boundary=1, unified_diff=1
- model_patch_reward > 0: 0
- export_as_model_patch_success: 0
- export_as_public_claim: 0

### 任務 F：T2.9 evidence pack
- **路徑**: `docs/reports/t2_9_20_task_evidence_pack.md`
- 包含：baseline manifest, task inventory, replay results, source distribution, rule distribution, attribution, workspace coverage, guard summary, registry freeze, export guard freeze, non-claims, known limitations, T3 gate decision

### 任務 G：T3 gate decision
- **路徑**: `docs/reports/t3_0_options_plan.md`
- **T2.9 GREEN → T3 ALLOWED**
- **Recommended: Option B — Model-Call Reintroduction Experiment**
- Rationale: clean replay evidence strong, bootstrap reproducible, next step is controlled model_calls>0
- T3.0 not executed, requires explicit user request

---

## 產出清單

| 產出 | 路徑 |
|------|------|
| Baseline manifest | configs/baselines/t2_9_20_task_recovery_baseline.yaml |
| Replay script | scripts/bench/t2_9_replay_20_task_baseline.py |
| Replay report | docs/reports/t2_9_20_task_baseline_replay.md |
| Evidence pack | docs/reports/t2_9_20_task_evidence_pack.md |
| Recovery registry v1.1 | docs/reports/recovery_rule_registry_v1_1_freeze.md |
| Export/claim guard | docs/reports/s2t_export_claim_guard_t2_9_freeze.md |
| Workspace bootstrap audit | docs/reports/workspace_bootstrap_audit_t2_9.md |
| T3 options plan | docs/reports/t3_0_options_plan.md |
| 20 receipts | .nexus/reports/local_heal/*__T2_9_20_TASK_BASELINE_REPLAY/ |

## 驗收標準核對

| 標準 | 狀態 |
|------|------|
| 20-task baseline manifest complete | YES |
| workspace/dependency bootstrap audit complete | YES |
| recovery registry v1.1 frozen | YES |
| export/claim guard frozen and tested | YES |
| 20-task clean replay 20/20 PASS | YES |
| 20/20 receipts present | YES |
| no public claim violation | YES |
| no attribution pollution | YES |
| evidence pack complete | YES |
| T3.0 plan prepared but not executed | YES |
| patcher runtime untouched | YES |
| T2.9 Verdict: GREEN | YES |

## Non-claims

This is NOT a public benchmark. NOT Qwen solve rate. NOT model patch synthesis success. This is an internal deterministic/canonical/recovery baseline.

## 下一步

T3.0 Option B recommended: controlled model-call reintroduction experiment.
