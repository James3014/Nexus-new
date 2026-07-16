# 動態能力路由與 A/B 演化 (Dynamic Capability Routing & A/B Evolution)

**建立日期**: 2026-06-05
**更新日期**: 2026-07-13
**上下文來源**: `capability_ab_runner.py` 與 `capability_planner.py` 演進歷史 + source-level 驗證

Nexus 引擎的核心優勢在於其「能力 (Capability)」的調用並非靜態腳本，而是透過數據驅動的動態路由與 A/B 測試持續演化。

## 1. 動態能力規劃器 (Capability Planner)

`Capability Planner` 負責在任務啟動前，根據上下文動態組裝最佳的能力清單。位於 `nexus/engine/capability_planner.py` (1453 lines)。

### 1.1 輸出結構

```
CapabilityPlan
  +- selected_capabilities: list[str]
  +- required_capabilities: list[str]
  +- optional_capabilities: list[str]
  +- conditional_capabilities: list[str]
  +- forbidden_capabilities: list[str]
  +- constraints: CapabilityConstraints
  +- decision_trace: list[dict]
  +- replan_trace: list[dict]
  +- score: float
  +-- signal_snapshot: dict  <- 關鍵：包含 execution_topology
```

### 1.2 40+ CapabilityNodes

| Category | Nodes |
|----------|-------|
| governance | harness_preflight_sensor, pregate, asi_constraint_extractor, belief, file_lock, sandbox, mempalace_gate |
| validation | semantic_failure_sensor, bdd_acceptance_skill, jit_validation, artifact_gate, claim_gate, delivery_gate, acceptance_check, ui_validator, stress_test |
| recon | codeintel, architecture_scout, external_doc_scout, xray |
| repair | hyper, nightshift, repair_loop, oracle_shadow |
| collaboration | swarm, swarm_quiet_moment, drone, multi_agent, integration_manager |
| reasoning | autoreason, judge_panel, llm_judge_panel |
| execution | direct_mode, local_model_executor |
| memory | memory, lancedb, semantic_searcher |
| routing | msa_router, research_route, autonomic_router |
| learning | learn_mode, learn_scheduler, learn_phase_slo |
| self_improvement | research_control_plane, benchmark, meta_opt, federation |
| acceleration | ddtree |
| continuity | metabolism |
| platform | registry_sync |

### 1.3 Routing Tier 決策

```
_routing_tier()
  |
  +-- L0: risk_score low, confidence high, simple task
  |   -> skip heavy phases, fast path
  |
  +-- L1: moderate risk
  |   -> standard pipeline
  |
  +-- L2: high risk, cross-module
  |   -> full pipeline + research
  |
  +-- L3: very high risk, hazard flags
  |   -> full pipeline + research + committee
  |
  +-- cloud_with_local_assist (when ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW=1)
      +-- medium/hard difficulty -> cloud_with_local_assist topology
      +-- easy difficulty -> local_only topology
```

### 1.4 signal_snapshot 中的 Local Model 欄位

當 `NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR=1` 時，Planner 會設定：

```
signal_snapshot
  +- selected_executor: "local_model"
  +- executor_provider: "ollama" (from env)
  +- executor_model: "qwen2.5-coder:7b" (from env)
  +- local_executor_authority: "candidate_only"
  +- protocol_mode: str
  +- model_call_allowed: bool
  +- candidate_enabled: bool
  +- mutation_allowed: bool
  +- verifier_allowed: bool
  +- execution_topology: str  <- 關鍵 routing 欄位
  |   +- "single_local_model" (default)
  |   +- "local_committee_only"
  |   +- "local_cascade"
  |   +-- "cloud_with_local_assist" (shadow only)
  |
  +- committee_profile: dict (if committee topology)
  +- proposer_specs: list (primary/secondary models)
  +-- judge_model: str
```

* **風險導向決策**: 根據任務屬性 (如 `bugfix`, `feature`, `doc-fix`) 與風險等級 (`low`, `critical`)，規劃器會決定哪些能力是 `required`，哪些是 `optional` 或 `forbidden`。
* **動態組裝**: 確保高風險任務強制套用 `governance_audit` 等防禦層，而低風險任務則採用輕量級流程以節省 Token。

## 2. A/B 測試驅動的演化 (A/B Test-Driven Evolution)

Nexus 嚴禁憑直覺新增能力。所有能力的演進都必須經過 `capability_ab_runner.py` 的科學驗證：

### 2.1 世界 B：Benchmark A/B Harness

```
benchmark runner (capability_ab_runner.py)
  |
  +- without_nexus arm (direct_provider_runner.py)
  |   +-- 直接問模型，無 Nexus context
  |       -> 同模型 bare baseline
  |
  +-- with_nexus arm (with_nexus_runner.py)
      |
      +- 1. CapabilityPlanner.plan()
      |   +-- 產生 route + signal_snapshot
      |
      +- 2. 組裝 Nexus-augmented prompt
      |   +- [NEXUS ROUTE SUMMARY]
      |   +- [NEXUS CODEINTEL SUMMARY]
      |   +- [NEXUS EXECUTION PROFILE]
      |   +- [NEXUS EXECUTOR FLAGS]
      |   +- [NEXUS HIDDEN-VERIFIER GUIDANCE]
      |   +-- Session boundary reset
      |
      +- 3. ask_patch() -> 模型回 patch
      |
      +- 4. verify_patch() -> pytest 驗證
      |
      +- 5. self-heal retry（1 次）
      |
      +-- 6. LocalModelExecutor bridge (N1 seam)
          |
          +- LocalModelExecutor.run(request)
          |   +- topology: local_committee_only / single_local_model
          |   +- provider: OllamaLocalModelProvider (Qwen)
          |   +- candidate generation
          |   +- isolation
          |   +-- verifier
          |
          +-- receipt + ledger -> 結算 row
```

* **雙軌驗證 (Dual-Track Evaluation)**: 當引入新能力 (Treatment) 時，必須與現有基準 (Baseline) 進行同題目的平行測試。
* **數據裁決**: 新能力必須在「Token 效率」、「解決率 (Solve Rate)」或「Wall Time」上展現出明確的統計優勢 (搭配 Hidden Verifier 驗證)，才能通過 Public Claim Gate。

### 2.2 Benchmark Runner 元件分析

| 元件 | 用途 | 是否可重用為產品 |
|------|------|-----------------|
| `capability_ab_runner.py` | A/B 比較主控 | 不適合（row-finalization 綁 benchmark） |
| `with_nexus_runner.py` | Nexus prompt 組裝 | 部分可重用 |
| `direct_provider_runner.py` | Bare baseline | 不需要重用 |
| `n30r_real_core_bridge.py` | 真實 LocalModelExecutor 驗證 | 參考價值高 |

## 3. 淘汰與收斂機制 (Deprecation & Convergence)

* 表現不佳或造成上下文污染的能力，會在其 Capability Receipt 的追蹤下被標記。
* 經過多次 A/B 測試證實無效的策略，將會被移除或降級。
* 這種機制確保了 Nexus 不會隨時間變成臃腫的「功能怪獸」，而是保持為極度精煉、數據驗證過的智能核心。

## 4. 關鍵缺口 (2026-07-13 確認)

1. **World B 是驗證儀器，不是產品主線**: row-finalization 綁 benchmark fixture，不應抽成整個產品 runtime
2. **World A 與 World C 沒有 bridge**: 日常 Agent 穿 Nexus 沒有自動 Local Assist
3. **LocalModelExecutor 主要 caller 是 benchmark scripts**: 非日常 CLI