---
aliases:
- Dual-Gate Response
- Report Gate
confidence: high
last_compiled: '2026-05-06'
owner: agent
related_pages:
- '[[06_Ops/Ops - Acceptance and Release.md]]'
source_of_truth: scripts/ops/ci_gate.py
status: hardened
tags:
- protocol
- reporting
- acceptance
title: Protocol - Dual-Gate Response
type: protocol
version_scope: v26
---

# Protocol - Dual-Gate Response

## One-sentence summary
定義任務報告的雙門檻輸出格式，讓每次回應同時滿足「任務敘述」與「驗證證據」。

## Role / responsibility
- 規範報告必須輸入 `[任務][數據][證據]` 三段資料。
- 對 residual debt、測試結果和阻斷點負責揭示。

## Upstream
- 任務規格與 runbook 目標。
- CI / QA 門檻輸出。

## Downstream
- `06_Ops/Ops - Acceptance and Release.md`
- `06_Ops/Ops - Wiki Drift Audit.md`

## Related modules / files
- `scripts/ops/ci_gate.py`
- `scripts/ops/wiki_truth_claims_check.py`
- `06_Ops/Ops - Closeout Hard Gate.md`

## Source notes
- 雙門檻對齊 `ci_gate` 與交付阻斷策略，避免僅以敘事通過流程。[Source: scripts/ops/ci_gate.py]

## Open questions / conflicts
- [ ] 是否需要固定 JSON 輸出 schema 版本欄位以支援 parser 兼容？
- [ ] Residual debt 是否要求每次都帶 0 值或未完成原因？

## Protocol Payload
- **Task**：任務摘要、目標範圍、改動單元。
- **Data**：可重放的數據、配置、路徑、測試輸入。
- **Evidence**：測試輸出、log、artifact、回歸比對。
- **Residual Debt**：未完成項、阻斷風險、下一次 action。

## Link to System
[[System Overview]]
