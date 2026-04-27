---
name: nexus-capability-upgrade
description: 用於系統化提升 Nexus 解題能力。聚焦「穿 Nexus vs 不穿 Nexus」可量化對比，透過固定 benchmark、A/B 評測、TDD 漸進調參，提升 solve rate 並維持 report/gate 信任一致性。
version: 2026.04.27
---

# Nexus Capability Upgrade

## 使用時機
- 需要提升 Nexus 的任務完成率，而非只修單一 bug。
- 需要證明「穿 Nexus」比「不穿 Nexus」更好（可量化）。
- 需要避免回報與實作不一致，並將改進納入可回歸流程。

## 不使用時機
- 單檔小修、純文件調整、無需 A/B 對比的任務。
- 沒有固定測試或無法定義完成標準的探索性工作。

## 核心原則
- 先固定評測，再調能力；禁止先改再找指標。
- 完成定義以 `semantic_status=VERIFIED` 為準，非 `status=SUCCESS`。
- 每波只改一個能力面向；每波都要有 TDD 與 A/B 報告。
- Fail-closed：trust mismatch 出現即視為退步。
- Nexus 是戰甲，不是 agent：比較必須是同一模型 bare vs 同一模型穿 Nexus，Nexus 只提供上下文、治理、路由、驗收、自癒與 evidence trail。
- 公開主張必須過 public claim gate：同題同 trial、token measured 足夠、Nexus wearing / 五支柱 / 六階段 / claim verified 達標，否則只能做內部診斷。

## Clean Code / Linus 原則檢核（每波必做）
1. 切小：每波只做一個責任邊界，不跨 2 個以上子系統同時重構。
2. 模組化：新增能力優先放 service 層，避免繼續堆進 `nexus/core/`。
3. 模組解耦：CLI 僅做參數轉發與合約封裝，業務邏輯留在 `nexus/app|services|research`。
4. 關注點分離：路由、修復、證據、門禁、報告分成獨立可測試函式。
5. 可驗證性優先：每個新分支都要有對應測試與可機器化驗收輸出。
6. 向後相容明確：保留 compatibility façade 時，必須有移除條件與截止里程碑。

## 🧬 五位一體能力映射（P/X/D/R/A/C）
- LanceDB（X 偵查）：
  - 目標：提升檢索命中與候選質量，降低 `stage1_no_passing_candidate`。
  - 主要模組：`nexus/core/router.py`, `nexus/research/*`, `nexus/services/*analyzer*`.
- Memory（P 指揮）：
  - 目標：讓歷史修復經驗影響路由與修復策略，而非只做旁路紀錄。
  - 主要模組：`nexus/services/memory.py`, `nexus/core/context_hub.py`, `nexus/research/learn/*`.
- MemPalace（D 審查）：
  - 目標：治理規約在 runtime 真正阻擋，不只是文件存在。
  - 主要模組：`scripts/ops/ci_gate.py`, `nexus/core/gate_evaluator.py`, `nexus/core/hallucination_guard.py`.
- Belief（D/R 決策）：
  - 目標：belief score 影響路由與修復深度，且有可追蹤 rollback 記錄。
  - 主要模組：`nexus/core/belief_engine.py`, `nexus/core/orchestrator.py`, `nexus/core/campaign_general.py`.
- Artifact（A/C 驗收）：
  - 目標：每條工作命令都能輸出可驗證 artifact + semantic contract。
  - 主要模組：`nexus/engine/completion_contract.py`, `scripts/engine/nexus_cli.py`, `.nexus/reports/*`.

## 目前瓶頸（按優先級）
1. 能力差距主要體現在「成本面」而不是「成功率面」：穿 Nexus 成功率已高，但 wall time 開銷仍偏大。
2. `core/` 仍偏胖：路由、belief、orchestration、swarm/drone 邊界尚未完全外推到 service/app。
3. learn/research/swarm 多條路徑雖已合約化，但 phase 級別閉環（P/X/D/R/A/C）仍缺統一 KPI 儀表板。
4. 夜間/高風險策略（hyper/nightshift）雖可用，但調參仍偏手動，缺自動收斂迴路。

