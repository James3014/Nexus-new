---
aliases:
- Split Repo Diff
- Legacy vs Split Family
- Capability Disposition 2026-10
confidence: high
last_compiled: '2026-10-12'
owner: agent
related_pages:
- '[Diff - v17.1 vs v22 vs v23](Diff - v17.1 vs v22 vs v23.md)'
- '[Code_to_Wiki_Alignment_Matrix](Code_to_Wiki_Alignment_Matrix.md)'
- '[CAPABILITY_EVIDENCE_LEDGER_2026-10-12](../04_State/CAPABILITY_EVIDENCE_LEDGER_2026-10-12.md)'
- '[CURRENT_STATE](../00_Home/CURRENT_STATE.md)'
source_of_truth: James3014/Nexus-new@0fb15f3e1, James3014/nexus-runtime@cfcb38d, James3014/nexus-learning@9a0eadf, James3014/nexus-core@f0909e9 (origin/main, observed 2026-10-12)
status: active
tags:
- diff
- split
- repo-family
- capability
- regression
title: Diff - Legacy Monolith vs Split Repo Family (2026-10-12)
type: diff
version_scope:
- v28
- split-2026-09
---

# Diff - Legacy Monolith vs Split Repo Family (2026-10-12)

## One-sentence summary
本頁以 2026-10-12 的實體程式碼稽核為準，逐一對照舊單體 (`nexus/` 套件) 的每項能力在拆分後的 repo 家族 (Nexus-new / nexus-runtime / nexus-learning / nexus-core) 中「住在哪裡、有沒有接線、有沒有量測」，並登記四個拆分後真正退步的點。 [Source: nexus_wiki_vault/08_Diffs/Code_to_Wiki_Alignment_Matrix.md] [Code: nexus/core/capability_executor_registry.py]

> [!important] 結論先行
> 拆分**沒有刪除任何能力程式碼**。Nexus-new 仍完整攜帶 `nexus/` 套件 (origin/main 1443 檔) 與同一支 live CLI (`scripts/engine/nexus_cli.py`，所有舊命令仍註冊)。nexus-core / nexus-learning / devspace / RIE **都不含**任何引擎實作。真正退步的是下方 §四個具體回歸，而大多數「舊版突破」在舊 wiki 自己的 AM3 再稽核中早已被判定為幻影或未接線（見 [CAPABILITY_EVIDENCE_LEDGER_2026-10-12](../04_State/CAPABILITY_EVIDENCE_LEDGER_2026-10-12.md)）。

## Role / responsibility
- **能力對位**: 回答「某能力拆分後在哪裡」，分清 *legacy copy only*（位元相同）、*evolved in-repo*（已在 Nexus-new 內演進）、*extracted*（搬到新套件並以 facade 回指）三種情況。 [Code: nexus/learning/outcome_memory.py]
- **接線判定**: 區分 Nexus-new CLI 路徑 (`EXECUTOR_REGISTRY`) 與 nexus-runtime 路徑 (planner node + contract table) 的接線狀態；兩者不可混為一談。 [Code: nexus/services/capability_registry.py]
- **回歸登記**: 把四個可修復的退步點寫成帶檔案路徑與行號的工單素材，供後續 PR 引用。 [Source: nexus_wiki_vault/01_System/System - Unknowns and Conflicts.md]

## Repo family after the split (observed 2026-10-12)

