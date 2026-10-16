# H7-1 Capability Routing Truth Source Seam Map v0

**日期**: 2026-06-25  
**狀態**: `H7_1_CAPABILITY_ROUTING_TRUTH_SOURCE_SEAM_MAP_DRAFT_READY_FOR_REVIEW`  
**治理/安全**: `NO_RUNTIME_BEHAVIOR_CHANGE`, `NO_PROVIDER_CALL`, `NO_MODEL_CALL`, `NO_MODEL_LOAD`, `NO_PROCESS_SPAWN`, `NO_NETWORK_CALL`, `PUBLIC_CLAIM_ALLOWED=false`  

> **安全聲明**: 本報告為純 audit/report-only 產出。本任務期間未新增任何 runtime routing behavior、未啟用 learned policy、未啟動 provider/model/network/model-load/model-call。H7 仍處於 planning-only 階段。

---

## 0. Status / Safety Boundary

本報告嚴格遵守以下安全防禦邊界：
* **status**: `H7_1_CAPABILITY_ROUTING_TRUTH_SOURCE_SEAM_MAP_DRAFT_READY_FOR_REVIEW`
* **no runtime behavior change** (不改變執行期行為)
* **no provider call** (不呼叫 provider)
* **no model call** (不進行模型調用)
* **no network call** (不啟用網路)
* **no model load** (不載入模型)
* **no model execution** (不執行模型)
* **no learned policy adoption** (不啟用學習策略)
* **no new router** (不新增路由器)
* **production_ready=false**
* **public_claim_allowed=false**
* **H7 runtime not started** (H7 執行期尚未啟動)

---

## 1. Scope

本報告專注於靜態分析與對齊現行 Nexus 17 個核心選路、特徵、憑證、學習及治理 primitives 之職責分工（Seam Mapping），以建立明確的真值源決策。
* **H7-1 is report-only**: 本任務不包含任何 runtime 程式變更。
* **H7-1 does not change routing behavior**: 不變更任何執行期分發路徑。
* **H7-1 does not adopt learned policy**: 所有OutcomeMemory 與 S2T 策略均保持唯讀，不寫入生產配置。
* **H7-1 does not authorize provider/model runtime**: Provider 邊界維持 deny-by-default。
* **H7-1 does not resolve U3 candidate isolation gaps**: 不解決 U3 候選隔離雜湊缺口，僅進行結構映射。

---

## 2. Current Workspace Contamination

**H7-1 artifact itself is report-only, but the workspace is not clean and contains unrelated staged/modified production, test, config, artifact, CI, and generated-data changes. H7-1 acceptance is scoped only to this report artifact; unrelated dirty files must not be committed with H7-1.**

目前 dirty 檔案清單包括：
* `.gitnexusignore`
* `artifacts/runtime/**`
* `nexus/experimental/__pycache__/**`
* `nexus/services/local_heal/*`
* `tests/unit/local_heal/*`
* `pyproject.toml` 與 `uv.lock`
* `.github/workflows/*`
* `scratch/*`

本報告被核准後，若要進行 commit，**只能包含**：
`docs/reports/h7_1_capability_routing_truth_source_seam_map_v0.md`

---

## 3. Primitive Seam Map

本表格靜態映射 Nexus 現行之 17 個選路相關 primitives，對其 Owner 模組、當前職責、調用路徑、輸出、重疊衝突及 H7 目標進行整理：

