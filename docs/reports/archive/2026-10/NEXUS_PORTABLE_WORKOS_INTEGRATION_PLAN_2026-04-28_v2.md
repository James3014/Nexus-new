# Nexus 可攜式 Work OS 整合計劃 v2（現況對齊版，供其他 Agent 接手）

## 0) 目的
以「增量整合」方式把你的實戰流程產品化到 Nexus；不重做已存在能力，只補真正缺口。

---

## 1) 現況核對（先決條件）
本計劃已先核對代碼現況，依據：
- `/Users/jameschen/Workspace/nexus/docs/reports/NEXUS_PLAN_VS_CODE_STATUS_2026-04-28.md`

### 1.1 已有能力（直接沿用，不重做）
1) 單一 owner 任務模型與 multi-agent 任務流
- `nexus/orchestrator/task_contract.py`
- `scripts/engine/nexus_cli.py`（`nexus multi-agent *`）

2) 任務狀態機（含 blocked/failed/rejected）
- `nexus/orchestrator/task_contract.py`

3) evidence bundle + replay + anti-drift 驗證
- `nexus/delivery/evidence_verifier.py`
- `scripts/engine/nexus_cli.py`（hallucination evidence/gate）

4) fail-closed gate 與 policy block
- `nexus/delivery/evidence_verifier.py`
- `nexus/services/policy_gate.py`

5) 高風險 requires_human_approval 文字 gate
- `scripts/engine/l6_gate.py`

### 1.2 部分有（需補齊）
1) Proposal/ADR gate：有分散實作痕跡，缺統一硬性 gate。
2) Acceptance Matrix：有驗證資料，但缺統一輸出格式契約。

### 1.3 缺口（本計劃主要實作）
1) `consulted_agents <= 2` 的程式級強制。
2) `delivery_profile`（mock_only/live_browser/live_api）內建 schema + gate。
3) `nexus ask` 前置 question normalization/source anchoring 內建化。

---

## 2) 來源（Sources）

### A. 一手需求來源
- 你提供的長文：`[AI實驗：愛馬仕升級為作業系統]`（本對話）
- 核心要求：skills-first、自治時間盒、踩雷修補閉環、live data 最後一哩、可攜到其他 agent。

### B. 已完成驗證資產
1. `/Users/jameschen/Workspace/nexus/docs/reports/NEXUS_PHASEA_REAL_PROMPT_REPLAY_2026-04-28.md`
2. `/Users/jameschen/Workspace/nexus/docs/reports/NEXUS_PHASEA_REPLAY_RESULTS_2026-04-28_v2.md`
3. `/Users/jameschen/Workspace/nexus/docs/reports/NEXUS_PHASEB_LIVE_REPLAY_RESULTS_2026-04-28_v3.md`
4. `/Users/jameschen/Workspace/nexus/docs/reports/assets/phaseC_failcase_evidence_pack_2026-04-28.json`

---

## 3) 實作策略（只做缺口）

## Phase A（P0）：把既有能力串成標準路徑（1-2 天）
What
- 固化單一路徑：`multi-agent create/start -> verify -> submit -> delivery gate`。
- 輸出統一 closeout 模板（changed files / acceptance matrix / evidence index / verdict）。

Why
- 先把「已有能力」用一致流程跑起來，避免不同 agent 各自解讀。

How
- 新增一份 ops 規格文件 + 最小 CLI 範例腳本（不改核心邏輯）。

驗收
- 任一 agent 可按文件重跑並產生一致 closeout 結構。


## Phase B（P1）：補齊 consulted_agents 與 proposal/ADR 硬 gate（2-3 天）
What
- 在 task schema/command path 增加 `consulted_agents`，強制最多 2。
- 跨邊界任務若無 proposal/ADR 標記，直接 RETURN/BLOCK。

Why
- 對齊你的治理規範：單一 owner + 最多 2 consulted + 先 proposal/ADR 再執行。

How
- 改動點（建議）：
  - `nexus/orchestrator/task_contract.py`
  - `scripts/engine/nexus_cli.py`（create-task/submit 前驗證）
  - 補對應 tests。

驗收
- 超過 2 consulted 直接失敗。
- 跨邊界任務缺 proposal/ADR 無法進入 submit。


## Phase C（P1）：內建 delivery_profile gate（2-3 天）
What
- 導入 `delivery_profile` 欄位：`mock_only | live_browser | live_api`。
- submit 時強制對應證據：
  - mock_only：不可宣稱 live
  - live_*：必須有 live 證據索引與 human approval

Why
- 防止「流程展示成果」被誤報為「真實 live 交付」。

How
- 改動點（建議）：
  - `task_contract.py` 增欄位
  - `submission.py` / `evidence_verifier.py` 增判定
  - CLI 增參數與輸出欄位

驗收
- live 任務缺 live 證據必 BLOCK。
- mock 任務標 live 直接 RETURN/BLOCK。


## Phase D（P2）：ask 前置正規化（2 天）
What
- 在 `nexus ask` 前加 question normalization + source anchoring（可配置）。

Why
- 已驗證會遇到高頻 notice/table claim 影響回答；需內建減噪。

How
- 新增可選 preprocessor（預設開啟，可關閉）。
- 保留 strict_topic + citation gate。

驗收
- 同一回放集命中率穩定 >= 95%，citation coverage = 100%。

---

## 4) 全局 Fail-Closed 規則
以下任一成立即 RETURN/BLOCK：
1) 無 evidence path
2) 無可重跑命令
3) 高風險無 human approval
4) 宣稱 live 無 live 證據
5) 回歸未達門檻

---

## 5) 交接給其他 Agent 的執行順序
1) 先讀：
- 本文件
- `NEXUS_PLAN_VS_CODE_STATUS_2026-04-28.md`
- Phase A/B 現有回放報告
2) 先跑現況基線（不可先改碼）
3) 依序做 Phase A -> B -> C -> D
4) 每階段都交付：
- changed files
- acceptance matrix
- evidence index
- verdict（PASS/RETURN/BLOCK）

---

## 6) Definition of Done
- 其他 agent 不依賴 Hermes 私有習慣，也能重現：
  - skills-first
  - evidence-first
  - fail-closed
  - owner+consulted 治理
  - live/mock 分級與核准門
- 且全流程可重跑、可審計、可回滾。