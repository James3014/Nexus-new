# 🛡️ Nexus Guarded Opt-In Proposal: Phase 4 Hardening

**Date**: 2026-06-01
**Status**: DRAFT (Observation-only)
**Promotion Effect**: NONE

## 1. 提案背景 (Background)
根據 Step 6 審計報表 (v4.4 Final)，LocalHeal 在 Phase 4 (Patch Synthesis) 仍面臨顯著的字面匹配失敗 (`SEARCH_MISMATCH`) 與語法無效 (`SYNTAX_INVALID`) 問題。為此，我們實施了 Phase 4 硬化計畫，目前已完成「語法前檢防線」與「量化觀測遙測」。

## 2. 建議啟動項目 (Proposed Optimizations)
本提案建議在特定本地模型 Profile 下，從「觀測模式」轉向「受控執行模式」：

*   **A. Syntax Preflight Enforcement**: 正式將 `ast.parse` 攔截機制納入 Patch 階段的硬性門禁，不合法補丁將直接觸發 `SelfCorrector`。
*   **B. Refusal-Aware Recovery**: 啟用 `SelfCorrector` 的拒絕感知指令，當模型道歉或輸出空值時，自動執行重對齊引導。
*   **C. Strict Aider Contract**: 強制執行 `PromptBuilder` 生成的精簡指令格式，減少 14B 模型的解釋性輸出。

## 3. 風險評估 (Risk Assessment)
- **環境穩定性**: 優化僅限於 `PatchSynthesisPhase` 內部，不改變 Orchestration 編排。
- **證據完整性**: 所有補償行為（如自動更正、重試）均會完整記錄於 `CapabilityReceipt` 的 `telemetries` 中，維持可審計性。

## 4. 結論 (Verdict)
本輪優化維持 **observation-only** 邊界，所有數據將繼續累積於審計 JSONL 中，直至下一輪 Canary 驗證通過。

[NEXUS PROPOSAL: PHASE 4 HARDENING DRAFT]