## 前置調整（Phase 0）
1. 固定題庫與格式
- 使用固定題庫：`scripts/bench/capability_tasks_v1.json`
- 驗證：
```bash
uv run pytest -q tests/benchmark/test_capability_tasks_schema.py
```

2. 固定評測欄位
- 使用 `scripts/bench/ab_eval.py` 統一比較指標：
  - `solve_rate`
  - `semantic_verified_rate`
  - `avg_duration_sec`
  - `avg_wall_duration_sec`
  - `avg_total_tokens`
  - `avg_model_calls`
  - `avg_attempt_count`
  - `trust_mismatch_rate`
- 驗證：
```bash
uv run pytest -q tests/test_ab_eval_schema.py
```

3. 固定基線命令（A/B）
- A（穿 Nexus）：
```bash
uv run scripts/engine/nexus_cli.py nexus research:auto-flow ...
```
- B（不穿 Nexus）：
```bash
uv run python -c 'from nexus.app.research_flow_service import run_auto_flow; ...'
```
- 建議直接使用統一 runner 產生 A/B 資料：
```bash
uv run scripts/bench/capability_ab_runner.py --max-tasks 6 --difficulty all --timeout-sec 30 --force-flow hyper_sprint
```

## 公開候選 A/B 流程（Gemini bare vs Gemini+Nexus）
使用時機：
- 使用者要知道「Nexus 強在哪、提升多少」。
- 做完 Nexus 優化後，需要比較優化前後成績。
- 需要產出可對外說明的數據與限制。

原則：
- 先跑前測 baseline，再改能力，再用同一題庫/同一模型/同一 timeout 重跑後測。
- 若 Gemini 額度不足，只做靜態修復、unit tests、報告工具，不跑模型 benchmark。
- 異常長耗時要止損：單題超過 600s 或超過設定 timeout 後仍有殘留程序，先修 runner/gateway timeout。
- 不可只挑好看的 row；infra-invalid rows 必須分開列出。

標準 smoke（6 題 x 2 trials）：
```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 \
NEXUS_GEMINI_MODEL_NAME=gemini-3-flash-preview \
NEXUS_DIRECT_GEMINI_MODEL=gemini-3-flash-preview \
NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin \
NEXUS_GATEWAY_COMPACT_PROMPT=1 \
NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 \
NEXUS_BENCH_GATEWAY_TIMEOUT_SEC=90 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_nexus_value_v1.json \
  --task-id-filter nexus-value-gov-001,nexus-value-gov-002,nexus-value-evidence-001,nexus-value-evidence-002,nexus-value-trust-001,nexus-value-trust-002 \
  --max-tasks 6 --difficulty hard --timeout-sec 120 --total-timeout-sec 2400 --stop-loss-sec 2400 \
  --force-flow hyper_sprint --with-nexus-runner subprocess --with-llm-mode all --without-mode gemini \
  --force-learn-slo-ready --neutralize-history --disable-learning-loop --repeat-trials 2 \
  --output-dir .nexus/reports/bench_gemini3flash_get6x2_<tag> \
  --markdown-report auto --progress-log
```

公開 gate 檢查：
- markdown report 的 `Public claim gate` 必須是 `PASS`。
- `hidden_verifier_mode` 必須是 `true`；若不是，該結果只能當容易模式 regression，不能當 Nexus 能力價值證據。
- `Token public-safe claim` 必須是 `YES` 才能談 token/cost。
- Nexus treatment 必須 `Formal treatment valid: N/N (100.0%)`。
- 若 gate fail，結論改成「不可公開引用；列失敗原因與下一步修正」。

後測比較格式：
1. `Before`: 前測 raw JSONL + 指標。
2. `Change`: 本波只改哪個能力邊界。
3. `After`: 後測 raw JSONL + 指標。
4. `Delta`: solve/semantic/trust/wall/tokens/model_calls/Nexus wearing。
5. `Decision`: 保留、回滾、或再優化。

公開候選說法只允許以下形狀：
```text
On a frozen <N>-task benchmark with <T> trials per task, using <same model>,
Gemini + Nexus changed verified delivery from <bare>% to <nexus>%,
changed average wall time by <x>%, changed measured tokens by <y>%,
and preserved trust mismatch at <z>%. Nexus wearing evidence was valid for <n>/<n> rows.
```

