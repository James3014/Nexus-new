# Pipeline 健康度 80%+ 衝刺計畫 (Night Shift自治版)

## 目標
- 以 `NightShift -> Nexus Battlesuit -> Gemini CLI OAuth` 自治方式修補 `nexus/engine/pipeline.py`。
- 目標健康度: `>= 80%`。
- 流程約束: 本輪由自治修補產生變更，人類/主代理只做驗收與決策，不手動改核心實作。

## 執行邊界
- 主要目標檔: `nexus/engine/pipeline.py`
- 證據輸出:
  - worktree 路徑
  - best commit SHA
  - target diff
  - 驗證命令結果
- 驗收前不自動 harvest 回主工作區。

## TODO 列表（超細）

### A. Baseline 與預檢
- [ ] A1. 確認 `task_manifest.yaml` 含 `auto.repair.repair_pipeline` 任務標記。
- [ ] A2. 確認 `pipeline.py` 內核方法現況:
  - [ ] `_init_pipeline_state`
  - [ ] `_finalize_and_report`
  - [ ] `_run_pipeline_inner`
- [ ] A3. 確認 `_LegacyPhaseAdapter` 仍為兼容路徑（非立即移除）。

### B. Night Shift 自治修補回合
- [ ] B1. 執行第一輪自治修補:
  - `uv run python scripts/nightshift.py --tasks nexus/engine/pipeline.py --max_rounds 1 --budget_min 2 --convergence-patience 1`
- [ ] B2. 擷取回合輸出:
  - [ ] worktree path
  - [ ] best score
  - [ ] target file
  - [ ] best commit
- [ ] B3. 匯出並記錄目標 diff（僅 `pipeline.py`）。

### C. 驗證矩陣（你指定）
- [ ] C1. 執行 `uv run scripts/engine/nexus_cli.py nexus acceptance-check`
- [ ] C2. 執行 `uv run scripts/engine/nexus_cli.py nexus contract-check`（若需參數，記錄阻塞原因）
- [ ] C3. 比對是否達成健康度門檻（若工具輸出可解析）

### D. 失敗循環（你指定）
- [ ] D1. 若 C 任一步驟失敗，建立 Failure Summary（原因/證據/阻塞類型）。
- [ ] D2. 啟動下一輪 Night Shift（仍只由自治修補改碼，不手改核心）。
- [ ] D3. 重跑 C 驗證。
- [ ] D4. 直到驗收通過或遇到外部不可解阻塞（例如 contract-check 缺必要參數）。

### E. 審批輸出（合併前）
- [ ] E1. 列出候選變更:
  - [ ] 檔案清單
  - [ ] commit SHA
  - [ ] 風險摘要
  - [ ] 驗證結果
- [ ] E2. 等待你同意後才進入 harvest / merge。

## 驗收準則
- `acceptance-check` 成功，且健康度指標不低於 `80%`（若輸出提供分數）。
- 目標檔有實體修改與可追溯 commit。
- 若 `contract-check` 因參數契約阻塞，需提供明確 blocker 證據與下一步命令。

## 回滾策略
- 每輪自治修補都在 worktree 內進行。
- 若驗收失敗，不污染主工作區，僅保留證據以便下一輪迭代。
