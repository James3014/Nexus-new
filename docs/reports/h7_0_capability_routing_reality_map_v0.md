# H7-0 Capability Routing Reality Map v0

**日期**: 2026-06-25  
**狀態**: `H7_0_CAPABILITY_ROUTING_REALITY_MAP_DRAFT_REVIEW_REQUIRED`  
**治理/安全**: `NO_RUNTIME_BEHAVIOR_CHANGE`, `NO_PROVIDER_CALL`, `NO_MODEL_CALL`, `NO_MODEL_LOAD`, `NO_PROCESS_SPAWN`, `NO_NETWORK_CALL`, `PUBLIC_CLAIM_ALLOWED=false`  

> **安全聲明**: 本報告為純 audit/report-only 產出。本任務期間未新增任何 runtime routing behavior、未啟用 learned policy、未啟動 provider/model/network/model-load/model-call。H7 仍處於 planning-only 階段。

---

## 0. Workspace Contamination Record

**H7-0 artifact itself is report-only, but the workspace is not clean and contains unrelated staged/modified production, test, config, artifact, CI, and generated-data changes. H7-0 acceptance must be evaluated only after isolating or cleaning unrelated changes.**

本 reality map 在以下 workspace 狀態下產出（`git status --short` 快照）：

```text
STAGED (unrelated CI/config — NOT part of H7-0 commit):
  A  .github/workflows/security.yml
  A  .github/workflows/typecheck.yml
  A  docs/reports/f02a_scoped_pyright_ci_gate_2026-06-25.md
  A  docs/reports/f03a_scoped_bandit_ci_gate_2026-06-25.md
  M  pyproject.toml
  M  uv.lock

UNTRACKED (planning-only artifacts, NOT part of H7-0 commit):
  ?? docs/reports/h7_0_capability_routing_reality_map_v0.md   <-- 本報告
  ?? docs/reports/h7_capability_routing_consolidation_plan_v0.md
  ?? docs/reports/hybrid_dynamic_route_h0_audit_v0.md
  ?? docs/reports/hybrid_dynamic_route_integration_point_matrix_v0.json
  ?? docs/reports/hybrid_dynamic_route_mode_schema_draft_v0.json
  ?? docs/reports/u3_candidate_isolation_preflight_audit_v0.md

DIRTY (unrelated staged/modified production/artifact/CI files):
  M  nexus/services/local_heal/backend_resource_policy.py
  M  nexus/services/local_heal/interface.py
  M  nexus/services/local_heal/native_route_adapter.py
  M  nexus/services/local_heal/phases/patch_synthesis.py
  M  nexus/services/local_heal/role_contract.py
  M  tests/unit/local_heal/test_role_contract.py
  M  artifacts/runtime/* (multiple runtime JSON files)
  M  nexus/**/__pycache__/*.pyc (compiled bytecode)
```

**H7-0 commit scope 限制**:  
若進行 commit，只能包含以下兩個檔案：
- `docs/reports/h7_0_capability_routing_reality_map_v0.md`
- `docs/reports/h7_capability_routing_consolidation_plan_v0.md`

所有 unrelated staged/modified workspace 檔案不得混入 H7-0 commit。

---

## 0.1 Analyzer Script Reproducibility

**The analyzer script used to generate the primitive map is not present as a tracked or untracked repository artifact; generation is therefore not reproducible from committed files yet.**

腳本在任務期間以 scratch artifact 形式存在，但從 repo 中無法找到：

```text
find . -name 'analyze_primitives.py'  =>  (no output)
即 analyze_primitives.py 未在 repo 中以任何形式存在。
生成此 reality map 的腳本目前不可從 committed files 重現。
```

若需重現本 reality map 的 primitive 分析：
1. 需手動重建 AST 分析腳本或使用 `rg` / manual inspection 驗證。
2. 腳本使用純 AST 靜態分析，不執行任何 runtime 行為。
3. 本報告表格中的 primitive 資訊已完整記錄，可作為唯一參考依據。

---

## 1. Reality Map

