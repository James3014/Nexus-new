# Nexus Learning Loop Closed-Loop Report

Date: 2026-04-03
Repo: `.`
Scope: `main` Python 主線的 learning / write-back / delivery 閉環

## 1. 結論

本輪已完成一個可運作的工程閉環：

1. 任務啟動時執行 protocol gate 與 CI gate。
2. 任務收尾時自動結晶 lesson。
3. 自動生成 write-back todo 與 delta artifact。
4. 任務先進入 `code_done_writeback_pending`。
5. 下一次 Nexus 啟動或 refresh 時，自動檢查並套用 write-back。
6. write-back 完成後自動升級為 `fully_delivered`。

這代表 Nexus 已從「只記錄事件」進化到「會留下 lesson、會產生回寫待辦、會自動完成回寫並結案」。

## 2. 已提交的 commit

- `2d054a6` `feat(nexus): enforce continuous learning loop`
- `f65931e` `fix(nexus): harden learning completion and test fallbacks`
- `c9e813e` `feat(nexus): auto-apply writeback deltas`

## 3. 重要提醒

上述三個 commit 已提交。

但 repo 目前不是全乾淨：

- [MUSE_ENGINE_SPEC_V17.1_HARDENED.md](./MUSE_ENGINE_SPEC_V17.1_HARDENED.md) 可能被 runtime auto writeback 修改
- [.codex_lessons.md](./.codex_lessons.md) 是執行時 artifact，目前未提交
- `.nexus/events/*`、`.nexus/reports/*` 屬於執行證據，不在 commit 範圍
- `nexus-desk` 與其他大量 dirty 檔案屬於另一條工作線，與本次 learning loop commit 無關

因此要分清楚：

- 已提交的是 learning loop 機制代碼與測試
- 未提交的是 runtime 執行證據與其他工作線變更

## 4. 本輪改動內容

### 4.1 Startup Gate

檔案：
- [nexus_cli.py](./scripts/engine/nexus_cli.py)
- [continuous_learning.py](./nexus/services/continuous_learning.py)
- [ci_gate.py](./scripts/ops/ci_gate.py)

行為：
- 主線 CLI 啟動時會跑 `run_protocol_startup_gate(...)`
- 寫入：
  - `.nexus/events/protocol_ack.jsonl`
  - `.nexus/events/session_start.jsonl`
- mutating command 走 `ci_gate.py --strict`
- read-only command 走 `ci_gate.py --dry-run`
- 支援 recent strict pass cache

目的：
- protocol loading 不再只是 reminder
- CI gate 有可追溯 audit trail
- read-only command 不會再被重型 strict lane 卡死

### 4.2 Lesson Crystallization

檔案：
- [continuous_learning.py](./nexus/services/continuous_learning.py)
- [pipeline_crystal.py](./nexus/engine/pipeline_crystal.py)
- [coordinator.py](./nexus/engine/coordinator.py)
- [steward.py](./scripts/steward.py)

行為：
- `finalize_learning_loop(...)` 會收斂：
  - `cycle_root_cause`
  - `phantom_success_reason`
  - `rejection_history`
- 呼叫 `MemorySteward.crystallize(...)`
- 寫入 [.codex_lessons.md](./.codex_lessons.md)

目的：
- 不只留下 machine event
- 也留下 human-readable lesson

### 4.3 Write-Back Todo 與 Delta Artifact

檔案：
- [continuous_learning.py](./nexus/services/continuous_learning.py)

輸出：
- [.nexus/reports/writeback_todo.json](./.nexus/reports/writeback_todo.json)
- [.nexus/reports/writeback](./.nexus/reports/writeback)

todo 預設目標：
- [.codex_lessons.md](./.codex_lessons.md)
- [INDEX.md](./docs/INDEX.md)
- [MUSE_ENGINE_SPEC_V17.1_HARDENED.md](./MUSE_ENGINE_SPEC_V17.1_HARDENED.md)

delta artifact 類型：
- `*_INDEX.delta.md`
- `*_SPEC.delta.md`

目的：
- 把知識回寫從隱性責任變成顯性待辦

### 4.4 Delivery Status 遞進

檔案：
- [continuous_learning.py](./nexus/services/continuous_learning.py)
- [coordinator.py](./nexus/engine/coordinator.py)
- [pipeline_crystal.py](./nexus/engine/pipeline_crystal.py)

