---
title: System - Next Questions for Human
aliases: [Human Intervention, Open Issues]
type: system
status: active
version_scope: [v22, v23]
source_of_truth: compiled-wiki
related_pages:
  - "[[Ops - Wisdom Layer]]"
  - "[[System Overview]]"
  - "[[System - Unknowns and Conflicts]]"
  - "[[State - Schemas]]"
tags: [questions, human]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# System - Next Questions for Human

## One-sentence summary
本頁彙整所有待解決的治理爭議、架構決策與需要人類授權的高風險問題。 [Source: compiled-governance]

## Role / responsibility
- **決策隊列**: 將 Wiki 衝突轉換為人類可理解的選擇題。 [Source: Page: System - Unknowns and Conflicts]
- **風險升級**: 標註具有「環境崩解」風險的問題。 [Source: `ci_gate.py`]
- **歷史存證**: 記錄過往人類對關鍵衝突的裁撤結果。

## Current Questions Bucket

| Question ID | Category | Description | Priority | Source Provenance |
|---|---|---|---|---|
| `Q-01` | **Flow** | 是否應正式廢棄 v17.1 的單一任務調用模式。 | HIGH | [Source: Diff Matrix] |
| `Q-02` | **States**| `v23.1` 是否應在 `manifest.json` 中強制包含風險評分。 | MEDIUM | [Source: `manifest_schema.json`] |
| `Q-03` | **Ops** | 何時啟動 Arweave 硬化同步計晝。 | LOW | [Source: `arweave_seal.py`] |

## Upstream
- **[[System - Unknowns and Conflicts]]**: 提供原始衝突報告。
- **Wiki Linter**: 反饋無法自動修復的一致性問題。 [Source: `wiki_linter.py`]

## Downstream
- **Human Response**: 更新 `.agents/skills/` 下的治理實施腳本。
- **[[System Overview]]**: 根據決策更新系統概覽與權威邊界。

## Related modules / files
- `01_System/System - Unknowns and Conflicts.md`: 衝突來源頁。
- `MUSE_NEXUS_v23_Wisdom.md`: 智慧決策的偏好底稿。 [Source: v23 Wisdom]

## Source notes
- v22 Engine Spec: 確立「人類作為最高治理決策者」的 Nexus 憲典位階。 [Source: Spec v22]

## Open questions / conflicts
- [ ] **Batch Decision**: 是否支持在一次會話中批次處理所有 OPEN 問題。
- [ ] **Response TTL**: 人類決策的有效期限，逾期是否自動回退至穩定版。
