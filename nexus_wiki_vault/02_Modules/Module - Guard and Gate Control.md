---
aliases:
- Gate Control
- Nexus Guard
- Security Gate
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[Module - Security and Tool Guard Registry](Module - Security and Tool Guard Registry.md)'
- '[Module - Implementation Responsibility
  Matrix](Module - Implementation Responsibility Matrix.md)'
source_of_truth: nexus/core/capability_gate.py
status: active
tags:
- core
- guard
- gate
- security
- access
title: Module - Guard and Gate Control
type: module
version_scope:
- v22
- v23
---



# Module - Guard and Gate Control

## One-sentence summary
本頁深入解析 Nexus 的安全閘門實作、工具權限動態判定與基於 Phase 的執行沙盒化機制。 [Source: nexus/core/capability_gate.py]

## Role / responsibility
- **權限閘門 (Capability Gate)**: 作為工具調用的最終檢查點，驗證當前 Phase 是否具備執行權限。
- **安全護欄 (Safety Guards)**: 在代碼修改、系統指令執行前進行靜態與動態掃描。
- **身分驗證**: 確保工具調用方符合該項權限的「指紋」特徵。

## Guard Logic Registry (護欄邏輯登記)

| Logic Component | Responsibility (職責) | Source (Path) |
|---|---|---|
| **Capability Gate** | 統籌工具存取權限的開關與驗證。 | [Source: nexus/core/capability_gate.py] |
| **Tool Lock** | 硬性禁止在非預期階段調用特定敏感工具。 | [Source: nexus/core/tool_lockdown.py] |
| **ACL Engine** | 具體執行權限清單 (Allowlist) 的查詢與匹配。 | [Source: nexus/core/access_control_list.py] |
| **Injection Guard** | 檢測並防止針對工具參數的惡意注入攻擊。 | [Source: nexus/core/jit_tool_injector.py] |

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 安全架構全景。
- **[Module - Security and Tool Guard Registry](Module - Security and Tool Guard Registry.md)**: 提供權限清單與組件實體。

## Downstream
- **[Module - Implementation Responsibility Matrix](Module - Implementation Responsibility Matrix.md)**: 映射至物理檔案。
- **[[Ops - CI/CD Promotion Gate]]**: 安全閘門狀態作為核心發版基準。

## Related modules / files
- `nexus/core/capability_gate.py`: 權限閘門。 [Code: nexus/core/capability_gate.py]
- `nexus/core/access_control_list.py`: 存取控制。 [Code: nexus/core/access_control_list.py]

## Source notes
- v22 Engine Spec: 要求安全性檢查必須在工具真正執行前 10ms 內完成鎖定。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Bypass Scenarios**: 緊急維護模式下如何安全且可審計地繞過特定閘門。

---
Back to [System Overview](../00_Home/System Overview.md)

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]