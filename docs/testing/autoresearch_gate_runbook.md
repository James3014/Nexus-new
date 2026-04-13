# AutoResearch 執行與守門手冊 (v1.0)

## 0. 單一產品入口
- 本地執行：
  - `uv run scripts/engine/nexus_cli.py nexus research:run --run-id local-smoke --scope docs/research/autoresearch_control_plane_spec.md --dry-run --report-file .nexus/reports/research/local-smoke.json`
  - `uv run scripts/engine/nexus_cli.py nexus research:route --task-desc \"fix flaky timeout in websocket\" --candidate-count 3 --root-cause-confidence 0.7 --output-json`
  - `uv run scripts/engine/nexus_cli.py nexus research:benchmark --manifest-file /tmp/research-benchmark-manifest.json --report-file .nexus/reports/research/benchmark-report.json`
  - `uv run scripts/engine/nexus_cli.py nexus research:benchmark --manifest-file /tmp/research-benchmark-ab.json --mode ab --ab-trials 5 --report-file .nexus/reports/research/benchmark-ab-report.json`
  - `uv run scripts/engine/nexus_cli.py nexus research:sprint --task \"Fix deadlock in transfer\" --target-file nexus/demo/bank_transfer.py --test-file tests/demo/test_concurrency_hard.py --candidate-count 1 --max-rounds 1 --no-llm-mode --safe-mode`
  - `uv run scripts/engine/nexus_cli.py nexus research:benchmark --manifest-file docs/research/research_benchmark_ab_template.json --mode ab --ab-trials 5 --report-file .nexus/reports/research/benchmark-ab-report.json`
  - `uv run scripts/engine/nexus_cli.py nexus research:auto-flow --task-desc \"Fix deadlock in transfer\" --target-file nexus/demo/bank_transfer_bench_ab_small.py --test-file tests/demo/test_concurrency_bench_ab_small.py --task-type bug --candidate-count 1 --root-cause-confidence 0.95 --output-json`
  - `uv run scripts/engine/nexus_cli.py run-bug \"Fix deadlock in transfer\" --auto-flow --target-file nexus/demo/bank_transfer_bench_ab_small.py --test-file tests/demo/test_concurrency_bench_ab_small.py`
- 報表路徑：
  - `.nexus/reports/research/*.json`

## 1. 啟動流程
1. **定義範圍**: 在任務描述或配置中明確 `modifiable_scope` (建議僅限研究用模組)。
2. **配置評估**: 確保 `UnifiedEvaluator` 已配置固定 Seeds 與 Budget。
3. **執行研究**: 使用群集指令啟動 Phase R (Research)。

## 2. 物理守門規則

| 情境 | 行動 | 理由 |
| :--- | :--- | :--- |
| **指標提升 > 10%** | **PROMOTE** | 通過多 Seeds 驗證且具備統計意義。 |
| **指標退化或門檻未過** | **SAFE ROLLBACK** | 觸發 `SelectorRollback.restore_scope` 回復至實驗前狀態。 |
| **非法檔案寫入** | **ABORT** | `ExperimentScheduler` 將主動阻斷超出 Scope 的寫入嘗試。 |
| **資源耗盡** | **HUMAN TAKEOVER** | 超出 Budget 時暫停，由工程師評估是否繼續。 |

## 3. 失敗排查與清理
- **磁碟空間**: 可調高 `--retain-last-n` 的清理強度，或手動檢查 `.nexus/experiments` / `.nexus/backups`。
- **回滾手動檢查**: 若自動回滾失敗，可檢查 `.nexus/backups/[CandidateID]` 進行手動恢復。
- **併發控制**: 禁止在同一工作區並發執行多個研究實驗。

## 4. CI 守門
- PR smoke:
  - Workflow: `.github/workflows/research-smoke.yml`
  - 輸出 artifact: `pr-smoke-report.json`
- Nightly gate:
  - Workflow: `.github/workflows/research-nightly.yml`
  - 輸出 artifact: `nightly-report.json`

## 5. Hyper-Sprint 報表欄位（P3）
- 預設輸出：`.nexus/reports/research/sprint-report.json`
- 核心欄位：
  - `status`, `reason`, `final_score`, `winner_source`
  - `attempt_count`, `model_calls`, `quota_backoffs`, `test_timeouts`
  - `error_codes[]`, `candidates[]`
