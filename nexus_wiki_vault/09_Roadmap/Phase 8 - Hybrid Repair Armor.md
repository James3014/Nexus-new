---
aliases:
- Hybrid Repair Armor
- 雙模式修復系統
- Hybrid Mode A/B
confidence: high
last_compiled: 2026-07-08
owner: agent
related_pages:
- '[System Overview](../00_Home/System Overview.md)'
- '[Nexus Evolution History v9-v28](../00_Product/Nexus_Evolution_History_v9_to_v28.md)'
- '[Ops - Learning Closure Matrix](../06_Ops/Ops - Learning Closure Matrix.md)'
- '[CapabilityPlanner Downstream Enforcement ADR](../01_System/ADR/ADR-2026-07-08-capability-planner-downstream-enforcement.md)'
source_of_truth: nexus/contracts/hybrid_route.py, nexus/services/local_heal/output_understanding.py
status: draft
tags:
- roadmap
- phase8
- hybrid-repair
- cloud-with-local-assist
- local-only
- double-mode
title: 'Phase 8 - Hybrid Repair Armor'
type: roadmap
version_scope:
- v28
- v29
---

# Phase 8 — Hybrid Repair Armor（雙模式修復系統）

## One-sentence summary

把 Nexus 變成「**模型提案合約 + 驗證治理鏈 + 編排主迴圈**」的雙模式修復系統：模式 A 雲端主力 + 本地助手，模式 B 純本地委員會逼近裸雲端，兩者共用同一個 CanonicalPatchCandidate + hash-chain + claim gate。

## Role / responsibility

- **Mode A（Cloud + Local Assist）**：Cloud Model 吃 ≤500 chars compact prompt（不是 full file），9B 本地當 cheap verifier，本地 cascade 兜底；verifier pass 才 claim。
- **Mode B（Local Only）**：3B advisor + 7B+6.7B+9B+14B 委員會（Borda 投票 + diversity selection），全部 verifier pass 才不 claim production。
- **模式切換**：Quota Monitor 觀察 cloud 429/5xx/token budget/local GPU memory → emit QuotaState 事件 → Degradation Controller 觸發；切換時 `degradation_reason_chain` 寫入 receipt。
- **權威層**：CapabilityPlanner / HybridRouteDecision 永遠是 route authority，下游 (LocalModelExecutor / CommitteeOrchestrator / RuntimePolicy) 是 pure consumer（見 CapabilityPlanner Downstream Enforcement ADR）。

## Upstream

- [Phase 6 - Nexus Hardening](Phase 6 - Nexus Hardening.md)
- [CAPABILITY_ROUTING_MIGRATION_PLAN_2026-04-29.md](CAPABILITY_ROUTING_MIGRATION_PLAN_2026-04-29.md)
- [Nexus Evolution History v9-v28](../00_Product/Nexus_Evolution_History_v9_to_v28.md)
- `28_V28_ARCHITECTURE_FREEZE.md`
- `MUSE-PROTO.md`

## Downstream

- [Ops - Learning Closure Matrix](../06_Ops/Ops - Learning Closure Matrix.md)（失敗教訓回寫）
- [Ops - Truth Claims Register](../06_Ops/Ops - Truth Claims Register.md)（claim 邊界）
- [Ops - CI Failure Playbook](../06_Ops/Ops - CI Failure Playbook.md)
- [Ops - Governance SLO Dashboard](../06_Ops/Ops - Governance SLO Dashboard.md)

## Related modules / files

- `nexus/contracts/hybrid_route.py`（route authority，8 種 RouteMode）
- `nexus/services/local_heal/output_understanding.py`（CanonicalPatchCandidate）
- `nexus/services/local_heal/source_hash_guard.py`（hash chain 物理攔截）
- `nexus/services/local_heal/candidate_isolation_gate.py`（候選隔離門）
- `nexus/services/local_heal/claim_delivery_gate.py`（claim gate 強制 public=false）
- `nexus/services/local_heal/quota_state.py` + `degradation_policy.py`（L4 已實作）
- `nexus/services/local_heal/local_model_executor.py`（local_* topology runtime）
- `nexus/services/local_heal/committee_orchestrator.py`（C6AX D/A live-verified）
- `nexus/services/local_heal/fuzzy_spec_registry.py`（PAW 雛形已有 5 個 fuzzy function）
- `nexus/services/local_heal/p3_*_*.py`（cloud_with_local_assist 4 stage 規劃）
- `scripts/bench/capability_ab_runner.py`（5 月 12/12 vs bare 8/12 baseline）

