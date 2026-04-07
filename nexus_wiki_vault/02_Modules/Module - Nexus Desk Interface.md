---
aliases:
- Nexus Desk
- Desktop UI
- Tauri Interface
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[[System Overview|System Overview]]'
- '[[Module - Runtime Services|Module - Runtime Services]]'
source_of_truth: nexus-desk/src-tauri/src/main.rs
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
Nexus Desk 是基於 Tauri 2 + Rust + React 的桌面監控駕駛艙，提供任務可視化與系統指標攔截。 [Source: nexus-desk/src-tauri/src/main.rs]

## Role / responsibility
- **可視化監控**: 提供 [[task]] Timeline, Diff Viewer 與成本看板。
- **指標攔截 (Bridge)**: 透過 Rust 層與 Nexus Core 進行非同步通訊。 [Source: nexus-desk/src/lib/bridge.ts]
- **系統托盤與通知**: 管理背景執行狀態。

## Upstream
- **[[Module - Runtime Services]]**: 提供基礎服務狀態。
- **[[Module - Core Orchestrator]]**: 提供任務排程數據。

## Downstream
- **User Feedback Loop**: 使用者透過 Desk 進行手動干預。

## Related modules / files
- `nexus-desk/src-tauri/src/main.rs`: Entry point. [Source: nexus-desk/src-tauri/src/main.rs]
- `nexus-desk/src/App.tsx`: UI Logic. [Source: nexus-desk/src/App.tsx]

## Source notes
- [Source: nexus-desk/src-tauri/src/main.rs]
- [Source: nexus-desk/src/lib/bridge.ts]

## Open questions / conflicts
- [ ] **Cross-Platform**: 目前僅在 Mac 進行過完整測試。
- [ ] **Auth**: 是否需要與 GitHub 帳號進行連動驗證。

---
[[System Overview]]
