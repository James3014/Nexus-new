---
aliases:
- Engineering Discipline
- Hardening Process
confidence: high
last_compiled: '2026-05-06'
owner: agent
related_pages:
- '[[06_Ops/Ops - CI Failure Playbook.md]]'
source_of_truth: scripts/ci_smoke_test.py
status: hardened
tags:
- protocol
- engineering
- discipline
title: Protocol - Engineering Discipline
type: protocol
version_scope: v26
---

# Protocol - Engineering Discipline

## One-sentence summary
將「先改再驗」的風險行為封裝為可執行規範，確保每次修改皆可回放與驗證。

## Role / responsibility
- 約束變更行為，禁止以口頭驗證替代測試證據。
- 推動 commit 粒度、測試、審核三位一體的交付節奏。

## Upstream
- CI 門檻、測試腳本與交付 gate。
- 運維回報中的阻斷案例。

## Downstream
- `06_Ops/Ops - Acceptance and Release.md`
- `06_Ops/Ops - Wiki Regression Evals.md`

## Related modules / files
- `scripts/ci_gate.py`
- `scripts/ops/ci_gate.py`
- `06_Ops/Ops - Closeout Hard Gate.md`

## Source notes
- 規範對齊 `ci_gate` 的 fail-closed 流程與最小化驗證責任。[Source: scripts/ops/ci_gate.py]

## Open questions / conflicts
- [ ] 如何把「臨時修復」情境正式化為最小化、明確期限的例外？
- [ ] 是否建立跨模組變更審核閾值自動提醒機制？

## 關鍵行為要求
- 測試不是可選：任何邏輯更動需附帶可執行驗證。
- Atomic Commit：單次提交聚焦單一目標，避免混雜改動。
- 若因環境問題無法測試，需先修環境而非先跳過。

## Link to System
[[System Overview]]
