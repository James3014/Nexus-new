---
name: nexus-root-cause-probe
description: 用於診斷 Nexus「看似完成但回報不可信、agent 與 gate 結果不一致、或任務被治理狀態卡住」的問題。當需要直接穿 Nexus 跑真實流程、檢查 evidence/report/gate 的因果鏈、先用 TDD 鎖定缺陷再修最小邊界時使用。
version: 2026.04.22
---

# Nexus Root Cause Probe

## 使用時機
- 使用者回報 `agent + Nexus` 一直說完成，但結果不可信。
- `acceptance-check`、`delivery-gate`、`ci_gate --dry-run` 的結果互相矛盾。
- 測試綠了，但真實 `nexus ...` 命令仍異常。
- 需要分辨是 runtime defect、report causality defect、governance-state block，還是操作競態。

## 不使用時機
- 單純功能開發，沒有 Nexus runtime / report / gate 問題。
- 只需要改文案、前端樣式或與 Nexus 無關的測試。

## 核心原則
- 不信口頭回報，只信實際 artifact。
- 不先猜 core，先驗 CLI 邊界、report verifier、gate script。
- 不只跑單元測試，必須至少跑一條真實 Nexus 命令。
- 不平行執行因果鏈探測步驟；先後順序錯了會製造假問題。
- `run` 類命令要做 CLI vs direct executor paired probe。
- `research` / `hyper` 類命令要做 CLI vs direct service paired probe。
- 全工作路徑不只看 seam，還要看 artifact/gate contract 是否存在。
- 對會回傳 `status=SUCCESS` 的工作命令，不只看 runtime status，還要檢查是否存在更高層的 `semantic_status` / semantic failures。

## 標準流程
1. 建立基線
- 跑：
```bash
uv run scripts/engine/nexus_cli.py --help
uv run scripts/engine/nexus_cli.py nexus --help
git status --short
git rev-parse --short HEAD
```
- 先確認要探測的命令真的存在，避免用錯 alias 或舊入口。

2. 選一條最小真實路徑
- 優先挑會寫出 artifact 的低風險命令，例如：
```bash
uv run scripts/engine/nexus_cli.py nexus content:rewrite ...
uv run scripts/engine/nexus_cli.py nexus learn:ingest ...
uv run scripts/engine/nexus_cli.py nexus acceptance-check --evidence <FILE>
```
- 目標不是完成任務，而是逼出真實 evidence -> report -> gate 鏈。

2.5 `research` / `hyper` 指令的 seam probe
- 對 service-backed 命令，優先比較：
```bash
uv run scripts/engine/nexus_cli.py nexus research:auto-flow ...
uv run python -c '... call research_flow_service.run_auto_flow(...) ...'
```
```bash
uv run scripts/engine/nexus_cli.py nexus research:benchmark ...
uv run python -c '... instantiate ResearchBenchmarkService(...).run_benchmark(...) ...'
```
- 判讀：
  - CLI 與 direct service 命中的 service / 參數一致：
    - CLI seam 正常，問題不在入口轉接。
  - CLI 有額外 fallback、吞錯、改參數：
    - 分類為 `execution seam defect`。
  - `research:run` 這種非 service-backed 命令：
    - 直接做路徑審計，確認它沒有偷偷調用 `execute_tactical_node` / `_execute_single_run_task`。

2.6 全工作路徑 seam audit
- 不只抽樣命令；對所有「會執行工作」的 CLI 命令做靜態稽核。
- 至少檢查：
  - `scripts/engine/nexus_cli.py` 內每個 work command block
  - `nexus/engine/cli_runner_async.py`
- 舊 seam 禁止詞：
```text
Compat-Fallback
materialize_test_scripts
_run_engine_flow(
```
- 目標：
  - 確認舊 `run` runner 不會透過其他 work command 再被引用回來。
  - 用單一 audit test 長期鎖住，避免未來某個 agent 又接回舊路徑。

2.7 全工作路徑 artifact/gate audit
- 對所有 work command 建立 contract matrix，分三類：
  - `mutating_with_artifact`
  - `mutating_with_gate`
  - `read_only_or_routing`
- 規則：
  - `mutating_with_artifact`
    - 至少要有 `report_file` / `output_file` / `evidence_file` / `write_text(` 其中一組明確工件契約。
  - `mutating_with_gate`
    - 至少要能看見 `acceptance-check` / `delivery-gate` / `contract-check` 之一。
  - `read_only_or_routing`
    - 不要求落盤，但不應偷偷 `write_text(`。
- 將 matrix 寫成回歸測試，避免只靠人工巡檢。

3. 檢查因果鏈
- 依序看：
  - evidence 檔
  - `.nexus/reports/agent_report.json`
  - `.nexus/reports/acceptance_check.json`
  - `.nexus/reports/delivery_gate.json`
- 若命令輸出同時含 runtime 與 semantic 層欄位：
  - 不可把 `status=SUCCESS` 直接當成任務完成
  - 必須同時核對 `semantic_status`
  - 若 `semantic_status != VERIFIED`，分類為 `semantic-completion defect`
