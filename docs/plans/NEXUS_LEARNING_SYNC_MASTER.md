# 📚 Nexus 核心範式知識庫 (13 柱神經元總合版)

> **致優化 Agent：**
> 本文件彙整了 Nexus 系統演化所依據的 13 項核心研究與工程範式。請以此為「事實來源」進行系統優化判斷。

---

## Public Promotion State Truth Table (2026-05-15)

本段是 benchmark / promotion lane 的狀態同步表。後續 agent 若發現 evidence bundle 更新，必須同步更新此表與
`docs/plans/NEXUS_PUBLIC_PROMOTION_SPEC_KIT_BRIDGE_2026-05-14.md`，不得讓舊 `RETURN` / `REGRESSED` / `quota_exhausted`
文字和最新 promotion contract 並存。

| Lane | Current state | Evidence bundle | Allowed claim |
| --- | --- | --- | --- |
| Gemini 3 Flash + Nexus | `PROMOTION_READY` | `/private/tmp/nexus-sanitized-runner-flash-full2-20260514/reports/evidence_bundle.json` | verified delivery, trust mismatch 0, cost efficiency improved |
| Gemini 3.1 Pro + Nexus | `PROMOTION_READY` | `/private/tmp/nexus-sanitized-runner-pro-hook4-20260514/reports/refilled_public4_20260515/evidence_bundle.json` | verified delivery, trust mismatch 0, cost efficiency improved with refill disclosure |
| GPT-5.5 direct | `BASELINE_REFERENCE` | `/private/tmp/nexus-sanitized-runner-gpt55-directonly3-20260514/reports/evidence_bundle.json` | direct baseline/reference only |
| GPT-5.5 + Nexus | `OBSERVATION_ONLY` | `/private/tmp/nexus-sanitized-runner-gpt55-hook10-20260515/reports/evidence_bundle.json` | hook10 provider-boundary analysis only; public delivery/cost gates pass, but no external public-model/parity claim |

Hard boundaries:

- Direct-arm refill may replace `quota_exhausted` or `provider_token_unmeasured` rows only when the replacement row is provider-token measured and remains semantically honest.
- GPT-5.5 + Nexus through Codex remains observation-only while the provider boundary is prompt-wearing-only or x3 readiness is not established. Hook10 has cleared the hook5 outbound-ledger, session-contamination, receipt-contract, model-annotation, route-policy-evidence, provider-token telemetry, wall-ledger telemetry, and prompt-purity blockers; its public delivery/cost gates pass but the external-provider promotion boundary still returns.
- Final-goal readiness is stricter than smoke promotion. The dashboard must require `benchmark_basis_contract.commercial_model_basis_ready=true` before claiming Gemini Flash/Pro + Nexus has reached the commercial-model-basis target against GPT-5.5 direct.
- Spec Kit is installed and may shape contracts, but `.specify` must not be initialized in a dirty worktree.

---

## 🏗️ I. 基礎設施與理解層 (Foundation & Logic)

### 1. AST (Abstract Syntax Tree)
*   **文獻重點**：代碼的樹狀結構表示法，是語法分析與靜態檢查的核心。
*   **實作細節**：
    *   透過遍歷樹狀節點（Node），可精確定位變數作用域（Scope）與函數調用鏈（Call Graph）。
    *   比 Regex 替換更安全，能確保代碼在修改後的結構完整性（Structural Integrity）。

### 2. RLM (Reasoning Loop Model / Recursive Language Models)
*   **文獻重點**：將長文本視為環境，透過「遞迴調用自身」處理超視窗任務。
*   **實作細節**：
    *   允許 LLM 程式化地檢查、分解並遞迴處理子任務。
    *   在處理長代碼或複雜邏輯時，優於傳統的單次 Compaction 方案。

### 3. MSA (Multi-System Alignment / Architecture)
*   **核心概念**：系統級的路由、對位與權限隔離。
*   **實作細節**：
    *   定義「領地（Tenants）」劃分，確保 Agent 在執行時具備明確的 Blast Radius（影響半徑）。
    *   所有能力調用必須遵循跨系統的對位契約。

---

## 🛡️ II. 治理與硬化層 (Governance & Hardening)

### 4. ACH (Automated Compliance Hardening)
*   **文獻重點**：Meta 提出的 LLM 引導式 **Mutation Testing (突變測試)**。
*   **實作細節**：
    *   **製造假 Bug**：故意改壞程式碼（Mutants），測試原有測試套件是否能偵測（Kill）它。
    *   **存活判定**：若 Mutant 存活（Survived），代表測試存在盲點（Blind Spot）。
    *   **有效性指標**：測試案例只有在能殺死 Mutant 時才被認定為「有效」。

