---
id: code_to_architecture_matrix
type: doc
status: active
created: 2026-04-07T07:29:31Z
updated: 2026-04-07T07:29:31Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: nexus_wiki_vault/06_Ops/Reference/docs/code_to_architecture_matrix.md
---
Waiver: 00_Home/[[System Overview]].md
[source: 00_Home/[[System Overview]].md]
## One-sentence summary
- Pending detailed [[documentation]].

## Role / responsibility
- Pending detailed [[documentation]].

## Upstream
- Pending detailed [[documentation]].

## Downstream
- Pending detailed [[documentation]].

## Related modules / files
- Pending detailed [[documentation]].

## Source notes
- Pending detailed [[documentation]].

## Open questions / conflicts
- Pending detailed [[documentation]].

---
# Code to Architecture Matrix

## Purpose
此文件追蹤 Nexus 每個核心架構概念與其對應代碼實作位置。

---

## Core Architecture → Code Mapping

| 架構角色 | 對應代碼 | 位置 |
|---|---|---|
| Commander | `NexusEngine` | `nexus/engine/coordinator.py` |
| State Contract | `NexusState` | `nexus/core/state_contracts.py` |
| Context Assembler | `ContextHub` | `nexus/core/context_hub.py` |
| Reviewer / Audit Gate | `CodexLoopV2` | `nexus/services/reviewer.py` |
| Persistence | `StateIO` | `nexus/core/state_io.py` |
| Skills Router | `SkillsRouter` | `nexus/core/router.py` |

---

## Conversation Governance — Implicit → Implemented

| 組件 | 舊狀態 | 現狀 |
|---|---|---|
| Conversation state 容器 | 無 (ad-hoc `metadata` dict) | `metadata["conversation"]` + helper methods |
| Conversation context pack | 無 | `ContextHub.assemble_conversation_pack()` |
| Conversation audit | 無 (走 code audit 路徑) | `CodexLoopV2 mode="conversation"` 完全 bypass code path |
| Dynamic return routing | 固定回 D | `NexusEngine.run_bug()` 依 `return_target_phase` 分流 D/X/R |
| Persistence discipline | 無強制 | 每次 helper 更新後強制 `StateIO.save_global_state()` |

> **備註**: Conversation Governance 目前實作在 Engine + ContextHub 內部 (implicit governance)。
> 未來可考慮抽出獨立 Conversation Governance Layer，但這不是 v1.6 MVP 必要條件。

---

## Phase Routing

```
task_type = "conversation"
  → P: init_conversation()
  → D: assemble_conversation_pack() → diagnose user intent
  → X: (if needs_research) external lookup
  → R: generate answer_draft
  → A: CodexLoopV2(mode="conversation") → audit level: skip/light/full
      APPROVED / SKIPPED_QUOTA → C
      REJECTED + return_target_phase → back to D / X / R
  → C: crystallize high-value lessons
```


---
[[System Overview]]