## Source notes

- 對齊 `NEXUS_CONSOLIDATED_STATUS_REPORT_20260706.md`（C6AV-C6BC 委員會實證鏈）
- 對齊 `Nexus本地委員會全能力路由接軌查證報告_20260706.md`（SPXDRAC 七階段）
- 對齊 `nexus_route分裂查證報告_2026-06-30`（CapabilityPlanner 唯一 route authority）
- 對齊 `Nexus_Knowledge_Agent_Integration_v2`（Knowledge Agent = audit/retrieval layer）
- 對齊 `Nexus_LLM_Committee_Architecture_Report.md`（5 條論文原則）
- 對齊 `論文參考.md`（AUTOMEM / SHEPHERD / PAW 三篇）
- 對齊 `NEXUS_HYBRID_REPAIR_CORRECTION_20260708.md`（本機稽核版本）

## Open questions / conflicts

- [ ] Semantic Correctness Gate（C6BC 唯一單點）何時接上 claim gate？
- [ ] Quota Monitor 的 cloud 觀察來源（provider API 429/5xx / 自家遙測 / 環境變數）哪個為主？
- [ ] SHEPHERD supervisor 是否會搶 CapabilityPlanner 決策權？需明確分邊界。
- [ ] PAW compiler 編 LoRA 會否動到 C11/C13 protocol contract？需隔離。

---

[System Overview](../00_Home/System Overview.md)

# Phase 8 — Hybrid Repair Armor 詳細 Roadmap

## 0. 四層架構現況評分

| 層 | 名稱 | 現況分數 (0-5) | 一句話 |
|----|------|---------------|--------|
| L1 | **Nexus Understanding** | **3.5** | evidence / classify / 壓縮 已有骨架；surgical slicing 有但未與 cloud 提示詞收斂 |
| L2 | **Model Proposal** | **2.5** | 本地委員會已 live-verified，cloud_with_local_assist 4 stage 從未真實演過 |
| L3 | **Verification / Decision** | **4.5** | CanonicalPatchCandidate + 三段 hash chain + isolation gate + claim gate 已收斂；缺 production-ready 編排主迴圈 |
| L4 | **Quota / Degradation** | **3.0** | policy 完整（HEALTHY/CONSTRAINED/EXHAUSTED/UNKNOWN 四態），缺 runtime 自動切換 |

## 1. 全能力 25 個 Mode 矩陣

| # | 能力 | 本地模式 | Online 模式 | 接軌狀態 |
|---|------|---------|-----------|---------|
| 1 | 證據檢索 (Evidence) | ✅ | ✅ | 已 wired |
| 2 | 手術切片 (Surgical Packer/Slicer/Intel) | ✅ | ✅ | 已 wired |
| 3 | 失敗分類 (Failure Analyzer) | ✅ | ✅ | 已 wired |
| 4 | 診斷（3B advisor） | ✅ shadow-only | ❌ 缺 runtime | P1 Stage 1 |
| 5 | 雲端候選 (Cloud primary) | ❌ | ✅ | 已 wired (`capability_ab_runner`) |
| 6 | 本地候選 (Local 7B/14B) | ✅ | ✅ | 已 wired |
| 7 | 多模型候選 (Heterogeneous provider) | ✅ | ✅ | 已 wired |
| 8 | Borda 投票 (Diversity selector) | ✅ | ✅ | C6Y closed out |
| 9 | 委員會 (D-phase + A-phase) | ✅ | ✅ | C6AX live-verified |
| 10 | Cheap Verifier (9B) | ✅ shadow-only | ❌ 缺 runtime | P1 Stage 3 |
| 11 | Full Verifier (T5) | ✅ | ✅ | 已 wired |
| 12 | Hash Chain (raw→norm→applied) | ✅ | ✅ | 已 wired |
| 13 | Candidate Isolation Gate | ✅ | ✅ | 已 wired |
| 14 | Claim Delivery Gate | ✅ 但不看 quota | ✅ 但不看 quota | **P3-2 改寫** |
| 15 | Quota Monitor | ❌ | ❌ | **P3-1 新建** |
| 16 | Quota Degradation | ⚠️ policy only | ⚠️ policy only | **P3-2 新建 controller** |
| 17 | Cascade Controller (3B→14B) | ❌ | ❌ | **P2 新建** |
| 18 | Knowledge Agent (EvoEmbedding) | ❌ | ❌ | P4-1 新建 |
| 19 | AUTOMEM Memory Curator | ❌ | ❌ | P4-2 新建 |
| 20 | SHEPHERD Supervisor | ❌ | ❌ | P4-3 新建 |
| 21 | PAW Compiler Seam | ❌ | ⚠️ fuzzy 雛形已有 | **P4-4 改寫 fuzzy_spec_registry** |
| 22 | Semantic Correctness Gate | ❌ | ❌ | **P0 新建**（C6BC 唯一單點）|
| 23 | Public Benchmark Regression | ⚠️ 5 月有 | ⚠️ 5 月有 | **P5 改寫 capability_ab_runner** |
| 24 | Learning Closure Writeback | ⚠️ 骨架 | ⚠️ 骨架 | P4-5 擴寫端 |
| 25 | Belief Engine | ✅ | ✅ | C6AC wired |

