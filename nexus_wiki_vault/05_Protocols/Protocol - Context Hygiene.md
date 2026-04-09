# Protocol - Context Hygiene

## 🎯 核心原則：上下文純淨度優先於一切 (Purity First)

隨意填充的大量日誌與冗餘上下文是導致 LLM 產生「幻覺」與「任務迷失」的根本原因。本協議定義了維持 Nexus 環境純淨度的物理邊界。

---

### 🛡️ 物理邊界 (Physical Boundaries)

1.  **輸出截斷 (The Truncation Wall)**：
    *   單次工具輸出超過 **2000 行** 或 **50KB** 時，必須由 `output_guard.py` 強制截斷。
    *   截斷後僅回傳：標頭、尾部 50 行、以及自動偵測到的 Root Cause 區塊。
2.  **記憶分片 (Memory Pagination)**：
    *   禁止一次性加載整個 Module 的源代碼。必須先使用 `get_symbols_overview` 進行預讀，精確定位後再讀取目標區塊。
3.  **結晶化代謝 (Metabolic Crystallization)**：
    *   長對話（超過 20 輪）必須觸發一次 `session_seed` 寫入，並重置上下文。當前狀態應由 `metabolism_engine` 保存並重新加載。

---

### 🛠️ 工作流要求 (Workflow Constraints)

*   **日誌讀取原則**：
    *   禁止盲目讀取 `/tmp/` 下的完整日誌。
    *   必須優先使用 `grep` 或 `awk` 尋找關鍵詞。
    *   範例：`grep -C 5 "AssertionError" /tmp/nexus_xxx.log`。
*   **變更摘要強制化**：
    *   每次修改文件後，必須在下一次推論中簡述「改動了哪些行」以及「為什麼這麼改」，作為對上下文的二次校準。

---

### ⚖️ 判定標準

*   **合格 (Clean)**：LLM 每次推論時，上下文中的代碼片段與日誌片段皆與當前目標高度相關。
*   **違規 (Polluted)**：上下文中存在大量與當前修復無關的編譯日誌、環境變量列表或無效的歷史輸出。

[METADATA]
Status: ACTIVE
Version: v1.0
Enforcement: ENGINE_LEVEL (via scripts/engine/output_guard.py)
