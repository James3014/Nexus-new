---
title: Module - Runtime Services
aliases: [Services Hub, Daemon Scripts]
type: module
status: active
version_scope: [v22, v23]
source_of_truth: nexus/services/
raw_sources:
  - pilot_cli.py
  - memory_service.py
  - disk_janitor.py
related_pages:
  - "[[Module - Core Orchestrator]]"
  - "[[System Overview]]"
  - "[[System - Unknowns and Conflicts]]"
tags: [module, services, runtime, daemon]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# Module - Runtime Services

## One-sentence summary
本頁記錄 Nexus 執行環境中提供 IO、儲存、清理與交互支援的運行時服務組件。 [Source: `nexus/services/`]

## Role / responsibility
- **IO 接管 (Pilot CLI)**: 處理 1024-byte TTY 限制下的非阻塞輸入。 [Code: `pilot_cli.py`]
- **記憶體協調 (Memory Service)**: 管理 LanceDB 存取與 FTS 檢索。 [Source: Module - Memory Repository]
- **磁碟維護 (Disk Janitor)**: 執行 Artifact Retention 政策要求的物理清理。 [Code: `disk_janitor.py`]

## Upstream
- **[[Module - Core Orchestrator]]**: 發起服務調用請求。
- **Retention Policy**: 提供清理時間戳 Cutoff。 [Source: Ops - Artifact Retention]

## Downstream
- **File System**: 實體檔案修改與刪除。
- **User Activity**: 提供實時反饋與異常提示。 [Code: `nexus_cli.py`]

## Related modules / files
- `nexus/services/pilot_cli.py`: 核心 CLI 驅動。 [Code: `pilot_cli.py`]
- `nexus/services/memory_repository.py`: 記憶體存儲持久層。 [Code: `memory_repository.py`]

## Source notes
- Muse Engine Spec v22: 確立服務層與核心編排層的解耦要求。 [Source: Spec v22]

## Open questions / conflicts
- [ ] **Service Discovery**: 當服務崩潰時的重啟機制。
- [ ] **Log Rotation**: 服務運行日誌的保留與截斷政策。
