---
aliases: '[README_Agent, Agent Guide]'
confidence: high
last_compiled: '2026-05-06'
owner: agent
source_of_truth: compiled-wiki
status: active
tags: '[home, agent, governance]'
title: README Agent
type: home
version_scope: '[v26]'
---

# 🤖 README: Agent 執行導覽 (Agent Guide)
**[ROLE: AGENT | AUDIENCE: AI_DRONES]**

## 1. 代理義務 (Mandates)
所有的代理在進入 Nexus 工作區時，必須嚴格遵守：
- [[01_System/MUSE_PROTO|MUSE_PROTO v2.4]] (最高規約)
- [[01_System/Code_Ownership_Matrix|擁有權矩陣]] (禁止越權)

## 2. 核心指令集 (The CLI)
- `nexus run`: 執行 P-X-D-R-A-C 閉環。
- `nexus status`: 檢查信任分數與 mTLS 狀態。
- `nexus closeout`: 提交物理誠信契約。

## 3. 執碼邊界
- 僅限於 `allowed_paths`。
- 嚴禁修改 `.nexus/certs/` 與 `.obsidian/`。

---
**[NEXUS AGENT PROTOCOL: GOVERNANCE_ENFORCED]**

## One-sentence summary
Agent 作業頁面定義代理進入 Nexus 時的執行規範、邊界與責任。

## Role / responsibility
- 定義代理起步規範、權限邊界與命令使用順序。

## Upstream
- [[01_System/MUSE_PROTO|MUSE_PROTO]]
- [[01_System/Code_Ownership_Matrix|Code Ownership Matrix]]

## Downstream
- [[06_Ops/Ops - Wiki Page Type Contracts|Wiki Page Type Contracts]]
- [[05_Protocols/Protocol - Engineering Discipline|Protocol - Engineering Discipline]]

## Related modules / files
- [Source: 01_System/MUSE_PROTO.md]
- [[System Overview]]

## Source notes
- [Source: compiled-wiki]

## Open questions / conflicts
- 如何將此頁的角色規範同時對齊多語系代理（非英文提示）語意一致？