狀態規則：
- 沒有 write-back 義務：`fully_delivered`
- 有 write-back 義務但未完成：`code_done_writeback_pending`
- write-back 完成後：`fully_delivered`

這是本輪最關鍵的治理改變。

### 4.5 Auto-Apply Writeback Deltas

檔案：
- [continuous_learning.py](./nexus/services/continuous_learning.py)

行為：
- `refresh_writeback_status(...)` 在預設情況下會：
  - 讀取 `writeback_todo.json`
  - 找對應 delta artifact
  - 自動把 delta 內容附加到：
    - [INDEX.md](./docs/INDEX.md)
    - [MUSE_ENGINE_SPEC_V17.1_HARDENED.md](./MUSE_ENGINE_SPEC_V17.1_HARDENED.md)
  - 使用 marker 避免重複套用
  - 完成後升級 delivery status
  - 寫入 `.nexus/events/writeback_completion.jsonl`

重要設計：
- `finalize_learning_loop(...)` 本身不會立刻 auto-apply
- 它只會把任務停在 `code_done_writeback_pending`
- 真正 auto-apply 發生在下一次 refresh / startup gate

因此形成明確的兩段式閉環：

1. 先產生 pending
2. 再由系統下一輪自動完成 write-back

## 5. 既有阻塞一併修復

### 5.1 重依賴 fallback

檔案：
- [lewm_predictor.py](./nexus/learning/lewm_predictor.py)
- [vector_cache.py](./nexus/learning/vector_cache.py)
- [vector_rag.py](./nexus/core/vector_rag.py)

修復內容：
- `torch` 缺失時不再 import-time 爆炸
- `lancedb` / `pyarrow` / `SentenceTransformer` 缺失時降級到 JSON fallback

目的：
- 廣域測試與本機開發環境不再被大型可選依賴綁死

### 5.2 CLI 舊預期漂移

檔案：
- [cli_commands_service.py](./nexus/services/cli_commands_service.py)
- [test_cli_commands.py](./tests/test_cli_commands.py)
- [test_coordinator.py](./tests/engine/test_coordinator.py)

修復內容：
- `hud()` 缺失 `time` import 已修
- CLI 測試已對齊現行命令
- coordinator 測試已對齊現行 `NexusEngine` 介面，而非舊版 lazy property / old otel patch 假設

## 6. 驗證結果

已驗證：

- `pytest -q tests/services/test_continuous_learning.py tests/test_cli_commands.py tests/engine/test_coordinator.py`
- `uv run scripts/engine/nexus_cli.py nexus:status --aos`

驗證重點：
- protocol ack / session start event 會生成
- read-only command 不再被 heavy strict CI 卡死
- lesson 會寫入 `.codex_lessons.md`
- `writeback_todo.json` 會生成
- 會先進入 `code_done_writeback_pending`
- 下一次 refresh 會 auto-apply delta
- 最後會自動變成 `fully_delivered`

## 7. 真正完成的閉環

現在的閉環是：

`startup gate -> task execution -> crystallize lesson -> writeback todo -> pending delivery -> startup refresh -> auto-apply docs/spec delta -> fully delivered`

## 8. 仍然存在的限制

### 8.1 Auto-apply 是附加式，不是段落級語義編修

目前只是往文件尾部附加 `Auto Writeback` 區塊。

缺點：
- 文件會膨脹
- 舊正文不會被精確替換
- 可能出現主文過期、附錄正確的雙重真相

### 8.2 `fully_delivered` 仍偏工程完成，不是治理審核完成

現在判斷的是：
- lesson 有寫
- todo 有完成
- delta 有套用

但還沒有做：
- spec content semantic validation
- human governance acceptance
- cross-doc consistency audit

### 8.3 Lesson 結構仍偏扁平

現在 lesson 主要靠 root cause / rejection history。

還缺：
- reusable scope
- negative conditions
- task taxonomy
- evidence chain normalization

### 8.4 學習還沒強力反饋到 planner / repair selector

已經有沉澱，但「學完立刻變聰明」這件事還不夠強。

## 9. 可交接結論

可以把本輪成果交給其他 agent 的結論是：

- 學習閉環已成立
- 不是只有事件寫入
- 而是有 pending / write-back / auto-apply / final delivery 的完整遞進
- 後續 agent 不需要重做閉環骨架，應該直接往治理精度與語義編修升級