## 2. 兩個模式差異表

| 維度 | 本地模式 | Online 模式 |
|------|---------|-----------|
| 觸發 | QuotaState=EXHAUSTED 或 UNKNOWN | QuotaState=HEALTHY |
| 主提案 | 本地委員會 (3B+6.7B+7B+9B+14B) | 雲端 (Gemini) + 本地委員會輔助 |
| Diagnosis | 3B advisor | 3B advisor（共用）|
| 驗證 | 9B cheap + T5 full | 9B cheap + T5 full（共用）|
| 套用 | SurgicalSlicer + SurgicalPacker | SurgicalSlicer + SurgicalPacker（共用）|
| 升級次序 | Cascade 3B→7B→9B→14B | Cloud 失敗才 fallback 到 cascade |
| Public claim | ❌ 強制 false | ✅ 通過 verifier 才可 true |
| 配額計費 | 0 | Cloud token 計入 |
| Receipt | 標 `local_only_executed` | 標 `cloud_with_local_assist` |
| Fallback 觸發 | 永遠不會（已在本地）| Cloud 429/5xx 3 週期 → 切本地 |

## 3. 6 個 Phase Roadmap（含去重 + 補既有重用）

### P0 — Semantic Correctness Gate — 1 週
**為何先做**：CEO 不知道「修對了」是什麼，所以 patch 套得進去但 bug 還在（C6BC 唯一單點瓶頸）。

**真實新建**：
- `nexus/contracts/semantic_correctness_contract.py`：`SemanticCorrectnessAssertion` + `SemanticCorrectnessCheck { assertion_coverage, replacement_references_buggy_symbol, expected_post_state_hash, passed }`

**改寫既有**：
- `nexus/services/local_heal/completion_contract.py`：在 `build_completion_envelope` 加 `semantic_correctness_passed` 欄位
- `nexus/services/local_heal/isolated_verifier.py`：跑完測試後跑 semantic check

**重用既有**：
- 5 個 domain verifier packs（`verifiers/packs/{astropy,django}_pack.py` + `verifiers/domain/{astropy,django,common_core,concurrency,name_sanity}.py`）

**完成條件**：
- `semantic_correctness_passed=False` → `claim_eligible=False`
- C6BC 紀錄的「model patch applies but bug remains」100% 攔截
- 5 月 `with_nexus` baseline 12/12 case 不誤殺

### P1 — Cloud-with-Local-Assist 4 Stage 真實 Runtime — 2-3 週
**為何先做**：CEO 已有 `local_committee_only` 劇本跑通，但從未演過「雲端主廚 + 本地助手」。

**真實新建**：
- `nexus/executors/cloud_executor_with_compact_prompt.py`：吃 ≤500 chars compact prompt，不是 full file

**改寫既有**（shadow → runtime 雙胞胎）：
- `nexus/services/local_heal/p3_local_diagnosis.py`：`shadow_only` flag 翻成 `runtime_enabled=True`，保留 shadow 雙胞胎
- `nexus/services/local_heal/p3_local_cheap_verifier.py`：同上
- `nexus/services/local_heal/p3_local_retry_stub.py`：同上