| Repo | Role (per its own docs) | What it physically holds | Source |
|---|---|---|---|
| `Nexus-new` | `LEGACY_INTEGRATION_LAB` + Compatibility Host；route decision authority 仍在此 | 完整 `nexus/` 套件、live CLI、`EXECUTOR_REGISTRY` (4078 行)、27 個 planner 模組已改為 `install_alias` 回指 runtime | [Source: docs/architecture/REPOSITORY_BOUNDARIES.md] [Source: docs/architecture/PLANNER_RUNTIME_LAYERING_WAVE2.md] |
| `nexus-runtime` | planner source owner + execution coordination；`runtime_is_planner_authority = false` | planner nodes、capability contract table (2773 行)、`ExecutionCoordinator`；**無任何能力引擎**，零 `from nexus.` import | `nexus-runtime/AGENTS.md`, `nexus-runtime/docs/PLANNER_RUNTIME_LAYERING.md` [Source: docs/architecture/PLANNER_RUNTIME_LAYERING_WAVE2.md] |
| `nexus-learning` | evidence-bounded learning；"Recommendation != Authority" | 21 個檔案：episode projection、closure effectiveness、outcome_memory、lessons、adoption；MIGRATION_MATRIX 55 列 = 8 CANONICAL_ADAPT / 20 LEAVE_IN_NEXUS_NEW / 27 LAB_ONLY | `nexus-learning/MIGRATION_MATRIX.md`, `nexus-learning/EXTRACTED_FROM.md` [Source: docs/architecture/LEARNING_CONSUMER_CUTOVER.md] |
| `nexus-core` | `nexus-certify` 完成驗證閘 | `product/` 175 檔，全是 lifecycle / certification / benchmark 產品；與本頁任何能力無對應 | `nexus-core/EXTRACTED_FROM.md` [Source: docs/architecture/EXTRACTION_PROVENANCE.md] |
| `devspace`, `repository-intelligence-engine` | 執行傳輸 / PR 顧問 | 對本頁所有能力名稱零命中（`devspace/src`, RIE 全文 grep） | [Source: docs/architecture/AI_CONTROL_PLANE_BOUNDARY.md] |

## Capability disposition matrix

狀態欄定義：**WIRED-NN** = 可從 Nexus-new live CLI 或 `EXECUTOR_REGISTRY` 抵達；**RT-BLOCKED** = nexus-runtime 僅有 planner node，執行器綁定失效（見回歸 R1）；**stub** = 可抵達但主體空心。證據欄取自 [CAPABILITY_EVIDENCE_LEDGER_2026-10-12](../04_State/CAPABILITY_EVIDENCE_LEDGER_2026-10-12.md)。

