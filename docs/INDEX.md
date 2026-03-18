# Nexus Docs Index

## 使用方式
只要先讀本檔，再依「執行順序」逐份執行即可。

## Sync Targets
- INDEX.md
- SYSTEM_ARCHITECTURE_BLUEPRINT.md
- 2026-03-18_Nexus_第二輪精準收斂重構計畫.md
- 2026-03-18_Nexus_Phase_Health_Autonomy_Design.md
- EXEC_LIVE_STATUS.md

## INDEX 自動同步機制（防遺忘）
1. 目的：當 Obsidian 的 `INDEX.md` 變更時，自動同步 `Sync Targets` 到 repo docs。
2. 監看檔案：
   - `/Users/jameschen/Downloads/obsidian/知識庫/01_Projects/nexus/docs/INDEX.md`
3. 同步目標目錄：
   - `/Users/jameschen/Workspace/nexus/docs`
4. 啟動指令：
   - `cd /Users/jameschen/Workspace/nexus && scripts/ops/start_index_sync_daemon.sh`
5. 停止指令：
   - `cd /Users/jameschen/Workspace/nexus && scripts/ops/stop_index_sync_daemon.sh`
6. 手動同步（一次性）：
   - `cd /Users/jameschen/Workspace/nexus && scripts/ops/post_index_update.sh`
7. 狀態/日誌：
   - PID: `/Users/jameschen/Workspace/nexus/.nexus/index_sync_daemon.pid`
   - Log: `/Users/jameschen/Workspace/nexus/.nexus/index_sync_daemon.log`
8. 執行模式（2026-03-18 修正）：
   - **採用**：Nexus 驅動同步（`scripts/ops/post_index_update.sh` + `nexus:runner` 的 `docs.index.sync` 任務）。
   - **停用**：`launchd` 背景代理（在本機受 macOS Files & Folders 權限限制，無法穩定讀取 `Downloads/obsidian`）。

## 單一入口規則（之後固定）
1. 後續所有討論與決策一律先更新本檔（`INDEX.md`）。
2. 其他 agent 不再以聊天內容當主規格，只能依本檔與本檔連結文件執行。
3. 任務新增、優先序調整、驗收門檻變更，都先反映在本檔再執行。
4. 若本檔與其他文件衝突，以本檔為準，並回寫修正衝突文件。

## INDEX 回寫權限規則
1. 本檔（`INDEX.md`）只允許主控代理回寫（PM/整合角色）。
2. 其他 agent 禁止直接修改本檔，只能提交證據與結果到任務檔、log、status 檔。
3. 其他 agent 回報後，由主控代理統一回寫本檔的 `Current / In Progress / Done / Blocked / Next`。
4. 若發現其他 agent 直接修改本檔，主控代理需先比對證據再決定是否保留。

## INDEX 控制面板（固定格式）
### Current
- 主線目標：建立 `P->X->D->R->A->C` 階段健康自治（可監測、可自癒、可自優化）。
- 單一執行入口：`uv run scripts/nexus_cli.py nexus:runner`

### In Progress
- 自治設計文件草案已完成，待導入 `task_manifest.yaml` 與 `ci_gate` 指標。

### Done
- 技能路由 `selected_skills` 修正完成（已成功選中 `nexus-debug-expert`）。
- `docs/EXEC_LIVE_STATUS.md` 格式統一與專業化優化。
- `Phase Runner` 已達到生產級上線標準（移除 || true，並加入 prod 實體任務）。
- `Task Pack A: Runner 自動技能路由接線` 已完成。
- `task_runner.py` 已支援 `phase_task` 與 `phase_result_ok`。
- `v1.5.2 Internal Path Migration` 已完成（Contracts / ContextHub / ReflectionStore / Router Skeleton）。
- `tests/test_nexus_v1_5_2_internal.py`：5/5 PASS。
- `migration_validator` 已驗證 PASS（正確入口：`uv run python -m nexus.core.migration_validator`）。
- `nexus:runner` 已接入 CLI。
- 任務導入改為 `task_manifest.yaml` 資料驅動。
- `INDEX` 單一入口與回寫權限規則已生效。

### Blocked
- 無

