# 鋼鐵 Nexus - 深度推理與實驗進化整合計劃 (V2)

## 0. 核心願景
將 Nexus 從「代碼生成器」轉化為「實驗驅動的工程師」。透過 **ASI (實驗記憶)**、**Borda (民主評審)** 與 **Plateau (高原轉向)** 機制，徹底消除修復幻覺。

---

## 1. 數據結構層：引入 ASI 帳本 (The Ledger)
**目標**: 在 Nexus 的 `State` 中加入長效實驗記憶，確保實驗不重複且具備連續性。

### 實作細節
- **修改檔案**: `nexus/nexus/schemas/pipeline_outcome.py` (或相關 State 定義)
- **新增類**: `ASIRecord`
  ```python
  class ASIRecord(BaseModel):
      run_id: int
      hypothesis: str           # 本次實驗的假設
      family: str               # 實驗家族 (如: "parallel-processing", "mem-fix")
      metric: float             # 主要指標數值
      status: str               # "keep" | "discard" | "crash"
      evidence: str             # 成功的證據或失敗的日誌截圖
      rollback_reason: str      # 若失敗，原因為何？
      next_action_hint: str     # 給下一個 Agent 的建議
  ```
- **狀態持久化**: 在 `Metadata` 中新增 `asi_ledger: List[ASIRecord]`。

---

## 2. 核心推理層：Autoreason 競賽服務 (The Tournament)
**目標**: 實作實體 `autoreason_service.py`，負責候選方案的生成與評審。

### 實作細節
- **新增檔案**: `nexus/nexus/engine/autoreason_service.py`
- **核心方法**:
  - `generate_candidates(A: Code) -> (B, AB)`: 
    - B: 針對 A 的盲點進行對抗性修改。
    - AB: 嘗試融合 A 與 B 的優點。
  - `run_blind_judge(candidates: List[Code]) -> List[Vote]`: 
    - 啟動 3 個隱藏 Context 的子 Agent。
    - 每個 Agent 輸出一個排序列表 (1st, 2nd, 3rd)。
  - `borda_aggregator(votes: List[List[int]]) -> winner_id`:
    - 實作 Borda 計分（第一名 3 分，第二名 2 分...）。
    - 輸出決策證據 (Reasoning Trace)。

---

## 3. 策略決策層：Plateau 偵測與自動轉向 (The Brain)
**目標**: 監控實驗進度，防止系統在局部最優解「鬼打牆」。

### 實作細節
- **修改檔案**: `nexus/nexus/app/research_flow_service.py`
- **新增邏輯**: `PlateauMonitor`
  - **Window 監控**: 觀察最近 5 輪的 `asi_ledger`。
  - **觸發條件**: 
    - 若最近 4 輪 `status == discard`。
    - 且 `family` 均相同。
    - 且 `metric` 波動小於 5%。
  - **轉向動作**: 
    - 強制將下一個實驗的 `Lane` 設為 `DISTANT_SCOUT`。
    - 提示 Agent：「局部微調已無效，請重新審視架構或更換底層演算法」。

---

## 4. 驗證與協作層：文檔偵查與 HITL (The Shield)
**目標**: 吸收 ResearchClaw 的外部驗證能力，並在信心不足時請求人類支援。

### 實作細節
- **新增檔案**: `nexus/nexus/research/doc_scout_adapter.py`
  - **DocScout**: 串接現有的 LanceDB，抓取項目內 README、Issue 與第三方庫的 ChangeLog。
  - **Claim Checker**: 在 `Packet` 執行前，對 `hypothesis` 進行斷言檢查（如：確認該 API 是否真的支援某參數）。
- **修改檔案**: `nexus/nexus/engine/pipeline.py`
  - **HITL Collaborative Gate**: 
    - 當 `belief_confidence < 0.6` 且處於 `Plateau` 時。
    - 暫停並輸出 `Dashboard URL`。
    - 提供 `Strategic Injection` 介面，允許工程師輸入指令（如：「試著往內存洩漏方向查」）。

---

## 5. 整合引導 (給實作 Agent 的指令)

1.  **Step 1**: 先修改 Schema，確保 `asi_ledger` 能正確存儲。
2.  **Step 2**: 實作 `autoreason_service.py` 並在本地跑通 Borda 投票單元測試。
3.  **Step 3**: 將 `ASIRecord` 寫入邏輯植入 `pipeline_repair.py` 的每一次循環。
4.  **Step 4**: 在 `research_flow_service` 中加入 `PlateauMonitor` 檢查點。
5.  **Step 5**: 最後接入 `DocScout`，在研究階段前置觸發。

---

## 6. 驗證與 Evidence
- **Log**: 需看到 `[AUTOREASON] Borda Winner: Candidate AB (Votes: [3, 2, 3])`。
- **ASI**: `.nexus/runs/` 下的 state 文件需包含完整的 `asi_ledger` 歷史。
- **Pivot**: 當實驗失敗多次時，日誌應顯示 `[PLATEAU DETECTED] Switching to DISTANT_SCOUT lane`。