| Capability | Legacy module (nexus/) | Where it lives now | Wiring | Evidence status |
|---|---|---|---|---|
| CodeIntel | `services/codeintel/*` (~1045 LOC) | Nexus-new evolved copy (`impact_service` 位元相同)；runtime 只有 `request.codeintel` 透傳 | WIRED-NN；RT planner-only | legacy P37 receipts 12/12；拆分後未量測 |
| Research route / auto-flow | `app/research_flow_service.py` (1960) | Nexus-new 1972 行 (diverged) | WIRED-NN | 未量測 |
| Hyper / Sprint | `research/sprint_service.py` (2093), `local_sprint_mutator.py` | Nexus-new 2113 行；`local_sprint_mutator` 位元相同 | WIRED-NN (僅經 auto-flow)；RT-BLOCKED | 未量測 |
| Nightshift | `app/nightshift_runner_service.py` (1282) | Nexus-new 1511 行 (diverged)；`ba1cc6a71` 加 opt-in auto-Nightshift | WIRED-NN (無直接命令)；RT-BLOCKED | phantom-per-P37（5 selected / 0 invoked） |
| Swarm / multi-agent / file lock | `core/swarm.py`, `orchestrator/worktree_manager.py` (2079) | Nexus-new `worktree_manager` 4119 行；Go `nexus-swarm-v22-prod` 已封存 (`d8d7a842f`)；`nexus delegate` 退役 | WIRED-NN；RT-BLOCKED | phantom-per-P37（4 selected / 0 invoked） |
| Drone | `core/drone_engine.py` (350) | Nexus-new 380 行；新增 `nexus drone run` | WIRED-NN；RT-BLOCKED | #1763：HUD 曾寫假資料（10-11 修正） |
| Ultra Review | `engine/ultra_review_service.py` (885) | Nexus-new 888 行 | WIRED-NN；RT-BLOCKED | #1763：dry-run only；`ci_gate.py` 步驟仍判 unverified |
| Autoreason | `engine/autoreason_service.py` (482) | Nexus-new 位元相同 | WIRED-NN (indirect)；local_heal 內為 advisory-only；RT-BLOCKED | AM3 NOT_WIRED (2026-06)；A/B 收據中分數恆為 6.0 / 5.0 |
| DDTree | `engine/ddtree_adapter.py` (101) | Nexus-new 位元相同 | WIRED-NN (indirect)；RT-BLOCKED | legacy 2/12 eligible rows；未量測 |
| LanceDB / Memory / Findings | `services/memory_repository.py` (251), `research/findings_memory.py` | Nexus-new 454 行 + 新 `services/lancedb_roots.py`；runtime 僅 read-port `MemoryRepositoryLessonStore` | WIRED-NN | NEUTRAL（舊 2026-06 與新 2026-10 皆中性） |
| MemPalace / Policy / Capability Gate | `services/mem_palace.py` (178) | Nexus-new 184 行 (+`constraints_source`)；`nexus-mempalace/` 目錄為空、gitlink 自指 | WIRED-NN (floor capability) | #1763：belief constraints 恆空 → `0fb15f3e1` 補 producer |
| Belief | `core/belief_engine.py` (85), `core/belief_contracts.py` | engine 位元相同留 Nexus-new；contracts 以 alias 指向 runtime `planning/core/belief_contracts.py`；v0.2 writer `d8d7a842f` | WIRED-NN | A/B 收據 373/502 筆 `uncertainty_delta = 0` |
| Artifact / Claim / Delivery / Acceptance | `delivery/*`, `research/learn/claim_service.py` | Nexus-new 位元相同；`claim_boundary` alias → runtime | WIRED-NN；`delivery_gate` 由 runtime online postflight 持有 | AM3 RECEIPT_ONLY |
| Pregate / Forecast / Plan Quality | `engine/cli_pregate.py` (211) | Nexus-new 286 行；forecast_gate e2e `31f19831a` | WIRED-NN，無 CLI | 未量測 |
| Sandbox / Replay | `engine/sandbox_runner.py` (558) | Nexus-new 位元相同 | WIRED-NN | 未量測 |
| Benchmark / Meta-Opt | `app/research_benchmark_service.py`, `services/benchmark_service.py` | Nexus-new；meta-opt preset consumer 僅 auto-flow opt-in (`3a0065f64`) | WIRED-NN；`_exec_meta_opt` 無 episode 即 BLOCKED | NOT CITABLE（#1762：亂數與常數 1.0） |
| Learning Closure | `services/local_heal/learning_closure_bridge.py` (587) | canonical 搬到 nexus-learning；Nexus-new 816 行 bridge + facade | WIRED-NN；`_exec_learning_closure` 僅 `class_instantiated` | 91 episodes / 40 retrieved / 0 applied / 0 uplift (2026-10-08) |
| Regression Guard | `scripts/bench/capability_regression_guard.py` | Nexus-new 位元相同 | UNWIRED（離線腳本，無 CLI、無 executor、無 planner node） | 未量測 |
| Autonomic Router | `engine/autonomic_routing_service.py` (105) | Nexus-new 位元相同；runtime `lite_route_oracle` + probe "route_probe_not_production_execute" | WIRED-NN | legacy MSA A/B（Unknown Correct Rate 0%→100%）；拆分後未量測 |
| Mission Control | `core/mission_contracts.py` (126) | Nexus-new 170 行 + `mission abort` | WIRED-NN | n/a |
| XRay | `core/xray_observer.py` (161) | Nexus-new 位元相同；無 CLI | WIRED-NN (indirect)；RT-BLOCKED | n/a |
| Metabolism (distill / resume) | `services/metabolism_engine.py` (93) | Nexus-new 位元相同；`distill` 蒸餾一個字面 dict | WIRED-NN (stub) | n/a |
| Oracle shadow apply | `oracle/promote.py` (32), `services/aos_oracle.py` | Nexus-new 標 lab-only + DeprecationWarning；`promote` 只能 patch 寫死的 `oracle_test.py` | WIRED-NN (stub)；RT EXPERIMENTAL_NOT_PROMOTED | n/a |
| Federation / nexus-evolve | `federation/*` (255), `fed-run` 36 行引擎 | Nexus-new 同檔；`nexus-evolve` 只是指向 CLI 的 symlink | WIRED-NN (stub)；RT EXPERIMENTAL_NOT_PROMOTED | v22 "100 PR P95 2.8s" 不可重現 |
| UI Validator / Stress Test | `scripts/ui-validator.py`, `engine/red_team_audit.py` | Nexus-new；`red_team_audit` 三個探針恆回 PASS | WIRED-NN (stub) | NOT CITABLE |
| LAB_ONLY 預測器 (latent_predictor_v20, lewm_predictor, router_nas_tuner, bandit pool, skill_fit_*, federated_rag) | `learning/*` | Nexus-new 位元相同；**但** `engine/coordinator.py:26`, `engine/bootstrap.py:12/32`, `engine/self_healing_selector.py`, `_exec_forecast_gate` 仍 import latent/lewm | 矩陣標 LAB_ONLY，實際仍 live（`federated_rag` 零 importer，真死碼） | 未量測；矩陣理由無任何數據 |