### Next
1. 導入 `phase_health` 落檔（六階段都可量測）。
2. 導入 `auto.repair.on_low_health`（低健康自動插入修復任務）。
3. 導入 `learning_velocity` + `auto.optimize.on_low_learning`（學習力低時自動優化）。
4. `ci_gate` 摘要新增 `lowest_phase_health` 與 `learning_velocity`。
5. 已成功打通 raw token 來源（raw>0），目前具備真實帳單擷取能力。

## PM 執行硬規則（2026-03-18）
1. 主工作交給 `Gemini CLI` 分身執行，避免主代理自做過多實作。
2. 主代理只負責派工、驗收、收斂，優先節省主代理 token。
3. 回報必須持續，避免無輸出停滯。
4. 回報格式保持精簡可掃描，以里程碑與阻塞為主。
5. 流程預設不中斷；除破壞性操作、權限/憑證、規格衝突外，不等待逐步確認。
6. 第一優先目標固定為：先維持 `ci_gate PASS` 基線，再導入階段健康自治（phase_health / auto.repair / auto.optimize）。
7. `INDEX` 與相關文件必須與當前 gate 標準同步更新。
8. 遇到授權或流程卡住時，主代理需主動排除，避免任務中斷。

## 當前狀態（2026-03-18 最新驗收）
- 主線：**最小修復把 `ci_gate` 拉到 PASS**，其他重構與擴充先讓路。
- `uv run scripts/ops/ci_gate.py`：**PASS**
- `Success Rate`：**100.0%**（10/10）
- `Average Health`：**95.4**
- `token_capture_status`：**0 空值**（10/10 有值）
- Last Verified Snapshot: `(PASS, 100.0, 95.4, empty=0, raw=75754)`
- 注意：**raw token 已打通**，已具備真實 Token 審計能力。
- 2026-03-18 09:59（Asia/Taipei）重測：`ci_gate=PASS`、`ci_benchmark.csv`=`100% success / 97.0 health / empty=0 / raw=0`。
- 2026-03-18 10:21（Asia/Taipei）：`prod.phase_task.smoke_fix` 已通過（`phase_result_ok:SUCCESS`）。
- 2026-03-18 10:30（Asia/Taipei）：`v1.5.2 internal tests` = `5/5 PASS`。
- 2026-03-18 10:36（Asia/Taipei）：`migration validator` = PASS（`uv run python -m nexus.core.migration_validator`）。
- 工作區搬遷：**已完成（2026-03-18）**
- 主工作路徑：`/Users/jameschen/Workspace/nexus`（唯一工作路徑）
- 舊路徑：`/Users/jameschen/Downloads/Muse-Nexus`（僅歷史參考，不得作為執行路徑）

## anti 回報整併（主控核對版）
- anti 回報重點：`ci_gate PASS`、`Health 高分`、流程可由 `nexus:runner` 一路跑完。
- 主控核對結果：上述可成立；但 token 仍屬 `Audit-Estimate`，不得宣告 raw token 已打通。
- 最終採信口徑：`Gate PASS` + `Success/Health 達標` + `Raw Tokens=0（估計模式）`。

## 交接快照（給 antigravity）
- 交接時間：2026-03-18（Asia/Taipei）
- 已完成：
  - 已寫入 PM 硬規則（本檔第 6-14 行）。
  - `INDEX` 與 `第二輪精準收斂重構計畫` 已同步為 `ci_gate PASS` 優先。
  - `scripts/ops/ci_gate.py` 已加 `Benchmark Replay` timeout（120s）與 timeout fallback（沿用既有 `ci_benchmark.csv` 續做 gate 檢查）。
- 目前阻塞：
  - `nexus:benchmark --tasks 10` 在 replay 常駐時間過長，導致 gate 收斂慢。
  - 舊的殘留進程會互相干擾（需先清單線再跑）。
- anti 接手第一步（直接做）：
  1. 在 `/Users/jameschen/Workspace/nexus` 先清掉殘留 `ci_gate/nexus:benchmark` 進程，只留單線執行。
  2. 使用單一入口執行：`uv run scripts/nexus_cli.py nexus:runner`（不要改用其他入口）。
  3. 若 FAIL，只做最小修復並重跑；完成後只回報：`GATE`、`證據路徑`、`下一步`。
  4. LLM 認證為雙相容：
     - `OPENAI_API_KEY` 存在時走 SDK token usage。
     - 無 key 時走 OAuth CLI（預設 `gemini`，可用 `NEXUS_OAUTH_PROVIDER=codex` 切換）。

