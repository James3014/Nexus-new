# Real Qwen Diff Hardening Report (v0)

本報告彙整了本地真實 Qwen/Ollama 模型的 Diff 合約加固與容錯修補（Real Qwen Diff Contract Hardening）的實作與驗收成果。

---

## 🛠️ Output Repair Normalizer 機制

為了容錯本地模型產生的 unified diff 中非標準 header 格式（如缺失 `a/` 與 `b/` 前綴，或檔案名稱與目標檔案錯置等），我們引入了 [diff_normalizer.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/diff_normalizer.py)：

1. **偵測與校正**:
   - 提取 diff 中的 `--- ` 與 `+++ ` 行。
   - 當格式不符標準時，將其自動修正轉正為合規的標準 unified diff header（例如 `--- a/<target_file>` 與 `+++ b/<target_file>`）。
   - 重新計算校正後 diff 的 SHA256 作為新 hash，保證 sandbox apply 與 `applied_patch_hash` 驗證對齊。

2. **憑證與審計收據 (Normalizer Receipt)**:
   - 校正過程會產生收據，並寫入 `metadata` 以供審查：
     - `original_target_file`: 原始 diff 解析出的檔名。
     - `normalized_target_file`: 轉正後的檔名。
     - `normalization_reason`: 觸發校正原因 (如 `missing_ab_prefix` 或 `filename_mismatch`)。
     - `normalized_by_rule`: 套用規則。
     - `normalized`: 是否觸發校正 (bool)。

---

## 🧪 測試驗證與覆蓋

1. **單元測試**:
   - 建立 [test_diff_normalizer.py](file:///Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_diff_normalizer.py) 單元測試，覆蓋標準無變更、缺失 prefix、檔名不匹配等三種場景的校正功能。
2. **整合測試**:
   - 於 [test_controlled_local_solve_fixture_runner.py](file:///Users/jameschen/Workspace/nexus/tests/integration/test_controlled_local_solve_fixture_runner.py) 增加 `test_fixture_diff_normalization_success`。
   - 使用故意給出錯置 header（如 `--- old_f.py` / `+++ new_f.py`）的 diff 做輸入，斷言其最終能藉由 normalizer 轉正，通過 verifier 沙箱，並成功寫入憑證收據。

---

## 📈 評估與結論
- **基礎設施加固**：在不放寬 `target_file_mismatch` 與 `SEARCH_MISMATCH` 的嚴格安全合約下，Normalizer 能安全轉正模型產出的 unified diff，顯著提升了真實本地模型解題路徑的魯棒性。
