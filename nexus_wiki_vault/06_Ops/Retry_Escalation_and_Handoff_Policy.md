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

## Role / responsibility
- 規範任務失敗時的重試與移交邊界，避免任務陷入無效循環。 [Source: nexus/core/exit_codes.py]
- 將失敗證據封裝成可稽核單位，供運維與合規查核。 [Source: scripts/ops/ci_gate.py]

## Upstream
- `nexus/core/exit_codes.py` 定義失敗分類與輸入邏輯。 [Source: nexus/core/exit_codes.py]
- `06_Ops/Ops - Acceptance and Release.md` 規範 cold-start 與阻斷策略。 [Source: 06_Ops/Ops - Acceptance and Release.md]

## Downstream
- 影響 `closeout` 與 `nexus:acceptance` 的人工移交觸發。 [Source: scripts/ops/ci_gate.py]
- 回填到 `06_Ops/Ops - Learning Closure Matrix.md` 形成防再發知識。 [Source: 06_Ops/Ops - Learning Closure Matrix.md]

## Related modules / files
- `nexus/core/exit_codes.py`: 失敗分類定義。 [Source: nexus/core/exit_codes.py]
- `scripts/ops/ci_gate.py`: 任務退出態流程與阻斷規則。 [Source: scripts/ops/ci_gate.py]
- `tests/ops/test_closeout_guard.py`: 人機移交回退測試。 [Source: tests/ops/test_closeout_guard.py]

## Source notes
- 依據 `exit_codes` 實作整理對應門檻。 [Source: nexus/core/exit_codes.py]

## Open questions / conflicts
- [ ] `ESCALATED` 是否需要加入自動降級窗口限制以保護成本。 [Source: nexus/core/exit_codes.py]

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

[[System Overview]]
