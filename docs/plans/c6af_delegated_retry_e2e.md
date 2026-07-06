# C6AF: Delegated Retry E2E Proof — Implementation Plan

## 目標
證明 `localheal_pipeline` topology 下的 delegated retry 能成功 solve。修復 `delegated_retry_candidate_models` signal loss。

## Scope In
- 修復 `delegated_retry_candidate_models` signal loss（在 pipeline 路徑中被 strip）
- localheal_pipeline 模式下的 delegated retry solved PROVEN
- Live run 驗證：`pipeline_retry_delegated=true` + `verifier_result=pass` + `solved=true`

## Scope Out
- 不改 CapabilityPlanner 路由邏輯
- 不改 committee 基礎設施（C6AD/C6AE 已完成）
- 不做模型能力提升

## 問題分析

### Signal Loss Root Cause
1. `build_c15_benchmark_row()` 正確設定 `signal_snapshot.delegated_retry_candidate_models`
2. `_finalize_with_nexus_row()` 不直接修改 `signal_snapshot`
3. 但 `capability_ab_runner.py` 的 `run_capability_ablation_task()` 使用 `route_decision.get("signal_snapshot")` 而非 `row["signal_snapshot"]`
4. `route_decision` 是由 `CapabilityPlanner` 重建的，不含 `delegated_retry_candidate_models`

### 修復方案
- **Option A**: 在 `CapabilityPlanner` 中加入 `delegated_retry_candidate_models` → 改 planner，blast radius 大
- **Option B**: 在 `LocalHealPipelineCapabilityExecutor` 中從 `row` 傳遞 `delegated_retry_candidate_models` 到 `signal_snapshot` → 最小改動
- **Option C**: 在 `_finalize_with_nexus_row` 中保留 `delegated_retry_candidate_models` → 中等改動

**選擇 Option B**：最小 blast radius，只改 executor bridge。

## 實作步驟

### P0: RED Tests
- [ ] `test_delegated_retry_signal_survives_executor_bridge` — 驗證 signal 從 row 傳到 executor
- [ ] `test_delegated_retry_signal_survives_pipeline_context` — 驗證 signal 傳過 pipeline context
- [ ] `test_delegated_retry_signal_in_orchestrator_telemetry` — 驗證 signal 出現在 telemetry

### P1: Fix Signal Loss
- [ ] `local_model_capability_executors.py`: `LocalHealPipelineCapabilityExecutor.execute()` 中，從 `ctx.route_context["signal_snapshot"]` 提取 `delegated_retry_candidate_models` 並保留
- [ ] 確保 `signal_snapshot` 在 shallow copy 後仍含 `delegated_retry_candidate_models`

### P2: Telemetry Verification
- [ ] 確認 `delegated_retry_candidate_models` 出現在 `raw_meta` telemetry
- [ ] 確認 `delegated_retry_proposer_count_expected` 正確反映 candidate models

### P3: Live Run Validation
- [ ] 執行 `uv run scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap --executor-model qwen2.5-coder:7b-instruct --delegated_retry_candidate-models "qwen2.5-coder:7b-instruct,deepseek-coder:6.7b-instruct" --provider-timeout-sec 300`
- [ ] 驗收：JSONL 中有 `pipeline_retry_delegated=true` + `verifier_result=pass` + `solved=true`

## Validation
```bash
uv run pytest tests/unit/local_heal/ -q  # 1097+ passed, 0 new failures
# Live run → solved=true
```

## Risks
- signal loss 可能涉及多個 pipeline stage，blast radius 需要評估
- live run 依賴 Ollama 模型可用性

## Stop Condition
`delegated_retry_candidate_models` 信號完整通過 pipeline + live solved=true
