# Nexus Brain Hub Layer 2 治理對位裂縫診斷報告

## ⚠️ 嚴重等級：CRITICAL (核心治理失靈)

### 1. 發現摘要
在 `08_HALLUCINATION_GUARD_AND_HI_AUDIT.md` 與 `nexus/governance/hallucination_guard.py` 之間存在嚴重的權重計算邏輯與門檻定義衝突。目前的治理系統處於「假性對位」狀態。

### 2. 關鍵裂縫 (Alignment Gaps)

#### 2.1 權重邏輯衝突 (Weight System Mismatch)
*   **文檔描述**：使用「扣分/加分制」（如 -7.0分, +2.0分）。
*   **代碼實作**：使用「正值累積制」（如 weight: 7）。
*   **後果**：AI 無法透過閱讀文檔來預測其回覆的幻覺得分，導致自我修正行為失敗。

#### 2.2 判決門檻偏差 (Threshold Gap)
*   **REJECTED 門檻**：代碼寫死為 6，而文檔宣稱是 >= 6。
*   **落差**：文檔描述的邊界條件與實體執行器存在 1 分的偏差，這可能導致不穩定的治理行為。

#### 2.3 功能缺失 (Ghost Features)
*   **文檔宣稱**：支援 `Logic Mismatch` 與 `Verified Claim` 審計。
*   **代碼實作**：`metrics` 中完全沒有對應的實作邏輯。
*   **後果**：文檔向外部宣稱的「高級治理能力」目前並不存在於系統中。

### 3. 急迫改進建議
1.  **強制 SSOT**：廢除 `hallucination_guard.py` 中的內建 fallback，強制使用 `nexus/schemas/hallucination_index_v1.json` 作為唯一真相來源。
2.  **自動化對齊測試**：建立測試用例，掃描 Markdown 中的權重表格並與實體 Schema 進行對位校驗。

---
*存檔日期：2026-05-04*
*執行代理：Gemini Nexus Engineer*
