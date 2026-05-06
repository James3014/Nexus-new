# RFC-2026-05-04: Nexus 鋼鐵研究與深度推理強化計劃

## 1. 計劃目標
將 `autoreason` 的競賽評審機制與 `AutoResearchClaw` 的長程管線能力，正式硬化為 Nexus 的核心組件，提升系統處理「高不確定性修復」與「長程技術調研」的能力。

---

## 2. 模組一：Autoreason 實體化 (The Reasoning Engine)
**目標**: 實作 `autoreason_service.py`，取代目前的 Mock 邏輯。

### 核心組件 (P0)
*   **Candidate Factory**: 生成 Incumbent (A)、Revision (B)、Synthesis (AB)。
*   **Blind Judge Panel**: 啟動 3-7 個獨立 Agent 進行盲評，禁止上下文洩漏。
*   **Borda Consensus**: 實作 Borda 計票演算法，輸出 `winner` 與 `stop_reason`。
*   **A-Streak Policy**: 實作 A 連勝 (預設 k=2) 自動停手策略，節省 Token。

### 預期改動
- `Create: nexus/nexus/engine/autoreason_service.py`
- `Modify: nexus/nexus/app/research_flow_service.py` (接入實體服務)
- `Create: tests/engine/test_autoreason_service.py`

---

## 3. 模組二：ResearchClaw 知識萃取 (The Knowledge Claw)
**目標**: 吸收 ResearchClaw 的偵查能力，強化 Nexus 的 `Research` 階段。

### 核心組件 (P1)
*   **DocScout Adapter**: 將文獻檢索邏輯轉化為「項目文檔/Issue/依賴庫變更日誌」的深度檢索。
*   **Claim Verification**: 引入「斷言驗證」，將修復計畫中的每一個「假設」與現有代碼實事進行物理比對。
*   **HITL Collaborative Gate**: 實作「共治門禁」，當路由信心低於 0.6 時，自動啟動互動式 CLI 請求工程師介入指導方向（而非僅是 approve/reject）。

### 預期改動
- `Create: nexus/nexus/research/doc_scout_adapter.py`
- `Modify: nexus/nexus/engine/pipeline_research.py` (升級 Master Loop)
- `Modify: scripts/ops/ultra_gate.py` (加入 Claim Check)

---

## 4. 實作路徑 (Action Items)

### Phase 1: 骨幹建立 (Next 24h)
1.  **實作 Autoreason 基礎框架**: 建立 `autoreason_service.py`，定義 `A/B/AB` 數據結構。
2.  **建立 Borda 投票器**: 實作 `BordaAggregator` 類，確保計票邏輯正確。
3.  **接入路由**: 讓 `research_flow_service` 在 `complexity > hard` 時能觸發 `autoreason_service`。

### Phase 2: 知識硬化 (Next 48h)
1.  **實作 DocScout**: 串接 LanceDB 與本地 Markdown Wiki，模擬文獻檢索的「背景調查」流程。
2.  **強化 HITL**: 在 `pipeline.py` 的 gate 階段，加入 `attach_session` 功能，允許人類注入 `Strategic Guidance`。

---

## 5. 驗收標準 (Success Criteria)
1.  **Autoreason 驗證**: 在 `human_eval` 測試集上，Autoreason 產出的修復品質優於單次生成 (Single-pass)。
2.  **路由透明度**: 報告中能明確顯示 `Borda Votes` 分布與 `Consensus Winner`。
3.  **HITL 有效性**: 系統在高風險任務中能主動「停手問路」，且能吸收人類注入的關鍵字進行重新路由。