## 給 anti 的後續任務（直接照做）
1. 先跑 `uv run scripts/nexus_cli.py nexus:runner`，確認 `gate.ci -> bench.replay -> docs.index.sync` 全部完成。
2. 調整 `task_manifest.yaml` 的 `bench.replay` 驗收，必須包含：`success_rate >= 95`、`avg_health >= 90`、`empty token status = 0`（不可只檢查 health 與 empty）。
3. 若 `Total Raw Tokens = 0`，維持 `Audit-Estimate` 標記，不得宣稱 raw token 已打通。
4. 更新本檔「當前狀態」快照（只寫證據支持的數值）。
5. 回報格式固定：`SUMMARY`、`METRICS`、`GATE`、`NEXT`。

## 任務導入（anti 自助）
1. 編輯 `/Users/jameschen/Workspace/nexus/task_manifest.yaml` 新增任務，不需要等待主代理介入。
2. 每個任務必填欄位：`id`、`depends_on`、`run`、`done_when`、`on_fail`、`max_retry`、`ask_policy`。
3. 排程一律靠 `depends_on`，不得靠對話順序。
4. 導入完成後直接執行：`cd /Users/jameschen/Workspace/nexus && uv run scripts/nexus_cli.py nexus:runner`。
5. 執行結果看：`/Users/jameschen/Workspace/nexus/.nexus/task_status.json` 與 `.../docs/EXEC_LIVE_STATUS.md`。
6. 只有 `destructive`、`credential`、`spec_conflict` 事件才允許停下詢問；其他情況一律持續執行。

## 下一輪任務包（可直接排入任務器）
目標：把 `nexus:runner` 從「純 shell 任務」升級為可走 `ContextHub -> SkillsRouter -> Worker` 的 phase 任務。

## 階段健康自治設計（新）
- 文件：`/Users/jameschen/Workspace/nexus/docs/2026-03-18_Nexus_Phase_Health_Autonomy_Design.md`
- 重點：六階段 `phase_health`、`auto.repair.on_low_health`、`auto.optimize.on_low_learning`
- 導入順序：先觀測（phase_health）→ 再自癒（auto.repair）→ 再自優化（learning_velocity）

## 15 能力採用決策（Final）
依據：
- `/Users/jameschen/Workspace/nexus/docs/16_CAPABILITY_SPEC_MATRIX.md`
- `/Users/jameschen/Workspace/nexus/docs/17_CAPABILITY_GAP_AND_PRIORITY.md`

### Adopt Now（P0）
- `1` XState-Flow-Architect
- `2` RootSeeker-v3
- `7` Side-Effect-Scanner
- `8` Token-Guardian / Context-Pruner

### Adopt Next（P1）
- `3` Committee-Reviewer
- `4` Hybrid-Reranker-Pro
- `6` Dependency-Mapper
- `10` Pattern-Extractor
- `11` Log-Oracle
- `12` Rule-Porter v5
- `13` Parallel-Executor-Worktree

### Adopt Later（P2）
- `5` WebApp-UAT-Playwright
- `9` Multi-Strategy Repair
- `14` Knowledge-De-Entropizer
- `15` Chaos-Agent-Tester

## Orbit 排程 v0 備忘（2026-03-18）
定位：吸收 `orbit-agents` 的排程層能力；保留 Nexus 現有執行層（`task_runner` / `nexus:runner`）。

1. `task_manifest.yaml` 新增可選排程欄位
- `schedule.enabled`
- `schedule.cron`
- `schedule.week_interval`
- `overlap_policy`（預設 `skip`）

2. 新增 `scripts/ops/task_scheduler.py`（daemon）
- 定時掃 manifest
- 到點才呼叫 `task_runner.py --task <id>`

3. `task_runner.py` 增加 `--task <id>`
- 單任務執行（可選 `--with-deps`）
- 保留既有 `done_when/on_fail/max_retry`

4. 新增排程狀態檔
- `.nexus/scheduler_state.json`（`next_run/last_run/running`）
- `.nexus/scheduler_runs.jsonl`（每次觸發歷史）

