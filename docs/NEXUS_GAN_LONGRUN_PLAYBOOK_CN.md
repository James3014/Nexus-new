# Nexus GAN 左右互搏長時 Coding 作戰手冊（草案 v1）

更新日期：2026-03-27  
適用範圍：Nexus 抗幻（Phantom Guard）/ 學習（Learning）/ 自癒（Self-Healing）整合管線

## 1. 目標與背景

本文件用來固定 Nexus 在長時間 Coding 的核心方法：  
將單一 Agent「自我規劃 + 自我實作 + 自我評分」的高風險流程，改為可對抗、可驗證、可回饋的三層閉環。

對應到 Anthropic 長時任務文章的核心精神：

1. 分工而非單腦暴衝（Planner / Generator / Evaluator）  
2. 長任務靠 harness，不靠硬撐 context  
3. 評估器要獨立且可執行，不能只靠模型自評

## 2. Nexus 與 GAN 對照

### 2.1 角色映射

- Planner：Nexus `RepairPlanner` + route bias（fault lessons + route weights）
- Generator：Nexus Repair / Self-Heal 執行器（task runner / safe execute）
- Discriminator（Evaluator）：Nexus Phantom Guard + delivery gate + proof contract + regression checks

### 2.2 對抗邏輯

- G 嘗試產生可通過的修復路徑與補丁
- D 只接受「可驗證的實體證據」，拒絕幻覺成功
- D 的結果回灌學習層，學習層再影響下一輪 G 的路由策略

## 3. 現況（已落地能力）

### 3.1 抗幻（D）

- `PASS/APPROVED + patch_generated + patch_apply_success` 必須附 `proof_type/proof_value`
- 無 proof 會被標記為 `missing_physical_proof` 並阻斷

### 3.2 學習

- Learning Evidence 已帶 proof 欄位
- 需要 proof 卻無 proof 時，`learning_frozen=true`，禁止 ingest

### 3.3 自癒（G）

- planner 使用 `fault_lesson_hits` + `self_heal_route_phase_weights` 進行路由偏置
- 每輪 cycle 依結果加減權重，並做衰減（避免僵化）
- route weights 已同步寫入 `.nexus/knowledge/policy_memory.jsonl`，可被 metabolizer 管理

### 3.4 可觀測

- 已提供 `nexus:health explain`
- 已包含 GAN 風格指標：D pass/block、G success、alignment score

## 4. 資料收集計畫（先收集，再調參）

### 4.1 收集週期

- 最小有效樣本：30~50 輪
- 建議觀察期：7~14 天

### 4.2 每輪固定執行

```bash
uv run scripts/engine/nexus_cli.py nexus:health explain --output json
```

說明：從現在開始，`nexus:health explain` 每次執行都會自動追加一筆同一份 time-series log（JSONL），不需要手動整理。

- 固定路徑：`./.nexus/metrics/health_explain_timeseries.jsonl`
- 寫入模式：append-only（每次一行 JSON，保留完整歷史）
- 主要欄位：`ts_utc`, `snapshot_score`, `snapshot_status`, `pipeline_health`, `phase_health`, `anti_hallucination`, `learning`, `self_healing`, `adversarial_metrics`, `notes`

快速查看最近 5 筆：

```bash
tail -n 5 .nexus/metrics/health_explain_timeseries.jsonl
```

### 4.3 必看指標

- `discriminator_block_rate`（越穩定越好，不追求盲目低）
- `discriminator_pass_rate`
- `generator_success_rate`
- `gan_alignment_score`
- `learning_frozen` / `learning_freeze_reasons`
- `self_heal_route_phase_weights`

### 4.4 目標區間（第一階段）

- `gan_alignment_score` 穩定 > 70
- `generator_success_rate` 穩定 > 65%
- `discriminator_pass_rate` 穩定 > 60%
- `learning_frozen` 比例 < 20%（且 freeze 原因可解釋）

### 4.5 交接注意（給下一位 Agent）

1. 任何調參前，先讀取最近 30 筆 time-series，再做結論。
2. 若 `notes` 出現 `timeseries_log_write_failed:*`，先修寫入路徑或權限，再談優化。
3. 以趨勢判斷，不用單輪極值判斷系統退化。

## 5. 後續路線圖

### Phase A：觀測穩定化（現在）

1. 固定收集 explain JSON
2. 每日檢查 freeze 原因與 phantom 攔截原因
3. 驗證 route weights 是否隨 outcomes 合理變動

### Phase B：離線校準（資料達標後）

1. 用歷史資料回歸校準 `gan_alignment_score` 權重
2. 驗證 D block 是否真的提升後續 G 成功率（避免過擋）
3. 產出第一版閾值（thresholds）建議

### Phase C：自動調參（第二版）

1. 若 `alignment < 60` 連續 3 輪，降低探索、提高 D gate 強度
2. 若 `alignment > 80` 連續 5 輪，放寬 route 探索，提升效率
3. 調參動作需落盤與可回滾（變更記錄 + TTL）

## 6. 風險與回滾

### 6.1 主要風險

- 過度攔截：D 太嚴導致吞吐下降
- 過度放行：學習資料污染，G 漸進退化
- 權重僵化：長期偏向單一路由，喪失探索

### 6.2 回滾策略

1. 關閉自動調參（保留觀測）
2. 回退 route weight prior 到 neutral（0）
3. 保留 proof contract，不回退抗幻底線

## 7. 操作口訣（給日常使用）

1. 先看 `nexus:health explain`  
2. 抗幻先過關，學習才有價值  
3. 學習不亂吃，自癒才會越修越準  
4. 沒資料不調參，有資料再調參

## 8. 參考

- Anthropic Engineering: [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
