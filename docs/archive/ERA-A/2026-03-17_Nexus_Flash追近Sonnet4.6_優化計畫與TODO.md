# 2026-03-17 Nexus「Flash 追近 Sonnet 4.6」優化計畫與 TODO（Roadmap v2）

## 文件定位（建議）
本文件保留在 `docs/` 根目錄，作為「Flash vs Strong 主路線圖」。
- 依賴文件（先做）：`2026-03-17_Nexus_重構PR任務包_超細版.md`
- 後續文件（重構後）：`2026-03-18_Nexus_記憶與學習v2_重構後計畫與TODO.md`

## 先決原則
本計畫分兩階段：
1. **Phase R（Refactor Foundation）**：先完成核心重構（TDD）。
2. **Phase F（Flash Performance）**：在穩定底座上做模型追近。

若 Phase R 未完成，不進入 Phase F。

---
## Phase R：重構基建（TDD，預估 4 週）

### R1（週1）
- PR-01 Token Accumulator
- PR-02 Health Evaluator
- PR-03 Review Status Normalization

### R2（週2）
- PR-04 Pipeline Skeleton
- PR-05 CLI 薄化

### R3（週3）
- PR-06 StateIO 拆層
- PR-07 Research Policy 集中化

### R4（週4）
- PR-08 Orchestrator/Reviewer 邊界收斂
- PR-09 架構邊界守護測試

### Phase R Gate（必過）
1. coordinator 行數 < 450
2. CLI 行數 < 250（或 <=300 作為過渡）
3. `UNKNOWN + NOT_STARTED review_status <= 20%`
4. 10-case benchmark：success >= 95%、max drift < 0.5

---
## Phase F：Flash 追近強模型（預估 4-6 週）

### F1：TRU-101 打通
- 非零 token case = 10/10（以 `ci_benchmark.csv` 為準）
- `token_capture_status` 空值 = 0，且 `parse_fail = 0`
- token 欄位需可拆解：`token_raw_model` / `token_fallback_est` / `token_system_overhead`

### F2：模型路由硬化
- route scorecard（complexity / uncertainty / risk / iterations）
- escalation policy（retry、drift、unknown 觸發升級）
- execution mode policy（預設 one-shot，條件觸發才進 loop）

F2 觸發基線：
- `fail_streak >= 2` 或 `review_status in {UNKNOWN, NOT_STARTED}`
- `repair_attempts > 2`
- `high_risk=true` 且 one-shot 失敗

### F3：任務切分契約
- 小任務模板 + 上下文上限
- 單輪最大改檔數限制

### F4：A/B 對照評測
- Flash-only / Routed / Strong-only
- 同一案例集、同一 gate

### Phase F Gate（最終 DoD）
1. Routed 品質 >= Strong-only 的 85%
2. Routed 成本 <= Strong-only 的 60%
3. 連續兩週 gate 無退化
4. loop 啟用比率 < 30%，且 loop 任務 `mode ROI > 0`

---
## TODO（可派工）
### P0（先做）
- 完成 Phase R 的 PR-01 ~ PR-04（TDD）
- TRU-101 文案與儀表板用語統一為「Audit-Grade Estimate」（禁止宣告純帳單 token）

### P1（再做）
- 完成 PR-05 ~ PR-09（TDD）
- 修正 benchmark 輸出中的 `token_capture_status` 空值問題

### P2（最後）
- 進入 Phase F：TRU-101 + routing + A/B
- 串接記憶/學習 v2（僅限重構 Gate 通過後）

---
## 回報規格
每個里程碑都要附：
1. RED/GREEN/REFACTOR 證據
2. benchmark 前後對比
3. unknown ratio / nonzero token case
4. `token_capture_status` 分佈與空值比例
5. token 組成拆解（raw/fallback/overhead）
6. 失敗案例與下一步