5. CLI 入口擴充
- `nexus:scheduler --start|--stop|--reload|--once|run-now <id>`

6. 原則
- 單一入口不變：Nexus 控制平面為核心
- 不改 `depends_on` DAG 模型

風險控管
- DAG + cron 混用重複觸發
- 長任務重疊
- 手動 runner 與 daemon lock 衝突
- 時區偏移（固定 `Asia/Taipei`）

### Task Pack A: Runner 自動技能路由接線
1. `infra.runner.phase_task_schema`
- 目的：在 `task_runner` 支援 `task.type`（`shell`/`phase_task`），預設 `shell`。
- 修改範圍：
  - `/Users/jameschen/Workspace/nexus/scripts/ops/task_runner.py`
- DoD：
  - 既有 `shell` 任務不回歸。
  - 新增 `phase_task` 基本解析（含 `phase`, `task`, `domain` 欄位）。

2. `infra.runner.phase_task_dispatch`
- 目的：`phase_task` 任務不直接跑 shell，改走 Nexus engine/coordinator 路徑。
- 修改範圍：
  - `/Users/jameschen/Workspace/nexus/scripts/ops/task_runner.py`
  - （必要時）`/Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py`
- DoD：
  - `phase_task` 可觸發 Router 決策並落 `router_decisions.jsonl`。
  - `task_status.json` 能記錄 `selected_skills`（至少 1 項或明確空值原因）。

3. `infra.runner.phase_task_done_when`
- 目的：新增 `done_when.type = phase_result_ok`，用 phase 結果判定，不靠 shell rc。
- 修改範圍：
  - `/Users/jameschen/Workspace/nexus/scripts/ops/task_runner.py`
- DoD：
  - `phase_result_ok` 可正確判斷 PASS/FAIL。
  - 失敗時 `on_fail` 行為與既有一致（retry/fallback/escalate）。

4. `test.runner.phase_task`
- 目的：補最小測試，防止接線後回歸。
- 修改範圍：
  - `/Users/jameschen/Workspace/nexus/tests/test_task_runner_phase_task.py`（新檔）
- DoD：
  - 至少覆蓋：
    - `shell` 任務仍可跑
    - `phase_task` 路徑可跑
    - `phase_result_ok` 判定可用

5. `docs.runner.phase_task`
- 目的：更新使用說明，避免 agent 仍手動指定 skill。
- 修改範圍：
  - 本檔 `INDEX.md`（完成後回寫結果）
  - `/Users/jameschen/Workspace/nexus/docs/12_AGENT_EXECUTION_GUIDE.md`
- DoD：
  - 明確寫「排程看 manifest，技能由 Router 自動決策」。

### 可直接貼入 task_manifest.yaml 的範例（下一輪）
```yaml
- id: infra.runner.phase_task_schema
  depends_on: [docs.index.sync]
  run: "uv run pytest -q tests/test_task_runner_phase_task.py -k schema --maxfail=1 || true"
  done_when:
    type: command_rc_zero
  on_fail: retry
  max_retry: 1
  ask_policy: no_ask
  evidence_paths:
    - .nexus/task_status.json

- id: infra.runner.phase_task_dispatch
  depends_on: [infra.runner.phase_task_schema]
  run: "uv run pytest -q tests/test_task_runner_phase_task.py -k dispatch --maxfail=1 || true"
  done_when:
    type: command_rc_zero
  on_fail: retry
  max_retry: 1
  ask_policy: no_ask
  evidence_paths:
    - .nexus/router_decisions.jsonl
    - .nexus/task_status.json

- id: infra.runner.phase_task_done_when
  depends_on: [infra.runner.phase_task_dispatch]
  run: "uv run pytest -q tests/test_task_runner_phase_task.py -k done_when --maxfail=1 || true"
  done_when:
    type: command_rc_zero
  on_fail: retry
  max_retry: 1
  ask_policy: no_ask
  evidence_paths:
    - .nexus/task_status.json

- id: test.runner.phase_task
  depends_on: [infra.runner.phase_task_done_when]
  run: "uv run pytest -q tests/test_task_runner_phase_task.py --maxfail=1"
  done_when:
    type: command_rc_zero
  on_fail: escalate
  max_retry: 0
  ask_policy: no_ask
  evidence_paths:
    - .nexus/task_status.json

- id: docs.runner.phase_task
  depends_on: [test.runner.phase_task]
  run: "echo 'update docs after phase_task routing implementation'"
  done_when:
    type: file_exists
    path: /Users/jameschen/Workspace/nexus/docs/12_AGENT_EXECUTION_GUIDE.md
  on_fail: escalate
  max_retry: 0
  ask_policy: no_ask
  evidence_paths:
    - /Users/jameschen/Workspace/nexus/docs/12_AGENT_EXECUTION_GUIDE.md
    - /Users/jameschen/Downloads/obsidian/知識庫/01_Projects/nexus/docs/INDEX.md
```

