---
aliases: '[Developer Guide, Core Hardening, Expert Rules]'
confidence: high
last_compiled: '2026-04-21'
owner: agent
status: production
tags: '[role, expert, guide, developer]'
title: Role Guide - Expert Developer
type: role-guide
version_scope: v24.1
aliases: [Expert Guide, Developer Guide]
---

# 專家開發者指南 (Expert Guide)

## 1. 職責與主權
專家級開發者負責 Nexus **Layer 3 (Architecture)** 與 **Layer 2 (Governance)** 的演化。您具備修改 `nexus/core/` 檔案的權限，但必須遵循以下鐵律：

## 🛡️ 核心修改鐵律 (Hard Laws)
- **1-bit Core 不可侵犯**: 嚴禁降低 `OneBitGate` 的基礎信心門檻 (0.5)。任何修改必須經過 Antigravity 物理簽署。
- **A/B 基準強制化**: 所有的性能優化必須檢附 `benchmark_ab.json`，且增益必須 > 5% 始可進入 Promotion。
- **零 Print()**: 嚴禁在核心路徑中使用 `print()`。所有遙測必須對齊 `logging.getLogger("nexus.core")`。

## ⚙️ 關鍵流程
1. **Sandbox Setup**: 執行 `nexus sandbox --expert` 初始化隔離環境。
2. **Refactor Alignment**: 修改後執行 `uv run scripts/ops/wiki_sync_check.py` 確保文碼對位。
3. **Formal Closeout**: 產出 v24.1-canonical 交付憑證。

---
Back to [[System Overview]]

## One-sentence summary
定義專家開發者在高權限階段的操作邊界、治理責任與交付約束。 [Source: 01_System/System - Unknowns and Conflicts.md]

## Role / responsibility
- 管控 `nexus/core` 重要路徑修改，確保不破壞信任門檻。 [Source: 01_System/MUSE_PROTO.md]
- 將性能、遙測與安全要求落實於實際重構與審核。 [Source: 06_Ops/Ops - Governance SLO Dashboard.md]

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 權限與職責的全域邏輯入口。 [Source: 00_Home/System Overview.md]
- **[MUSE_PROTO](../01_System/MUSE_PROTO.md)**: 行為邊界與交付規則參考。 [Source: 01_System/MUSE_PROTO.md]

## Downstream
- **[01_System/Nexus v24.0 Agent Handover & Truth Protocol](../01_System/Nexus v24.0 Agent Handover & Truth Protocol.md)**: 交接與真相責任對齊。 [Source: 01_System/Nexus v24.0 Agent Handover & Truth Protocol.md]
- **[06_Ops/Ops - Acceptance and Release.md](../06_Ops/Ops - Acceptance and Release.md)**: 專家變更封關依據。 [Source: 06_Ops/Ops - Acceptance and Release.md]

## Related modules / files
- `nexus/core/orchestrator.py`
- `01_System/MUSE_PROTO.md`
- `06_Ops/Ops - Governance Changelog.md`

## Source notes
- 開發規範結合系統知識庫與治理文檔。 [Source: 01_System/MUSE_PROTO.md]

## Open questions / conflicts
- [ ] 1-bit Core 是否需要更細化到模組級別的審批清單？
- [ ] 高權限任務是否需引入雙重人工簽核機制？

**[Source: 01_System/MUSE_PROTO.md]**

[[System Overview]]
