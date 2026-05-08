---
aliases: '[Tool Control, Phase Isolation, SKILL_GROUPS]'
confidence: high
last_audit: '2026-04-21 16:30'
last_compiled: '2026-04-21'
owner: agent
source_of_truth: nexus/governance/capability_gate.py
status: hardened
tags: '[governance, security, tools, capability]'
title: Governance - Capability Gate & Tool Isolation
---

# Governance - Capability Gate & Tool Isolation (v26 Hardened)

## One-sentence summary
本模組透過 **CapabilityGate** 實施 Phase-Level 的工具權限隔離，確保 Agent 在不同生命週期階段（P-X-D-R-A-C）僅能使用授權的工具集。

## 🛡️ 外觀模式與邊界 (Facade Boundaries)
為了維持系統解耦，Nexus 採用了「外觀模式 (Facade Pattern)」：
- **實體邏輯**: 位於 `nexus/governance/capability_gate.py`。
- **兼容外觀**: 位於 `nexus/core/capability_gate.py`，作為進入治理層的唯一受控入口。

## ⚙️ 階段工具隔離 (Tool Isolation Matrix)
系統將工具劃分為不同群組，並在運行時根據 `Phase` 枚舉進行動態注入：

| Phase (階段) | Key Tools (授權工具) | Governance Goal |
| :--- | :--- | :--- |
| **P (Plan)** | `read_file`, `git_status`, `list_dir` | 建立初步計畫，禁止修改。 |
| **X (Research)**| `search_web`, `grep_search`, `read_resource` | 外部知識檢索與深度代碼掃描。 |
| **D (Diagnose)**| `grep_search`, `run_command`, `command_status`| 定位根因，禁止執行編輯。 |
| **R (Repair)** | `replace_file`, `write_to_file`, `safe_patch` | 執行物理修改與補丁生成。 |
| **A (Audit)** | `pytest`, `git_diff`, `command_status` | 驗證修改誠信，禁止進一步修改。 |
| **C (Crystallize)**| `git_commit`, `write_memory` | 提交變更並捕捉教訓。 |

## 🛡️ 實體執行規約
- **JIT Injection**: 所有的工具集均透過 `managed_toolsets()` 進行即時過濾。
- **Hidden Tools**: 任何未在當前階段授權的工具將對 Agent 隱藏，物理阻斷「越權調用」的可能性。

## Role / responsibility
- 提供 phase 級工具訪問邊界，控制不同階段可用工具範圍。 [Source: nexus/governance/capability_gate.py]
- 落實治理隔離，阻斷越權工具調用。 [Source: 06_Ops/Ops - Governance Changelog.md]

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 定義全域治理入口。 [Source: 00_Home/System Overview.md]
- **[Protocol - Evidence Map](../05_Protocols/Protocol - Evidence Map.md)**: 對應治理證據格式。 [Source: 05_Protocols/Protocol - Evidence Map.md]

## Downstream
- **[06_Ops/Ops - Ownership and Review SLA](../06_Ops/Ops - Ownership and Review SLA.md)**: 執行能力邊界責任稽核。 [Source: 06_Ops/Ops - Ownership and Review SLA.md]
- **[Protocol - Security & Tool Guard Registry](../02_Modules/Module - Security and Tool Guard Registry.md)**: 核對工具注入點映射。 [Source: 02_Modules/Module - Security and Tool Guard Registry.md]

## Related modules / files
- `nexus/governance/capability_gate.py`
- `nexus/core/capability_gate.py`
- `02_Modules/Module - Security and Tool Guard Registry.md`

## Source notes
- 能力隔離邏輯依據治理路徑與實際程式碼一致。 [Source: nexus/governance/capability_gate.py]
- 可回放驗證結果可在 CI Gate 與 Audit Log 中查詢。 [Source: scripts/ops/ci_gate.py]

## Open questions / conflicts
- [ ] 是否需加入能力組跨任務配額與突發切斷保護？
- [ ] 是否需要更細顆粒的 tool cooldown 防止高頻錯誤重試？

**[Source: nexus/governance/capability_gate.py]**

[[System Overview]]
