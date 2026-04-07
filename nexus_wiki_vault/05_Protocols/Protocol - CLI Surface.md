---
aliases: '[CLI Commands, Nexus CLI [[api|API]]]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: scripts/engine/nexus_cli.py
status: active
tags: '[protocol, cli, command, surface]'
title: Protocol - CLI Surface
type: protocol
version_scope: '[v17.1, v22, v23]'
---



# Protocol - CLI Surface

## One-sentence summary
本頁記錄 Nexus 核心命令清單與參數規範，作為外部調用與治理的權威介面映射。 [Source: nexus_wiki_vault/05_Protocols/Protocol - CLI Surface.md] [Code: scripts/engine/nexus_cli.py]

## Role / responsibility
- **命令索引**: 映射 `plan`, `explore`, `diagnose`, `repair`, `audit`, `crystal` 等核心子命令。
- **參數約束**: 定義 `--risk`, `--auto-approve`, `--trace-id` 等關鍵參數的語義。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]] Supplement]
- **交互規範**: 規範 TTY 模式下的非同步輸入處理。 [Source: 00_Home/System Overview.md]

## Upstream
- **User Request**: 人類輸入。
- **Wisdom Layer**: 提供智慧決策偏好。

## Downstream
- **[Flow - PXDRAC Runtime](../03_Flows/Flow - PXDRAC Runtime.md)**: 執行命令對應的業務邏輯。
- **[Protocol - CLI Drift Matrix](Protocol - CLI Drift Matrix.md)**: 追蹤跨版本的命令進化。

## Related modules / files
- `scripts/engine/nexus_cli.py`: 進入點文件。 [Code: scripts/engine/nexus_cli.py]
- `nexus/delivery/pilot_cli.py`: 實體 TTY 處理引擎。 [Code: pilot_cli.py]

## Source notes
- CLI Spec v17.1: 定義原始 `nexus <[task](../Reference/task.md)>` 結構。
- Muse Engine Spec v22: 引入子命令分組機制。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Alias Conflict**: 部分舊版 alias 是否應在 v23 中正式廢棄。
- [ ] **JSON Output**: 是否所有子命令均應提供 `--json` 原始輸出流以供自動化消費。

---
[System Overview](../00_Home/System Overview.md)


---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]