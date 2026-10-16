# 🛡️ Nexus Phase 52-55: Failure-Guided Retry v1 評估報告

本報告總結了 **失效引導重試機制 (Failure-Guided Retry v1)** 的設計實作與實測小批次數據。

---

## 1. 核心設計與機制
我們在 `capability_adapter.py` 層級引進了 `max_attempts=2` 迴圈控制，職責分離確保 Sandbox 執行器與 LLM 連接邏輯解耦：
1. **縮寫式反饋 (`failure_feedback_builder.py`)**：在 attempt 1 失敗時，過濾並僅截取 verifier 最末尾的 15 行日誌，拼裝 task_id, failure_class, previous_block_reason 等屬性與標準輸出合約提示，建立無雜音的 retry prompt。
2. **重試門檻限制**：
   - 僅在 `VERIFIER_FAIL` 或 `SEARCH_MISMATCH`（排除 `patch_outside_locked_span` 實質越界）時觸發重試。
   - 硬性越界（真正修改到 locked span 之外）直接阻斷，不予重試。

---

## 2. 實測小批次評估數據

- **總嘗試題數 (Attempted)**：10 題
- **重試觸發題數 (Retry Attempted)**：3 題 (`t_batch_4`, `t_batch_6`, `t_batch_10`)
- **重試理由 (Retry Reason)**：3 題均為 `VERIFIER_FAIL`
- **重試成功率 (Retry Success)**：0/3 (0%)
- **最終解決率 (Solved Rate)**：**70% (7/10)**

---

## 3. 殘餘阻斷定性分析 (Remaining Blockers)
對於觸發重試但最終失敗的 3 題：
- **`t_batch_4` (Off-by-one bug)** & **`t_batch_10` (Boolean Inversion)**:
  - *分析*: 模型在第一輪和第二輪均產生了與實體測試不相容的 patch，因而被 verifier fail-closed 攔截。
- **`t_batch_6` (Recursion Base case)**:
  - *分析*: 自癒修復器重建 diff 成功，但因內容邏輯與 context 存在本質衝突，第二輪套用與 verifier 測試依舊失敗。

儘管重試未能在這 3 道難度較高的題上產生 direct solve，但 **results.jsonl** 完整記錄了重試過程收據，且沒有任何越界修改被放行。這證實了本階段 Failure-Guided Retry 基建的可靠性與安全性。
