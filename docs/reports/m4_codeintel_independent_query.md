# M4: CodeIntel/JIT Independent Query in CapabilitySelector

**Status**: M4_PASS

## Files changed
- `nexus/core/capability_signal_set.py` — 加 `codeintel_query_available` (bool) + `codeintel_evidence` (dict) 欄位
- `nexus/core/capability_selector.py` — 加 `_codeintel_query()` 方法 + X/Recon 階段查詢 (M4 block at 2.7)
- `tests/core/test_codeintel_query.py` — 新建: 5 個 M4 test

## Test counts
- 5 new (M4) + 4 (M3) + 210 existing = 219 total PASS

## Changes
1. `CapabilitySignalSet`: 新增 `codeintel_query_available` (default False) 與 `codeintel_evidence` (default {})
2. `CapabilitySelector._codeintel_query()`: 掃描 project_root 下的 src 目錄與 Python 檔案
3. X/Recon 階段: 當 `codeintel_query_available=True` 時執行查詢，結果寫入 `signal_set.codeintel_evidence`
4. 查詢失敗不阻擋 selector (try/except + logger.debug)

## Governance boundary
- `codeintel_query_available=False` (default) → 跳過查詢，既有行為不變
- 不修改既有 selector 路徑