| Primitive | Owner module | Exists? yes/no/missing_or_moved | Current responsibility | Current call path | Current receipt/evidence output | Truth-source status | Overlap/conflict | Recommended H7 role | Runtime adoption allowed? yes/no | Reason | Missing tests / gaps |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **A. CapabilityPlanner** | `nexus/engine/capability_planner.py` | yes | 裝配訊號與政策，動態規劃能力執行清單 | Agent main / benchmark | `CapabilityPlan` 物件 | `route_truth_source` | 與 `AutonomicRouter` 存在能力選路規劃 overlap | 唯一選路決策 settlements 機制 | yes | 現行能力調度的核心 settlements 中心 | 缺少對 `_apply_s2t_policy_promotion` 的 E2E 整合測試 |
| **B. CapabilityPlan** | `nexus/engine/capability_contracts.py` | yes | 記錄 planner 動態規劃出的能力清單（含 selected, required, forbidden 等） | planner.plan() | `CapabilityPlan` 物件 | `route_truth_source` | 與 `RouteDecision` 存在概念重疊 | 選路結果的強型別承載載體 | yes | 屬靜態資料結構，無 runtime 副作用 | 缺少 serialization/deserialization 測試 |
| **C. CapabilitySignalSet** | `nexus/engine/capability_signals.py` | yes | 蒐集任務、風險、記憶體等訊號以供 planner 選路參考 | planner.plan() | `CapabilitySignalSet` 物件 | `signal_source`, `evidence_source` | 部分關鍵字與特徵提取邏輯與 `AutonomicRouter` 重複 | 唯讀 `signal_source` | yes | 純特徵萃取，不影響狀態 | 缺少對 LanceDB 特徵與 signal set 映射的穩定性測試 |
| **D. CapabilityContracts** | `nexus/engine/capability_contracts.py` | yes | 定義 planner、receipt 與 decision 的強型別合約定義 | across engine modules | Strongly-typed dict / JSON schemas | `evidence_source`, `receipt_truth_source` | 無 | 靜態合約型別 SSOT (定義層) | yes | 屬靜態定義，對 runtime 無副作用 | 缺少 JSON schema validation 單元測試 |
| **E. RouteDecision** | `nexus/engine/capability_contracts.py` | yes | 儲存選路最終決策，供留檔與學習審計 | planner.plan() -> archive | `RouteDecision` 物件 | `route_truth_source` | 與 `CapabilityPlan` 在選路結果上有 overlap | 決策歸檔真值源 | yes | 結構化決策存檔，供後續 shadow 學習讀取 | 缺少對 decision_trace 的 schema 檢驗測試 |
| **F. CapabilityReceipt** | `nexus/engine/capability_contracts.py` | yes | 記錄能力執行的真實狀態 (含 invoked, gate_passed 等)，判定 public claim 安全性 | capability_receipts.py | `CapabilityReceipt` 物件 | `receipt_truth_source` | 與 `SkillReceipt` 存有職責 overlap | 執行憑證之真值源 | yes | 屬憑證型別，供自癒與學習作客觀判定 | 缺少 `public_claim_safe` telemetry 邊界條件測試 |
| **G. SkillReceipt** | `nexus/engine/capability_contracts.py` | yes | 記錄特定 Skill 的注入、使用與成果狀態 | capability_receipts.py | `SkillReceipt` 物件 | `receipt_truth_source` | 與 `CapabilityReceipt` 存有部分 overlap | Skill 憑證之真值源，禁止干涉選路 mode | yes | 提供細粒度 Skill 憑證 | 缺少對 selected_without_injection 的單元測試 |
| **H. AutonomicRouter** | `nexus/engine/autonomic_router.py` | yes | 藉由 policy_memory 匹配，試圖判定 ExecutionPlan 模式 | test / legacy paths | `ExecutionPlan` 物件 | `facade_only`, `duplicate_or_overlap`, `unsafe_to_runtime_adopt` | 其選路機制與 `CapabilityPlanner` 嚴重 overlap | 降級為唯讀的 autonomic_signals facade | no | 變更執行期狀態，易引發選路衝突 | 缺少將其降級並移除 mode-changing 邏輯的測試 |
| **I. S2T policy / S2TAdoptionDecision** | `nexus/contracts/s2t_policy.py` | yes | 選拔 S2T 候選並利用 shadow 評估是否可升級 `strict_opt_in` | shadow evaluation | `S2TAdoptionDecision` / `S2TSelectionDecision` | `policy_loader`, `governance_gate` | 部分策略解析與 `learning_policy_loader` 重複 | 唯讀 `governance_gate` 與 shadow `policy_loader` | no | 屬學習成果，需透過 Planner 整合 settling，禁止 runtime override | 缺少 `S2TStrictGate` 不同 risk profiles 的 fail-closed 單元測試 |
| **J. OutcomeMemory** | `nexus/learning/outcome_memory.py` | yes | 記錄任務成果並動態加權評估能力分數，產出 dynamic policy | save_episode_and_tune() | outcome_history.jsonl / dynamic_learning_policy.json | `learning_trace_source`, `shadow_only` | 部分評分與 S2T 有 overlap | 學習歷程之唯讀 shadow trace 來源 | no | 屬於後續學習，僅作為規劃參考，不得 runtime override | 缺少並行寫入衝突與排除 `trust_mismatch` 的測試 |
| **K. learning_policy_loader** | `nexus/engine/learning_policy_loader.py` | yes | 載入並 merge 磁碟上的學習政策與成本政策至執行期 budget 中 | capability_planner.plan() | Merged policy dict | `policy_loader` | 載入邏輯與 planner 內部有些微重疊 | 唯讀 `policy_loader` | yes | 純唯讀載入配置，前題是 enforce_penalties=false | 缺少環境變數被修改時對 `protect_expected_capability_controls` 的安全測試 |
| **L. HallucinationGuard** | `nexus/governance/hallucination_guard.py` | yes | 比對回覆與 evidence，偵測並攔截幻覺宣稱 | governance audit gate | Verdict dict, score, markdown | `governance_gate` | 與 `ClaimGate`/`ArtifactGate` 有 overlap | 獨立幻覺治理閘，若有違規僅作 audit/reject | yes | 安全防禦閘，對狀態無副作用 | 缺少對「有錯誤宣稱但 artifact 缺失」的邊界評分測試 |
| **M. lesson_retrieval / lesson_writeback** | `nexus/services/lesson_retrieval.py` | yes | pre-flight 時利用 keyword & vector 檢索教訓以增寫 prompt | pre-flight / CI | List of lesson dicts/texts | `learning_trace_source`, `audit_only` | 與 LanceDB 向量庫以及 OutcomeMemory 有概念重疊 | 唯讀 prompt context 注入器 | yes | 僅增強 LLM context，不影響選路決策 | 缺少檢索 Consensus Engine 結果衝突時的決策測試 |
| **N. RLM controller / RLM receipt** | `nexus/engine/rlm_controller.py` | yes | 負責 X/R 迭代控制與 token/iteration budget 計算 | research_flow_service | RLM receipts / Nightshift handoff | `receipt_truth_source`, `evidence_source`, `shadow_only` | 與 `SelfHealingSelector` 有控制邏輯重疊 | 熔斷預算管理器，保持 `bounded_adapter_not_dispatch` | yes | 僅限 shadow 憑證與預算記錄，禁止 runtime 遞迴分發 | 缺少遞迴 depth 超出 budget 時的熔斷單元測試 |
| **O. verifier / claim gate / artifact gate** | `nexus/delivery/evidence_verifier.py` | yes | 系統級獨立驗證器與治理閘，確保 artifacts 符合 safety 合約 | audit evaluate stage | `VerificationResult` / gate receipts | `governance_gate`, `evidence_source` | 邏輯與 `HallucinationGuard` 有 overlap | 核心治理防禦閘，fail-closed | yes | 核心治理防禦，必備 fail-closed 閘 | 缺少獨立的 Mock Verifier 整合測試 |
| **P. MemPalace / memory gate** | `nexus/services/mem_palace.py` | yes | 稽核 memory-centric state，確保狀態安全性 | audit stage | `MemPalaceGateReceipt` | `governance_gate`, `evidence_source` | 與 `OutcomeMemory` 存在 overlap | 記憶體治理閘，唯讀稽核 | yes | 屬於安全防禦與記憶體邊界治理 | 缺少針對多線程寫入下的 memory gate 壓測 |
| **Q. TaskRecoveryState / RecoveryState** | `missing_or_moved` | no | 當前專案中無此 runtime modules 定義，僅有規劃草案 | 無 | 無 | `unsafe_to_runtime_adopt` | 易與現行的 `RouteDecision` 及 `CapabilityReceipt` 造成狀態衝突 | 唯讀 `recovery_projection_candidate` (規劃草案) | no | 當前無實體定義，且缺乏 candidate isolation 防禦，H7 禁止影響選路 | 缺乏對應的單元與整合測試 |

