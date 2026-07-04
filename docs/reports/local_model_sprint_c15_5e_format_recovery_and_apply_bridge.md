# 📑 LocalModel Sprint C15-5E: Format Recovery and Deterministic Apply Bridge for Small-Model Committee

## 1. 任務摘要 (Handoff Summary)
在 C15-5E 任務中，我們為異質小模型委員會（Small-Model Committee）實作了 **Path B: Deterministic Unified-Diff-to-SSRP Bridge**。小模型（如 `ornith:9b`，`qwythos:9b`）傾向於輸出標準的 `unified diff` 格式而非 `SEARCH/REPLACE`。為了解決此格式合約不匹配的問題，我們建立了一個精確的 Unified-Diff-to-SSRP 轉換器，並整合至 `PatchSynthesisPhase` 與 `LocalModelExecutor` 格式過濾門。

---

## 2. 轉換與過濾路徑設計 (Call Path Map)
```
[LLM Raw Output: Unified Diff]
              │
              ▼
[SolidSearchReplaceProtocol.classify_format()]  ──► Classified as "UNIFIED_DIFF"
              │
              ▼
[PatchSynthesisPhase.run() (Path B Converter)]
   - Read original source code
   - Verify single-file targeting
   - Match exact preimage in source
   - Reconstruct structured SSRP blocks
              │
   ┌──────────┴──────────┐
   ▼ (Success)           ▼ (Fail)
[SSRP Patch Generated]  [Response set to empty]
   │                     │
   ▼                     ▼
[Parser: SUCCESS]      [Parser: PATCH_FORMAT_INVALID]
   │                     │
   ▼                     ▼
[Executor Gate]        [Executor Gate]
   - Allow converted      - Reject with specific reason
     SSRP to pass           (e.g., target_mismatch)
```

---

## 3. 實作細節與改動檔案 (Changes Made)

### 3.1 `diff_to_ssrp.py` [NEW]
- 實作 `DiffToSSRPConverter.convert(raw_diff, expected_target_file, source_text)`。
- 嚴格解析統一比對區塊（Hunks），驗證是否為單一檔案、目標路徑是否一致、以及搜尋內容（Preimage）是否在原始碼中唯一存在。
- 回傳精確轉換後的 SSRP 字串、狀態碼以及對應的 Telemetry 雜湊。

### 3.2 `protocol.py` [MODIFY]
- 新增靜態方法 `classify_format(raw)`，精確識別輸出種類（`EMPTY`, `REFUSAL`, `UNIFIED_DIFF`, `VALID_SEARCH_REPLACE`, `FENCED_SEARCH_REPLACE`, `MALFORMED_SEARCH_REPLACE`, `MARKDOWN_FENCED`, `PLAIN_TEXT`, `NATURAL_LANGUAGE`），統一分類合約。

### 3.3 `patch_synthesis.py` [MODIFY]
- 將 `output_class` 分類委託給 `SolidSearchReplaceProtocol.classify_format`。
- 在解析之前，若分類為 `UNIFIED_DIFF`，主動執行 `DiffToSSRPConverter` 進行橋接轉換。若成功則代入轉換後的 SSRP，失敗則清除 Response 以觸發 `PATCH_FORMAT_INVALID` 解析錯誤。

### 3.4 `local_model_executor.py` [MODIFY]
- 優化格式過濾門，優先自 `model_decisions` 取得已分類的 `output_class`。
- 新增 `unified_diff_to_ssrp_converted` 過濾放行邏輯，其餘 Unified Diff 錯誤則依轉換狀態回傳對應的拒絕原因（例如 `unified_diff_target_mismatch` 等）。
- 於 `LegacyHealContext` 建立時明確傳遞並記錄候選模型 `committee_proposer_model`。

### 3.5 `prompt_builder.py` [MODIFY]
- 修正 `is_small_local` 定義，將 `14b` 自預設小模型清單中移除（僅保留 `7b`, `9b`, `6.7b` 等），確保 14B 等級模型套用完整版引導提示。

---

## 4. 紅線與合約審核 (Red-line Review)
| 規則 | 審核結果 | 說明 |
| :--- | :---: | :--- |
| 不新增 route/router/planner | 🟢 通過 | 完全沒有修改 CapabilityPlanner 或 HybridRouteDecision |
| 不放寬 SEARCH/REPLACE parser | 🟢 通過 | parser 解析規則維持不變，僅在解析前執行 Path B 橋接轉換 |
| 不改動 verifier 行為 / 不 fuzzy apply | 🟢 通過 | apply 依然使用精確比對，未放寬 preimage 比對標準 |
| 僅對單一 task_id commit 限制作業 | 🟢 通過 | 僅提交 C15-5E 任務所屬之 `local_model_executor.py` 等關聯檔案 |

---

## 5. 驗證與基準測試證據 (Evidence)

### 5.1 單元測試 (Unit Tests)
建立獨立單元測試 `tests/unit/local_heal/test_diff_to_ssrp.py`，完整覆蓋各項轉換與拒絕邏輯。全量本地測試通過：
```text
tests/unit/local_heal/test_diff_to_ssrp.py::test_diff_to_ssrp_converts_single_file_exact_preimage PASSED
tests/unit/local_heal/test_diff_to_ssrp.py::test_diff_to_ssrp_rejects_multi_file_diff PASSED
tests/unit/local_heal/test_diff_to_ssrp.py::test_diff_to_ssrp_rejects_target_file_mismatch PASSED
tests/unit/local_heal/test_diff_to_ssrp.py::test_diff_to_ssrp_rejects_missing_preimage PASSED
tests/unit/local_heal/test_diff_to_ssrp.py::test_diff_to_ssrp_rejects_ambiguous_preimage PASSED
tests/unit/local_heal/test_diff_to_ssrp.py::test_diff_to_ssrp_records_source_hash PASSED

tests/unit/local_heal/test_prompt_builder.py PASSED (6/6)
tests/unit/local_heal/test_local_model_executor.py PASSED (154/154)
```

### 5.2 基準測試 (Live Run Evidence)
執行 `toy-math-verifier-evidence-gap`（候選模型：`qwen2.5-coder:7b-instruct`）回報之關鍵資訊：
- `delegated_retry_stage`: `first_patch_failed` (過濾門通過，但 isolated verifier 不符 ZeroDivisionError 檢驗而失敗)
- `delegated_retry_provider_called`: `True`
- `delegated_retry_status`: `SUCCESS` (代表格式解析與 isolated apply 均綠燈通過)

---

## 6. 決策門與後續路徑 (Decision Gate & Debt)
- **判定結果**：**Gate C** (Parser Pass, Verifier Fail)
- **技術債 (Debt)**：本地模型推理在細緻度合約上容易因 verifier 特殊語法要求而遭阻斷。
- **後續路徑建議**：進入 **C15-3U / C15-5F: Verifier-Guided Delegated Retry Quality**，利用 verifier feedback 引導異質小模型修復精細邏輯細節。
