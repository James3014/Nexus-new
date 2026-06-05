# 本地自動修復架構流程 (Local Heal Architecture Flow)

**建立日期**: 2026-06-05
**上下文來源**: Git 歷史提煉 (近一個月演進紀錄)

`local_heal` 是 Nexus 專案近期引入的核心子系統，旨在建立一個高度自動化、閉環的錯誤重現與代碼修復流水線。

## 1. 核心使命與架構解耦 (Core Mission & Decoupling)

根據近期重構 (Step 5 ~ Phase 6)，Local Heal 已經從單一腳本演進為由 **Orchestrator** 驅動的模組化流水線。其主要目標是：在將修改提交回主線或交由全域驗證前，於沙盒/本地環境中進行「重現 -> 診斷 -> 修復 -> 驗證」。

## 2. 流水線階段 (Pipeline Phases)

Local Heal 的執行被嚴格拆分為多個獨立的 Phase：

*   **Syntax Preflight (語法預檢)**: 在啟動深層分析前，先進行基礎的語法與結構掃描，排除低級錯誤。
*   **Planning & Preparation (規劃與預處理)**: 包含 Classifier 與 Sanitizer，負責清理輸入的錯誤報告並制定修復策略。
*   **Reproduction (自動重現)**: 
    *   這是一個核心里程碑。系統會嘗試生成自動化的重現腳本 (Reproduction Script Prepper)。
    *   具備**自我修正 (Self-correction)** 能力：若腳本生成失敗或報錯，會重新調整 prompt 包含 assertion directives。
    *   支援從 `expert_repro` 快取中載入專家級重現腳本。
*   **Patch Synthesis (修復合成)**: 也就是 Patch Invocation Boundary，這層負責與本地模型互動並產生修正代碼。具備 Refusal Recovery 機制以應對模型的拒絕回應。
*   **Verification (驗證)**: 在沙盒內運行重現腳本，驗證 Patch 是否真正解決了問題。
*   **Expected Stop Layer (預期停止層)**: 探測框架 (Probe Framework) 中的安全機制，確保修復過程符合預期原因並能及時止損。

## 3. 遙測與證據追蹤 (Telemetry & Receipts)

為確保修復過程的透明度與可追溯性，`local_heal` 實作了高精度的追蹤系統：

*   **Telemetry Tracker**: 追蹤每個階段的 Token 消耗與執行時間 (Duration)，以支援成本控制與效能優化。
*   **Receipt Builder**: 自動將 Telemetry 記錄、執行軌跡與模型 Prompt 注入到最終的 Receipt 中。這份 Receipt 成為了該次修復是否可信的重要「法庭證據」。

## 4. 隔離與安全 (Isolation & Safety)

*   **Research Isolation**: 修復過程與核心路由智慧分離，確保在探索與生成 Patch 時不會污染全域 Context。
*   **Canary Receipt & Baseline**: 透過標準化的金絲雀驗證與基線比較，確保修復不會引入退化。