## 執行流程（每一波都一樣）
1. Red（先寫失敗測試）
- 對該波能力點新增最小回歸測試（先紅）。

2. Green（最小修正）
- 只改對應邊界（優先 `nexus/app`、`scripts/engine`、`nexus/engine`）。

3. Verify（雙層驗證）
- 跑目標測試 + 真實 CLI smoke：
```bash
uv run pytest -q <targeted tests>
uv run scripts/engine/nexus_cli.py nexus <real command>
```

4. Benchmark（A/B 對比）
- 產出兩組結果檔（jsonl/csv/json）後比較：
```bash
uv run scripts/bench/ab_eval.py --a <without_nexus_file> --b <with_nexus_file> --label-a without --label-b with --output-json
```

5. Gate（信任鏈）
- 每波收尾至少跑：
```bash
uv run scripts/ops/ci_gate.py --dry-run
```
- 若該波修改 `research:auto-flow` 路由，必須加上固定 guard audit 並納入 `REPORT_TRUST_AUDIT_TARGETS`：
```bash
uv run pytest -q tests/engine/test_research_auto_flow_guard_audit.py
```

## 五波能力提升計劃（建議順序）
### Wave 1: Strategy Budget
- 目標：高風險任務自動提升探索深度（candidate/round/parallel）。
- 主要位置：`nexus/app/research_flow_service.py`
- 驗收：
  - `avg_attempt_count`（with）高於（without）
  - `solve_rate` 不下降

### Wave 2: Mutation Quality
- 目標：降低 `stage1_no_passing_candidate`。
- 主要位置：`nexus/research/local_sprint_mutator.py`, `nexus/research/sprint_service.py`
- 驗收：
  - hard bucket `solve_rate` 提升
  - `semantic_failures` 中 stage1 失敗比例下降

### Wave 3: Routing Accuracy
- 目標：hard 任務更準確導向 hyper/nightshift，simple 任務不過度升級。
- 主要位置：`nexus/app/research_flow_service.py`, route policy
- 驗收：
  - hard 題誤路由下降
  - `avg_duration_sec` 不劣化過多
  - `tests/engine/test_research_auto_flow_guard_audit.py` 常駐綠燈

### Wave 4: Semantic Completion
- 目標：所有工作命令統一 semantic completion 判定。
- 主要位置：`nexus/engine/completion_contract.py`, CLI command wrappers
- 驗收：
  - `trust_mismatch_rate == 0`
  - 無 `status=SUCCESS` 但 `semantic_status!=VERIFIED` 的誤判完成

### Wave 5: Bounded Continuation
- 目標：retryable 任務可有界續修，不陷入無限重試。
- 主要位置：research/run continuation sidecar + handoff state
- 驗收：
  - retryable 題 `solve_rate` 再提升
  - retry 次數可追蹤且有上限

## 下一階段長計劃（Wave 6~12）
### Wave 6: Phase KPI 儀表板（P/X/D/R/A/C）
- 目標：六階段全量可觀測，建立每 phase 的成功率/耗時/阻擋原因。
- 變更：
  - 新增 phase 指標聚合器（可先落在 `nexus/research/learn/phase_*_service.py` + reports）。
  - 報告標準化輸出：`phase_metrics.json` + `semantic_failure_topn.json`。
- 驗收：
  - 每輪 A/B 都能看到 phase 分解差異，而不只總體 solve rate。

### Wave 7: LanceDB + Memory 協同路由
- 目標：讓歷史成功修法對當前 route/mutation 有權重影響。
- 變更：
  - `research_flow_service` 增加「prior fix hit」權重欄位。
  - `local_sprint_mutator` 優先採用高命中模式（帶退場機制）。
- 驗收：
  - hard bucket 的首輪命中率上升；
  - `avg_attempt_count` 下降且不犧牲 solve rate。

### Wave 8: MemPalace 規約下沉到命令層
- 目標：所有 mutating 命令統一 enforcement middleware（非各命令各自實作）。
- 變更：
  - 抽出 CLI command middleware：`artifact required`, `semantic gate`, `evidence writeback`。
  - 移除重複檢查碼，降低 CLI 內部重複 shaping。