## 四個具體回歸 (R1–R4)

| ID | Regression | Physical evidence | Fix (status 2026-10-12) |
|---|---|---|---|
| **R1** | nexus-runtime 執行器綁定失效：`build_real_executor_invoker` 與 `_has_physical_executor` import 不存在的 `nexus_runtime.support.core.capability_executor_registry`（`belief_contracts` 實際在 `planning/core/`），try/except 吞掉後永遠回 None，所有 escalate-gated 能力 (hyper, swarm, nightshift, drone, xray, ddtree, autoreason, metabolism, ultra_review) 在 runtime/gateway 路徑一律 `BLOCKED_EXECUTOR_UNAVAILABLE`。無測試覆蓋。 | `nexus-runtime@cfcb38d src/nexus_runtime/support/services/capability_registry.py:1340, 1735-1736`；`git ls-tree origin/main` 無 `support/core/` | nexus-runtime #163（merged `a6801a99b`，executor resolver 注入縫取代死 import）+ Nexus-new #1824（merged，runtime_compat 註冊 resolver，pin bump 前為 no-op）。**runtime 路徑要等下一次 canonical-runtime pin bump 才真正解封** |
| **R2** | 新實驗在「裝甲關閉」下執行：記憶 A/B runner 直接呼叫 `nexus.services.local_heal`，不經 CapabilityPlanner。本機 502 份收據全部 `with_nexus_armor=false`、`p4_committee_invoked=false`、`consumption_chain` 僅 `local_heal_repair`。 | `Nexus-new scripts/eval/run_memory_ab_v1.py` L209-223；`artifacts/runtime/memory_ab_v1/*/reports/local_heal/*/receipt.json` | Nexus-new #1830（merged，記憶 A/B runner 加 `--armor on/off` 軸與 `capabilities_invoked` 收據欄） |
| **R3** | 唯一有可信 uplift 的 Gemini 同模型 A/B 車道停擺：`scripts/bench/with_nexus_runner.py` 自 2026-05-23 未動，2026-08 後無任何報告；planner 於 10-11/12 改為 alias shim 後未驗證可跑。 | `git log origin/main -1 -- scripts/bench/with_nexus_runner.py` = `74f900aa0 2026-05-23` | Nexus-new #1825（merged，同模型 A/B 車道復活並強制 strict LLM baseline） |
| **R4** | 自適應機制整批凍結無量測：MIGRATION_MATRIX 27 列 LAB_ONLY 理由皆為一行 "prohibited / experimental"，未引用任何實驗；同時 Nexus-new 引擎仍 import 其中 latent/lewm，矩陣與現實不符。 | `nexus-learning/MIGRATION_MATRIX.md`；`Nexus-new nexus/engine/coordinator.py:26`, `bootstrap.py:12` | Nexus-new #1831（merged，latent / lewm 開關、`predictor_influence` 收據、消融腳本）+ nexus-learning #99（merged，MIGRATION_MATRIX 兩列改為量測結果） |

> [!note] 同日相關變更
> Nexus-new #1836 與 nexus-runtime #165（皆 merged）把 `model_workforce.yaml` 對齊 M5 推理主機；與 R1–R4 無關，但影響任何本地模型實驗的執行位置。

