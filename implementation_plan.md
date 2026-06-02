# 🛡️ Implementation Plan: Phase 4 Patch-Synthesis Hardening

## 1. 計劃定位 (Rationale)
LocalHeal 已完成多階段編排、7B/14B 分流與治理收口。審計數據顯示瓶頸集中在 Phase 4 的「字面補丁品質」與「格式穩定性」。本計畫旨在透過「防禦先行、觀測隨後、受控優化」的節奏，硬化 Patch 階段的 fail-closed 能力，並以本地模型作為壓力測試探針，降低 `SEARCH_MISMATCH` 與 `SYNTAX_ERROR` 率。

## 2. 里程碑與任務 (Milestones & Tasks)

### 🚩 Milestone 1: Guardrail Hardening (防禦性守衛)
*   **Task 4A — Syntax Preflight (ast.parse)**: 在補丁套用前執行語法校驗，攔截非法代碼。
*   **Task 4B — Patch Error Taxonomy**: 統一補丁錯誤分類語義，確保審計一致性。

### 🚩 Milestone 2: Observation Telemetry (量化觀測)
*   **Task 4C — Phase 4 Observation Schema**: 建立獨立的觀測遙測，捕捉拒絕與空回應樣式。
*   **Task 4D — Offline Analysis Scripts**: 建立分佈分析工具，量化修補成本與失敗根因。

### 🚩 Milestone 3: Controlled Experiments (受控優化)
*   **Task 4E — Prompt Purity Spike**: 在觀測分流下實驗極簡 Aider 提示詞契約。
*   **Task 4F — Refusal Recovery Spike**: 實驗拒絕感知補償指令。

### 🚩 Milestone 4: Phase 5 Controlled Canary Governance (治理收斂)
*   **Task 5A — Canary Execution Contract**: 建立正式的 Canary 執行契約、Runbook 與 Checklist (Completed)。
*   **Task 5B — Governance Baseline Sealing**: 以前序 Phase 4 Probe 數據作為准入基線，封存治理邊界 (Sealed)。
*   **Task 5C — Small-Scale Canary Ready**: 準備第一輪小流量驗證樣本，定義 Canary Receipt Schema。

### 🚩 Milestone 5: Phase 6 Implementation Plan Formalization (架構封裝)
*   **Workstream A — Research Isolation Policy**: 定義 L0-L2 隔離分級與研究收據合約 (Plan Formalized)。
*   **Workstream B — Route Decision Intelligence**: 建立路由可解釋性 Rationale 與原因碼註冊表 (Plan Formalized)。
*   **Workstream C — Pre-Patch Preparation Layer**: 定義補丁前置預處理與 Reject Taxonomy (Plan Formalized)。
*   **Workstream D — Cost-Aware Autonomy**: 定義 observation-only 本地模型適配度基準 (Plan Formalized)。

## 3. 執行原則 (Principles)
- **Measured-Only**: 所有新增遙測維持 observation-only，不影響 public claim 或 promotion 門禁。
- **Fail-Closed**: 任何不合法或低信心的產物必須在 Patch 階段早停。
- **Local-Agnostic**: 優化應對所有模型有效，但必須先在 14B 本地模型上通過壓力測試。

---
[NEXUS STATUS: PHASE 4 INITIATED]