**重用既有**：
- `surgical_context.build_annotated_context`（anchor 切片）
- `isolated_local_solve_loop.run_isolated_local_solve_loop`（solve loop 主體）
- `p3_route_skeleton.compute_p3_route_skeleton`（4 stage 規劃）

**完成條件**：
- 真實 cloud 接到 ≤500 chars compact prompt
- 3B diagnosis + 9B cheap verifier 真實被呼叫
- Cloud 失敗時自動 fallback 到 Stage 4 cascade

### P2 — Local Cascade Orchestrator — 2 週
**為何先做**：本地模式現況是「並列投票」，不是「3B 失敗才換 7B」。升級次序沒正式 controller。

**真實新建**：
- `nexus/services/local_heal/local_cascade_orchestrator.py`：3B failure → 7B；7B failure → 9B；9B failure → 14B

**改寫既有**：
- `nexus/services/local_heal/diversity_selector.py`：加「跨 stage」consolidation（cascade 內不同 stage candidate 也做 diversity）
- `nexus/services/local_heal/local_model_executor.py`：加 `execution_topology="local_cascade"` 支援

**重用既有**（**不**新建這些，因為已有）：
- `p3_local_retry_stub.compute_p3_local_retry`（已有 `cascade_models_planned` 欄位）
- `isolated_local_solve_loop.run_isolated_local_solve_loop`（solve loop 主體）
- `autonomic_routing_service.AutonomicRoutingService`（**不能碰**，已是 route 決策）
- `completion_contract.build_completion_envelope`（已有 `semantic_status` 欄位）

**完成條件**：
- cascade 內 N stage 失敗不會崩潰，會 escalate 下一 stage
- cascade 結束時 single winner 由 `diversity_selector` 統一選出
- 全部 stage 都失敗時回 `fail_closed` 而非 silent drop

### P3 — Quota Monitor + Degradation Controller + Claim Gate quota 依賴 — 2 週
**為何先做**：CEO 沒有自動知道雲端下班了。`quota_state.py` 是純函式，沒 background watcher。`claim_delivery_gate.py` 也不看 quota。

**真實新建**：
- `nexus/services/local_heal/quota_monitor.py`：週期 30s emit `QuotaState` change event，附 `source` / `confidence` / `reason`
- `nexus/services/local_heal/degradation_controller.py`：連續切換需寫 `degradation_reason_chain: list[str]`

**改寫既有**：
- `nexus/services/local_heal/claim_delivery_gate.py`：在 `ClaimDeliveryGate.validate` 加 `quota_state` 依賴（`local_only_executed` 模式 → 強制 `public_claim_allowed=False`）
- `nexus/contracts/hybrid_route.py`：`HybridRouteDecision` 加 `degradation_reason_chain` 欄位

**重用既有**：
- `quota_state.resolve_quota_state`（從 env 解析）
- `degradation_policy.evaluate_degradation_policy`（HEALTHY/CONSTRAINED/EXHAUSTED/UNKNOWN → action）
- `quota_policy_simulator.simulate_p6_quota_policy`（memory-signal read-only policy）

**完成條件**：
- cloud 429 持續 3 週期自動觸發降級
- 降級時 `HybridRouteDecision.fallback_block_reason` 帶「為何降級 + 之前狀態」
- `production_ready` 永遠 `False`；`public_claim_allowed` 在 `local_only_executed` 時強制 `False`

### P4 — Knowledge Agent 全套（含 AUTOMEM / SHEPHERD / PAW）— 3 週
**為何先做**：圖書館員的卡片還沒建。Knowledge Agent 是 audit/retrieval/evidence support layer，不搖 CEO 決策權。

**真實新建**：
- `nexus/knowledge/evo_embedding_index.py`（P4-1）：對 `learning_closure.jsonl` + `failure_memory.jsonl` + `committee_receipt` 做時序感知 embedding
- `nexus/knowledge/autonomous_memory_curator.py`（P4-2，依 arXiv:2607.01224 AUTOMEM）：每 1000 步軌跡跑 meta-LLM 找記憶用錯
- `nexus/orchestrator/shepherd_supervisor.py`（P4-3，依 arXiv:2605.10913 SHEPHERD）：sub-agent 中途改定義、觀察不打擾、分叉試錯、跳回任一時刻