本表格對應 Nexus 現行之 12 個核心 capability routing 相關 primitives，分析其擁有者模組、調用路徑、輸出證據、重疊縫隙、缺失測試及目標階段，並給予 no-behavior-change (不改變執行期行為) 建議。

| Primitive Name | Owner Module | Current Call Path | Current Receipt/Evidence Output | Duplicate/Overlap Seams | Missing Tests | Target Stage | No-Behavior-Change Recommendation |
|---|---|---|---|---|---|---|---|
| **CapabilityPlanner** | `nexus.engine.capability_planner` | benchmark/agent main | `CapabilityPlan` 物件 (含 selected/required 列表) | 與 `AutonomicRouter` 存在能力規劃上的 overlap，planner 為真實選路真值源。 | 缺少對 `_apply_s2t_policy_promotion` 和 `_apply_mutation_assurance_policy` 的 E2E 整合測試。 | `H7` | 保持 planner 作為唯一選路決策點，禁止其他 facade/router 變更 mode。 |
| **CapabilitySignalSet** | `nexus.engine.capability_signals` | `CapabilityPlanner.plan` | `CapabilitySignalSet`, `CapabilityConstraints` 字典 | 與 `AutonomicRouter` 內部自帶的特徵提取有潛在邏輯重複。 | 缺少針對 dynamic/LanceDB 回收特徵與 signal set 映射的穩定性測試。 | `H7` | 作為 Planner plan 階段 the 唯讀資料來源，不影響選路決策。 |
| **CapabilityContracts** | `nexus.engine.capability_contracts` | across engine modules | Strongly-typed dict / JSON schemas (e.g. `RouteDecision`, `CapabilityReceipt`) | 無重大 overlap，這是所有 contracts 定義的 SSOT。 | 缺少對 JSON schema validation 的單元測試。 | `H7`/`H8` | 僅做型別與欄位擴充，不變更 runtime 狀態。 |
| **CapabilityReceipts** | `nexus.engine.capability_receipts` | task wrap-up/evaluation | List of `CapabilityReceipt` dicts | 存在一部分從執行日誌（trace）粗暴映射為 receipt 的邏輯，而非直接由 execution unit 回傳 receipt。 | 缺少對非 normal trace (例如 timeout 或 fail-closed 異常) 的 receipt 建立測試。 | `H8` | 僅做 Trace 解析與 Receipt 轉換，不得跳過或弱化驗證。 |
| **AutonomicRouter** | `nexus.engine.autonomic_router` | legacy / test paths | `ExecutionPlan` 物件 | 與 `CapabilityPlanner` 存在嚴重選路 overlap 與衝突。 | 缺少對將其降級為 facade 後，在 planner 中轉換為訊號輸入的測試。 | `H7` | 降級為唯讀的 autonomic_signals facade，禁止直接影響執行期 mode。 |
| **OutcomeMemory** | `nexus.learning.outcome_memory` | task finalize autotune | episode outcomes / `NEXUS_OUTCOME_MEMORY_RETENTION.json` | 與 `S2TAdoptionDecision` 有部分學習結果與評分算法的 overlap，且排除 `trust_mismatch` 邏輯分散在多個模組中。 | 缺少對於多任務並行（concurrency）下 OutcomeMemory 寫入衝突與排除 `trust_mismatch` 的 tests。 | `H9` | 維持唯讀的 tuning 計算，`enforce_penalties=false` 不主導 runtime 變更。 |
| **S2TSelector / StrictGate** | `nexus.contracts.s2t_policy` | shadow eval / adoption gate | `S2TAdoptionDecision` 與 `S2TSelectionDecision` | 與 `learning_policy_loader` 中的部分 S2T policy 解析/載入有 overlap。 | 缺少對 `S2TStrictGate` 處於不同 risk profiles 下的 fail-closed 單元測試。 | `H9`/`H10` | 僅在 shadow mode 下執行計算，不寫回生產線 policy。 |
| **LearningPolicyLoader** | `nexus.engine.learning_policy_loader` | `CapabilityPlanner.plan` | Budget controls / expected executor flags | 讀取環境變數與 policy 檔案時，與 planner 本身存在部分邏輯 overlap。 | 缺少在環境變數被意外設定時，對於 `protect_expected_capability_controls` 邊界防禦的安全測試。 | `H7`/`H10` | 作為唯讀 policy loader 載入控制項，不新增 runtime 策略。 |
| **HallucinationGuard** | `nexus.governance.hallucination_guard` | governance audit gate | verdict dict, score, rendered markdown | 與 `ClaimGate` 及 `ArtifactGate` 的邏輯在 claim 驗證上有 overlap，且 hallucination 檢查的規則與 claimability 協議是分散的。 | 缺少對「有錯誤宣稱但 artifact 缺失」的 hallucination 評分邊界測試。 | `H9` | 唯讀分析與分數產出，若有違規僅作 audit/reject，不改變程式執行邏輯。 |
| **LessonRetrieval** | `nexus.services.lesson_retrieval` | pre-flight / agent TDD | List of relevant lesson dicts/texts | 與 LanceDB 向量檢索以及 OutcomeMemory 有部分 overlap，檢索機制同時包含了 Lexical 和 Vector。 | 缺少檢索 Consensus Engine 在不同召回結果衝突時的決策測試。 | `H9` | 僅做 Prompt 級別的 Context 注入，不作為 runtime 選路依據。 |
| **LessonWritebackCheck** | `scripts/ops/lesson_writeback_check.py` | CI / Ops check | Exit code (console logs) | 屬於 facade，是一個獨立的 linter 工具，沒有嵌入在 runtime learning cycle 中。 | 缺少對 invalid lesson formatting 的自動修復測試。 | `H9` | 唯讀靜態檢查，不影響執行期。 |
| **RlmController** | `nexus.engine.rlm_controller` | self-healing / loop control | RLM receipts / Nightshift handoff receipts | 與 `SelfHealingSelector` 和 `Nightshift` 的排程控制有 overlap。 | 缺少遞迴 depth 超出 budget 時，RLM 熔斷機制的單元測試。 | `H9` | 保持 `bounded_adapter_not_dispatch` 唯讀模式，禁止分發實際 recursive 工作。 |

