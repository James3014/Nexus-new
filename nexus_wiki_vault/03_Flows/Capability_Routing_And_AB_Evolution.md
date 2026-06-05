# 動態能力路由與 A/B 演化 (Dynamic Capability Routing & A/B Evolution)

**建立日期**: 2026-06-05
**上下文來源**: `capability_ab_runner.py` 與 `capability_planner.py` 演進歷史

Nexus 引擎的核心優勢在於其「能力 (Capability)」的調用並非靜態腳本，而是透過數據驅動的動態路由與 A/B 測試持續演化。

## 1. 動態能力規劃器 (Capability Planner)

`Capability Planner` 負責在任務啟動前，根據上下文動態組裝最佳的能力清單。
* **風險導向決策**: 根據任務屬性 (如 `bugfix`, `feature`, `doc-fix`) 與風險等級 (`low`, `critical`)，規劃器會決定哪些能力是 `required`，哪些是 `optional` 或 `forbidden`。
* **動態組裝**: 確保高風險任務強制套用 `governance_audit` 等防禦層，而低風險任務則採用輕量級流程以節省 Token。

## 2. A/B 測試驅動的演化 (A/B Test-Driven Evolution)

Nexus 嚴禁憑直覺新增能力。所有能力的演進都必須經過 `capability_ab_runner.py` 的科學驗證：
* **雙軌驗證 (Dual-Track Evaluation)**: 當引入新能力 (Treatment) 時，必須與現有基準 (Baseline) 進行同題目的平行測試。
* **數據裁決**: 新能力必須在「Token 效率」、「解決率 (Solve Rate)」或「Wall Time」上展現出明確的統計優勢 (搭配 Hidden Verifier 驗證)，才能通過 Public Claim Gate。

## 3. 淘汰與收斂機制 (Deprecation & Convergence)

* 表現不佳或造成上下文污染的能力，會在其 Capability Receipt 的追蹤下被標記。
* 經過多次 A/B 測試證實無效的策略，將會被移除或降級。
* 這種機制確保了 Nexus 不會隨時間變成臃腫的「功能怪獸」，而是保持為極度精煉、數據驗證過的智能核心。