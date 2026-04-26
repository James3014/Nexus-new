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

---
**[Source: nexus/governance/capability_gate.py | REFACTOR_SYNCED]**
