---
aliases:
- Context Hygiene
- Context Boundaries
confidence: high
last_compiled: '2026-05-06'
owner: agent
related_pages:
- '[[05_Protocols/Protocol - Knowledge Lineage.md]]'
source_of_truth: scripts/ops/wiki_drift_audit.py
status: hardened
tags:
- protocol
- context
- operations
title: Protocol - Context Hygiene
type: protocol
version_scope: v26
---

# Protocol - Context Hygiene

## One-sentence summary
控制上下文訊號密度與雜訊輸入，降低幻覺與目標漂移風險，讓推理維持高信噪比。

## Role / responsibility
- 規定讀取與輸出的上下文邊界。
- 防止無關訊息侵入導致推理路徑偏移。

## Upstream
- 運行日誌、任務 trace 及 `context` 產生源。
- `scripts/ops/wiki_drift_audit.py` 的漂移檢出結果。

## Downstream
- `05_Protocols/Protocol - Engineering Discipline.md`
- `06_Ops/Ops - Wisdom Layer v22 Architecture.md`

## Related modules / files
- `scripts/ops/wiki_drift_audit.py`
- `nexus/core/context_hub.py`
- `nexus/services/memory_pipeline.py`

## Source notes
- 本協議對應 `ContextHub` 與輸出截斷策略的治理約束。[Source: scripts/ops/wiki_drift_audit.py]

## Open questions / conflicts
- [ ] 是否需要對長對話自動強制輸出摘要後再繼續推理？
- [ ] 2000 行截斷門檻是否需依任務類型調參？

## 核心規則
1. 工具輸出若超過 2000 行/50KB，必須啟用截斷策略（標頭 + 尾部 + Root Cause）。
2. 首次讀取禁止一次性加載整個模組，必須以符號預覽導向精準讀取。
3. 每次上下文切換都應建立 session seed，保留關鍵上下文快照。

## 驗證標準
- **清潔 (Clean)**：輸入上下文與當前目標相關度高，無大量環境噪音。
- **污染 (Polluted)**：存在大量編譯日誌、環境 dump 或非任務歷史。

## Link to System
[[System Overview]]
