# AutoResearch 控制平面規格 (v1.0)
## 1. 物理範圍契約 (Modifiable Scope)
- **定義**: 每次實驗前必須宣告 `modifiable_scope` (List of Paths)。
- **硬化**: `ExperimentScheduler` 將在檔案寫入前執行路徑校核，超出範圍則阻斷。
## 2. 評估執行契約 (Eval Contract)
- **Seed 鎖定**: 強制使用 `FIXED_SEEDS = [42, 1337, 2026]` 進行多輪驗收。
- **Budget 鎖定**: 單次實驗總成本 (LLM Tokens/Time) 不得超過 `budget_limit`。
## 3. 候選生命週期 (Candidate Lifecycle)
- **狀態**: `created` -> `running` -> `evaluated` -> `promoted/rejected`。
- **淘汰**: 低於基線評分或觸發 Regression 者自動進入 Rejected 狀態。
## 4. 人機接管 (Human Takeover)
- **中斷點**: 實驗停滯或指標異常偏移。
- **Quest Repo**: 每次實驗自動建立 `.nexus/experiments/[ID]` 作為 Quest 工作目錄，包含 diff 與 log。

## 5. 產品入口 (`nexus research:run`)
- **入口命令**:
  - `uv run scripts/engine/nexus_cli.py nexus research:run ...`
  - `uv run scripts/engine/nexus_cli.py nexus research:route --task-desc \"...\" ...`
  - `uv run scripts/engine/nexus_cli.py nexus research:benchmark --manifest-file ...`
- **固定報表**: 預設輸出 `.nexus/reports/research/report.json`
- **Schema v1.0** (machine-readable):
  - `schema_version`
  - `run_id`, `status`, `winner`
  - `top_k[]`: `candidate_id`, `average_score`, `passed_gate`
  - `elimination_matrix[]`: `candidate_id`, `reason_codes[]`
  - `cost_curve`: `estimated_cost_per_round`, `total_cost`, `budget_limit`, `budget_remaining`
  - `decision_log[]`, `rejected_reasons[]`, `rollback_trace[]`
  - `budget_summary`, `timestamps`, `candidate`

## 6. 治理參數 (P1-A)
- `--candidate-count` (multi-candidate evaluate/select)
- `--max-parallel`
- `--max-retries`
- `--timeout-sec`
- `--retain-last-n`
- `--disk-watermark-gb`
- **執行層落地**:
  - `max_parallel/max_retries/timeout_sec` 已接入 `UnifiedEvaluator.evaluate(...)` 實際執行器。
  - `retain-last-n` 已接入清理執行器（reports / experiments / backups）。
  - `research:route` 已接入 `ResearchPolicy.route(...)`，並可透過 findings 命中調整 `root_cause_confidence`。

## 7. CI/Nightly Gate (P1-C/P1-D)
- PR smoke: `.github/workflows/research-smoke.yml`
- Nightly: `.github/workflows/research-nightly.yml`

## 8. Hyper-Sprint Service (P1-P3 Refactor)
- `research:sprint` 已改為薄 CLI，核心流程下沉至 `nexus/research/sprint_service.py`。
- 關注點分離：
  - `SprintConfig` / `SprintResult` / `CandidateEval`（資料模型）
  - `LocalCandidateGenerator` / `LLMCandidateGenerator`（候選生成）
  - `SprintExecutor`（sandbox + pytest 驗證）
  - `promote_patch_to_branch`（交付）
- 統一機器可讀報表（預設 `.nexus/reports/research/sprint-report.json`）：
  - `status`, `reason`, `final_score`, `winner_source`
  - `attempt_count`, `model_calls`, `quota_backoffs`, `test_timeouts`, `error_codes[]`
  - `candidates[]`（每個候選的 score/error/source/elapsed）
