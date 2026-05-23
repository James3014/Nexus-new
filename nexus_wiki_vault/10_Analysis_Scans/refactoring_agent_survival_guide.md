# 🛡️ Nexus Agent 重構物理生存與導航指南 (Survival Guide)

本指引為**專屬重構任務 AI Agent** 打造的運行期生存手冊。在對 Nexus 進行任何高業力、大規模重構前，重構 Agent **必須**強制加載並核對本指南，確保重構變更滿足無損合規（Behavioral Integrity）與 Fail-Closed 門禁要求。

---

## 🗺️ 靜態地圖對接 (Static Analysis Anchors)

重構前，請先深度查閱以下由 NKP 管線編譯生成之靜態圖譜與熱點地圖，鎖定代碼物理結構：

1. **[代碼全庫打包與 Token 分佈樹](file:///Users/jameschen/workspace/nexus/nexus_wiki_vault/10_Analysis_Scans/repomix/repomix_complete.md)**: 
   - 快速理清 Nexus 37 個子模組的物理階層，避開測試資料與 Swarm 暫存區的雜訊干擾。
2. **[AST 依賴與死代碼審計報告](file:///Users/jameschen/workspace/nexus/nexus_wiki_vault/10_Analysis_Scans/codegraph_audit/codegraph_status.md)**:
   - 鎖定 `PENDING_EXECUTOR_CAPABILITIES` 等無用符號，重構時予以徹底清除。
3. **[圈複雜度與重構機會矩陣](file:///Users/jameschen/workspace/nexus/nexus_wiki_vault/10_Analysis_Scans/codex_complexity/complexity_optimizer_report.md)**:
   - 定位 `capability_planner.py` (CC: 42) 與 `research_flow_service.py` (CC: 35) 圈複雜度熱點，依據 ROI 建議優化重構優先級。

---

## ⚙️ 動態運行期測試與驗證自檢 (Dynamic Pytest Checklists)

靜態分析只是地圖，**重構 Agent 必須在重構前後物理執行以下測試命令**，驗證代碼語意無損：

### 1. 核心 JIT 技能組裝與約束自檢 (ASI Constraints)
* **目的**: 驗證重構沒有破壞 HEEP 13 種能力的適配與 JIT 負控制（Negative-control）查表邏輯。
* **物理執行命令**:
  ```bash
  pytest tests/engine/test_asi_constraints.py
  ```

### 2. ContextHub 嚴格隔離與依賴檢查
* **目的**: 確保重構未在 `context_hub.py` 中引入任何隱式或循環引用，維護 strict dependency 原則。
* **物理執行命令**:
  ```bash
  pytest tests/core/test_context_hub_strict_deps.py
  ```

### 3. Research Flow 拆分後葉子模組集成測試
* **目的**: 驗證拆分後的 10 個葉子模組在與 `ResearchFlowService` 門面（Facade）聯動時運作正常。
* **物理執行命令**:
  ```bash
  pytest tests/research/test_flow_leaf_modules.py
  pytest tests/app/test_research_s2t_runtime.py
  ```

---

## 🛡️ 零信任 V2 macOS 沙盒與憑證重播指引 (Zero-Trust V2 Sandbox)

在大規模重構完成後，由於物理程式碼已發生變動，舊有的 attested receipts 將自動失效，引發門禁鎖死（`runtime_mutation_allowed=false`）。重構 Agent 必須執行以下「憑證補刷與解鎖」流程：

### 步驟 1：在 macOS `sandbox-exec` 唯讀沙盒下運行重播
確保所有的重播與測試皆在 macOS 沙盒下安全完成，物理隔離業務程式碼：
```bash
# 啟用 macOS 沙盒唯讀探測
uv run scripts/ops/build_zero_trust_v2_sandbox_probe.py
```

### 步驟 2：物理補刷並重新生成 signed receipts
利用 V2 behavior runner 對重構後的能力進行重新執行，補刷 attested 憑證鏈：
```bash
# 強制重新計算並簽章 fresh task receipts
uv run scripts/ops/build_zero_trust_v2_fresh_task_refs.py --force-sign
```

### 步驟 3：運行 CI Gate 結算檢測
```bash
uv run scripts/ops/ci_gate.py
```
只有當 `ci_gate.py` 回傳 `PASS` 且 receipts 重新解鎖後，方可宣稱重構成功交付。

---

## 📈 運行期 3% 效能開銷與安全限制 (Performance Gates)

重構 Agent 必須對位以下安全門禁限制：
1. **3% CPU/Token 開銷防線**:
   - `HallucinationGuard`（防幻覺攔截）與 `CompletionEnvelope`（結算收據）調用鏈在運行期的總消耗開銷**嚴禁大於 3%**。
   - 治理邏輯必須被限制在「路由決定」與「結算審計」兩個核心 Gate 上被動調用，嚴禁置於常規業務計算高頻迴圈。
2. **無損回退 (Idempotent Rollback)**:
   - 所有代碼變更必須支持一鍵無損回滾。重構 Agent 必須在提交中明確備註 `Rollback Plan: git revert <commit_sha>`。

[NEXUS IDENTITY: de0969ff + v2.8 RUNTIME-ALIGNED]
