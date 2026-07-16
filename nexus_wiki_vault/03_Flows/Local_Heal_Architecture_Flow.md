# 本地自動修復架構流程 (Local Heal Architecture Flow)

**建立日期**: 2026-06-05
**更新日期**: 2026-07-13
**上下文來源**: Git 歷史提煉 + source-level 驗證 (codex/local-armor-baseline-integration, HEAD ffae4fe20)

`local_heal` 是 Nexus 專案的核心子系統，旨在建立高度自動化、閉環的錯誤重現與代碼修復流水線。

## 1. 核心使命與架構解耦 (Core Mission & Decoupling)

Local Heal 已從單一腳本演進為由 **Orchestrator** 驅動的模組化流水線。其主要目標是：在將修改提交回主線或交由全域驗證前，於沙盒/本地環境中進行「重現 -> 診斷 -> 修復 -> 驗證」。

## 2. LocalModelExecutor 核心架構 (2026-07-13 驗證)

LocalModelExecutor 是 Local Heal 的核心執行引擎，位於 `nexus/services/local_heal/local_model_executor.py` (3535 lines)。

### 2.1 請求/回應合約

```
LocalModelExecutorRequest (Frozen)
  +- task_id, problem_statement, repo_root, target_file
  +- selected_capabilities: list[str]
  +- execution_topology: str (from signal_snapshot)
  +- model_name, dry_run, mutation_allowed, verifier_allowed
  +-- route_context (含 signal_snapshot)

LocalModelExecutorResponse (Frozen)
  +- invoked, local_model_called
  +- candidate_patch, candidate_hash
  +- reasoning_summary, raw_model_metadata
  +- provider, model_name, error, timeout
  +- evidence_refs, cascade_stages_run
```

### 2.2 執行流程

```
LocalModelExecutor.run(request, provider=None)
  |
  +- 1. _resolve_execution_topology(request)
  |   +-- 從 signal_snapshot.execution_topology 讀取，無 fallback
  |
  +- 2. resolve_local_armor_profile(route_context)
  |   +-- LITE / STANDARD / FULL
  |
  +- 3. dry_run gate -> P3 skeleton + dry_run_receipt
  |
  +- 4. build_local_model_provider_from_signal_snapshot()
  |   +-- InertLocalModelProvider / OllamaLocalModelProvider / InjectedLocalModelProvider
  |
  +- 5. RecordingLocalModelProvider(provider)  <- ledger 紀錄
  |
  +- 6. topology dispatch
  |   |
  |   +- [local_committee_only]
  |   |   LocalCommitteeCandidateProvider
  |   |   -> 多模型提案 + Borda 選擇
  |   |
  |   +- [local_cascade]
  |   |   _local_cascade_orchestrate()
  |   |   -> 多階段降級
  |   |
  |   +- [cloud_with_local_assist]  <- SHADOW ONLY
  |   |   Stage 1: _p3_stage1_local_diagnosis() (deterministic)
  |   |   Stage 2: FakeCloudCandidateProvider() (empty)
  |   |   Stage 3: _p3_stage3_cheap_verifier() (deterministic)
  |   |   -> fall through to single_local_model
  |   |
  |   +-- [single_local_model] (default)
  |       provider.generate() -> normalize -> apply -> verify
  |
  +- 7. Stage 5: escalation -> P4 committee
  |
  +- 8. build_local_armor_attempt_receipt()
  |
  +-- 9. build_local_assist_telemetry_from_executor_meta()
```

### 2.3 Execution Topology 決策

| Topology | 行為 | 狀態 |
|----------|------|------|
| `single_local_model` | 單一本地模型生成 candidate | Production |
| `local_committee_only` | 多模型提案 + Borda 選擇 | Production |
| `local_cascade` | 多階段降級 | Production |
| `cloud_with_local_assist` | Stage 1-3 + FakeCloud + fallback | **SHADOW ONLY** |

### 2.4 Local Armor Execution Profile

| Profile | 控制開關 |
|---------|---------|
| **LITE** | planning_llm=Y, spec_gen=Y, candidate=低, retry=低, committee=N, autoreason=N |
| **STANDARD** | planning_llm=Y, spec_gen=Y, candidate=中, retry=中, committee=N, autoreason=Y |
| **FULL** | planning_llm=Y, spec_gen=Y, candidate=高, retry=高, committee=Y, autoreason=Y, ddtree=Y |

### 2.5 cloud_with_local_assist 的 Shadow 狀態