- 驗收：
  - `test_cli_semantic_contract_audit` 覆蓋面擴大且維護成本下降。

### Wave 9: Belief 驅動 repair budget
- 目標：belief/confidence 直接決定 hyper budget、candidate count、rounds。
- 變更：
  - `build_hyper_execution_profile` 接 belief signal；
  - 低信心走保守補證據，高信心走快速修復。
- 驗收：
  - time/token 效率提升，`trust_mismatch_rate` 維持 0。

### Wave 10: Swarm/Drone 分工閉環
- 目標：swarm 做規劃分派，drone 做局部修復，結果統一回 completion contract。
- 變更：
  - `swarm` / `drone` 報告欄位對齊 `semantic_status` 與 artifact 路徑。
  - phase handoff 補上 machine-readable `handoff_reason`。
- 驗收：
  - `swarm:run` 與 `research:*` 報告格式一致，可納入同一 trust audit。

### Wave 11: NightShift 自動升級與回退
- 目標：符合條件自動升 nightshift，不符合自動回退 hyper/baseline。
- 變更：
  - 集中化升級條件（避免散落在多命令判斷）。
  - 引入「最多 N 輪」保護，防止資源失控。
- 驗收：
  - 高風險任務成功率提升，平均 wall time 增幅受控。

### Wave 12: 能力自動調參（autotune loop）
- 目標：讓 route/mutation/budget 權重可由最近窗口績效自動調整。
- 變更：
  - 以 `scripts/learning/*` 為基礎做 nightly autotune（僅調小範圍參數）。
  - 異常時自動回滾到上一組權重。
- 驗收：
  - 連續 7 天 A/B 指標穩定不退步。

## A/B 實驗矩陣（持續執行）
1. 每日 smoke（6 題）：
```bash
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/capability_tasks_v1.json \
  --difficulty all --max-tasks 6 \
  --with-nexus-runner inprocess \
  --without-mode bare \
  --neutralize-history \
  --output-dir .nexus/reports/bench/daily
```
2. 每次重構後標準（12 題）：
```bash
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/capability_tasks_v1.json \
  --difficulty all --max-tasks 12 \
  --with-nexus-runner inprocess \
  --without-mode bare \
  --neutralize-history \
  --output-dir .nexus/reports/bench/iter
```
3. 每週 full（30 題）：
```bash
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/capability_tasks_v1.json \
  --difficulty all --max-tasks 30 \
  --with-nexus-runner inprocess \
  --without-mode bare \
  --neutralize-history \
  --output-dir .nexus/reports/bench/full30
```
4. 統一評估：
```bash
uv run python scripts/bench/ab_eval.py --a <without_file> --b <with_file> --output-json
```

5. autotune（Wave 12）：
```bash
uv run python scripts/bench/capability_autotune.py \
  --eval-file <ab_eval_json> \
  --tuning-file .nexus/config/capability_tuning.json \
  --apply --output-json
```

6. operations loop（daily/iter/weekly 一鍵）：
```bash
uv run python scripts/bench/capability_ops_loop.py --profile daily --output-json
uv run python scripts/bench/capability_ops_loop.py --profile iter --apply-autotune --output-json
uv run python scripts/bench/capability_ops_loop.py --profile weekly --apply-autotune --output-json
```

## TODO 狀態格式（每完成一項就更新）
- `[ ] Wave-N / Item`：未開始
- `[~] Wave-N / Item`：進行中（附當前測試）
- `[x] Wave-N / Item`：已完成（附 A/B delta + gate 結果）

範例：
- `[x] Wave-8 / CLI semantic middleware`  
  evidence: `pytest ... passed`, `ci_gate --dry-run PASS`, `solve_rate_delta=+0.18`

