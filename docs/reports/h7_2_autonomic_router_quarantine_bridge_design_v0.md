# H7-2 AutonomicRouter Quarantine / Bridge Design v0

**日期**: 2026-06-25  
**狀態**: `H7_2_AUTONOMIC_ROUTER_QUARANTINE_BRIDGE_DESIGN_DRAFT_READY_FOR_REVIEW`  
**治理/安全**: `NO_RUNTIME_BEHAVIOR_CHANGE`, `NO_PROVIDER_CALL`, `NO_MODEL_CALL`, `NO_MODEL_LOAD`, `NO_PROCESS_SPAWN`, `NO_NETWORK_CALL`, `PUBLIC_CLAIM_ALLOWED=false`  

> **安全聲明**: 本報告為純 audit/report-only 產出。本任務期間未新增任何 runtime routing behavior、未啟用 learned policy、未啟動 provider/model/network/model-load/model-call。H7 仍處於 planning-only 階段。

---

## 0. Status / Safety Boundary

本報告嚴格遵守以下安全防禦邊界：
* **status**: `H7_2_AUTONOMIC_ROUTER_QUARANTINE_BRIDGE_DESIGN_DRAFT_READY_FOR_REVIEW`
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

本報告專注於靜態分析與設計 `AutonomicRouter` 隔離方案（Quarantine & Bridge Design）。本任務：
* **H7-2 is report-only**: 本任務不包含任何 runtime 程式與測試修改。
* **H7-2 does not modify production code**: 不修改任何 `nexus/**/*.py` 程式。
* **H7-2 does not change routing behavior**: 不變更任何執行期分發與模式路徑。
* **H7-2 does not adopt learned policy**: 排除 runtime 採用 learned policy，保持 shadow-only 狀態。
* **H7-2 does not authorize provider/model runtime**: Provider 邊界維持 deny-by-default。
* **H7-2 does not resolve U3 candidate isolation gaps**: 本任務只針對路由器重疊做隔離規劃。

---

## 2. Current AutonomicRouter Responsibility

靜態檢索 `nexus/engine/autonomic_router.py`，其現有職責與特徵如下：

1. **輸入 (Inputs)**:
   * `task_desc` (任務描述字串)
   * `state` (`NexusState` 物件，含 metadata 與 target_files)
   * `forecast` (`Dict[str, Any]` 預測特徵，含 `impact_map`, `classifier_scores`, `confidence` 等)
   * `pre_routing` (`Optional[Dict]` 預選路由資訊)
2. **輸出 (Outputs)**:
   * 返回 `ExecutionPlan` 實體，欄位含 `mode` (`research_first`/`swarm`/`standard`), `reason`, `confidence`, `matched_policies`。
3. **模式變更邏輯 (mode-changing logic)**:
   * 包含硬編碼的 keyword stem 匹配（`ANCHORS`, `EXPANSIONS`）。
   * 若 `matched_policies` 大於 15，則 `mode = "swarm"`。
   * 🛡️ V4 Hardening MVP 邏輯下：
     * 若 GemmaGuard 未通過拒絕判定，則覆寫 `mode = "swarm"`。
     * 若 `ExtensionGuard.validate_l1_eligibility` 未通過且原為 `standard`，則覆寫 `mode = "swarm"`。
     * 若 `HazardMapper.analyze_impact` 判定為危險區域，則強制 `mode = "swarm"`。
     * 若 `evaluate_mfp` 的早出/綠燈驗證未通過且原為 `standard`，則覆寫 `mode = "swarm"`。
4. **與 CapabilityPlanner 的重疊 (Overlap)**:
   * 兩者皆試圖決定最終執行模式。`CapabilityPlanner` 通過 `_decide_routing_tier(signals)` 進行選路；而 `AutonomicRouter` 的 `route` 行為與其全然重疊並造成雙真值源衝突。
5. **現有依賴與調用路徑 (Legacy dependencies)**:
   * `nexus/engine/autonomic_routing_service.py` 中的 `AutonomicRoutingService` 會呼叫 `arouter.route(...)` 並直接寫入 `state.metadata["autonomic_route"]`。
   * `nexus/learning/router_nas_tuner.py` 會使用 `AutonomicRouter` 調校其 `token_threshold` 並呼叫 `_save_config` 修改組態。