```python
# local_model_executor.py line 2825
class FakeCloudCandidateProvider:
    def generate(self, request):
        # 永遠回傳空 candidate_patch, 空 candidate_hash
        # provider="fake_cloud"
        # reasoning_summary="fake_cloud_no_endpoint"
```

Planner 雖可選中 `cloud_with_local_assist` topology，但 Cloud stage 使用 `FakeCloudCandidateProvider` — 沒有真實雲端 provider。所有 report 標註 `shadow only`。

## 3. 流水線階段 (Pipeline Phases)

Local Heal 的執行被嚴格拆分為多個獨立的 Phase：

*   **Syntax Preflight (語法預檢)**: 在啟動深層分析前，先進行基礎的語法與結構掃描，排除低級錯誤。
*   **Planning & Preparation (規劃與預處理)**: 包含 Classifier 與 Sanitizer，負責清理輸入的錯誤報告並制定修復策略。
*   **Reproduction (自動重現)**: 
    *   這是一個核心里程碑。系統會嘗試生成自動化的重現腳本 (Reproduction Script Prepper)。
    *   具備**自我修正 (Self-correction)** 能力：若腳本生成失敗或報錯，會重新調整 prompt 包含 assertion directives。
    *   支援從 `expert_repro` 快取中載入專家級重現腳本。
*   **Patch Synthesis (修復合成)**: 也就是 Patch Invocation Boundary，這層負責與本地模型互動並產生修正代碼。具備 Refusal Recovery 機制以應對模型的拒絕回應。
*   **Verification (驗證)**: 在沙盒內運行重現腳本，驗證 Patch 是否真正解決了問題。
*   **Expected Stop Layer (預期停止層)**: 探測框架 (Probe Framework) 中的安全機制，確保修復過程符合預期原因並能及時止損。

## 4. 遙測與證據追蹤 (Telemetry & Receipts)

為確保修復過程的透明度與可追溯性，`local_heal` 實作了高精度的追蹤系統：

*   **Telemetry Tracker**: 追蹤每個階段的 Token 消耗與執行時間 (Duration)，以支援成本控制與效能優化。
*   **Receipt Builder**: 自動將 Telemetry 記錄、執行軌跡與模型 Prompt 注入到最終的 Receipt 中。這份 Receipt 成為了該次修復是否可信的重要「法庭證據」。
*   **LocalAssistTelemetryCollection**: 7 個結構化 section — compaction, memory_rerank, preflight, cheap_judge, isolation, verifier, learning_closure。

## 5. 隔離與安全 (Isolation & Safety)

*   **Research Isolation**: 修復過程與核心路由智慧分離，確保在探索與生成 Patch 時不會污染全域 Context。
*   **Canary Receipt & Baseline**: 透過標準化的金絲雀驗證與基線比較，確保修復不會引入退化。
*   **RecordingLocalModelProvider**: 包裝任何 LocalModelProvider，每次 generate() 自動 append LedgerRecord 到 ledger。

## 6. 關鍵缺口 (2026-07-13 確認)

1. **Canonical CLI 沒有 Executor Dispatch Bridge**: 一般 `nexus run` 的 Repair phase 走 deterministic `try_local_repair()`，不是 `LocalModelExecutor`
2. **cloud_with_local_assist 使用 Fake Cloud**: Contract 存在但無真實 Cloud provider
3. **沒有 Agent-facing assist envelope**: LocalModelExecutor 回傳 candidate/metadata，不是上層 coding agent 容易消費的 assist response
4. **主要 caller 是 benchmark scripts**: capability_ab_runner、n30r_*，非日常 CLI

## 7. 關鍵檔案

| 檔案 | 行數 | 角色 |
|------|------|------|
| `nexus/services/local_heal/local_model_executor.py` | 3535 | Local model execution core |
| `nexus/services/local_heal/local_committee_candidate_provider.py` | 201 | Multi-model committee |
| `nexus/services/local_heal/committee_orchestrator.py` | 605 | Committee orchestration |
| `nexus/services/local_heal/local_armor_execution_profile.py` | 151 | LITE/STANDARD/FULL profiles |
| `nexus/services/local_heal/local_armor_attempt_receipt.py` | 339 | Per-attempt telemetry |
| `nexus/services/local_heal/local_assist_receipts.py` | 149 | Observational telemetry |
| `nexus/services/local_heal/local_model_provider.py` | -- | Provider + ledger |