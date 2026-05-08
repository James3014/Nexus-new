# 2026-03-19 Phantom Success Incident RCA & Prevention

## Summary
- Incident: `ci_gate` 曾出現「流程回報成功但未實體寫入」與後續全 FAIL 波動。
- Scope: `reviewer -> patcher -> pipeline -> ci_gate`。
- Current: 已止血並通過全量 gate（100% success / phantom=0）。

## Root Causes
1. PASS 合約鬆散：`PASS` 可在無 patch/no-change 證據下成立。
2. 寫回鏈路缺陷：`SafePatcher` 的 `git apply` 未固定 `cwd`，造成套用失敗。
3. 成功判定偏語意：審核狀態可通過，但缺少「實體改動」硬證據閘。

## Fix Timeline (Commits)
- `fc85508`: block phantom success in review pipeline and ci gate
- `60b94ff`: add bypass no-change evidence for phantom-success guard
- `52d9cc0`: run git apply in project_root to restore write path

## Guardrails (5 Rules, Effective Immediately)
1. Smoke before full:
   - `uv run python scripts/ops/write_path_smoke.py`
2. Success contract:
   - PASS 必須 `patch_generated=true && patch_apply_success=true`
   - 或 `patch_generated=false && no_change_reason != ""`
3. No silent failure:
   - `git apply` 失敗不可吞錯，必須回傳失敗。
4. Gate ladder:
   - L0: `scope_guard + write_path_smoke + focused tests`
   - L1: mini benchmark (`ci_benchmark_mini.csv`)
   - L2: full `ci_gate`
5. Scope lock:
   - 非目標路徑變更由 `scripts/ops/scope_guard.py` 攔截。

## New Operational Entry
- One-shot ladder:
  - `scripts/ops/gate_ladder.sh`
- Includes:
  - `scripts/ops/scope_guard.py`
  - `scripts/ops/write_path_smoke.py`

## Evidence
- `.nexus/ci_gate_report.json`
- `ci_benchmark.csv`
- `tests/test_ci_gate_phantom_guard.py`
- `tests/test_phantom_success_guards.py`
