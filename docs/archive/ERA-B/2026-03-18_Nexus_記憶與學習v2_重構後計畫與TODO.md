# 2026-03-19 Nexus 記憶與學習 v2.1 (v9 Alignment)

## 啟動前提（Gate） [PASSED]
本計畫**排在重構之後**，前置依賴如下：
1. `2026-03-17_Nexus_重構PR任務包_超細版.md` 內高優先 PR 已完成。 [DONE]
2. Benchmark 與 CI replay 可重跑且結果穩定。 [DONE]
3. Token 與 phase 事件欄位契約固定 (v1.5.2)。 [DONE]

未達上述條件時，不進入本計畫開發。

---

## 目標（第一性原理）
1. 記憶：在決策當下提供可提升成功率/成本效率的資訊。
2. 學習：讓下一次同類任務有可驗證改善，不是只寫文字 lesson。
3. 治理：記憶可追溯、可淘汰、可回放驗證。

## 範圍與非範圍
- 範圍：Episodic Memory、Policy Memory、檢索、效果評估、升降級機制。
- 非範圍：端到端全自動自我改碼（先不做 autonomous self-modifying code）。

## 分階段規劃（排程在重構後）

1. 記憶雙層模型
- `episodic_memory`：任務事件原始紀錄（task/phase/decision/result/cost）。
- `policy_memory`：可執行規則（條件/動作/信心分數/來源證據）。

2. Schema 與版本
- `schema_version`、`created_at`、`source_run_id`、`confidence`、`status`。
- `status` 僅允許：`candidate|validated|deprecated`。

3. 寫入 API（先最小）
- `record_episode(event)`
- `propose_policy(rule)`
- `promote_policy(rule_id)` / `deprecate_policy(rule_id)`

TODO（M1）：
- [ ] 定義 `episodic_memory` JSON schema。
- [ ] 定義 `policy_memory` JSON schema。
- [ ] 在 `state_io/context_hub` 補 memory repository 抽象層。
- [ ] 加 schema 契約測試（invalid payload 必須 fail）。

DoD（M1）：
- schema 有版本與遷移策略。
- 單元測試全綠。
- 可從一次 benchmark run 產生 episode 記錄。

### Phase M2（Week 2）檢索與決策注入
交付：
1. Policy 檢索器
- 依 task 特徵取 top-k（預設 k=3）。
- 回傳必含 `confidence` 與 `evidence_ref`。

2. 決策注入點
- 僅在 P/D 階段注入 policy 建議。
- R 階段只接受白名單類型策略（避免過度干預）。

3. 執行模式策略（one-shot vs loop）
- 新增欄位：`execution_mode`, `trigger_reason`。
- 先用硬規則決策 loop 觸發，再由學習機制調整閾值。

4. 觀測
- 新增欄位：`policy_hit_ids`、`policy_hit_count`、`policy_applied`。

TODO（M2）：
- [ ] 完成 policy ranking（先 rule-based，後續可向量檢索）。
- [ ] 在 coordinator 加 `apply_policy_pack()` 注入點。
- [ ] benchmark CSV 增加 policy 命中欄位。
- [ ] 增加「命中但未採用」原因欄位（可審計）。
- [ ] benchmark/state 增加 `execution_mode` 與 `trigger_reason` 欄位。

DoD（M2）：
- 同一 case 重跑可穩定命中同批高相關 policy。
- 觀測欄位完整落盤且無空值。

### Phase M3（Week 3）學習閉環與治理閘口
交付：
1. 效果評估器（Evaluator）
- 比較「有 policy」vs「無 policy」基線。
- 指標：成功率、平均耗時、平均 tokens、drift。

2. 模式評估器（Mode Evaluator）
- 比較 `one_shot` vs `loop` 的淨效益（mode ROI）。
- 指標：`mode_success_delta`, `mode_cost_delta`, `mode_latency_delta`。

3. 升降級機制（Updater）
- 改善達標 -> `validated`。
- 連續負遷移 -> `deprecated`。

4. CI Gate
- 若 `Negative Transfer Rate` 超門檻，阻擋升版。

TODO（M3）：
- [ ] 建 `policy_eval_report.json`。
- [ ] 實作 `memory ROI`、`policy hit precision`、`negative transfer rate`。
- [ ] 實作 `mode ROI`（one-shot vs loop）。
- [ ] nightly job 加離線 replay 子集。
- [ ] 將 Gate 接進 `scripts/ci_gate.py`。

DoD（M3）：
- 至少 10 個離線 case 可產生 policy 評估報告。
- 有明確 `promote/deprecate` 證據鏈。

## 優先順序（P0/P1/P2）
P0：
- schema + repository + 契約測試。
- benchmark policy 欄位落地。

P1：
- top-k 檢索 + P/D 注入。
- policy 命中可觀測。

P2：
- 升降級自動化 + CI Gate + nightly 趨勢。

## 風險與控管
1. 風險：記憶污染（錯誤 policy 累積）
- 控管：狀態機 `candidate -> validated -> deprecated`，禁止直接 production。

2. 風險：過度依賴歷史導致負遷移
- 控管：每次命中都要做效果評分，連續劣化自動降級。

3. 風險：資料欄位漂移導致回放失真
- 控管：schema_version + migration + replay contract tests。

## 驗收指令（重構完成後再執行）
```bash
uv run pytest tests/test_memory_schema_contract.py -v
uv run pytest tests/test_policy_retrieval.py -v
uv run scripts/nexus_cli.py nexus:benchmark --tasks 10 --output nexus_benchmark_memory_v2.csv
uv run scripts/ci_gate.py
```

## 最終驗收標準
1. Memory ROI > 0（相對無記憶基線有淨改善）。
2. Policy Hit Precision >= 70%。
3. Negative Transfer Rate <= 10%。
4. 全部結果可回放、可追溯、可審計。
