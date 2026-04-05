---
title: Protocol - CLI Surface
aliases: [CLI Commands, Nexus CLI API]
type: protocol
status: active
version_scope: [v17.1, v22, v23]
source_of_truth: scripts/engine/nexus_cli.py
related_pages:
  - "[[Protocol - CLI Drift Matrix]]"
  - "[[System Overview]]"
  - "[[System - Unknowns and Conflicts]]"
tags: [protocol, cli, command, surface]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# Protocol - CLI Surface

## One-sentence summary
本頁記錄 Nexus 核心命令清單與參數規範，作為外部調用與治理的權威介面映射。 [Source: `nexus_cli.py`]

## Role / responsibility
- **命令索引**: 映射 `plan`, `explore`, `diagnose`, `repair`, `audit`, `crystal` 等核心子命令。
- **參數約束**: 定義 `--risk`, `--auto-approve`, `--trace-id` 等關鍵參數的語義。 [Source: v23 Wisdom Supplement]
- **交互規範**: 規範 TTY 模式下的非同步輸入處理。 [Source: Pilot CLI v100+]

## Upstream
- **User Request**: 人類輸入。
- **Wisdom Layer**: 提供智慧決策偏好。

## Downstream
- **[[Flow - PXDRAC Runtime]]**: 執行命令對應的業務邏輯。
- **[[Protocol - CLI Drift Matrix]]**: 追蹤跨版本的命令進化。

## Related modules / files
- `scripts/engine/nexus_cli.py`: 進入點文件。 [Code: `nexus_cli.py`]
- `nexus/delivery/pilot_cli.py`: 實體 TTY 處理引擎。 [Code: `pilot_cli.py`]

## Source notes
- CLI Spec v17.1: 定義原始 `nexus <task>` 結構。
- Muse Engine Spec v22: 引入子命令分組機制。 [Source: Spec v22]

## Open questions / conflicts
- [ ] **Alias Conflict**: 部分舊版 alias 是否應在 v23 中正式廢棄。
- [ ] **JSON Output**: 是否所有子命令均應提供 `--json` 原始輸出流以供自動化消費。
