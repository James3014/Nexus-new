---
aliases:
- Nexus Desk
- Desktop UI
- Tauri Interface
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[System Overview](../00_Home/System Overview.md)'
- '[Module - Runtime Services](Module - Runtime Services.md)'
source_of_truth: 02_Modules/Module - Nexus Desk Interface.md
status: active
tags:
- module
- ui
- desktop
- tauri
- rust
title: Module - Nexus Desk Interface
type: module
version_scope:
- v22
---



# Module - Nexus Desk Interface

## One-sentence summary
本頁記錄桌面監控介面 (若外部專案存在) 與 Nexus 監控需求的對位邊界；當前實作以 `Nexus` runtime 流程為準。 [Source: 00_Home/System Overview.md]

## Role / responsibility
- **可視化監控**: 提供任務 Timeline、Diff 與成本觀測的需求規範。 [Source: 00_Home/System Overview.md]
- **指標轉導**: 將 CLI 與核心服務的關鍵指標映射到可視化需求。 [Source: scripts/ops/ci_gate.py]
- **作業入口規範**: 定義外部 UI 連接點與授權邊界。 [Source: 06_Ops/Ops - Wiki Page Type Contracts.md]

## Upstream
- **[Module - Runtime Services](Module - Runtime Services.md)**: 提供基礎服務狀態。 [Source: 02_Modules/Module - Runtime Services.md]
- **[Module - Core Orchestrator](Module - Core Orchestrator.md)**: 提供任務排程數據。 [Source: 02_Modules/Module - Core Orchestrator.md]

## Downstream
- **User Feedback Loop**: 使用者透過 CLI / 外部介面反饋，回流到 CI gate 驗收。 [Source: scripts/engine/nexus_cli.py]

## Related modules / files
- `scripts/engine/nexus_cli.py`: 外部介面發起與執行入口。 [Source: scripts/engine/nexus_cli.py]
- `06_Ops/Ops - CI/CD Promotion Gate.md`: 運行與發版門禁。 [Source: 06_Ops/Ops - CI/CD Promotion Gate.md]
- `00_Home/System Overview.md`: 架構參考。 [Source: 00_Home/System Overview.md]

## Source notes
- 本頁用 runtime repo 可驗證路徑為主；Tauri 實作若未併入主 repo，暫標記為外部規格。 [Source: 00_Home/System Overview.md]
- [Source: scripts/engine/nexus_cli.py]

## Open questions / conflicts
- [ ] **Cross-Platform**: 若 Desk 仍外部專案，是否需回補 mac/linux/windows 規格。 [Source: 00_Home/System Overview.md]
- [ ] **Auth**: 是否需要與 GitHub 帳號進行連動驗證。 [Source: 06_Ops/Ops - CI/CD Promotion Gate.md]

---
[System Overview](../00_Home/System Overview.md)


---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]
