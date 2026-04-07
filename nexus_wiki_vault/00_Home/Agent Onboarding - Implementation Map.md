---
aliases: '[Implementation Map, Nexus Map, Entry Point Map]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: scripts/ops/ci_gate.py
status: active
tags: '[[System Overview|home]], [[Agent Onboarding - Command Pack|onboarding]], implementation,
  governance]'
title: Agent [[Agent Onboarding - Command Pack|Onboarding]] - Implementation Map
type: '[[System Overview|home]]'
version_scope: '[v22, v23]'
---



# Agent [[Agent Onboarding - Command Pack|Onboarding]] - Implementation Map

## One-sentence summary
本頁將 Nexus 的宏觀架構與微觀實體檔案進行物理對照，作為 Agent 進場後的導航地圖。 [Source: scripts/ops/ci_gate.py]

## Role / responsibility
- **消除實作迷霧**: 明確標註每個治理概念在 Repo 中的具體入口。 [Source: 00_Home/System Overview.md]] - Implementation Map.md]
- **導航加速**: 提供從 [[System Overview]] 到 `/nexus/core` 的最短路徑。

## Implementation Map (實作地圖)

### 1. 治理與門禁 (Governance & Gate)
- **[[CD Promotion Gate|CI Gate]] 硬閘**: `scripts/ops/ci_gate.py` [Code: scripts/ops/ci_gate.py]
- **Wiki Linter**: `scripts/ops/wiki_linter.py` [Code: scripts/ops/wiki_linter.py]
- **故障排除**: 參考 `[[Ops - CI Failure Playbook]]`。 [Source: nexus_wiki_vault/06_Ops/Ops - CI Failure Playbook.md]].md]

## Upstream
- **[[System Overview]]**: 宏觀定位。 [Source: nexus_wiki_vault/00_Home/System Overview.md]].md]

## Downstream
- **[[Module - Implementation Responsibility Matrix]]**: 詳細責任矩陣。

## Related modules / files
- `scripts/ops/ci_gate.py`: 門禁核心。 [Source: scripts/ops/ci_gate.py]

## Source notes
- v22 Engine Spec: 要求「凡實作必有地圖」。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Dynamic Updates**: 是否由 Linter 自動更新地圖次數。