---

## 2. Reality Map Classifications

針對上述 12 個核心 Primitives，依據 reality map 分類標準歸納如下：

*   **route_truth_source** (路由真值源):
    *   `CapabilityPlanner` (主要決策者)
*   **receipt_truth_source** (憑證真值源):
    *   `CapabilityReceipts`
    *   `CapabilityContracts` (提供 data models)
*   **evidence_source** (證據源):
    *   `CapabilitySignalSet` (特徵與環境變數)
    *   `CapabilityContracts`
*   **learning_trace_source** (學習軌跡源):
    *   `OutcomeMemory` (episode outcomes)
    *   `LessonRetrieval` (引導學習歷史)
*   **policy_loader** (策略載入器):
    *   `LearningPolicyLoader`
    *   `S2TSelector` (解析與裝配 shadow policies)
*   **governance_gate** (治理閘):
    *   `S2TSelector / StrictGate`
    *   `HallucinationGuard`
*   **recovery_projection_candidate** (復原投影候選者):
    *   `OutcomeMemory` (episode 回溯)
    *   `RlmController` (X/R-loop 預算控制與 iteration 記數)
*   **audit_only** (唯讀審計者):
    *   `LessonWritebackCheck` (Ops script)
*   **unsafe_to_runtime_adopt** (執行期不可直接採用者):
    *   `AutonomicRouter` (含有 legacy 模式切換邏輯，易干擾 Planner 決策)
*   **duplicate_or_facade** (重複或外觀者):
    *   `AutonomicRouter` (選路邏輯與 Planner 重複)
*   **missing_tests** (缺失測試者):
    *   上述表格中標示之所有 Primitives。

---

## 3. Recovery Map

在評估 Nexus 的 Task Recovery (任務自癒/重試/復原) 系統時，目前仍缺乏對 "Reconstructable Runtime" 的完全支援。現行 Primitive 在 Recovery 場景中的對應關係如下：

### 3.1 Recovery Map Classifications