---

## 4. Truth Source Decision

本 seam map 表明 Nexus 在選路與自癒治理上必須確立以下決策：

1. **CapabilityPlanner / RouteDecision 是唯一的 routing truth-source 候選**。所有的選路決策（selected, required, forbidden 等）均應由 CapabilityPlanner 進行 Settlements，並歸檔至 RouteDecision。其他任何路由器或學習政策載入器均不得在執行期繞過 Planner 或變更 mode。
2. **CapabilitySignalSet 僅能作為 signal_source**。它不擁有任何選路決策權，亦不能繞過 Planner 的 policy 規則。
3. **CapabilityReceipt / SkillReceipt 是唯一的 receipt_truth_source 候選**。它們是執行結果的客觀憑證，用於判定 `public_claim_safe`。
4. **EvidenceBundle / verifier output / artifact gate output 是 evidence_source**。它們提供客觀的事後證據，但不具有路由決定權，僅供治理閘（governance_gate）進行攔截判定。
5. **OutcomeMemory / S2TTraceEvent / learning traces 僅能支援 shadow learning**。它們不得 runtime override 任何選路與執行， enforc_penalties 必須保持為 False。
6. **learning_policy_loader 僅是 policy_loader**。它僅載入被 Promoted 的規則給 planner，其本身不得直接成為 runtime router 或繞過 settlements。
7. **HallucinationGuard / verifier / claim gate / artifact gate / MemPalace gate 必須保持 governance_gate**。它們僅進行唯讀的 audit 與 reject (fail-closed)，絕不能主動重寫選路模式（例如將 mode 覆寫為直接執行）。
8. **AutonomicRouter 不得作為 replacement router**。它目前處於 `facade_only / duplicate_or_overlap / unsafe_to_runtime_adopt` 狀態，應降級為唯讀訊號。
9. **TaskRecoveryState / RecoveryState 不得在 H7 影響選路**。目前在 codebase 中無實體定義，列為 `unsafe_to_runtime_adopt`，僅能作為事後 Recovery 投影（projection-only）規劃，嚴禁影響執行期選路。

