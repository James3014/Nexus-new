---
aliases:
- Algebraic Reasoning
- Formal Change Discipline
confidence: high
last_compiled: '2026-05-06'
owner: agent
related_pages:
- '[[05_Protocols/Protocol - Evidence Map.md]]'
source_of_truth: nexus/core/orchestrator.py
status: hardened
tags:
- protocol
- reasoning
- formal
title: Protocol - Algebraic Reasoning
type: protocol
version_scope: v26
---

# Protocol - Algebraic Reasoning

## One-sentence summary
要求所有高風險修改使用可追溯推導，將「直覺修補」轉為「不變量保證」。

## Role / responsibility
- 定義 patch 變更時的推導邊界與反例要求。
- 約束高風險變更不得缺少可驗證的不變量描述。

## Upstream
- `nexus/core/orchestrator.py` 的流程契約。
- 現場 RCA 與重現案例。

## Downstream
- `05_Protocols/Protocol - Evidence Map.md`
- `06_Ops/Ops - Weekly Governance Report.md`

## Related modules / files
- `nexus/core/orchestrator.py`
- `06_Ops/Ops - Acceptance and Release.md`
- `05_Protocols/Protocol - Knowledge Lineage.md`

## Source notes
- 本規範用於將代碼重寫轉化為可驗證步驟，避免只靠敘事式宣告完成補丁。[Source: 05_Protocols/Protocol - Knowledge Lineage.md]

## Open questions / conflicts
- [ ] 如何在極小改動（如命名修正）仍保留最低「不變量」證明責任？
- [ ] 是否要為臨時修補提供明確但有限的豁免條件？

> [!CAUTION]
> 本文件原有的部分內容被標註為無效推導，已重新整理為可驗證規範版型。

## 核心原則
禁止未經推導的 Trial-and-Error 堆疊；高風險更動需先定義以下三個欄位：
- 不變量（Invariant）
- 轉換步驟（Rewrite Trace）
- 反例縮減（Counter-example）

## 判定規則
- **合格**：Patch 產生步驟可回溯至既有不變量。
- **不合格**：僅憑直覺描述，未提供可重放證據。

## Link to System
[[System Overview]]