**改寫既有**（**不**新建 PAW compiler seam）：
- `nexus/services/local_heal/fuzzy_spec_registry.py`：補 `paw_backend_available=True` 的 function runtime 編譯（`candidate_quality_v1` / `duplicate_similarity_v1` / `popularity_trap_risk_v1` 已有 PAW 雛形，補 0.6B Qwen3 LoRA 編譯）
- `nexus/learning/outcome_memory.py`：擴寫端到 `committee_orchestrator.py` + `local_model_executor.py`

**重用既有**：
- LanceDB 既有檢索（`lancedb` 已 wired）
- `fuzzy_functions.py`（5 個 fuzzy function 實作）
- `repair_pattern_retrieval.py`（C6AB 雛形，僅取 verifier_pass/correct_abstain）

**完成條件**：
- Knowledge Agent 可用，但**不下決策**（符合 Knowledge Agent v2 邊界）
- AUTOMEM 跑 1000 步後記憶命中率 +20%
- SHEPHERD 對 delegated retry 失敗重試時間 -60%
- PAW 對 SEARCH_MISMATCH 類 bug token 用量 -50%
- 兩種模式都能用 Knowledge Agent 4 個子能力

### P5 — Public Benchmark Regression（持續）— 1 週啟動 + 持續
**為何先做**：5 月 `with_nexus` 12/12 vs bare 8/12 的證據沒持續更新。退步沒人知道。

**真實新建**：無

**改寫既有**：
- `scripts/bench/capability_ab_runner.py`：改 4 象限（`with_nexus` / `bare` / `local_only_executed` / `cloud_exhausted`）

**重用既有**：
- local_heal 套件 1143 tests
- `p3_synthetic_e2e_trace`（既有 seam）

**完成條件**：
- daily_hybrid_score.json 30 天連續無 false regression
- 任何降級事件都有 `degradation_reason_chain` 與 rollback drill 結果
- 5 月 12/12 vs 8/12 證據可被外部 reviewer 重新跑出（reproducible evidence bundle）

## 4. 12 個不可變規則（防未來走偏）

| # | 規則 | 來源 |
|---|------|------|
| 1 | `route_truth_source == CapabilityPlanner` | `nexus/contracts/hybrid_route.py` |
| 2 | 不下放 RouteMode / Router / Planner / topology selector | `nexus_downstream_enforcement_plan` |
| 3 | Knowledge Agent = audit/retrieval/evidence support layer | `Nexus_Knowledge_Agent_Integration_v2` |
| 4 | `public_claim_allowed` / `production_ready` 預設 false | `28_V28_ARCHITECTURE_FREEZE.md` |
| 5 | D/A Committee = 4-model + Borda + diversity | `LLM Committee Report` 5 條原則 |
| 6 | Diversity > Consensus / Borda > Majority / Small models matter / 2 models is enough / Confidence ≠ Quality | LLM Ensemble 論文 |
| 7 | Hash chain raw→norm→applied | `output_understanding.py` + `source_hash_guard.py` |
| 8 | Candidate isolation gate | `candidate_isolation_gate.py` |
| 9 | v28 architecture freeze 邊界 4 模組 | `28_V28_ARCHITECTURE_FREEZE.md` |
| 10 | Shadow-only 翻 runtime 走雙胞胎 | `p3_*_shadow_only` → `p3_*_runtime_enabled` |
| 11 | `autonomic_router.py` 是 CapabilityRouter 主體，不能碰 | `autonomic_router.py` v4.40 MVP Hardened |
| 12 | PAW 編 LoRA 不動 C11/C13 protocol contract | `protocol.py` 是 SEARCH/REPLACE 契約 |

## 5. 6 條重複造輪子防呆原則

