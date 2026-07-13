---
title: Nexus Legacy Governance Rules
type: governance-snapshot
status: review_required
lifecycle: legacy
authority: non_normative
snapshot_period: 2026-03_to_2026-04
superseded_for_document_authority_by: DOC_AUTHORITY_MANIFEST.yaml
confidence: medium
---

# Nexus Governance & Rules

> [!warning] Legacy governance snapshot
>
> This document reflects the March-April 2026 execution model.
> References to Gemini CLI sub-agents, Nexus-only execution,
> AUTO-EXECUTE, voice notification, PASS baseline, or related operating
> assumptions have not been reconciled with the current multi-provider
> architecture.
>
> Do not treat this file as current normative policy.
> Preserve it for historical review only.

## Token 口徑（唯一判定規則）
1. 每輪 benchmark 必須記錄 `total_raw_tokens`。
2. 若 `total_raw_tokens > 0`：該輪模式標記 `RAW_AUDIT`。
3. 若 `total_raw_tokens = 0`：該輪模式標記 `AUDIT_ESTIMATE`。
4. 文件對外敘述一律使用「最新驗收快照時間點」。

## PM 執行硬規則
1. 主工作交給 `Gemini CLI` 分身執行。
2. 主代理只負責派工、驗收、收斂。
3. 第一優先目標：維持 `ci_gate PASS` 基線。

## 執行授權規則（Default Authorization）
1. 依路線圖直接開跑，不等待逐步確認。
2. 僅破壞性操作、憑證、規格衝突才暫停。

## AUTO-EXECUTE（No-Ask）硬規則
1. 預設模式：AUTO-EXECUTE。
2. 禁止詢問「是否繼續」。

## [重要] 核心意識形態（憲法級）
1. **Nexus 優先執行制**：所有實施任務（Coding, Benchmarking, Fixing）必須由 Nexus 引擎或分身執行，Agent 僅負責 Orchestration。
2. **語音通報分級**：重要的提示（Startup, Completion, Critical Alert）不受靜默模式限制，必須發出語音。

---
*Created by Nex-CEx Orchestrator*