### 5. Harness Engineering (前饋與回饋)
*   **文獻重點**：91APP 提出的 AI 開發防護架構。
*   **實作細節**：
    *   **前饋 (Feed-forward)**：在出發前定義規格、架構、邊界與 Sensor。
    *   **回饋 (Feedback)**：執行後用語義感測器（Semantic Sensors）確認 AI 沒有走偏。
    *   **BDD 驗收**：自動執行 Given-When-Then 案例，驗證「需求正確性」而非僅「代碼邏輯」。

### 6. JIT (Just-In-Time Validation)
*   **文獻重點**：即時生成「捕捉失敗」的測試，專門在代碼落地前發現潛在 Bug。
*   **實作細節**：
    *   透過 LLM 評估器（Assessor）過濾掉誤報，確保生成的捕捉測試具有高殺傷力。

### 7. HL / HS (Heuristic System / Hard Stops)
*   **文獻重點**：更新軟體結構（Policy/Tests/Memory），而非僅神經網路權重。
*   **實作細節**：
    *   **顯式狀態**：必須具備 Programmatic Policy、State Detectors 與 Feedback Channels。
    *   **壓縮歷史**：健康系統必須同時「吸收反饋」與「壓縮規則」，防止規則通脹。

---

## 🎯 III. 效能與測試維度 (Performance & Testing)

### 8. Performance Testing Triad (測試三劍客)
*   **文獻重點**：區分 Performance、Load 與 Stress Test 的不同目標與失效模式。
*   **實作細節**：
    *   **Performance Test (日常效率)**：在正常狀況下量測回應時間與資源使用率。對應 Nexus 的 `avg_wall_sec` 與 `process_boot_time`。
    *   **Load Test (峰值承載)**：在預期最大負載下驗證 SLA。對應 Nexus 的 `Swarm` 節點並發能力。
    *   **Stress Test (極限壓力)**：挖掘高壓下的隱性 Bug (Race condition, leaks)。對應 Nexus 的 `Safety Floor` 在低預算或高重試下的邏輯韌性。

### 9. AutoTTS (Automated Test-Time Scaling)
*   **文獻重點**：環境驅動的動態計算分配框架。
*   **實作細節**：
    *   **寬度-深度權衡**：Agent 自動發現何時該增加推理深度、何時該停止或轉向。
    *   **動態剪枝**：基於廉價且頻繁的反饋循環執行推理分支的自動剪除。

### 10. S2T (Strategic Self-Training / DivPO)
*   **文獻重點**：多樣性偏好優化（Diverse Preference Optimization）。
*   **實作細節**：
    *   **樣本選擇**：選擇「稀有但高品質」的樣本作為正例，避免模型輸出趨於保守單一。
    *   **對位效果**：提升生成任務的多樣性，同時維持高解決率（Win-rate）。

---

## 🧹 IV. 數據與評價層 (Data & Metrics)

### 11. Autodata
*   **文獻重點**：讓 Agent 扮演資料科學家，執行「生產、分析、再生產」的閉環。
*   **實作細節**：
    *   **鑑別力標準**：數據必須能區分強模型與弱模型（Strong-Weak Gap > 20%）。
    *   **演化層**：利用失敗軌跡修改 Harness 與 Prompt。

### 12. RubricEM
*   **文獻重點**：結構化評分與解釋性指標。
*   **實作細節**：
    *   **細粒度評分**：將全局分數拆解為 Fidelity、Safety、Efficiency 等子維度，並附帶語義解釋。

### 13. DCI (Deep Code Intelligence)
*   **核心概念**：深度代碼理解與影響力映射。
*   **實作細節**：
    *   執行 `Scan -> Impact -> Verify` 的閉環，確保 Agent 對複雜重構具備全量上下文。

---

## 🛡️ V. 質量保證與自動化工作流 (QA & Automation Workflow)

### 14. AI-DD QA Automation Workflow (Q42 品質框架)
*   **文獻重點**：91APP 提出的 AI 驅動開發（AI-DD），將產品需求（PRD）自動轉化為可執行的 Playwright UI 測試案例，實現測試左移。
*   **實作細節**：
    *   **嚴格的 GWT (Given/When/Then) 結構**：When 步驟必須對應單一 DOM 互動，動詞限定為精確動作（如點擊、輸入），並利用 Skill Labels 標籤將自然語言精確對應至程式碼實作。
    *   **AI 自我審查機制 (Self-Review Checklist)**：產出後強制執行 16 條 Checklist（如檢查模糊詞、DOM 互動唯一性），避免產生無效或易碎的測試。
    *   **自動化閉環與平台整合**：透過 AI 讀取需求進行「向上追溯」，並與 DevOps 平台深度整合，實現從 Test Goal 生成到測試任務狀態更新的全自動追蹤。

---
**[NEXUS KNOWLEDGE BASE v1.1 | PURE SYNTHESIS]**