| # | 原則 | 說明 |
|---|------|------|
| 1 | **grep 先決** | 任何新建 module 前必須 `find ... -name '*.py' | xargs grep -l '<關鍵字>'` 至少 2 次 |
| 2 | **既有 fuzzy / completion / claim / router 優先** | `fuzzy_spec_registry.py` / `completion_contract.py` / `claim_delivery_gate.py` / `autonomic_router.py` 已有完整實作，**只能補不能新建** |
| 3 | **shadow-only 翻成 runtime 必走雙胞胎** | 保留 `p3_*_shadow_only` + 新寫 `p3_*_runtime_enabled` |
| 4 | **CapabilityPlanner 下游不碰** | 任何「route / topology / model selection」程式碼都**不可**碰 |
| 5 | **概念詞 grep 必須 0 命中** | AUTOMEM/SHEPHERD/PAW 概念詞命中 0 才可新建（PAW 已命中 fuzzy 雛形 → 改寫不新建）|
| 6 | **28_V28_ARCHITECTURE_FREEZE 四模組邊界不可破** | 4 個核心模組邊界不可破 |

## 6. 已存在的零件盤點（不重建，要重用）

| 零件 | 檔案 | 用途 | 對應 P 階段 |
|------|------|------|------------|
| `FuzzyFunctionSpec` 帶 `paw_backend_available` / `paw_runtime_allowed` | `fuzzy_spec_registry.py` | PAW 編譯器雛形 | P4-4 補 runtime |
| 5 個 fuzzy function specs | `fuzzy_spec_registry.py:50-90` | 已定義 candidate_quality / duplicate_similarity / popularity_trap_risk / memory_usefulness / quota_degradation_risk | P4-4 直接實作 deterministic backend |
| `ClaimDeliveryGate` 強制 `public_claim_allowed=False` / `production_ready=False` / `internal_only=True` | `claim_delivery_gate.py:62-78` | claim gate 主體 | P3-2 在 `validate()` 加 `quota_state` 依賴 |
| `P3LocalRetryStub` 已有 `cascade_models_planned` / `cascade_models_invoked` 欄位 | `p3_local_retry_stub.py:15-17` | cascade 規劃 stub | P2 把 shadow-only 翻成 runtime_enabled |
| `run_isolated_local_solve_loop` 已接 isolated_apply + isolated_verifier + candidate_isolation_gate | `isolated_local_solve_loop.py` | solve loop 主體 | P2 cascade 在外層包，loop 內不動 |
| `AutonomicRoutingService` + `AutonomicRouter` | `autonomic_routing_service.py` + `autonomic_router.py` | route 決策 | **不能碰**，已是 CapabilityPlanner 下游 |
| `completion_contract.build_completion_envelope` 已有 `semantic_status` / `runtime_classification` | `completion_contract.py` | completion 評估 | P0 semantic gate 補 `semantic_correctness_passed` 欄位 |
| `runtime_resilience` 已有 retry + escalation | `research/runtime/runtime_resilience.py` | retry + escalation | P2 借鑑 retry pattern |
| `p3_synthetic_e2e_trace` 已是完整 seam | `p3_synthetic_e2e_trace.py` | synthetic e2e | P1 升級成 real |
| `quota_policy_simulator` 已有 memory-signal read-only policy | `quota_policy_simulator.py` | quota 政策 | P3-1 quota monitor **呼叫** simulator |
| `repair_pattern_retrieval` (C6AB) 僅取 verifier_pass/correct_abstain | `repair_pattern_retrieval.py` | knowledge 雛形 | P4-2 AUTOMEM curator 擴展 |
| `committee_orchestrator.diagnose_with_committee` + `audit_with_committee` (C6AX) | `committee_orchestrator.py` | D/A committee | 已 live-verified |
| `surgical_context.build_annotated_context` | `surgical_context.py` | 手術切片 | P1 Stage 1 吃 anchor |
| `diversity_selector` 已有 Borda + diversity | `diversity_selector.py` | 候選投票 | P2 加「跨 stage」consolidation |
| `local_model_executor` 已有 local_* topology | `local_model_executor.py` | local runtime | P1/P2 加新 topology 支援 |

## 7. 風險與 ADR 連結

