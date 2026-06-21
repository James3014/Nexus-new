# AB1 — Full Capability Route Definition Report

**狀態**: `AB1_FULL_CAPABILITY_ROUTE_DEFINED`, `AB1_CAPABILITY_MATRIX_COMPLETE`  
**評估日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 智慧路由能力定義 (Route Definition)
我們正式定義並註冊了內部基準路由：`local_full_nexus_repair_control_plane_v0`。
該路由定義了在本地模型修復場景下，Nexus 所能提供之 10 個核心智慧能力階段的串聯與邊界。

### 10 大智慧能力階段 (10 Capability Stages)
1.  **Pregate / Plan Quality**:
    *   **機制**: `budget_manager` 進行 budget 預估與風險分類。
    *   **限制**: 低風險任務可跳過重型能力以節約 token，高/中風險任務強制要求全能力校驗。
2.  **CodeIntel / Evidence Graph**:
    *   **機制**: 基於 AST 動態提取 imports、caller/callee 與 producer/consumer。
    *   **綁定**: 所有 graph nodes 具備 source_hash 與 provenance。
3.  **Memory / LanceDB / Findings Memory**:
    *   **機制**: 檢索 LanceDB 中相似成功/失敗 lessons，透過 scorer 計算 **+10 / -15** 的權重調整。
    *   **限制**: 必須具備來源追蹤，嚴禁 dump 裸 memory 輸出。
4.  **Autoreason / DDTree / Belief**:
    *   **機制**: `reasoning_router` 評估 plausibility，並透過 DDTree 對 candidate 候選路徑進行剪枝與 pruning；寫入信念與信心值。
    *   **限制**: 無任何推理結果可 Override Verifier 判定。
5.  **Model Portfolio (模型組合)**:
    *   **機制**: 異質組合 3B Judge (進行證據充足度與 abstain 判定)、Qwen 7B (主要 proposer)、DeepSeek 6.7B (次要 proposer)，以及備用 14B fallback。
6.  **Controlled Action Protocol**:
    *   **機制**: 單一與多 anchor sequence。協同編輯（2-file）強制 owner_approval；3個檔案以上直接阻斷並回報 `ABSTAIN_BOUNDARY_EDIT`。
7.  **Deterministic Applier**:
    *   **機制**: 對搜尋區塊與替換區塊進行 source_hash 校驗與 dry-run apply，支援發生錯誤時自動 rollback 復原。
8.  **Sandbox / Replay / Ultra Review**:
    *   **機制**: sandbox 環境隔離執行微驗證，並在多檔案與協同編輯下自動生成 Ultra Review 安全與風險評估報告。
9.  **Artifact / Claim / Delivery Gate**:
    *   **機制**: 只有在 Verifier 執行通過時，claim 才能記錄為 `signed_delivery`；否則一律記為 `rejected_delivery` 或 `internal_unverified`，嚴禁任何 silently promote success。
10. **Learning Closure / Meta-Opt**:
    *   **機制**: 寫入成功/失敗的 lessons 機制回饋至本地 JSONL 歷史，以供下次 selector 調用打分。

---

## 2. 能力調用與 Stub 狀態說明 (Missing or Stubbed Capabilities)
經過代碼稽核與 native_route_adapter 檢驗，目前除以下 1 項能力外，其餘能力均已完成第一版 wired：
*   **Swarm/Drone 本地鎖定機制**:
    *   **狀態**: **STUBBED** (Stub)
    *   **原因**: 本地多執行緒 Worktree 鎖定機制仍為 Stub 占位符，安全延期至下一階段。
    *   **影響**: 限制了 concurrent 併發修復能力，但不影響單線程 Full Capability 的基準評測與真實修復上限評估。

---

## 3. 安全與門禁檢驗 (Safety Checks)
1.  **無直接修補**: 所有 Proposer 僅產生 Search/Replace 結構，無任何模型可繞過 Protocol 直接改寫原始碼。
2.  **不污染綠燈**: 門禁系統獨立於 Verifier，Verifier 通過為 signed_delivery 的唯一充分條件，杜絕偽成功。
3.  **四項合規限制**: 合規 flags 維持 `false`，全能力路由僅用於內部基準測試。
