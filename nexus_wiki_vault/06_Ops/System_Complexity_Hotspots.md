# 代碼效能與複雜度熱點 (Complexity & Bottleneck Radar)

**掃描日期**: 2026-06-05
**工具來源**: `codex-complexity-optimizer`
**原始產物位置**: `docs/perplexity/codex-complexity-optimizer/report.json`

本文件記錄了系統中潛在的效能瓶頸與 O(N^2) 高風險區，應在後續重構或效能調優時優先處理。

## 🔴 HIGH Risk - 高風險熱點

### 1. `notebooklm-bulk-injector` 雙重迴圈
*   **路徑**: `.agents/skills/notebooklm-bulk-injector/scripts/bulk_upload.py:14` (包含 `eval` 執行目錄下的同名文件)
*   **問題描述**: `HIGH nested-loop`。存在雙重迴圈，可能導致 O(N^2) 或更差的執行效能。
*   **修復建議**: 檢查是否能透過建立 Map/Set 索引 (Hash Table)、Sort + 雙指標掃描、分組 (Grouping) 或批次處理 (Batching) 來取代內部迴圈掃描。

### 2. `swe_harness.py` N+1 I/O 查詢
*   **路徑**: `.nexus/runs/eval_113/benchmarking/swebench_lite/swe_harness.py:141`
*   **問題描述**: `HIGH io-or-query-in-loop`。在迴圈內部執行 Database / API / 檔案系統操作，容易觸發 N+1 效能地雷。
*   **修復建議**: 應改為在迴圈外部進行批量預載 (Batch / Preload)，同時確保權限驗證、過濾與錯誤處理邏輯正確轉移。

### 3. `swe_harness.py` 雙重迴圈
*   **路徑**: `.nexus/runs/eval_113/benchmarking/swebench_lite/swe_harness.py:179`
*   **問題描述**: `HIGH nested-loop`。同樣存在可能導致 O(N^2) 的巢狀迴圈問題。
*   **修復建議**: 使用哈希索引或批量處理技術展平迴圈結構。