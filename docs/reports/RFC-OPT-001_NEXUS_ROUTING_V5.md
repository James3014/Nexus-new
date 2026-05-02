# RFC-OPT-001: Nexus Autonomic Routing v5 (V3 Hardened)

## 1. 核心問題
- **過度治理 (Over-governance)**: 低風險任務（如文件修復）觸發全量政策匹配與 Swarm。
- **上下文冗餘**: `AutonomicRouter` 加載所有 `policy_memory.jsonl`，導致 Token 浪費。
- **決策延遲**: 缺乏針對「重複任務」與「高信心路徑」的早退機制。

## 2. 優化方案：AOS-P34-OPT-V3

### 2.1 三級治理分層 (Governance Tiering)
| 等級 | 觸發條件 | 能力組合 | 預期節省 |
| :--- | :--- | :--- | :--- |
| **L1 (Green-Lane)** | Risk < 0.3 & Ambiguity < 0.3 | Single Model + Memory | Time -60%, Token -50% |
| **L2 (Hardened)** | Risk 0.3-0.7 | Model + Ultra Review + LanceDB | Time -20%, Token -20% |
| **L3 (Swarm/Deep)** | Risk > 0.7 or Core Module | Full Swarm + Research + RedTeam | N/A (保持穩定) |

### 2.2 DDTree 影響力感知剪枝 (Impact-Aware Pruning)
- **機制**: 從 Planner 獲取 `impact_map` (影響檔案列表)。
- **操作**: 僅加載標籤與影響模組（如 `core`, `infra`, `ui`）相關的政策。
- **安全鎖**: 標記為 `GLOBAL` 的政策（如安全洩漏檢測）禁止剪枝。

### 2.3 預測門禁 (Forecast-Gate) 早退機制
- 若 `Memory` 命中率 > 0.9 且 `confidence` > 0.95，跳過 Research 階段，直接進入 R (Repair) 階段。

### 2.4 新增：Codex 危害地圖 (Hazard-Mapping) [V3]
- **機制**：在路由決策前，強制檢索 `.codex_lessons.md`。
- **規則**：若任務涉及歷史上的「重災區」（如 `CompoundModels`, `Tauri ACL`, `Handoff Drift`），路由權重強制設為 **L3 (Full Swarm)**，無視任何 L1/L2 判定。

### 2.5 新增：具備「信念淨化」的 Gemma 分類器 [V3]
- **機制**：本地 Gemma-1B 僅接收「去語義化 Payload」（如 `ACTION:UPDATE, TARGET:CORE_LOGIC`）。
- **防禦**：透過 **Median-based Outlier Rejection** 技術，徹底阻斷透過 Task Description 進行的 Prompt Injection，確保 L1 不會被惡意誘導。

### 2.6 新增：代數微診斷 (Algebraic Micro-D) [V3]
- **機制**：利用 v26 `NexusDerivation` 模型執行「不變式邏輯核對」。
- **驗證**：在早退至 Repair 前，確保當前函數簽名符合歷史形式化證明，維持雙閘 AC-N 強制契約。

---

## 3. 紅隊對抗記錄 (Red Team Review)

### 3.1 攻擊點：降級治理導致的漏檢
- **防禦對策**: **強制模組鎖** + **Hazard-Mapping**。核心變更與歷史陷阱強制進 L3。

### 3.2 攻擊點：Gemma 分類器被 Prompt Injection 欺騙 [V3]
- **紅隊觀點**: 「Gemma-1B 容易被誘導將高危任務判定為 L1。」
- **防禦對策**: **去語義化 Payload** + **信念淨化 (Belief Purification)**。Gemma 僅處理結構化指令，且過濾非正態分佈的分類結果。

---

## 4. 實作路線圖 (Implementation Roadmap) [V3]
1.  **Step 1**: 修改 `nexus/core/router.py`，接入 `HazardMapper` 類別並掃描 `.codex_lessons.md`。
2.  **Step 2**: 實作 `payload_sanitizer.py` 用於 Gemma 分類器的輸入去語義化。
3.  **Step 3**: 於 `commander.py` 的 `_orchestrate_p` 階段整合「代數微診斷」門禁。

---

## 5. 結論
優化後的路由將具備「歷史自省」與「抗毒能力」。
- **預期目標**: 平均 Wall time 下降 40%，Token 消耗下降 30%，安全性提升 100%。

[NEXUS RFC: OPT-001 v3.0 Hardened]