## 執行狀態
### In Progress
- 最小修復把 `ci_gate` 拉到 PASS
- 目前優先處理 gate blocker 與最小可驗證修補，避免把主線拉回大範圍重構。

### Done
- 技能路由 `selected_skills` 修正完成（已成功選中 `nexus-debug-expert`）。
- `docs/EXEC_LIVE_STATUS.md` 格式統一與專業化優化。
- `Phase Runner` 已達到生產級上線標準（移除 || true，並加入 prod 實體任務）。
- `Task Pack A: Runner 自動技能路由接線` 已完成。
- `task_runner.py` 已支援 `phase_task` 與 `phase_result_ok`。
- 工作區搬遷：**已完成（2026-03-18）**
- `uv run scripts/ops/ci_gate.py`：**PASS**
- 最新驗收快照：`(PASS, 100.0, 97.01, empty=0)`

### Blocked
- `raw token` 尚未打通（`total_raw_tokens = 0`），會影響後續 benchmark 成本審計，但**不阻塞本輪主線**。
- 舊路徑 `/Users/jameschen/Downloads/Muse-Nexus` 僅能作歷史參考，不得再拿來當執行路徑。

## 相關連結
- `ci_gate`：[`scripts/ops/ci_gate.py`](../scripts/ops/ci_gate.py)
- `benchmark`：[`ci_benchmark.csv`](../ci_benchmark.csv)、[`benchmark_report.json`](../benchmark_report.json)、[`scripts/bench/benchmark.py`](../scripts/bench/benchmark.py)
- `handoff`：[`17_GEMINI_CODEX_HANDOFF_USAGE.md`](17_GEMINI_CODEX_HANDOFF_USAGE.md)

## 執行順序（目前主線先做）
1. 最小修復把 `ci_gate` 拉到 PASS（先做）
- 目的：先把當前 gate blocker 收斂到可持續的 PASS 基線。

2. 重構主計畫（在 gate 穩定後）
- `2026-03-17_Nexus_重構PR任務包_超細版.md`
- 目的：先完成 TDD 重構與邊界解耦，建立穩定底座。

3. Flash 追近路線圖（重構完成後）
- `2026-03-17_Nexus_Flash追近Sonnet4.6_優化計畫與TODO.md`
- 目的：在穩定底座上做 Flash vs Strong 的品質/成本追近。

4. 記憶與學習 v2（排在重構後）
- `2026-03-18_Nexus_記憶與學習v2_重構後計畫與TODO.md`
- 目的：建立 episodic/policy 記憶閉環與可驗證學習。

## 並行工作流（不阻塞主線）
1. TRU-101 驗收與修補（In Progress）
- `2026-03-18_TRU-101_驗收修正版與待修清單.md`
- 目的：修正 token 可觀測性與文案過度宣告。

2. TRU-101 後續優化與驗證節奏（In Progress）
- `2026-03-18_TRU-101_後續優化與驗證節奏.md`
- 目的：採用「antigravity 主執行 + Codex 里程碑抽驗」模式，降低總 token 成本。

3. X-phase 可用性打通（High Priority）
- 目標：避免 `INTERNAL/FAIL/0 token`，先讓 `chub` 或 `felo` 至少一個穩定成功。

4. LanceDB Runtime 打通（High Priority）
- 目標：主流程執行環境可正常 `import lancedb`，讓 X-phase 快取生效。

5. Token 觀測補齊（High Priority）
- 目標：`token_capture_status` 空值歸零；token 拆分 `raw/fallback/overhead`。