- 對 report 至少檢查：
  - `head_alignment`
  - `commit_integrity`
  - `branch_delta_integrity`
  - `test_evidence`
  - `freshness`

4. 先分類，不要急著修
- `runtime defect`
  - 命令本身跑不起來，或檔案根本沒產生。
- `execution seam defect`
  - CLI 沒打到預期 service/executor，或在入口層吞錯、改參數、走舊路徑。
- `report causality defect`
  - 舊 report 被當成本輪結果、report 比 evidence 舊、tests evidence 缺失、HEAD 對不上。
- `semantic-completion defect`
  - 命令回 `SUCCESS`，但需求要求的高階語義契約未完成，例如缺必要欄位、必要文件、必要 protocol 接線。
- `governance-state block`
  - report 是真的，但因 `UNVERIFIED_COLD_START`、缺樣本、policy 條件不滿足而被擋。
- `operator race`
  - 平行跑命令導致剛寫出的檔案還沒被下一步看到，或相互覆寫。

5. 先寫失敗測試，再修
- 將問題落到最小回歸測試：
  - CLI 參數傳遞：`tests/ops/test_acceptance_check_claim_hook.py`
  - Research seam：`tests/engine/test_cli_research_seams.py`
  - Full work-path audit：`tests/engine/test_cli_work_path_audit.py`
  - Artifact/gate matrix：`tests/engine/test_cli_artifact_gate_audit.py`
  - gate / verifier 契約：`tests/ops/test_verify_report_claims.py`, `tests/ops/test_delivery_gate_contract.py`
  - runtime smoke：`tests/ops/test_stage_f_flow.py`
  - learn / ingest 契約：`tests/research/test_learn_ingest_channels.py`, `tests/research/test_learn_services_split.py`
- 先看到測試失敗，再改碼。

6. 修最小邊界
- 優先順序：
  - `scripts/engine/nexus_cli.py`
  - `nexus/app/research_flow_service.py`
  - `nexus/app/research_benchmark_service.py`
  - `scripts/ops/verify_report_claims.py`
  - `scripts/ops/nexus_acceptance_check.py`
  - `scripts/ops/nexus_delivery_gate.sh`
  - 對應 service / schema
- 只有在邊界證據指向核心邏輯時，才深入 `nexus/core` 或 `nexus/research/...`。

7. 重新驗證
- 至少要有三層：
```bash
uv run pytest -q <targeted tests>
uv run scripts/engine/nexus_cli.py nexus <real command>
uv run scripts/ops/ci_gate.py --dry-run
```
- 若真實 Nexus smoke 和 targeted tests 的結論不一致，繼續追 artifact，不要宣布完成。

## 常見陷阱
- 只看 pytest，不穿 Nexus 跑真實命令。
- 將 `UNVERIFIED_COLD_START` 當成回報造假；它通常是治理狀態，不一定是 runtime bug。
- 用舊 `agent_report.json` 誤判本輪成功。
- 平行跑 ingest / acceptance，導致 evidence 路徑看起來不存在。
- 一開始就改 `core/`，結果真正問題只是 CLI 沒把 `--report-file` 或 `--report-newer-than` 傳下去。

## 修復策略
- 若是 report 不可信：
  - 補 causality/freshness 檢查。
- 若是 cold start 擋路：
  - 先分 `dev` / `prod` 策略，再決定是否允許放行。
- 若是 service 契約飄移：
  - 在 facade 層 fail-closed，要求必要欄位存在。
- 若是命令表面重複或漂移：
  - 先加命令唯一性測試，再修 CLI 註冊。
- 若發現 CLI seam 與 async seam 各自複製一份 task routing / service 呼叫：
  - 先用測試鎖定兩者都必須共用單一 canonical helper。
  - 再把重複邏輯集中到單一模組，避免一邊修好、另一邊回退。
- 若發現多個入口各自 `NexusEngine(EngineConfig(...))` 或 `NexusCommandService(...)`：
  - 先抽成 shared factory，例如 `build_engine(...)` / `build_command_service(...)`。
  - CLI、legacy shim、async runner、benchmark/smoke script 都必須走同一組 factory。
- 若 legacy caller 仍需要舊簽名（例如 `execute_bug(task, ...)`）：
  - 不要在每個入口各自包 `_CompatService`。
  - 改成單一 `LegacyTaskServiceAdapter`，集中 request shaping，避免 CLI、swarm、舊 façade 各自複製一份。

## 交付格式
- `Symptom`: 觀察到的表面問題。
- `Probe Path`: 實際跑了哪條 Nexus 命令。
- `Artifact Evidence`: 哪個 evidence/report/gate 證明了真因。
- `Root Cause`: 真因分類與精準原因。
- `Fix Boundary`: 修在哪一層，為什麼不往更深層改。
- `Regression Tests`: 新增或更新哪些測試。
- `Residual Risk`: 還剩哪些治理狀態或非本波範圍問題。
