# Agent B T2.7 回報

## Verdict: Green (module完成)

## 已完成

### 1. Baseline Manifest
- 路徑: configs/baselines/t2_7_15_task_recovery_baseline.yaml
- 15 tasks with full metadata
- baseline_role: anchor/closure/regression/new_diagnostic
- 所有 task 都有 expected_verification_result: PASS, expected_model_calls: 0

### 2. Workspace Bootstrap Scripts
- scripts/workspaces/bootstrap_astropy.sh
- scripts/workspaces/bootstrap_sympy.sh (Python 3.9 + mpmath)
- scripts/workspaces/bootstrap_django.sh

### 3. Recovery Registry Updated
- 16 rules total (added 4 new rules)
- 新增: repro_script_wrong_expected_behavior_fix, dependency_missing_fix, parser_dependency_missing_fix, astropy_html_dependency_fix, sympy_python39_workspace_fix, django_workspace_validation
- 所有規則都有完整 attribution 欄位

### 4. Export Guard v2
- verified with repro/dependency/workspace handling
- model_calls=0 → export_as_model_patch_success=false
- deterministic_fallback → export_as_model_patch_success=false
- repro/dependency/workspace failure → count_as_model_failure=false, count_as_patcher_failure=false

### 5. Evidence Pack
- docs/reports/t2_7_evidence_pack.md
- Non-claims section included
- 15-task baseline list
- Source run history (T2.1-T2.6)

## Tests
9/9 pass

## Patcher Logic
untouched

## StraTA S1
not connected

## 下一步
需要報告到 ChatGPT 並執行 T2.7 clean replay，然後根據結果決定 T2.8

## 注意
- ChatGPT send mechanism is BROKEN — messages not being sent
- Need to fix before continuing iterations
- User wants 20 iterations minimum
