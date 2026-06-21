# BDE-Track 全庫能力發現與路徑相關性審計報告 (BDE8 最終決策)

## 1. 執行摘要 (Executive Summary)

本報告在 BE（實施針對性 14B 回退與 action-protocol 擴展）啟動前，對 Nexus 專案進行全庫能力發現與路徑相關性審計（BDE1-BDE8）。目的是確認 BDC 階段定義的 23 個核心防禦能力是否遺漏了任何實際存在於程式庫中、且對本地修復極限有實質影響的 Nexus 能力。

* **BDE8 最終決策**: `BDE8_NO_MISSED_REPAIR_RELEVANT_CAPABILITIES_PROCEED_BE` 結合 `BDE8_BD_CEILING_REMAINS_LOCAL_HEAL_FULL_ARMOR`。
* **審計結論**:
  * 我們在 `CapabilityRegistry` ( castle SSoT ) 中掃描到了全部 **34 個 canonical capabilities**。
  * 對照 BDC 參照地圖，發現 BDC 遺漏了 4 個與 `local_heal` 無關的能力（例如學術引用治理 `research_and_source_discipline`、外置生產力調用 `external_productivity` 等），但經審核後，這些缺失能力皆確實屬於 **OUT_OF_SCOPE**。
  * 本地修復路線中並無任何 P0 / P1 等級的缺失能力。
  * **24/35 解決率** 確實是核心防護齊備下的真實模型能力極限（local_heal-core full-armor ceiling）。
  * 批准進入 BE 階段：**批准 BE 針對性 14B 回退與 action-protocol 優化工作**。

---

## 2. 全庫能力清冊與 BDC 差異分析 (BDE1 & BDE2)

全量 capabilities 清冊存於 [repo_capability_inventory.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/bde_repo_wide_capability_audit_v0/repo_capability_inventory.json)，與 BDC 的覆蓋對比報告存於 [bdc_coverage_diff.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/bde_repo_wide_capability_audit_v0/bdc_coverage_diff.json)。

* **Repo Discovered Capabilities**: 34 個能力。
* **BDC 對應狀態**: 
  * 23 個核心 local_heal 能力完全覆蓋且真實 active。
  * 其餘 11 個能力（如 `external_productivity`, `research_and_source_discipline`, `nightshift`, `drone`, `swarm_multi_agent` 等）在 BDC 中被分類為 `MISSING_FROM_BDC_BUT_OUT_OF_SCOPE`，此分類經 BDE 覆蓋差異檢視後被證實為 **完全正確**。

---

## 3. 路徑相關性與隱藏註冊表掃描 (BDE3 & BDE4)

相關性與隱藏註冊表數據記錄於 [route_relevance_classification.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/bde_repo_wide_capability_audit_v0/route_relevance_classification.json) 與 [hidden_registry_scan.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/bde_repo_wide_capability_audit_v0/hidden_registry_scan.json)。

* **缺失/未激活能力的優先級評定**:
  * 評為 `P0_REQUIRED_BEFORE_BE`（必須在 BE 前集成）的能力：**0 個**。
  * 評為 `P1_REQUIRED_FOR_TRUST_OR_VALIDATION`（信賴/驗證相關，非修復率阻礙）：1 個 (`forecast_pregate`)，已作為 autonomic routing service 的預測特徵調用。
  * 評為 `P3_PRODUCT_OR_CAMPAIGN_LEVEL`（產品化/多代理級，與 local_heal 無關）：其餘 10 個。

這證明 local_heal 路徑的架構是乾淨且高凝聚的，所有異步、異質和高成本的能力在 BD 中被正確 skipped，不影響本地 ceiling 測量。

---

## 4. 缺失能力對 BD 失敗任務影響與決策 (BDE5 & BDE6)

對於 BD 階段失敗的 11 個任務之影響評估記錄於 [missed_capability_impact_on_bd_failures.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/bde_repo_wide_capability_audit_v0/missed_capability_impact_on_bd_failures.json)：

* **評估結果**: 無論哪一項缺失或 out-of-scope 的能力，均對這 11 個失敗任務的 verifier PASS 沒有任何正面影響（`potential_impact = NONE`）。
* **BE 准入狀態**: 批准 `PROCEED_TO_BE`。

---

## 5. BDE8 最終審計問答 (BDE8 Required Answers)

### 1. BDC 階段是否遺漏了任何程式庫中實體存在的能力？
* **是**。BDC 遺漏了 4 個與本地修復無關的能力（例如學術引用治理 `research_and_source_discipline`、外置生產力 `external_productivity` 等），但經審計，這 4 個能力在技術上本就無法在 `local_heal` 路徑中被消費，因此不影響 ceiling。

### 2. 哪些遺漏的能力是與修復相關的 (repair-relevant)？
* **無**。所有與修復相關的能力在 BD 階段均已 100% 激活且被覆蓋。

### 3. 哪些遺漏的能力是僅在產品/多代理級別 (product/campaign/multi-agent) 的？
* 包含 `swarm_multi_agent`、`drone`、`ui_validator`、`nightshift`、`metabolism_resume`、`registry_skills_sync`、`external_productivity` 與 `research_and_source_discipline` 等。

### 4. 是否存在任何 P0 級別的 blocker 能力？
* **否**。無任何 P0 級別的 blocker 缺失能力。

### 5. 24/35 的解決率此時是否依然是 valid 的 local_heal 全防具極限？
* **是，完全有效**。BDE 審計強化並證明了該數據的權威性與真實度。

### 6. BE 應前進還是應先整合缺失能力？
* 應 **直接前進至 BE 階段**。不需要做任何前置能力整合。

### 7. 下一步應具體追隨哪項任務？
* 應前進至 **BE1/BE8 針對性 14B 回退與 action-protocol 擴展實施**。