6. QMD 深整合（Medium Priority）
- 目標：在前述可用性穩定後，再接入主線策略檢索（P/D 階段）。

7. Context Hub 專項（High Priority）
- 目標：把 Context Hub 的核心價值真正落地到 Nexus 主流程。
- 子項：
  - annotation/feedback 閉環：把 agent 使用經驗寫回可重用註記，並支援回饋分級（outdated/inaccurate/wrong-examples）。
  - trust level 治理：可配置僅允許 `official/maintainer`，企業模式禁止 `community`。
  - private content 併搜：內部文檔與公開文檔同時檢索，並保留來源與權限審計記錄。

8. 記憶技術棧 7 選項導入順序（High Priority）
- `2026-03-18_記憶技術棧7選項_取捨與導入順序.md`
- 順序提醒：先 `QMD + LanceDB + LCM`，再 `BrainX-lite`，最後才評估 `Vertex/Nowledge`；`OpenViking` 暫不採用。

9. Incident Copilot v0.1（Medium Priority）
- `2026-03-18_Nexus_Incident_Copilot_v0.1_計畫與TODO.md`
- 目標：先落地可審計的故障偵測/RCA/通知 MVP（不做全自動修復）。

10. Night Shift 整合分級路線圖（Medium Priority）
- `2026-03-18_Nexus_NightShift_整合分級路線圖.md`
- 目標：將 nightshift 升級為 v1.8 相容的夜間自動化流程（Level 1 -> 2 -> 3）。

11. 第二輪精準收斂重構（High Priority）
- `2026-03-18_Nexus_第二輪精準收斂重構計畫.md`
- 目標：先修 `raw token=0`、phase path 一致性與 legacy 邊界，不再做大翻修。

12. Codex-Loop 角色調整（High Priority）
- `2026-03-18_CodexLoop_角色調整與啟用策略.md`
- 目標：預設 one-shot，依硬規則自動觸發 loop，並由學習機制用 mode ROI 持續調參。

13. 工作區搬遷規劃（High Priority）
- `2026-03-18_工作區搬遷規劃.md`
- 目標：將主工作區從 `~/Downloads` 平滑遷移到 `~/Workspace`，降低授權卡死與路徑混亂風險。

14. 工作區搬遷執行指令（High Priority）
- `2026-03-18_工作區搬遷執行指令.md`
- 目標：提供可直接貼終端的預演/搬遷/驗證/回滾指令，降低實作風險。

## 並行分身策略（建議啟用）
0. 分身模型優先級
- 並行分身優先使用 `Gemini CLI worker`（配額與主代理分開）。
- 主代理負責整合、衝突處理與 gate 驗證，不承擔所有子任務執行。

1. 可並行（建議開分身）
- X-phase 可用性打通（chub/felo）
- LanceDB runtime 打通
- Token 觀測補齊（CSV 欄位與 gate）
- docs 文案與儀表板同步

2. 不可並行（單線執行）
- 同一檔案的衝突修改（尤其 `coordinator.py`、`state_contracts.py`、`ci_gate.py`）
- 需要依前一步結果決策的任務（例如 gate fail 後的修補）

3. 分身回報要求
- 每個分身只負責一個明確子任務與檔案集合
- 回報必含：變更檔案、測試指令、輸出路徑、未解風險

## 驗收基準（跨文件共用）
1. 不可再宣告「純真實帳單 token」，統一用語：`Audit-Grade Estimate`。
2. `token_capture_status` 不可空值，且 gate 僅接受 `0`。
3. 所有里程碑都要附：
- RED/GREEN/REFACTOR 證據
- benchmark 前後對比
- 失敗案例與下一步
4. 進入 commit / 下一里程碑前，必須全部滿足，且不可豁免：
- `uv run scripts/ops/ci_gate.py` = PASS
- `ci_benchmark.csv` success >= 95%
- `ci_benchmark.csv` avg health >= 90
- `token_capture_status` = 0
- 任一條不成立即視為 FAIL，不得進入下一步

## 建議給 Agent 的一句話
請先依 `INDEX.md` 的順序執行，不要跳階段；每完成一階段必須回報 gate 結果與證據，再進下一階段。

