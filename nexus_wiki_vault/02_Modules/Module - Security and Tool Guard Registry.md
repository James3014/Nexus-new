---
title: Module - Security and Tool Guard Registry
aliases: [Security Guard, Access Control, Tool Lockdown]
type: module
status: active
version_scope: [v22, v23]
source_of_truth: nexus/core/capability_gate.py
related_pages:
  - "[[Module - Guard and Gate Control]]"
  - "[[Module - Implementation Responsibility Matrix]]"
tags: [core, security, guard, lock, validator]
last_compiled: 2026-04-06
confidence: high
owner: agent
---

# Module - Security and Tool Guard Registry

## One-sentence summary
本模組集合了 Nexus 的安全性防線、存取控制列表、工具鎖定機制與運算資源硬化驗證器。 [Source: nexus/core/capability_gate.py]

## Role / responsibility
- **權限防護**: 定義 ACL 並以此實施工具級別的細粒度權限管控。
- **動態注入控管**: 使用 `JIT Tool Injector` 確保護欄 (Guards) 與工具並行注入。
- **物理鎖定**: 在高風險階段硬性關切所有寫入路徑。

## Security Component Registry (安全組件登記)

| Guard / Logic | Responsibility (職責) | Source (Path) |
|---|---|---|
| **Access Control List** | 基於身分與特權的工具存取標記。 | [Source: nexus/core/access_control_list.py] |
| **Capability Gate** | 動態 JIT 工具分發與 Phase 物理隔離。 | [Source: nexus/core/capability_gate.py] |
| **Gate Evaluator** | 閘門邏輯求值與安全規則匹配。 | [Source: nexus/core/gate_evaluator.py] |
| **JIT Tool Injector** | 運行時工具即時注入與驗證。 | [Source: nexus/core/jit_tool_injector.py] |
| **Tool Lockdown** | 特定高風險階段的工具全域鎖定。 | [Source: nexus/core/tool_lockdown.py] |
| **Project Sentinel** | 全局哨兵監控，處理跨 Agent 風險。 | [Source: nexus/core/project_sentinel.py] |
| **Hazard Classifier** | 意圖與操作風險等級分類 (v23)。 | [Source: nexus/core/hazard_classifier.py] |
| **Hardened Validator** | 針對物理路徑與系統呼叫的二進位級驗證。 | [Source: nexus/core/hardened_validator.py] |
| **Subagent Armor** | 強化子代理 (Sub-agents) 執行邊界防禦。 | [Source: nexus/core/subagent_armor.py] |
| **Phantom Detect** | 偵測並攔截惡意「幽靈」進程。 | [Source: nexus/core/phantom_detect.py] |

## Upstream
- **[[System Overview]]**: 全域安全性導航。
- **MUSE-NEXUS Spec**: 要求系統必須具備 Zero-Trust 工具隔離能力。

## Downstream
- **[[Module - Implementation Responsibility Matrix]]**: 安全防護模組與物理檔案映射。
- **[[Module - Guard and Gate Control]]**: 深層技術實作對接。

## Related modules / files
- `nexus/core/capability_gate.py`: 主閘門。 [Code: nexus/core/capability_gate.py]
- `nexus/core/tool_lockdown.py`: 本地鎖定。 [Code: nexus/core/tool_lockdown.py]
- `nexus/core/access_control_list.py`: 存取列表。 [Code: nexus/core/access_control_list.py]

## Source notes
- v22 Engine Spec: 規定「凡涉及寫入操作 (Write-path)，必須通過 JIT 標籤檢查」。 [Source: Spec v22]

## Open questions / conflicts
- [ ] **Cross-OS Compatibility**: 物理進程鎖定在 macOS 與 Linux 環境下的行為一致性。

---
Back to [[System Overview]]
