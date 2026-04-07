---
aliases: '[CLI Commands](../05_Protocols/Protocol - CLI Surface.md) Service, Command Registry]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
raw_sources: ''
related_pages: ''
source_of_truth: nexus/services/cli_commands_service.py
status: active
tags: '[module, service, cli, command]'
title: Module - [CLI Commands](../05_Protocols/Protocol - CLI Surface.md) Service
type: module
version_scope: '[v17.1, v22, v23]'
---



# Module - [CLI Commands](../05_Protocols/Protocol - CLI Surface.md) Service

> [!NOTE]
> **Canonical Page**: 本頁描述 Nexus CLI 命令的具體服務端實作。關於命令路徑解析請見 [Protocol - CLI Surface](../05_Protocols/Protocol - CLI Surface.md)。

## One-sentence summary
本服務模組負責將高階 CLI 指令轉譯為核心調度器可執行的原子任務對象。 [Source: nexus/services/cli_commands_service.py]

## Role / responsibility
- **指令轉譯**: 將用戶輸入的 `nexus:*` 命令映射至內部的 `Action` 實體。 [Code: nexus/services/cli_commands_service.py]
- **參數硬化**: 在服務層執行二次 Schema 驗證，防止非法參數注入核心。
- **異步處理**: 處理與 `pilot_cli` 交互時的非阻塞響應邏輯。

## Upstream
- **User Interface (CLI)**: 原始命令流經過 `nexus_cli.py` 後進入本服務。
- **[Module - Core Orchestrator](Module - Core Orchestrator.md)**: 作為調度器的直接依賴項。
- **[System Overview](../00_Home/System Overview.md)**: 系統導航。

## Downstream
- **Capability Gate**: 驗證當前任務是否具備執行權限。
- **[Module - State Contracts](Module - State Contracts.md)**: 確保各指令產出的狀態符合合約。

## Related modules / files
- `nexus/services/cli_commands_service.py`: 物理實作。 [Source: nexus/services/cli_commands_service.py]

## Source notes
- v22 Engine Spec: 要求 CLI 指令具備「零阻礙」交互特性。

## Open questions / conflicts
- [ ] **Batch Mode**: 是否應在本層提供批量命令流水線執行能力。