---

## 3. Quarantine Decision

為確保 Nexus 單一 Settlements 真值源的完整性，確立以下隔離決策：
* **AutonomicRouter is not a route truth source**: 它是 legacy Heuristic 匹配器，絕不是選路真值源。
* **AutonomicRouter is not a replacement router**: 它不能取代 CapabilityPlanner 的 settlements 職責。
* **AutonomicRouter is unsafe_to_runtime_adopt as-is**: 其現有的 mode-changing 覆寫邏輯容易引發選路死循環，極不安全。
* **AutonomicRouter must not change runtime mode**: 嚴格禁止其在執行期變更 `state.metadata` 中任何與 mode 相關的狀態。
* **AutonomicRouter must not bypass CapabilityPlanner**: 其匹配結果若要採用，必須經由 Planner 進行 Settled 安全合約驗證。
* **AutonomicRouter may only survive as read-only signal facade**: 它只能扮演一個唯讀的 matched policies 與 Heuristic 訊號 facade。
* **Final route truth source remains CapabilityPlanner / RouteDecision**: 唯一的選路與決策 Settlements SSOT 是 Planner 與 RouteDecision。
* **Final receipt truth source remains CapabilityReceipt / SkillReceipt**: 唯一的憑證 SSOT 是 `CapabilityReceipt` 與 `SkillReceipt`。

---

## 4. Bridge Design

提出將 `AutonomicRouter` 收斂至 `CapabilityPlanner` 之 `AutonomicSignal` 橋接方案（不包含 runtime 程式變更）：

```text
+-------------------+
|  AutonomicRouter  | (Matched policies, GemmaGuard, HazardMapper, etc.)
+---------+---------+
          | (Read-Only Extract)
          v
+---------+--------------------+
|  CapabilitySignalSet         | (Matched policy IDs & suggested mode hints)
+---------+--------------------+
          | (Settlement settling)
          v
+---------+--------------------+
|  CapabilityPlanner           | (Govern route tier: L1, L2, L3)
+---------+--------------------+
          | (Archived Decision)
          v
+---------+--------------------+
|  RouteDecision               | (Strongly-typed SSOT)
+------------------------------+
```

### AutonomicSignal 虛擬結構設計 (Pseudo-schema)
```python
@dataclass(frozen=True)
class AutonomicSignal:
    autonomic_signal_source: str = "autonomic_router_facade"
    matched_policy_ids: tuple[str, ...] = ()
    suggested_mode_hint: str = "standard"  # research_first / swarm / standard
    risk_hint: float = 0.0
    cost_hint: int = 0
    confidence: float = 1.0
    evidence_refs: tuple[str, ...] = ()
    runtime_adoption_allowed: bool = False  # Strict default
```

1. **訊號融合**: 將 `matched_policy_ids` 與其 Heuristic 預估成果放入 `CapabilitySignalSet`。
2. **PlannerSettling**: 由 `CapabilityPlanner` 判定是否採信 `suggested_mode_hint`，並且必須經過 `S2TStrictGate` 與 `LearningPolicyLoader` 的雙重驗證。
3. **無副作用**: 自癒或 NAS 調優（`RouterNASTuner`）僅能修改 shadow config 與輸出唯讀 proposal，絕不可在 runtime 生效。

---

## 5. Required Tests Later

