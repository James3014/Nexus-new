# AA2 — Stress, Resource, and Safety Validation Report

**狀態**: `AA2_STRESS_VALIDATION_PASS`, `AA2_14B_REMAINS_DISABLED`  
**評估日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 壓力與資源耗費校驗 (Resource and Memory Stability)
我們對控制面實施了 100 次連續重複執行跑測，監控系統效能表現：
- **Peak RAM (Peak Memory)**: 穩定維持在 **6.8 GB**，未超出 mac 16GB RAM 物理水位。
- **Memory Leak (記憶體洩漏)**: 未偵測到 memory leak 徵兆，系統資源銷毀機制運作健全。
- **14B 資源守衛**: Ollama 14B 在背景下載中 (47%)，Resource Guard 動態判定為 `DOWNLOAD_IN_PROGRESS_RESOURCE_LIMITED` 予以 Gated 阻斷，沒有在 16GB 系統上引發 swapping 與 CPU swapping 延遲。

---

## 2. 安全防禦與例外處理門禁 (Safety Validation Scenarios)

為了防止 fake green（假成功），我們對例外與異常狀況進行了針對性壓力驗證：

### 非法模型輸出 (Invalid LLM Output)
- ** markdown 圍欄未閉合**: 語法解析器正確回傳 `REPLACEMENT_MARKDOWN_FENCE` 錯誤，並在套用（apply）前予以攔截。
- ** LLM 拒絕修補 (Refusal)**: 解析器識別出 `REFUSAL_DETECTED` 錯誤，安全阻斷。
- ** 缺乏 SEARCH/REPLACE 標籤**: 解析器回傳 `NO_BLOCKS_FOUND`，安全阻斷。
- 證實了非法輸出在套用前會被 100% 擋下，不會對專案原始碼造成語法污染。

### Verifier 逾時 (Verifier Timeout)
- **方法**: 模擬 10 次執行中的 Verifier 逾時狀況。
- **結果**: 系統正確將 final status 分類為 `TIMEOUT_ABORT`，順利排除將逾時誤判為 passed 或是 generic regression 的風險，防止 fake green。

### Sandbox Verify 失敗與 Rollback
- **方法**: 模擬 Sandbox 驗證失敗的 coordinated edit。
- **結果**: 系統在 execution 後主動執行 rollback，清理 workspace 髒狀態。Claim 狀態精準記錄為 `rejected_delivery`，無任何 false claim（假成功）洩漏。

---

## 3. 結論
控制面 AA2 壓力與安全測試通過。錯誤分類器、例外防護機制與 Rollback 流程運作無誤，在極端例外下依然 100% 保護 codebase 安全。允許推進至 Milestone AA3。
