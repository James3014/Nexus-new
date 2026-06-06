---
aliases: '[Nexus Evolution History, v9 to v28, Detailed Product History]'
confidence: high
last_compiled: '2026-06-05'
owner: agent
source_of_truth: nexus_wiki_vault/
status: hardened
tags: '[history, evolution, strategy, governance]'
title: Nexus Evolution History (v9 to v28)
type: system
version_scope: '[v9, v28]'
---

# Nexus 系統演化史 (v9 - v28)

## 1. 核心定位 (Executive Summary)
Nexus 自 v9 演進至 v28，已從單純的代碼執行代理 (Code-Execution Agent) 轉變為一套**治理優先 (Governance-First) 的作業系統級戰甲**。此演化核心解決了當前 AI 產業最大的痛點：**AI 幻覺無法控管、審計證據匱乏、以及企業對決策過程的信任缺失**。

## 2. 演化矩陣 (Detailed Evolution Matrix)

| 版本範圍 | 演化階段 | 核心架構演進 | 解決的核心痛點 |
| :--- | :--- | :--- | :--- |
| **v9 - v17** | 探索階段 | 實作基礎 Agent 協作與簡單記憶層，引入 `P-X-D-R-A-C` 原型 | AI 缺乏持續性執行任務的能力，容易產生孤立的錯誤。 |
| **v17 - v23** | 加固階段 | 引入 Governance Layer, L5.7 雙平面治理邊界 | AI 決策路徑模糊，缺乏法庭級別的審計證據。 |
| **v23 - v28** | Meta-Stable階段 | 引入 `Local Heal` 閉環、Migration Contracts, 統一決策語言 (UDL) | 系統隨規模擴大而治理失穩，修復手段污染主線環境，大規模自動化部署缺乏合規基準。 |

---

## 3. 戰鬥演進場景 (Combat Evolution Scenarios)

### 3.1 v9-v17: 混沌初開的「實驗場」
在早期版本，Nexus 僅作為單體執行代理運作。主要的戰鬥場景是解決 `ImportError` 與基礎的環境相容性問題。當時缺乏隔離機制，導致修復一個 Bug 常會導致全域測試崩潰。

### 3.2 v17-v23: 治理優先的「邊界建立」
為了處理幻覺問題，Nexus 導入了 L5.7 的「雙平面架構」。
* **物理隔離**: 嚴格劃分「執行平面」與「公開宣稱平面」。
* **合約校驗**: 實作了四層合約 (Lane, Receipt, Policy, Telemetry)，強制拒絕未經完整驗證的 artifact 進入發布區。

### 3.3 v23-v28: Meta-Stable 的「閉環自治」
這是 Nexus 近期最劇烈的重構。透過 Git 紀錄 (v27.1-v28.2) 可見大量的架構演進：
* **`Local Heal` 系統**: 從單一腳本進化為具備 ORM 執行流、預檢、自動重現、修復合成、CANARY 驗證的完整子系統。解決了「修復不可控」的惡性循環。
* **Migration Contracts (遷移合約)**: 在 v28.2 引入，確保在架構發生重大跳變（如從舊治理 API 遷移到 unified decision language）時，系統能維持狀態一致性。
* **回歸基準 (Regression Baselines)**: 建立了 `solidify regression baseline`，自動化篩選出真正的 Bug 修復，而非環境漂移導致的雜訊。

---

## 4. 關鍵技術護城河 (Technical Moats)

### 4.1 治理合約防彈玻璃
Nexus 透過 `public_telemetry_boundary_contract.py` 等硬合約，確保 Agent 輸出的所有商業 KPI 數據（如 Wall Time, Token Cost）都經過「非觀察式」審計，杜絕「影子數據」偷渡至公開報告。

### 4.2 從 Bug 到免疫細胞 (Learning Closure)
透過 `Ops - Learning Closure Matrix`，Nexus 將每一次實戰中產生的 `Combat History`（如 `astropy` 編譯崩潰、`concurrency` 競態條件修復）自動轉化為新的「閘門規則」。Bug 不僅被修復，還在 CI Pipeline 中固化為一道防線。

### 4.3 數據驅動的路由 (Meta-Routing)
現在的 Nexus 使用 A/B 測試驅動的決策引擎 (`capability_ab_runner.py`)。它不再盲目信任單一策略，而是透過同題實驗，動態選擇解決率最高、最省 Token 的能力組合。

---
- **核心來源檔案**: 
  - `nexus_wiki_vault/04_Research/Nexus Combat History Ledger.md` (實戰修復與防禦細節)
  - `nexus_wiki_vault/06_Ops/Ops - Governance Changelog.md` (詳細演進紀錄)
  - `nexus_wiki_vault/01_System/Governance_L5.7_Two_Plane_Four_Contract_Architecture.md` (架構白皮書)
  - `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` (免疫系統演化)
  - `git log --oneline --grep="v27\|v28"` (最新架構演進證據)