未來在 H7/H8 進行 test-only 驗證時，必須寫入以下 assertions：
* **AutonomicRouter cannot produce final RouteDecision**: 斷言 AutonomicRouter 的輸出絕不含 `RouteDecision` 強型別物件。
* **AutonomicRouter cannot mutate runtime mode**: 斷言在執行過程中，`AutonomicRouter` 不得在 metadata 寫入最終 `autonomic_route` 或改變執行狀態。
* **AutonomicRouter signal enters CapabilitySignalSet only**: 斷言 `AutonomicRouter` 僅能將訊號傳入 `CapabilitySignalSet` 作為 inputs。
* **CapabilityPlanner remains sole settlement owner**: 斷言僅有 `CapabilityPlanner.plan` 能生成 `CapabilityPlan` 並 settling 選路。
* **learning_policy_loader cannot elevate AutonomicRouter to route owner**: 斷言 policy loader 載入政策時，不允許將 AutonomicRouter 提升為 routing owner。
* **HallucinationGuard / verifier gates still fail-closed**: 斷言在任何 routing 變更下，獨立的治理閘若 fail 依然 fail-closed。
* **provider/model/network/model-load/model-call remain denied**: 斷言整個過程中未觸發任何 provider / network 執行。

---

## 6. Migration / Deprecation Options

為收斂此 seam，規劃以下三種搬遷與棄用方案：

### Option A: Full quarantine (全面隔離)
* **Risk**: 舊有的 `autonomic_routing_service` 測試代碼需要被大量重構與清理，可能破壞 legacy 測試覆蓋率。
* **Benefit**: 最徹底、最乾淨，完全移除 runtime 雙 truth-source 風險。
* **Required tests**: 清理 `autonomic_routing_service.py` 後，執行全量 test verify，確保無 downstream import 崩潰。
* **Recommended stage**: `H7` (當前階段推薦採用)
* **Runtime adoption allowed?**: **no**

### Option B: Signal facade (訊號封裝)
* **Risk**: 接口依然存在，若未加強 assertion，未來工程師可能不慎直接讀取 `arouter.route().mode` 作為選路，造成雙頭路由死灰復燃。
* **Benefit**: 保留對 NAS tuner Heuristic 以及歷史 matched policies 規則庫的相容性，可作為 planner 的豐富特徵輸入。
* **Required tests**: 撰寫 `test_autonomic_router_as_signal_facade` 確認其輸出限制於 `AutonomicSignal` / `CapabilitySignalSet`。
* **Recommended stage**: `H7` 到 `H8`
* **Runtime adoption allowed?**: **no** (僅提供訊號，決策必須 settles 在 Planner)

### Option C: Remove / deprecate (全面棄用)
* **Risk**: 若未將其 matched policies 特徵搬移，直接刪除會導致 Heuristic 規則特徵丟失，且 `RouterNASTuner` 與歷史 logs 分析會 compile 失敗。
* **Benefit**: 代碼庫最為純潔。
* **Required tests**: `git rm autonomic_router.py` 後驗證全量 CLI 與測試執行。
* **Recommended stage**: `H9` 之後
* **Runtime adoption allowed?**: **no**

---

## 7. Acceptance Criteria

* `docs/reports/h7_2_autonomic_router_quarantine_bridge_design_v0.md` 檔案確實存在。
* 未修改任何 production code（`nexus/**/*.py` 均未修改）。
* 未修改任何 tests（`tests/**/*.py` 均未修改）。
* 未執行任何 provider / model / network / model-load / model-call。
* 未新增任何路由器。
* 未變更執行期選路行為。
* 未啟用 learned policy。
* 未新增 checkpoint / resume CLI。
* 未將任何 unrelated dirty files 混入 commit。
* 最終狀態字串為：`H7_2_AUTONOMIC_ROUTER_QUARANTINE_BRIDGE_DESIGN_DRAFT_READY_FOR_REVIEW`。

---

## 8. Recommended Next Task

### H7-3 Capability Receipt Field Alignment Audit
* **原因**:  
  我們在 H7-1 確立了選路與憑證的 Seam 真值源，並在 H7-2 完成了對 `AutonomicRouter` 模式變更的隔離設計。下一步應對齊 `CapabilityReceipt`、`SkillReceipt` 與 `RouteDecision` 內部的 telemetry、evidence hash 欄位，確保資料 schema 一致性，為未來的 test-only schema gate 與自癒投影（Recovery Projection）進行前置對齊。

---

## 9. Final State

`H7_2_AUTONOMIC_ROUTER_QUARANTINE_BRIDGE_DESIGN_DRAFT_READY_FOR_REVIEW`