---

## 5. Duplicate / Overlap Risk

本節識別並分析至少 5 個重大重疊縫隙（Overlap Seams）：

### 1) CapabilityPlanner vs AutonomicRouter
* **Risk**: 兩個路由器獨立進行選路，導致執行期模式（Mode）衝突與不一致。
* **Current evidence**: `AutonomicRouter` 含模式判定邏輯（`mode = "swarm"`），而 `CapabilityPlanner` 亦有 `_decide_routing_tier` 與能力配置。
* **Recommended H7 handling**: 將 AutonomicRouter 全面降級，取消其 mode-changing 行為，僅在 planner 中將其 matched_policies 作為 inputs。
* **Runtime adoption allowed?**: **no**

### 2) CapabilityReceipt vs SkillReceipt
* **Risk**: 混淆了系統級能力（Capabilities）與細粒度任務工具（Skills）的憑證，導致能力稽核失真。
* **Current evidence**: 兩者在 `capability_receipts.py` 中被分別建立，但在 telemetry 合約上欄位不對齊。
* **Recommended H7 handling**: 嚴格對齊兩者欄位，但 SkillReceipt 不得參與 `public_claim_safe` 的決策權。
* **Runtime adoption allowed?**: **yes** (僅作為各自的憑證 SSOT)

### 3) S2TTraceEvent vs OutcomeMemory
* **Risk**: 兩套獨立的學習歷程收集機制，易產生重複計分與排除邏輯不一致。
* **Current evidence**: `s2t_policy.py` 與 `outcome_memory.py` 各自維護 shadow events 與 EP 歷程。
* **Recommended H7 handling**: 統一由 OutcomeMemory 進行 Episode Outcome 記錄，S2T 專注於 candidate selector 評估。
* **Runtime adoption allowed?**: **no**

### 4) learning_policy_loader vs runtime routing
* **Risk**: 載入的 policy 被錯誤提升為 runtime selector，繞過了 planner 的安全限制（如 denied by default 邊界）。
* **Current evidence**: `learning_policy_loader` 會嘗試從 `.nexus/memory/dynamic_learning_policy.json` 載入 promoted 列表。
* **Recommended H7 handling**: 確保載入器載入的規則為 Planner 的唯讀 inputs，且預設 `enforce_penalties=false`。
* **Runtime adoption allowed?**: **no** (僅允許唯讀載入配置，不啟用新 policy)

### 5) HallucinationGuard/verifier gates vs routing decision adoption
* **Risk**: 治理閘與選路邏輯混雜，導致治理閘被繞過或在選路中被弱化。
* **Current evidence**: 部分 verifier/gate 狀態被轉換為 `CapabilityReceipt` telemetries，與 `public_claim_safe` 深度綁定。
* **Recommended H7 handling**: 保持治理閘獨立，治理閘之 Verdict 必須是 immutable 且 fail-closed，不可被 planner 策略動態調低。
* **Runtime adoption allowed?**: **yes** (僅限唯讀 audit / fail-closed，不影響路由選取狀態)