*   **route_truth_source** (復原路由真值源):
    *   `CapabilityPlanner` (控制當前階段允許的能力清單)
*   **receipt_truth_source** (復原憑證真值源):
    *   `CapabilityReceipts` (提供自癒程序中已發生動作的 objective receipts)
*   **evidence_source** (復原證據源):
    *   `CapabilitySignalSet` (提供 Task 狀態及失敗原因的訊號組)
*   **recovery_projection_candidate** (自癒投影候選):
    *   `RlmController` (擁有 `RlmBudget`，能控制 `should_continue_x` 和 `should_continue_r`)
    *   `OutcomeMemory` (記錄先前失敗的 attempt 分數，用於迴避失敗路徑)
*   **audit_only** (復原審計專用):
    *   `scripts/ops/lesson_writeback_check.py`
*   **unsafe_to_resume** (不安全恢復源):
    *   `AutonomicRouter` (無狀態，重啟時會遺失當前 context，且硬編碼的切換邏輯容易導致死循環)
*   **missing_hash** (缺少雜湊校驗者):
    *   `RlmController` (RLM 收據不包含當前 workspace code 的 hash，無法確保 resume 後的工作區是一致的)
    *   `OutcomeMemory` (學習歷程未記錄 source code 狀態之 hash)
*   **missing_phase_pointer** (缺少階段指標者):
    *   `RlmController` / `RlmBudget` (僅包含 `x_iteration` 和 `r_iteration` 計數，無法指示具體中斷的 execution phase，如 P2 還是 P3)
*   **missing_next_action** (缺少下一動作引導者):
    *   `RlmController` (無 `next_action` 或 `recovery_projection` 預測控制，熔斷後直接 return False，無法引導 fallback 策略)

---

## 4. Key Findings & Architectural Gaps

1.  **ACRouter 與 Planner 重疊機制**:
    *   `AutonomicRouter` 原先設計為 autonomic control facade，但依然保留了 runtime 模式配置行為，與 `CapabilityPlanner` 之策略覆蓋 (policy overlays) 存在權力衝突。
    *   **改善**: 應將 `AutonomicRouter` 全面降級為唯讀的訊號提供者，所有能力選路路徑最終必由 `CapabilityPlanner` 統一 settlement。
2.  **Recovery Primitives 嚴重缺口**:
    *   目前 RLM (Recursive Loop Mechanism) 在自癒時處於 `bounded_adapter_not_dispatch` 階段。若要走向實質 Recovery (H7-R/H8-R)，目前控制項缺乏 **Code State Hash**、**Phase Pointer** 以及 **Next Action Projection**，這代表一旦中斷，重啟便會面臨 blind resume 的巨大安全隱患。
3.  **Governance 與 Claimability 隔離**:
    *   `Claim` (公開宣告) 與 `Artifact` (客觀證據) 的檢驗邏輯依然散落（`HallucinationGuard`, `ClaimGate`, `ArtifactGate`）。
    *   `HallucinationGuard` 應只作為客觀數據分析（audit-only），不應主動變更執行邏輯；而 `Claim` 必須是獨立且 fail-closed 的安全保護閘。

本 reality map 表明：**目前 Nexus 的 Intelligent Routing 正式具備完整的靜態與憑證基礎，但任何動態學習/自癒分發/H7 runtime 執行均不具備開啟條件，必須嚴格維持 shadow-only 狀態。**

---

## 5. Safety & Non-Behavior-Change Statement

本任務（H7-0 及 H7-0A）遵守以下全部限制：

```text
no runtime behavior change
no provider call
no model call
no network call
no model load
no learned policy adoption
no new router
no resume CLI added
no checkpoint writer added
no TaskRecoveryState routing influence
no verifier weakened
no claim gate weakened
no artifact gate weakened
no hallucination guard weakened
no MemPalace gate weakened
production_ready=false
public_claim_allowed=false
routing_ready=false
provider_ready=false
H7_STARTED=false
```

**H7 仍為 planning-only 階段。本報告不構成任何 H7 runtime 啟動宣告。**