> [!note] 非回歸的誤判
> 舊 clone `nexus/services/mem_palace.py` 的 `admission_binding()` sha256 綁定在 Nexus-new 不存在，但那是**從未 commit 的本機修改**（`git status` 顯示 ` M`），不是拆分遺失。

## Upstream
- **[CURRENT_STATE](../00_Home/CURRENT_STATE.md)**: 提供 2026-10-08 的各 repo 修訂快照與證據天花板。
- **[Diff - v17.1 vs v22 vs v23](Diff - v17.1 vs v22 vs v23.md)**: 拆分前的版本演化矩陣。
- **[nexus_能力盤點_2026-02-20後新增](../02_Modules/nexus_能力盤點_2026-02-20後新增.md)**: 198 列能力盤點（~134 wired / ~56 standalone）的拆分前基線。 [Source: nexus_wiki_vault/02_Modules/nexus_能力盤點_2026-02-20後新增.md]

## Downstream
- **[CAPABILITY_EVIDENCE_LEDGER_2026-10-12](../04_State/CAPABILITY_EVIDENCE_LEDGER_2026-10-12.md)**: 每個標題數字的可引用性判定。
- **[System - Unknowns and Conflicts](../01_System/System - Unknowns and Conflicts.md)**: C-10 ~ C-13 登記本頁發現的術語與矩陣衝突。
- **[System - Next Questions for Human](../01_System/System - Next Questions for Human.md)**: Q-04 ~ Q-06 需要人類決策的 LAB_ONLY 解凍與 runtime 綁定方式。

## Related modules / files
- `nexus/core/capability_executor_registry.py`: Nexus-new 端真實執行器（`_exec_*`）。 [Code: nexus/core/capability_executor_registry.py]
- `nexus/services/capability_registry.py`: Nexus-new 端 planner node → invoker 對照，與 runtime 版本為同源複本。 [Code: nexus/services/capability_registry.py]
- `nexus-runtime/src/nexus_runtime/support/services/capability_registry.py`: runtime 端複本，R1 所在。
- `nexus-learning/MIGRATION_MATRIX.md`: 學習模組 55 列處置表。
- `scripts/eval/run_memory_ab_v1.py`: 記憶 A/B runner（R2）。 [Code: scripts/eval/run_memory_ab_v1.py]
- `scripts/bench/with_nexus_runner.py`: Gemini A/B 車道（R3）。 [Code: scripts/bench/with_nexus_runner.py]

## Source notes
- 本頁由 2026-10-12 五路唯讀稽核彙整：舊 wiki 突破盤點、新架構遷移文件、程式碼存在性稽核 ×2（含 legacy vs Nexus-new 位元比對）、實驗證據比對。所有 LOC 與行號以 Nexus-new `0fb15f3e1`、nexus-runtime `cfcb38d` 為準。 [Source: nexus_wiki_vault/10_Analysis_Scans/nexus_am3_post_al_capability_reaudit_20260621.md]
- 「phantom-per-P37」指 `CAPABILITY_ROUTING_MIGRATION_PLAN_2026-04-29` 記錄的 selected_without_invocation。 [Source: nexus_wiki_vault/09_Roadmap/CAPABILITY_ROUTING_MIGRATION_PLAN_2026-04-29.md]
- 「#1763 / #1762」指 Nexus-new GitHub issues（2026-10-11 能力接線稽核與模擬評測冒充量測）。 [Source: HANDOFF.md]

## Open questions / conflicts
- [ ] R1 修法：runtime 端注入 resolver（保持 runtime 不 import `nexus.*`）是否與 Phase 4b「runtime_compat 不注入 factory」的決議相容？
- [ ] LAB_ONLY 27 列中除 latent/lewm 外，其餘是否逐一補量測或正式宣告死碼？
- [ ] `nexus-mempalace` gitlink 自指 (`.gitmodules` URL = `.`) 應移除或補真實來源？
- [ ] Nexus-new 與 nexus-runtime 的 `capability_registry.py` 同源複本是否應收斂為單一 owner？

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]
