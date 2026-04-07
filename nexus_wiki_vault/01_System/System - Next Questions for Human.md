---
aliases:
- Human Intervention
- Open Issues
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[Ops - Wisdom Layer](../06_Ops/Ops - Wisdom Layer.md)'
- '[System Overview](../00_Home/System Overview.md)'
- '[Unknowns](System - Unknowns and Conflicts.md) and Conflicts|[[System - [[System
  - Unknowns and Conflicts|Unknowns]] and Conflicts|System - [[System - Unknowns and
  Conflicts|Unknowns]] and Conflicts]]]]'
- '[State - Schemas](../04_State/State - Schemas.md)'
source_of_truth: compiled-wiki
status: active
tags:
- questions
- human
title: System - Next Questions for Human
type: system
version_scope:
- v22
- v23
---



# System - Next Questions for Human

## One-sentence summary
本頁彙整所有待解決的治理爭議、架構決策與需要人類授權的高風險問題。 [Source: 00_Home/System Overview.md]

## Role / responsibility
- **決策隊列**: 將 Wiki 衝突轉換為人類可理解的選擇題。 [Source: 01_System/System - Unknowns and Conflicts.md]]]
- **風險升級**: 標註具有「環境崩解」風險的問題。 [Source: scripts/ops/ci_gate.py]
- **歷史存證**: 記錄過往人類對關鍵衝突的裁撤結果。

## Current Questions Bucket

| Question ID | Category | Description | Priority | Source Provenance |
|---|---|---|---|---|
| `Q-01` | **Flow** | 是否應正式廢棄 v17.1 的單一任務調用模式。 | HIGH | [Source: 00_Home/System Overview.md] |
| `Q-02` | **States**| `v23.1` 是否應在 `manifest.json` 中強制包含風險評分。 | MEDIUM | [Source: 00_Home/System Overview.md] |
| `Q-03` | **Ops** | 何時啟動 Arweave 硬化同步計晝。 | LOW | [Source: 00_Home/System Overview.md] |

## Upstream
- **[System - Unknowns and Conflicts](System - Unknowns and Conflicts.md)**: 提供原始衝突報告。
- **Wiki Linter**: 反饋無法自動修復的一致性問題。 [Source: wiki_linter.py]

## Downstream
- **Human Response**: 更新 `.agents/skills/` 下的治理實施腳本。
- **[System Overview](../00_Home/System Overview.md)**: 根據決策更新系統概覽與權威邊界。

## Related modules / files
- `01_System/[System - Unknowns and Conflicts](System - Unknowns and Conflicts.md).md`: 衝突來源頁。
- `MUSE_NEXUS_v23_Wisdom.md`: 智慧決策的偏好底稿。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]]]

## Source notes
- v22 Engine Spec: 確立「人類作為最高治理決策者」的 Nexus 憲典位階。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Batch Decision**: 是否支持在一次會話中批次處理所有 OPEN 問題。
- [ ] **Response TTL**: 人類決策的有效期限，逾期是否自動回退至穩定版。