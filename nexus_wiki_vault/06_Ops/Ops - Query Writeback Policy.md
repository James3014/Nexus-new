---
title: Ops - Query Writeback Policy
type: governance
status: active
version_scope: [v23]
source_of_truth: compiled-wiki
tags: [ops, wiki, governance, policy, query]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# Ops - Query Writeback Policy

## One-sentence summary
本文件定義 Nexus 系統中將「查詢結果」(Query Results) 回寫至 Wiki 知識庫的觸發條件、審核機制與元數據要求。 [Source: scripts/ops/wiki_linter.py]

## Role / responsibility
- **知識轉化**: 將動態的執行數據或 AI 探查結果轉化為持久的 Wiki 知識。
- **減少重複**: 避免對同一問題進行重複的昂貴探查。
- **維護一致性**: 確保回寫的內容符合 `Ops - Wiki Page Type Contracts`。

## Upstream
- **[[System Overview]]**: 總體治理入口。
- **[[01_System/System - Unknowns and Conflicts.md]]**: 提供回寫的潛在目標（待解問題）。

## Downstream
- **[[nexus_wiki_vault/]]**: 回寫內容的目標存儲。
- **[[scripts/ops/wiki_linter.py]]**: 檢查回寫內容的結構。

## Related modules / files
- `scripts/ops/wisdom_daemon.py`
- `scripts/engine/nexus_explore.py`

## Writeback Eligibility (回寫準則)

### 1. 什麼是值得回寫的 (Writeback-worthy)?
- **重大發現**: 發現了未記錄的系統組件或未知的物理路徑。
- **根本原因 (RCA)**: 解決了一個複雜事件，其解決過程具有通用參考價值。
- **決策紀錄**: AI 在執行過程中做出的架構級選擇。
- **真值變更**: 經由 `truth_claims` 驗證後的狀態變更。

### 2. 禁止回寫的情況
- **臨時狀態**: 單次執行的日誌、暫時性的變數。
- **未驗證的假設**: AI 尚未經過物理驗證 (Physical Verification) 的推測內容。
- **重複數據**: 已存在於 Wiki 且未發生變化的內容。

## Mandatory Metadata (必要元數據)
所有回寫內容必須附帶以下元數據：
- `query_context`: 觸發此回寫的原始查詢或任務 ID。
- `evidence_link`: 指向證明此知識為真的證據工件（如 `.nexus/artifacts/` 中的檔案）。
- `timestamp`: 回寫執行的精確時間。
- `confidence_score`: AI 對此內容準確性的信心評估 (0.0 - 1.0)。

## Workflow (回寫流程)
1. **觸發**: 執行 `nexus explore` 或 `nexus diagnose` 產生高價值結論。
2. **格式化**: 依照 `Ops - Wiki Page Type Contracts` 將結論轉化為 Markdown 格式。
3. **驗證**: 執行 `wiki_linter.py` 確保格式正確。
4. **提交**: 由 Agent 建立新頁面或更新現有頁面。
5. **標註**: 在 Wiki 中使用 `[Reference: query_id]` 標記來源。

## Source notes
- v23 Wisdom Memory Specifications
- Release Discipline v2.0

## Open questions / conflicts
- [ ] 是否應引入 Human-in-the-loop 審核機制（對於 Tier 0 頁面）。
- [ ] 回寫內容的過期與自動清理策略。
