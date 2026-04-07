---
aliases:
- Terminology
- Nexus Terms
- Shared Vocabulary
confidence: high
last_compiled: 2026-04-07
owner: agent
related_pages:
- '[[System Overview|System Overview]]'
- '[[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] Runtime|[[Flow - [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]]
  Runtime|Flow - [[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]] Runtime]]]]'
- '[[Ops - Acceptance and Release|Ops - Acceptance and Release]]'
- '[[Ops - Truth Claims Register|Truth Claims]] Register|[[Ops - [[Ops - Truth Claims
  Register|Truth Claims]] Register|Ops - [[Ops - Truth Claims Register|Truth Claims]]
  Register]]]]'
source_of_truth: compiled
status: active
tags:
- system
- glossary
- terminology
title: Nexus Glossary
type: system
version_scope:
- v22
- v23
---



# Nexus Glossary

## One-sentence summary
本頁提供 Nexus 核心術語的單一語義定義，降低多代理協作中的用詞歧義與規約誤解。 [Source: 00_Home/System Overview.md]

## Role / responsibility
- **語義對齊**: 統一關鍵詞定義，避免不同 agent 產生衝突語意。
- **治理穩定**: 作為文件、CI 報告與任務回報的共用詞彙基準。

## Upstream
- `[[System Overview]]`: 全系統定位與版本邊界。
- `[[Flow - PXDRAC Runtime]]`: 執行相位定義。

## Downstream
- `[[Agent Boot Sequence]]`: 新 agent 啟動時快速對齊術語。
- `[[Ops - CI Failure Playbook]]`: 故障分類與修復語境一致化。

## Related modules / files
- `scripts/engine/nexus_cli.py`
- `scripts/ops/ci_gate.py`
- `.nexus/reports/acceptance_check.json`

## Source notes
- 建議固定詞義：
- `[[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]]`: Probe / eXplore / Diagnose / Repair / Audit / Crystallize 的任務生命週期。
- `P0 Drift`: 會阻斷發布的關鍵漂移問題。
- `Observe-only`: 樣本為 0 時不阻斷，但必須留下可追蹤證據（例如 `no_sample_observe_only=true`）。
- `Truth Claim`: 必須可由命令或實體路徑驗證的聲明。
- `[[task]] Contract`: 對任務交付範圍、命令、工件與變更路徑的約束。

## Open questions / conflicts
- [ ] 是否將 `PDRAC` (legacy) 與 `[[SYSTEM_ARCHITECTURE_BLUEPRINT|PXDRAC]]` (current) 的差異固定為獨立術語頁。
- [ ] 是否建立術語版本化（v22/v23）避免未來升級時語義混淆。