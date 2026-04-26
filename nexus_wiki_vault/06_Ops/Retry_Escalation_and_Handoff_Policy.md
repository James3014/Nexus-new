---
aliases: '[Retry Policy, Escalation Rules, Handoff SOP]'
confidence: high
last_compiled: '2026-04-20'
owner: agent
source_of_truth: nexus/core/exit_codes.py
status: hardened
tags: '[ops, recovery, handoff, policy]'
title: Ops - Retry Escalation and Handoff Policy
---

# Ops - Retry Escalation and Handoff Policy (v26 Hardened)

## One-sentence summary
本頁定義 Nexus 在任務失敗時的「自癒重試」與「人工移交」分流政策，確保機群在極限狀態下具備安全退場機制。

## 📊 任務分流政策 (Decision Matrix)

| Exit Code | Classification | Retry Policy (重試) | Handoff Action (移交) |
| :--- | :--- | :--- | :--- |
| **0 (SUCCESS)** | ✅ 完成 | N/A | 更新 Wiki 並 Promote。 |
| **1 (FAILED)** | ❌ 局部失敗 | 自動重試 (最多 3 輪)。 | 無需移交。 |
| **2 (ESCALATED)**| ⚠️ 邏輯死鎖 | **禁止重試**。 | 觸發 `CampaignGeneral` 重新規劃。 |
| **3 (HUMAN_REVIEW)**| 🛑 治理違規 | **物理阻斷**。 | ✅ **立即打包 HandoffBundle**。 |

## 🚀 人機移交流程 (Handoff SOP)
當系統觸發 `HUMAN_REVIEW` 或 `ESCALATED` 且無法自動復原時：
1. **證據保全**: 系統調用 `HandoffBundle.py`。
2. **狀態打包**:
    - 當前 Git Diff 補丁。
    - 所有的 `tracelog` 與 `evidence_id`。
    - 物理環境快照 (Environment Snapshot)。
3. **路徑轉發**: 將包路徑輸出至終端，並發送 `Code 16/3` 警報。

## 🛡️ 物理守護
- 嚴禁對 `HUMAN_REVIEW` 狀態進行自動 `force_retry`，以防系統在已知違規路徑上循環導致配額耗盡。

---
**[Source: nexus/core/exit_codes.py]**