## 目前進度（2026-04-23）
- `[x] Wave-6 / Phase KPI dashboard payload + CLI command (learn:phase-kpi)`
- `[x] Wave-7 / prior-fix 記憶命中權重（auto findings query + prior_fix_hits）`
- `[x] Wave-8 / learn mutating commands semantic middleware 去重`
- `[x] Wave-9 / belief confidence 驅動 hyper budget`
- `[x] Wave-10 / drone evolution crystal 對齊 semantic contract`
- `[x] Wave-11 / nightshift recommendation signal（history/stage1 fail）`
- `[x] Wave-12 / capability autotune script（含 apply + backup）`
- `[x] Wave-13 / token-model observability 全鏈路打通（sprint_service -> auto_flow -> ab_runner -> ab_eval）`
  evidence: `tests/research/test_sprint_service.py`, `tests/benchmark/test_capability_ab_runner.py`, `tests/test_ab_eval_schema.py`
- `[x] Wave-14 / baseline probe reuse（early shortcut 不重跑 apply）`
  evidence: `tests/engine/test_research_auto_flow_guard_audit.py::test_early_baseline_shortcut_reuses_probe_result_without_second_generation`
- `[x] Wave-15 / hard first-pass 命中提升（prior-fix 加速 + mutator 高風險關鍵字擴充 + prior-art 汙染隔離）`
  evidence: `tests/app/test_research_flow_service.py::test_build_hyper_execution_profile_accelerates_first_pass_for_strong_prior_hits`, `tests/app/test_research_flow_service.py::test_baseline_local_mutation_ignores_prior_art_keyword_pollution`, `tests/research/test_local_mutator_safety.py::test_compute_backoff_websocket_high_risk_uses_conservative_patch`
  benchmark: `ops_loop_iter_1776882767.json` 與 `ops_loop_iter_1776882809.json`，with-nexus `solve_rate=1.0`、hard-003/004 由 FAILED -> VERIFIED。

## 固定驗證矩陣（必跑）
1. 可信回報與語義合約矩陣：
```bash
uv run pytest -q \
  tests/engine/test_completion_contract.py \
  tests/engine/test_completion_enforcer.py \
  tests/engine/test_direct_mode_semantic_audit.py \
  tests/engine/test_cli_semantic_contract_audit.py \
  tests/engine/test_cli_work_path_audit.py \
  tests/engine/test_cli_artifact_gate_audit.py \
  tests/engine/test_research_auto_flow_guard_audit.py \
  tests/engine/test_delegate_completion_contract.py \
  tests/services/test_cli_commands_service_runtime.py \
  tests/engine/test_swarm_command_runtime.py \
  tests/test_cli_learn_mode.py
```

2. 30 題全量 A/B（能力 vs 成本）：
```bash
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/capability_tasks_v1.json \
  --difficulty all --max-tasks 30 \
  --with-nexus-runner inprocess \
  --without-mode bare \
  --neutralize-history \
  --output-dir .nexus/reports/bench/full30
uv run python scripts/bench/ab_eval.py \
  --a .nexus/reports/bench/full30/with_nexus_<ts>.jsonl \
  --b .nexus/reports/bench/full30/without_nexus_<ts>.jsonl \
  --output-json
```

3. Gate 閉環：
```bash
uv run scripts/ops/ci_gate.py --dry-run
```

## Go/No-Go 門檻
- 相較 without-nexus，with-nexus 至少達成：
  - `solve_rate_delta >= +0.15`
  - `semantic_verified_rate_delta >= +0.15`
  - `trust_mismatch_rate == 0`
  - `avg_duration_sec_delta <= +20%`（核心執行時間，可依情況放寬）
  - `avg_wall_duration_sec_delta` 用來追蹤啟動/包裝成本，不作為能力退步唯一判準
  - `avg_total_tokens_delta <= +25%`（若 solve rate 顯著提升可討論放寬）

## 失敗處理
- 任一波若 `trust_mismatch_rate` 上升：立即回滾該波。
- 任一波若 `ci_gate --dry-run` fail：先修 gate/trust，再談能力優化。
- 任一波若 only test-green but CLI-smoke-red：分類 `execution seam defect`，不得宣稱完成。

## 交付格式
- `Baseline`: 本波前 A/B 指標
- `Change`: 變更範圍（檔案與能力點）
- `Result`: 本波後 A/B 指標
- `Evidence`: 命令與輸出（pytest/CLI/ci_gate/ab_eval）
- `Decision`: 保留 / 回滾
- `Next Wave`: 下一波計劃
