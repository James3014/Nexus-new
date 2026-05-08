---
aliases: '[Identity Vault, Agent Identity]'
confidence: medium
last_compiled: '2026-05-06'
owner: agent
source_of_truth: compiled-wiki
status: active
tags: '[system, identity, rbac]'
title: Identity Vault
type: system
version_scope: '[v24]'
---

# Identity Vault: Nexus v24 Agent Ecosystem
- learn_mode_agent:
  - role: Autonomous Ingest & Sync
  - boundary: [research/learn, wiki/knowledge]
  - lifecycle: Init/Active/Archive
  - forbidden: [modify:core/engine_core, invoke:manual_patching]

- codex_supervisor:
  - role: Codebase Audit & Guardrail
  - boundary: [nexus/core, nexus/delivery]
  - lifecycle: Init/Active/Archive
  - forbidden: [modify:wiki, invoke:autonomic_routing]

- gemini_router:
  - role: Intent Classifier
  - boundary: [nexus/app/entrypoint]
  - lifecycle: Init/Active/Archive
  - forbidden: [read:secret_ledger, modify:core/logic]

## One-sentence summary
身份保險庫定義各類 Agent 的角色、權限邊界與生命週期，是治理與運行時隔離的基線。

## Role / responsibility
- 提供 Agent 身份規格，約束可執行範圍與禁止行為。

## Upstream
- [[01_System/Code_Ownership_Matrix|Code Ownership Matrix]]
- [[01_System/System Relationship and Dependency Graph|System Relationship and Dependency Graph]]

## Downstream
- [[06_Ops/Ops - Acceptance and Release|Acceptance and Release]]
- [[06_Ops/Ops - Closeout Hard Gate|Closeout Hard Gate]]

## Related modules / files
- [Source: compiled-wiki]
- [[System Overview]]

## Source notes
- [Source: compiled-wiki]

## Open questions / conflicts
- 是否要引入「角色能力到期」與「自動吊銷」機制以防止越權殘留？
