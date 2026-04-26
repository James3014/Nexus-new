# Nexus 測試執行手冊 (Test Runbook)

## 1. 執行流程 (Recommended Flow)
建議依序執行，確保從最快、最核心的驗證開始。

1. **L1 (Commit 級別)**: `bash scripts/ops/test_fast.sh`
2. **L2 (PR 級別)**: `bash scripts/ops/test_changed.sh [變更檔案路徑...]`
3. **L3 (合併級別)**: `bash scripts/ops/test_full.sh`

## 1.1 L2 變更關聯層

`test_changed.sh` 透過 `scripts/ops/select_tests.py` 查詢
`.nexus/test_impact_index.json` 與 `docs/testing/test_impact_map.md`，
再執行選出的 pytest targets。

更新 import index：

```bash
uv run python scripts/ops/build_test_impact_index.py
```

範例：

```bash
bash scripts/ops/test_changed.sh nexus/app/nightshift_runner_service.py
```

會選到：

```text
tests/app
```

多檔案變更可一次傳入：

```bash
bash scripts/ops/test_changed.sh nexus/core/state_validator.py docs/testing/test_runbook.md
```

若任何路徑沒有 active mapping，L2 會額外加入 core smoke fallback：

```text
tests/core tests/services/test_policy_gate.py
```

檢查 selector 決策細節：

```bash
uv run python scripts/ops/select_tests.py --json nexus/core/state_validator.py
```

JSON 會包含 `targets`、`reasons`、`confidence`、`risk`、`sources`。
若 `.nexus/reports/test_history.jsonl` 存在，selector 也會使用歷史耗時與 flaky 訊號排序。

CI gate 也提供相同 selector 的 changed-only lane：

```bash
uv run python scripts/ops/ci_gate.py --changed-only scripts/ops/select_tests.py
```

這條 lane 只跑受影響 pytest targets，不執行 wiki、benchmark、learn 或 release gates。

Strict gate 可把 JIT preflight 放在完整治理檢查之前：

```bash
uv run python scripts/ops/ci_gate.py --strict --changed-paths scripts/ops/select_tests.py
```

Nightly lane 執行 L3 全量回歸，並追加 `.nexus/reports/test_history.jsonl`：

```bash
uv run python scripts/ops/ci_gate.py --nightly
```

High-risk escalation:

- `nexus/core`
- `nexus/security`
- `scripts/ops/ci_gate.py`

這些路徑會自動標記 `risk=high`，並追加 policy-gate safety target。

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
