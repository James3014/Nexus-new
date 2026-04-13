# Nexus 測試執行手冊 (Test Runbook)

## 1. 執行流程 (Recommended Flow)
建議依序執行，確保從最快、最核心的驗證開始。

1. **L1 (Commit 級別)**: `bash scripts/ops/test_fast.sh`
2. **L2 (PR 級別)**: `bash scripts/ops/test_changed.sh [變更檔案路徑]`
3. **L3 (合併級別)**: `bash scripts/ops/test_full.sh`

## 2. 失敗排查清單 (Troubleshooting)

### 磁碟空間壓力 (Errno 28)
- **現象**: 測試中斷，提示 `No space left on device`。
- **對策**: 
  - `rm -rf .pytest_cache`
  - `uv cache clean`
  - `rm -rf /tmp/pytest-of-$(whoami)`

### 併發污染 (Concurrency Issues)
- **現象**: 大量隨機失敗，提示 `tmux duplicate session` 或資料庫鎖死。
- **對策**: **禁止同時並發跑多個 pytest 進程**。請確保當前只有一個測試腳本正在執行。

## 3. 隔離環境
所有測試必須透過 `uv run python -m pytest` 執行，以確保使用專案內部的 `.venv` 依賴組合。
