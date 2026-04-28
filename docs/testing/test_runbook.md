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

JSON 會包含 `targets`、`reasons`、`confidence`、`risk`、`risk_reasons`、`sources`、`selected_count`、`fallback_used`、`high_risk_escalated`、`unmatched_paths`、`retry_recommended`。
若 `.nexus/reports/test_history.jsonl` 存在，selector 也會使用歷史耗時與 flaky 訊號排序。

CI gate 也提供相同 selector 的 changed-only lane：

```bash
uv run python scripts/ops/ci_gate.py --changed-only scripts/ops/select_tests.py
```

這條 lane 只跑受影響 pytest targets，不執行 wiki、benchmark、learn 或 release gates。
它會產生 `.nexus/reports/changed_only_junit.xml`，並把總耗時與 per-target duration 寫回 `.nexus/reports/test_history.jsonl`。

Strict gate 可把 JIT preflight 放在完整治理檢查之前：

```bash
uv run python scripts/ops/ci_gate.py --strict --changed-paths scripts/ops/select_tests.py
```

Nightly lane 執行 L3 全量回歸，並追加 `.nexus/reports/test_history.jsonl`：

```bash
uv run python scripts/ops/ci_gate.py --nightly
```

Gemini benchmark 前的本地 readiness gate：

```bash
uv run python scripts/ops/nexus_benchmark_preflight.py --output-json
```

這條 lane 不呼叫 Gemini，也不消耗模型額度。它會檢查 CodeIntel impact evidence、RLM trace quality、JIT predictive promotion fail-closed boundary、public claim gate guardrails，並輸出 `.nexus/reports/benchmark_preflight_readiness.json`。只有 `ready_for_benchmark=true` 時，才適合啟動 Gemini bare vs Gemini+Nexus 正式 benchmark。

JIT observation:

```bash
uv run python scripts/ops/jit_coverage_gap.py
```

這會讀 `.nexus/reports/jit_observation.jsonl` 並輸出 `.nexus/reports/jit_coverage_gap.json`，用來找 fallback-heavy、unmatched、high-risk、slow generic target。這不是 ML ranking，只是先累積資料與缺口。

High-risk escalation:

`docs/testing/test_impact_map.md` 的 `風險` 與 `風險原因` 欄位是 high-risk SSoT；`risk=high` 的 active row 會追加 policy-gate safety target，並輸出 `risk_reasons`，例如 `governance`、`security`、`core_contract`。`ci_gate.py --strict --changed-paths ...` 也會讀 selector metadata 來決定是否觸發 Ultra Review。

Flaky retry recommendation:

- selector 會根據歷史 `0 < failures < runs` 標記 `retry_recommended`
- v3 只輸出 retry 建議，不自動重跑；自動 retry 需要等 history 穩定後再接

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