### 7.1 殘留風險
- **Risk 1**：P1 把 shadow-only 翻成真實 runtime 可能撞到「env_guarded dry-run」契約邊界。緩解：保留 `p3_*_shadow_only` family，新寫 `p3_*_runtime_enabled` family。
- **Risk 2**：P3 quota monitor 觀察 token 用量時可能把 user-level token 與 system token 混算。緩解：明確分 `user_token` / `system_token` 兩 source。
- **Risk 3**：P4 SHEPHERD supervisor 可能被誤用成「搶 CEO 決策」。緩解：supervisor 只能「分叉 / 觀察 / 改 sub-agent 定義」，不能決定 route / topology / model。
- **Risk 4**：P4 PAW compiler 編 LoRA 可能改動 prompt contract。緩解：LoRA 只能作為 fuzzy bug 的「後處理加速器」，不能改 C11/C13 protocol contract。
- **Risk 5**：P5 daily regression 跑了 30 天可能暴露既有 shadow-only 契約邊界問題。緩解：先開 dry-run flag `daily_regression_observation_only=True` 觀察 14 天再 enable。

### 7.2 對應 ADR
- `ADR-2026-07-08-capability-planner-downstream-enforcement.md`：phase 8 邊界聲明
- `ADR-2026-07-08-semantic-correctness-gate.md`：P0 決策
- `ADR-2026-07-08-cloud-with-local-assist-runtime-promotion.md`：P1 決策
- `ADR-2026-07-08-local-cascade-controller.md`：P2 決策
- `ADR-2026-07-08-quota-monitor-runtime-degradation.md`：P3 決策
- `ADR-2026-07-08-knowledge-agent-evoreason-autoreason.md`：P4 決策
- `ADR-2026-07-08-paw-compiler-seam-fuzzy-bug.md`：P4-4 決策
- `ADR-2026-07-08-shepherd-supervisor-sub-agent.md`：P4-3 決策
- `ADR-2026-07-08-daily-public-regression.md`：P5 決策

### 7.3 與既有 ADR/教訓的對位
- 引用 `ADR-2026-05-14-nexus-wearing-gate-stabilization.md`：phase 8 全部納入 wearing-gate 邊界
- 引用 `ADR-2026-05-07-route-ab-infra-invalid-lesson.md`：P5 重建 capability_ab_runner 必須避免 route AB infra 污染
- 引用 `Ops - Learning Closure Matrix.md` 內「`mcp malformed-response test mismatch`」與「`Real-world LLM format drift in Shadow Eval`」：P1 升級 cloud_with_local_assist 必須含 robust parser
- 引用「`Plan patch anchor drift`」：P1 改 prompt contract 必須用 heading/line range 重定位
- 引用「`Optional dependency blocks local autonomy`」：P4 PAW / AUTOMEM 必須可降級，不作為硬依賴
- 引用「`SF Overlay Fixture Verdict Drift`」（2026-05-20）：P5 daily regression 必須用 cleaned contract，不能用 raw verdict
- 引用 `C6BC forensic`（`docs/reports/c6bc_post_apply_semantic_gap_forensics.md`）：P0 semantic gate 直接接 C6BC recommendation `assertion-grounded prompt patch`

## 8. 結語

Phase 8 的目標是把 Nexus 從「**零件齊全但編排散落**」升級為「**模型提案合約 + 驗證治理鏈 + 編排主迴圈**」的雙模式修復系統。全程在 `28_V28_ARCHITECTURE_FREEZE.md` 與 `CapabilityPlanner Downstream Enforcement` 邊界內，只把分散的 100+ 模組 + 3 篇論文級能力（AUTOMEM / SHEPHERD / PAW）編排成「Nexus 雙模式修復系統」。

最終驗收：
- Cloud Model + Nexus > bare cloud：5 月 12/12 vs 8/12 + 每日 regression 持續不退步
- Local Model + Nexus ≈ bare cloud：semantic correctness gate 通過 + P5 證據
- Cloud unavailable → local armor：Quota Monitor 自動降級 + 降級 receipt 有原因鏈
- Cloud quota low → 減少 cloud usage：Degradation Controller 切換 + Claim Gate 拒絕 local_only claim
- 不繞過 hash-chain / isolation / verifier / receipt / claim gate：12 個不可變規則全保留
- Local Model 4 角色：diagnosis (3B) / anchor scorer (3B) / cheap verifier (9B) / fallback repairer (cascade) 全部真實呼叫
- Cloud Model 穿 Nexus armor：Cloud 吃 ≤500 chars compact prompt
- Model-agnostic repair operating layer：CapabilityPlanner 不變，CEO 永遠是 CEO，workers 可換
- Knowledge Agent 4 子能力：EvoEmbedding + AUTOMEM + SHEPHERD + PAW 全部可選啟用