### 6) RecoveryState vs RouteDecision
* **Risk**: 復原狀態（RecoveryState）若能覆寫選路決定，將在沒有 candidate isolation 情況下造成 execution drift。
* **Current evidence**: Codebase 中目前無 TaskRecoveryState 的實體定義。
* **Recommended H7 handling**: 規定 RecoveryState 僅能是 RouteDecision 的 read-only projection，絕不能在 runtime 修改路由決策。
* **Runtime adoption allowed?**: **no**

### 7) lesson_writeback vs policy adoption
* **Risk**: 未經 verifier 的 lesson writeback 直接寫回生產線，破壞規則生命週期治理。
* **Current evidence**: `lesson_writeback_check.py` 僅在 CI 作為靜態 check。
* **Recommended H7 handling**: Lesson writeback 必須嚴格保持為 CI 靜態稽核與唯讀 prompt 注入，禁止 runtime 變更選路配置。
* **Runtime adoption allowed?**: **no**

---

## 6. H7 Routing Consolidation Rule

為確保 Nexus 選路系統收斂，應遵守以下六大收斂鐵律：
1. **One route truth source**: 選路規劃之 settlements 真值源僅限於 CapabilityPlanner 與 RouteDecision。
2. **One receipt truth source per decision type**: 能力執行憑證僅限 `CapabilityReceipt`，任務細粒度工具僅限 `SkillReceipt`
3. **Signal can inform route, but signal cannot own route**: 特徵訊號（如 CapabilitySignalSet）僅供規劃參考，不具選路決策權。
4. **Learning can propose, but learning cannot adopt**: 所有 shadow 學習與 OutcomeMemory 只能產出 draft policy 訊號，預設 `enforce_penalties=false`，不可 runtime 自動變更路由行為。
5. **Governance gate can block, but not silently rewrite route**: 治理閘（如 HallucinationGuard、verifier）如果失敗必須直接 fail-closed，不得私自將 mode 修改或降級為非受管模式。
6. **Recovery can project state, but not become routing authority**: 自癒復原僅能投影現有 RouteDecision / CapabilityReceipt 狀態，不得超越或修改 routing constraints。
7. **Provider/model execution remains denied by default**: 任何 provider/model/network 調用預設依然被全面封鎖，保持 deny-by-default。

---

## 7. H7-2 Candidate Tasks

為安全推進下一階段，規劃以下 H7-2 任務清單（均為 safe / report-only / test-only，不包含 runtime 程式變更）：

1. **H7-2 Capability Receipt Field Alignment Audit**: 審計並對齊 CapabilityReceipt 與 SkillReceipt 欄位，特別是 telemetry 與 evidence 雜湊的對齊。
2. **H7-2 RouteDecision / CapabilityReceipt Schema Consistency Test Plan**: 撰寫靜態測試計畫，驗證 decision 與 receipt 結構在極端 exception 下的一致性。
3. **H7-2 AutonomicRouter Quarantine / Bridge Design**: 設計將 AutonomicRouter 正式降級為唯讀 facade 的詳細隔離方案與 matched_policies 橋接架構。
4. **H7-2 Learning Policy Shadow Contract Draft**: 擬定 shadow 學習政策的驗證合約草案，規定 dynamic_learning_policy 的靜態提升門檻。
5. **H7-R0 Recovery Projection Source Map**: 針對 TaskRecoveryState 草案，對應當前 17 個 primitives，清點能提供重建投影的確切欄位與 gaps。
6. **H7-U3 Candidate Isolation Dependency Matrix**: 列出 committee route 在 hash match、mismatch fail-closed 上所需修改 the code dependency 矩陣。

---

## 8. Acceptance Criteria

* `docs/reports/h7_1_capability_routing_truth_source_seam_map_v0.md` 檔案確實存在。
* 未修改任何 production code。
* 未執行 any provider / model / network / model-load / model-call。
* 未新增任何路由器。
* 未變更執行期選路行為。
* 未啟用 learned policy。
* 未新增 checkpoint / resume CLI。
* 未將任何 unrelated dirty files 混入 commit。
* 最終狀態字串為：`H7_1_CAPABILITY_ROUTING_TRUTH_SOURCE_SEAM_MAP_DRAFT_READY_FOR_REVIEW`。

---

## 9. Final State

`H7_1_CAPABILITY_ROUTING_TRUTH_SOURCE_SEAM_MAP_DRAFT_READY_FOR_REVIEW`
