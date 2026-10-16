# 2026-03-17 Nexus（Clean Code + Linus 原則）分析與漸進式重構清單

## 評估準則
- Clean Code：單一職責、短函式、命名清晰、可測試性、低耦合。
- Linus 原則（工程實務版）：避免特例分支、資料結構先行、不要大爆改、保持可回滾的小步重構。

---
## 一、架構診斷（先看核心問題）

## A. 過大協調器（High Coupling）
- `nexus/engine/coordinator.py` 目前約 671 行，`run_bug/run_feature/run_benchmark` 同時承擔：
  - 流程編排
  - 風險決策
  - token 累加
  - health 計算
  - trace/metrics 寫入
- 問題：關注點混雜，任何變更都會影響多條路徑。

## B. CLI 仍有業務邏輯與模擬行為混入
- `scripts/nexus_cli.py` 約 390 行。
- `run_test/run_check/run_upgrade` 含大量模擬與輸出邏輯，與「薄命令層」目標不一致。
- 問題：命令層與應用層責任邊界不清。

## C. 特例分支偏多（Linus 忌諱）
- 在 `run_feature/run_bug` 可見多種條件特判：
  - `external_needed`、task keyword 觸發 X-phase、fast_mode、dry_run、audit_level。
- 問題：規則散落在多處，容易出現「同義但不一致」行為。

## D. 狀態存取責任過重
- `nexus/core/state_io.py` 同時負責：
  - 狀態追加
  - metrics 寫入
  - contract 寫入
  - fallback 路徑策略
- 問題：IO 與指標/治理邏輯綁死，測試替身難做。

## E. Reviewer/Orchestrator 邏輯邊界模糊
- `nexus/services/reviewer.py` 與 `nexus/core/orchestrator.py` 存在交疊責任（loop/audit/token 收集/回退）。
- 問題：雙層控制流造成理解與除錯成本上升。

## F. benchmark 可觀測性進步但仍不足
- 已新增 `token_source_x/token_source_r/token_capture_status`，是正向。
- 但目前仍常見 `tokens=0`，且 `review_status=UNKNOWN` 比例偏高。
- 問題：資料有欄位，診斷鏈還沒全打通。

---
## 二、重構策略（遵守 Linus：小步、可回滾）

## 原則
1. 不做大爆改；每步都可單獨合併。
2. 先抽資料結構/策略，再移動流程。
3. 每個 PR 僅解一個問題，附對應測試。

---
## 三、漸進式重構清單（高 -> 低優先級）

## P0（最高）：流程與資料一致性

### P0-1 抽離 Token Accumulator（先解 TRU-101 根因）
- 目標：把 token 累加與 capture status 從 `run_bug/run_feature` 抽成單一模組。
- 建議新增：`nexus/engine/metrics/token_accumulator.py`
- TODO：
  - 統一 `record_phase_tokens(phase, tokens, status)`
  - 統一更新 `state.phase_tokens/state.total_token_usage/state.metadata.token_capture_status`
  - coordinator 只呼叫 API，不直接散寫欄位
- 驗收：
  - 既有測試通過
  - 10-case benchmark 中 token/capture 欄位一致性提高（無 parse_fail）

### P0-2 抽離 Health Evaluator
- 目標：`_evaluate_health` 移出 coordinator，避免流程與評分耦合。
- 建議新增：`nexus/engine/health/evaluator.py`
- TODO：
  - `evaluate(state, success)` 回傳純資料
  - coordinator 只負責調用與保存
- 驗收：health 計算有獨立單元測試。

### P0-3 明確化 Review Status Enum
- 目標：減少 `APPROVED/UNKNOWN/...` 字串散落。
- 建議新增：`nexus/core/review_status.py`
- TODO：
  - status 正規化集中在一處
  - benchmark 與 gate 共用同一映射
- 驗收：`UNKNOWN` 來源可追蹤，不再是黑箱字串。

---
## P1：關注點分離（SoC）

### P1-1 將 run_bug/run_feature 共用骨架抽出
- 目標：避免兩段近似流程重複演化。
- 建議：`execute_pipeline(task_kind, request)` 的模板方法。
- TODO：
  - 共同步驟：P -> X -> D -> R -> A -> C
  - 差異透過 strategy/context 注入
- 驗收：run_bug/run_feature 代碼行數各下降 >= 25%。

### P1-2 CLI 真正薄化
- 目標：`nexus_cli.py` 只做參數解析與 dispatch。
- TODO：
  - 把 `run_check/run_upgrade/run_test` 模擬邏輯移入 application service
  - CLI 僅做 `service.execute(command)`
- 驗收：CLI 中不再出現業務判斷與 mock sleep。

### P1-3 StateIO 拆層
- 目標：IO 與指標輸出解耦。
- TODO：
  - `StateRepository`（只管 state）
  - `MetricsWriter`（只管 .nexus_metrics）
  - `ContractWriter`（只管 plan/diagnosis）
- 驗收：StateIO 轉為 facade，單檔責任下降。

---
## P2：策略化與可測性

### P2-1 X-phase 觸發策略集中化
- 目標：移除 keyword 特判散落（`SDK/WebSocket/fix/bug`）。
- 建議新增：`research_policy.py`
- TODO：
  - 單一決策函數 `should_research(task, decision, mode)`
  - case 層可明確 `force_external`
- 驗收：X-phase 觸發行為可預測、可測試。

### P2-2 Orchestrator / Reviewer 邊界收斂
- 目標：只保留一個主循環控制點。
- TODO：
  - `CodexLoopV2` 專注「審核迴圈」
  - `NexusOrchestrator` 專注「框架接口」或退化為抽象基類
- 驗收：避免雙層 while/strike 分散。

### P2-3 建立架構守護測試
- 新增：
  - `tests/test_layer_boundaries.py`
  - 禁止 CLI import 深層業務模組
  - 禁止 coordinator 直接寫入 raw metrics file
- 驗收：違反邊界時 CI fail。

---
## P3：目錄與產品化整潔

### P3-1 scripts/ 歷史與核心分層
- 目標：把高噪音腳本與核心命令隔離。
- 建議目錄：
  - `scripts/core_runtime/`
  - `scripts/ops/`
  - `scripts/legacy_archive/`
- 驗收：新成員可在 5 分鐘內定位主命令。

### P3-2 契約文件自動生成
- 目標：避免文案與實作脫鉤。
- TODO：
  - 每次 CI 產生 `metrics schema`、`gate thresholds`、`route policy` 摘要
- 驗收：docs 與輸出檔可機器比對。

---
## 四、建議實施順序（最小風險）
1. 先做 P0-1/P0-2（不改外部接口）。
2. 再做 P1-1（抽模板），保持功能等價。
3. 接著 P1-2/P1-3（把層次切乾淨）。
4. 最後 P2/P3（策略化與整潔）。

---
## 五、每階段驗收 KPI
- 代碼層：
  - coordinator 行數下降（目標 < 450）
  - CLI 行數下降（目標 < 250）
- 資料層：
  - benchmark 非零 token case >= 3
  - UNKNOWN review ratio <= 20%
- 穩定層：
  - success rate >= 95%
  - avg health >= 90
  - max drift < 0.5

---
## 六、總結
Nexus 現況已具備「治理可用」基礎，但仍有典型成長痛：核心協調器過重、策略散落、命令層混責。  
最佳路徑不是重寫，而是依序做「抽資料/抽策略/抽責任」的小步重構，逐步把系統拉到可長期演化的乾淨架構。
