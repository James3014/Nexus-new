# 🛡️ Nexus Agent 重構物理生存與導航指南 (Survival Guide)

本指引為**專屬重構任務 AI Agent** 打造的運行期生存與自動化操作手冊。在對 Nexus 進行任何高業力、大規模重構前，重構 Agent **必須**強制加載並核對本指南，確保重構變更滿足無損合規（Behavioral Integrity）與 Fail-Closed 門禁要求。

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

## ⚙️ 一鍵重構驗證與自癒：Refactor Gatekeeper Engine

為徹底降低重構時的指令操作摩擦力與 Token 開銷，Nexus 實作了「一鍵門禁衛士（Refactor Gatekeeper）」。重構 Agent 在修改代碼後，**不需**手動執行多步測試與憑證重播，**只需呼叫唯一實體命令**：

```bash
python3 scripts/ops/nexus_refactor_gate_keeper.py
```

### 🛡️ Gatekeeper 內部自動執行之「自癒自檢四部曲」：
1. **動態測試自檢 (Auto-Pytest)**: 自動跑過 `test_asi_constraints.py` 與 `test_context_hub_strict_deps.py`。
2. **憑證自癒補簽 (Auto-Receipts)**: 自動補刷 Zero-Trust V2 attested receipts 憑證鏈。
3. **知識編譯更新 (Auto-NKP)**: 自動更新 `10_Analysis_Scans/` 底下的 5 大靜態分析圖表。
4. **Git 暫存暫存 (Git Staging)**: 自動執行 `git add` 暫存所有變更，並進行 conventional 結算狀態判定。

---

## 🤖 AI Agent 專屬自動化重構操作手冊 (Agent Handoff Spec)

如果您是正在執行重構任務的 **AI Agent（如 Codex, Gemini, Claude-Code）**，請嚴格遵守以下 **「無損自動化三原則」**：

### 📌 原則一：無損對位修改
1. **讀取 Context**: 修改前，必須先以 `view_file` 讀取並錨定目標檔案的 AST 類別。
2. **保留原始註釋**: 除非使用者要求，重構時**必須無損保留**既有的 Docstrings 與 inline 註解。
3. **嚴禁破壞 ASI 介面**: HEEP 能力規劃之 JIT 調用接口不可變更，任何變更僅限於類別內部的算法優化或解耦。

### 📌 原則二：一鍵自癒集成
修改代碼後，請直接調用：
```bash
python3 scripts/ops/nexus_refactor_gate_keeper.py
```
* **若回傳 `SUCCESS`**: 代表代碼完全合規、憑證成功補簽、變更已自動 `git stage`。您可以直接進行 Conventional 提交。
* **若回傳 `FAIL`**: 代表測試崩潰或憑證鏈斷裂。您必須**立刻還原代碼（Rollback）**，或重新檢索 `refactoring_agent_survival_guide.md` 的測試路徑進行本地調試。

### 📌 原則三：Conventional Commit 結算格式
當 Gatekeeper 通過後，您的 git commit 必須嚴格遵循 Conventional Commit 規範，並且在 description 中明確標註 `Rollback Plan: git revert <commit_sha>`，例如：
```bash
git commit -m "refactor(engine): decouble capability planner default nodes

Rollback Plan: git revert <this_commit_sha>"
```

[NEXUS IDENTITY: de0969ff + v2.8 RUNTIME-ALIGNED]