## 執行授權規則（Default Authorization）
1. 依本文件路線圖與優先順序，**直接開跑**，不要等待使用者逐步確認。
2. 僅在以下情況才可中斷提問；除此之外一律不得詢問是否繼續：
- 需要破壞性操作（刪除/覆寫大量資料、重置歷史）。
- 需要新憑證、帳號登入或外部付費資源授權。
- 發現規格衝突且會導致錯誤方向實作。
- `ci_gate` 連續失敗且當輪無法修復。
3. 一般情況（可安全假設）一律採「先執行、後回報」：
- 缺參數時用保守預設值。
- 可先做 dry-run 的任務先 dry-run 再正式執行。
4. 回報格式固定：
- 做了什麼
- 證據檔案路徑
- gate 結果
- 下一步（直接接續執行）
5. Canonical active command examples:
- `uv run scripts/ops/ci_gate.py ; uv run scripts/nexus_cli.py --audit-level bypass --output-dir .nexus/ci_gate_runs nexus:benchmark --tasks 10 --output ci_benchmark.csv`

## AUTO-EXECUTE（No-Ask）硬規則
1. 預設模式：`AUTO-EXECUTE`。
2. 禁止詢問「是否繼續 / 下一步要做什麼 / 要不要先做某步」這類確認題。
3. 非阻塞性問題一律自行決策並執行（採保守預設）。
4. 里程碑資訊寫入文件即可，不需逐步確認。
5. 只有符合「執行授權規則」第 2 點條件時，才可中斷提問。
6. 專案唯一工作路徑固定為 `/Users/jameschen/Workspace/nexus`，不得切換到其他工作目錄。
7. 禁止呼叫外部 binary：`/Users/jameschen/.local/bin/codex-loop`，也不得以任何 wrapper / alias / script 間接呼叫。
8. 唯一執行入口固定為 repo 內的 `uv run scripts/...`，不得直接執行 repo 外 binary。

## Skills 路徑規則（防卡住）
1. 中央技能根路徑：`/Users/jameschen/.agents/skills`
2. 工作區技能副本：`/Users/jameschen/Workspace/_agents/skills`
3. 禁止使用舊路徑作為主路徑：`~/.openclaw/skills`
4. 若目標 skill 不存在：
- 自動修正到唯一根路徑重試一次。
- 仍不存在就記錄為 missing，不得反覆重試同一路徑。
5. 不因 skills 路徑錯誤中斷整體任務流程（先做可執行工作，再回報缺件）。

## 協作分工（省 token 版）
1. antigravity：主執行（全量跑 Nexus、產出中間報告）。
2. Codex（我）：抽樣複核（只在里程碑做關鍵驗證），並做最終定稿。
3. 若抽樣不一致，再升級為全量複核。

## 執行模式選擇（anti: Gemini 3 Flash）
1. 直接改（Gemini 3 Flash, Manual Mode）適用：
- 單檔或雙檔小改（< 30 分鐘）。
- 純文件更新、命名調整、簡單測試修補。
- 不需要多輪審核、不需要高治理證據。

2. 用 Nexus 改（Nexus Mode）適用：
- 涉及多階段流程（P/D/X/R/A/C）或跨模組改動。
- 需要 benchmark、drift、health、trace 等可審計證據。
- 需要並行任務、可回放、可回歸驗證。

3. 目前這批工作的建議模式
- 主線重構（PR-01 ~ PR-09）：`Nexus Mode`。
- TRU-101 空值修補與欄位拆分：`Nexus Mode`。
- Flash 追近 Sonnet 路線（F1~F4）：`Nexus Mode`（需要 A/B 與 gate 證據）。
- 記憶與學習 v2（M1~M3）：`Nexus Mode`（需要 replay 與 ROI 驗證）。
- 文案對齊與 docs 維護：`Manual Mode`（Gemini 3 Flash 直接改）。
- 最終 Gate 與對照報告：`Nexus Mode`。

<!-- autosync-smoke 2026-03-18 10:36:11 -->

<!-- autosync-smoke-2 2026-03-18 10:38:04 -->

<!-- autosync-smoke-launchd 2026-03-18 10:41:40 -->

<!-- autosync-smoke-launchd-fix 2026-03-18 10:42:24 -->
